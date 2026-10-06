# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""Hardware-independent input model.

Tools see only an `InputFrame`: the head pose and, per hand, a pose plus the five abstract inputs
(`trigger`, `grip`, `stick` xy + click, `button1`, `button2`) with edge events. Backends (OpenXR, Sim)
fill the raw values; `InputTracker.update` derives the edges, so tools never touch OpenXR.

Poses are in metres in the stage (tracking) frame, Y up, orientation as a quaternion (x, y, z, w).
This module has no FreeCAD, Coin or OpenXR imports.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple

PRESS_THRESHOLD = 0.7    # analog value at or above which a press starts
RELEASE_THRESHOLD = 0.3  # analog value below which a press ends (hysteresis)

LEFT, RIGHT = 0, 1
HAND_NAMES = ("left", "right")

ANALOG_INPUTS = ("trigger", "grip")
DIGITAL_INPUTS = ("stick_click", "button1", "button2", "menu")
PRESS_INPUTS = ANALOG_INPUTS + DIGITAL_INPUTS


@dataclass
class Pose:
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    tracked: bool = False


@dataclass
class HandInput:
    """Raw values of one hand; edge sets are filled by `InputTracker`."""
    aim: Pose = field(default_factory=Pose)    # tool direction (-Z points forward)
    grip_pose: Pose = field(default_factory=Pose)
    trigger: float = 0.0
    grip: float = 0.0
    stick: Tuple[float, float] = (0.0, 0.0)
    stick_click: bool = False
    button1: bool = False
    button2: bool = False
    menu: bool = False
    pressed: frozenset = frozenset()   # inputs that went down in this frame
    released: frozenset = frozenset()  # inputs that went up in this frame
    held: frozenset = frozenset()      # inputs that are down after this frame (analog ones with hysteresis)

    def down(self, name: str) -> bool:
        """Whether an input is held; valid for frames that went through `InputTracker.update`."""
        return name in self.held


@dataclass
class InputFrame:
    time: float = 0.0   # seconds
    dt: float = 0.0     # seconds since the previous frame
    head: Pose = field(default_factory=Pose)
    hands: Tuple[HandInput, HandInput] = field(default_factory=lambda: (HandInput(), HandInput()))
    profile: Optional[str] = None   # active interaction profile (None when unknown)

    @property
    def left(self) -> HandInput:
        return self.hands[LEFT]

    @property
    def right(self) -> HandInput:
        return self.hands[RIGHT]


class InputTracker:
    """Derives press/release edges (with hysteresis on analog inputs) between consecutive frames."""

    def __init__(self):
        self._held = [set(), set()]
        self._time = None

    def update(self, frame: InputFrame) -> InputFrame:
        frame.dt = 0.0 if self._time is None else max(0.0, frame.time - self._time)
        self._time = frame.time
        for hand_index, hand in enumerate(frame.hands):
            held = self._held[hand_index]
            pressed, released = set(), set()
            for name in PRESS_INPUTS:
                value = getattr(hand, name)
                if name in ANALOG_INPUTS:
                    if name not in held and value >= PRESS_THRESHOLD:
                        pressed.add(name)
                    elif name in held and value < RELEASE_THRESHOLD:
                        released.add(name)
                else:
                    if bool(value) and name not in held:
                        pressed.add(name)
                    elif not value and name in held:
                        released.add(name)
            held |= pressed
            held -= released
            hand.pressed = frozenset(pressed)
            hand.released = frozenset(released)
            hand.held = frozenset(held)
        return frame

    def reset(self):
        self._held = [set(), set()]
        self._time = None
