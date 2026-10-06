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
"""Grabbing an object with the hand, and choosing what the hand touches. No FreeCAD or Coin imports.

A grab attaches the object to the hand as a rigid body: when the hand moves from the pose it had at the start, the object moves
the same way. Poses are a position (document millimetres) and an orientation quaternion in document axes. The hand position is
the cursor, which already lies on the grid, so a translation is a whole number of grid steps; a rotation is rounded to steps of
`ROTATION_STEP` degrees, so the numbers in the document stay clean.

`classify` decides what the cursor touches: the nearest vertex, edge or face within a reach, or the inside of a solid."""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from freecad.BlocksCAD.core import mathutil as mu

ROTATION_STEP = 15.0       # degrees
REACH = {"vertex": 0.012, "edge": 0.02, "face": 0.03}   # metres on the stage: how far from an element the cursor still touches it


def snap_rotation(q, step_degrees=ROTATION_STEP):
    """The rotation `q` with its angle rounded to a multiple of `step_degrees` (its axis is kept)."""
    x, y, z, w = mu.quat_normalize(q)
    if w < 0:
        x, y, z, w = -x, -y, -z, -w
    angle = 2.0 * math.acos(min(1.0, w))
    sine = math.sqrt(max(0.0, 1.0 - w * w))
    if sine < 1e-9 or angle < 1e-9:
        return mu.IDENTITY_QUAT
    snapped = round(math.degrees(angle) / step_degrees) * step_degrees
    if snapped == 0:
        return mu.IDENTITY_QUAT
    return mu.quat_from_axis_angle((x / sine, y / sine, z / sine), math.radians(snapped))


@dataclass(frozen=True)
class Grab:
    """The poses at the start of a grab: the hand (`hand_position`, `hand_rotation`) and the object (`base`, `rotation`)."""
    hand_position: Tuple[float, float, float]
    hand_rotation: Tuple[float, float, float, float]
    base: Tuple[float, float, float]
    rotation: Tuple[float, float, float, float]

    def at(self, position, rotation, rotate=True, step_degrees=ROTATION_STEP):
        """(base, rotation) of the object when the hand has the pose (`position`, `rotation`)."""
        turn = mu.IDENTITY_QUAT
        if rotate:
            turn = snap_rotation(mu.quat_multiply(rotation, mu.quat_conjugate(self.hand_rotation)), step_degrees)
        base = mu.add(position, mu.rotate(turn, mu.sub(self.base, self.hand_position)))
        return base, mu.quat_normalize(mu.quat_multiply(turn, self.rotation))


def classify(d_vertex, d_edge, d_face, inside, mm_per_metre) -> Optional[str]:
    """What the cursor touches: "vertex", "edge" or "face" when it lies within the reach of one (distances in document millimetres,
    `mm_per_metre` the document length of one metre of the stage), otherwise "object" when it is inside a solid, else None."""
    if d_vertex is not None and d_vertex <= REACH["vertex"] * mm_per_metre:
        return "vertex"
    if d_edge is not None and d_edge <= REACH["edge"] * mm_per_metre:
        return "edge"
    if d_face is not None and d_face <= REACH["face"] * mm_per_metre:
        return "face"
    return "object" if inside else None
