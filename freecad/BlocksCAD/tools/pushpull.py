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
"""The Push/Pull tool: move a flat face of a solid along its normal (docs/ux-design.md, Push/Pull tool).

The tip of the tool hand is the cursor and only faces are touched (`tools/touch.py`). The trigger pressed on a flat face starts the
gesture: the distance the hand moves along the normal of the face, rounded to the grid, is how far the face is pushed (out of the
solid) or pulled (into it); a ghost shows the volume the face sweeps and the readout names the distance. Releasing makes the change
as parametric features (`cad/pushpull.py`) in one undo step; a release within one grid step of the start is a tap that selects the
face. A grip cancels. The stick up and down change the grid.

Services besides those of `TouchTool`: ghost (`render.ghost.Ghost`), and `pushpull_face(obj, sub)`, `pushpull_mesh(obj, sub, distance)`
and `pushpull(doc, name, sub, distance)` that replace `cad.pushpull.face_info`, `preview_mesh` and `apply` (tests)."""

from freecad.BlocksCAD.cad import pushpull
from freecad.BlocksCAD.core import guides
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.tools.registry import register
from freecad.BlocksCAD.tools.touch import TouchTool



@register
class PushPullTool(TouchTool):
    name = "pushpull"
    label = "Push/Pull"
    controls = (("Trigger", "press a face, move along it"),)
    hint = "Press on a flat face and move the hand along it to push or pull"
    pick_kind = "face"

    def __init__(self, ctx):
        super().__init__(ctx)
        self._drag = None            # state of a gesture in progress
        self._built = None           # the distance the ghost shows

    @property
    def busy(self):
        return self._drag is not None

    def _ghost(self):
        return self._service("ghost")

    # lifecycle
    def deactivate(self):
        self._cancel()
        super().deactivate()

    def _cancel(self):
        self._drag = self._built = None
        self.hide_guides()
        ghost = self._ghost()
        if ghost is not None:
            ghost.hide_shape()
        self._readout(None)

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
                self._cancel()
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
        elif free and "trigger" in hand.pressed:
            self._select(doc, [])
        self._show_selection(doc)

    def _press(self, doc, pick, raw):
        obj = doc.getObject(pick.name)
        info = None if obj is None else self._service("pushpull_face", pushpull.face_info)(obj, pick.sub)
        self._select(doc, [(pick.name, pick.sub)])
        if info is None:
            self._toast("Only flat faces can be pushed or pulled")
            return
        self._drag = {"pick": pick, "start": raw, "centre": info[0], "normal": info[1], "distance": 0.0, "source": None, "candidates": []}
        self._forget_hover()
        self._haptic(0.3, 0.02)

    def _follow(self, doc, hand, raw):
        state = self._drag
        pick = state["pick"]
        obj = doc.getObject(pick.name)
        if obj is None:
            self._cancel()
            return
        distance, anchor = self._align(state, obj, mu.dot(mu.sub(raw, state["start"]), state["normal"]))
        self._show_guide(state, raw, anchor)
        if distance != state["distance"]:
            state["distance"] = distance
            self._haptic(0.08, 0.008)
        ghost = self._ghost()
        if ghost is not None and distance != self._built:
            self._built = distance
            mesh = self._service("pushpull_mesh", pushpull.preview_mesh)(obj, pick.sub, distance) if distance else None
            if mesh is None:
                ghost.hide_shape()
            else:
                ghost.show_shape(mesh)
        self._readout(pushpull.describe(distance, self._format))
        if not hand.down("trigger"):
            self._commit(doc, state)

    def _align(self, state, obj, raw_distance):
        """(distance, anchor): the distance rounded to the grid, or the one that puts the face level with a point of the model (the
        service `guide_anchors`, without the object itself; a point already in the plane of the face is no anchor) and that point."""
        grid = pushpull.snapped(raw_distance, self.grid)
        service = self._service("guide_anchors")
        if service is None:
            return grid, None
        anchors, tolerance = service((obj.Name,))
        if state["source"] is not anchors:
            state["source"] = anchors
            offsets = ((mu.dot(mu.sub(a, state["centre"]), state["normal"]), a) for a in anchors)
            state["candidates"] = [(d, a) for d, a in offsets if abs(d) > 1e-6]
        return guides.align_along(raw_distance, grid, state["candidates"], tolerance)

    def _show_guide(self, state, raw, anchor):
        """The guide of the anchor the face lines up with: a cross on it and a line to the hand's place in the plane of the face."""
        if anchor is None:
            self.hide_guides()
            return
        normal = state["normal"]
        axis = next((i for i in range(3) if abs(normal[i]) > 0.999), guides.OFF_AXIS)
        point = mu.sub(raw, mu.mul(normal, mu.dot(mu.sub(raw, anchor), normal)))
        self.show_guides([guides.Guide("axis", axis, tuple(anchor), tuple(point))], self.grid * 0.5)

    def _commit(self, doc, state):
        self._cancel()
        pick, distance = state["pick"], state["distance"]
        if distance == 0:
            self._select(doc, [(pick.name, pick.sub)])           # a tap selects the face
            return
        try:
            text, result = self._service("pushpull", pushpull.apply)(doc, pick.name, pick.sub, distance)
        except Exception as error:      # a change FreeCAD cannot make must not stop the session
            self._toast("Could not push or pull the face")
            print(f"BlocksCAD: push/pull failed: {error}")
            return
        self._toast(text)
        if result is not None:
            self._select(doc, [(result, "")])
            self._haptic(0.5, 0.04)
