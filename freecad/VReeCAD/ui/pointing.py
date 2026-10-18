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
"""Where a controller points (docs/ux-design.md, Pointer). No Coin, OpenXR or FreeCAD imports.

Every controller has a pointer pose derived from its aim pose and the pointer settings. In laser mode the pointer starts at the
controller and its direction is the aim direction tilted down by the tip angle; the interface casts a ray along it. In tip mode the
pointer is a point at the tip length in front of the controller along that tilted direction, like the brush tip of Open Brush; the
interface reacts to what the tip touches."""

import math
from dataclasses import dataclass
from typing import Tuple

from freecad.VReeCAD.core import mathutil as mu

FORWARD = (0.0, 0.0, -1.0)


@dataclass(frozen=True)
class PointerPose:
    position: Tuple[float, float, float]            # the ray origin (laser) or the tip (tip)
    direction: Tuple[float, float, float]           # unit vector the pointer looks along
    orientation: Tuple[float, float, float, float]  # aim orientation turned down by the tip angle (its -Z is `direction`)
    tip: bool                                       # tip mode: `position` is a point, not a ray origin
    tracked: bool = True


def pointer_pose(aim, mode="laser", angle=0.0, length=0.0) -> PointerPose:
    """The pointer pose of a controller whose aim pose is `aim` (an `input.Pose`); `angle` in degrees, `length` in metres."""
    tilt = mu.quat_from_axis_angle((1.0, 0.0, 0.0), -math.radians(angle))
    orientation = mu.quat_normalize(mu.quat_multiply(aim.orientation, tilt))
    direction = mu.rotate(orientation, FORWARD)
    if mode == "tip":
        return PointerPose(mu.add(aim.position, mu.mul(direction, length)), direction, orientation, True, aim.tracked)
    return PointerPose(aim.position, direction, orientation, False, aim.tracked)
