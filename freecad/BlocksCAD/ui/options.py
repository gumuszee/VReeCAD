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
"""The stick of the tool hand adjusts the options of the active tool (docs/ux-design.md, Tool hand). No Coin imports.

The stick up and down changes the first option of the tool, left and right the second. A number option steps while the stick is
held out (after a short delay, repeating), a choice option steps once per flick. A press of the stick (the click) puts the
option changed last (the first when none was changed) back to its default. Every step gives a haptic tick and a readout text that
stays for `READOUT_TIME` seconds. A tool without options leaves the stick alone (`owns_stick` is False)."""

from dataclasses import dataclass, field
from typing import List, Optional

from freecad.BlocksCAD.core import units

PUSH_ON, PUSH_OFF = 0.65, 0.3
FIRST_REPEAT = 0.3      # seconds the stick is held out before a number option repeats
REPEAT = 0.1            # seconds between repeated steps
READOUT_TIME = 1.5      # seconds the readout stays after the last change


@dataclass
class OptionState:
    owns_stick: bool = False                     # the active tool has options: the stick belongs to them
    readout: Optional[str] = None                # text to show next to the tool hand
    changed: Optional[str] = None                # name of the option changed this frame
    haptics: List[tuple] = field(default_factory=list)   # (hand, amplitude, duration_s)


class OptionControl:
    def __init__(self, hand=1):
        self.hand = hand
        self._dir = [0, 0]          # direction the stick is pushed on each axis (up/down, left/right)
        self._repeat = [0.0, 0.0]   # seconds until the next repeated step
        self._last = 0              # index of the option changed last
        self._readout = None
        self._readout_time = 0.0

    def _set(self, tool, index, value, state, system):
        option = tool.options[index]
        changed = value != tool.values[option.name]
        tool.values[option.name] = value
        self._last = index
        if changed:
            state.changed = option.name
            state.haptics.append((self.hand, 0.12, 0.012))
        self._readout, self._readout_time = f"{option.label}: {option.format(value, system)}", 0.0

    def _step(self, tool, index, direction, state, system):
        option = tool.options[index]
        value = tool.values[option.name]
        if option.kind == "choice":
            new = option.choices[(option.choices.index(value) + direction) % len(option.choices)]
        else:
            new = option.clamp(value + direction * option.step)
        self._set(tool, index, new, state, system)

    def update(self, frame, tool, blocked=False, system=units.METRIC_MM) -> OptionState:
        """One frame for the active `tool` (or None); `system` formats lengths."""
        state = OptionState()
        options = getattr(tool, "options", ()) if tool is not None else ()
        if not options:
            self._dir, self._readout = [0, 0], None
            return state
        state.owns_stick = True
        hand = frame.hands[self.hand]
        blocked = blocked or any(h.down("grip") for h in frame.hands)
        pushes = (hand.stick[1], hand.stick[0])
        for axis in range(min(2, len(options))):
            push = 0.0 if blocked else pushes[axis]
            if abs(push) <= PUSH_OFF:
                direction = 0
            elif abs(push) >= PUSH_ON:
                direction = 1 if push > 0 else -1
            else:
                direction = self._dir[axis]       # between the thresholds the push stays as it was
            if direction != self._dir[axis]:
                self._dir[axis] = direction
                if direction:                      # a new push steps at once
                    self._repeat[axis] = FIRST_REPEAT
                    self._step(tool, axis, direction, state, system)
            elif direction and options[axis].kind != "choice":   # held out: repeat
                self._repeat[axis] -= frame.dt
                if self._repeat[axis] <= 0.0:
                    self._repeat[axis] += REPEAT
                    self._step(tool, axis, direction, state, system)
        if "stick_click" in hand.pressed and not blocked:
            index = min(self._last, len(options) - 1)
            self._set(tool, index, options[index].default, state, system)
        self._readout_time += frame.dt
        if self._readout is not None and self._readout_time < READOUT_TIME:
            state.readout = self._readout
        return state
