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
hands, the scale follows the ratio of the hand distance, the rotation follows the line between the hands. The rotation is a free
orbit (the shortest rotation that turns the old hand line into the new one); while the modifier button (button1 of the tool hand) is
held it is limited to the vertical axis, so the bottom of the model stays down. Button2 of the tool hand snaps the scale to 1 : 1
about the hands. Gestures are computed from the pose at grab time and the hand positions at that moment, so no error accumulates;
a change of the gripping hands or of the rotation mode starts a new gesture. The stick click of a gripping hand resets the view
with a short animation to the home pose: the origin in front of the head.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple

from freecad.BlocksCAD.core import mathutil as mu

UP = (0.0, 1.0, 0.0)
HOME_DISTANCE = 1.0       # metres from the head to the origin, horizontally
HOME_HEIGHT = 0.75        # origin height as a fraction of the head height above the floor (chest height when standing)


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


def home_pose(head):
    """The pose that puts the origin `HOME_DISTANCE` in front of the head at chest height, scale 1 : 1, turned so that the front
    view (looking along the document Y axis) points away from the head. `head` is an `input.Pose`; an untracked head gives IDENTITY."""
    if not head.tracked:
        return IDENTITY
    forward = mu.rotate(head.orientation, (0.0, 0.0, -1.0))
    flat = (forward[0], 0.0, forward[2])
    if mu.length(flat) < 0.2:     # looking straight up or down: the top of the head points forward
        top = mu.rotate(head.orientation, (0.0, 1.0, 0.0))
        flat = (top[0], 0.0, top[2]) if forward[1] < 0 else (-top[0], 0.0, -top[2])
    if mu.length(flat) < 1e-6:
        flat = (0.0, 0.0, -1.0)
    flat = mu.normalize(flat)
    position = (head.position[0] + flat[0] * HOME_DISTANCE, head.position[1] * HOME_HEIGHT,
                head.position[2] + flat[2] * HOME_DISTANCE)
    yaw = math.atan2(-flat[0], -flat[2])
    return WorldPose(position, mu.quat_from_axis_angle(UP, yaw), 1.0)


def one_point(world0, hand0, hand1):
    """The world follows one hand: translation by the hand movement."""
    return WorldPose(mu.add(world0.position, mu.sub(hand1, hand0)), world0.rotation, world0.scale)


def two_point(world0, left0, right0, left1, right1, up=UP, constrain_up=False, min_scale=0.01, max_scale=100.0):
    """Pose after the hands moved from (left0, right0) to (left1, right1) while both gripped the world with pose `world0`.
    `constrain_up` limits the rotation to the vertical axis; otherwise it is the shortest rotation between the hand lines."""
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


def scale_about(world, pivot, ratio):
    """The pose scaled by `ratio` about the stage point `pivot` (the world point under the pivot stays under it)."""
    return WorldPose(mu.add(pivot, mu.mul(mu.sub(world.position, pivot), ratio)), world.rotation, world.scale * ratio)


def blend(a, b, t):
    """Pose between a and b (scale interpolated geometrically)."""
    return WorldPose(mu.lerp(a.position, b.position, t), mu.quat_slerp(a.rotation, b.rotation, t),
                     math.exp(math.log(a.scale) + (math.log(b.scale) - math.log(a.scale)) * t))


def format_scale(scale):
    """Readout such as "4 : 1" (world enlarged) or "1 : 4" (world shrunk)."""
    def fmt(v):
        return f"{v:.0f}" if v >= 10 or abs(v - round(v)) < 0.05 else f"{v:.1f}"
    return f"{fmt(scale)} : 1" if scale >= 1.0 else f"1 : {fmt(1.0 / scale)}"


def _smooth(t):
    return t * t * (3 - 2 * t)


