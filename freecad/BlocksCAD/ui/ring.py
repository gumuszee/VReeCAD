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
"""Behaviour and geometry of the palette ring (docs/ux-design.md, Palette ring). No Coin, OpenXR or FreeCAD imports.

Pages stand on a ring around the palette hand's controller; the front page faces the user. The stick of the palette hand turns the
ring one page per flick, the ring fades in while the head looks at the controller (or when pinned) and out otherwise, the tool hand's
ray hovers faces and its trigger activates them. `update` returns what the host needs: hover, activation, haptics, ray end point."""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui.layout import COLS, ROWS

UP = (0.0, 1.0, 0.0)
CELL = 0.05            # metres, face edge
GAP = 0.008
GRID_W = COLS * CELL + (COLS - 1) * GAP
GRID_H = ROWS * CELL + (ROWS - 1) * GAP
RADIUS = 0.16          # distance of the page planes from the ring axis
LIFT = 0.13            # height of the page centres above the controller
GAZE_COS = math.cos(math.radians(35.0))
GAZE_RANGE = (0.12, 0.95)
FLICK_ON, FLICK_OFF = 0.65, 0.3
FADE_RATE = 8.0        # per second
TURN_RATE = 14.0       # exponential approach rate of the ring angle
FRONT_COS = 0.5        # pages within 60 degrees of the front are interactive


@dataclass
class RingResult:
    visible: bool = False
    hover: Optional[Tuple[int, int]] = None      # (page index, slot) under the ray
    activated: Optional[Tuple[int, int]] = None  # (page index, slot) activated this frame
    ray_end: Optional[Tuple[float, float, float]] = None
    haptics: List[tuple] = field(default_factory=list)   # (hand, amplitude, duration_s)
    consume_trigger: bool = False                # the tool hand's trigger belongs to the ring this frame


class PaletteRing:
    def __init__(self, page_count, palette_hand=0, tool_hand=1):
        self.page_count = page_count
        self.palette_hand, self.tool_hand = palette_hand, tool_hand
        self.index = 0                 # page at the front (unbounded, modulo page_count)
        self.angle = 0.0               # displayed ring angle (radians), eases towards the target
        self.fade = 0.0
        self.pinned = False
        self._front = (0.0, 0.0, 1.0)  # horizontal direction from the controller to the head, kept when degenerate
        self._armed = True             # the stick must return to the centre before the next flick
        self.hover = None

    # -- geometry ---------------------------------------------------------------------------------------------------
    @property
    def step(self):
        return 2 * math.pi / max(1, self.page_count)

    @property
    def target_angle(self):
        return -self.index * self.step

    def front_page(self):
        return self.index % self.page_count

    def frame_vectors(self, controller, head):
        """(axis origin, front f, right r): f points horizontally from the controller towards the head."""
        d = mu.sub(head, controller)
        d = (d[0], 0.0, d[2])
        if mu.length(d) > 0.05:
            self._front = mu.normalize(d)
        f = self._front
        r = mu.cross(UP, f)
        origin = mu.sub(mu.add(controller, mu.mul(UP, LIFT)), mu.mul(f, RADIUS))
        return origin, f, r

    def page_frame(self, page, controller, head):
        """(centre, u, v, n) of a page: u right and v up on the page as seen from outside, n the outward normal."""
        origin, f, r = self.frame_vectors(controller, head)
        a = self.angle + page * self.step
        n = mu.add(mu.mul(f, math.cos(a)), mu.mul(r, math.sin(a)))
        u = mu.add(mu.mul(f, -math.sin(a)), mu.mul(r, math.cos(a)))
        return mu.add(origin, mu.mul(n, RADIUS)), u, UP, n

    def page_cos(self, page):
        """Cosine of the page's angle from the front: 1 = facing the user."""
        return math.cos(self.angle + page * self.step)

    @staticmethod
    def locate_slot(x, y):
        """Slot index for local coordinates (metres from the grid centre, y up), or None outside the grid."""
        pitch = CELL + GAP
        col = math.floor((x + GRID_W / 2 + GAP / 2) / pitch)
        row = math.floor((GRID_H / 2 + GAP / 2 - y) / pitch)
        if 0 <= col < COLS and 0 <= row < ROWS and abs(x) <= GRID_W / 2 + GAP / 2 and abs(y) <= GRID_H / 2 + GAP / 2:
            return row * COLS + col
        return None

    def hit_test(self, origin, direction, controller, head):
        """Ray against the interactive pages. Returns (page, slot, point) or None."""
        best = None
        for page in range(self.page_count):
            if self.page_cos(page) < FRONT_COS:
                continue
            centre, u, v, n = self.page_frame(page, controller, head)
            denom = mu.dot(direction, n)
            if denom >= -1e-6:
                continue
            t = mu.dot(mu.sub(centre, origin), n) / denom
            if t <= 0:
                continue
            point = mu.add(origin, mu.mul(direction, t))
            rel = mu.sub(point, centre)
            slot = self.locate_slot(mu.dot(rel, u), mu.dot(rel, v))
            if slot is not None and (best is None or t < best[3]):
                best = (page, slot, point, t)
        return None if best is None else best[:3]

    # -- behaviour --------------------------------------------------------------------------------------------------
    def wants_visible(self, controller, head, head_orientation):
        to_ctrl = mu.sub(controller, head)
        dist = mu.length(to_ctrl)
        if not GAZE_RANGE[0] <= dist <= GAZE_RANGE[1]:
            return False
        forward = mu.rotate(head_orientation, (0.0, 0.0, -1.0))
        return mu.dot(forward, mu.mul(to_ctrl, 1.0 / dist)) >= GAZE_COS

    def update(self, frame, navigating=False):
        result = RingResult()
        palette, tool = frame.hands[self.palette_hand], frame.hands[self.tool_hand]
        if not palette.aim.tracked:
            self.fade = 0.0
            self.hover = None
            return result
        controller = palette.aim.position
        head = frame.head.position
        dt = frame.dt

        if "button1" in palette.pressed:
            self.pinned = not self.pinned
        want = (self.pinned or self.wants_visible(controller, head, frame.head.orientation)) and not navigating
        self.fade = min(1.0, self.fade + FADE_RATE * dt) if want else max(0.0, self.fade - FADE_RATE * dt)
        if self.fade <= 0.0:
            self.hover = None
            self._armed = True
            return result
        result.visible = True

        # stick flick turns the ring one page
        x = palette.stick[0]
        if self._armed and abs(x) >= FLICK_ON and self.page_count > 1 and self.fade > 0.5:
            self.index += 1 if x > 0 else -1
            self._armed = False
            result.haptics.append((self.palette_hand, 0.35, 0.025))
        elif abs(x) <= FLICK_OFF:
            self._armed = True
        self.angle += (self.target_angle - self.angle) * min(1.0, TURN_RATE * dt)

        # ray hover and activation
        hit = None
        if tool.aim.tracked and self.fade > 0.8:
            direction = mu.rotate(tool.aim.orientation, (0.0, 0.0, -1.0))
            hit = self.hit_test(tool.aim.position, direction, controller, head)
        previous = self.hover
        self.hover = None if hit is None else (hit[0], hit[1])
        if hit is not None:
            result.hover, result.ray_end, result.consume_trigger = self.hover, hit[2], True
            if self.hover != previous:
                result.haptics.append((self.tool_hand, 0.15, 0.015))
            if "trigger" in tool.pressed:
                result.activated = self.hover
                result.haptics.append((self.tool_hand, 0.5, 0.04))
        return result
