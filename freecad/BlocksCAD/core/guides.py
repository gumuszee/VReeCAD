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
"""Alignment guides: where a point being placed lines up with the points of the model (docs/ux-design.md, Guides). Lengths are
document millimetres. No FreeCAD imports.

An anchor is a point of the model that a new point can line up with (a vertex, the middle of a straight edge). `align` takes the
cursor before and after the grid, and the anchors: on every axis on which an anchor has nearly the same coordinate as the cursor the
point takes that coordinate (a guide runs from the anchor to the point), and when one anchor matches on all three axes the point is
that anchor (a point guide)."""

from dataclasses import dataclass
from typing import List, Optional, Tuple

AXIS_NAMES = "XYZ"


@dataclass(frozen=True)
class Guide:
    kind: str                         # "axis" (the point has the coordinate of the anchor on `axis`) or "point" (the point is the anchor)
    axis: int                         # 0, 1 or 2 for an axis guide, -1 for a point guide
    anchor: Tuple[float, float, float]
    point: Tuple[float, float, float]

    @property
    def text(self):
        return "On the point" if self.kind == "point" else f"Aligned {AXIS_NAMES[self.axis]}"


def _distance_squared(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def align(raw, grid_point, anchors, tolerance):
    """(point, guides) for a cursor at `raw` that the grid rounds to `grid_point`: see the module text. `tolerance` is how far in
    millimetres a coordinate may be from the one of an anchor to line up with it."""
    nearest: List[Optional[tuple]] = []
    for axis in range(3):
        best, best_distance = None, None
        for anchor in anchors:
            if abs(anchor[axis] - raw[axis]) < tolerance:
                distance = _distance_squared(anchor, raw)
                if best is None or distance < best_distance:
                    best, best_distance = anchor, distance
        nearest.append(best)
    if nearest[0] is not None and nearest[0] == nearest[1] == nearest[2]:
        return tuple(nearest[0]), [Guide("point", -1, tuple(nearest[0]), tuple(nearest[0]))]
    point = tuple(nearest[axis][axis] if nearest[axis] is not None else grid_point[axis] for axis in range(3))
    guides = [Guide("axis", axis, tuple(nearest[axis]), point) for axis in range(3) if nearest[axis] is not None]
    return point, guides
