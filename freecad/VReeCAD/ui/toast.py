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
"""The logic of the small messages the interface shows (docs/ux-design.md, Toasts, tooltips and readouts). No Coin imports.

A toast is a line of text that stays for a couple of seconds; up to `MAX_SHOWN` stand at the same time, newest at the bottom.
Showing the text of a toast that is still there renews it instead of stacking a copy. A tooltip appears when the same button has
been hovered for `TOOLTIP_DELAY` seconds."""

from dataclasses import dataclass
from typing import List, Optional

DURATION = 2.2         # seconds a toast stays
MAX_SHOWN = 3
POP_IN = 0.12          # seconds a toast takes to grow to full size
POP_OUT = 0.2          # and to shrink away at the end
TOOLTIP_DELAY = 0.5    # seconds of hovering one button before its tooltip shows


@dataclass
class Toast:
    text: str
    duration: float = DURATION
    age: float = 0.0

    @property
    def scale(self):
        """Size factor from 0 to 1: grows in and shrinks out."""
        return max(0.0, min(1.0, self.age / POP_IN, (self.duration - self.age) / POP_OUT))


class Toasts:
    def __init__(self):
        self.items: List[Toast] = []

    def show(self, text, duration=DURATION):
        """Show a line of text (empty text is ignored)."""
        if not text:
            return
        for toast in self.items:
            if toast.text == text:
                self.items.remove(toast)
                toast.age, toast.duration = min(toast.age, POP_IN), duration
                self.items.append(toast)
                return
        self.items.append(Toast(text, duration))
        del self.items[:-MAX_SHOWN]

    def update(self, dt):
        """Age the toasts and drop the expired ones; returns the toasts to draw, oldest first."""
        for toast in self.items:
            toast.age += dt
        self.items = [t for t in self.items if t.age < t.duration]
        return self.items


class Dwell:
    """Tells when a hovered target (anything comparable) has been hovered long enough for its tooltip."""

    def __init__(self, delay=TOOLTIP_DELAY):
        self.delay = delay
        self.target = None
        self.time = 0.0

    def update(self, target, dt) -> Optional[object]:
        """The target once it has been hovered for the delay, else None. Any change of target starts the count again."""
        if target != self.target:
            self.target, self.time = target, 0.0
        else:
            self.time += dt
        return self.target if self.target is not None and self.time >= self.delay else None
