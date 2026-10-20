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
"""The tangents of the features of the model at a point (docs/ux-design.md, Placement and inference): the Points tool snaps a handle
of a curve onto them. A feature is an edge of a visible object (a line, an arc, a circle, a curve of a block); `tangents_at` reads the
document, in document millimetres."""

NEAREST = 4                 # the tangents of this many nearest features are given


def _unit(vector):
    length = vector.Length
    return None if length < 1e-12 else (vector.x / length, vector.y / length, vector.z / length)


def tangents_at(doc, point, reach, exclude=()):
    """The unit directions of the tangents (one way each) of the edges of the visible objects of `doc` except those named in `exclude`
    that pass within `reach` millimetres of `point`, the nearest edges first (at most `NEAREST`)."""
    import FreeCAD as App
    here = App.Vector(*point)
    found = []
    for obj in doc.Objects:
        shape = getattr(obj, "Shape", None)
        if obj.Name in exclude or shape is None or shape.isNull() or not getattr(obj, "Visibility", True):
            continue
        box = shape.BoundBox
        if not box.isValid() or not (box.XMin - reach <= point[0] <= box.XMax + reach and box.YMin - reach <= point[1] <= box.YMax + reach
                                     and box.ZMin - reach <= point[2] <= box.ZMax + reach):
            continue
        for edge in shape.Edges:
            try:
                u = min(max(edge.Curve.parameter(here), edge.FirstParameter), edge.LastParameter)
                distance = edge.valueAt(u).distanceToPoint(here)
                if distance <= reach:
                    direction = _unit(edge.tangentAt(u))
                    if direction is not None:
                        found.append((distance, direction))
            except (TypeError, RuntimeError, ValueError, App.Base.FreeCADError):
                continue                                    # a degenerated edge has no curve
    found.sort(key=lambda item: item[0])
    return [direction for _, direction in found[:NEAREST]]
