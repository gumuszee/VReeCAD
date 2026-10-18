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
"""Sketches made in space (docs/ux-design.md, Sketch tool): real `Sketcher::SketchObject`s with real constraints.

A sketch lies on a plane of the document (XY, XZ or YZ, at the height of the cursor) or is attached to a flat face of a solid (map
mode FlatFace), so it follows that face. Lines, rectangles and circles are added with the constraints that they imply to what is
there (`cad/sketchinfer.py`); if the solver does not accept them (it reports redundant or conflicting constraints) the shape is kept
with fewer constraints rather than lost. A point is dragged by moving it and letting the solver find the nearest sketch that keeps
the constraints; a dimension is a named driving constraint (`length`, `radius`) whose value the value panels edit and bind.
`extrude` makes a `Part::Extrusion` of a sketch. Points are given in document millimetres when they are world points and in the
coordinates of the sketch when they are local. FreeCAD is imported inside the functions that need it."""

import math

from freecad.VReeCAD.cad import sketchinfer
from freecad.VReeCAD.cad.picking import Display, Pick
from freecad.VReeCAD.core import grab
from freecad.VReeCAD.core import mathutil as mu

TYPE = "Sketcher::SketchObject"
PLANES = ("XY", "XZ", "YZ")
# rotation of the sketch (x, y, z, w) and the normal of its plane, per plane
PLANE_ROTATION = {"XY": (0.0, 0.0, 0.0, 1.0), "XZ": (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)), "YZ": (0.5, 0.5, 0.5, 0.5)}
LENGTH_DIMENSIONS = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter")
CIRCLE_POINTS = 64
EXTRUDE_LENGTH = 20.0       # millimetres: how far a sketch is extruded at first (the length is a value of the new solid)


def plane_normal(plane):
    """The unit normal of a sketch plane in the document."""
    return mu.rotate(PLANE_ROTATION[plane], (0.0, 0.0, 1.0))


def is_sketch(obj):
    return obj is not None and getattr(obj, "TypeId", "") == TYPE


def current_sketch(doc, items):
    """The first sketch among the selected `items` ((object name, sub-element name) pairs), or None."""
    for name, _ in items:
        obj = doc.getObject(name)
        if is_sketch(obj):
            return obj
    return None


# frames
def placement(sketch):
    """(base, rotation x, y, z, w) of a sketch in the document."""
    p = sketch.Placement
    q = p.Rotation.Q
    return tuple(p.Base), (q[0], q[1], q[2], q[3])


def frame_to_local(frame, point):
    """A document point in the coordinates of `frame` ((base, rotation) as `placement` gives them)."""
    base, rotation = frame
    return mu.rotate(mu.quat_conjugate(rotation), mu.sub(point, base))


def frame_to_world(frame, point):
    """A point of `frame` in the document."""
    base, rotation = frame
    return mu.add(base, mu.rotate(rotation, point))


def to_local(sketch, point):
    """A document point in the coordinates of a sketch (x and y on the plane, z off it)."""
    return frame_to_local(placement(sketch), point)


def to_world(sketch, point):
    """A point of a sketch (x, y, z) in the document."""
    return frame_to_world(placement(sketch), point)


def plane_frame(plane, point, grid):
    """The frame of a new sketch on `plane` at the height of `point` (document millimetres) along the normal, rounded to the grid."""
    normal = plane_normal(plane)
    height = round(mu.dot(point, normal) / grid) * grid
    return mu.mul(normal, height), PLANE_ROTATION[plane]


def world_axes(frame):
    """For the x and the y of `frame` the axis of the document (0, 1 or 2) it runs along, or 3 when it runs along none."""
    axes = []
    for unit in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)):
        direction = mu.rotate(frame[1], unit)
        axes.append(next((i for i in range(3) if abs(direction[i]) > 0.999), 3))
    return tuple(axes)


def own_points(sketch, apart_from=None):
    """The points of the geometry of a sketch as (x, y, 0), except those at the position of the point `apart_from` ((geometry id,
    position id)): a point that is dragged does not line up with itself or with the points that move with it."""
    found = existing(sketch)
    skip = next((at for geo, pos, at in found.points if (geo, pos) == apart_from), None)
    return [(at[0], at[1], 0.0) for _, _, at in found.points if skip is None or math.dist(at, skip) > 1e-6]


