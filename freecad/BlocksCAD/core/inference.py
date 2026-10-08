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
"""Inference: the points of the model that the alignment guides may use are those near what the hand works on, plus those it has
dwelt on (docs/ux-design.md, Guides). Lengths are document millimetres. No FreeCAD imports.

The plain guides (`core/guides.py`) line a point up with every anchor of the model, so in a scene with many objects every coordinate
matches some anchor and the guides pull the point all the time. Inference narrows the anchors that are offered to the guides: the
anchors within `NEAR` of a probe (the cursor, or the points of an object being moved), and the anchors that have been **acquired**: an
anchor the probe has stayed within `ACQUIRE` of for `DWELL` seconds stays offered, up to `LIMIT` of them, until the hand has worked
elsewhere for `FORGET` seconds, so a point far away can be lined up with by hovering over it first. The module stands alone: the host
calls `Inference.select` in place of using every anchor, and nothing else depends on it, so it can be dropped by removing that call."""

NEAR = 0.06             # metres of hand space: anchors this close to a probe are offered
ACQUIRE = 0.012         # metres of hand space: a probe this close to an anchor for `DWELL` seconds acquires it
DWELL = 0.4             # seconds
LIMIT = 3               # acquired anchors kept
FORGET = 1.0            # seconds without a call after which the acquired anchors are forgotten


def _distance_squared(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


class Inference:
    def __init__(self, near=NEAR, acquire=ACQUIRE, dwell=DWELL, limit=LIMIT, forget=FORGET):
        self.near, self.acquire, self.dwell, self.limit, self.forget = near, acquire, dwell, limit, forget
        self.acquired = []                 # the anchors that stay offered, oldest first
        self._candidate = None             # the anchor the probe is dwelling on
        self._since = 0.0                  # the time the dwelling began
        self._last = None                  # the time of the last call

    def reset(self):
        self.acquired, self._candidate, self._last = [], None, None

    def select(self, anchors, probes, mm_per_metre, now):
        """(anchors to offer, whether an anchor was acquired by this call). `probes` are points of the hand's work, `mm_per_metre` the
        document millimetres of one metre of hand space, `now` a time in seconds."""
        if self._last is not None and now - self._last > self.forget:
            self.reset()
        self._last = now
        if not probes:
            return list(self.acquired), False
        reach, acquire = (self.near * mm_per_metre) ** 2, (self.acquire * mm_per_metre) ** 2
        offered, closest = [], None
        for anchor in anchors:
            gap = min(_distance_squared(anchor, p) for p in probes)
            if gap <= reach:
                offered.append(anchor)
                if closest is None or gap < closest[0]:
                    closest = (gap, anchor)
        fresh = False
        if closest is not None and closest[0] <= acquire and tuple(closest[1]) not in self.acquired:
            if self._candidate != tuple(closest[1]):
                self._candidate, self._since = tuple(closest[1]), now
            elif now - self._since >= self.dwell:
                self.acquired = (self.acquired + [self._candidate])[-self.limit:]
                self._candidate, fresh = None, True
        else:
            self._candidate = None
        offered += [a for a in self.acquired if a not in offered]
        return offered, fresh
