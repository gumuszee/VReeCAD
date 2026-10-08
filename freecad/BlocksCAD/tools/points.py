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
"""The Points tool: move the points of a block and split its edges (docs/ux-design.md, Points tool).

The tip of the tool hand is the cursor. Every point of every block is marked, the point (or in the split mode the edge) the cursor
touches is highlighted (`tools/touch.py`). In the **Move** mode the trigger pressed on a point drags it: the point follows the
cursor, rounded to the grid (the A button held leaves it free), and the block is built again at every step, so the solid follows the
hand; a position that makes no solid (a block turned inside out, a flat block) is refused and the point stays at the last good one.
In the **Split** mode the trigger pressed on an edge adds a point on it, where the cursor is nearest, and the drag goes on with that
new point. In the **Remove** mode the trigger pressed on a point takes it out of the block in one undo step: a point that splits an
edge vanishes, a corner is cut off (the corners next to it become a face of their own); a point whose removal leaves no solid, or
whose coordinates are bound to variables, stays. With the faces **Flat** the dragged point stays in the planes of the faces that have it (every face of four or more corners
is held flat: the plane of its other corners), so it moves in a plane, along a line or not at all; with **Free** faces a face that
bends is built from triangles. Releasing keeps the change as one undo step and selects the block (so the value panels follow it); a
grip cancels. The stick chooses from an option disc: the three modes and the two kinds of faces; its click
puts the mode and the faces back.

Services besides those of `TouchTool`: `blocks`, an object with the functions of `cad.block` that the tool uses (`pick`, `display`,
`handles`, `signature`, `read`, `apply`, `to_local`, `to_world`), replaced in tests."""

from freecad.BlocksCAD.cad import blockgeom
from freecad.BlocksCAD.core import snapping
from freecad.BlocksCAD.tools.base import DiscSlot, ToolOption
from freecad.BlocksCAD.tools.registry import register
from freecad.BlocksCAD.tools.touch import TouchTool

MODES = ("Move", "Split", "Remove")
KINDS = {"Move": "vertex", "Split": "edge", "Remove": "vertex"}
FACES = ("Free", "Flat")


