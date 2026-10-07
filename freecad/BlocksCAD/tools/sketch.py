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
"""The Sketch tool: draw lines, rectangles and circles in space with constraints, drag their points, dimension them (docs/ux-design.md,
Sketch tool).

The tip of the tool hand is the cursor. The **current sketch** is the sketch that is selected (the tool selects the sketch it draws in,
so drawing goes on in it; anything else selected, or the click of the stick, ends it). With no current sketch the first press makes a new
one: on the flat face the tip touches, else on the chosen plane (XY, XZ or YZ, at the height of the cursor on the grid). In a sketch the
cursor is the point of its plane that is nearest to the tip, rounded to the grid of the sketch. **Line**, **Rectangle** and **Circle**:
the trigger pressed at one point, dragged and released at another draws the shape in one undo step, with the constraints it implies
(`cad/sketchinfer.py`). **Edit**: the trigger pressed on a point of a sketch drags it (the solver keeps the constraints, so a constrained
point may stop short), pressed on a line or a circle it gives that a named dimension, which the value panels then edit. A grip cancels. The
stick chooses from an option disc (the grid and the four modes); its click ends the current sketch and turns to the next plane.

Services besides those of `TouchTool`: `ghost` (`render.ghost.Ghost`) and `sketching`, an object with the functions of `cad.sketching`
that the tool uses, replaced in tests."""

import math

from freecad.BlocksCAD.cad import sketching
from freecad.BlocksCAD.cad.meshes import Mesh
from freecad.BlocksCAD.core import guides
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import snapping
from freecad.BlocksCAD.tools.base import DiscSlot, ToolOption
from freecad.BlocksCAD.tools.registry import register
from freecad.BlocksCAD.tools.touch import TouchTool

GRID_LABELS = tuple(f"{step:g} mm" for step in snapping.GRID_STEPS)
MODES = ("Line", "Rectangle", "Circle", "Edit")
PLANE_HALF_CELLS = 5            # the square that shows the plane of a new sketch reaches this many grid steps from the cursor


def plane_square(plane, centre, half):
    """The outline of a square of half side `half` on `plane` around `centre` (document millimetres)."""
    rotation = sketching.PLANE_ROTATION[plane]
    corners = [(-half, -half), (half, -half), (half, half), (-half, half), (-half, -half)]
    return [mu.add(centre, mu.rotate(rotation, (x, y, 0.0))) for x, y in corners]