# making sketches
def create_on_plane(doc, plane, point, grid):
    """A sketch on `plane` at the height of `point` (document millimetres) along the normal, rounded to the grid."""
    import FreeCAD as App
    base, rotation = plane_frame(plane, point, grid)
    sketch = doc.addObject(TYPE, "Sketch")
    sketch.Placement = App.Placement(App.Vector(*base), App.Rotation(*rotation))
    return sketch


def create_on_face(doc, obj, sub):
    """A sketch attached to the flat face `sub` of `obj`, so it follows the face."""
    sketch = doc.addObject(TYPE, "Sketch")
    sketch.AttachmentSupport = [(obj, sub)]
    sketch.MapMode = "FlatFace"
    doc.recompute()
    return sketch


def pick_face(doc, point, mm_per_metre):
    """The flat face of a solid that `point` touches, as a `Pick`, or None: a sketch can be attached to it."""
    from freecad.VReeCAD.cad import picking, pushpull
    found = picking.pick(doc, point, mm_per_metre, "face")
    if found is None:
        return None
    obj = doc.getObject(found.name)
    if obj is None or is_sketch(obj) or pushpull.face_info(obj, found.sub) is None:
        return None
    return found


# the geometry of a sketch
def existing(sketch):
    """`sketchinfer.Existing` of the geometry of a sketch (construction geometry and external geometry are left out)."""
    found = sketchinfer.Existing()
    for geo, g in enumerate(sketch.Geometry):
        if sketch.getConstruction(geo):
            continue
        kind = g.TypeId
        if kind == "Part::GeomLineSegment":
            start, end = (g.StartPoint.x, g.StartPoint.y), (g.EndPoint.x, g.EndPoint.y)
            found.points += [(geo, 1, start), (geo, 2, end)]
            found.lines.append((geo, start, end))
        elif kind == "Part::GeomCircle":
            centre = (g.Center.x, g.Center.y)
            found.points.append((geo, 3, centre))
            found.circles.append((geo, centre, g.Radius))
        elif kind == "Part::GeomArcOfCircle":
            found.points += [(geo, 1, (g.StartPoint.x, g.StartPoint.y)), (geo, 2, (g.EndPoint.x, g.EndPoint.y)),
                             (geo, 3, (g.Center.x, g.Center.y))]
            found.arcs.append((geo, (g.Center.x, g.Center.y), g.Radius, g.FirstParameter, g.LastParameter))
    return found


def lines(sketch):
    """Every line of a sketch as (start, end) in sketch coordinates."""
    return [(a, b) for _, a, b in existing(sketch).lines]


def slanted_lines(sketch):
    """The lines of a sketch that run along neither axis of it, as (start, end) in sketch coordinates."""
    return [(a, b) for _, a, b in existing(sketch).lines if sketchinfer.direction(a, b) is None]


def _constraint(spec):
    import Sketcher
    return Sketcher.Constraint(*spec)


def solved(sketch):
    """Whether the solver accepts the constraints of a sketch (no conflict, nothing redundant)."""
    return sketch.solve() == 0


def _constrain(doc, sketch, essential, optional):
    """Add the constraints that make a shape what it is, then the inferred ones that tie it to the rest; the inferred ones are dropped
    one group at a time when the solver does not accept them. Returns the number of constraints kept."""
    first = len(sketch.Constraints)
    for specs in (essential + optional, essential, []):
        if specs:
            sketch.addConstraint([_constraint(s) for s in specs])
        if solved(sketch):
            return len(specs)
        for index in range(len(sketch.Constraints) - 1, first - 1, -1):
            sketch.delConstraint(index)
    return 0


def add_line(doc, sketch, p0, p1):
    """Add a line from `p0` to `p1` (sketch coordinates) with the constraints that it implies; returns (geometry id, constraints kept)."""
    import FreeCAD as App
    import Part
    found = existing(sketch)
    geo = sketch.addGeometry(Part.LineSegment(App.Vector(p0[0], p0[1], 0), App.Vector(p1[0], p1[1], 0)), False)
    wanted = sketchinfer.infer_line(geo, p0, p1, found)
    along = [c for c in wanted if c[0] in ("Horizontal", "Vertical")]
    return geo, _constrain(doc, sketch, along, [c for c in wanted if c not in along])


