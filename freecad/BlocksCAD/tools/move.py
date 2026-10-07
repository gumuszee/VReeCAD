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
"""The Move tool: touch, select, move, turn and scale objects (docs/ux-design.md, Move tool).

The tip of the tool hand is the cursor. What it touches (the nearest vertex, edge or face within reach, else the inside of a solid)
is highlighted (`tools/touch.py`). The trigger pressed on it starts a grab in one transaction: the object follows the hand as a
rigid body, free in position and angle (or only moved, by the option). While the A button (`button1`) is held the grab is locked: it moves by whole
grid steps and turns by multiples of the angle step, and a padlock over the A button shows it. Releasing makes the change; one undo
step takes it back. A press that does not move anything is a tap: it selects the touched element (the FreeCAD selection), a tap on
nothing clears the selection. The trigger of the other hand pressed during a grab scales the object through the size properties of
its feature (the distance between the hands sets the factor; locked, every size is rounded to the grid); only the primitives made
by the Create tool can be scaled. A grip cancels the grab. While a grab is free (the A button is not held) the object lines up with the model: the middle and the
corners of its box and its vertices are level with the vertices and straight edge middles of the other objects where one is near on an
axis (`core/guides.py`, `cad/anchors.py`), with a guide and a tick of the hand. The stick chooses from an option disc: the grid larger (up) and smaller
(down), the angle step larger and smaller (left) and the two move modes (right). The click of the stick puts the grid and the angle step
back to their defaults. The value panels of the left-hand carousel follow the selection that this tool makes (`ui/value_module.py`)."""

import math

from freecad.BlocksCAD.cad import anchors as model_anchors
from freecad.BlocksCAD.cad import edit
from freecad.BlocksCAD.core import grab as grabbing
from freecad.BlocksCAD.core import guides
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import snapping
from freecad.BlocksCAD.tools.base import DiscSlot, ToolOption
from freecad.BlocksCAD.tools.registry import register
from freecad.BlocksCAD.tools.touch import TouchTool

GRID_LABELS = tuple(f"{step:g} mm" for step in snapping.GRID_STEPS)
MODES = ("Move and rotate", "Move")
ANGLE_LABELS = ("5 deg", "15 deg", "30 deg", "45 deg", "90 deg")


