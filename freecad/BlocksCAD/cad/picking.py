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
"""What the hand touches in a document, how to draw it, and the selection (docs/ux-design.md, Move tool).

`pick` finds the vertex, edge, face or solid that a point in document millimetres touches: it is the nearest element within the
reach of `core.grab.classify`, so a corner wins over the edge it lies on and an edge over its face. `display` builds the geometry
of a pick or of a selected element for the highlight overlay. The selection is FreeCAD's own selection, so what is selected in VR is
selected on the desktop and the other way round. FreeCAD is imported inside the functions."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from freecad.BlocksCAD.core import grab

PRIORITY = {"vertex": 0, "edge": 1, "face": 2, "object": 3}
MAX_EDGES = 400            # an object outline stops at this many edges
EDGE_POINTS = 32           # points per discretised edge


@dataclass
class Pick:
    name: str          # name of the object
    kind: str          # "vertex", "edge", "face" or "object"
    sub: str           # sub-element name ("Face3"), empty for the object
    distance: float    # millimetres from the point to the element (0 inside a solid)


@dataclass
class Display:
    """Geometry for the highlight overlay, in document millimetres."""
    triangles: Tuple[List, List] = field(default_factory=lambda: ([], []))    # (points, triangles) of a filled face
    polylines: List[List] = field(default_factory=list)
    markers: List[Tuple[float, float, float]] = field(default_factory=list)


def kind_of(sub):
    """"vertex", "edge", "face" or "object" for a sub-element name."""
    for prefix, kind in (("Vertex", "vertex"), ("Edge", "edge"), ("Face", "face")):
        if sub.startswith(prefix):
            return kind
    return "object"


def _nearest(items, distance):
    best, index = None, -1
    for i, item in enumerate(items):
        d = distance(item)
        if best is None or d < best:
            best, index = d, i
    return best, index


def pick(doc, point, mm_per_metre, kind=None) -> Optional[Pick]:
    """The element of the visible objects of `doc` that `point` (document millimetres) touches, or None.

    Without `kind` it is the nearest of any sort. With `kind` "vertex", "edge" or "face" it is the nearest element of that sort within
    its reach, however close another sort is; with "object" it is the object that any element of it touches (a `Pick` of kind "object")."""
    import FreeCAD as App
    import Part
    p = App.Vector(*point)
    marker = Part.Vertex(p)
    reach = grab.REACH["face"] * mm_per_metre
    best = None
    for obj in doc.Objects:
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull() or not getattr(obj, "Visibility", True) or not (shape.Faces or shape.Edges):
            continue
        box = App.BoundBox(shape.BoundBox)
        if not box.isValid():
            continue
        box.enlarge(reach)
        if not box.isInside(p):
            continue
        if kind in ("vertex", "edge", "face"):
            items, distance = {"vertex": (shape.Vertexes, lambda v: (v.Point - p).Length),
                               "edge": (shape.Edges, lambda e: e.distToShape(marker)[0]),
                               "face": (shape.Faces, lambda f: f.distToShape(marker)[0])}[kind]
            d, index = _nearest(items, distance)
            if grab.within_reach(kind, d, mm_per_metre) and (best is None or d < best.distance):
                best = Pick(obj.Name, kind, f"{kind.capitalize()}{index + 1}", d)
            continue
        d_vertex, vertex = _nearest(shape.Vertexes, lambda v: (v.Point - p).Length)
        d_edge, edge = _nearest(shape.Edges, lambda e: e.distToShape(marker)[0])
        d_face, face = _nearest(shape.Faces, lambda f: f.distToShape(marker)[0])
        try:
            inside = bool(shape.Solids) and shape.isInside(p, 1e-6, True)
        except Exception:
            inside = False
        found = grab.classify(d_vertex, d_edge, d_face, inside, mm_per_metre)
        if found is None:
            continue
        sub, distance = {"vertex": (f"Vertex{vertex + 1}", d_vertex), "edge": (f"Edge{edge + 1}", d_edge),
                         "face": (f"Face{face + 1}", d_face), "object": ("", 0.0)}[found]
        candidate = Pick(obj.Name, found, sub, distance)
        if best is None or (PRIORITY[found], distance) < (PRIORITY[best.kind], best.distance):
            best = candidate
    if best is not None and kind == "object":
        return Pick(best.name, "object", "", best.distance)
    return best


def display(obj, sub="") -> Display:
    """The geometry that shows a sub-element of an object, or the whole object (an empty `sub`): the vertex as a marker, an edge as
    a curve, a face filled with its boundary, an object filled all over with all its edges."""
    shape = obj.Shape
    kind = kind_of(sub)
    if kind == "vertex":
        point = shape.getElement(sub).Point
        return Display(markers=[(point.x, point.y, point.z)])
    if kind == "edge":
        return Display(polylines=[_curve(shape.getElement(sub))])
    if kind == "face":
        face = shape.getElement(sub)
        box = shape.BoundBox
        points, triangles = face.tessellate(max(box.DiagonalLength / 150.0, 0.02))
        return Display(triangles=([(v.x, v.y, v.z) for v in points], [tuple(t) for t in triangles]),
                       polylines=[_curve(e) for e in face.Edges[:MAX_EDGES]])
    points, triangles = shape.tessellate(max(shape.BoundBox.DiagonalLength / 150.0, 0.02))
    return Display(triangles=([(v.x, v.y, v.z) for v in points], [tuple(t) for t in triangles]),
                   polylines=[_curve(e) for e in shape.Edges[:MAX_EDGES]])


def _curve(edge):
    return [(v.x, v.y, v.z) for v in edge.discretize(Number=EDGE_POINTS)]


def signature(obj, sub=""):
    """Changes whenever what `display(obj, sub)` shows changes."""
    return (obj.Name, sub, obj.Shape.hashCode())


# the selection: FreeCAD's own
def get_selection(doc) -> List[Tuple[str, str]]:
    """(object name, sub-element name) of everything selected in `doc`; an object selected as a whole has an empty sub-element name."""
    import FreeCADGui as Gui
    items = []
    for selected in Gui.Selection.getSelectionEx(doc.Name):
        for sub in selected.SubElementNames or ("",):
            items.append((selected.ObjectName, sub))
    return items


def set_selection(doc, items):
    import FreeCADGui as Gui
    Gui.Selection.clearSelection()
    for name, sub in items:
        Gui.Selection.addSelection(doc.Name, name, sub)


def clear_selection():
    import FreeCADGui as Gui
    Gui.Selection.clearSelection()
