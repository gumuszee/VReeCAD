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
"""Behaviour and geometry of the palette carousel (docs/ux-design.md, Palette carousel). No Coin, OpenXR or FreeCAD imports.

The carousel is a prism around the long axis of the palette hand's controller: the sides turn with the controller and all of them
are visible, the side at the front stands on the thumb side of the controller facing up. Each side carries rows of panels (pages of
faces): the first row is the bottom row nearest the user, further rows are further forward. The stick of the palette hand turns the
carousel one side per flick, the carousel fades in while the head looks at the controller (or when pinned) and out otherwise, the
tool hand's ray hovers faces and its trigger activates them. Holding the trigger on the title bar of a panel lifts the panel;
releasing it over the left or right half of another panel puts the panel next to it in its row, over the upper or lower part makes a
new row above or below it, over the empty slot of an empty side gives the panel that side.
`update` returns what the host needs: hover, activation, drop, haptics and the ray end point."""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import pointing
from freecad.BlocksCAD.ui.layout import COLS, ROWS

CELL = 0.05            # metres, face edge
GAP = 0.008
GRID_W = COLS * CELL + (COLS - 1) * GAP
GRID_H = ROWS * CELL + (ROWS - 1) * GAP
PANEL_W = GRID_W + 0.02
PANEL_H = GRID_H + 0.05
GRID_Y = -0.015        # centre of the grid of faces in panel coordinates (origin at the centre of the panel plate)
TITLE_Y = (GRID_Y + GRID_H / 2 + 0.004, GRID_Y + GRID_H / 2 + 0.036)   # title bar, the handle for lifting a panel
PANEL_GAP = 0.012
FORWARD = 0.09         # distance of the carousel centre in front of the grip point, along the controller
RADIUS_MIN = 0.09      # distance of the side planes from the controller axis
GAZE_COS = math.cos(math.radians(35.0))
GAZE_RANGE = (0.12, 0.95)
FLICK_ON, FLICK_OFF = 0.65, 0.3
FADE_RATE = 8.0        # per second
TURN_RATE = 14.0       # exponential approach rate of the carousel angle
POINT_COS = -0.3       # sides turned further away than this cannot be pointed at
EDGE_ZONE = 0.5        # while lifting: the outer quarter above and below a panel (fraction of its half height)
TIP_FRONT = 0.03       # a tip within this distance in front of a panel touches it
TIP_BEHIND = 0.015     # and this far behind its plate (pushing through)

DropTarget = Tuple[int, int, Optional[int], bool]    # (side, row, page to insert before or None, new row at `row`)


@dataclass
class PanelPose:
    centre: Tuple[float, float, float]
    u: Tuple[float, float, float]      # right on the panel as seen from outside
    v: Tuple[float, float, float]      # up on the panel: the direction the controller points
    n: Tuple[float, float, float]      # outward normal
    cos: float = 1.0                   # cosine of the angle of its side from the front: 1 = facing up from the controller
    side: int = 0                      # carousel side the panel stands on
    row: int = 0                       # row on the side


@dataclass
class Hit:
    kind: str                          # "face", "title", "body" or "ghost"
    side: int
    row: int
    page: Optional[int]                # None on a ghost
    slot: Optional[int]
    point: Tuple[float, float, float]
    distance: float
    zone: str = ""                     # "left", "right", "above" or "below": where on the panel the ray is


@dataclass
class RingResult:
    visible: bool = False
    hover: Optional[Tuple[int, int]] = None      # (page index, slot) of the face under the ray
    hover_title: Optional[int] = None            # page whose title bar is under the ray
    activated: Optional[Tuple[int, int]] = None  # (page index, slot) activated this frame
    lifted: Optional[int] = None                 # page held by the trigger (being rearranged)
    lift_point: Optional[Tuple[float, float, float]] = None
    drop_target: Optional[DropTarget] = None     # where the lifted page would go if released now
    drop_marker: Optional[Tuple[Optional[int], str, int]] = None   # (page or None on a ghost, zone, side) to highlight
    dropped: Optional[tuple] = None              # (page, side, row, before, new_row): released onto a target this frame
    ray_end: Optional[Tuple[float, float, float]] = None
    haptics: List[tuple] = field(default_factory=list)   # (hand, amplitude, duration_s)
    consume_trigger: bool = False                # the tool hand's trigger belongs to the carousel this frame