def add_rectangle(doc, sketch, c0, c2):
    """Add a rectangle between the opposite corners `c0` and `c2`: four lines, joined, horizontal and vertical, and tied to what the
    corners touch; returns (id of the first line, constraints kept)."""
    import FreeCAD as App
    import Part
    found = existing(sketch)
    first = len(sketch.Geometry)
    corners, wanted = sketchinfer.infer_rectangle(first, c0, c2, found)
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        sketch.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), False)
    shape = [c for c in wanted if c[0] in ("Horizontal", "Vertical") or (c[0] == "Coincident" and c[3] >= first)]
    ties = [c for c in wanted if c not in shape]
    return first, _constrain(doc, sketch, shape, ties)


def add_circle(doc, sketch, centre, radius):
    """Add a circle (sketch coordinates) with its centre tied to what it touches; returns (geometry id, constraints kept)."""
    import FreeCAD as App
    import Part
    found = existing(sketch)
    geo = sketch.addGeometry(Part.Circle(App.Vector(centre[0], centre[1], 0), App.Vector(0, 0, 1), radius), False)
    return geo, _constrain(doc, sketch, [], sketchinfer.infer_circle(geo, centre, radius, found))


def add_arc(doc, sketch, start, end, middle):
    """Add the arc from `start` to `end` through `middle` (sketch coordinates) with its ends tied to what they touch; returns (geometry
    id, constraints kept) or raises ValueError when the three points lie on a line."""
    import FreeCAD as App
    import Part
    arc = sketchinfer.arc_through(start, end, middle)
    if arc is None:
        raise ValueError("the three points lie on a line")
    centre, radius, first, last, p_first, p_last = arc
    found = existing(sketch)
    circle = Part.Circle(App.Vector(centre[0], centre[1], 0), App.Vector(0, 0, 1), radius)
    geo = sketch.addGeometry(Part.ArcOfCircle(circle, first, last), False)
    return geo, _constrain(doc, sketch, [], sketchinfer.infer_arc(geo, centre, p_first, p_last, found))


def outline(kind, a, b, sketch=None, c=None):
    """A preview of a shape in sketch coordinates as polylines of (x, y, 0): a line from `a` to `b` (also an arc whose third point `c`
    is not given yet or lies on the line), the rectangle between them, the circle with centre `a` through `b`, or the arc from `a` to
    `b` through `c`."""
    if kind == "Arc" and c is not None:
        arc = sketchinfer.arc_through(a, b, c)
        if arc is not None:
            return [[(x, y, 0.0) for x, y in sketchinfer.arc_points(*arc[:4])]]
    if kind in ("Line", "Arc"):
        return [[(a[0], a[1], 0.0), (b[0], b[1], 0.0)]]
    if kind == "Rectangle":
        corners = sketchinfer.rectangle(a, b)
        return [[(x, y, 0.0) for x, y in corners + corners[:1]]]
    radius = math.dist(a, b)
    return [[(a[0] + radius * math.cos(2 * math.pi * i / CIRCLE_POINTS), a[1] + radius * math.sin(2 * math.pi * i / CIRCLE_POINTS), 0.0)
             for i in range(CIRCLE_POINTS + 1)]]


# dimensions
def dimensions(sketch):
    """(constraint index, name, kind, millimetres) of every named driving length of a sketch."""
    found = []
    for index, c in enumerate(sketch.Constraints):
        if c.Name and not c.Name.startswith("lock") and c.Driving and c.Type in LENGTH_DIMENSIONS:
            found.append((index, c.Name, c.Type, float(c.Value)))
    return found


def curve_kind(sketch, geo):
    """"line", "circle" (a circle or an arc: it has a radius) or "other" for the geometry `geo` of a sketch."""
    type_id = sketch.Geometry[geo].TypeId
    if type_id == "Part::GeomLineSegment":
        return "line"
    return "circle" if type_id in ("Part::GeomCircle", "Part::GeomArcOfCircle") else "other"


