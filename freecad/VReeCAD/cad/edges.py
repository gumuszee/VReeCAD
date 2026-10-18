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
"""Fillets and chamfers of the selected edges (docs/ux-design.md, Modify panel).

A fillet is a `Part::Fillet` and a chamfer a `Part::Chamfer`: a feature that refers to the object whose edges were selected and keeps
the edges and their size as properties, so the object stays editable and the size is a value on the value panels (`EdgeValues` in
`cad/values.py`). A size that the edges cannot take is replaced by the largest one that they can (`largest_feasible`), and the faces that
the feature adds to its source are what is selected afterwards (`new_faces`). `edge_selection`, `edge_index`, `edge_rows` and
`surface_key` are pure Python; the functions that make features work on a document and import nothing else from FreeCAD."""

import math

from freecad.VReeCAD.cad.combine import hide, sound

KINDS = ("fillet", "chamfer")
TYPES = {"fillet": "Part::Fillet", "chamfer": "Part::Chamfer"}
VERBS = {"fillet": "Fillet", "chamfer": "Chamfer"}
SIZE = 5.0                  # millimetres: the radius of a new fillet and the length of a new chamfer
UNIT = 0.1                  # millimetres: the sizes that `largest_feasible` tries are multiples of this


def edge_index(sub):
    """The number of the edge named `Edge<n>` (1 based, as FreeCAD counts them), or None for any other sub-element name."""
    if sub.startswith("Edge") and sub[4:].isdigit():
        return int(sub[4:])
    return None


def edge_selection(items):
    """The selected edges grouped by object: a list of (object name, [edge numbers]) in the order the objects were first selected,
    each edge once. Whole objects and faces do not count."""
    groups = {}
    for name, sub in items:
        index = edge_index(sub)
        if index is not None and index not in groups.setdefault(name, []):
            groups[name].append(index)
    return list(groups.items())


def edge_rows(indices, size):
    """The value of the `Edges` property of a fillet or chamfer: one (edge number, size, size) row per edge."""
    return [(index, size, size) for index in indices]


def largest_feasible(doc, objects, upper):
    """The largest size below `upper` (a multiple of `UNIT`) at which every fillet or chamfer of `objects` builds, or None when not even
    `UNIT` does. `upper` is a size that does not build. The objects are left at the last size that was tried: the caller sets the size."""
    low, high = 0, max(1, math.ceil(upper / UNIT - 1e-9))
    while high - low > 1:
        middle = (low + high) // 2
        for obj in objects:
            set_size(obj, round(middle * UNIT, 6))
        doc.recompute()
        if all(sound(obj) for obj in objects):
            low = middle
        else:
            high = middle
    return round(low * UNIT, 6) if low else None


def _canonical(vector, offset=None):
    """The direction `vector` (a tuple) with its first non-zero component positive, rounded; the sign of an axis is arbitrary."""
    length = math.sqrt(sum(c * c for c in vector)) or 1.0
    unit = [c / length for c in vector]
    sign = -1.0 if next((c for c in unit if abs(c) > 1e-6), 1.0) < 0 else 1.0
    return tuple(round(sign * c + 0.0, 3) for c in unit), sign


def surface_key(surface):
    """A comparable description of an analytic surface (a plane, a cylinder, a cone, a sphere or a torus: type, direction, position and
    radii, rounded), or None for any other surface. Two faces on the same surface have the same key."""
    kind = type(surface).__name__
    try:
        if kind == "Plane":
            axis, _ = _canonical(tuple(surface.Axis))
            return (kind, axis, round(sum(a * p for a, p in zip(axis, tuple(surface.Position))) + 0.0, 2))
        if kind in ("Cylinder", "Cone", "Toroid"):
            axis, _ = _canonical(tuple(surface.Axis))
            centre = tuple(surface.Center if kind != "Cone" else surface.Apex)
            along = sum(a * c for a, c in zip(axis, centre))
            foot = tuple(round(c - along * a, 2) for c, a in zip(centre, axis))      # the point of the axis nearest to the origin
            radii = ((surface.Radius,) if kind == "Cylinder" else (surface.SemiAngle,) if kind == "Cone"
                     else (surface.MajorRadius, surface.MinorRadius))
            return (kind, axis, foot, tuple(round(r, 3) for r in radii)) + ((round(along, 2),) if kind == "Toroid" else ())
        if kind == "Sphere":
            return (kind, tuple(round(c, 2) for c in surface.Center), round(surface.Radius, 3))
    except Exception:
        return None
    return None


def new_faces(base_shape, shape):
    """The numbers (1 based) of the faces of `shape` that lie on no surface of `base_shape`: the faces that a fillet or a chamfer adds.
    A face on a surface that has no key (a freeform surface) does not count."""
    known = {surface_key(face.Surface) for face in base_shape.Faces}
    result = []
    for number, face in enumerate(shape.Faces, 1):
        key = surface_key(face.Surface)
        if key is not None and key not in known:
            result.append(number)
    return result


def selection_after(doc, names):
    """What to select once the features `names` are made: the faces that each added to its source, or the whole feature when it added
    none that can be told apart. A list of (object name, sub-element name) pairs."""
    chosen = []
    for name in names:
        obj = doc.getObject(name)
        faces = []
        try:
            faces = new_faces(obj.Base.Shape, obj.Shape)
        except Exception:
            pass
        chosen += [(name, f"Face{n}") for n in faces] or [(name, "")]
    return chosen


def make(doc, items, kind, size=SIZE):
    """Fillet or chamfer the selected edges, one feature per object that has edges selected, in one transaction (one undo step). The
    source objects are hidden, not changed. A size that the edges cannot take becomes the largest one they can take, and the text says
    so. Returns (text for a toast, names of the new features)."""
    if kind not in KINDS:
        raise ValueError(f"unknown edge feature '{kind}'")
    groups = [(n, e) for n, e in edge_selection(items) if doc.getObject(n) is not None]
    if not groups:
        return ("Select edges first" if items else "Nothing selected"), []
    label = VERBS[kind]
    doc.openTransaction(f"{label} " + (doc.getObject(groups[0][0]).Label if len(groups) == 1 else f"{len(groups)} objects"))
    made = []
    try:
        for name, indices in groups:
            source = doc.getObject(name)
            obj = doc.addObject(TYPES[kind], label)
            obj.Base = source
            obj.Edges = edge_rows(indices, size)
            made.append(obj)
        doc.recompute()
        smaller = []
        for obj in made:
            if not sound(obj):
                best = largest_feasible(doc, [obj], size)
                if best is None:
                    raise ValueError("these edges cannot be dressed")
                set_size(obj, best)
                smaller.append(best)
        doc.recompute()
        for obj in made:
            if not sound(obj):
                raise ValueError(f"{size:g} mm is too large for these edges")
        for name, _ in groups:
            hide(doc.getObject(name))
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"{label} failed: {error}", []
    count = sum(len(e) for _, e in groups)
    text = f"{label}: {count} edge" + ("" if count == 1 else "s")
    if smaller:
        text += f", {min(smaller):g} mm ({size:g} mm is too large)"
    return text, [obj.Name for obj in made]


def is_edge_feature(obj):
    return obj is not None and obj.TypeId in TYPES.values()


def size_of(obj):
    """The size (radius or length) of a fillet or chamfer: that of its first edge."""
    return float(obj.Edges[0][1])


def set_size(obj, size):
    """Give every edge of the fillet or chamfer the size."""
    obj.Edges = edge_rows([row[0] for row in obj.Edges], size)
