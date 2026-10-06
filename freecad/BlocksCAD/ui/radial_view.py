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
"""Coin3D drawing of the quick radial (docs/ux-design.md, Quick radial): a ring of faces in a plane that faces the head, drawn over
the model, with a dot that follows the hand. Same look as the palette faces (`style`, `ring_view`)."""

import math

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import radial as rd
from freecad.BlocksCAD.ui import ring as rg
from freecad.BlocksCAD.ui import style
from freecad.BlocksCAD.ui.ring_view import DEPTH, _Cell, _plate

CURSOR = 0.012     # edge of the dot that follows the hand


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
        self._cells = []
        self._built_for = None

    def _build(self, labels):
        self._items.removeAllChildren()
        self._cells = []
        # the backing plate comes first: with the depth test off, what is drawn later lies on top
        _plate(self._items, 2 * rd.RADIUS + rg.CELL, 2 * rd.RADIUS + rg.CELL, style.PLATE, 0.0, 0.0, -DEPTH * 2)
        count = len(labels)
        for i, label in enumerate(labels):
            angle = 2 * math.pi * i / count
            self._cells.append(_Cell(self._items, rd.RADIUS * math.sin(angle), rd.RADIUS * math.cos(angle), label))
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
        reach = min(math.hypot(*state.cursor), rd.RADIUS)
        scale = reach / math.hypot(*state.cursor) if math.hypot(*state.cursor) > 1e-9 else 0.0
        self._cursor_move.translation.setValue(state.cursor[0] * scale, state.cursor[1] * scale, DEPTH)
        for i, cell in enumerate(self._cells):
            cell.set_state(state.selected == i, False, True)
