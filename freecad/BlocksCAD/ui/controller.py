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
"""The user interface as one unit: grip navigation, the palette ring with its faces, the scale readout and action dispatch.
Hosts (the XR widget and the Sim session) feed it one `InputFrame` per frame and apply what it returns: the world pose goes to a
scene transform, `haptics` to the controllers, `ray_end` to the tool hand's ray, `consume_trigger` suppresses the tool hand's trigger."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core.navigation import Navigator, format_scale
from freecad.BlocksCAD.ui import defaults
from freecad.BlocksCAD.ui.layout import load_layout
from freecad.BlocksCAD.ui.readout import Readout
from freecad.BlocksCAD.ui.ring import PaletteRing
from freecad.BlocksCAD.ui.ring_view import RingView


@dataclass
class UiUpdate:
    haptics: List[tuple] = field(default_factory=list)   # (hand, amplitude, duration_s)
    ray_end: Optional[tuple] = None
    consume_trigger: bool = False
    activated: Optional[str] = None                      # action id executed this frame


class UiController:
    def __init__(self, tool_names, tool_label, actions: Dict[str, Callable], palette_hand=0, tool_hand=1,
                 layout_path=None, use_user_layout=True):
        self.actions = actions
        self.faces = defaults.build_faces(tool_names, tool_label)
        default = defaults.default_layout(tool_names)
        self.layout = load_layout(default, set(self.faces), layout_path) if use_user_layout else default
        self.navigator = Navigator()
        self.ring = PaletteRing(len(self.layout.pages), palette_hand, tool_hand)
        self.view = RingView()
        self.readout = Readout()
        self.root = coin.SoSeparator()
        self.root.ref()
        self.root.addChild(self.view.root)
        self.root.addChild(self.readout.root)
        self.active_actions = set()

    def action_at(self, page, slot):
        face_id = self.layout.face_at(page, slot)
        face = self.faces.get(face_id) if face_id else None
        return face.action if face else None

    def update(self, frame) -> UiUpdate:
        out = UiUpdate()
        events = self.navigator.update(frame)
        for event in events:
            if event[0] == "grab":
                out.haptics += [(0, 0.25, 0.03), (1, 0.25, 0.03)]
            elif event[0] == "tick":
                out.haptics += [(hand, 0.6, 0.04) for hand in event[1]]
            elif event[0] == "reset":
                out.haptics += [(0, 0.7, 0.12), (1, 0.7, 0.12)]

        navigating = self.navigator.state != "idle" or self.navigator.resetting
        result = self.ring.update(frame, navigating=navigating)
        out.haptics += result.haptics
        out.ray_end, out.consume_trigger = result.ray_end, result.consume_trigger
        controller = frame.hands[self.ring.palette_hand].aim.position
        self.view.update(self.ring, result, self.layout, self.faces, controller, frame.head.position, self.active_actions)

        if result.activated is not None:
            action = self.action_at(*result.activated)
            if action is not None:
                out.activated = action
                handler = self.actions.get(action)
                if handler is not None:
                    handler()

        if self.navigator.state == "two":
            middle = mu.lerp(Navigator.hand_position(frame.hands[0]), Navigator.hand_position(frame.hands[1]), 0.5)
            self.readout.show(format_scale(self.navigator.world.scale), mu.add(middle, (0.0, 0.1, 0.0)), frame.head.position)
        else:
            self.readout.hide()
        return out

    def close(self):
        self.root.unref()