def side_layout(rows):
    """Centres of the panels of one side in side coordinates (x right, y forward, metres), the half width and the half height.
    Rows are centred on the side, the first row is at the bottom."""
    centres = {}
    half_w, n = 0.0, len(rows)
    for r, row in enumerate(rows):
        width = len(row) * PANEL_W + (len(row) - 1) * PANEL_GAP
        half_w = max(half_w, width / 2)
        y = (r - (n - 1) / 2) * (PANEL_H + PANEL_GAP)
        for k, page in enumerate(row):
            centres[page] = (-width / 2 + PANEL_W / 2 + k * (PANEL_W + PANEL_GAP), y)
    half_h = (n * PANEL_H + max(n - 1, 0) * PANEL_GAP) / 2 if n else PANEL_H / 2
    return centres, max(half_w, PANEL_W / 2), half_h


class PaletteRing:
    def __init__(self, sides, palette_hand=0, tool_hand=1):
        self.sides = [[list(r) for r in s] for s in sides]   # page indexes: side -> rows -> pages
        self.palette_hand, self.tool_hand = palette_hand, tool_hand
        self.index = 0                 # side at the front (unbounded, modulo the number of sides)
        self.angle = 0.0               # displayed carousel angle (radians), eases towards the target
        self.fade = 0.0
        self.pinned = False
        self.hover = None
        self.hover_title = None
        self.lifted: Optional[int] = None
        self.poses: Dict[int, PanelPose] = {}
        self.ghosts: Dict[int, PanelPose] = {}       # empty sides while lifting
        self.origin = (0.0, 0.0, 0.0)  # centre of the carousel axis
        self.radius = RADIUS_MIN
        self._armed = True             # the stick must return to the centre before the next flick
        self._count = max(1, len(self.sides))
        self._known_count = None
        self._target: Optional[DropTarget] = None
        self._lift_distance = 0.5

    # structure
    def set_sides(self, sides):
        self.sides = [[list(r) for r in s] for s in sides]

    def display_sides(self):
        """The sides as drawn: without the lifted page, and while lifting with one empty side at the end to start a new side."""
        if self.lifted is None:
            return self.sides
        shown = lay.without_page(self.sides, self.lifted)
        if not any(len(side) == 0 for side in shown):
            shown.append([])
        return shown

    def focus_side(self, side):
        self.index = side
        self.angle = self.target_angle

    @property
    def step(self):
        return 2 * math.pi / max(1, self._count)

    @property
    def target_angle(self):
        return -self.index * self.step

    def front_side(self):
        return self.index % max(1, self._count)

    # geometry
    @staticmethod
    def controller_axes(pose):
        """(origin of the carousel, right, up, forward) of a controller pose."""
        q = pose.orientation
        right, up, forward = mu.rotate(q, (1.0, 0.0, 0.0)), mu.rotate(q, (0.0, 1.0, 0.0)), mu.rotate(q, (0.0, 0.0, -1.0))
        return mu.add(pose.position, mu.mul(forward, FORWARD)), right, up, forward

    def side_frame(self, side, pose):
        """(centre, u, v, n) of the plane of a carousel side at the current angle."""
        origin, right, up, forward = self.controller_axes(pose)
        a = self.angle + side * self.step
        n = mu.add(mu.mul(up, math.cos(a)), mu.mul(right, math.sin(a)))
        u = mu.cross(forward, n)
        return mu.add(origin, mu.mul(n, self.radius)), u, forward, n

    def _pose_at(self, side, row, x, y, pose):
        centre, u, v, n = self.side_frame(side, pose)
        a = self.angle + side * self.step
        return PanelPose(mu.add(centre, mu.add(mu.mul(u, x), mu.mul(v, y))), u, v, n, math.cos(a), side, row)

    def layout_poses(self, pose):
        """Compute the pose of every panel (and of the ghost slots of empty sides while lifting) for a palette controller pose."""
        shown = self.display_sides()
        self._count = max(1, len(shown))
        layouts = [side_layout(rows) for rows in shown]
        half = max([lo[1] for lo in layouts] or [PANEL_W / 2])
        self.radius = max(RADIUS_MIN, half / math.tan(math.pi / self._count)) if self._count >= 3 else RADIUS_MIN
        self.origin = self.controller_axes(pose)[0]
        self.poses, self.ghosts = {}, {}
        for side, (rows, (centres, _, _)) in enumerate(zip(shown, layouts)):
            if not rows:
                self.ghosts[side] = self._pose_at(side, 0, 0.0, 0.0, pose)
            for r, row in enumerate(rows):
                for page in row:
                    x, y = centres[page]
                    self.poses[page] = self._pose_at(side, r, x, y, pose)
        return shown

    @staticmethod
    def locate_slot(x, y):
        """Slot index for local coordinates (metres from the grid centre, y up), or None outside the grid."""
        pitch = CELL + GAP
        col = math.floor((x + GRID_W / 2 + GAP / 2) / pitch)
        row = math.floor((GRID_H / 2 + GAP / 2 - y) / pitch)
        if 0 <= col < COLS and 0 <= row < ROWS and abs(x) <= GRID_W / 2 + GAP / 2 and abs(y) <= GRID_H / 2 + GAP / 2:
            return row * COLS + col
        return None

    @staticmethod
    def _locate(pose, point):
        rel = mu.sub(point, pose.centre)
        return mu.dot(rel, pose.u), mu.dot(rel, pose.v)

    def _candidates(self):
        return list(self.poses.items()) + [(None, p) for p in self.ghosts.values()]

    def _make_hit(self, page, pose, point, distance):
        """The `Hit` for a point on the plane of a panel (or ghost), or None when it lies outside the plate."""
        x, y = self._locate(pose, point)
        if abs(x) > PANEL_W / 2 or abs(y) > PANEL_H / 2:
            return None
        fy = y / (PANEL_H / 2)
        zone = "above" if fy > EDGE_ZONE else "below" if fy < -EDGE_ZONE else "left" if x < 0 else "right"
        if page is None:
            return Hit("ghost", pose.side, 0, None, None, point, distance, zone)
        if TITLE_Y[0] <= y <= TITLE_Y[1]:
            return Hit("title", pose.side, pose.row, page, None, point, distance, zone)
        slot = self.locate_slot(x, y - GRID_Y)
        return Hit("face" if slot is not None else "body", pose.side, pose.row, page, slot, point, distance, zone)

    def hit_test(self, origin, direction):
        """Ray against the panels that face it. Returns the nearest `Hit` or None. Needs `layout_poses` first."""
        best = None
        for page, pose in self._candidates():
            if pose.cos < POINT_COS:
                continue
            denom = mu.dot(direction, pose.n)
            if denom >= -1e-6:
                continue
            t = mu.dot(mu.sub(pose.centre, origin), pose.n) / denom
            if t <= 0:
                continue
            hit = self._make_hit(page, pose, mu.add(origin, mu.mul(direction, t)), t)
            if hit is not None and (best is None or t < best.distance):
                best = hit
        return best

    def hit_tip(self, tip):
        """The panel a tip point touches: within `TIP_FRONT` in front of its plate or `TIP_BEHIND` behind it. Returns the `Hit`
        (the point is the tip projected onto the plate) or None."""
        best = None
        for page, pose in self._candidates():
            if pose.cos < POINT_COS:
                continue
            d = mu.dot(mu.sub(tip, pose.centre), pose.n)
            if d > TIP_FRONT or d < -TIP_BEHIND:
                continue
            hit = self._make_hit(page, pose, mu.sub(tip, mu.mul(pose.n, d)), abs(d))
            if hit is not None and (best is None or abs(d) < best.distance):
                best = hit
        return best

    def drop_target(self, hit):
        """Where the lifted page goes when released over `hit`."""
        if hit.kind == "ghost":
            return (hit.side, 0, None, False)
        if hit.zone == "above":
            return (hit.side, hit.row + 1, None, True)
        if hit.zone == "below":
            return (hit.side, hit.row, None, True)
        row = self.display_sides()[hit.side][hit.row]
        k = row.index(hit.page)
        if hit.zone == "left":
            return (hit.side, hit.row, hit.page, False)
        return (hit.side, hit.row, row[k + 1] if k + 1 < len(row) else None, False)

    # behaviour
    def wants_visible(self, origin, head, head_orientation):
        to_ctrl = mu.sub(origin, head)
        dist = mu.length(to_ctrl)
        if not GAZE_RANGE[0] <= dist <= GAZE_RANGE[1]:
            return False
        forward = mu.rotate(head_orientation, (0.0, 0.0, -1.0))
        return mu.dot(forward, mu.mul(to_ctrl, 1.0 / dist)) >= GAZE_COS

    def _hide(self):
        self.hover = self.hover_title = self.lifted = self._target = None
        self.poses, self.ghosts = {}, {}

    def update(self, frame, navigating=False, pointers=None):
        """One frame. `pointers` holds the `pointing.PointerPose` of each hand; without it the tool hand casts a ray along its aim."""
        result = RingResult()
        palette, tool = frame.hands[self.palette_hand], frame.hands[self.tool_hand]
        pose = palette.grip_pose if palette.grip_pose.tracked else palette.aim
        if not pose.tracked:
            self.fade = 0.0
            self._hide()
            return result
        head = frame.head.position
        dt = frame.dt

        if "button1" in palette.pressed:
            self.pinned = not self.pinned
        self.layout_poses(pose)
        want = (self.pinned or self.lifted is not None
                or self.wants_visible(self.origin, head, frame.head.orientation)) and not navigating
        self.fade = min(1.0, self.fade + FADE_RATE * dt) if want else max(0.0, self.fade - FADE_RATE * dt)
        if self.fade <= 0.0:
            self._hide()
            self._armed = True
            return result
        result.visible = True

        # a change in the number of sides keeps the front side in front
        if self._known_count != self._count:
            self._known_count = self._count
            self.index %= self._count
            self.angle = self.target_angle
            self.layout_poses(pose)

        # stick flick turns the carousel one side
        x = palette.stick[0]
        if self._armed and abs(x) >= FLICK_ON and self._count > 1 and self.fade > 0.5:
            self.index += 1 if x > 0 else -1
            self._armed = False
            result.haptics.append((self.palette_hand, 0.35, 0.025))
        elif abs(x) <= FLICK_OFF:
            self._armed = True
        self.angle += (self.target_angle - self.angle) * min(1.0, TURN_RATE * dt)
        self.layout_poses(pose)

        # ray hover, activation and rearranging
        pointer = pointers[self.tool_hand] if pointers is not None else pointing.pointer_pose(tool.aim)
        hit = None
        if pointer.tracked and self.fade > 0.8:
            hit = self.hit_tip(pointer.position) if pointer.tip else self.hit_test(pointer.position, pointer.direction)
        previous = (self.hover, self.hover_title, self._target)
        self.hover = (hit.page, hit.slot) if hit is not None and hit.kind == "face" else None
        self.hover_title = hit.page if hit is not None and hit.kind == "title" else None
        result.hover, result.hover_title = self.hover, self.hover_title
        self._target = None

        if self.lifted is None:
            if hit is not None:
                result.ray_end, result.consume_trigger = hit.point, True
                if (self.hover, self.hover_title) != previous[:2]:
                    result.haptics.append((self.tool_hand, 0.15, 0.015))
                if "trigger" in tool.pressed:
                    if hit.kind == "face":
                        result.activated = self.hover
                        result.haptics.append((self.tool_hand, 0.5, 0.04))
                    elif hit.kind == "title":
                        self.lifted = hit.page
                        self._lift_distance = hit.distance
                        result.haptics.append((self.tool_hand, 0.4, 0.04))
                        self.layout_poses(pose)
        else:
            result.consume_trigger = True
            if hit is not None:
                self._target = self.drop_target(hit)
                result.ray_end = hit.point
                result.drop_marker = (hit.page, "" if hit.kind == "ghost" else hit.zone, hit.side)
            if self._target != previous[2]:
                result.haptics.append((self.tool_hand, 0.15, 0.015))
            if not tool.down("trigger"):
                page, target = self.lifted, self._target
                self.lifted = None
                if target is not None:
                    result.dropped = (page,) + target
                    result.haptics.append((self.tool_hand, 0.5, 0.04))
                self._target = None
            elif pointer.tracked:
                if pointer.tip:
                    result.lift_point = pointer.position if hit is None else hit.point
                else:
                    reach = self._lift_distance if hit is None else hit.distance
                    result.lift_point = mu.add(pointer.position, mu.mul(pointer.direction, reach))
        result.lifted = self.lifted
        result.drop_target = self._target
        return result
