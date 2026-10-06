# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2023-2025 Adrian Przekwas adrian.v.przekwas@gmail.com   *
# *                                                                         *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import logging

from enum import Enum
from dataclasses import dataclass

from pivy.coin import SoSeparator
from pivy.coin import SbVec3f, SbVec4f, SbRotation
from pivy.coin import SoTransform, SoTranslation
from pivy.coin import SoSphere
from pivy.coin import SoVertexProperty, SoLineSet
from pivy.coin import SoBaseColor, SbColor
from pivy.coin import SoRayPickAction, SoPickStyle
from pivy.coin import SoSwitch, SO_SWITCH_NONE, SO_SWITCH_ALL

from freecad.BlocksCAD.render.controller_shape import build_fallback


LOW_STATE = 0.3
HIGH_STATE = 0.7


class AnInpEv(Enum):
    JUST_RELEASED = 1
    RELEASED = 2
    JUST_PRESSED = 3
    PRESSED = 4


@dataclass
class ButtonsState:
    grab: float = 0.0
    grab_ev: int = AnInpEv.RELEASED
    lever_x: float = 0.0
    lever_y: float = 0.0


class xrController:
    def __init__(self, iden=0, ray=False, log_level=logging.WARNING):
        logging.basicConfig()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        # this node contains everything that moves with controller, SoSwitch
        # can behave like a standard node
        self.controller_node = SoSwitch()
        self.controller_node.whichChild = SO_SWITCH_ALL
        self.iden = iden
        self.buttons_state = ButtonsState()
        self.con_localtransform = SoTransform()
        self.con_transform = SoTransform()      # the pointer pose: what tools pick with (the aim pose, or the tip in tip mode)
        self.aim_transform = SoTransform()      # the aim pose: where the generated controller shape is drawn
        self.reach = None                       # metres a pick ray reaches (tip mode: the tip touches); None is unlimited
        self.ray_enabled = True                 # tip mode shows no inherited ray
        if ray:
            self.ray_node = SoSwitch()
            self.add_picking_ray()
        else:
            self.ray_node = None
        self.runtime_model = None
        self.picked_tail = None
        self.picked_tex_coords = SbVec4f(0, 0, 0, 0)
        self.picked_normal = SbVec3f(0.0, 0.0, 0.0)
        self.add_controller_shape()

    def add_controller_shape(self):
        """Scene of the visible controller: a generated shape at the aim pose, or the runtime model at its own pose."""
        con_sep = SoSeparator()
        unpickable = SoPickStyle()
        unpickable.style = SoPickStyle.UNPICKABLE
        con_sep.addChild(unpickable)
        self.fallback_switch = SoSwitch()
        fallback_sep = SoSeparator()
        fallback_sep.addChild(self.aim_transform)
        self.fallback_model = build_fallback("left" if self.iden == 0 else "right")
        fallback_sep.addChild(self.fallback_model.root)
        self.fallback_switch.addChild(fallback_sep)
        self.fallback_switch.whichChild = SO_SWITCH_ALL
        con_sep.addChild(self.fallback_switch)
        self.runtime_switch = SoSwitch()
        self.runtime_sep = SoSeparator()
        self.model_transform = SoTransform()
        self.runtime_sep.addChild(self.model_transform)
        self.runtime_switch.addChild(self.runtime_sep)
        self.runtime_switch.whichChild = SO_SWITCH_NONE
        con_sep.addChild(self.runtime_switch)
        self.controller_node.addChild(con_sep)

    def set_runtime_model(self, model):
        """Show a runtime-provided model (render.gltf_coin.Model) instead of the generated shape; None restores the shape."""
        if self.runtime_model is not None:
            self.runtime_sep.removeChild(self.runtime_model.root)
        self.runtime_model = model
        if model is None:
            self.runtime_switch.whichChild = SO_SWITCH_NONE
            self.fallback_switch.whichChild = SO_SWITCH_ALL
        else:
            self.runtime_sep.addChild(model.root)
            self.runtime_switch.whichChild = SO_SWITCH_ALL
            self.fallback_switch.whichChild = SO_SWITCH_NONE

    def update_model_pose(self, position, orientation, world_transform):
        """Pose of the runtime model (stage frame, metres); combined with the artificial world movement like the aim pose."""
        local = SoTransform()
        local.translation.setValue(SbVec3f(*position))
        local.rotation.setValue(SbRotation(*orientation))
        combined = SoTransform()
        combined.copyFieldValues(world_transform)
        combined.combineLeft(local)
        self.model_transform.copyFieldValues(combined)
        self.model_transform.center.setValue(SbVec3f(0, 0, 0))

    def apply_node_states(self, states):
        """Animate the runtime model from `openxr_models.NodeState`s."""
        if self.runtime_model is None:
            return
        for state in states:
            part = self.runtime_model.part(state.name)
            if part is not None:
                part.set_visible(state.visible)
                part.set_pose(state.position, state.orientation)

    def add_picking_ray(self):
        self.ray_vtxs = SoVertexProperty()
        # set first vertex, later update to center of the controller (global
        # location)
        self.ray_vtxs.vertex.set1Value(0, 0, 0, 0)
        # set second vertex, later update to point of intersection ray with hit
        # object (global location)
        self.ray_vtxs.vertex.set1Value(1, 0, 0, 1)
        ray_line = SoLineSet()
        ray_line.vertexProperty = self.ray_vtxs
        self.ray_color = SoBaseColor()
        self.make_ray_red()
        # required since SoSwitch behaves like a node not like a separator
        ray_sep = SoSeparator()
        ray_sep.addChild(self.ray_color)
        ray_sep.addChild(ray_line)
        self.sph_trans = SoTranslation()
        self.sph_trans.translation.setValue(0, 0, 0)
        self.sph_node = SoSwitch()
        self.sph_node.addChild(self.sph_trans)
        ray_sph = SoSphere()
        ray_sph.radius.setValue(0.02)
        self.sph_node.addChild(ray_sph)
        ray_sep.addChild(self.sph_node)
        self.ray_node.addChild(ray_sep)

    def make_ray_red(self):
        self.ray_color.rgb = SbColor(1, 0, 0)

    def make_ray_green(self):
        self.ray_color.rgb = SbColor(0, 1, 0)

    def get_controller_scenegraph(self):
        return self.controller_node

    def get_ray_scenegraph(self):
        return self.ray_node

    def update_pose(self, position, orientation, world_transform, pointer_position=None, pointer_orientation=None):
        """Aim pose in the stage frame: position (x, y, z) and orientation quaternion (x, y, z, w). The pointer pose (laser origin
        and direction, or the tip) defaults to the aim pose; picking and the tools use the pointer pose."""
        self._set_transform(self.aim_transform, position, orientation, world_transform)
        self._set_transform(self.con_transform, pointer_position or position, pointer_orientation or orientation, world_transform)

    def _set_transform(self, target, position, orientation, world_transform):
        self.con_localtransform.translation.setValue(SbVec3f(*position))
        self.con_localtransform.rotation.setValue(SbRotation(*orientation))
        combined = SoTransform()
        combined.copyFieldValues(world_transform)
        # combine real hmd and artificial movement
        combined.combineLeft(self.con_localtransform)
        target.copyFieldValues(combined)
        target.center.setValue(SbVec3f(0, 0, 0))

    def find_ray_axis(self):
        rot = self.con_transform.rotation.getValue()
        ray_axis = rot.multVec(SbVec3f(0, 0, 1))
        return ray_axis

    def show_ray(self):
        if self.ray_node and self.ray_enabled:
            self.ray_node.whichChild = SO_SWITCH_ALL

    def hide_ray(self):
        if (self.ray_node):
            self.ray_node.whichChild = SO_SWITCH_NONE

    # this is used if the ray should show point calculated elsewhere
    # if there is no point it will show just ray, without sphere at the end
    def show_ray_ext(self, end_vec=None):
        if not (self.ray_node and self.ray_enabled):
            return SbVec3f(0, 0, 0)
        self.ray_node.whichChild = SO_SWITCH_ALL
        ray_axis = self.find_ray_axis()
        ray_start_vec = self.con_transform.translation.getValue()
        ray_end_vec = self.con_transform.translation.getValue() - ray_axis
        if (end_vec):
            self.sph_node.whichChild = SO_SWITCH_ALL
            ray_end_vec = end_vec
        self.sph_trans.translation.setValue(ray_end_vec)
        self.ray_vtxs.vertex.set1Value(0, ray_start_vec)
        self.ray_vtxs.vertex.set1Value(1, ray_end_vec)
        return ray_end_vec

    def show_controller(self):
        self.controller_node.whichChild = SO_SWITCH_ALL

    def hide_controller(self):
        self.controller_node.whichChild = SO_SWITCH_NONE

    def find_picked_coin_object(
            self,
            separator,
            vp_reg,
            near_plane,
            far_plane,
            camera=None):
        ray_axis = self.find_ray_axis()
        ray_start_vec = self.con_transform.translation.getValue()
        ray_end_vec = self.con_transform.translation.getValue() - ray_axis
        if self.reach is not None:
            far_plane = min(far_plane, self.reach)

        # picking ray
        con_pick_action = SoRayPickAction(vp_reg)
        if (camera):
            camera.position.setValue(ray_start_vec)
            camera.pointAt(ray_end_vec)
            camera.nearDistance = near_plane
            camera.farDistance = far_plane
            # pixel in the middle of the viewport region
            con_pick_action.setPoint(vp_reg.getWindowSize() / 2)
        else:
            # direction is reversed controller Z axis
            con_pick_action.setRay(
                ray_start_vec, -1 * ray_axis, near_plane, far_plane)

        self.ray_vtxs.vertex.set1Value(0, ray_start_vec)
        self.ray_vtxs.vertex.set1Value(1, ray_end_vec)

        con_pick_action.apply(separator)
        picked_p_coords = SbVec3f(0.0, 0.0, 0.0)
        picked_point = con_pick_action.getPickedPoint()

        if (picked_point):
            picked_p_coords = picked_point.getPoint()
            self.sph_node.whichChild = SO_SWITCH_ALL
            self.sph_trans.translation.setValue(picked_p_coords)
            self.ray_vtxs.vertex.set1Value(1, picked_p_coords)
            self.picked_tail = picked_point.getPath().getTail()
            self.picked_tex_coords = picked_point.getTextureCoords()
            self.picked_normal = picked_point.getNormal()
        else:
            # show the sphere only if an object is pickable
            self.sph_node.whichChild = SO_SWITCH_NONE

        # returning value seems to be safer
        return picked_point, picked_p_coords.getValue()

    def get_picked_tail(self):
        return self.picked_tail

    def get_picked_tex_coords(self):
        return self.picked_tex_coords.getValue()

    def get_picked_normal(self):
        return self.picked_normal.getValue()

    def get_rotation_from_picked_normal(self):
        normal = self.picked_normal
        # SbRotation (from, to)
        # default for SbRotation axis is (0.0, 0.0, 1.0)
        rot = SbRotation(SbVec3f(0, 0, 1), normal)
        return rot.getValue()

    def update_lever(self, x_lever_value, y_lever_value):
        self.buttons_state.lever_x = x_lever_value
        self.buttons_state.lever_y = y_lever_value
        self.logger.debug(
            "Controller %d X %.2f Y %.2f",
            self.iden,
            self.buttons_state.lever_x,
            self.buttons_state.lever_y)

    def update_grab(self, grab_value):
        self.buttons_state.grab = grab_value
        if (self.buttons_state.grab > HIGH_STATE):
            if (self.buttons_state.grab_ev == AnInpEv.RELEASED
                    or self.buttons_state.grab_ev == AnInpEv.JUST_RELEASED):
                self.buttons_state.grab_ev = AnInpEv.JUST_PRESSED
            else:
                self.buttons_state.grab_ev = AnInpEv.PRESSED
        elif (self.buttons_state.grab < LOW_STATE):
            if (self.buttons_state.grab_ev == AnInpEv.PRESSED
                    or self.buttons_state.grab_ev == AnInpEv.JUST_PRESSED):
                self.buttons_state.grab_ev = AnInpEv.JUST_RELEASED
            else:
                self.buttons_state.grab_ev = AnInpEv.RELEASED

        self.logger.debug(
            "Controller %d Grab %.2f",
            self.iden,
            self.buttons_state.grab)

    def get_local_transf(self):
        return self.con_localtransform

    def get_global_transf(self):
        return self.con_transform

    def get_buttons_states(self):
        return self.buttons_state
