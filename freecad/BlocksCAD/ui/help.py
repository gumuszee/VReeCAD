# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                         *
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
"""The controls card (docs/ux-design.md, Controls card): what the buttons of each controller do just now. No Coin imports.

One card hangs over each controller: the tool hand's lists the controls of the active tool (what the tool declares in
`Tool.controls`, then the ones every tool has), the palette hand's the controls of the palette. `HelpState` is whether the cards
show: the Controls face toggles them, they go by themselves after `SHOW_SECONDS`, and the first time the addon runs they show once
(the host asks for it, and the setting `onboarded` remembers that it has been seen)."""

SHOW_SECONDS = 40.0

TOOL_HAND_DEFAULT = (("A", "hold: quick menu"),)
TOOL_HAND_COMMON = (
    ("Stick", "options of the tool"),
    ("B", "tap: undo, hold: redo"),
    ("Grip", "grab the world (both: turn, scale)"),
)
PALETTE_HAND = (
    ("Stick", "turn the palette"),
    ("Trigger", "press a face with the tip"),
    ("Grip", "grab the world (both: turn, scale)"),
    ("A", "pin the palette"),
    ("D-pad", "left: undo, right: redo"),
)


def tool_card(label, controls):
    """(title, lines) of the card of the tool hand for the tool called `label` that declares `controls` ((control, text) pairs)."""
    declared = list(controls)
    names = {name for name, _ in declared}
    lines = declared + [entry for entry in TOOL_HAND_DEFAULT if entry[0] not in names] + list(TOOL_HAND_COMMON)
    return f"{label}: tool hand", [f"{name}: {text}" for name, text in lines]


def palette_card():
    """(title, lines) of the card of the palette hand."""
    return "Palette hand", [f"{name}: {text}" for name, text in PALETTE_HAND]


class HelpState:
    """Whether the cards show. `update(dt)` ends them after `SHOW_SECONDS` and says so (True) when it did."""

    def __init__(self):
        self.visible = False
        self.age = 0.0

    def show(self):
        self.visible, self.age = True, 0.0

    def hide(self):
        self.visible = False

    def toggle(self):
        """Show or hide; returns whether the cards show now."""
        if self.visible:
            self.hide()
        else:
            self.show()
        return self.visible

    def update(self, dt):
        if not self.visible:
            return False
        self.age += dt
        if self.age >= SHOW_SECONDS:
            self.hide()
            return True
        return False
