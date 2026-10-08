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
"""The Sketch tool: draw lines, rectangles, circles and arcs in space with constraints, drag their points, dimension them
(docs/ux-design.md, Sketch tool).

The tip of the tool hand is the cursor. The **current sketch** is the sketch that is selected (the tool selects the sketch it draws in,
so drawing goes on in it; anything else selected, or the click of the stick, ends it). With no current sketch the first press makes a new
one: on the flat face the tip touches, else on the chosen plane (XY, XZ or YZ, at the height of the cursor on the grid). In a sketch the
cursor is the point of its plane that is nearest to the tip, rounded to the grid of the sketch. **Line**, **Rectangle** and **Circle**:
the trigger pressed at one point, dragged and released at another draws the shape in one undo step, with the constraints it implies
(`cad/sketchinfer.py`). **Arc**: the same drag gives the two ends; after the release the third point follows the hand (a preview of
the arc through it) and the next press of the trigger draws the arc, all in one undo step. **Edit**: the trigger pressed on a point of a sketch drags it (the solver keeps the constraints, so a constrained
point may stop short), pressed on a line it gives that a named dimension, which the value panels then edit, and pressed on a circle or an arc it gives
that a radius dimension (when it has none) and drags it: once the hand has left the press the radius follows the distance of the
hand from the centre. A grip cancels. The stick chooses from an option disc of two pages (the grid and Line, Rectangle, Circle and Edit; the grid and Arc and the
three planes) and its click turns the page. Choosing a plane ends the current sketch, so the next one lies on that plane.

Services besides those of `TouchTool`: `ghost` (`render.ghost.Ghost`) and `sketching`, an object with the functions of `cad.sketching`
that the tool uses, replaced in tests."""

import math

from freecad.BlocksCAD.cad import sketching
from freecad.BlocksCAD.cad import sketchinfer
from freecad.BlocksCAD.cad.meshes import Mesh
from freecad.BlocksCAD.core import guides
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import snapping
from freecad.BlocksCAD.tools.base import DiscSlot, ToolOption
from freecad.BlocksCAD.tools.registry import register
from freecad.BlocksCAD.tools.touch import TouchTool

