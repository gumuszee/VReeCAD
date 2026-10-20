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
"""Alignment guides: where a point being placed lines up with the points of the model (docs/ux-design.md, Guides). Lengths are
document millimetres. No FreeCAD imports.

An anchor is a point of the model that a new point can line up with (a vertex, the middle of a straight edge). `align` takes the
cursor before and after the grid, and the anchors: on every axis on which an anchor has nearly the same coordinate as the cursor the
point takes that coordinate (a guide runs from the anchor to the point), and when one anchor matches on all three axes the point is
that anchor (a point guide)."""

from bisect import bisect_left
from dataclasses import dataclass
from typing import List, Optional, Tuple

AXIS_NAMES = "XYZ"


@dataclass(frozen=True)
class Guide:
    kind: str                         # "axis" (the point has the coordinate of the anchor on `axis`) or "point" (the point is the anchor)
    axis: int                         # 0, 1 or 2 for an axis guide, -1 for a point guide
    anchor: Tuple[float, float, float]
    point: Tuple[float, float, float]
    label: str = ""                   # what the guide says when it is no alignment with an axis ("Parallel", "Perpendicular")

    @property
    def text(self):
        if self.label:
            return self.label
        if self.kind == "point":
            return "On the point"
        return f"Aligned {AXIS_NAMES[self.axis]}" if 0 <= self.axis < 3 else "Aligned"


