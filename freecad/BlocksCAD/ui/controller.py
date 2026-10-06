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
"""The user interface as one unit: grip navigation with its ruler, the palette carousel with its panels, action dispatch.
Hosts (the XR widget and the Sim session) feed it one `InputFrame` per frame and apply what it returns: the world pose goes to a
scene transform, `haptics` to the controllers, `ray_end` to the tool hand's ray, `consume_trigger` suppresses the tool hand's trigger.
The scene graph has two roots: `root` (the carousel, depth tested) and `overlay` (the ruler, drawn last on top of everything)."""

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import units
from freecad.BlocksCAD.core.navigation import Navigator
from freecad.BlocksCAD.ui import defaults
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import pointing, settings as cfg
from freecad.BlocksCAD.ui.pointer import Pointer, TipMarker
from freecad.BlocksCAD.ui.ring import PaletteRing
from freecad.BlocksCAD.ui.ring_view import RingView
from freecad.BlocksCAD.ui.ruler import Ruler


@dataclass
class UiUpdate:
    haptics: List[tuple] = field(default_factory=list)   # (hand, amplitude, duration_s)
    ray_end: Optional[tuple] = None
    consume_trigger: bool = False
    activated: Optional[str] = None                      # action id executed this frame


class UiController:
    def __init__(self, tool_names, tool_label, actions: Dict[str, Callable], palette_hand=0, tool_hand=1,
                 layout_path=None, use_user_layout=True, mm_to_stage=0.001, settings_path=None):
        self.actions = actions
        self.faces = defaults.build_faces(tool_names, tool_label)
        self._tool_names = list(tool_names)
        default = defaults.default_layout(self._tool_names)
        self.use_user_layout, self.layout_path = use_user_layout, layout_path
        self.layout = lay.load_layout(default, set(self.faces), layout_path) if use_user_layout else default
        self.settings = cfg.load_settings(settings_path) if use_user_layout else cfg.Settings()
        self.settings_path = settings_path
        if use_user_layout and self.layout is not default and self.layout.add_missing(default):
            self._save_layout()
        self.palette_hand, self.tool_hand = palette_hand, tool_hand
        self.navigator = Navigator(modifier_hand=tool_hand)
        self.ring = PaletteRing(self.layout.sides(), palette_hand, tool_hand)
        self.view = RingView()
        self.ruler = Ruler()
        self.pointer = Pointer()
        self.tips = [TipMarker(), TipMarker()]
        self.pointer_poses = [None, None]     # `pointing.PointerPose` of each hand, set by `update`
        self.system = units.METRIC_MM
        self.mm_to_stage = mm_to_stage     # stage length of one document millimetre at world scale 1
        self.root = coin.SoSeparator()
        self.root.ref()
        self.root.addChild(self.view.root)
        self.overlay = coin.SoSeparator()
        self.overlay.ref()
        self.overlay.addChild(self.ruler.root)
        self.overlay.addChild(self.pointer.root)
        for tip in self.tips:
            self.overlay.addChild(tip.root)
        self.active_actions = set()

    def set_unit_system(self, name):
        """Use the measurement system of a FreeCAD document unit system name (the document's `UnitSystem` property)."""
        self.system = units.system_for(name)

    def action_at(self, page, slot):
        face_id = self.layout.face_at(page, slot)
        face = self.faces.get(face_id) if face_id else None
        return face.action if face else None

    def reset_layout(self):
        """Back to the default layout; a saved layout file is removed."""
        self.layout = defaults.default_layout(self._tool_names)
        self.ring.set_sides(self.layout.sides())
        self.ring.focus_side(0)
        self._save_layout(remove=True)

    def _save_layout(self, remove=False):
        if not self.use_user_layout:
            return
        try:
            if remove:
                os.remove(self.layout_path or lay.user_layout_path())
            else:
                lay.save_layout(self.layout, self.layout_path)
        except OSError:
            pass   # the layout is a convenience; a failed write must not stop the session

    def labels(self):
        """Labels of the faces whose text shows a value, by face id."""
        s = self.settings
        return {
            "pointer.mode": "Pointer: " + ("Tip" if s.pointer_mode == "tip" else "Laser"),
            "pointer.angle_up": f"Angle + {s.tip_angle:.0f}\u00b0",
            "pointer.angle_down": f"Angle - {s.tip_angle:.0f}\u00b0",
            "pointer.length_up": "Length + " + units.format_length(s.tip_length * 1000.0, self.system),
            "pointer.length_down": "Length - " + units.format_length(s.tip_length * 1000.0, self.system),
        }

    def _change_pointer(self, action):
        s = self.settings
        if action == "pointer:mode":
            s.toggle_mode()
        elif action == "pointer:angle+":
            s.adjust_angle(1)
        elif action == "pointer:angle-":
            s.adjust_angle(-1)
        elif action == "pointer:length+":
            s.adjust_length(1)
        elif action == "pointer:length-":
            s.adjust_length(-1)
        if self.use_user_layout:
            try:
                cfg.save_settings(s, self.settings_path)
            except OSError:
                pass   # settings are a convenience; a failed write must not stop the session

    def _run(self, action, out):
        if action == "layout:reset":
            self.reset_layout()
        elif action.startswith("pointer:"):
            self._change_pointer(action)
        else:
            handler = self.actions.get(action)
            if handler is not None:
                handler()
        out.activated = action

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
            elif event[0] == "snap":
                out.haptics += [(0, 0.5, 0.06), (1, 0.5, 0.06)]
            elif event[0] == "level":
                out.haptics.append((self.tool_hand, 0.3, 0.03))

        s = self.settings
        self.pointer_poses = [pointing.pointer_pose(h.aim, s.pointer_mode, s.tip_angle, s.tip_length) for h in frame.hands]
        self.ring.set_sides(self.layout.sides())
        result = self.ring.update(frame, navigating=self.navigator.navigating, pointers=self.pointer_poses)
        out.haptics += result.haptics
        out.ray_end, out.consume_trigger = result.ray_end, result.consume_trigger
        if result.dropped is not None:
            page, side, row, before, new_row = result.dropped
            index = self.layout.move_page(page, side, row, before, new_row)
            self.ring.set_sides(self.layout.sides())
            self.ring.focus_side(self.layout.pages[index].side)
            self._save_layout()
        self.view.update(self.ring, result, self.layout, self.faces, frame.head.position, self.active_actions, self.labels())

        if result.activated is not None:
            action = self.action_at(*result.activated)
            if action is not None:
                self._run(action, out)

        palette = frame.hands[self.palette_hand]
        for name, action in (("aux1", "doc:undo"), ("aux2", "doc:redo")):
            if name in palette.pressed:
                self._run(action, out)
                out.haptics.append((self.palette_hand, 0.4, 0.03))

        nav = self.navigator
        if nav.state == "two":
            self.ruler.update(Navigator.hand_position(frame.hands[0]), Navigator.hand_position(frame.hands[1]), frame.head,
                              nav.world.scale, self.mm_to_stage, self.system, nav.level, nav.scale_locked)
        elif nav.state == "one":
            hand = frame.hands[0 if nav.gripping[0] else 1]
            self.ruler.show_single(Navigator.hand_position(hand), frame.head, nav.world.scale, nav.level, nav.scale_locked)
        else:
            self.ruler.hide()

        tool_pointer = self.pointer_poses[self.tool_hand]
        if s.pointer_mode == "laser" and self.ring.fade > 0.3 and tool_pointer.tracked and not nav.navigating:
            self.pointer.show(tool_pointer.position, tool_pointer.direction, result.ray_end)
        else:
            self.pointer.hide()
        for hand, marker in enumerate(self.tips):
            ptr = self.pointer_poses[hand]
            if s.pointer_mode == "tip" and ptr.tracked and not nav.navigating:
                touching = hand == self.tool_hand and result.ray_end is not None
                marker.show(frame.hands[hand].aim.position, ptr.position, touching)
            else:
                marker.hide()
        return out

    def close(self):
        self.root.unref()
        self.overlay.unref()