@register
class MoveTool(TouchTool):
    name = "move"
    label = "Move"
    hint = "Touch to highlight, tap to select, hold the trigger to move; the other trigger scales"
    controls = (("Trigger", "tap: select, hold: move and turn"), ("Other trigger", "scale"), ("A", "hold: lock to grid and angles"))
    options = (ToolOption("grid", "Grid", "choice", default="10 mm", choices=GRID_LABELS, wrap=False),
               ToolOption("angle", "Angle", "choice", default="15 deg", choices=ANGLE_LABELS, wrap=False),
               ToolOption("mode", "Mode", "choice", default=MODES[0], choices=MODES))

    def __init__(self, ctx):
        super().__init__(ctx)
        self._grab = None             # state of a grab in progress
        self._locked = False          # the A button is held: the grab is locked to the grid and the angles

    @property
    def busy(self):
        return self._grab is not None

    @property
    def lock_state(self):
        return self._locked if self._grab is not None else None

    def disc_slots(self):
        """The option disc, clockwise from the top: grid up, the two move modes, grid down, angle down and up."""
        return (DiscSlot("Grid +", "grid", 1, "step"), DiscSlot("Move, turn", "mode", MODES[0]), DiscSlot("Move only", "mode", MODES[1]),
                DiscSlot("Grid -", "grid", -1, "step"), DiscSlot("Angle -", "angle", -1, "step"), DiscSlot("Angle +", "angle", 1, "step"))

    def disc_hub(self):
        return [self.values["grid"], self.values["angle"]]

    def stick_click(self):
        self.values["grid"], self.values["angle"] = (o.default for o in self.options[:2])
        return "Grid and angle reset"

    @property
    def grid(self):
        return float(self.values["grid"].split()[0])

    @property
    def angle(self):
        return float(self.values["angle"].split()[0])

    # lifecycle
    def deactivate(self):
        if self._grab is not None:
            self._abort()
        super().deactivate()

    def update(self, frame):
        cursor, to_document = self._service("cursor"), self._service("to_document")
        doc = self._service("document", lambda: None)()
        if cursor is None or to_document is None or doc is None:
            return
        hand = frame.hands[self.ctx.dominant]
        raw = to_document(cursor(self.ctx.dominant))
        gripping = any(h.down("grip") for h in frame.hands)
        if self._grab is not None:
            if gripping:
                self._abort()
                self._toast("Cancelled")
            else:
                self._drag(doc, frame, hand, raw, to_document, cursor)
            self._show_selection(doc)
            return
        free = self._service("trigger_free", lambda: True)() and not gripping and hand.aim.tracked
        pick = self._steady(self._touch(doc, raw) if free else None, frame.dt)
        self._show_hover(doc, pick)
        if free and "trigger" in hand.pressed:
            self._press(doc, pick, raw)
        self._show_selection(doc)

    # grabbing
    def _hand_pose(self, hand, snapped):
        rotation = self._service("hand_rotation", lambda h: mu.IDENTITY_QUAT)(hand)
        return snapped, rotation

    def _press(self, doc, pick, raw):
        if pick is None:
            self._select(doc, [])
            return
        obj = doc.getObject(pick.name)
        if obj is None or not hasattr(obj, "Placement"):
            self._select(doc, [(pick.name, pick.sub)])
            return
        base, rotation = edit.placement(obj)
        position, hand_rotation = self._hand_pose(self.ctx.dominant, raw)
        doc.openTransaction(f"Move {obj.Label}")
        self._grab = {"pick": pick, "name": pick.name, "label": obj.Label, "start": (base, rotation),
                      "grab": grabbing.Grab(position, hand_rotation, base, rotation), "now": (base, rotation),
                      "cell": tuple(round(c / self.grid) for c in base), "scaling": False, "scaled": False, "size0": None, "points": None, "source": None, "index": None}
        self._locked = False
        self._hover = None
        self._select(doc, [(pick.name, "")])             # the object is selected as the grab starts, so it shows as selected at once
        self._show_hover(doc, None)
        self._haptic(0.3, 0.02)

    def _drag(self, doc, frame, hand, raw, to_document, cursor):
        state = self._grab
        obj = doc.getObject(state["name"])
        if obj is None:
            self._abort()
            return
        other_index = 1 - self.ctx.dominant
        other = frame.hands[other_index]
        two_hands = other.down("trigger") and edit.scalable(obj.TypeId)
        position, hand_rotation = self._hand_pose(self.ctx.dominant, raw)
        locked = self._locked = hand.down("button1")                    # the A button locks to the grid and the angles
        if not hand.down("trigger"):                    # released: the change stays as the last frame left it (A may let go in the same frame)
            self._finish(doc, obj)
            return
        if two_hands and not state["scaling"]:
            mine, theirs = to_document(cursor(self.ctx.dominant)), to_document(cursor(other_index))
            state.update(scaling=True, size0=edit.size_values(obj), span0=max(mu.length(mu.sub(mine, theirs)), 1e-6),
                         centre0=self._centre(obj))
            self._haptic(0.3, 0.02)
        elif not two_hands and state["scaling"]:
            state["scaling"] = False                    # moving goes on from the pose the object has now
            state["points"] = None                      # and from the points it has now
            base, rotation = edit.placement(obj)
            state["grab"] = grabbing.Grab(position, hand_rotation, base, rotation)
            state["now"] = (base, rotation)
        if state["scaling"]:
            self._scale(doc, obj, state, to_document, cursor, locked)
        else:
            rotate = self.values["mode"] == MODES[0]
            base, rotation = state["grab"].at(position, hand_rotation, rotate, self.grid if locked else None,
                                              self.angle if locked else None)
            if locked:
                self.hide_guides()
            else:
                base = self._align(state, obj, base, rotation)
            if (base, rotation) != state["now"]:
                edit.set_placement(obj, base, rotation)
                state["now"] = (base, rotation)
                cell = tuple(round(c / self.grid) for c in base)
                if cell != state["cell"]:           # a free grab changes every frame: the hand ticks for every grid step it travels
                    state["cell"] = cell
                    self._haptic(0.08, 0.008)
            self._readout(self._move_text(state))

    def _align(self, state, obj, base, rotation):
        """`base` shifted so that a point of the object (its box and its vertices, turned by `rotation`) lines up with an anchor of the
        model on each axis where one is near; draws the guides. The object itself is no anchor."""
        service = self._service("guide_anchors")
        if service is None:
            return base
        anchors, tolerance = service((state["name"],))
        if state["source"] is not anchors:
            state["source"], state["index"] = anchors, guides.index_anchors(anchors)
        if state["points"] is None:
            state["points"] = self._service("object_points", model_anchors.local_points)(obj)
        points = [mu.add(base, mu.rotate(rotation, p)) for p in state["points"]]
        shift, found = guides.align_translation(points, state["index"], tolerance)
        self.show_guides(found, self.grid * 0.5)
        return mu.add(base, shift)

    def _centre(self, obj):
        c = obj.Shape.BoundBox.Center
        return (c.x, c.y, c.z)

    def _scale(self, doc, obj, state, to_document, cursor, locked):
        mine, theirs = to_document(cursor(self.ctx.dominant)), to_document(cursor(1 - self.ctx.dominant))
        factor = mu.length(mu.sub(mine, theirs)) / state["span0"]
        values = edit.scaled_values(obj.TypeId, state["size0"], factor, self.grid if locked else None)
        if values != edit.size_values(obj):
            edit.set_size(obj, values)
            doc.recompute()
            shift = mu.sub(state["centre0"], self._centre(obj))          # the centre of the object stays where it was
            base, rotation = edit.placement(obj)
            edit.set_placement(obj, mu.add(base, shift), rotation)
            state["now"] = (mu.add(base, shift), rotation)
            state["scaled"] = True
            if locked:
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
        self._locked = False
        self._readout(None)
        self.hide_guides()
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
        self._locked = False
        self._readout(None)
        self.hide_guides()
        doc = self._service("document", lambda: None)()
        if doc is not None and state is not None:
            doc.abortTransaction()
