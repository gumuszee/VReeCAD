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
"""World navigation with the grips (docs/ux-design.md, Navigation).

The world pose maps world coordinates to stage coordinates: stage = position + rotation * (scale * world).
One grip on empty space drags the world with the hand. Both grips transform it with two points: the pivot is the midpoint of the
hands, the scale follows the ratio of the hand distance, the rotation follows the line between the hands (about the vertical axis
when `constrain_up`). Gestures are computed from the pose at grab time and the hand positions at that moment, so no error accumulates;
a change of the gripping hands starts a new gesture. The stick click of a gripping hand resets the view with a short animation.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple

from freecad.BlocksCAD.core import mathutil as mu

UP = (0.0, 1.0, 0.0)


@dataclass(frozen=True)
class WorldPose:
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float, float] = mu.IDENTITY_QUAT
    scale: float = 1.0

    def to_stage(self, point):
        return mu.add(self.position, mu.rotate(self.rotation, mu.mul(point, self.scale)))

    def to_world(self, point):
        local = mu.rotate(mu.quat_conjugate(self.rotation), mu.sub(point, self.position))
        return mu.mul(local, 1.0 / self.scale)


IDENTITY = WorldPose()


def one_point(world0, hand0, hand1):
    """The world follows one hand: translation by the hand movement."""
    return WorldPose(mu.add(world0.position, mu.sub(hand1, hand0)), world0.rotation, world0.scale)


def two_point(world0, left0, right0, left1, right1, up=UP, constrain_up=True, min_scale=0.01, max_scale=100.0):
    """Pose after the hands moved from (left0, right0) to (left1, right1) while both gripped the world with pose `world0`."""
    pivot0 = mu.lerp(left0, right0, 0.5)
    pivot1 = mu.lerp(left1, right1, 0.5)
    v0, v1 = mu.sub(right0, left0), mu.sub(right1, left1)
    d0, d1 = mu.length(v0), mu.length(v1)
    ratio = 1.0 if d0 < 1e-6 else d1 / d0
    scale = min(max(world0.scale * ratio, min_scale), max_scale)
    ratio = scale / world0.scale
    if d0 < 1e-6 or d1 < 1e-6:
        delta = mu.IDENTITY_QUAT
    elif constrain_up:
        delta = mu.quat_from_axis_angle(up, mu.yaw_between(v0, v1, up))
    else:
        delta = mu.quat_between(v0, v1)
    # p_stage = pivot1 + delta * ratio * (p_stage0 - pivot0)
    position = mu.add(pivot1, mu.rotate(delta, mu.mul(mu.sub(world0.position, pivot0), ratio)))
    return WorldPose(position, mu.quat_normalize(mu.quat_multiply(delta, world0.rotation)), scale)


def blend(a, b, t):
    """Pose between a and b (scale interpolated geometrically)."""
    return WorldPose(mu.lerp(a.position, b.position, t), mu.quat_slerp(a.rotation, b.rotation, t),
                     math.exp(math.log(a.scale) + (math.log(b.scale) - math.log(a.scale)) * t))


def format_scale(scale):
    """Readout such as "4 : 1" (world enlarged) or "1 : 4" (world shrunk)."""
    def fmt(v):
        return f"{v:.0f}" if v >= 10 or abs(v - round(v)) < 0.05 else f"{v:.1f}"
    return f"{fmt(scale)} : 1" if scale >= 1.0 else f"1 : {fmt(1.0 / scale)}"


class Navigator:
    RESET_TIME = 0.35  # seconds

    def __init__(self, world=IDENTITY, min_scale=0.01, max_scale=100.0, constrain_up=True):
        self.world = world
        self.min_scale, self.max_scale, self.constrain_up = min_scale, max_scale, constrain_up
        self.gripping = (False, False)
        self.state = "idle"        # "idle", "one" or "two"
        self._anchor = None        # (world, hand positions at the start of the gesture)
        self._reset_from = None
        self._reset_t = 0.0
        self._wait_release = False
        self._octave = None

    @staticmethod
    def hand_position(hand):
        pose = hand.grip_pose if hand.grip_pose.tracked else hand.aim
        return pose.position

    @property
    def resetting(self):
        return self._reset_from is not None

    def update(self, frame, blocked=(False, False)) -> List[tuple]:
        """Advance with one `InputFrame`. `blocked[i]` excludes hand i (for example while it grabs an object).
        Returns events: ("grab", n_hands), ("release",), ("tick", hand_indexes) and ("reset",)."""
        events = []
        hands = frame.hands
        gripping = tuple(bool(hands[i].down("grip") and hands[i].aim.tracked and not blocked[i]) for i in range(2))

        if self.resetting:
            self._reset_t += frame.dt
            t = min(1.0, self._reset_t / self.RESET_TIME)
            eased = t * t * (3 - 2 * t)
            self.world = blend(self._reset_from, IDENTITY, eased)
            if t >= 1.0:
                self._reset_from = None
                self._wait_release = any(gripping)
                self.state, self._anchor = "idle", None
            self.gripping = gripping
            return events

        if self._wait_release:
            if not any(gripping):
                self._wait_release = False
            self.gripping = gripping
            return events
        if any(gripping) and any(hands[i].down("grip") and "stick_click" in hands[i].pressed for i in range(2) if gripping[i]):
            if self.world != IDENTITY:
                self._reset_from, self._reset_t = self.world, 0.0
                events.append(("reset",))
                self.gripping = gripping
                return events

        if gripping != self.gripping:
            count = sum(gripping)
            self.state = {0: "idle", 1: "one", 2: "two"}[count]
            if count:
                self._anchor = (self.world, tuple(self.hand_position(hands[i]) for i in range(2)))
                events.append(("grab", count))
            else:
                self._anchor = None
                events.append(("release",))
            self.gripping = gripping

        if self._anchor is not None:
            world0, (left0, right0) = self._anchor
            left1, right1 = (self.hand_position(hands[0]), self.hand_position(hands[1]))
            if self.state == "one":
                i = 0 if gripping[0] else 1
                a0, a1 = (left0, left1) if i == 0 else (right0, right1)
                self.world = one_point(world0, a0, a1)
            else:
                self.world = two_point(world0, left0, right0, left1, right1, constrain_up=self.constrain_up,
                                       min_scale=self.min_scale, max_scale=self.max_scale)
            octave = math.floor(math.log2(self.world.scale) + 1e-9)
            if self._octave is not None and octave != self._octave:
                events.append(("tick", tuple(i for i in range(2) if gripping[i])))
            self._octave = octave
        else:
            self._octave = math.floor(math.log2(self.world.scale) + 1e-9)
        return events
