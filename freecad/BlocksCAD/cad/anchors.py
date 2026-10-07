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
"""The points of the model that a new point can line up with (docs/ux-design.md, Guides): the vertices of the visible objects and the middles
of their straight edges, in document millimetres, as `core.guides.align` takes them. `object_points` reads one object, `collect` reads
a document, and `Anchors` keeps the points of every object (`cad/changes.py`: only the objects that changed are read again) and the
combined list, so that a tool may ask for it every frame; the list is the same object until something other than the excluded
objects changes."""

MAX_ANCHORS = 3000          # a model with more points than this lines up with the first ones only


def object_points(obj):
    """The anchors of one object (vertices and the middles of straight edges, a point may come twice), or None when it has none: it has
    no shape, or is hidden."""
    import Part
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull() or not getattr(obj, "Visibility", True):
        return None
    points = [(v.X, v.Y, v.Z) for v in shape.Vertexes]
    for edge in shape.Edges:
        if isinstance(edge.Curve, Part.Line):
            middle = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
            points.append((middle.x, middle.y, middle.z))
    return points or None


def combine(lists, limit=MAX_ANCHORS):
    """The points of the `lists`, each point once, at most `limit`."""
    seen, anchors = set(), []
    for points in lists:
        for x, y, z in points:
            key = (round(x, 4), round(y, 4), round(z, 4))
            if key not in seen:
                if len(anchors) >= limit:
                    return anchors
                seen.add(key)
                anchors.append((x, y, z))
    return anchors


def collect(doc, exclude=(), limit=MAX_ANCHORS):
    """The anchors of the visible objects of `doc` except those named in `exclude`, each point once (every object is read)."""
    found = (object_points(obj) for obj in doc.Objects if obj.Name not in exclude)
    return combine((points for points in found if points), limit)


def local_points(obj, limit=64):
    """The points of the object `obj` that can line up with the anchors of the model, in its own frame (the placement left out): the
    middle and the corners of the box around it, then its vertices, each once, at most `limit`."""
    import FreeCAD as App
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        return []
    shape = shape.copy()
    shape.Placement = App.Placement()
    box = shape.BoundBox
    seen, points = set(), []

    def add(x, y, z):
        key = (round(x, 4), round(y, 4), round(z, 4))
        if key not in seen and len(points) < limit:
            seen.add(key)
            points.append((x, y, z))

    add(box.Center.x, box.Center.y, box.Center.z)
    for x in (box.XMin, box.XMax):
        for y in (box.YMin, box.YMax):
            for z in (box.ZMin, box.ZMax):
                add(x, y, z)
    for vertex in shape.Vertexes:
        add(vertex.X, vertex.Y, vertex.Z)
    return points


class Anchors:
    """`get(doc, exclude)` is `collect` kept up to date through a `cad.changes.Changes` log (the log of the process by default): the
    points of an object are read when it is new or has changed, and the list is made again only when the exclusions or the document
    differ or an object that is not excluded changed. An object that is dragged and excluded costs nothing per frame."""

    def __init__(self, changes=None, per_object=object_points):
        self._changes, self._per_object = changes, per_object
        self._cache = None
        self._key = self._found = None

    def get(self, doc, exclude=()):
        from freecad.BlocksCAD.cad import changes as log
        if self._cache is None:
            self._cache = log.ObjectCache(self._changes if self._changes is not None else log.shared(), self._per_object)
        values, touched = self._cache.sync(doc)
        key = (doc.Name, tuple(sorted(exclude)))
        if self._found is None or key != self._key or touched is None or any(name not in exclude for name in touched):
            self._key = key
            self._found = combine(points for name, points in values.items() if name not in exclude)
        return self._found
