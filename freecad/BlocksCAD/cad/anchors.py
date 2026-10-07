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
of their straight edges, in document millimetres, as `core.guides.align` takes them. `collect` reads a document; `Anchors` keeps the
result for a short while so that a tool may ask for it every frame."""

import time

MAX_ANCHORS = 3000          # a model with more points than this lines up with the first ones only
REFRESH = 0.5               # seconds a collected list is kept


def collect(doc, exclude=(), limit=MAX_ANCHORS):
    """The anchors of the visible objects of `doc` except those named in `exclude`, each point once."""
    import Part
    seen, anchors = set(), []

    def add(x, y, z):
        key = (round(x, 4), round(y, 4), round(z, 4))
        if key not in seen and len(anchors) < limit:
            seen.add(key)
            anchors.append((x, y, z))

    for obj in doc.Objects:
        shape = getattr(obj, "Shape", None)
        if obj.Name in exclude or shape is None or shape.isNull() or not getattr(obj, "Visibility", True):
            continue
        for vertex in shape.Vertexes:
            add(vertex.X, vertex.Y, vertex.Z)
        for edge in shape.Edges:
            if isinstance(edge.Curve, Part.Line):
                middle = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
                add(middle.x, middle.y, middle.z)
    return anchors


class Anchors:
    """`get(doc, exclude)` is `collect` kept for `REFRESH` seconds for the same document and exclusions."""

    def __init__(self, clock=time.monotonic, collector=collect):
        self._clock, self._collector = clock, collector
        self._key = self._stamp = self._found = None

    def get(self, doc, exclude=()):
        key = (doc.Name, tuple(sorted(exclude)))
        now = self._clock()
        if key != self._key or self._stamp is None or now - self._stamp > REFRESH:
            self._key, self._stamp, self._found = key, now, self._collector(doc, exclude)
        return self._found
