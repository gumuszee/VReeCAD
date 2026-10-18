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
"""The Block feature: a solid made of points (docs/ux-design.md, Points tool).

A block is a `Part::FeaturePython` whose proxy is `Block`. Its parameters are the property `Vertices` (a vector list, the points in the
placement of the object) and the property `Faces` (a string list, one string of vertex indices such as "0 3 2 1" per face, counter-clockwise
seen from outside). Because the points are ordinary properties, each of them can carry an expression, so a point can follow a
variable; the shape is built again from them at every recompute: a flat face is a face, a face that is not flat is built from
triangles, the faces are sewn and made a solid (`cad/blockgeom.py` holds the geometry that needs no FreeCAD).

`pick`, `display` and `handles` find and draw the points and edges of the blocks of a document for the Points tool; `apply` changes
the points or the faces of a block and takes the change back when the block cannot be built. A document with blocks needs this addon
to recompute them; the shape is stored with the document, so it opens and shows without.

A point that is bound to a variable carries a property of its own, `Point<i>` (a vector, made when the point is first bound): FreeCAD
applies an expression to a property but not to one element of a vector list, so `Point6.z` can be bound to `Variables.lift` and
the point takes the value of that property, whatever `Vertices` holds. `read` gives the points as they are built, `apply` refuses a
move of a component that an expression holds, and `set_picked` remembers the point that the value panels show for a block."""

import re

from freecad.VReeCAD.cad import blockgeom
from freecad.VReeCAD.cad.picking import Display, Pick
from freecad.VReeCAD.core import grab

TYPE = "VReeCAD::Block"
_POINT = re.compile(r"Point(\d+)")
_PICKED = {}                # (document name, object name) -> index of the point that the value panels show


def make_shape(vertices, faces):
    """The solid of a block; ValueError with a short text when the points and faces do not make one."""
    import FreeCAD as App
    import Part
    error = blockgeom.validate(vertices, faces)
    if error is not None:
        raise ValueError(error)
    parts = []
    for face in faces:
        points = [App.Vector(*vertices[i]) for i in face]
        if len(face) == 3 or blockgeom.is_flat([vertices[i] for i in face]):
            try:
                parts.append(Part.Face(Part.makePolygon(points + points[:1])))
                continue
            except Part.OCCError:
                pass                                        # not flat enough for FreeCAD: triangles below
        for a, b, c in blockgeom.face_triangles(vertices, face):
            triangle = [App.Vector(*vertices[i]) for i in (a, b, c)]
            parts.append(Part.Face(Part.makePolygon(triangle + triangle[:1])))
    shell = Part.Shell(parts)
    shell.sewShape()
    solid = Part.Solid(shell)
    if not solid.isValid() or solid.Volume <= 0.0:
        raise ValueError("FreeCAD cannot build that block")
    return solid


class Block:
    """The proxy of a block object."""
    Type = TYPE

    def __init__(self, obj):
        obj.addProperty("App::PropertyVectorList", "Vertices", "Block", "The points of the block, in the placement of the block")
        obj.addProperty("App::PropertyStringList", "Faces", "Block", "The faces: the indices of the points of each, counter-clockwise from outside")
        obj.Proxy = self

    def execute(self, obj):
        vertices, faces = read(obj)
        obj.Shape = make_shape(vertices, faces)

    def onDocumentRestored(self, obj):
        obj.Proxy = self

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


def is_block(obj):
    return isinstance(getattr(obj, "Proxy", None), Block)


def point_properties(obj):
    """index -> name of the `Point<i>` properties of a block (the points that can be bound)."""
    found = {}
    for name in obj.PropertiesList:
        match = _POINT.fullmatch(name)
        if match:
            found[int(match.group(1))] = name
    return found


def read(obj):
    """(vertices as tuples, faces as tuples of indices) of a block, the points as they are built (a bound point is its property). A box
    that the Points tool can turn into a block reads as the block it would become."""
    if not is_block(obj):
        return blockgeom.box((0.0, 0.0, 0.0), (obj.Length.Value, obj.Width.Value, obj.Height.Value))
    vertices = [(v.x, v.y, v.z) for v in obj.Vertices]
    for index, name in point_properties(obj).items():
        if index < len(vertices):
            value = getattr(obj, name)
            vertices[index] = (value.x, value.y, value.z)
    return vertices, blockgeom.faces_from_text(obj.Faces)


def write(obj, vertices, faces=None):
    """Set the points (and the faces when given) of a block; the shape follows at the next recompute."""
    import FreeCAD as App
    obj.Vertices = [App.Vector(*v) for v in vertices]
    for index, name in point_properties(obj).items():
        if index < len(vertices):
            setattr(obj, name, App.Vector(*vertices[index]))
    if faces is not None:
        obj.Faces = blockgeom.faces_to_text(faces)


