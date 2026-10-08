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
"""The primitive tool: make a parametric box, cylinder, cone, sphere, torus, wedge or prism by moving a point in space.

The tip of the tool hand is the cursor. Its position snaps to the grid in document millimetres and a cross shows where a press
would start. Holding the trigger and moving the hand drags out an axis-aligned box; the chosen shape is fitted into it (a ghost
shows the result, the readout names the three sizes). Releasing the trigger makes the feature in one undo step; a tap without a
drag places the shape at a default size (4 grid steps) centred on the cursor. The stick chooses from an option disc of six
sections: the grid larger (up) and smaller (down), and four shapes; the click of the stick turns to the other page of shapes. A grip
or a change of tool cancels a drag.

Services (`ToolContext.services`; every one is optional so the tool also runs in tests):
  cursor(hand) -> stage point of the tip of that hand        to_document(point) -> document millimetres
  document() -> the active FreeCAD document or None          trigger_free() -> False while the interface owns the trigger
  ghost -> `render.ghost.Ghost`                              toast(text), readout(text or None), format_length(mm)
  create(doc, shape, lo, size), mesh(shape, lo, size)        replace `cad.primitives.create` and `cad.meshes.build` (tests)"""

from freecad.BlocksCAD.cad import meshes, primitives
from freecad.BlocksCAD.core import snapping
from freecad.BlocksCAD.tools.base import DiscSlot, Tool, ToolOption
from freecad.BlocksCAD.tools.registry import register

SHAPE_PAGES = (("Box", "Cylinder", "Cone", "Sphere"), ("Torus", "Wedge", "Prism", primitives.BLOCK))   # four shapes on the disc at a time


@register
class PrimitiveTool(Tool):
    name = "primitive"
    label = "Create"
    hint = "Drag a box in space to make a shape, tap to place one"
    controls = (("Trigger", "drag out a shape, tap: place one"), ("A", "trigger held: snap, grid, free"), ("Stick click", "other shapes"))
    options = (ToolOption("shape", "Shape", "choice", default="Box", choices=primitives.SHAPES + (primitives.BLOCK,)),)

    def __init__(self, ctx):
        super().__init__(ctx)
        self._page = 0
        self._start = None        # document point (on the grid) where the trigger went down
        self._current = None
        self._built = None       # (shape, lo, size) the ghost shows

    @property
    def busy(self):
        return self._start is not None

    def disc_slots(self):
        """The option disc, clockwise from the top: nothing, the four shapes of the page (the first at the lower left), nothing."""
        first, second, third, fourth = (DiscSlot(name, "shape", name) if name else DiscSlot("") for name in SHAPE_PAGES[self._page])
        return (DiscSlot(""), second, third, DiscSlot(""), fourth, first)

    def disc_hub(self):
        return [self.grid_text(), self.values["shape"]]

    def stick_click(self):
        """Turn to the other page of shapes."""
        self._page = (self._page + 1) % len(SHAPE_PAGES)
        return "Shapes: " + ", ".join(name for name in SHAPE_PAGES[self._page] if name)

    # services
    def _service(self, name, default=None):
        return self.ctx.services.get(name, default)

    def _format(self, mm):
        return self._service("format_length", lambda v: f"{v:g} mm")(mm)

    def _haptic(self, amplitude, duration):
        if self.ctx.haptic is not None:
            self.ctx.haptic(self.ctx.dominant, amplitude, duration)

    def _ghost(self):
        return self._service("ghost")

    # lifecycle
    def deactivate(self):
        self._cancel()
        ghost = self._ghost()
        if ghost is not None:
            ghost.hide()

    def _cancel(self):
        self._start = self._current = self._built = None
        self.hide_guides()
        ghost = self._ghost()
        if ghost is not None:
            ghost.hide_shape()
        readout = self._service("readout")
        if readout is not None:
            readout(None)

    def update(self, frame):
        cursor, to_document = self._service("cursor"), self._service("to_document")
        if cursor is None or to_document is None:
            return
        hand = frame.hands[self.ctx.dominant]
        raw = to_document(cursor(self.ctx.dominant))
        point, guides = self.place(raw)
        gripping = any(h.down("grip") for h in frame.hands)
        if self._start is not None:
            if gripping:
                self._cancel()
                return
            self.show_guides(guides, self.grid * 0.5)
            self._drag(hand, point)
            return
        free = self._service("trigger_free", lambda: True)()
        ghost = self._ghost()
        if ghost is not None:
            if free and not gripping and hand.aim.tracked:
                ghost.show_marker(point, self.grid * 0.75)
                self.show_guides(guides, self.grid * 0.5)
            else:
                ghost.hide_marker()
                self.hide_guides()
        if free and not gripping and "trigger" in hand.pressed and hand.aim.tracked:
            self._start = self._current = point
            self._haptic(0.3, 0.02)

    def _drag(self, hand, point):
        ghost, readout = self._ghost(), self._service("readout")
        if point != self._current:
            self._current = point
            self._haptic(0.08, 0.008)
        lo, size = snapping.drag_box(self._start, self._current, self.grid)
        shape = self.values["shape"]
        if ghost is not None:
            ghost.hide_marker()
            key = (shape, lo, size)
            if key != self._built:
                self._built = key
                ghost.show_shape(self._service("mesh", meshes.build)(shape, lo, size))
                ghost.show_box(lo, size)
        if readout is not None:
            readout(primitives.describe(shape, size, self._format))
        if not hand.down("trigger"):
            self._commit(shape, lo, size)

    def _commit(self, shape, lo, size):
        toast = self._service("toast", lambda text: None)
        doc = self._service("document", lambda: None)()
        self._cancel()
        if doc is None:
            toast("No document open")
            return
        try:
            self._service("create", primitives.create)(doc, shape, lo, size)
        except Exception as error:      # a shape FreeCAD cannot make must not stop the session
            toast(f"Could not make the {shape.lower()}")
            print(f"BlocksCAD: could not make a {shape}: {error}")
            return
        self._haptic(0.5, 0.04)
        toast(primitives.describe(f"{shape} made", size, self._format))