@register
class PointsTool(TouchTool):
    name = "points"
    label = "Points"
    hint = "Press on a point of a block and drag it; the stick switches to splitting an edge or removing a point"
    controls = (("Trigger", "drag, split or remove a point"), ("A", "hold: off the grid"))
    options = (ToolOption("mode", "Mode", "choice", default=MODES[0], choices=MODES),
               ToolOption("faces", "Faces", "choice", default=FACES[0], choices=FACES))

    def __init__(self, ctx):
        super().__init__(ctx)
        self._drag = None             # the point being dragged
        self._handles_key = None      # what the markers of the points show

    @property
    def busy(self):
        return self._drag is not None

    @property
    def pick_kind(self):
        return KINDS[self.values["mode"]]

    def disc_slots(self):
        """The option disc, clockwise from the top: nothing, the three modes, free faces, flat faces."""
        return (DiscSlot(""), DiscSlot("Move point", "mode", MODES[0]), DiscSlot("Split edge", "mode", MODES[1]),
                DiscSlot("Remove point", "mode", MODES[2]), DiscSlot("Free faces", "faces", FACES[0]), DiscSlot("Flat faces", "faces", FACES[1]))

    def disc_hub(self):
        return [self.grid_text(), f"{self.values['mode']}, {self.values['faces'].lower()}"]

    def stick_click(self):
        for option in self.options:
            self.values[option.name] = option.default
        return "Mode and faces reset"

    def _blocks(self):
        service = self._service("blocks")
        if service is None:
            from freecad.BlocksCAD.cad import block as service
        return service

    # touching: the points and the edges of the blocks instead of the elements of the shapes
    def _touch(self, doc, point):
        mm = self._service("mm_per_metre", lambda: 1000.0)()
        try:
            return self._blocks().pick(doc, point, mm, self.pick_kind)
        except Exception as error:
            print(f"BlocksCAD: picking a point failed: {error}")
            return None

    def _display(self, doc, name, sub):
        obj = doc.getObject(name)
        if obj is None:
            return None, None
        try:
            vertices, _ = self._blocks().read(obj)
            return self._blocks().display(obj, sub), (name, sub, tuple(vertices))
        except Exception as error:
            print(f"BlocksCAD: cannot draw {name} {sub}: {error}")
            return None, None

    def _show_selection(self, doc):
        """Mark every point of every block."""
        highlight = self._service("highlight")
        if highlight is None:
            return
        key = self._blocks().signature(doc)
        if key == self._selected_key:
            return
        self._selected_key = key
        markers = self._blocks().handles(doc)
        if markers.markers:
            highlight.selected.show([markers], self._marker_half())
        else:
            highlight.selected.hide()

    # lifecycle
    def activate(self):
        self.values["mode"] = MODES[0]          # the tool always starts by moving points; the grid and the faces stay as they were

    def deactivate(self):
        if self._drag is not None:
            self._abort()
        self.hide_guides()
        super().deactivate()

    def update(self, frame):
        cursor, to_document = self._service("cursor"), self._service("to_document")
        doc = self._service("document", lambda: None)()
        if cursor is None or to_document is None or doc is None:
            return
        hand = frame.hands[self.ctx.dominant]
        raw = to_document(cursor(self.ctx.dominant))
        gripping = any(h.down("grip") for h in frame.hands)
        if self._drag is not None:
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
        if free and pick is not None and "trigger" in hand.pressed:
            self._press(doc, pick, raw)
        elif free and pick is None and "trigger" in hand.pressed and not self._blocks().blocks(doc):
            self._toast("Nothing to edit: make a box or a block with the Create tool")
        self._show_selection(doc)

    # dragging a point
    def _press(self, doc, pick, raw):
        blocks = self._blocks()
        obj = doc.getObject(pick.name)
        if obj is None:
            return
        vertices, faces = blocks.read(obj)
        kind, what = blocks.parse_sub(pick.sub)
        removing = kind == "point" and self.values["mode"] == MODES[2]
        if removing and getattr(blocks, "has_bound_points", lambda o: False)(obj):
            self._toast("Unbind the points of the block first")
            return
        doc.openTransaction(f"{'Remove point' if removing else 'Move point' if kind == 'point' else 'Split edge'} of {obj.Label}")
        convert = getattr(blocks, "convert_box", None)
        if convert is not None and obj.TypeId == "Part::Box":      # a box becomes a block as the press starts: one undo step with the move
            try:
                obj = convert(doc, obj)
            except Exception as error:
                doc.abortTransaction()
                self._toast("Could not turn the box into a block")
                print(f"BlocksCAD: cannot turn {obj.Label} into a block: {error}")
                return
        if removing:
            self._remove(doc, obj, what, vertices, faces)
            return
        if kind == "segment":
            a, b = what
            _, point, _ = self._edge_point(vertices, a, b, blocks.to_local(obj, raw))
            if (min(a, b), max(a, b)) not in blockgeom.edges(faces):       # a line that cuts a bent face into triangles: it becomes an edge
                faces = blockgeom.cut_face(faces, a, b)
            new_vertices, new_faces, index = blockgeom.split_edge(vertices, faces, a, b, point)
            error = blocks.apply(doc, obj, new_vertices, new_faces)
            if error is not None:
                doc.abortTransaction()
                self._toast(error)
                return
            vertices, faces, what, label = new_vertices, new_faces, index, "Split"
        else:
            label = "Moved"
        planes = blockgeom.face_planes(vertices, faces, what) if self.values["faces"] == "Flat" else []
        self._drag = {"name": obj.Name, "label": obj.Label, "index": what, "now": vertices[what], "changed": label == "Split",
                      "verb": label, "planes": planes}
        self._forget_hover()
        blocks.set_picked(obj, what)                        # the value panels show this point
        self._select(doc, [(obj.Name, "")])
        self._haptic(0.3, 0.02)

    def _remove(self, doc, obj, index, vertices, faces):
        """Take point `index` out of the block (the transaction is open): one undo step, or nothing when the result is no solid."""
        blocks = self._blocks()
        try:
            new_vertices, new_faces = blockgeom.remove_vertex(vertices, faces, index)
        except ValueError as error:
            doc.abortTransaction()
            self._toast(str(error))
            return
        error = blocks.apply(doc, obj, new_vertices, new_faces)
        if error is not None:
            doc.abortTransaction()
            self._toast("Cannot remove that point: " + error[0].lower() + error[1:])
            return
        doc.commitTransaction()
        self._forget_hover()
        blocks.set_picked(obj, None)
        self._select(doc, [(obj.Name, "")])
        self._toast(f"Removed point {index} of {obj.Label}")
        self._haptic(0.4, 0.03)

    @staticmethod
    def _edge_point(vertices, a, b, local):
        return None, blockgeom.inner_point_on_segment(local, vertices[a], vertices[b]), None

    def _follow(self, doc, hand, raw):
        blocks = self._blocks()
        state = self._drag
        obj = doc.getObject(state["name"])
        if obj is None:
            self._abort()
            return
        if not hand.down("trigger"):
            self._finish(doc)
            return
        free = hand.down("button1")                         # the A button leaves the point off the grid
        if free:
            target = raw
            self.hide_guides()
        else:
            target, guides = self.align(raw, snapping.snap_point(raw, self.grid), (state["name"],))
            self.show_guides(guides, self.grid * 0.5)
        local = tuple(blocks.to_local(obj, target))
        if state["planes"]:
            local = blockgeom.constrain_to_planes(local, state["planes"])
        if local != state["now"]:
            vertices, _ = blocks.read(obj)
            if blockgeom.coincident(vertices, state["index"], local) is not None:
                self._readout("Two points cannot be at the same place")
                return
            error = blocks.apply(doc, obj, blockgeom.move_vertex(vertices, state["index"], local))
            if error is None:
                state["now"], state["changed"] = local, True
                self._haptic(0.08, 0.008)
            else:
                self._readout(error)
                return
        world = blocks.to_world(obj, state["now"])
        held = " (flat)" if state["planes"] else ""
        self._readout(f"Point {state['index']}: " + ", ".join("0" if abs(c) < 1e-6 else self._format(c) for c in world) + held)

    def _finish(self, doc):
        state, self._drag = self._drag, None
        self._readout(None)
        self.hide_guides()
        if state["changed"]:
            doc.commitTransaction()
            self._toast(f"{state['verb']} point {state['index']} of {state['label']}")
            self._haptic(0.4, 0.03)
        else:
            doc.abortTransaction()
        self._select(doc, [(state["name"], "")])

    def _abort(self):
        self._drag = None
        self._readout(None)
        self.hide_guides()
        doc = self._service("document", lambda: None)()
        if doc is not None:
            doc.abortTransaction()
            doc.recompute()
