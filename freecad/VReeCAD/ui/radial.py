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
"""The quick radial (docs/ux-design.md, Quick radial). No Coin, OpenXR or FreeCAD imports.

Holding `button1` of the tool hand (outside navigation) opens a disc around the hand, cut into one segment per favourite button. The item is chosen by the
direction the hand moves from the spot where the button went down, seen from the head: the first item is straight up, the others
follow clockwise. Releasing the button activates the chosen item; releasing it before the hand has left the dead zone activates the
hub item (the button in the middle, `CENTRE`), and starting a grip cancels. The plane of the radial and its axes are fixed when it opens, so turning the head does not move the choice."""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from freecad.VReeCAD.core import mathutil as mu

MAX_ITEMS = 8
DEAD_ZONE = 0.03       # metres the hand must move before an item is chosen
INNER = DEAD_ZONE      # radius of the hub: the area in which nothing is chosen
OUTER = 0.115          # outer radius of the segments
GAP = 0.003            # metres of dark between neighbouring segments, measured at the outer radius
TOWARDS_HEAD = 0.05    # the radial stands this far in front of the hand, so the controller does not hide it
RECENT = 8             # number of favourites: the buttons used last, padded from `DEFAULT_FAVOURITES`; the option discs of the tools have as many sections
DEFAULT_FAVOURITES = ("doc.undo", "doc.redo", "view.reset", "doc.delete", "tool.move", "pointer.mode", "doc.copy", "doc.colour")
NEVER_FAVOURITE = ("view.layout", "app.close")   # buttons that must not sit one flick from the hand
CENTRE = "tool.select"   # the button in the hub: a release without moving the hand activates it; it is never one of the segments


@dataclass
class RadialState:
    open: bool = False
    items: List[str] = field(default_factory=list)              # button ids, first item straight up, then clockwise
    selected: Optional[int] = None
    activated: Optional[int] = None                             # item index chosen by releasing the button this frame
    hub: Optional[str] = None                                   # button id of the hub item, or None for a hub without one
    activated_hub: bool = False                                 # the button was released inside the dead zone: the hub item is chosen
    centre: Tuple[float, float, float] = (0.0, 0.0, 0.0)        # of the drawn radial
    right: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    up: Tuple[float, float, float] = (0.0, 1.0, 0.0)
    cursor: Tuple[float, float] = (0.0, 0.0)                    # the hand relative to where the button went down (right, up), metres
    haptics: List[tuple] = field(default_factory=list)          # (hand, amplitude, duration_s)


def sector(x, y, count):
    """The item (0 is straight up, clockwise) for a displacement x (right) and y (up) with `count` items."""
    step = 2 * math.pi / count
    angle = math.atan2(x, y) % (2 * math.pi)
    return int((angle + step / 2) // step) % count


def segment_strip(index, count, r_in=INNER, r_out=OUTER, gap=GAP, steps=10):
    """The points (x right, y up, metres) of a triangle strip that fills the segment of item `index` of `count`: a ring sector
    centred on the direction of the item (0 is straight up, clockwise), alternating outer and inner points."""
    half = math.pi / count - gap / (2 * r_out)
    centre = 2 * math.pi * index / count
    points = []
    for k in range(steps + 1):
        a = centre - half + 2 * half * k / steps
        points += [(r_out * math.sin(a), r_out * math.cos(a)), (r_in * math.sin(a), r_in * math.cos(a))]
    return points


def choose_items(recent, known, hidden=(), count=RECENT):
    """The favourites: the buttons used last (newest first), then the defaults, without buttons that are unknown, hidden, never a
    favourite or the hub item, and without repeats. `recent` and the result hold button ids."""
    items = []
    for button_id in list(recent) + list(DEFAULT_FAVOURITES):
        if button_id in known and button_id not in hidden and button_id not in NEVER_FAVOURITE and button_id != CENTRE and button_id not in items:
            items.append(button_id)
        if len(items) == count:
            break
    return items


def remember(recent, button_id, limit=RECENT):
    """`recent` with `button_id` moved to the front, at most `limit` long."""
    return ([button_id] + [f for f in recent if f != button_id])[:limit]


class QuickRadial:
    def __init__(self, hand=1):
        self.hand = hand
        self.is_open = False
        self._items: List[str] = []
        self._origin = (0.0, 0.0, 0.0)
        self._right = (1.0, 0.0, 0.0)
        self._up = (0.0, 1.0, 0.0)
        self._forward = (0.0, 0.0, -1.0)
        self._selected: Optional[int] = None

    def close(self):
        self.is_open = False
        self._selected = None

    def update(self, frame, items, blocked=False, hub=None) -> RadialState:
        """One frame. `items` are the button ids to offer when the radial opens; `blocked` stops it from opening and cancels an open
        radial (the tool hand is busy: navigating, dragging a slider, lifting a panel); `hub` is the button id of the item in the middle,
        which a release inside the dead zone activates (without one such a release cancels)."""
        state = RadialState()
        hand = frame.hands[self.hand]
        pose = hand.grip_pose if hand.grip_pose.tracked else hand.aim
        blocked = blocked or any(h.down("grip") for h in frame.hands) or not pose.tracked
        if self.is_open and blocked:
            self.close()
        if not self.is_open and not blocked and "button1" in hand.pressed and items:
            q = frame.head.orientation
            self._right, self._up, self._forward = (mu.rotate(q, (1.0, 0.0, 0.0)), mu.rotate(q, (0.0, 1.0, 0.0)),
                                                   mu.rotate(q, (0.0, 0.0, -1.0)))
            self._origin, self._items, self._selected, self.is_open = pose.position, list(items[:MAX_ITEMS]), None, True
            state.haptics.append((self.hand, 0.3, 0.03))
        if not self.is_open:
            return state

        offset = mu.sub(pose.position, self._origin)
        x, y = mu.dot(offset, self._right), mu.dot(offset, self._up)
        selected = sector(x, y, len(self._items)) if math.hypot(x, y) >= DEAD_ZONE else None
        if selected != self._selected:
            self._selected = selected
            if selected is not None:
                state.haptics.append((self.hand, 0.2, 0.02))
        state.open, state.items, state.selected, state.cursor, state.hub = True, self._items, selected, (x, y), hub
        state.right, state.up = self._right, self._up
        state.centre = mu.add(self._origin, mu.mul(self._forward, -TOWARDS_HEAD))
        if not hand.down("button1"):
            state.open = False
            state.activated = selected
            state.activated_hub = selected is None and hub is not None
            if selected is not None or state.activated_hub:
                state.haptics.append((self.hand, 0.5, 0.04))
            self.close()
        return state
