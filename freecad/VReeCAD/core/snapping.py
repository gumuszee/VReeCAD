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
"""Snapping to a grid and the box a drag spans. Lengths are document millimetres. No FreeCAD imports.

A drag from a start point to an end point spans an axis-aligned box in document axes. Every axis is at least one grid step long,
so a box never collapses; when the drag does not leave its starting cell it is a tap, and the box is a default size centred on the
starting point."""

import math

GRID_STEPS = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)   # millimetres
ANGLE_STEPS = (5.0, 15.0, 30.0, 45.0, 90.0)              # degrees
DEFAULT_GRID, DEFAULT_ANGLE = 10.0, 15.0
PLACEMENTS = ("snap", "grid", "free")       # where a tool puts a point: on the grid and lined up with the model, on the grid only, anywhere
PLACEMENT_LABELS = {"snap": "Snap", "grid": "Grid", "free": "Free"}
TAP_CELLS = 4                                            # a tap makes a box of this many grid steps on every side


def snap(value, step):
    """The multiple of `step` nearest to `value` (halves go up)."""
    return math.floor(value / step + 0.5) * step


def snap_point(point, step):
    return tuple(snap(c, step) for c in point)


def drag_box(start, end, step):
    """(lowest corner, size) of the box a drag from `start` to `end` spans; both points are on the grid. A drag that stays in
    its cell is a tap: the box is `TAP_CELLS` steps wide and centred on the start."""
    if all(abs(e - s) < step / 2 for s, e in zip(start, end)):
        size = TAP_CELLS * step
        return tuple(s - size / 2 for s in start), (size, size, size)
    lo = tuple(min(s, e) for s, e in zip(start, end))
    size = tuple(max(abs(e - s), step) for s, e in zip(start, end))
    return lo, size


def is_tap(start, end, step):
    return all(abs(e - s) < step / 2 for s, e in zip(start, end))
