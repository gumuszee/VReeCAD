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
"""User settings of the interface, stored as JSON (`%APPDATA%\\BlocksCAD\\settings.json`). No Coin, OpenXR or FreeCAD imports.

The pointer settings: the mode ("laser" or "tip"), the tilt of the tip below the controller axis in degrees and the distance of the
tip from the controller in metres (docs/ux-design.md, Pointer), and the ids of the faces used last, which fill the quick radial
(docs/ux-design.md, Quick radial)."""

import json
import os
from dataclasses import asdict, dataclass, field
from typing import List

from freecad.BlocksCAD.ui.layout import current_face

MODES = ("laser", "tip")
ANGLE_RANGE = (-90.0, 90.0)
LENGTH_RANGE = (0.0, 0.4)


def _clamp(value, low, high):
    return min(max(value, low), high)


@dataclass
class Settings:
    pointer_mode: str = "laser"
    tip_angle: float = 15.0       # degrees; positive tilts the pointer down from the controller axis
    tip_length: float = 0.04      # metres from the controller to the tip
    recent: List[str] = field(default_factory=list)   # ids of the faces used last, newest first

    def __post_init__(self):
        if self.pointer_mode not in MODES:
            self.pointer_mode = "laser"
        self.tip_angle = _clamp(float(self.tip_angle), *ANGLE_RANGE)
        self.tip_length = _clamp(float(self.tip_length), *LENGTH_RANGE)
        self.recent = [current_face(f) for f in self.recent if isinstance(f, str)] if isinstance(self.recent, list) else []

    def toggle_mode(self):
        self.pointer_mode = "tip" if self.pointer_mode == "laser" else "laser"

    def to_json(self):
        return json.dumps(asdict(self), indent=1)

    @classmethod
    def from_json(cls, text):
        data = json.loads(text)
        known = {k: data[k] for k in ("pointer_mode", "tip_angle", "tip_length", "recent") if k in data}
        return cls(**known)


def user_settings_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "BlocksCAD", "settings.json")


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
