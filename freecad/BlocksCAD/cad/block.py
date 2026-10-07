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
to recompute them; the shape is stored with the document, so it opens and shows without."""

from freecad.BlocksCAD.cad import blockgeom
from freecad.BlocksCAD.cad.picking import Display, Pick
from freecad.BlocksCAD.core import grab

TYPE = "BlocksCAD::Block"


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


def read(obj):
    """(vertices as tuples, faces as tuples of indices) of a block."""
    return [(v.x, v.y, v.z) for v in obj.Vertices], blockgeom.faces_from_text(obj.Faces)


def write(obj, vertices, faces=None):
    """Set the points (and the faces when given) of a block; the shape follows at the next recompute."""
    import FreeCAD as App
    obj.Vertices = [App.Vector(*v) for v in vertices]
    if faces is not None:
        obj.Faces = blockgeom.faces_to_text(faces)


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


def apply(doc, obj, vertices, faces=None):
    """Change the points (and faces) of a block and recompute. Returns None, or a short text when the block cannot be built with them,
    in which case the block is as it was."""
    new_faces = faces if faces is not None else read(obj)[1]
    error = blockgeom.validate(vertices, new_faces)
    if error is not None:
        return error
    before = read(obj)
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


def blocks(doc):
    """The visible block objects of a document."""
    return [o for o in doc.Objects if is_block(o) and getattr(o, "Visibility", True)]


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
    return tuple((o.Name, tuple((v.x, v.y, v.z) for v in o.Vertices), tuple(o.Placement.Base), tuple(o.Placement.Rotation.Q)) for o in blocks(doc))
