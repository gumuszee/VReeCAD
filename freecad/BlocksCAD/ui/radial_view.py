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
"""Coin3D drawing of a disc of segments (docs/ux-design.md, Quick radial and Tool options): a disc in a plane that faces the head,
cut into one segment per item around a hub, drawn over the model, with a dot that follows the hand or the stick. The quick radial
and the option disc of a tool are both drawn by `RadialView`, with different radii. Same colours and font as the palette."""

import math

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import radial as rd
from freecad.BlocksCAD.ui import style
from freecad.BlocksCAD.ui.ring_view import DEPTH

BACKDROP = 0.012      # the dark disc reaches this far beyond the segments
CURSOR = 0.012        # edge of the dot that follows the hand


def _strip(parent, points, rgb, z):
    """A filled triangle strip in the plane of the disc; returns its colour node."""
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


def _text(parent, lines, x, y, z, rgb, factor=1.0):
    """Lines of text centred on (x, y); returns the colour node."""
    sep = coin.SoSeparator()
    move = coin.SoTranslation()
    move.translation.setValue(x, y + (len(lines) - 1) * 0.5 * style.LINE_HEIGHT * factor - 0.0035 * factor, z)
    sep.addChild(move)
    colour = style.color(rgb)
    sep.addChild(colour)
    sep.addChild(style.text_scale(factor))
    text = coin.SoText3()
    text.justification = coin.SoText3.CENTER
    text.string.setValues(0, len(lines), lines)
    sep.addChild(text)
    parent.addChild(sep)
    return colour


class RadialView:
    def __init__(self, outer=rd.OUTER, inner=rd.INNER, text_factor=1.0):
        self.outer, self.inner, self.text_factor = outer, inner, text_factor
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
        hub = coin.SoSeparator()
        hub_move = coin.SoTranslation()
        hub_move.translation.setValue(0.0, 0.0, DEPTH)
        hub.addChild(hub_move)
        hub.addChild(style.color(style.TEXT))
        hub.addChild(style.text_scale(0.9 * text_factor))
        self._hub = coin.SoText3()
        self._hub.justification = coin.SoText3.CENTER
        hub.addChild(self._hub)
        self._hub_shift = hub_move
        sep.addChild(hub)
        cursor = coin.SoSeparator()
        self._cursor_move = coin.SoTranslation()
        cursor.addChild(self._cursor_move)
        cursor.addChild(style.color(style.TEXT))
        dot = coin.SoCube()
        dot.width, dot.height, dot.depth = CURSOR, CURSOR, DEPTH
        cursor.addChild(dot)
        sep.addChild(cursor)
        self.root.addChild(sep)
        self._segments = []       # (colour node of the plate, colour node of the text or None)
        self._built_for = None
        self._hub_lines = None

    def _build(self, labels):
        """With the depth test off what is drawn later lies on top, so the order is: backdrop, hub, segments, labels."""
        self._items.removeAllChildren()
        self._segments = []
        count = len(labels)
        _strip(self._items, _disc(self.outer + BACKDROP), style.PLATE, -DEPTH)
        _strip(self._items, _disc(self.inner - rd.GAP), style.EMPTY, 0.0)
        plates = [_strip(self._items, rd.segment_strip(i, count, self.inner, self.outer), style.FACE, 0.0) for i in range(count)]
        radius = (self.inner + self.outer) / 2 + 0.004
        for i, label in enumerate(labels):
            a = 2 * math.pi * i / count
            text = _text(self._items, lay.wrap_label(label), radius * math.sin(a), radius * math.cos(a), DEPTH, style.TEXT,
                         self.text_factor) if label else None
            self._segments.append((plates[i], text))
        self._built_for = tuple(labels)

    def _write_hub(self, lines):
        if lines != self._hub_lines:
            self._hub_lines = lines
            self._hub.string.setValues(0, len(lines), lines or [""])
            self._hub.string.setNum(max(len(lines), 1))
            self._hub_shift.translation.setValue(0.0, (len(lines) - 1) * 0.5 * style.LINE_HEIGHT * 0.9 - 0.0035, DEPTH)

    def update(self, state, labels, active=None, hub=None):
        """Show the disc for a `radial.RadialState`; `labels` are the texts of its items (an empty text is an empty segment),
        `active` flags the items that hold the current value of their option and `hub` the lines of text in the middle."""
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
        scale = min(reach, self.outer) / reach if reach > 1e-9 else 0.0
        self._cursor_move.translation.setValue(state.cursor[0] * scale, state.cursor[1] * scale, DEPTH)
        self._write_hub(list(hub or []))
        for i, (plate, text) in enumerate(self._segments):
            if text is None:
                plate.rgb = coin.SbColor(*style.EMPTY)
                continue
            lit = bool(active and active[i])
            plate.rgb = coin.SbColor(*(style.HOVER if state.selected == i else style.ACTIVE if lit else style.FACE))
            text.rgb = coin.SbColor(*(style.TEXT_ON_ACTIVE if lit and state.selected != i else style.TEXT))
