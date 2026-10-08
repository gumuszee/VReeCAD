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
"""The Select tool: touch things and select them, one or many (docs/ux-design.md, Select tool).

The tip of the tool hand is the cursor. The option **Target** says what is touched: whole objects, faces, edges or vertices (the
nearest element of that sort within its reach). The element is highlighted, and the trigger pressed on it changes the selection,
which is FreeCAD's own selection: **Replace** makes it the only selected element (a press on nothing clears the selection), **Add**
appends it and **Remove** takes it out. Every target can be selected many times over, so a selection may hold objects, faces, edges
and vertices side by side. The option disc of the stick: the four targets (top, right and bottom), Remove and Add (left, a second
push of the same section goes back to Replace). The click of the stick puts the target and the operation back to their defaults.
The tool changes nothing in the document; the value panels of the left-hand carousel follow the selection (`ui/value_module.py`)."""

from freecad.BlocksCAD.cad import picking
from freecad.BlocksCAD.core import selecting
from freecad.BlocksCAD.tools.base import DiscSlot, ToolOption
from freecad.BlocksCAD.tools.registry import register
from freecad.BlocksCAD.tools.touch import TouchTool

TARGETS = ("Object", "Face", "Edge", "Vertex")
KINDS = {"Object": "object", "Face": "face", "Edge": "edge", "Vertex": "vertex"}


@register
class SelectTool(TouchTool):
    name = "select"
    label = "Select"
    controls = (("Trigger", "select what the tip touches"), ("Stick click", "back to Object and Replace"))
    hint = "Touch and press the trigger to select; the stick chooses objects, faces, edges or vertices, and adds or removes"
    options = (ToolOption("target", "Select", "choice", default=TARGETS[0], choices=TARGETS),
               ToolOption("operation", "Mode", "choice", default=selecting.REPLACE, choices=selecting.OPERATIONS))

    def __init__(self, ctx):
        super().__init__(ctx)
        self._kind_shown = None       # the sort of element the hover was made for

    @property
    def pick_kind(self):
        return KINDS[self.values["target"]]

    def disc_slots(self):
        """The option disc, clockwise from the top: the targets (object, face, edge, vertex), then remove and add."""
        return (DiscSlot("Object", "target", "Object"), DiscSlot("Face", "target", "Face"), DiscSlot("Edge", "target", "Edge"),
                DiscSlot("Vertex", "target", "Vertex"), DiscSlot("Remove", "operation", selecting.REMOVE, "toggle"),
                DiscSlot("Add", "operation", selecting.ADD, "toggle"))

    def disc_hub(self):
        return [self.values["target"], self.values["operation"]]

    def stick_click(self):
        self.values["target"], self.values["operation"] = (o.default for o in self.options)
        return "Select objects, replace"

    def deactivate(self):
        super().deactivate()
        self._kind_shown = None

    def update(self, frame):
        cursor, to_document = self._service("cursor"), self._service("to_document")
        doc = self._service("document", lambda: None)()
        if cursor is None or to_document is None or doc is None:
            return
        hand = frame.hands[self.ctx.dominant]
        raw = to_document(cursor(self.ctx.dominant))
        gripping = any(h.down("grip") for h in frame.hands)
        if self.pick_kind != self._kind_shown:          # another target: what was highlighted is not what a press selects now
            self._kind_shown = self.pick_kind
            self._forget_hover()
        free = self._service("trigger_free", lambda: True)() and not gripping and hand.aim.tracked
        pick = self._steady(self._touch(doc, raw) if free else None, frame.dt)
        self._show_hover(doc, pick)
        if free and "trigger" in hand.pressed:
            self._press(doc, pick)
        self._show_selection(doc)

    def _name_of(self, doc, pick):
        obj = doc.getObject(pick.name)
        label = obj.Label if obj is not None else pick.name
        return f"{label} {pick.sub}" if pick.sub else label

    def _press(self, doc, pick):
        operation = self.values["operation"]
        current = list(self._service("get_selection", picking.get_selection)(doc))
        if pick is None:
            if operation == selecting.REPLACE and current:
                self._select(doc, [])
                self._toast("Selection cleared")
            return
        items = selecting.combine(current, (pick.name, pick.sub), operation)
        text = self._name_of(doc, pick)
        if items == current:
            if operation != selecting.REPLACE:
                self._toast(f"{text} is already selected" if operation == selecting.ADD else f"{text} is not selected")
            return
        self._select(doc, items)
        if operation == selecting.ADD:
            self._toast(f"Added {text}, {len(items)} selected")
        elif operation == selecting.REMOVE:
            self._toast(f"Removed {text}, {len(items)} selected")
        else:
            self._toast(f"Selected {text}")
        self._haptic(0.3, 0.02)
