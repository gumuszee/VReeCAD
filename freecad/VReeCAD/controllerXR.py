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

"""The scene node of one controller: the generated shape at the aim pose or the model the runtime provides, hidden while the
controller is not tracked. The pose of the node comes from the `InputFrame`; picking and the tools never use it."""

from pivy.coin import SoSeparator
from pivy.coin import SoTransform
from pivy.coin import SoPickStyle
from pivy.coin import SoSwitch, SO_SWITCH_NONE, SO_SWITCH_ALL

from freecad.VReeCAD.render.controller_shape import build_fallback
from freecad.VReeCAD.render.model_anchor import button_anchor, stage_frame


class _PoseWriter:
    """Writes the pose of a `SoTransform`, with the fields looked up once and only when the pose changes."""

    def __init__(self, transform):
        self._move, self._turn = transform.translation, transform.rotation
        self._key = None

    def set(self, position, orientation):
        key = (tuple(position), tuple(orientation))
        if key != self._key:
            self._key = key
            self._move.setValue(*position)
            self._turn.setValue(*orientation)


class xrController:
    def __init__(self, iden=0):
        self.iden = iden
        # this node contains everything that moves with the controller; a SoSwitch can behave like a standard node
        self.controller_node = SoSwitch()
        self.controller_node.whichChild = SO_SWITCH_ALL
        self._shown = True
        self._which = self.controller_node.whichChild
        self.aim_transform = SoTransform()      # the aim pose: where the generated controller shape is drawn
        self._aim_writer = _PoseWriter(self.aim_transform)
        self.runtime_model = None
        self._aim_pose = None                   # (position, orientation) the generated shape is drawn at, stage frame
        self._model_pose = None                 # the same for the runtime model
        self._anchors = {}                      # id of a model -> where its button is, in the frame of the model
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
        self._model_writer = _PoseWriter(self.model_transform)
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

    def part_frame(self, names, lift=0.0):
        """(position, right, forward, up) in the stage of the top of the first of the named parts of the controller model, `lift`
        metres above it, with the axes of the model; None when the model has none of the parts or its pose is not known."""
        model, pose = (self.runtime_model, self._model_pose) if self.runtime_model is not None else (self.fallback_model, self._aim_pose)
        if model is None or pose is None:
            return None
        key = (id(model), names, lift)
        anchor = self._anchors.get(key)
        if anchor is None:                                   # a part that could not be found is looked for again next time
            anchor = self._anchors[key] = button_anchor(model, names, lift)
        return None if anchor is None else stage_frame(pose, anchor)

    def update_pose(self, position, orientation):
        """Aim pose in the stage frame: position (x, y, z) and orientation quaternion (x, y, z, w)."""
        self._aim_pose = (tuple(position), tuple(orientation))
        self._aim_writer.set(position, orientation)

    def update_model_pose(self, position, orientation):
        """Pose of the runtime model (stage frame, metres)."""
        self._model_pose = (tuple(position), tuple(orientation))
        self._model_writer.set(position, orientation)

    def apply_node_states(self, states):
        """Animate the runtime model from `openxr_models.NodeState`s."""
        if self.runtime_model is None:
            return
        for state in states:
            part = self.runtime_model.part(state.name)
            if part is not None:
                part.set_visible(state.visible)
                part.set_pose(state.position, state.orientation)

    def get_controller_scenegraph(self):
        return self.controller_node

    def show_controller(self):
        if not self._shown:
            self._shown = True
            self._which.setValue(SO_SWITCH_ALL)

    def hide_controller(self):
        if self._shown:
            self._shown = False
            self._which.setValue(SO_SWITCH_NONE)
