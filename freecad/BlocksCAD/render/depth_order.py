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
"""A fixed depth order for the objects of a document (docs/ux-design.md, Overlapping faces).

Two objects that share a plane (a box standing on another, a cut that ends in the plane of the base) draw faces at the same depth,
and the depth test then picks one of them per pixel, differently from frame to frame: a flicker, which shows most where the two
objects have different colours or one of them is selected. Every object gets a `SoPolygonOffset` as the first child of the root of its
view provider, with an offset that grows with the place of the object in the document (`LEVELS` levels, newer objects nearer), so the
winner of a shared plane is always the same. The offsets are a few steps of the depth buffer (micrometres), no visible shift. The nodes
are made for the viewer and taken out again when it stops (`release`): the scene graph is the one of the FreeCAD view, which is not left
changed. Pivy only; objects without a view provider (no GUI) are left alone."""

from pivy import coin

LEVELS = 16              # objects whose places differ by a multiple of this share an offset
FACTOR_STEP = -0.5       # the slope part of the offset of one level (towards the viewer)
UNITS_STEP = -2.0        # the part in depth buffer steps


def offset_for(rank):
    """(factor, units) of the polygon offset of the object with place `rank` in the document."""
    level = rank % LEVELS
    return FACTOR_STEP * level, UNITS_STEP * level


def _make_node(rank):
    node = coin.SoPolygonOffset()
    factor, units = offset_for(rank)
    node.factor.setValue(factor)
    node.units.setValue(units)
    node.styles.setValue(coin.SoPolygonOffset.FILLED)
    node.on.setValue(True)
    return node


def _root_of(obj):
    view = getattr(obj, "ViewObject", None)
    try:
        return None if view is None else view.RootNode
    except Exception:                      # a view provider without a root, or one that is going away
        return None


class DepthOrder:
    def __init__(self):
        self._placed = {}                  # object name -> (root, node, the address of the root)
        self._ranks = {}                   # object name -> its rank: the order in which the objects were first seen, kept when others go

    def sync(self, doc):
        """Give every object of `doc` its offset (and the new ones theirs); the offsets of objects that are gone are dropped."""
        objects = list(doc.Objects)
        names = {o.Name for o in objects}
        for name in [n for n in self._placed if n not in names]:
            self._remove(name)
        for obj in objects:
            rank = self._ranks.setdefault(obj.Name, len(self._ranks))
            known = self._placed.get(obj.Name)
            root = _root_of(obj)
            if root is None:
                if known is not None:
                    self._remove(obj.Name)
                continue
            where = str(root.this)                                        # the same object keeps the same root, a new one under that name does not
            if known is not None and known[2] == where:
                continue
            if known is not None:
                self._remove(obj.Name)
            node = _make_node(rank)
            root.ref()
            root.insertChild(node, 0)
            self._placed[obj.Name] = (root, node, where)

    def _remove(self, name):
        root, node, _ = self._placed.pop(name)
        try:
            if root.findChild(node) >= 0:
                root.removeChild(node)
        finally:
            root.unref()

    def release(self):
        """Take every offset out of the scene graph."""
        for name in list(self._placed):
            self._remove(name)

    @property
    def count(self):
        return len(self._placed)
