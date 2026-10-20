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
the same way. Poses are a position (document millimetres) and an orientation quaternion in document axes. A grab is free; when it
is locked, the position is on the absolute grid (multiples of the grid step from the document origin) and the angles are multiples of
an angle step, so the numbers in the document stay clean.

`classify` decides what the cursor touches: the nearest vertex, edge or face within a reach, or the inside of a solid."""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from freecad.VReeCAD.core import mathutil as mu

ROTATION_STEP = 15.0       # degrees
REACH = {"vertex": 0.012, "edge": 0.02, "face": 0.03}   # metres on the stage: how far from an element the cursor still touches it


def snap_rotation(q, step_degrees=ROTATION_STEP):
    """The rotation `q` as turns about the X, Y and Z axes (applied in that order), each rounded to a multiple of `step_degrees`, so the
    result is aligned to the axes in all three; without a step it is unchanged."""
    if not step_degrees:
        return mu.quat_normalize(q)
    x, y, z, w = mu.quat_normalize(q)
    sine = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(sine)
    if abs(sine) > 1.0 - 1e-9:                          # looking straight up or down: only the sum of the turns about X and Z is defined
        roll, yaw = 0.0, math.atan2(-2.0 * (x * y - w * z), 1.0 - 2.0 * (x * x + z * z))
    else:
        roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
        yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    steps = [round(math.degrees(a) / step_degrees) * step_degrees for a in (roll, pitch, yaw)]
    if not any(steps):
        return mu.IDENTITY_QUAT
    turn = mu.IDENTITY_QUAT
    for axis, degrees in zip(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), steps):
        turn = mu.quat_multiply(mu.quat_from_axis_angle(axis, math.radians(degrees)), turn)
    return mu.quat_normalize(turn)


@dataclass(frozen=True)
class Grab:
    """The poses at the start of a grab: the hand (`hand_position`, `hand_rotation`) and the object (`base`, `rotation`)."""
    hand_position: Tuple[float, float, float]
    hand_rotation: Tuple[float, float, float, float]
    base: Tuple[float, float, float]
    rotation: Tuple[float, float, float, float]

    def at(self, position, rotation, rotate=True, grid=None, step_degrees=None):
        """(base, rotation) of the object when the hand has the pose (`position`, `rotation`). When `grid` and `step_degrees` are given (a
        locked grab) the result is on the absolute grid: the base is a multiple of `grid` on every axis, counted from the origin of the
        document, and the angles of the rotation about X, Y and Z are multiples of `step_degrees`, whatever the object had at the start;
        otherwise both are free. A grab that does not rotate leaves the rotation as it was."""
        turn = mu.IDENTITY_QUAT
        if rotate:
            turn = mu.quat_normalize(mu.quat_multiply(rotation, mu.quat_conjugate(self.hand_rotation)))
            if step_degrees:
                wanted = snap_rotation(mu.quat_multiply(turn, self.rotation), step_degrees)
                turn = mu.quat_multiply(wanted, mu.quat_conjugate(self.rotation))
        move = mu.sub(position, self.hand_position)
        base = mu.add(self.hand_position, mu.add(move, mu.rotate(turn, mu.sub(self.base, self.hand_position))))
        if grid:
            base = tuple(math.floor(c / grid + 0.5) * grid for c in base)
        return base, mu.quat_normalize(mu.quat_multiply(turn, self.rotation))


def within_reach(kind, distance, mm_per_metre) -> bool:
    """Whether an element of `kind` ("vertex", "edge" or "face") at `distance` document millimetres is touched."""
    return distance is not None and distance <= REACH[kind] * mm_per_metre


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