def _distance_squared(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def align(raw, grid_point, anchors, tolerance, axes=(0, 1, 2)):
    """(point, guides) for a cursor at `raw` that the grid rounds to `grid_point`: see the module text. `tolerance` is how far in
    millimetres a coordinate may be from the one of an anchor to line up with it. Only the coordinates in `axes` line up; the point is
    an anchor when one anchor matches on all of them."""
    nearest: List[Optional[tuple]] = [None, None, None]
    for axis in axes:
        best, best_distance = None, None
        for anchor in anchors:
            if abs(anchor[axis] - raw[axis]) < tolerance:
                distance = _distance_squared(anchor, raw)
                if best is None or distance < best_distance:
                    best, best_distance = anchor, distance
        nearest[axis] = best
    first = nearest[axes[0]]
    if first is not None and all(nearest[axis] == first for axis in axes):
        return tuple(first), [Guide("point", -1, tuple(first), tuple(first))]
    point = tuple(nearest[axis][axis] if nearest[axis] is not None else grid_point[axis] for axis in range(3))
    guides = [Guide("axis", axis, tuple(nearest[axis]), point) for axis in axes if nearest[axis] is not None]
    return point, guides


def align_along(raw, grid_value, candidates, tolerance):
    """(value, anchor) for a value `raw` along a line (a distance) that the grid rounds to `grid_value`: the nearest of the
    `candidates` ((value, anchor) pairs) within `tolerance` of `raw`, or (`grid_value`, None) when none is."""
    best = None
    for value, anchor in candidates:
        gap = abs(value - raw)
        if gap < tolerance and (best is None or gap < best[0]):
            best = (gap, value, anchor)
    return (grid_value, None) if best is None else (best[1], best[2])


def align_direction(start, end, references, tolerance):
    """(end, relation) for a line drawn from `start` towards `end` (points of a plane): when the line is nearly parallel or perpendicular
    to a reference line, `end` moves to the nearest point of the ray from `start` that is exactly so, and `relation` is ("Parallel" or
    "Perpendicular", the reference (a, b)); else (`end`, None). "Nearly" is a distance of `end` from that ray of less than `tolerance`
    (the nearest wins). A reference without length, or a line without length, is left out."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx * dx + dy * dy < 1e-12:
        return tuple(end), None
    best = None
    for a, b in references:
        rx, ry = b[0] - a[0], b[1] - a[1]
        length = (rx * rx + ry * ry) ** 0.5
        if length < 1e-9:
            continue
        along, across = (rx / length, ry / length), (-ry / length, rx / length)
        for relation, ray in (("Parallel", along), ("Perpendicular", across)):
            lateral = abs(dx * ray[1] - dy * ray[0])
            if lateral < tolerance and (best is None or lateral < best[0]):
                reach = dx * ray[0] + dy * ray[1]
                if abs(reach) > 1e-9:
                    best = (lateral, (start[0] + ray[0] * reach, start[1] + ray[1] * reach), relation, (a, b))
    if best is None:
        return tuple(end), None
    return best[1], (best[2], best[3])


def align_length(start, end, references, tolerance):
    """(end, reference) for a line drawn from `start` towards `end`: when its length is within `tolerance` of the length of a
    reference line ((a, b) pairs), `end` moves along the line to exactly that length and `reference` is that line (the nearest length
    wins); else (`end`, None)."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-9:
        return tuple(end), None
    best = None
    for a, b in references:
        wanted = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        gap = abs(wanted - length)
        if wanted > 1e-9 and gap < tolerance and (best is None or gap < best[0]):
            best = (gap, wanted, (a, b))
    if best is None:
        return tuple(end), None
    scale = best[1] / length
    return (start[0] + dx * scale, start[1] + dy * scale), best[2]


def align_tangent(base, tip, directions, tolerance):
    """(point, direction) for the tip of a handle that starts at `base` and ends at `tip`: when the tip is within `tolerance` of the line
    through `base` along one of the unit `directions` (either way), the point is the foot of the tip on that line and `direction` the
    direction (the nearest line wins); else (`tip`, None). A tip within `tolerance` of the base is left alone."""
    d = tuple(t - b for t, b in zip(tip, base))
    if sum(c * c for c in d) < tolerance * tolerance:
        return tuple(tip), None
    best = None
    for u in directions:
        along = sum(c * k for c, k in zip(d, u))
        lateral = sum((c - along * k) ** 2 for c, k in zip(d, u)) ** 0.5
        if lateral < tolerance and (best is None or lateral < best[0]):
            best = (lateral, tuple(b + along * k for b, k in zip(base, u)), tuple(u))
    return (tuple(tip), None) if best is None else (best[1], best[2])


def index_anchors(anchors):
    """The anchors sorted by each coordinate, as ((values, anchors) of x, of y, of z), for `align_translation`."""
    index = []
    for axis in range(3):
        ordered = sorted(anchors, key=lambda a: a[axis])
        index.append(([a[axis] for a in ordered], ordered))
    return tuple(index)


def align_translation(points, index, tolerance):
    """(shift, guides) for a body whose points are `points` that is moved freely: on each axis the shift brings the point that is
    nearest to an anchor (within `tolerance`, anchors from `index_anchors`) level with that anchor, so a corner or a middle of the
    body lines up with the model. The guides run from the anchors to the points as they lie after the shift; when one pair of a point
    and an anchor is level on all three axes the guide is a point guide. The shift is zero on an axis where nothing is near."""
    shift, picks = [0.0, 0.0, 0.0], [None, None, None]
    for axis in range(3):
        values, ordered = index[axis]
        best = None
        for point in points:
            i = bisect_left(values, point[axis])
            for j in (i - 1, i):
                if 0 <= j < len(values):
                    gap = values[j] - point[axis]
                    if abs(gap) < tolerance and (best is None or abs(gap) < abs(best[0])):
                        best = (gap, ordered[j], point)
        if best is not None:
            shift[axis], picks[axis] = best[0], best
    moved = lambda p: tuple(p[axis] + shift[axis] for axis in range(3))
    if all(p is not None for p in picks) and picks[0][1] == picks[1][1] == picks[2][1] and picks[0][2] == picks[1][2] == picks[2][2]:
        anchor = tuple(picks[0][1])
        return tuple(shift), [Guide("point", -1, anchor, anchor)]
    guides = [Guide("axis", axis, tuple(p[1]), moved(p[2])) for axis, p in enumerate(picks) if p is not None]
    return tuple(shift), guides


OFF_AXIS = 3                         # the `axis` of a guide along a direction of a face that is no axis of the document


def flatten(anchors, to_local):
    """The anchors seen on a plane: each one in the coordinates `to_local` gives, as (x, y, 0), a position once."""
    seen, flat = set(), []
    for anchor in anchors:
        x, y, _ = to_local(anchor)
        key = (round(x, 4), round(y, 4))
        if key not in seen:
            seen.add(key)
            flat.append((x, y, 0.0))
    return flat


def align_plane(raw, grid_point, flat, tolerance, to_world, world_axes):
    """`align` for a point that moves on a plane. `raw` and `grid_point` are (x, y) on the plane, `flat` the anchors of `flatten`;
    returns ((x, y), guides) with the guides in the document (`to_world` of the plane) and `world_axes` giving for the x and the y of
    the plane the axis of the document it runs along (or `OFF_AXIS`), which sets the colour of the guide."""
    point, found = align((raw[0], raw[1], 0.0), (grid_point[0], grid_point[1], 0.0), flat, tolerance, axes=(0, 1))
    guides = [Guide(g.kind, g.axis if g.kind == "point" else world_axes[g.axis], tuple(to_world(g.anchor)), tuple(to_world(g.point)))
              for g in found]
    return (point[0], point[1]), guides