def radius_dimension(sketch, geo):
    """The index of the driving radius dimension of the circle or arc `geo`, or None when it has none."""
    for index, c in enumerate(sketch.Constraints):
        if c.First == geo and c.Type == "Radius" and c.Driving:
            return index
    return None


def centre_of(sketch, geo):
    """The centre (x, y) of the circle or arc `geo` in sketch coordinates."""
    centre = sketch.Geometry[geo].Center
    return (centre.x, centre.y)


def dimension_value(sketch, index):
    """The value in millimetres of the dimension `index`."""
    return float(sketch.Constraints[index].Value)


def dimension(doc, sketch, geo):
    """Give the line or the circle `geo` a named length or radius that is its present size. Returns (text for a toast, name or None)."""
    g = sketch.Geometry[geo]
    for c in sketch.Constraints:
        if c.First == geo and c.Type in ("Distance", "Radius", "Diameter") and c.Driving:
            return "That is dimensioned already", None
    taken = {c.Name for c in sketch.Constraints if c.Name}
    if g.TypeId == "Part::GeomLineSegment":
        spec, base, label = ("Distance", geo, float((g.EndPoint - g.StartPoint).Length)), "length", "length"
    elif g.TypeId in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
        spec, base, label = ("Radius", geo, float(g.Radius)), "radius", "radius"
    else:
        return "Only lines, circles and arcs can be dimensioned", None
    name = sketchinfer.length_name(taken, base)
    index = sketch.addConstraint(_constraint(spec))
    sketch.renameConstraint(index, name)
    if not solved(sketch):
        sketch.delConstraint(index)
        sketch.solve()
        return "The sketch is fixed there already", None
    return f"Dimension {name} = {spec[2]:g} mm", name


def set_dimension(sketch, index, value):
    """Give the dimension `index` the length `value` millimetres; returns None, or a short text when the solver does not accept it (the
    old value is put back)."""
    import FreeCAD as App
    before = float(sketch.Constraints[index].Value)
    try:
        sketch.setDatum(index, App.Units.Quantity(f"{value:.12g} mm"))
        if solved(sketch):
            return None
    except ValueError:                  # FreeCAD refuses a negative length by itself
        return "The sketch cannot take that value"
    sketch.setDatum(index, App.Units.Quantity(f"{before:.12g} mm"))
    sketch.solve()
    return "The sketch cannot take that value"


# points and curves for the tool
_VISIBLE = None


def sketches(doc):
    """The visible sketches of a document (found again only for the objects that changed: `cad/changes.py`)."""
    global _VISIBLE
    if _VISIBLE is None:
        from freecad.VReeCAD.cad import changes
        _VISIBLE = changes.ObjectCache(changes.shared(), lambda o: True if is_sketch(o) and getattr(o, "Visibility", True) else None)
    return [o for o in (doc.getObject(name) for name in _VISIBLE.get(doc)) if o is not None]


def _points(sketch):
    return existing(sketch).points


def handles(doc):
    """The points of every visible sketch as markers."""
    return Display(markers=[to_world(s, (x, y, 0.0)) for s in sketches(doc) for _, _, (x, y) in _points(s)])


def signature(doc):
    """Changes whenever `handles` would."""
    return tuple((s.Name, tuple(p[2] for p in _points(s)), placement(s)) for s in sketches(doc))


def pick(doc, point, mm_per_metre, kind):
    """The point ("vertex": sub "Point<geo>.<pos>") or the line or circle ("edge": sub "Curve<geo>") of a visible sketch that `point`
    (document millimetres) touches, or None; the reach is that of `core.grab`."""
    best = None
    for sketch in sketches(doc):
        local = to_local(sketch, point)
        if kind == "vertex":
            found = [(math.dist(local, (x, y, 0.0)), f"Point{geo}.{pos}") for geo, pos, (x, y) in _points(sketch)]
        else:
            found = []
            current = existing(sketch)
            for geo, a, b in current.lines:
                found.append((_distance_to_segment(local, a, b), f"Curve{geo}"))
            for geo, centre, radius in current.circles:
                found.append((_distance_to_circle(local, centre, radius), f"Curve{geo}"))
            for geo, centre, radius, first, last in current.arcs:
                found.append((_distance_to_arc(local, centre, radius, first, last), f"Curve{geo}"))
        for distance, sub in found:
            if grab.within_reach(kind, distance, mm_per_metre) and (best is None or distance < best.distance):
                best = Pick(sketch.Name, kind, sub, distance)
    return best


