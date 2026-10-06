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
"""The user interface as one unit: grip navigation with its ruler, the palette carousel with its panels, the quick radial, action
dispatch, undo and redo on the tool hand, tool options, toasts, tooltips.
Hosts (the XR widget and the Sim session) feed it one `InputFrame` per frame and apply what it returns: the world pose goes to a
scene transform, `haptics` to the controllers, `ray_end` to the tool hand's ray, `consume_trigger` suppresses the tool hand's trigger.
The scene graph has two roots: `root` (the carousel, depth tested) and `overlay` (the ruler, drawn last on top of everything)."""

import os
from dataclasses import dataclass, field
from dataclasses import replace
from typing import Callable, Dict, List, Optional

from pivy import coin

from freecad.BlocksCAD.core import units
from freecad.BlocksCAD.core.navigation import Navigator
from freecad.BlocksCAD.ui import defaults
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import pointing, settings as cfg
from freecad.BlocksCAD.ui import options as tool_options
from freecad.BlocksCAD.ui import radial, toast
from freecad.BlocksCAD.ui.feedback_view import FeedbackView
from freecad.BlocksCAD.ui.pointer import Pointer, TipMarker
from freecad.BlocksCAD.ui.radial_view import RadialView
from freecad.BlocksCAD.ui.ring import PaletteRing
from freecad.BlocksCAD.ui.ring_view import RingView
from freecad.BlocksCAD.ui.ruler import Ruler
from freecad.BlocksCAD.ui.undo_button import UndoButton


@dataclass
class UiUpdate:
    haptics: List[tuple] = field(default_factory=list)   # (hand, amplitude, duration_s)
    ray_end: Optional[tuple] = None
    consume_trigger: bool = False
    owns_stick: bool = False                             # the active tool has options: the stick of the tool hand belongs to them
    activated: Optional[str] = None                      # action id executed this frame


