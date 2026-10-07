# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""Sim backend: a scripted head and two controllers without a headset (docs/design.md, Test strategy).

`SimInput` produces `InputFrame`s from poses and button values that a script sets, with the same edge detection as the
OpenXR backend. `SimSession` adds a Coin scene (the FreeCAD document scene, generated controller shapes at the hand poses)
and renders it offscreen from the head or either eye, so a test can "move in VR space" and photograph the result.

Stage frame: metres, Y up, the head looks along -Z. The document scene is placed like in the headset: millimetres to
metres and Z up to Y up.
"""

import math

from freecad.BlocksCAD.core.mathutil import look_at, quat_from_axis_angle, quat_multiply, rotate  # noqa: F401  (re-exported for scripts)
from freecad.BlocksCAD.input import HandInput, InputFrame, InputTracker, Pose

IPD = 0.064  # metres between the eyes


class SimInput:
    """Scripted input source; `frame()` advances the clock and returns an `InputFrame` with edges."""

    HAND_FIELDS = ("trigger", "grip", "stick", "stick_click", "button1", "button2", "menu", "aux1", "aux2")

    def __init__(self, profile="/interaction_profiles/valve/frame_controller_valve"):
        self.profile = profile
        self.time = 0.0
        self.head = Pose((0.0, 1.6, 0.0), (0.0, 0.0, 0.0, 1.0), True)
        self.hands = [HandInput(), HandInput()]
        self.set_hand(0, position=(-0.25, 1.2, -0.35))
        self.set_hand(1, position=(0.25, 1.2, -0.35))
        self._tracker = InputTracker()

    def set_head(self, position=None, orientation=None, look_at_point=None):
        pos = tuple(position) if position is not None else self.head.position
        if look_at_point is not None:
            orientation = look_at(pos, look_at_point)
        ori = tuple(orientation) if orientation is not None else self.head.orientation
        self.head = Pose(pos, ori, True)

    def set_hand(self, hand, position=None, orientation=None, point_at=None, **inputs):
        """Pose and input values of one hand (0 = left, 1 = right). `point_at` aims the controller (-Z) at a stage point."""
        h = self.hands[hand]
        pos = tuple(position) if position is not None else h.aim.position
        if point_at is not None:
            orientation = look_at(pos, point_at)
        ori = tuple(orientation) if orientation is not None else h.aim.orientation
        h.aim = Pose(pos, ori, True)
        h.grip_pose = Pose(pos, ori, True)
        for name, value in inputs.items():
            if name not in self.HAND_FIELDS:
                raise ValueError(f"unknown input '{name}'")
            setattr(h, name, value)

    def frame(self, dt=1.0 / 72.0):
        self.time += dt
        frame = InputFrame(time=self.time, head=self.head, profile=self.profile)
        frame.hands = tuple(HandInput(**{f: getattr(h, f) for f in (
            "aim", "grip_pose", "trigger", "grip", "stick", "stick_click", "button1", "button2", "menu", "aux1", "aux2")}) for h in self.hands)
        return self._tracker.update(frame)


class SimSession:
    """Input plus a renderable scene. `document_scene` is the FreeCAD scene graph (millimetres, Z up) or None."""

    def __init__(self, document_scene=None, profile="/interaction_profiles/valve/frame_controller_valve", actions=None):
        from pivy import coin
        from freecad.BlocksCAD import tools
        import freecad.BlocksCAD.tools.primitives  # noqa: F401  (registers the tools)
        import freecad.BlocksCAD.tools.select  # noqa: F401
        import freecad.BlocksCAD.tools.move  # noqa: F401
        import freecad.BlocksCAD.tools.pushpull  # noqa: F401
        import freecad.BlocksCAD.tools.points  # noqa: F401
        from freecad.BlocksCAD.render.controller_shape import build_fallback
        from freecad.BlocksCAD.render.ghost import Ghost
        from freecad.BlocksCAD.render.highlight import Highlights
        from freecad.BlocksCAD.ui.controller import UiController
        self._coin = coin
        self.input = SimInput(profile)
        self.last_frame = None
        self.ui_update = None
        self.actions = {} if actions is None else actions
        self.ui = UiController(tools.names(), tools.label_of, self.actions, use_user_layout=False, tool_hint=tools.hint_of)
        self.navigator = self.ui.navigator
        self.scene = coin.SoSeparator()
        self.scene.ref()
        environment = coin.SoEnvironment()
        environment.ambientIntensity = 0.7
        self.scene.addChild(environment)
        light = coin.SoDirectionalLight()
        light.direction.setValue(-0.4, -0.8, -0.6)
        self.scene.addChild(light)
        self.nav_xf = coin.SoTransform()
        doc = coin.SoSeparator()                 # the document: navigation, millimetres to metres, Z up
        doc.addChild(self.nav_xf)
        xf = coin.SoTransform()
        xf.scaleFactor.setValue(0.001, 0.001, 0.001)
        xf.rotation.setValue(coin.SbRotation(coin.SbVec3f(1, 0, 0), -math.pi / 2))
        doc.addChild(xf)
        if document_scene is not None:
            doc.addChild(document_scene)
        self.ghost = Ghost()                     # the preview of a shape being made lives in document space
        doc.addChild(self.ghost.root)
        self.highlights = Highlights()           # hover and selection, also in document space
        doc.addChild(self.highlights.root)
        self.scene.addChild(doc)
        self.doc_scene = doc                     # where a script may attach more of the document (view provider nodes)
        self._setup_tools()
        self.ui.part_frame = self._part_frame
        self.ui.values_source = self._values_source
        self.hand_transforms = []
        self.hand_models = []
        self.scene.addChild(self.ui.root)
        for side in ("left", "right"):
            sep = coin.SoSeparator()
            xf = coin.SoTransform()
            sep.addChild(xf)
            model = build_fallback(side)
            sep.addChild(model.root)
            self.scene.addChild(sep)
            self.ui.add_occluder(sep)
            self.hand_transforms.append(xf)
            self.hand_models.append(model)
        self.scene.addChild(self.ui.overlay)   # last: drawn over everything

    def _setup_tools(self):
        """A tool manager with the services of the headset host, so tools run in the Sim as they do in the headset."""
        from freecad.BlocksCAD import tools
        from freecad.BlocksCAD.core import stage, units
        context = tools.ToolContext(host=self, dominant=self.ui.tool_hand)
        context.services.update({
            "cursor": lambda hand: self.ui.cursor(self.last_frame.hands[hand]),
            "to_document": lambda point: stage.to_document(self.navigator.world, point),
            "document": self._document,
            "trigger_free": lambda: not (self.ui_update is not None and self.ui_update.consume_trigger),
            "ghost": self.ghost,
            "highlight": self.highlights,
            "hand_rotation": lambda hand: stage.orientation_to_document(self.navigator.world, self.last_frame.hands[hand].aim.orientation),
            "mm_per_metre": lambda: 1.0 / (stage.MM_TO_STAGE * self.navigator.world.scale),
            "toast": self.ui.toast,
            "readout": self.ui.set_readout,
            "format_length": lambda mm: units.format_length(mm, self.ui.system),
        })
        self.tool_manager = tools.ToolManager(context)

    @staticmethod
    def _document():
        try:
            import FreeCAD
            return FreeCAD.ActiveDocument
        except ImportError:
            return None

    def _values_source(self):
        """The object the value panels follow: the first editable object selected in the active document."""
        from freecad.BlocksCAD.cad import values
        return values.source(self._document())

    def _part_frame(self, hand, names, lift=0.0):
        """(position, right, forward, up) of a part of the generated controller of a hand, in the stage frame."""
        from freecad.BlocksCAD.render.model_anchor import button_anchor, stage_frame
        anchor = button_anchor(self.hand_models[hand], names, lift)
        aim = self.last_frame.hands[hand].aim if self.last_frame is not None else None
        if anchor is None or aim is None or not aim.tracked:
            return None
        return stage_frame((aim.position, aim.orientation), anchor)

    def select_tool(self, name):
        """Make a registered tool the active tool (the same as choosing its face)."""
        self.tool_manager.activate(name)
        self.ui.active_tool = self.tool_manager.active

    def frame(self, dt=1.0 / 72.0):
        """Advance the simulated time, pose the controller models and return the `InputFrame`."""
        from freecad.BlocksCAD.render.controller_shape import animate
        frame = self.input.frame(dt)
        self.last_frame = frame
        self.ui.active_actions = {f"tool:{self.tool_manager.active_name}"}
        self.ui.active_tool = self.tool_manager.active
        self.ui_update = self.ui.update(frame)
        self.tool_manager.update(frame)
        world = self.navigator.world
        self.nav_xf.translation.setValue(*world.position)
        self.nav_xf.rotation.setValue(*world.rotation)
        self.nav_xf.scaleFactor.setValue(world.scale, world.scale, world.scale)
        for hand, xf in enumerate(self.hand_transforms):
            aim = frame.hands[hand].aim
            xf.translation.setValue(*aim.position)
            xf.rotation.setValue(*aim.orientation)
            animate(self.hand_models[hand], frame.hands[hand])
        self.last_frame = frame
        return frame

    def render(self, eye="head", size=(1024, 768), fov=1.2, **kwargs):
        """Render from the head (`eye` = "head", "left" or "right") and return a QImage."""
        from freecad.BlocksCAD.render import offscreen
        head = self.input.head
        offset = {"head": 0.0, "left": -IPD / 2, "right": IPD / 2}[eye]
        pos = tuple(p + o for p, o in zip(head.position, rotate(head.orientation, (offset, 0.0, 0.0))))
        return offscreen.render(self.scene, pos, orientation=head.orientation, size=size, fov=fov,
                                near=0.02, far=200.0, headlight=False, **kwargs)

    def render_stereo(self, size=(960, 960), **kwargs):
        """Side by side image like the headset mirror: left eye, right eye."""
        from PySide6 import QtGui
        left = self.render("left", size, **kwargs)
        right = self.render("right", size, **kwargs)
        both = QtGui.QImage(size[0] * 2, size[1], QtGui.QImage.Format_RGB888)
        painter = QtGui.QPainter(both)
        painter.drawImage(0, 0, left)
        painter.drawImage(size[0], 0, right)
        painter.end()
        return both

    def close(self):
        self.ui.close()
        self.scene.unref()
