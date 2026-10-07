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
"""Mirrors and patterns of the selected objects (docs/ux-design.md, Modify panel).

Both are features that refer to their source and carry their numbers as properties, so they stay parametric: a mirror is a
`Part::Mirroring` (its `Base` point and `Normal` give the plane), a pattern is a Draft array (`NumberX` and `IntervalX` and the
like). `mirror_plane` and `array_spacing` are pure Python. The functions that touch a document import FreeCAD when they run."""

from freecad.BlocksCAD.cad.combine import GAP, selected_names, sound as _sound

AXES = "XYZ"
PATTERN_COUNT = 3        # the objects in a pattern, the original included


def unit(axis):
    """The unit vector of an axis (0, 1 or 2)."""
    return tuple(1.0 if i == axis else 0.0 for i in range(3))


def mirror_plane(low, high, axis, gap=GAP):
    """(base point, normal) of the plane that mirrors an object with the box `low` to `high` (document millimetres) across the
    axis: the plane stands half a `gap` beyond the box, so the mirror image lies one `gap` from the object."""
    base = tuple((l + h) / 2 for l, h in zip(low, high))
    base = tuple(high[axis] + gap / 2 if i == axis else c for i, c in enumerate(base))
    return base, unit(axis)


def array_spacing(low, high, axis, gap=GAP):
    """The interval of a pattern along the axis: the length of the box plus a `gap`."""
    return (high[axis] - low[axis]) + gap


def _each(doc, items, label, make):
    """Run `make(source)` for every selected whole object in one transaction; returns (text, names of the results)."""
    import FreeCAD as App  # noqa: F401
    names = [n for n in selected_names(items) if doc.getObject(n) is not None]
    if not names:
        return ("Select a whole object" if items else "Nothing selected"), []
    first = doc.getObject(names[0]).Label
    doc.openTransaction(f"{label} " + (first if len(names) == 1 else f"{len(names)} objects"))
    results = []
    try:
        for name in names:
            results.append(make(doc.getObject(name)))
        doc.recompute()
        for obj in results:
            if not _sound(obj):
                raise ValueError("FreeCAD could not make it")
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"{label} failed: {error}", []
    return (f"{label}: {first}" if len(names) == 1 else f"{label}: {len(names)} objects"), [obj.Name for obj in results]


def mirror(doc, items, axis, gap=GAP):
    """Mirror the selected objects across the plane just beyond their box along the axis (0, 1, 2 for X, Y, Z), in one transaction.
    Returns (text for a toast, names of the mirrored objects)."""
    import FreeCAD as App

    def make(source):
        box = source.Shape.BoundBox
        base, normal = mirror_plane((box.XMin, box.YMin, box.ZMin), (box.XMax, box.YMax, box.ZMax), axis, gap)
        obj = doc.addObject("Part::Mirroring", "Mirror")
        obj.Source = source
        obj.Base = App.Vector(*base)
        obj.Normal = App.Vector(*normal)
        return obj
    return _each(doc, items, f"Mirror {AXES[axis]}", make)


def pattern(doc, items, axis, count=PATTERN_COUNT, gap=GAP):
    """Repeat the selected objects `count` times along the axis, one box length plus `gap` apart, as Draft arrays in one
    transaction. Returns (text for a toast, names of the arrays)."""
    import Draft
    import FreeCAD as App

    def make(source):
        box = source.Shape.BoundBox
        step = array_spacing((box.XMin, box.YMin, box.ZMin), (box.XMax, box.YMax, box.ZMax), axis, gap)
        vectors = [App.Vector(*(c * (step if i == axis else 1.0) for c in unit(i))) for i in range(3)]
        counts = [count if i == axis else 1 for i in range(3)]
        return Draft.make_ortho_array(source, vectors[0], vectors[1], vectors[2], *counts, use_link=False)
    return _each(doc, items, f"Pattern {AXES[axis]}", make)
