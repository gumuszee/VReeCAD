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
"""User settings of the interface, stored as JSON (`%APPDATA%\\VReeCAD\\settings.json`). No Coin, OpenXR or FreeCAD imports.

The pointer settings: the mode ("laser" or "tip"), the tilt of the tip below the controller axis in degrees and the distance of the
tip from the controller in metres (docs/ux-design.md, Pointer), and the ids of the faces used last, which fill the quick radial
(docs/ux-design.md, Quick radial)."""

import json
import os
from dataclasses import asdict, dataclass, field
from typing import List

from freecad.VReeCAD.core import snapping
from freecad.VReeCAD.ui.layout import current_face

MODES = ("laser", "tip")
SUB_MM = ("mm", "um")         # lengths under a millimetre as decimals of mm (0.25 mm) or as micrometres (250 um)
SIDES = ("left", "right")
SNAPPING = ("guides", "inference")   # the alignment guides use every point of the model, or only those near the hand and those it has dwelt on
ANGLE_RANGE = (-90.0, 90.0)
LENGTH_RANGE = (0.0, 0.4)


def _clamp(value, low, high):
    return min(max(value, low), high)


def _nearest(value, choices, default):
    """The member of `choices` nearest to `value`, `default` when it is not a number."""
    try:
        return min(choices, key=lambda c: abs(c - float(value)))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    pointer_mode: str = "laser"
    tip_angle: float = 15.0       # degrees; positive tilts the pointer down from the controller axis
    tip_length: float = 0.04      # metres from the controller to the tip
    recent: List[str] = field(default_factory=list)   # ids of the faces used last, newest first
    onboarded: bool = False       # the controls card has been shown (and gone) once
    tool_hand: str = "right"      # the hand that holds the tool; the palette is on the other
    sub_mm: str = "mm"            # how lengths under a millimetre are written, one of `SUB_MM`
    grid: float = snapping.DEFAULT_GRID      # the grid step of every tool in millimetres, one of `snapping.GRID_STEPS`
    angle: float = snapping.DEFAULT_ANGLE    # the angle step of a locked turn in degrees, one of `snapping.ANGLE_STEPS`
    placement: str = "snap"       # how a tool places a point, one of `snapping.PLACEMENTS`; the A button changes it while the trigger is held
    snap_source: str = "guides"      # which points the guides line up with, one of `SNAPPING`

    def __post_init__(self):
        if self.pointer_mode not in MODES:
            self.pointer_mode = "laser"
        self.tip_angle = _clamp(float(self.tip_angle), *ANGLE_RANGE)
        self.tip_length = _clamp(float(self.tip_length), *LENGTH_RANGE)
        self.recent = [current_face(f) for f in self.recent if isinstance(f, str)] if isinstance(self.recent, list) else []
        self.onboarded = bool(self.onboarded)
        if self.tool_hand not in SIDES:
            self.tool_hand = "right"
        if self.sub_mm not in SUB_MM:
            self.sub_mm = "mm"
        self.grid = _nearest(self.grid, snapping.GRID_STEPS, snapping.DEFAULT_GRID)
        self.angle = _nearest(self.angle, snapping.ANGLE_STEPS, snapping.DEFAULT_ANGLE)
        if self.placement not in snapping.PLACEMENTS:
            self.placement = "snap"
        if self.snap_source not in SNAPPING:
            self.snap_source = "guides"

    def cycle_placement(self):
        """The next placement (snap, grid, free, snap ...); returns it."""
        order = snapping.PLACEMENTS
        self.placement = order[(order.index(self.placement) + 1) % len(order)]
        return self.placement

    def toggle_snapping(self):
        self.snap_source = "inference" if self.snap_source == "guides" else "guides"

    def toggle_mode(self):
        self.pointer_mode = "tip" if self.pointer_mode == "laser" else "laser"

    def to_json(self):
        return json.dumps(asdict(self), indent=1)

    @classmethod
    def from_json(cls, text):
        data = json.loads(text)
        known = {k: data[k] for k in ("pointer_mode", "tip_angle", "tip_length", "recent", "onboarded", "tool_hand", "sub_mm", "grid", "angle", "placement", "snap_source") if k in data}
        return cls(**known)


def user_settings_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "VReeCAD", "settings.json")


def load_settings(path=None):
    """The saved settings, or the defaults when there is no usable file."""
    try:
        with open(path or user_settings_path(), encoding="utf-8") as f:
            return Settings.from_json(f.read())
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings, path=None):
    path = path or user_settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(settings.to_json())
    return path
