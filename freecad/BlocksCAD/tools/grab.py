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
"""The Grab tool: touch, select, move, turn and scale objects (docs/ux-design.md, Grab tool).

The tip of the tool hand is the cursor. What it touches (the nearest vertex, edge or face within reach, else the inside of a solid)
is highlighted. The trigger pressed on it starts a grab in one transaction: the object follows the hand as a rigid body, moved by
whole grid steps and turned in steps of 15 degrees (or only moved, by the option). Releasing makes the change; one undo step takes
it back. A press that does not move anything is a tap: it selects the touched element (the FreeCAD selection), a tap on nothing
clears the selection. The trigger of the other hand pressed during a grab scales the object through the size properties of its
feature (the distance between the hands sets the factor, every size is rounded to the grid); only the primitives made by the
Create tool can be scaled. A grip cancels the grab.

Services (`ToolContext.services`, all optional): cursor(hand), hand_rotation(hand), to_document(point), mm_per_metre(), document(),
trigger_free(), highlight (`render.highlight.Highlights`), toast(text), readout(text or None), format_length(mm), and `pick`,
`display`, `get_selection`, `set_selection`, `clear_selection` that replace the functions of `cad.picking`."""

import math

from freecad.BlocksCAD.cad import edit, picking
from freecad.BlocksCAD.core import grab as grabbing
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import snapping
from freecad.BlocksCAD.tools.base import Tool, ToolOption
from freecad.BlocksCAD.tools.registry import register

GRID_LABELS = tuple(f"{step:g} mm" for step in snapping.GRID_STEPS)
MODES = ("Move and rotate", "Move")
MARKER = 0.004          # metres on the stage: the arm of the cross at a vertex


