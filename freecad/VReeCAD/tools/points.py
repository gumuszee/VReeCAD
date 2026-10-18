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

from freecad.VReeCAD.cad import blockcurve, blockgeom
from freecad.VReeCAD.core import mathutil as mu
from freecad.VReeCAD.tools.base import DiscSlot, ToolOption
from freecad.VReeCAD.tools.registry import register
from freecad.VReeCAD.tools.touch import TouchTool

DRAG_START = 0.012          # metres on the stage: a point that was pressed starts to move only when the hand has moved this far, so a tap picks it
MODES = ("Move", "Split", "Remove", "Bend")
KINDS = {"Move": "vertex", "Split": "edge", "Remove": "vertex", "Bend": "curve"}
FACES = ("Free", "Flat")


@register
class PointsTool(TouchTool):
    name = "points"
    label = "Points"
    hint = "Press on a point of a block and drag it; the stick switches to splitting an edge, removing a point or bending an edge"
    controls = (("Trigger", "move, split, remove, bend, handle"), ("A", "trigger held: snap, grid, free"),
                ("B", "held: fix/straighten, tap: undo, hold: redo"), ("Stick click", "back to Move, Free faces"))
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
        """The option disc, clockwise from the top: the four modes, free faces, flat faces."""
        return (DiscSlot("Move point", "mode", MODES[0]), DiscSlot("Split edge", "mode", MODES[1]), DiscSlot("Remove point", "mode", MODES[2]),
                DiscSlot("Bend edge", "mode", MODES[3]), DiscSlot("Free faces", "faces", FACES[0]), DiscSlot("Flat faces", "faces", FACES[1]), DiscSlot(""), DiscSlot(""))

    def disc_hub(self):
        return [self.grid_text(), f"{self.values['mode']}, {self.values['faces'].lower()}"]

    def stick_click(self):
        for option in self.options:
            self.values[option.name] = option.default
        return "Mode and faces reset"

    def _blocks(self):
        service = self._service("blocks")
        if service is None:
            from freecad.VReeCAD.cad import block as service
        return service

    # touching: the points and the edges of the blocks instead of the elements of the shapes
    def _touch(self, doc, point):
        mm = self._service("mm_per_metre", lambda: 1000.0)()
        try:
            return self._blocks().pick(doc, point, mm, self.pick_kind)
        except Exception as error:
            print(f"VReeCAD: picking a point failed: {error}")
            return None

    def _display(self, doc, name, sub):
        obj = doc.getObject(name)
        if obj is None:
            return None, None
        try:
            vertices, _ = self._blocks().read(obj)
            return self._blocks().display(obj, sub), (name, sub, tuple(vertices), getattr(self._blocks(), "handle_text", lambda o: ())(obj))
        except Exception as error:
            print(f"VReeCAD: cannot draw {name} {sub}: {error}")
            return None, None

    def _show_selection(self, doc):
        """Mark every point of every block; in the Bend mode also the handles of the curved edges."""
        highlight = self._service("highlight")
        if highlight is None:
            return
        curves = self.values["mode"] == MODES[3]
        key = (curves, self._blocks().signature(doc))
        if key == self._selected_key:
            return
        self._selected_key = key
        markers = self._blocks().handles(doc, curves=True) if curves else self._blocks().handles(doc)
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
        bending = self.values["mode"] == MODES[3]
        if kind == "handle" and not bending:
            return                                          # a hover from the Bend mode that the mode has left
        removing = kind == "point" and self.values["mode"] == MODES[2]
        if removing and getattr(blocks, "has_bound_points", lambda o: False)(obj):
            self._toast("Unbind the points of the block first")
            return
        if removing and getattr(blocks, "is_point_fixed", lambda o, i: False)(obj, what):
            self._toast(f"Point {what} is fixed: press B while holding it to release it")
            return
        doc.openTransaction(f"{'Remove point' if removing else 'Move point' if kind == 'point' else 'Bend edge' if bending else 'Split edge'} of {obj.Label}")
        convert = getattr(blocks, "convert_box", None)
        if convert is not None and obj.TypeId == "Part::Box":      # a box becomes a block as the press starts: one undo step with the move
            try:
                obj = convert(doc, obj)
            except Exception as error:
                doc.abortTransaction()
                self._toast("Could not turn the box into a block")
                print(f"VReeCAD: cannot turn {obj.Label} into a block: {error}")
                return
        if removing:
            self._remove(doc, obj, what, vertices, faces)
            return
        if bending:
            self._begin_bend(doc, obj, kind, what, raw, vertices, faces)
            return
        if kind == "segment":
            a, b = what
            curved = getattr(blocks, "is_curved", lambda o, x, y: False)(obj, a, b)
            if curved:                                      # the new point lies on the curve, which the halves go on to follow
                t, point = blocks.edge_point(obj, a, b, blocks.to_local(obj, raw))
            else:
                _, point, _ = self._edge_point(vertices, a, b, blocks.to_local(obj, raw))
            if (min(a, b), max(a, b)) not in blockgeom.edges(faces):       # a line that cuts a bent face into triangles: it becomes an edge
                faces = blockgeom.cut_face(faces, a, b)
            new_vertices, new_faces, index = blockgeom.split_edge(vertices, faces, a, b, point)
            if curved:
                blocks.split_handles(obj, a, b, index, t)
            error = blocks.apply(doc, obj, new_vertices, new_faces)
            if error is not None:
                doc.abortTransaction()
                self._toast(error)
                return
            vertices, faces, what, label = new_vertices, new_faces, index, "Split"
        else:
            label = "Moved"
        planes = blockgeom.face_planes(vertices, faces, what) if self.values["faces"] == "Flat" else []
        fixed = getattr(blocks, "is_point_fixed", lambda o, i: False)(obj, what)
        self._drag = {"name": obj.Name, "label": obj.Label, "index": what, "now": vertices[what], "changed": label == "Split",
                      "verb": label, "planes": planes, "start": tuple(raw), "moving": label == "Split", "fixed": fixed, "fix_changed": False,
                      "rebase": False}
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
        getattr(blocks, "renumber_handles", lambda o, i: None)(obj, index)
        error = blocks.apply(doc, obj, new_vertices, new_faces)
        if error is not None:
            doc.abortTransaction()
            self._toast("Cannot remove that point: " + error[0].lower() + error[1:])
            return
        getattr(blocks, "renumber_fixed", lambda o, i: None)(obj, index)
        doc.commitTransaction()
        self._forget_hover()
        blocks.set_picked(obj, None)
        self._select(doc, [(obj.Name, "")])
        self._toast(f"Removed point {index} of {obj.Label}")
        self._haptic(0.4, 0.03)

    @staticmethod
    def _edge_point(vertices, a, b, local):
        return None, blockgeom.inner_point_on_segment(local, vertices[a], vertices[b]), None

    # bending an edge: the curve itself or one of its handles is dragged
    def _begin_bend(self, doc, obj, kind, what, raw, vertices, faces):
        """The press of the Bend mode (the transaction is open): the edge `what` is grabbed where `raw` touches it, or the tip of the
        handle `what`; the drag moves it freely in space."""
        blocks = self._blocks()
        a, b = what[:2]
        if (min(a, b), max(a, b)) not in blockgeom.edges(faces):       # a line that cuts a bent face into triangles: it becomes an edge
            error = blocks.apply(doc, obj, vertices, blockgeom.cut_face(faces, a, b))
            if error is not None:
                doc.abortTransaction()
                self._toast(error)
                return
        t = blocks.edge_point(obj, a, b, blocks.to_local(obj, raw))[0] if kind == "segment" else None
        bend = {"a": min(a, b), "b": max(a, b), "end": what[2] if kind == "handle" else None, "t": t}
        self._drag = {"name": obj.Name, "label": obj.Label, "index": None, "now": None, "changed": False, "verb": "Bent", "planes": [],
                      "start": tuple(raw), "moving": False, "fixed": False, "fix_changed": False, "rebase": False, "bend": bend}
        self._bend_anchor(obj)
        self._forget_hover()
        self._select(doc, [(obj.Name, "")])
        self._haptic(0.3, 0.02)

    def _bend_anchor(self, obj):
        """Read the curve of the edge being bent as it is, and the point of it that the hand holds (state of the drag)."""
        blocks = self._blocks()
        state = self._drag
        bend = state["bend"]
        vertices, _ = blocks.read(obj)
        curve = blockcurve.poles(vertices, blocks.read_handles(obj), bend["a"], bend["b"])
        if bend["end"] is None:
            anchor = blockcurve.point_at(curve, blockcurve.clamp_t(bend["t"]))
        else:
            anchor = curve[1] if bend["end"] == 0 else curve[2]
        state["curve0"], state["anchor0"] = curve, anchor

    def _follow_bend(self, doc, obj, target):
        """Bend the edge so that what the hand holds goes with the hand (`target` is the placed cursor); False when the block refuses."""
        blocks = self._blocks()
        state = self._drag
        bend = state["bend"]
        delta = mu.sub(target, state["start"])
        desired = tuple(blocks.to_local(obj, mu.add(blocks.to_world(obj, state["anchor0"]), delta)))
        curve = list(state["curve0"])
        if bend["end"] is None:
            curve = blockcurve.bend_through(curve, bend["t"], desired)
        else:
            curve[1 if bend["end"] == 0 else 2] = desired
        if state["now"] is not None and all(mu.length(mu.sub(p, q)) < 1e-9 for p, q in zip(curve, state["now"])):
            return True
        vertices, _ = blocks.read(obj)
        handles = blockcurve.store_edge(blocks.read_handles(obj), vertices, bend["a"], bend["b"], curve)
        error = blocks.set_handles(doc, obj, handles)
        if error is not None:
            self._readout(error)
            return False
        state["now"], state["changed"] = curve, True
        self._haptic(0.08, 0.008)
        what = "Edge" if bend["end"] is None else "Handle of"
        self._readout(f"{what} {bend['a']}-{bend['b']}: handles {self._format(mu.length(mu.sub(curve[1], curve[0])))} and "
                      f"{self._format(mu.length(mu.sub(curve[2], curve[3])))}")
        return True

    def _straighten(self, doc, obj):
        """B while an edge is bent: the edge goes back to the straight line and the hand goes on from there."""
        blocks = self._blocks()
        state = self._drag
        bend = state["bend"]
        handles = blocks.read_handles(obj)
        if blockcurve.key(bend["a"], bend["b"]) not in handles:
            return None
        del handles[blockcurve.key(bend["a"], bend["b"])]
        error = blocks.set_handles(doc, obj, handles)
        if error is not None:
            return error
        state["changed"], state["rebase"], state["now"] = True, True, None
        return f"Straightened edge {bend['a']}-{bend['b']}"

    def toggle_fixed(self):
        """B while a point is held: the point is fixed (the tool does not move it), or released when it was fixed. While an edge is bent
        it is straightened."""
        state = self._drag
        doc = self._service("document", lambda: None)()
        blocks = self._blocks()
        obj = doc.getObject(state["name"]) if state is not None and doc is not None else None
        if state is not None and state.get("bend") and obj is not None:
            return self._straighten(doc, obj)
        setter = getattr(blocks, "set_point_fixed", None)
        if obj is None or setter is None:
            return None
        state["fixed"] = not state["fixed"]
        setter(obj, state["index"], state["fixed"])
        state["fix_changed"], state["rebase"] = True, True
        return f"Fixed point {state['index']}" if state["fixed"] else f"Released point {state['index']}"

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
        if state["rebase"]:                                 # fixed or released: the hand goes on from where it is
            state["rebase"], state["start"], state["moving"] = False, tuple(raw), False
            if state.get("bend"):
                self._bend_anchor(obj)
        if state["fixed"]:
            self._readout(f"Point {state['index']} is fixed (B releases)")
            return
        if not state["moving"]:                             # a tap picks the point: it moves only once the hand has left the place of the press
            mm = self._service("mm_per_metre", lambda: 1000.0)()
            if mu.length(mu.sub(raw, state["start"])) < DRAG_START * mm:
                self._readout(f"Point {state['index']}")
                return
            state["moving"] = True
        target, guides = self.place(raw, (state["name"],))   # by the placement: the A button changes it while the trigger is held
        if guides:
            self.show_guides(guides, self.grid * 0.5)
        else:
            self.hide_guides()
        if state.get("bend"):
            self._follow_bend(doc, obj, target)
            return
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
        if state["changed"] or state["fix_changed"]:
            doc.commitTransaction()
            if state.get("bend"):
                self._toast(f"Bent edge {state['bend']['a']}-{state['bend']['b']} of {state['label']}")
            elif state["fix_changed"] and not state["changed"]:
                self._toast(f"{'Fixed' if state['fixed'] else 'Released'} point {state['index']} of {state['label']}")
            else:
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
