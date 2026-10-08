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
calls `Inference.select` in place of using every anchor, and nothing else depends on it, so it can be dropped by removing that call.

`Snapper` is the stronger half: a cursor within `SNAP` of a vertex or the middle of an edge, or within `EDGE` of an edge, snaps to that
feature (the nearest point of the edge) and holds on to it, so the point is not just lined up with an axis but is on the feature
that drives it; `Features` describes an anchor as the vertex or the middle of an edge that it is, for the highlight of that feature."""

import math
from dataclasses import dataclass
from typing import Optional, Tuple

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


# ---- snapping to the feature near the hand (vertices, middles and edges) ----

SNAP = 0.014            # metres of hand space: a vertex or the middle of an edge this close to the cursor is snapped to
EDGE = 0.011            # and an edge this close: the point is the nearest point of the edge
STICKY = 1.6            # a feature that is snapped to is kept until the cursor is this many times further than it takes to catch it


@dataclass(frozen=True)
class Snap:
    point: Tuple[float, float, float]
    kind: str                                          # "vertex", "middle" or "edge"
    edge: Optional[tuple] = None                       # the straight edge ((x, y, z), (x, y, z)) that a middle or an edge snap lies on


def nearest_on_segment(p, a, b):
    """(nearest point of the segment from `a` to `b` to `p`, its distance)."""
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    length2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2]
    if length2 < 1e-18:
        return tuple(a), math.sqrt(_distance_squared(p, a))
    t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1] + (p[2] - a[2]) * ab[2]) / length2
    t = min(max(t, 0.0), 1.0)
    q = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    return q, math.sqrt(_distance_squared(p, q))


def _key(point):
    return (round(point[0], 3), round(point[1], 3), round(point[2], 3))


class Features:
    """What the hand can snap to: `anchors` (vertices and the middles of straight edges) and the straight `edges`. Describes an anchor as
    the vertex or the middle of an edge that it is (`describe`), looked up by position."""

    def __init__(self, anchors, edges):
        self.anchors, self.edges = anchors, edges
        self._middles = {}
        for a, b in edges:
            self._middles[_key(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0))] = (a, b)

    def describe(self, anchor):
        edge = self._middles.get(_key(anchor))
        return Snap(tuple(anchor), "middle", edge) if edge is not None else Snap(tuple(anchor), "vertex")


class Snapper:
    """Snapping like Onshape's inference: the cursor snaps to the nearest vertex or middle of an edge within `SNAP`, else to the nearest
    point of an edge within `EDGE`, and holds on to what it snapped to until the cursor is `STICKY` times as far away (a nearer vertex
    takes over), so the point does not jump between features while the hand trembles."""

    def __init__(self, snap=SNAP, edge=EDGE, sticky=STICKY):
        self.snap, self.edge, self.sticky = snap, edge, sticky
        self.held = None                                # the `Snap` the cursor is held on

    def reset(self):
        self.held = None

    def _place(self, raw, held):
        """(point, distance) of the held feature for a cursor at `raw` (an edge is held by its line, the others by their point)."""
        if held.kind == "edge":
            return nearest_on_segment(raw, *held.edge)
        return held.point, math.sqrt(_distance_squared(raw, held.point))

    def snap_to(self, raw, features, mm_per_metre):
        """The `Snap` for a cursor at `raw` (document millimetres) or None; `mm_per_metre` converts the reaches to the document."""
        reach, edge_reach = self.snap * mm_per_metre, self.edge * mm_per_metre
        best = None
        for anchor in features.anchors:
            d = math.sqrt(_distance_squared(raw, anchor))
            if d <= reach and (best is None or d < best[0]):
                best = (d, anchor)
        if self.held is not None:
            point, d = self._place(raw, self.held)
            limit = (edge_reach if self.held.kind == "edge" else reach) * self.sticky
            if d <= limit and (best is None or (self.held.kind != "edge" and (best[0] >= d or tuple(best[1]) == self.held.point))):
                return Snap(tuple(point), self.held.kind, self.held.edge)       # a vertex or a middle always takes over from an edge
        if best is not None:
            self.held = features.describe(best[1])
            return self.held
        nearest = None
        for edge in features.edges:
            point, d = nearest_on_segment(raw, edge[0], edge[1])
            if d <= edge_reach and (nearest is None or d < nearest[0]):
                nearest = (d, point, edge)
        self.held = None if nearest is None else Snap(tuple(nearest[1]), "edge", nearest[2])
        return self.held