def ensure_point(obj, index):
    """Make the property that can carry an expression for point `index`; returns its name."""
    import FreeCAD as App
    name = f"Point{index}"
    if name not in obj.PropertiesList:
        value = read(obj)[0][index]                          # before the property exists, which would read as zero
        obj.addProperty("App::PropertyVector", name, "Block points", f"Point {index} of the block, bound by expressions")
        setattr(obj, name, App.Vector(*value))
    return name


def expressions(obj):
    """(index, axis 0 to 2) -> expression of every component of a point that is bound."""
    found = {}
    for path, expression in getattr(obj, "ExpressionEngine", []):
        match = re.fullmatch(r"\.?Point(\d+)\.([xyz])", path)
        if match:
            found[(int(match.group(1)), "xyz".index(match.group(2)))] = expression
    return found


FIXED = "FixedPoints"


def is_point_fixed(obj, index):
    """Whether point `index` of the block is fixed: the Points tool does not move it."""
    return index in (getattr(obj, FIXED, None) or [])


def set_point_fixed(obj, index, value):
    """Fix or release point `index` (the caller owns the transaction); the property is made when a point is first fixed."""
    if FIXED not in obj.PropertiesList:
        obj.addProperty("App::PropertyIntegerList", FIXED, "Block points", "Points held in place: the Points tool does not move them")
    points = set(getattr(obj, FIXED) or [])
    points.add(index) if value else points.discard(index)
    setattr(obj, FIXED, sorted(points))


def renumber_fixed(obj, removed):
    """The fixed points after point `removed` was taken out of the block: the points after it are numbered one lower."""
    if FIXED in obj.PropertiesList:
        setattr(obj, FIXED, sorted(i - 1 if i > removed else i for i in obj.FixedPoints if i != removed))


def has_bound_points(obj):
    """Whether a coordinate of a point of the block is bound to an expression (the points would change their numbers if one went)."""
    return bool(expressions(obj))


def set_picked(obj, index):
    """Remember `index` as the point of the block `obj` that the value panels show (None forgets it)."""
    key = (obj.Document.Name, obj.Name)
    if index is None:
        _PICKED.pop(key, None)
    else:
        _PICKED[key] = index


def picked(obj):
    """The index of the point of the block that the value panels show, or None."""
    return _PICKED.get((obj.Document.Name, obj.Name))


def point_of_vertex(obj, sub):
    """The index of the point of the block `obj` that sits where the sub-element `sub` ("Vertex<n>", a corner of the shape that the Select
    tool selected) is, or None when `sub` is no vertex or no point lies there. The numbers of the vertices of the shape are not those
    of the points, so the point is found by its place."""
    if not (sub.startswith("Vertex") and sub[6:].isdigit()):
        return None
    try:
        corner = obj.Shape.getElement(sub).Point
    except Exception:
        return None
    best = None
    for index, point in enumerate(read(obj)[0]):
        world = _world(obj, point)
        d = ((world[0] - corner.x) ** 2 + (world[1] - corner.y) ** 2 + (world[2] - corner.z) ** 2) ** 0.5
        if d < 1e-3 and (best is None or d < best[0]):
            best = (d, index)
    return None if best is None else best[1]


def make(doc, vertices, faces, name="Block"):
    """Add a block object with these points and faces to `doc` (the caller owns the transaction); returns it."""
    obj = doc.addObject("Part::FeaturePython", name)
    Block(obj)
    write(obj, vertices, faces)
    if getattr(obj, "ViewObject", None) is not None:
        obj.ViewObject.Proxy = 0                            # the default view provider draws the shape
    return obj


def create(doc, lo, size):
    """Make a block shaped like the box with lowest corner `lo` and edge lengths `size` inside one transaction (one undo step)."""
    vertices, faces = blockgeom.box(lo, size)
    doc.openTransaction("Create Block")
    try:
        obj = make(doc, vertices, faces)
        doc.recompute()
        if not obj.isValid() or obj.Shape.isNull() or obj.Shape.Volume <= 0.0:
            raise ValueError(f"FreeCAD could not make a block of {tuple(size)}")
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    return obj


def editable_box(obj):
    """Whether `obj` is a box that the Points tool can turn into a block: nothing else uses it and its sizes are no expressions."""
    return (getattr(obj, "TypeId", "") == "Part::Box" and not obj.InList and not obj.ExpressionEngine
            and getattr(obj, "Visibility", True))