MIN_RADIUS = 0.1             # millimetres: the smallest radius that a drag gives a circle
DRAG_START = 0.012           # metres on the stage: the radius changes only once the hand has moved this far from the press
MODES = ("Line", "Rectangle", "Circle", "Arc", "Edit")
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
    controls = (("Trigger", "drag a shape (an arc: press again)"), ("A", "trigger held: snap, grid, free"), ("B", "held: fix it, else tap: undo, hold: redo"), ("Stick click", "other page of the disc"))
    hint = "Drag a line, rectangle or circle on a plane or a face; Edit drags a point or dimensions a line"
    options = (ToolOption("mode", "Mode", "choice", default=MODES[1], choices=MODES),
               ToolOption("plane", "Plane", "choice", default=sketching.PLANES[0], choices=sketching.PLANES))

    def __init__(self, ctx):
        super().__init__(ctx)
        self._page = 0                # the page of the option disc
        self._plane_seen = self.values["plane"]
        self._gesture = None
        self._handles_key = None
        self._flat_source = self._flat_frame = self._flat = None    # the anchors of the model on the plane being drawn on, kept per frame

    @property
    def busy(self):
        return self._gesture is not None

    @property
    def plane(self):
        return self.values["plane"]

    @property
    def editing(self):
        return self.values["mode"] == "Edit"

    def disc_slots(self):
        """The option disc, clockwise from the top: nothing, then on the first page rectangle, circle, edit and line, on the second page
        arc and the planes XY, XZ and YZ, and nothing at the bottom."""
        none = DiscSlot("")
        if self._page == 0:
            return (none, DiscSlot("Rectangle", "mode", "Rectangle"), DiscSlot("Circle", "mode", "Circle"), none,
                    DiscSlot("Edit", "mode", "Edit"), DiscSlot("Line", "mode", "Line"))
        return (none, DiscSlot("Arc", "mode", "Arc"), DiscSlot("XY plane", "plane", "XY"), none,
                DiscSlot("XZ plane", "plane", "XZ"), DiscSlot("YZ plane", "plane", "YZ"))

    def disc_hub(self):
        return [self.grid_text(), self.values["mode"] if self.editing else f"{self.values['mode']} on {self.plane}"]

    def stick_click(self):
        """Turn to the other page of the option disc."""
        self._page = 1 - self._page
        return "Arc and planes" if self._page else "Line, Rectangle, Circle and Edit"

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
        if self._gesture is None and self.values["plane"] != self._plane_seen:      # another plane ends the sketch that is current
            self._plane_seen = self.values["plane"]
            if self._current(doc) is not None:
                self._select(doc, [])
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
        mode = self.placement
        if mode == "free":
            return (local[0], local[1]), []
        snapped = self._snap2(local)
        service = self._service("guide_anchors")
        if service is None or frame is None or mode == "grid":
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
        if kind == "Arc":
            if state.get("phase") != "bulge":
                return f"Arc: chord {self._format(math.dist((x0, y0), (x1, y1)))}"
            arc = sketchinfer.arc_through(state["start"], state["now"], state["bulge"])
            return "Arc: press on the third point" if arc is None else f"Arc: radius {self._format(arc[1])}"
        return f"Line: {self._format(math.dist((x0, y0), (x1, y1)))}"

    def _place(self, sketch, local, hand, apart_from=None, line_from=None):
        """The point (x, y) of the sketch for the hand at `local`: on the grid and the guides, off both while the A button is held. With
        `line_from` (the start of a line being drawn) the point also moves to where the line is exactly parallel or perpendicular to a
        slanted line of the sketch when it is nearly so, and to the length of a line of the sketch when it is nearly as long (the drawn
        line then gets that constraint)."""
        sk = self._sk()
        frame = sk.placement(sketch)
        point, found = self._align2(frame, local, sketch, apart_from)
        service = self._service("guide_anchors")
        if line_from is not None and service is not None and self.placement == "snap":
            reach = service(())[1]
            point, relation = guides.align_direction(line_from, point, sk.slanted_lines(sketch), reach)
            found = list(found)
            mid = lambda p, q: ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0, 0.0)
            if relation is not None:
                name, (a, b) = relation
                found.append(guides.Guide("axis", guides.OFF_AXIS, tuple(sk.frame_to_world(frame, mid(a, b))),
                                          tuple(sk.frame_to_world(frame, mid(line_from, point))), name))
            point, same = guides.align_length(line_from, point, sk.lines(sketch), reach)
            if same is not None:
                found.append(guides.Guide("axis", guides.OFF_AXIS, tuple(sk.frame_to_world(frame, mid(*same))),
                                          tuple(sk.frame_to_world(frame, mid(line_from, point))), "Equal length"))
        self.show_guides(found, self.grid * 0.5)
        return point

    def _preview(self, sketch, state):
        ghost = self._ghost()
        if ghost is not None:
            polylines = sketching.outline(state["kind"], state["start"], state["now"], c=state.get("bulge"))
            ghost.show_shape(Mesh(outline=[[self._sk().to_world(sketch, p) for p in line] for line in polylines]))

    def _follow(self, doc, hand, raw):
        sk = self._sk()
        state = self._gesture
        sketch = doc.getObject(state["sketch"])
        if sketch is None:
            self._abort()
            return
        local = sk.to_local(sketch, raw)
        if state.get("radius") is not None:
            self._follow_radius(doc, hand, sketch, local)
            return
        if state.get("edit") is not None:
            self._follow_edit(doc, hand, sketch, local)
            return
        if state.get("phase") == "bulge":                   # an arc has its ends: the third point follows the hand until the next press
            bulge = self._place(sketch, local, hand)
            if bulge != state["bulge"]:
                state["bulge"] = bulge
                self._haptic(0.08, 0.008)
            self._preview(sketch, state)
            self._readout(self._describe(state))
            if "trigger" in hand.pressed:
                if sketchinfer.arc_through(state["start"], state["now"], state["bulge"]) is None:
                    self._toast("The three points lie on a line")
                else:
                    self._finish_draw(doc, sketch, state)
            return
        if not hand.down("trigger"):                        # released: the shape is what the last frame left (A may let go in the same frame)
            if state["kind"] == "Arc" and self._extent(state) >= self.grid / 2:
                state["phase"], state["bulge"] = "bulge", state["now"]
                self.hide_guides()
                self._haptic(0.3, 0.02)
                self._readout(self._describe(state))
                return
            self._finish_draw(doc, sketch, state)
            return
        now = self._place(sketch, local, hand, line_from=state["start"] if state["kind"] == "Line" else None)
        if now != state["now"]:
            state["now"] = now
            self._haptic(0.08, 0.008)
        self._preview(sketch, state)
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
            elif kind == "Arc":
                _, kept = sk.add_arc(doc, sketch, start, now, state["bulge"])
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
        if kind == "curve" and sk.curve_kind(sketch, geo) == "circle":
            self._start_radius(doc, sketch, geo, sk.to_local(sketch, raw))
            return
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
                         "now": sk.point_position(sketch, geo, pos), "locked": sk.point_locked(sketch, geo, pos), "fix_changed": False}
        self._forget_hover()
        self._select(doc, [(sketch.Name, "")])
        self._haptic(0.3, 0.02)

    def _start_radius(self, doc, sketch, geo, local):
        """A press on a circle or an arc starts to drag its radius, which has a dimension from now on (made now when it has none): once
        the hand has left the press the radius grows and shrinks with the distance of the hand from the centre, in one undo step with
        the dimension."""
        sk = self._sk()
        doc.openTransaction(f"Radius of {sketch.Label}")
        index, made = sk.radius_dimension(sketch, geo), None
        if index is None:
            text, name = sk.dimension(doc, sketch, geo)
            if name is None:
                doc.abortTransaction()
                self._select(doc, [(sketch.Name, "")])
                self._toast(text)
                return
            doc.recompute()
            index, made = sk.radius_dimension(sketch, geo), text
        radius = sk.dimension_value(sketch, index)
        centre = sk.centre_of(sketch, geo)
        self._gesture = {"sketch": sketch.Name, "radius": geo, "index": index, "changed": made is not None, "kind": "Edit",
                         "now": radius, "made": made, "dragged": False, "start": (local[0], local[1]), "r0": radius,
                         "d0": ((local[0] - centre[0]) ** 2 + (local[1] - centre[1]) ** 2) ** 0.5, "moving": False}
        self._forget_hover()
        self._select(doc, [(sketch.Name, "")])
        self._haptic(0.3, 0.02)

    def _follow_radius(self, doc, hand, sketch, local):
        sk = self._sk()
        state = self._gesture
        if not hand.down("trigger"):
            self._gesture = None
            self._readout(None)
            if state["changed"]:
                doc.commitTransaction()
                self._toast(state["made"] if state["made"] and not state["dragged"] else f"Radius {self._format(state['now'])}")
                self._haptic(0.4, 0.03)
            else:
                doc.abortTransaction()
                self._toast(f"Radius {self._format(state['now'])}: drag to change it")
            self._select(doc, [(sketch.Name, "")])
            return
        mm = self._service("mm_per_metre", lambda: 1000.0)()
        if not state["moving"]:                             # a tap or a trembling hand leaves the radius as it is
            if ((local[0] - state["start"][0]) ** 2 + (local[1] - state["start"][1]) ** 2) ** 0.5 < DRAG_START * mm:
                self._readout(f"Radius: {self._format(state['now'])}")
                return
            state["moving"] = True
        centre = sk.centre_of(sketch, state["radius"])
        distance = ((local[0] - centre[0]) ** 2 + (local[1] - centre[1]) ** 2) ** 0.5
        wanted = state["r0"] + distance - state["d0"]       # the radius follows the distance of the hand from the centre, from where it was pressed
        radius = max(wanted, MIN_RADIUS) if self.placement == "free" else max(snapping.snap(wanted, self.grid), self.grid)
        if abs(radius - state["now"]) > 1e-9:
            error = sk.set_dimension(sketch, state["index"], radius)
            if error is not None:
                self._readout(error)
                return
            doc.recompute()
            state["now"], state["changed"], state["dragged"] = radius, True, True
            self._haptic(0.08, 0.008)
        self._readout(f"Radius: {self._format(state['now'])}")

    def toggle_fixed(self):
        """B while a point of a sketch is held: the point is fixed where it is (as constraints of the sketch: it stays put while other
        points are dragged or the sketch is changed), or released when it was fixed."""
        state = self._gesture
        doc = self._service("document", lambda: None)()
        sketch = doc.getObject(state["sketch"]) if state is not None and doc is not None else None
        if sketch is None or state.get("edit") is None:
            return None
        sk = self._sk()
        geo, pos = state["edit"]
        if state["locked"]:
            sk.unlock_point(sketch, geo, pos)
        elif not sk.lock_point(doc, sketch, geo, pos):
            return "The sketch cannot fix that point"
        state["locked"] = not state["locked"]
        state["fix_changed"] = True
        doc.recompute()
        return "Fixed the point" if state["locked"] else "Released the point"

    def _follow_edit(self, doc, hand, sketch, local):
        sk = self._sk()
        state = self._gesture
        if not hand.down("trigger"):
            self._gesture = None
            self._readout(None)
            self.hide_guides()
            if state["changed"] or state["fix_changed"]:
                doc.commitTransaction()
                if state["fix_changed"] and not state["changed"]:
                    self._toast(f"{'Fixed' if state['locked'] else 'Released'} a point of {sketch.Label}")
                else:
                    self._toast(f"Moved a point of {sketch.Label}")
                self._haptic(0.4, 0.03)
            else:
                doc.abortTransaction()
            self._select(doc, [(sketch.Name, "")])
            return
        geo, pos = state["edit"]
        if state["locked"]:
            self._readout("The point is fixed (B releases)")
            return
        target = self._place(sketch, local, hand, (geo, pos))
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