@register
class SketchTool(TouchTool):
    name = "sketch"
    label = "Sketch"
    hint = "Drag a line, rectangle or circle on a plane or a face; Edit drags a point or dimensions a line"
    options = (ToolOption("grid", "Grid", "choice", default="10 mm", choices=GRID_LABELS, wrap=False),
               ToolOption("mode", "Mode", "choice", default=MODES[1], choices=MODES))

    def __init__(self, ctx):
        super().__init__(ctx)
        self._plane = 0               # index into `sketching.PLANES`: the plane of the next new sketch
        self._gesture = None
        self._handles_key = None
        self._flat_source = self._flat_frame = self._flat = None    # the anchors of the model on the plane being drawn on, kept per frame

    @property
    def busy(self):
        return self._gesture is not None

    @property
    def grid(self):
        return float(self.values["grid"].split()[0])

    @property
    def plane(self):
        return sketching.PLANES[self._plane]

    @property
    def editing(self):
        return self.values["mode"] == "Edit"

    def disc_slots(self):
        """The option disc, clockwise from the top: grid up, rectangle, circle, grid down, edit, line."""
        return (DiscSlot("Grid +", "grid", 1, "step"), DiscSlot("Rectangle", "mode", MODES[1]), DiscSlot("Circle", "mode", MODES[2]),
                DiscSlot("Grid -", "grid", -1, "step"), DiscSlot("Edit", "mode", MODES[3]), DiscSlot("Line", "mode", MODES[0]))

    def disc_hub(self):
        return [self.values["grid"], self.values["mode"]]

    def stick_click(self):
        """End the current sketch and turn to the next plane."""
        doc = self._service("document", lambda: None)()
        if doc is not None and self._current(doc) is not None:
            self._select(doc, [])
        self._plane = (self._plane + 1) % len(sketching.PLANES)
        return f"Next sketch on the {self.plane} plane"

    def _sk(self):
        return self._service("sketching", sketching)

    def _ghost(self):
        return self._service("ghost")

    def _current(self, doc):
        return self._sk().current_sketch(doc, self._service("get_selection", self._default_selection)(doc))

    @staticmethod
    def _default_selection(doc):
        from freecad.BlocksCAD.cad import picking
        return picking.get_selection(doc)

    # touching
    def _touch(self, doc, point):
        mm = self._service("mm_per_metre", lambda: 1000.0)()
        try:
            if self.editing:
                found = self._sk().pick(doc, point, mm, "vertex")
                return found or self._sk().pick(doc, point, mm, "edge")
            return None if self._current(doc) is not None else self._sk().pick_face(doc, point, mm)
        except Exception as error:
            print(f"BlocksCAD: picking in a sketch failed: {error}")
            return None

    def _display(self, doc, name, sub):
        obj = doc.getObject(name)
        if obj is None:
            return None, None
        if sub.startswith("Face"):
            return super()._display(doc, name, sub)
        try:
            return self._sk().display(obj, sub), (name, sub, self._sk().signature(doc))
        except Exception as error:
            print(f"BlocksCAD: cannot draw {name} {sub}: {error}")
            return None, None

    def _show_selection(self, doc):
        """Mark every point of every sketch."""
        highlight = self._service("highlight")
        if highlight is None:
            return
        key = self._sk().signature(doc)
        if key == self._selected_key:
            return
        self._selected_key = key
        markers = self._sk().handles(doc)
        if markers.markers:
            highlight.selected.show([markers], self._marker_half())
        else:
            highlight.selected.hide()

    # lifecycle
    def deactivate(self):
        if self._gesture is not None:
            self._abort()
        self._hide_preview()
        super().deactivate()

    def _hide_preview(self):
        self.hide_guides()
        ghost = self._ghost()
        if ghost is not None:
            ghost.hide_shape()
            ghost.hide_marker()

    def update(self, frame):
        cursor, to_document = self._service("cursor"), self._service("to_document")
        doc = self._service("document", lambda: None)()
        if cursor is None or to_document is None or doc is None:
            return
        hand = frame.hands[self.ctx.dominant]
        raw = to_document(cursor(self.ctx.dominant))
        gripping = any(h.down("grip") for h in frame.hands)
        if self._gesture is not None:
            if gripping:
                self._abort()
                self._toast("Cancelled")
            else:
                self._follow(doc, hand, raw)
            self._show_selection(doc)
            return
        free = self._service("trigger_free", lambda: True)() and not gripping and hand.aim.tracked
        pick = self._steady(self._touch(doc, raw) if free else None, frame.dt)
        self._show_hover(doc, pick)
        if self.editing:
            self._hide_preview()
            if free and pick is not None and "trigger" in hand.pressed:
                self._press_edit(doc, pick, raw)
        else:
            self._show_cursor(doc, raw, free)
            if free and "trigger" in hand.pressed:
                self._press_draw(doc, pick, raw)
        self._show_selection(doc)

    # drawing
    def _snap2(self, point):
        return (snapping.snap(point[0], self.grid), snapping.snap(point[1], self.grid))

    def _align2(self, frame, local, sketch=None, apart_from=None):
        """((x, y), guides) for a cursor at `local` (x and y of `frame`): the grid point lined up with the points of the model and of the
        sketch (service `guide_anchors`; a sketch is left out of the model's points and read live: the point `apart_from` of it, and those
        that move with it, are not anchors). The guides are in the document; the same grid point and no guides without the service."""
        snapped = self._snap2(local)
        service = self._service("guide_anchors")
        if service is None or frame is None:
            return snapped, []
        sk = self._sk()
        anchors, tolerance = service((sketch.Name,) if sketch is not None else ())
        if self._flat_source is not anchors or self._flat_frame != frame:
            self._flat_source, self._flat_frame = anchors, frame
            self._flat = guides.flatten(anchors, lambda p: sk.frame_to_local(frame, p))
        flat = self._flat + (sk.own_points(sketch, apart_from) if sketch is not None else [])
        return guides.align_plane(local, snapped, flat, tolerance, lambda p: sk.frame_to_world(frame, p), sk.world_axes(frame))

    def _show_cursor(self, doc, raw, free):
        """The cross where a press would start; with no current sketch the square that shows the plane of the new one."""
        ghost = self._ghost()
        if ghost is None:
            return
        if not free:
            self._hide_preview()
            return
        sk = self._sk()
        sketch = self._current(doc)
        if sketch is not None or self._hover is None:
            frame = sk.placement(sketch) if sketch is not None else sk.plane_frame(self.plane, raw, self.grid)
            (x, y), found = self._align2(frame, sk.frame_to_local(frame, raw), sketch)
            point = sk.frame_to_world(frame, (x, y, 0.0))
            self.show_guides(found, self.grid * 0.5)
            ghost.show_marker(point, self.grid * 0.75)
            if sketch is not None:
                ghost.hide_shape()
            else:
                ghost.show_shape(Mesh(outline=[plane_square(self.plane, point, self.grid * PLANE_HALF_CELLS)]))
            return
        self.hide_guides()
        ghost.show_marker(snapping.snap_point(raw, self.grid), self.grid * 0.75)
        ghost.hide_shape()

    def _press_draw(self, doc, pick, raw):
        sk = self._sk()
        sketch = self._current(doc)
        created = sketch is None
        if created:
            doc.openTransaction("Sketch")
            if pick is not None:
                sketch = sk.create_on_face(doc, doc.getObject(pick.name), pick.sub)
            else:
                sketch = sk.create_on_plane(doc, self.plane, raw, self.grid)
            doc.recompute()
        else:
            doc.openTransaction(f"Draw {self.values['mode']}")
        frame = sk.placement(sketch)
        start, _ = self._align2(frame, sk.frame_to_local(frame, raw), sketch)
        self._gesture = {"sketch": sketch.Name, "created": created, "start": start, "now": start, "kind": self.values["mode"]}
        self._forget_hover()
        self._hide_preview()
        self._haptic(0.3, 0.02)

    def _extent(self, state):
        (x0, y0), (x1, y1) = state["start"], state["now"]
        if state["kind"] == "Line":
            return math.dist((x0, y0), (x1, y1))
        if state["kind"] == "Rectangle":
            return min(abs(x1 - x0), abs(y1 - y0))
        return math.dist((x0, y0), (x1, y1))

    def _describe(self, state):
        (x0, y0), (x1, y1) = state["start"], state["now"]
        kind = state["kind"]
        if kind == "Rectangle":
            return f"Rectangle: {self._format(abs(x1 - x0))} x {self._format(abs(y1 - y0))}"
        if kind == "Circle":
            return f"Circle: radius {self._format(math.dist((x0, y0), (x1, y1)))}"
        return f"Line: {self._format(math.dist((x0, y0), (x1, y1)))}"

    def _follow(self, doc, hand, raw):
        sk = self._sk()
        state = self._gesture
        sketch = doc.getObject(state["sketch"])
        if sketch is None:
            self._abort()
            return
        local = sk.to_local(sketch, raw)
        if state.get("edit") is not None:
            self._follow_edit(doc, hand, sketch, local)
            return
        if not hand.down("trigger"):                        # released: the shape is what the last frame left (A may let go in the same frame)
            self._finish_draw(doc, sketch, state)
            return
        if hand.down("button1"):
            now = (local[0], local[1])
            self.hide_guides()
        else:
            now, found = self._align2(sk.placement(sketch), local, sketch)
            self.show_guides(found, self.grid * 0.5)
        if now != state["now"]:
            state["now"] = now
            self._haptic(0.08, 0.008)
        ghost = self._ghost()
        if ghost is not None:
            polylines = sketching.outline(state["kind"], state["start"], state["now"])
            ghost.show_shape(Mesh(outline=[[sk.to_world(sketch, p) for p in line] for line in polylines]))
        self._readout(self._describe(state))

    def _finish_draw(self, doc, sketch, state):
        sk = self._sk()
        self._gesture = None
        self._hide_preview()
        self._readout(None)
        if self._extent(state) < self.grid / 2:
            doc.abortTransaction()                          # a tap draws nothing (and makes no empty sketch)
            doc.recompute()
            return
        kind, start, now = state["kind"], state["start"], state["now"]
        try:
            if kind == "Line":
                _, kept = sk.add_line(doc, sketch, start, now)
            elif kind == "Rectangle":
                _, kept = sk.add_rectangle(doc, sketch, start, now)
            else:
                _, kept = sk.add_circle(doc, sketch, start, math.dist(start, now))
            doc.recompute()
        except Exception as error:                          # a shape the sketch cannot take must not stop the session
            doc.abortTransaction()
            doc.recompute()
            self._toast(f"Could not draw the {kind.lower()}")
            print(f"BlocksCAD: sketching failed: {error}")
            return
        doc.commitTransaction()
        self._select(doc, [(sketch.Name, "")])
        self._toast(f"{kind} drawn, {kept} constraint{'s' if kept != 1 else ''}")
        self._haptic(0.4, 0.03)

    # editing
    def _press_edit(self, doc, pick, raw):
        sk = self._sk()
        sketch = doc.getObject(pick.name)
        if sketch is None:
            return
        kind, geo, pos = sk.parse_sub(pick.sub)
        if kind == "curve":
            doc.openTransaction("Dimension")
            text, name = sk.dimension(doc, sketch, geo)
            if name is None:
                doc.abortTransaction()
            else:
                doc.recompute()
                doc.commitTransaction()
                self._haptic(0.4, 0.03)
            self._select(doc, [(sketch.Name, "")])
            self._toast(text)
            return
        doc.openTransaction(f"Move point of {sketch.Label}")
        self._gesture = {"sketch": sketch.Name, "edit": (geo, pos), "changed": False, "kind": "Edit",
                         "now": sk.point_position(sketch, geo, pos)}
        self._forget_hover()
        self._select(doc, [(sketch.Name, "")])
        self._haptic(0.3, 0.02)

    def _follow_edit(self, doc, hand, sketch, local):
        sk = self._sk()
        state = self._gesture
        if not hand.down("trigger"):
            self._gesture = None
            self._readout(None)
            self.hide_guides()
            if state["changed"]:
                doc.commitTransaction()
                self._toast(f"Moved a point of {sketch.Label}")
                self._haptic(0.4, 0.03)
            else:
                doc.abortTransaction()
            self._select(doc, [(sketch.Name, "")])
            return
        geo, pos = state["edit"]
        if hand.down("button1"):
            target = (local[0], local[1])
            self.hide_guides()
        else:
            target, found = self._align2(sk.placement(sketch), local, sketch, (geo, pos))
            self.show_guides(found, self.grid * 0.5)
        error = sk.move_point(doc, sketch, geo, pos, target)
        if error is not None:
            self._readout(error)
            return
        doc.recompute()
        moved = sk.point_position(sketch, geo, pos)
        if moved != state["now"]:
            state["now"], state["changed"] = moved, True
            self._haptic(0.08, 0.008)
        self._readout(f"Point: {self._format(moved[0])}, {self._format(moved[1])}")

    def _abort(self):
        state, self._gesture = self._gesture, None
        self._hide_preview()
        self._readout(None)
        doc = self._service("document", lambda: None)()
        if doc is not None and state is not None:
            doc.abortTransaction()
            doc.recompute()
