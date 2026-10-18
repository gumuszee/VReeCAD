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
"""Undo and redo on `button2` of the tool hand (docs/ux-design.md, Tool hand). No Coin, OpenXR or FreeCAD imports.

A tap (released within `HOLD` seconds) undoes; holding the button for `HOLD` seconds redoes once, while the button is still down.
Outside navigation only: a press while a grip holds the world is the 1 : 1 lock, and a grip pressed while the button is down
cancels it."""

from dataclasses import dataclass, field
from typing import List, Optional

HOLD = 0.4   # seconds


@dataclass
class UndoState:
    action: Optional[str] = None                        # "undo" or "redo" when to run it this frame
    haptics: List[tuple] = field(default_factory=list)  # (hand, amplitude, duration_s)


class UndoButton:
    def __init__(self, hand=1):
        self.hand = hand
        self._armed = False
        self._fired = False
        self._age = 0.0

    def update(self, frame, blocked=False) -> UndoState:
        state = UndoState()
        hand = frame.hands[self.hand]
        blocked = blocked or any(h.down("grip") for h in frame.hands)
        if blocked:
            self._armed = False
        elif "button2" in hand.pressed:
            self._armed, self._fired, self._age = True, False, 0.0
        if not self._armed:
            return state
        self._age += frame.dt
        if not hand.down("button2"):
            self._armed = False
            if not self._fired:
                state.action = "undo"
        elif not self._fired and self._age >= HOLD:
            self._fired = True
            state.action = "redo"
        if state.action is not None:
            state.haptics.append((self.hand, 0.4, 0.03))
        return state
