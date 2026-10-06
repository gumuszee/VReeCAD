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
"""Coin3D drawing of the quick radial (docs/ux-design.md, Quick radial): a disc in a plane that faces the head, cut into one
segment per item around a hub, drawn over the model, with a dot that follows the hand. Same colours and font as the palette."""

import math

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import radial as rd
from freecad.BlocksCAD.ui import style
from freecad.BlocksCAD.ui.ring_view import DEPTH, _text

BACKDROP = 0.012      # the dark disc reaches this far beyond the segments
CURSOR = 0.012        # edge of the dot that follows the hand
LABEL_RADIUS = (rd.INNER + rd.OUTER) / 2 + 0.004


def _strip(parent, points, rgb, z):
    """A filled triangle strip in the plane of the radial; returns its colour node."""
    sep = coin.SoSeparator()
    colour = style.color(rgb)
    sep.addChild(colour)
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(points), [(x, y, z) for x, y in points])
    sep.addChild(coords)
    strip = coin.SoTriangleStripSet()
    strip.numVertices.setValue(len(points))
    sep.addChild(strip)
    parent.addChild(sep)
    return colour


def _disc(radius, steps=48):
    """Strip points that fill a disc: outer point and centre alternate."""
    points = []
    for k in range(steps + 1):
        a = 2 * math.pi * k / steps
        points += [(radius * math.sin(a), radius * math.cos(a)), (0.0, 0.0)]
    return points


class RadialView:
    def __init__(self):
        self.root = coin.SoSwitch()
        self.root.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        sep.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        sep.addChild(light)
        depth = coin.SoDepthBuffer()      # drawn over the model, never hidden by it
        depth.test.setValue(False)
        depth.getField("write").setValue(False)
        sep.addChild(depth)
        sep.addChild(style.font())
        self._transform = coin.SoTransform()
        sep.addChild(self._transform)
        self._items = coin.SoSeparator()
        sep.addChild(self._items)
        cursor = coin.SoSeparator()
        self._cursor_move = coin.SoTranslation()
        cursor.addChild(self._cursor_move)
        cursor.addChild(style.color(style.TEXT))
        dot = coin.SoCube()
        dot.width, dot.height, dot.depth = CURSOR, CURSOR, DEPTH
        cursor.addChild(dot)
        sep.addChild(cursor)
        self.root.addChild(sep)
        self._segments = []
        self._built_for = None

    def _build(self, labels):
        """With the depth test off what is drawn later lies on top, so the order is: backdrop, hub, segments, labels."""
        self._items.removeAllChildren()
        self._segments = []
        count = len(labels)
        _strip(self._items, _disc(rd.OUTER + BACKDROP), style.PLATE, -DEPTH)
        _strip(self._items, _disc(rd.INNER - rd.GAP), style.EMPTY, 0.0)
        for i in range(count):
            self._segments.append(_strip(self._items, rd.segment_strip(i, count), style.FACE, 0.0))
        for i, label in enumerate(labels):
            a = 2 * math.pi * i / count
            _text(self._items, lay.wrap_label(label), LABEL_RADIUS * math.sin(a), LABEL_RADIUS * math.cos(a), DEPTH, style.TEXT)
        self._built_for = tuple(labels)

    def update(self, state, labels):
        """Show the radial for a `radial.RadialState`; `labels` are the texts of its items."""
        if not state.open:
            self.root.whichChild = coin.SO_SWITCH_NONE
            return
        if self._built_for != tuple(labels):
            self._build(labels)
        self.root.whichChild = coin.SO_SWITCH_ALL
        normal = mu.cross(state.right, state.up)
        self._transform.translation.setValue(*state.centre)
        self._transform.rotation.setValue(*mu.quat_from_basis(state.right, state.up, normal))
        reach = math.hypot(*state.cursor)
        scale = min(reach, rd.OUTER) / reach if reach > 1e-9 else 0.0
        self._cursor_move.translation.setValue(state.cursor[0] * scale, state.cursor[1] * scale, DEPTH)
        for i, colour in enumerate(self._segments):
            colour.rgb = coin.SbColor(*(style.HOVER if state.selected == i else style.FACE))