def convert_box(doc, obj):
    """Replace the box `obj` by a block of the same size, label, colour and place (the caller owns the transaction, so the Points tool
    makes it one undo step with the move that follows); returns the block. The points of the block are those of `blockgeom.box`."""
    view = getattr(obj, "ViewObject", None)
    colour = tuple(view.ShapeColor)[:3] if view is not None else None
    vertices, faces = blockgeom.box((0.0, 0.0, 0.0), (obj.Length.Value, obj.Width.Value, obj.Height.Value))
    label, placement = obj.Label, obj.Placement
    selected = obj.Name
    doc.removeObject(selected)
    made = make(doc, vertices, faces)
    made.Placement = placement
    made.Label = label
    if colour is not None and getattr(made, "ViewObject", None) is not None:
        made.ViewObject.ShapeColor = colour
    doc.recompute()
    if not made.isValid() or made.Shape.isNull():
        raise ValueError("FreeCAD could not make the block")
    return made


def apply(doc, obj, vertices, faces=None):
    """Change the points (and faces) of a block and recompute. Returns None, or a short text when the block cannot be built with them,
    in which case the block is as it was."""
    new_faces = faces if faces is not None else read(obj)[1]
    error = blockgeom.validate(vertices, new_faces)
    if error is not None:
        return error
    before = read(obj)
    bound = expressions(obj)
    for index, (new, old) in enumerate(zip(vertices, before[0])):
        for axis in range(3):
            if (index, axis) in bound and abs(new[axis] - old[axis]) > 1e-9:
                from freecad.VReeCAD.core.values import pretty_expression
                return f"Point {index} is bound to {pretty_expression(bound[(index, axis)])}: unbind it first"
    write(obj, vertices, faces)
    doc.recompute()
    if not obj.isValid():
        write(obj, *before)
        doc.recompute()
        return "FreeCAD cannot build that block"
    return None


def _world(obj, point):
    import FreeCAD as App
    p = obj.Placement.multVec(App.Vector(*point))
    return (p.x, p.y, p.z)


def _local(obj, point):
    import FreeCAD as App
    p = obj.Placement.inverse().multVec(App.Vector(*point))
    return (p.x, p.y, p.z)


def to_local(obj, point):
    """A document point in the placement of a block."""
    return _local(obj, point)


def to_world(obj, point):
    """A point of a block in the document."""
    return _world(obj, point)


_VISIBLE = None


def blocks(doc):
    """The visible objects of a document that the Points tool edits, the blocks and the boxes it can turn into blocks (found again only
    for the objects that changed: `cad/changes.py`)."""
    global _VISIBLE
    if _VISIBLE is None:
        from freecad.VReeCAD.cad import changes
        _VISIBLE = changes.ObjectCache(changes.shared(), lambda o: True if (is_block(o) and getattr(o, "Visibility", True)) or editable_box(o) else None)
    return [o for o in (doc.getObject(name) for name in _VISIBLE.get(doc)) if o is not None]


def pick(doc, point, mm_per_metre, kind):
    """The point (`kind` "vertex") or the edge ("edge") of a visible block that `point` (document millimetres) touches, or None: a
    `Pick` whose `sub` is "Point<i>" or "Segment<a>-<b>". The reach is that of `core.grab` and measured on the stage."""
    best = None
    for obj in blocks(doc):
        vertices, faces = read(obj)
        local = _local(obj, point)
        if kind == "vertex":
            d, index = blockgeom.nearest_vertex(vertices, local)
            found = None if index < 0 else (d, f"Point{index}")
        else:
            nearest = blockgeom.nearest_edge(vertices, faces, local)
            found = None if nearest is None else (nearest[0], f"Segment{nearest[1][0]}-{nearest[1][1]}")
        if found is not None and grab.within_reach(kind, found[0], mm_per_metre) and (best is None or found[0] < best.distance):
            best = Pick(obj.Name, kind, found[1], found[0])
    return best


def parse_sub(sub):
    """("point", index) or ("segment", (a, b)) for a `sub` made by `pick`."""
    if sub.startswith("Point"):
        return "point", int(sub[5:])
    a, b = sub[7:].split("-")
    return "segment", (int(a), int(b))


def display(obj, sub):
    """The highlight of a picked point or edge of a block."""
    vertices, _ = read(obj)
    kind, what = parse_sub(sub)
    if kind == "point":
        return Display(markers=[_world(obj, vertices[what])])
    return Display(polylines=[[_world(obj, vertices[what[0]]), _world(obj, vertices[what[1]])]])


def handles(doc):
    """The points of every visible block as markers, so the user sees what can be moved."""
    markers = []
    for obj in blocks(doc):
        markers += [_world(obj, v) for v in read(obj)[0]]
    return Display(markers=markers)


def signature(doc):
    """Changes whenever `handles` would."""
    return tuple((o.Name, tuple(read(o)[0]), tuple(o.Placement.Base), tuple(o.Placement.Rotation.Q)) for o in blocks(doc))