class Navigator:
    RESET_TIME = 0.35  # seconds
    SNAP_TIME = 0.2

    def __init__(self, world=IDENTITY, min_scale=0.01, max_scale=100.0, modifier_hand=1):
        self.world = world
        self.min_scale, self.max_scale = min_scale, max_scale
        self.modifier_hand = modifier_hand   # the hand whose button1 levels the rotation and whose button2 snaps the scale
        self.gripping = (False, False)
        self.state = "idle"        # "idle", "one" or "two"
        self.level = False         # the rotation is limited to the vertical axis (modifier held)
        self._anchor = None        # (world, hand positions at the start of the gesture)
        self._reset_from = None
        self._reset_to = IDENTITY
        self._reset_t = 0.0
        self._reset_requested = False
        self._snap_t = None        # progress of the 1 : 1 snap, None when not snapping
        self._wait_release = False
        self._octave = None

    @staticmethod
    def hand_position(hand):
        pose = hand.grip_pose if hand.grip_pose.tracked else hand.aim
        return pose.position

    @property
    def resetting(self):
        return self._reset_from is not None

    @property
    def navigating(self):
        return self.state != "idle" or self.resetting

    def request_reset(self):
        """Animate the view back to the home pose at scale 1 : 1 (the stick click of a gripping hand does the same).
        The animation starts with the next `update`, which knows where the head is."""
        self._reset_requested = True

    def _begin_reset(self, head):
        target = home_pose(head)
        self._reset_requested = False
        if (mu.length(mu.sub(self.world.position, target.position)) < 1e-3 and abs(self.world.scale - 1.0) < 1e-4
                and mu.length(mu.sub(mu.rotate(self.world.rotation, UP), mu.rotate(target.rotation, UP))) < 1e-4
                and mu.length(mu.sub(mu.rotate(self.world.rotation, (1.0, 0.0, 0.0)),
                                     mu.rotate(target.rotation, (1.0, 0.0, 0.0)))) < 1e-4):
            return False
        self._reset_from, self._reset_to, self._reset_t = self.world, target, 0.0
        self.state, self._anchor, self._snap_t = "idle", None, None
        return True

    def update(self, frame, blocked=(False, False)) -> List[tuple]:
        """Advance with one `InputFrame`. `blocked[i]` excludes hand i (for example while it grabs an object).
        Returns events: ("grab", n_hands), ("release",), ("tick", hand_indexes), ("reset",), ("snap",) and ("level", bool)."""
        events = []
        hands = frame.hands
        gripping = tuple(bool(hands[i].down("grip") and hands[i].aim.tracked and not blocked[i]) for i in range(2))
        modifier = hands[self.modifier_hand]

        if self._reset_requested and not self.resetting:
            if self._begin_reset(frame.head):
                events.append(("reset",))
            self._reset_requested = False

        if self.resetting:
            self._reset_t += frame.dt
            t = min(1.0, self._reset_t / self.RESET_TIME)
            self.world = self._reset_to if t >= 1.0 else blend(self._reset_from, self._reset_to, _smooth(t))
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
            if self._begin_reset(frame.head):
                events.append(("reset",))
                self.gripping = gripping
                return events

        if gripping != self.gripping:
            count = sum(gripping)
            self.state = {0: "idle", 1: "one", 2: "two"}[count]
            self._snap_t = None
            if count:
                self._anchor = (self.world, tuple(self.hand_position(hands[i]) for i in range(2)))
                events.append(("grab", count))
            else:
                self._anchor = None
                events.append(("release",))
            self.gripping = gripping

        level = modifier.down("button1")
        if level != self.level:
            self.level = level
            if self.state == "two":
                # a new rotation mode starts a new gesture from the current pose, so nothing jumps
                self._anchor = (self.world, tuple(self.hand_position(hands[i]) for i in range(2)))
                events.append(("level", level))

        if self._anchor is not None:
            if "button2" in modifier.pressed and self._snap_t is None and abs(math.log(self.world.scale)) > 1e-3:
                self._snap_t = 0.0
                events.append(("snap",))
            world0, (left0, right0) = self._anchor
            left1, right1 = (self.hand_position(hands[0]), self.hand_position(hands[1]))
            if self.state == "one":
                i = 0 if gripping[0] else 1
                a0, a1 = (left0, left1) if i == 0 else (right0, right1)
                world = one_point(world0, a0, a1)
                pivot = a1
            else:
                world = two_point(world0, left0, right0, left1, right1, constrain_up=self.level,
                                  min_scale=self.min_scale, max_scale=self.max_scale)
                pivot = mu.lerp(left1, right1, 0.5)
            if self._snap_t is not None:
                self._snap_t = min(1.0, self._snap_t + frame.dt / self.SNAP_TIME)
                eased = _smooth(self._snap_t)
                target = math.exp(math.log(world.scale) * (1.0 - eased))
                world = scale_about(world, pivot, target / world.scale)
                if self._snap_t >= 1.0:
                    self._snap_t = None
                    world = scale_about(world, pivot, 1.0 / world.scale)
                    self._anchor = (world, (left1, right1))
            self.world = world
            octave = math.floor(math.log2(self.world.scale) + 1e-9)
            if self._octave is not None and octave != self._octave and self._snap_t is None:
                events.append(("tick", tuple(i for i in range(2) if gripping[i])))
            self._octave = octave
        else:
            self._octave = math.floor(math.log2(self.world.scale) + 1e-9)
        return events
