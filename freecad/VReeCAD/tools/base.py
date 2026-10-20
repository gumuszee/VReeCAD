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
"""Tool base class and the services a tool may use."""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

from freecad.VReeCAD.core import snapping, units

TICK_AMPLITUDE = 0.2    # a pulse weaker than this is a tick of a tool (a grid step, a guide), the others mark a start or an end
TICK_INTERVAL = 0.15    # s between two ticks of a hand


def tick_limited(send, interval=TICK_INTERVAL, now=time.monotonic):
    """`send(hand, amplitude, duration_s)` that drops a tick (amplitude below `TICK_AMPLITUDE`) when the hand got a pulse less than
    `interval` seconds ago, so a moving hand does not buzz; the stronger pulses always go through."""
    last = {}

    def haptic(hand, amplitude, duration_s):
        t = now()
        if amplitude < TICK_AMPLITUDE and t - last.get(hand, -interval) < interval:
            return
        last[hand] = t
        send(hand, amplitude, duration_s)
    return haptic


@dataclass(frozen=True)
class ToolOption:
    """One adjustable value of a tool, changed with the stick of the tool hand (docs/ux-design.md, Tool hand).

    kind "number": `low` to `high` in steps of `step`, shown with `unit` ("" for none); kind "length": millimetres, shown in the
    measurement system of the document; kind "choice": one of `choices`, cycled."""
    name: str
    label: str
    kind: str = "number"
    low: float = 0.0
    high: float = 1.0
    step: float = 1.0
    default: Any = 0.0
    unit: str = ""
    choices: Tuple[str, ...] = ()
    wrap: bool = True         # a choice that is stepped past its last value goes back to the first (else it stops)

    def clamp(self, value):
        """The nearest allowed value: clamped and rounded to the step (numbers), or a valid choice."""
        if self.kind == "choice":
            return value if value in self.choices else self.default
        value = min(max(value, self.low), self.high)
        return round(self.low + round((value - self.low) / self.step) * self.step, 9)

    def format(self, value, system=units.METRIC_MM):
        if self.kind == "choice":
            return str(value)
        if self.kind == "length":
            return units.format_length(value, system)
        text = f"{value:.0f}" if float(value).is_integer() else f"{value:g}"
        return f"{text} {self.unit}".strip()


@dataclass
class ToolContext:
    """Services handed to every tool. Fields are filled by the host (the XR widget or the Sim session).

    host:     the object that owns the scene, for the inherited tools that still call back into it
    haptic:   callable (hand, amplitude, duration_s) or None
    dominant: index of the tool hand (0 = left, 1 = right)
    """
    host: Any = None
    haptic: Optional[Callable] = None
    dominant: int = 1
    services: dict = field(default_factory=dict)

    @property
    def off_hand(self) -> int:
        return 1 - self.dominant


@dataclass(frozen=True)
class DiscSlot:
    """One of the six sections of the option disc that the stick of the tool hand chooses from (docs/ux-design.md, Tool options).

    kind "set": pushing the stick towards the section sets the option `option` to `value`. Kind "step": it steps the option by
    `value` (+1 or -1) and repeats while the stick is held out. Kind "toggle": it sets the option to `value`, or back to its default
    when it already has that value. A slot without an option is an empty section."""
    label: str
    option: str = ""
    value: Any = None
    kind: str = "set"


