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

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

from freecad.BlocksCAD.core import units


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
    hint = ""        # one line shown as a toast when the tool is chosen and as the tooltip of its face
    options = ()     # `ToolOption`s: with `disc_slots` the disc chooses among them, else the first is on the stick up and down, the second left and right
    busy = False     # a gesture is running: the quick radial stays closed
    lock_state = None   # None: no hint; False: the padlock over the A button is open (free); True: closed (locked to the grid and the angles)

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.values = {option.name: option.default for option in self.options}
        self._guide_key = None

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
            self._guide_key = key
            if key and self.ctx.haptic is not None:
                self.ctx.haptic(self.ctx.dominant, 0.12, 0.01)
        ghost.show_guides(guides, half)

    def hide_guides(self):
        self._guide_key = None
        ghost = self.ctx.services.get("ghost")
        if ghost is not None:
            ghost.hide_guides()

    def disc_slots(self):
        """The six `DiscSlot`s of the option disc, clockwise from the top (the stick up), or None for a tool without a disc."""
        return None

    def disc_hub(self):
        """The lines of text in the middle of the option disc."""
        return []

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
