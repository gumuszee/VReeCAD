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
`cad/values.py`). `edge_selection`, `edge_index` and `edge_rows` are pure Python; the functions that make features work on a document
and import nothing else from FreeCAD."""

from freecad.BlocksCAD.cad.combine import hide, sound

KINDS = ("fillet", "chamfer")
TYPES = {"fillet": "Part::Fillet", "chamfer": "Part::Chamfer"}
VERBS = {"fillet": "Fillet", "chamfer": "Chamfer"}
SIZE = 5.0                  # millimetres: the radius of a new fillet and the length of a new chamfer


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


def make(doc, items, kind, size=SIZE):
    """Fillet or chamfer the selected edges, one feature per object that has edges selected, in one transaction (one undo step). The
    source objects are hidden, not changed. Returns (text for a toast, names of the new features)."""
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
    return f"{label}: {count} edge" + ("" if count == 1 else "s"), [obj.Name for obj in made]


def is_edge_feature(obj):
    return obj is not None and obj.TypeId in TYPES.values()


def size_of(obj):
    """The size (radius or length) of a fillet or chamfer: that of its first edge."""
    return float(obj.Edges[0][1])


def set_size(obj, size):
    """Give every edge of the fillet or chamfer the size."""
    obj.Edges = edge_rows([row[0] for row in obj.Edges], size)
