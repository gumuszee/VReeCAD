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
"""Radial tool palette logic (docs/design.md): hold `button1` on the palette hand, push the stick towards an item,
release the button to pick it. No Coin or OpenXR imports; `palette_view` draws it."""

import math

DEADZONE = 0.55  # stick magnitude below which no item is highlighted


class RadialPalette:
    def __init__(self, items=(), button="button1"):
        self.items = list(items)   # [(name, label)]
        self.button = button
        self.is_open = False
        self.highlighted = None    # index into items, or None

    def set_items(self, items):
        self.items = list(items)
        self.highlighted = None

    def sector_angle(self, index):
        """Angle of an item centre in radians, 0 = stick up, increasing clockwise."""
        return 2 * math.pi * index / len(self.items)

    def item_at(self, stick):
        """Index of the item the stick points at, or None inside the dead zone."""
        x, y = stick
        if not self.items or math.hypot(x, y) < DEADZONE:
            return None
        angle = math.atan2(x, y) % (2 * math.pi)
        step = 2 * math.pi / len(self.items)
        return int(round(angle / step)) % len(self.items)

    def update(self, hand):
        """Feed the palette hand (`input.HandInput` after `InputTracker.update`). Returns the picked tool name on release, else None."""
        if not self.is_open:
            if self.button in hand.pressed and self.items:
                self.is_open = True
                self.highlighted = None
            return None
        self.highlighted = self.item_at(hand.stick)
        if self.button in hand.released:
            picked = self.items[self.highlighted][0] if self.highlighted is not None else None
            self.is_open = False
            self.highlighted = None
            return picked
        return None