@register
class GrabTool(Tool):
    name = "grab"
    label = "Grab"
    hint = "Touch to highlight, tap to select, hold the trigger to move; the other trigger scales"
    options = (ToolOption("grid", "Grid", "choice", default="10 mm", choices=GRID_LABELS),
               ToolOption("mode", "Mode", "choice", default=MODES[0], choices=MODES))

    def __init__(self, ctx):
        super().__init__(ctx)
        self._hover = None            # the `Pick` under the cursor
        self._hover_key = None
        self._selected_key = None
        self._grab = None             # state of a grab in progress
        self._last_cursor = None

    # services
    def _service(self, name, default=None):
        return self.ctx.services.get(name, default)

    @property
    def grid(self):
        return float(self.values["grid"].split()[0])

    def _format(self, mm):
        return self._service("format_length", lambda v: f"{v:g} mm")(mm)

    def _haptic(self, amplitude, duration):
        if self.ctx.haptic is not None:
            self.ctx.haptic(self.ctx.dominant, amplitude, duration)

    def _toast(self, text):
        self._service("toast", lambda t: None)(text)

    def _readout(self, text):
        readout = self._service("readout")
        if readout is not None:
            readout(text)

    # lifecycle
    def deactivate(self):
        if self._grab is not None:
            self._abort()
        highlight = self._service("highlight")
        if highlight is not None:
            highlight.hide()
        self._hover = self._hover_key = self._selected_key = None

    def update(self, frame):
        cursor, to_document = self._service("cursor"), self._service("to_document")
        doc = self._service("document", lambda: None)()
        if cursor is None or to_document is None or doc is None:
            return
        hand = frame.hands[self.ctx.dominant]
        raw = to_document(cursor(self.ctx.dominant))
        snapped = snapping.snap_point(raw, self.grid)
        gripping = any(h.down("grip") for h in frame.hands)
        if self._grab is not None:
            if gripping:
                self._abort()
                self._toast("Cancelled")
            else:
                self._drag(doc, frame, hand, snapped, to_document, cursor)
            self._show_selection(doc)
            return
        free = self._service("trigger_free", lambda: True)() and not gripping and hand.aim.tracked
        pick = self._touch(doc, raw) if free else None
        self._show_hover(doc, pick)
        if free and "trigger" in hand.pressed:
            self._press(doc, pick, snapped)
        self._show_selection(doc)

    # touching and showing
    def _touch(self, doc, point):
        pick = self._service("pick", picking.pick)
        mm = self._service("mm_per_metre", lambda: 1000.0)()
        try:
            return pick(doc, point, mm)
        except Exception as error:      # a shape that cannot be measured must not stop the session
            print(f"BlocksCAD: picking failed: {error}")
            return None

    def _display(self, doc, name, sub):
        obj = doc.getObject(name)
        if obj is None or getattr(obj, "Shape", None) is None or obj.Shape.isNull():
            return None, None
        try:
            return self._service("display", picking.display)(obj, sub), picking.signature(obj, sub)
        except Exception as error:
            print(f"BlocksCAD: cannot draw {name} {sub}: {error}")
            return None, None

    def _marker_half(self):
        return MARKER * self._service("mm_per_metre", lambda: 1000.0)()

    def _show_hover(self, doc, pick):
        highlight = self._service("highlight")
        if highlight is None:
            return
        key = None
        if pick is not None:
            obj = doc.getObject(pick.name)
            key = (pick.name, pick.sub, obj.Shape.hashCode() if obj is not None and hasattr(obj, "Shape") else None)
        if key == self._hover_key:
            return
        before = (self._hover.name, self._hover.sub) if self._hover else None
        if before != ((pick.name, pick.sub) if pick else None):
            self._haptic(0.1, 0.01)                  # a tick whenever the hand touches another element
        self._hover, self._hover_key = pick, key
        if pick is None:
            highlight.hover.hide()
            return
        display, _ = self._display(doc, pick.name, pick.sub)
        if display is None:
            highlight.hover.hide()
        else:
            highlight.hover.show([display], self._marker_half())

    def _show_selection(self, doc):
        highlight = self._service("highlight")
        if highlight is None:
            return
        items = self._service("get_selection", picking.get_selection)(doc)
        shown, key = [], []
        for name, sub in items:
            display, signature = self._display(doc, name, sub)
            if display is not None:
                shown.append(display)
                key.append(signature)
        key = tuple(key)
        if key != self._selected_key:
            self._selected_key = key
            if shown:
                highlight.selected.show(shown, self._marker_half())
            else:
                highlight.selected.hide()

    def _select(self, doc, items):
        if items:
            self._service("set_selection", picking.set_selection)(doc, items)
        else:
            self._service("clear_selection", picking.clear_selection)()

    # grabbing
    def _hand_pose(self, hand, snapped):
        rotation = self._service("hand_rotation", lambda h: mu.IDENTITY_QUAT)(hand)
        return snapped, rotation

    def _press(self, doc, pick, snapped):
        if pick is None:
            self._select(doc, [])
            return
        obj = doc.getObject(pick.name)
        if obj is None or not hasattr(obj, "Placement"):
            self._select(doc, [(pick.name, pick.sub)])
            return
        base, rotation = edit.placement(obj)
        position, hand_rotation = self._hand_pose(self.ctx.dominant, snapped)
        doc.openTransaction(f"Move {obj.Label}")
        self._grab = {"pick": pick, "name": pick.name, "label": obj.Label, "start": (base, rotation),
                      "grab": grabbing.Grab(position, hand_rotation, base, rotation), "now": (base, rotation),
                      "scaling": False, "scaled": False, "size0": None}
        self._show_hover(doc, None)
        self._haptic(0.3, 0.02)

    def _drag(self, doc, frame, hand, snapped, to_document, cursor):
        state = self._grab
        obj = doc.getObject(state["name"])
        if obj is None:
            self._abort()
            return
        other_index = 1 - self.ctx.dominant
        other = frame.hands[other_index]
        two_hands = other.down("trigger") and edit.scalable(obj.TypeId)
        position, hand_rotation = self._hand_pose(self.ctx.dominant, snapped)
        if two_hands and not state["scaling"]:
            mine, theirs = to_document(cursor(self.ctx.dominant)), to_document(cursor(other_index))
            state.update(scaling=True, size0=edit.size_values(obj), span0=max(mu.length(mu.sub(mine, theirs)), 1e-6),
                         centre0=self._centre(obj))
            self._haptic(0.3, 0.02)
        elif not two_hands and state["scaling"]:
            state["scaling"] = False                    # moving goes on from the pose the object has now
            base, rotation = edit.placement(obj)
            state["grab"] = grabbing.Grab(position, hand_rotation, base, rotation)
            state["now"] = (base, rotation)
        if state["scaling"]:
            self._scale(doc, obj, state, to_document, cursor)
        else:
            rotate = self.values["mode"] == MODES[0]
            base, rotation = state["grab"].at(position, hand_rotation, rotate)
            if (base, rotation) != state["now"]:
                edit.set_placement(obj, base, rotation)
                state["now"] = (base, rotation)
                self._haptic(0.08, 0.008)
            self._readout(self._move_text(state))
        if not hand.down("trigger"):
            self._finish(doc, obj)

    def _centre(self, obj):
        c = obj.Shape.BoundBox.Center
        return (c.x, c.y, c.z)

    def _scale(self, doc, obj, state, to_document, cursor):
        mine, theirs = to_document(cursor(self.ctx.dominant)), to_document(cursor(1 - self.ctx.dominant))
        factor = mu.length(mu.sub(mine, theirs)) / state["span0"]
        values = edit.scaled_values(obj.TypeId, state["size0"], factor, self.grid)
        if values != edit.size_values(obj):
            edit.set_size(obj, values)
            doc.recompute()
            shift = mu.sub(state["centre0"], self._centre(obj))          # the centre of the object stays where it was
            base, rotation = edit.placement(obj)
            edit.set_placement(obj, mu.add(base, shift), rotation)
            state["now"] = (mu.add(base, shift), rotation)
            state["scaled"] = True
            self._haptic(0.08, 0.008)
        self._readout(f"Scale: {factor * 100:.0f} %")

    def _move_text(self, state):
        (base, rotation), (start_base, start_rotation) = state["now"], state["start"]
        delta = mu.sub(base, start_base)
        text = "Move: " + ", ".join("0" if abs(d) < 1e-6 else self._format(d) for d in delta)
        turn = mu.quat_multiply(rotation, mu.quat_conjugate(start_rotation))
        angle = math.degrees(2.0 * math.acos(min(1.0, abs(turn[3]))))
        return text + (f", turn {angle:.0f} deg" if angle > 0.5 else "")

    def _finish(self, doc, obj):
        state, self._grab = self._grab, None
        self._readout(None)
        changed = state["scaled"] or state["now"] != state["start"]
        if changed:
            doc.recompute()
            doc.commitTransaction()
            self._select(doc, [(state["name"], "")])
            if state["scaled"]:
                self._toast(f"Scaled {state['label']}")
            else:
                turned = state["now"][1] != state["start"][1]
                self._toast(f"{'Moved and turned' if turned else 'Moved'} {state['label']}")
            self._haptic(0.4, 0.03)
        else:
            doc.abortTransaction()
            pick = state["pick"]
            self._select(doc, [(pick.name, pick.sub)])

    def _abort(self):
        state, self._grab = self._grab, None
        self._readout(None)
        doc = self._service("document", lambda: None)()
        if doc is not None and state is not None:
            doc.abortTransaction()