class UiController:
    def __init__(self, tool_names, tool_label, actions: Dict[str, Callable], palette_hand=0, tool_hand=1,
                 layout_path=None, use_user_layout=True, mm_to_stage=0.001, settings_path=None, tool_hint=None):
        self.actions = actions
        self.faces = defaults.build_faces(tool_names, tool_label, tool_hint)
        self._tool_names = list(tool_names)
        default = defaults.default_layout(self._tool_names)
        self.use_user_layout, self.layout_path = use_user_layout, layout_path
        self.layout = lay.load_layout(default, set(self.faces), layout_path) if use_user_layout else default
        self.settings = cfg.load_settings(settings_path) if use_user_layout else cfg.Settings()
        self.settings_path = settings_path
        self.wide = {fid for fid, face in self.faces.items() if face.kind == "slider"}
        if use_user_layout and self.layout is not default and self.layout.add_missing(default, self.wide):
            self._save_layout()
        self.palette_hand, self.tool_hand = palette_hand, tool_hand
        self.navigator = Navigator(modifier_hand=tool_hand)
        self.ring = PaletteRing(self.layout.sides(), palette_hand, tool_hand)
        self.ring.can_lift = lambda page, slot: self.layout.face_at(page, slot) is not None
        self.ring.can_drop = lambda src, dst: self.layout.can_move_face(*src, *dst, self.wide)
        self.radial = radial.QuickRadial(tool_hand)
        self.radial_view = RadialView()
        self.undo_button = UndoButton(tool_hand)
        self.options = tool_options.OptionControl(tool_hand)
        self.active_tool = None            # the active `tools.base.Tool`, set by the host before `update`
        self.toasts = toast.Toasts()
        self.dwell = toast.Dwell()
        self.feedback = FeedbackView()
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
        self.overlay.addChild(self.pointer.root)
        for tip in self.tips:
            self.overlay.addChild(tip.root)
        # the controller models are drawn again over the laser and the tips, so the controllers always hide them (`add_occluder`)
        self.occluders = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.occluders.addChild(pick)
        depth = coin.SoDepthBuffer()
        depth.test.setValue(True)
        depth.function.setValue(coin.SoDepthBuffer.LEQUAL)
        depth.getField("write").setValue(False)
        self.occluders.addChild(depth)
        self.overlay.addChild(self.occluders)
        self.overlay.addChild(self.ruler.root)
        self.overlay.addChild(self.feedback.root)
        self.overlay.addChild(self.radial_view.root)
        self.active_actions = set()

    def set_unit_system(self, name):
        """Use the measurement system of a FreeCAD document unit system name (the document's `UnitSystem` property)."""
        self.system = units.system_for(name)

    def action_at(self, page, slot):
        face_id = self.layout.face_at(page, slot)
        face = self.faces.get(face_id) if face_id else None
        return face.action if face else None

    def add_occluder(self, node):
        """Draw a scene node (the model of a controller) a second time over the laser and the tips, wherever it is visible in the
        scene: the depth test against the depth the scene already wrote passes only where nothing is in front of it. The node is
        shared, not copied, so it follows its original."""
        self.occluders.addChild(node)

    def toast(self, text):
        """Show a short message in front of the head."""
        self.toasts.show(text)

    def radial_items(self):
        """Face ids offered by the quick radial: the faces used last, then the defaults."""
        return radial.choose_items(self.settings.recent, self.faces, self.layout.hidden)

    def _activate(self, face_id, out):
        """Run the action of a face and remember the face for the quick radial."""
        face = self.faces.get(face_id) if face_id else None
        if face is None:
            return
        self._run(face.action, out)
        if face.kind == "button" and (not self.settings.recent or self.settings.recent[0] != face_id):
            self.settings.recent = radial.remember(self.settings.recent, face_id)
            self._save_settings()

    def show_hidden(self):
        """Put the hidden faces back on the panels."""
        shown = len(self.layout.hidden)
        if self.layout.show_hidden(defaults.default_layout(self._tool_names), self.wide):
            self._save_layout()
        left = len(self.layout.hidden)
        if not shown:
            self.toast("No hidden faces")
        elif not left:
            self.toast("Faces shown")
        elif left < shown:
            self.toast(f"{shown - left} faces shown, no room for {left}")
        else:
            self.toast("No room for the hidden faces")

    def reset_layout(self):
        """Back to the default layout (no hidden faces); a saved layout file is removed."""
        self.layout = defaults.default_layout(self._tool_names)
        self.ring.set_sides(self.layout.sides())
        self.ring.focus_side(0)
        self._save_layout(remove=True)
        self.toast("Layout reset")

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
            "pointer.angle": f"Angle {s.tip_angle:.0f}\u00b0",
            "pointer.length": "Length " + units.format_length(s.tip_length * 1000.0, self.system),
        }

    def slider_states(self):
        """Position along the track and label of each slider, by face id."""
        labels = self.labels()
        return {fid: (spec.fraction(getattr(self.settings, spec.attr)), labels[fid]) for fid, spec in defaults.SLIDERS.items()}

    def slider_rows(self):
        """Pages and grid rows that hold a slider: page -> row -> face id."""
        rows = {}
        for p, page in enumerate(self.layout.pages):
            for r in range(lay.ROWS):
                face_id = page.slots[r * lay.COLS]
                face = self.faces.get(face_id) if face_id else None
                if face is not None and face.kind == "slider":
                    rows.setdefault(p, {})[r] = face_id
        return rows

    def _save_settings(self):
        if self.use_user_layout:
            try:
                cfg.save_settings(self.settings, self.settings_path)
            except OSError:
                pass   # settings are a convenience; a failed write must not stop the session

    def _change_pointer(self, action):
        if action == "pointer:mode":
            self.settings.toggle_mode()
            self._save_settings()
            self.toast("Pointer: " + ("Tip" if self.settings.pointer_mode == "tip" else "Laser"))

    def _run(self, action, out):
        if action == "layout:reset":
            self.reset_layout()
        elif action == "layout:show_hidden":
            self.show_hidden()
        elif action.startswith("pointer:"):
            self._change_pointer(action)
        else:
            handler = self.actions.get(action)
            if handler is not None:
                message = handler()
                if isinstance(message, str):
                    self.toast(message)
        out.activated = action

    def update(self, frame) -> UiUpdate:
        out = UiUpdate()
        s = self.settings
        self.pointer_poses = [pointing.pointer_pose(h.aim, s.pointer_mode, s.tip_angle, s.tip_length) for h in frame.hands]
        # in tip mode the world is held with the tips: it pivots about them and the ruler measures between them
        points = [p.position for p in self.pointer_poses] if s.pointer_mode == "tip" else None
        events = self.navigator.update(frame, points=points)
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

        self.ring.set_sides(self.layout.sides())
        self.ring.slider_rows = self.slider_rows()
        # the quick radial takes the tool hand while it is open: the carousel does not see its pointer
        busy = (self.navigator.navigating or self.ring.lifted is not None or self.ring.lifted_face is not None
                or self.ring.slider_drag is not None or self.ring.press is not None)
        quick = self.radial.update(frame, self.radial_items(), blocked=busy)
        out.owns_stick, readout = self._tool_hand_buttons(frame, busy or self.radial.is_open, out)
        pointers = list(self.pointer_poses)
        if self.radial.is_open:
            pointers[self.tool_hand] = replace(pointers[self.tool_hand], tracked=False)
        result = self.ring.update(frame, navigating=self.navigator.navigating, pointers=pointers)
        out.haptics += result.haptics + quick.haptics
        out.ray_end = result.ray_end
        out.consume_trigger = result.consume_trigger or self.radial.is_open or quick.activated is not None
        if result.slider is not None:
            page, slot, along = result.slider
            spec = defaults.SLIDERS.get(self.layout.face_at(page, slot))
            if spec is not None:
                value = spec.value(along)
                if value != getattr(self.settings, spec.attr):
                    setattr(self.settings, spec.attr, value)
                    out.haptics.append((self.tool_hand, 0.15, 0.01))
        if result.slider_done is not None:
            self._save_settings()
        if result.dropped is not None:
            page, side, row, before, new_row = result.dropped
            index = self.layout.move_page(page, side, row, before, new_row)
            self.ring.set_sides(self.layout.sides())
            self.ring.focus_side(self.layout.pages[index].side)
            self._save_layout()
        if result.face_dropped is not None:
            page, slot, target_page, target_slot = result.face_dropped
            if target_page is None:
                moved = self.layout.hide_face(page, slot, self.wide)
            else:
                moved = self.layout.move_face(page, slot, target_page, target_slot, self.wide)
            if moved:
                self._save_layout()
                if target_page is None:
                    face = self.faces.get(self.layout.hidden[-1]) if self.layout.hidden else None
                    self.toast(f"Hidden: {face.label}" if face else "Face hidden")
        labels = self.labels()
        self.view.update(self.ring, result, self.layout, self.faces, frame.head.position, self.active_actions, labels, self.slider_states())
        self.radial_view.update(quick, [labels.get(f, self.faces[f].label) for f in quick.items])
        tooltip = self._tooltip(result, frame.dt, labels)
        shown = readout and (readout, self.pointer_poses[self.tool_hand].position)
        self.feedback.update(frame.head, self.toasts.update(frame.dt), tooltip, shown or None)

        if result.activated is not None:
            self._activate(self.layout.face_at(*result.activated), out)
        if quick.activated is not None:
            self._activate(quick.items[quick.activated], out)

        palette = frame.hands[self.palette_hand]
        for name, action in (("aux1", "doc:undo"), ("aux2", "doc:redo")):
            if name in palette.pressed:
                self._run(action, out)
                out.haptics.append((self.palette_hand, 0.4, 0.03))

        nav = self.navigator
        if nav.state == "two":
            self.ruler.update(nav.point(frame.hands, 0), nav.point(frame.hands, 1), frame.head,
                              nav.world.scale, self.mm_to_stage, self.system, nav.level, nav.scale_locked)
        elif nav.state == "one":
            self.ruler.show_single(nav.point(frame.hands, 0 if nav.gripping[0] else 1), frame.head, nav.world.scale, nav.level,
                                   nav.scale_locked)
        else:
            self.ruler.hide()

        tool_pointer = self.pointer_poses[self.tool_hand]
        if s.pointer_mode == "laser" and self.ring.fade > 0.3 and tool_pointer.tracked and not nav.navigating and not self.radial.is_open:
            self.pointer.show(tool_pointer.position, tool_pointer.direction, result.ray_end)
        else:
            self.pointer.hide()
        for hand, marker in enumerate(self.tips):
            ptr = self.pointer_poses[hand]
            # the tips stay visible while navigating; the tip of the palette hand is hidden while the carousel is shown
            palette_shown = hand == self.palette_hand and self.ring.fade > 0.3 and not nav.navigating
            if s.pointer_mode == "tip" and ptr.tracked and not palette_shown:
                touching = hand == self.tool_hand and result.ray_end is not None
                marker.show(frame.hands[hand].aim.position, ptr.position, touching)
            else:
                marker.hide()
        return out

    def _tool_hand_buttons(self, frame, blocked, out):
        """Undo and redo on button2 of the tool hand and the options of the active tool on its stick.
        Returns (whether the tool owns the stick, the text of the readout or None)."""
        undo = self.undo_button.update(frame, blocked)
        if undo.action is not None:
            self._run("doc:" + undo.action, out)
        out.haptics += undo.haptics
        chosen = self.options.update(frame, self.active_tool, blocked, self.system)
        out.haptics += chosen.haptics
        return chosen.owns_stick, chosen.readout

    def _tooltip(self, result, dt, labels):
        """(text, centre, u, v) of the tooltip of the hovered face once it has been hovered for a moment, else None."""
        idle = self.ring.lifted is None and self.ring.lifted_face is None and self.ring.press is None and not self.radial.is_open
        target = self.dwell.update(result.hover if idle and self.ring.fade > 0.8 else None, dt)
        if target is None:
            return None
        face = self.faces.get(self.layout.face_at(*target) or "")
        place = self.ring.slot_centre(*target)
        if face is None or place is None:
            return None
        return (face.tip or labels.get(face.id, face.label), *place)

    def close(self):
        self.root.unref()
        self.overlay.unref()
