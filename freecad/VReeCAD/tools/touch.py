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
"""The base of the tools that touch the document with the tip of the tool hand (the Select and the Move tool).

The tip is the cursor. What it touches is highlighted (the hover) and what FreeCAD has selected is drawn in a colour of its own (the
selection). The hover moves to another element only after that has stayed under the hand for a moment, so a trembling hand does not
make it jump. A subclass sets `pick_kind` to touch one sort of element only, and decides what a press does.

Services (`ToolContext.services`, all optional): cursor(hand), to_document(point), mm_per_metre(), document(), trigger_free(),
highlight (`render.highlight.Highlights`), toast(text), readout(text or None), format_length(mm), and `pick`, `display`,
`get_selection`, `set_selection`, `clear_selection` that replace the functions of `cad.picking`."""

from freecad.VReeCAD.cad import picking
from freecad.VReeCAD.tools.base import Tool

MARKER = 0.004          # metres on the stage: the arm of the cross at a vertex
SWITCH_TO_NEW = 0.08    # seconds a new element must stay under the hand before the hover moves to it (the hand trembles)
SWITCH_TO_NONE = 0.15   # and before the hover goes away


class TouchTool(Tool):
    pick_kind = None      # None: the nearest vertex, edge, face or the inside of a solid; else "vertex", "edge", "face" or "object"

    def __init__(self, ctx):
        super().__init__(ctx)
        self._hover = None            # the `Pick` under the cursor
        self._hover_key = None
        self._candidate = None        # what the hand touches now, while the hover has not moved to it yet
        self._candidate_age = 0.0
        self._selected_key = None

    # services
    def _service(self, name, default=None):
        return self.ctx.services.get(name, default)

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
        highlight = self._service("highlight")
        if highlight is not None:
            highlight.hide()
        self._hover = self._hover_key = self._selected_key = None

    def _forget_hover(self):
        """Drop the hover at once (what is touched is chosen in another way now)."""
        highlight = self._service("highlight")
        if highlight is not None:
            highlight.hover.hide()
        self._hover = self._hover_key = self._candidate = None
        self._candidate_age = 0.0

    # touching and showing
    def _touch(self, doc, point):
        pick = self._service("pick", picking.pick)
        mm = self._service("mm_per_metre", lambda: 1000.0)()
        try:
            return pick(doc, point, mm, self.pick_kind) if self.pick_kind else pick(doc, point, mm)
        except Exception as error:      # a shape that cannot be measured must not stop the session
            print(f"VReeCAD: picking failed: {error}")
            return None

    def _steady(self, touched, dt):
        """The element the hover shows: it moves to another element only when that has stayed under the hand for a moment, so a
        trembling hand does not make the highlight jump between a corner, its edge and its face."""
        def same(a, b):
            return (a.name, a.sub) == (b.name, b.sub) if a is not None and b is not None else a is b

        if same(touched, self._hover):
            self._candidate, self._candidate_age = None, 0.0
            return touched
        if self._hover is None and touched is not None:
            return touched                                       # nothing was shown: show at once
        if not same(touched, self._candidate):
            self._candidate, self._candidate_age = touched, 0.0
        self._candidate_age += dt
        if self._candidate_age >= (SWITCH_TO_NONE if touched is None else SWITCH_TO_NEW):
            self._candidate, self._candidate_age = None, 0.0
            return touched
        return self._hover

    def _display(self, doc, name, sub):
        obj = doc.getObject(name)
        if obj is None or getattr(obj, "Shape", None) is None or obj.Shape.isNull():
            return None, None
        try:
            return self._service("display", picking.display)(obj, sub), picking.signature(obj, sub)
        except Exception as error:
            print(f"VReeCAD: cannot draw {name} {sub}: {error}")
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
        key = []
        for name, sub in items:
            obj = doc.getObject(name)
            if obj is not None and getattr(obj, "Shape", None) is not None and not obj.Shape.isNull():
                key.append(picking.signature(obj, sub))
        key = tuple(key)
        if key == self._selected_key:
            return                                               # nothing changed: the geometry is not built again
        self._selected_key = key
        shown = [d for d in (self._display(doc, name, sub)[0] for name, sub in items) if d is not None]
        if shown:
            highlight.selected.show(shown, self._marker_half())
        else:
            highlight.selected.hide()

    def _select(self, doc, items):
        if items:
            self._service("set_selection", picking.set_selection)(doc, items)
        else:
            self._service("clear_selection", picking.clear_selection)()
