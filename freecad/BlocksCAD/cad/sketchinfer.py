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
"""Which Sketcher constraints a new shape implies (docs/ux-design.md, Sketch tool). Pure Python, no FreeCAD imports.

A new line, rectangle, circle or arc is drawn on the grid of the sketch, so the relations it has to what is there already are exact: an
end that lies on a point of the sketch is coincident with it, an end that lies on a line, a circle or an axis is on that object, a line
that runs along an axis of the sketch is horizontal or vertical. `infer_*` return constraints as tuples that `Sketcher.Constraint(*t)`
takes; the geometry that the constraints refer to gets the ids that the caller gives (`first_id` is the id of the first new
geometry). Geometry ids follow Sketcher: -1 is the horizontal axis (its start point -1, 1 is the origin) and -2 the vertical axis;
point positions are 1 (start), 2 (end) and 3 (centre).

`Existing` describes the sketch: its points `(geo id, position, (x, y))`, its lines `(geo id, start, end)`, its circles
`(geo id, centre, radius)` and its arcs `(geo id, centre, radius, start angle, end angle)` (counter-clockwise, radians). At most one constraint is made per new point, so nothing is redundant."""

import math
from dataclasses import dataclass, field
from typing import List, Tuple

TOLERANCE = 1e-6          # millimetres: a point this close to an element lies on it
H_AXIS, V_AXIS = -1, -2


@dataclass
class Existing:
    points: List[Tuple[int, int, Tuple[float, float]]] = field(default_factory=list)
    lines: List[Tuple[int, Tuple[float, float], Tuple[float, float]]] = field(default_factory=list)
    circles: List[Tuple[int, Tuple[float, float], float]] = field(default_factory=list)
    arcs: List[Tuple[int, Tuple[float, float], float, float, float]] = field(default_factory=list)


def _near(a, b, tolerance=TOLERANCE):
    return abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance


def _on_segment(p, a, b, tolerance=TOLERANCE):
    """Whether `p` lies on the segment from `a` to `b` strictly between its ends."""
    ab = (b[0] - a[0], b[1] - a[1])
    length2 = ab[0] ** 2 + ab[1] ** 2
    if length2 == 0:
        return False
    t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / length2
    if t <= 0 or t >= 1:
        return False
    nearest = (a[0] + ab[0] * t, a[1] + ab[1] * t)
    return math.dist(p, nearest) <= tolerance


def point_relation(new_id, position, point, existing, allow_axes=True):
    """The constraint that ties the point `position` (1, 2 or 3) of the new geometry `new_id` at `point` to what is there, or None:
    coincident with a point (the origin included), else on a line or a circle, else on an axis."""
    if _near(point, (0.0, 0.0)):
        return ("Coincident", new_id, position, H_AXIS, 1)
    for geo, pos, at in existing.points:
        if geo != new_id and _near(point, at):
            return ("Coincident", new_id, position, geo, pos)
    for geo, a, b in existing.lines:
        if geo != new_id and _on_segment(point, a, b):
            return ("PointOnObject", new_id, position, geo)
    for geo, centre, radius in existing.circles:
        if geo != new_id and abs(math.dist(point, centre) - radius) <= TOLERANCE:
            return ("PointOnObject", new_id, position, geo)
    if allow_axes:
        if abs(point[1]) <= TOLERANCE:
            return ("PointOnObject", new_id, position, H_AXIS)
        if abs(point[0]) <= TOLERANCE:
            return ("PointOnObject", new_id, position, V_AXIS)
    return None


def direction(p0, p1):
    """"horizontal", "vertical" or None for a line from `p0` to `p1` (along an axis of the sketch)."""
    if abs(p1[1] - p0[1]) <= TOLERANCE and abs(p1[0] - p0[0]) > TOLERANCE:
        return "horizontal"
    if abs(p1[0] - p0[0]) <= TOLERANCE and abs(p1[1] - p0[1]) > TOLERANCE:
        return "vertical"
    return None