class Tool:
    """Subclass, set `name` (unique, lower case) and `label`, and register with `@register`."""

    name = ""
    label = ""
    hint = ""        # one line shown as a toast when the tool is chosen and as the tooltip of its button
    controls = ()    # (control, text) pairs for the controls card of the tool hand: what the trigger and the A button do in this tool
    options = ()     # `ToolOption`s: with `disc_slots` the disc chooses among them, else the first is on the stick up and down, the second left and right
    busy = False     # a gesture is running: the quick radial stays closed
    lock_state = None   # None: no hint; False: the padlock over the A button is open (free); True: closed (locked to the grid and the angles)

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.values = {option.name: option.default for option in self.options}
        self._guide_key = None

    @property
    def grid(self):
        """The grid step in document millimetres: the one setting of the Settings panel that every tool shares (the service `grid`)."""
        service = self.ctx.services.get("grid")
        return float(service()) if service is not None else snapping.DEFAULT_GRID

    @property
    def angle(self):
        """The angle step in degrees that a locked turn is rounded to: the one setting of the Settings panel (the service `angle`)."""
        service = self.ctx.services.get("angle")
        return float(service()) if service is not None else snapping.DEFAULT_ANGLE

    @property
    def placement(self):
        """How a point is placed: "snap" (rounded to the grid and lined up with the model), "grid" (rounded to the grid) or "free". The
        setting of the Settings panel that the A button changes while the trigger is held (the service `placement`)."""
        service = self.ctx.services.get("placement")
        return service() if service is not None else "snap"

    def place(self, raw, exclude=()):
        """(point, guides) for a cursor at `raw` by the placement: `raw` itself when free, the grid point when on the grid, the grid
        point lined up with the model when snapping."""
        mode = self.placement
        if mode == "free":
            return tuple(raw), []
        point = snapping.snap_point(raw, self.grid)
        return (point, []) if mode == "grid" else self.align(raw, point, exclude)

    def grid_text(self):
        """The grid step as text, in the measurement system of the document."""
        format_length = self.ctx.services.get("format_length")
        return "Grid " + (format_length(self.grid) if format_length is not None else f"{self.grid:g} mm")

    def align(self, raw, point, exclude=()):
        """(point, guides) for a cursor at `raw` that the grid rounded to `point`: the point lined up with the points of the model (the
        service `guides`, which skips the objects named in `exclude`); the same point and no guides when there is no such service."""
        service = self.ctx.services.get("guides")
        return (point, []) if service is None else service(raw, point, tuple(exclude))

    def show_guides(self, guides, half):
        """Draw the guides of `align` (crosses of `half` millimetres on the anchors); a tick of the hand tells when another guide appears."""
        ghost = self.ctx.services.get("ghost")
        if ghost is None:
            return
        key = tuple((g.kind, g.axis, g.anchor) for g in guides)
        if key != self._guide_key:
            appeared = bool(key) and not self._guide_key        # a change from one guide to another is silent: near many objects it never stops
            self._guide_key = key
            if appeared and self.ctx.haptic is not None:
                self.ctx.haptic(self.ctx.dominant, 0.08, 0.008)
        ghost.show_guides(guides, half)
        feature = self.ctx.services.get("feature")
        if feature is not None:
            feature(guides)                      # the host highlights what drives them (inference)

    def show_grid_points(self, point, dims=3, to_document=None):
        """Faint spheres on the grid points around `point` (the pointer, before it is snapped), smaller the farther they are; none when
        the placement is free. `hide_guides` hides them too, so call this after it. With `dims` 2 the points are those of a
        plane (the first two coordinates) and `to_document` turns a point of that plane into a document point."""
        ghost = self.ctx.services.get("ghost")
        show = getattr(ghost, "show_grid_points", None)
        if show is None:
            return
        if self.placement == "free":
            show([])
            return
        spheres = snapping.grid_anchors(point, self.grid, dims)
        show([(to_document(p) if to_document is not None else p, r) for p, r in spheres])

    def hide_grid_points(self):
        hide = getattr(self.ctx.services.get("ghost"), "hide_grid_points", None)
        if hide is not None:
            hide()

    def hide_guides(self):
        self._guide_key = None
        ghost = self.ctx.services.get("ghost")
        if ghost is not None:
            ghost.hide_guides()
        self.hide_grid_points()
        feature = self.ctx.services.get("feature")
        if feature is not None:
            feature(())

    def disc_slots(self):
        """The six `DiscSlot`s of the option disc, clockwise from the top (the stick up), or None for a tool without a disc."""
        return None

    def disc_hub(self):
        """The lines of text in the middle of the option disc."""
        return []

    def toggle_fixed(self):
        """The B button was pressed while a gesture runs (`busy`): fix what the gesture holds, or release it when it is fixed already.
        Returns the text of a toast, or None when the tool fixes nothing."""
        return None

    def stick_click(self):
        """The stick of the tool hand was clicked; returns a short text for a toast when the tool used the click, else None."""
        return None

    def set_option(self, name, value):
        """Set an option (clamped to what it allows); returns the value that was stored."""
        option = next(o for o in self.options if o.name == name)
        self.values[name] = option.clamp(value)
        return self.values[name]

    def activate(self):
        """Called when the tool becomes the active tool."""

    def deactivate(self):
        """Called when another tool replaces it; discard any uncommitted gesture state here."""

    def update(self, frame):
        """Called once per frame with the current `InputFrame` while the tool is active."""