def _distance_to_segment(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1], 0.0)
    length2 = ab[0] ** 2 + ab[1] ** 2
    t = 0.0 if length2 == 0 else min(max(((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / length2, 0.0), 1.0)
    return math.dist(p, (a[0] + ab[0] * t, a[1] + ab[1] * t, 0.0))


def _distance_to_circle(p, centre, radius):
    """Distance from `p` to the circle; the point's height above the plane counts."""
    flat = math.hypot(p[0] - centre[0], p[1] - centre[1])
    return math.hypot(abs(flat - radius), p[2])


def _distance_to_arc(p, centre, radius, first, last):
    """Distance from `p` to the arc (counter-clockwise from the angle `first` to `last`): to the circle where the point lies within
    the angles of the arc, else to the nearer end; the point's height above the plane counts."""
    angle = math.atan2(p[1] - centre[1], p[0] - centre[0])
    tau = 2.0 * math.pi
    if (angle - first) % tau <= (last - first) % tau:
        return _distance_to_circle(p, centre, radius)
    return min(math.dist(p, (centre[0] + radius * math.cos(a), centre[1] + radius * math.sin(a), 0.0)) for a in (first, last))


def parse_sub(sub):
    """("point", geo, position) or ("curve", geo, None) for a `sub` made by `pick`."""
    if sub.startswith("Point"):
        geo, pos = sub[5:].split(".")
        return "point", int(geo), int(pos)
    return "curve", int(sub[5:]), None


def display(sketch, sub):
    """The highlight of a picked point or curve."""
    kind, geo, pos = parse_sub(sub)
    current = existing(sketch)
    if kind == "point":
        for g, p, (x, y) in current.points:
            if (g, p) == (geo, pos):
                return Display(markers=[to_world(sketch, (x, y, 0.0))])
        return Display()
    polylines = []
    for g, a, b in current.lines:
        if g == geo:
            polylines.append([to_world(sketch, (a[0], a[1], 0.0)), to_world(sketch, (b[0], b[1], 0.0))])
    for g, centre, radius in current.circles:
        if g == geo:
            polylines.append([to_world(sketch, p) for p in outline("Circle", centre, (centre[0] + radius, centre[1]))[0]])
    for g, centre, radius, first, last in current.arcs:
        if g == geo:
            polylines.append([to_world(sketch, (x, y, 0.0)) for x, y in sketchinfer.arc_points(centre, radius, first, last)])
    return Display(polylines=polylines)


LOCK = "lock"                # constraints that fix a point are named lock_<geometry>_<point>_x and _y: they are no values of the panels


def point_locked(sketch, geo, pos):
    """Whether the point `pos` of the geometry `geo` is fixed by the constraints that `lock_point` makes."""
    return any(c.Name.startswith(LOCK) and c.First == geo and c.FirstPos == pos for c in sketch.Constraints)


def lock_point(doc, sketch, geo, pos):
    """Fix the point `pos` of `geo` where it is (its distances from the origin along x and y become constraints); returns whether the
    solver accepted them."""
    x, y = point_position(sketch, geo, pos)
    first = len(sketch.Constraints)
    sketch.addConstraint([_constraint(("DistanceX", geo, pos, x)), _constraint(("DistanceY", geo, pos, y))])
    sketch.renameConstraint(first, f"{LOCK}_{geo}_{pos}_x")
    sketch.renameConstraint(first + 1, f"{LOCK}_{geo}_{pos}_y")
    if solved(sketch):
        return True
    sketch.delConstraint(first + 1)
    sketch.delConstraint(first)
    sketch.solve()
    return False


def unlock_point(sketch, geo, pos):
    """Release a point that `lock_point` fixed."""
    for index in sorted((i for i, c in enumerate(sketch.Constraints) if c.Name.startswith(LOCK) and c.First == geo and c.FirstPos == pos),
                        reverse=True):
        sketch.delConstraint(index)
    sketch.solve()


def point_position(sketch, geo, pos):
    """The sketch coordinates (x, y) of point `pos` of geometry `geo`."""
    for g, p, at in existing(sketch).points:
        if (g, p) == (geo, pos):
            return at
    raise ValueError("That point is gone")


def move_point(doc, sketch, geo, pos, target):
    """Drag a point to `target` (sketch coordinates): the point is moved and the solver finds the sketch nearest to that which keeps
    the constraints, so a constrained point may stop short or not move at all. Returns None, or a short text when the sketch cannot take
    the move (it is put back)."""
    import FreeCAD as App
    now = point_position(sketch, geo, pos)
    delta = (target[0] - now[0], target[1] - now[1])
    if abs(delta[0]) < 1e-9 and abs(delta[1]) < 1e-9:
        return None
    sketch.moveGeometry(geo, pos, App.Vector(delta[0], delta[1], 0), True)
    if solved(sketch):
        return None
    sketch.moveGeometry(geo, pos, App.Vector(-delta[0], -delta[1], 0), True)
    sketch.solve()
    return "The sketch cannot take that move"


# using a sketch
def open_ends(sketch):
    """The two end points (sketch coordinates) of the one open chain of lines and arcs of a sketch, or None when it has no open end, more
    than two, or when the line between them is there already (a single line)."""
    counts = {}
    ends = []
    segments = set()
    for geometry, construction in zip(sketch.Geometry, [sketch.getConstruction(i) for i in range(len(sketch.Geometry))]):
        if construction or not (hasattr(geometry, "StartPoint") and hasattr(geometry, "EndPoint")):
            continue                                                                  # a circle is closed by itself
        a, b = (geometry.StartPoint.x, geometry.StartPoint.y), (geometry.EndPoint.x, geometry.EndPoint.y)
        for point in (a, b):
            key = (round(point[0], 6), round(point[1], 6))
            counts[key] = counts.get(key, 0) + 1
            ends.append((key, point))
        if type(geometry).__name__ == "LineSegment":                                  # an arc is not the line between its ends
            segments.add(frozenset(((round(a[0], 6), round(a[1], 6)), (round(b[0], 6), round(b[1], 6)))))
    open_keys = [key for key, n in counts.items() if n == 1]
    if len(open_keys) != 2 or frozenset(open_keys) in segments:
        return None
    return tuple(next(point for key, point in ends if key == wanted) for wanted in open_keys)


def close_outline(doc, sketch):
    """Add the line that closes the one open chain of a sketch between its ends (with the constraints that join it); returns whether one
    was added."""
    found = open_ends(sketch)
    if found is None:
        return False
    add_line(doc, sketch, found[0], found[1])
    return True


def extrude(doc, items, length):
    """Extrude each selected sketch by `length` millimetres along its normal into a solid, in one transaction. The sketch is hidden. A
    sketch whose outline is open at two ends only (an arc, a line that has not come back to its start) is closed with a line between
    them. Returns (text for a toast, names of the new objects)."""
    from freecad.VReeCAD.cad import combine
    sketches_ = []
    for name, _ in items:
        obj = doc.getObject(name)
        if is_sketch(obj) and obj not in sketches_:
            sketches_.append(obj)
    if not sketches_:
        return ("Select a sketch to extrude" if items else "Nothing selected"), []
    doc.openTransaction("Extrude " + (sketches_[0].Label if len(sketches_) == 1 else f"{len(sketches_)} sketches"))
    made = []
    closed = []
    try:
        for sketch in sketches_:
            solid = doc.addObject("Part::Extrusion", "Extrude")
            solid.Base = sketch
            solid.DirMode = "Normal"
            solid.LengthFwd = float(length)
            solid.Solid = True
            doc.recompute()
            if not combine.sound(solid) and close_outline(doc, sketch):
                closed.append(sketch)
                doc.recompute()
            if not combine.sound(solid):
                raise ValueError(f"{sketch.Label} has no closed outline")
            combine.hide(sketch)
            made.append(solid)
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"Extrude failed: {error}", []
    text = f"Extruded {sketches_[0].Label}" if len(made) == 1 else f"Extruded {len(made)} sketches"
    if closed:
        text += ", closed with a line" if len(closed) == 1 else f", {len(closed)} closed with a line"
    return text, [o.Name for o in made]
