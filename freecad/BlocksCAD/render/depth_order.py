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
objects have different colours or one of them is selected. Every object gets a polygon offset that grows with the place of the object
in the document (`LEVELS` levels): older objects are pushed back a little further than newer ones, so the winner of a shared plane is
always the newer object. The offsets are a few steps of the depth buffer (micrometres), no visible shift, and they only push back, so
the edges of an object (drawn without an offset) stay in front of its faces. The view provider of a Part object has an offset node
of its own, which replaces any node before it, so its values are shifted; a view provider without one gets a node of our own. Everything
is put back by `release` when the viewer stops: the scene graph is the one of the FreeCAD view. Pivy only; objects without a view
provider (no GUI) are left alone."""

from pivy import coin

LEVELS = 16              # objects whose places differ by a multiple of this share an offset
FACTOR_STEP = 0.0        # the slope part of the push back of one level: none, a slope term lets the far edges show through grazing faces
UNITS_STEP = 1.0         # the part in depth buffer steps


def offset_for(rank):
    """(factor, units) that the object with place `rank` in the document is pushed back by: the newest level is not pushed."""
    back = LEVELS - 1 - rank % LEVELS
    return FACTOR_STEP * back, UNITS_STEP * back


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


def _offsets_in(root):
    """The polygon offset nodes inside a view provider root (a Part view provider has one, between its points and its faces)."""
    action = coin.SoSearchAction()
    action.setType(coin.SoPolygonOffset.getClassTypeId())
    action.setInterest(coin.SoSearchAction.ALL)
    action.setSearchingAll(True)
    action.apply(root)
    paths = action.getPaths()
    return [paths[i].getTail() for i in range(paths.getLength())]


class DepthOrder:
    """Each object has one entry: either the polygon offsets its view provider already has (their values are shifted by the offset of
    the object and put back by `release`; a node later in the root replaces an earlier one, so a node of our own in front of the faces
    would change nothing), or, for a view provider without any, a node of our own as the first child of its root."""

    def __init__(self):
        self._placed = {}                  # object name -> (root, [(node, factor, units, shifted factor, shifted units)], own node or None, address)
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
            if known is not None and known[3] == where:
                self._reassert(known)                                      # the view provider may have written its own values since
                continue
            if known is not None:
                self._remove(obj.Name)
            self._place(obj.Name, root, rank, where)

    def _place(self, name, root, rank, where):
        factor, units = offset_for(rank)
        shifted, own = [], None
        for node in _offsets_in(root):
            f, u = node.factor.getValue(), node.units.getValue()
            node.factor.setValue(f + factor)
            node.units.setValue(u + units)
            shifted.append((node, f, u, f + factor, u + units))
        if not shifted:
            own = _make_node(rank)
            root.insertChild(own, 0)
        root.ref()
        self._placed[name] = (root, shifted, own, where)

    @staticmethod
    def _reassert(entry):
        for node, f, u, sf, su in entry[1]:
            if node.factor.getValue() != sf or node.units.getValue() != su:
                node.factor.setValue(sf)
                node.units.setValue(su)

    def _remove(self, name):
        root, shifted, own, _ = self._placed.pop(name)
        try:
            for node, f, u, _, _ in shifted:
                node.factor.setValue(f)
                node.units.setValue(u)
            if own is not None and root.findChild(own) >= 0:
                root.removeChild(own)
        finally:
            root.unref()

    def release(self):
        """Put every offset back as it was and take our own nodes out of the scene graph."""
        for name in list(self._placed):
            self._remove(name)

    @property
    def count(self):
        return len(self._placed)