def infer_line(new_id, p0, p1, existing):
    """The constraints of a new line from `p0` to `p1`: horizontal or vertical when it runs along an axis, and its ends tied to what
    they touch. An end on an axis is not tied to it when the line runs along that direction already (that would be redundant)."""
    constraints = []
    along = direction(p0, p1)
    if along is not None:
        constraints.append(("Horizontal" if along == "horizontal" else "Vertical", new_id))
    start = point_relation(new_id, 1, p0, existing)
    if start is not None:
        constraints.append(start)
    end = point_relation(new_id, 2, p1, existing, allow_axes=along is None)
    if end is not None and not (start is not None and start[0] == "Coincident" and end[0] == "Coincident" and start[3:] == end[3:]):
        constraints.append(end)
    return constraints


def infer_circle(new_id, centre, radius, existing):
    """The constraints of a new circle: its centre tied to what it touches."""
    relation = point_relation(new_id, 3, centre, existing)
    return [relation] if relation is not None else []


def arc_through(start, end, middle):
    """The counter-clockwise arc from `start` to `end` that passes through `middle`, as (centre, radius, first angle, last angle, first
    point, last point) (the points are `start` and `end`, swapped when the arc runs from `end` to `start`), or None when the three
    points lie on a line (or two of them are one)."""
    (ax, ay), (bx, by), (cx, cy) = start, middle, end
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    centre = ((a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d, (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d)
    radius = math.dist(centre, start)
    angle = [math.atan2(p[1] - centre[1], p[0] - centre[0]) for p in (start, middle, end)]
    tau = 2.0 * math.pi
    if (angle[1] - angle[0]) % tau <= (angle[2] - angle[0]) % tau:
        first, last, p_first, p_last = angle[0], angle[2], start, end
    else:
        first, last, p_first, p_last = angle[2], angle[0], end, start
    while last <= first:
        last += tau
    return centre, radius, first, last, p_first, p_last


def arc_points(centre, radius, first, last, count=48):
    """Points along the arc from the angle `first` to `last` (radians), `count` + 1 of them."""
    return [(centre[0] + radius * math.cos(first + (last - first) * i / count), centre[1] + radius * math.sin(first + (last - first) * i / count))
            for i in range(count + 1)]


def infer_arc(new_id, p_first, p_last, existing):
    """The constraints of a new arc whose first and last point are `p_first` and `p_last`: each end tied to what it touches."""
    constraints = []
    first = point_relation(new_id, 1, p_first, existing)
    if first is not None:
        constraints.append(first)
    last = point_relation(new_id, 2, p_last, existing)
    if last is not None and not (first is not None and first[0] == "Coincident" and last[0] == "Coincident" and first[3:] == last[3:]):
        constraints.append(last)
    return constraints


def rectangle(c0, c2):
    """The four corners, counter-clockwise, of the axis-aligned rectangle between the opposite corners `c0` and `c2`."""
    (x0, y0), (x2, y2) = c0, c2
    return [(min(x0, x2), min(y0, y2)), (max(x0, x2), min(y0, y2)), (max(x0, x2), max(y0, y2)), (min(x0, x2), max(y0, y2))]


def infer_rectangle(first_id, c0, c2, existing):
    """(corners, constraints) of a rectangle drawn from corner `c0` to the opposite corner `c2`: four lines with ids `first_id` to
    `first_id + 3` that run from corner to corner, joined end to start, two horizontal and two vertical, and the lower left and the upper
    right corner tied to what they touch."""
    corners = rectangle(c0, c2)
    constraints = [("Coincident", first_id + i, 2, first_id + (i + 1) % 4, 1) for i in range(4)]
    constraints += [("Horizontal", first_id), ("Horizontal", first_id + 2), ("Vertical", first_id + 1), ("Vertical", first_id + 3)]
    for corner, geo, position in ((corners[0], first_id, 1), (corners[2], first_id + 1, 2)):
        relation = point_relation(geo, position, corner, existing)
        if relation is not None:
            constraints.append(relation)
    return corners, constraints


def length_name(taken, base="length"):
    """A name for a new dimension that is not in `taken`: "length", "length2", ..."""
    name, number = base, 1
    while name in taken:
        number += 1
        name = f"{base}{number}"
    return name
