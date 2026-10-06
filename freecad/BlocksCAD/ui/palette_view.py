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
"""Coin3D drawing of a `RadialPalette`: one label per item on a ring in the XY plane of the node's parent frame
(+Y up, facing +Z). Attach `root` below a controller transform; the view hides itself while the palette is closed."""

import math

from pivy import coin

RADIUS = 0.07   # metres
TEXT_SCALE = 0.006
COLOR_IDLE = (0.85, 0.85, 0.9)
COLOR_ACTIVE = (1.0, 0.75, 0.1)


class PaletteView:
    def __init__(self, palette):
        self.palette = palette
        self.root = coin.SoSwitch()
        self.root.whichChild = coin.SO_SWITCH_NONE
        self._sep = coin.SoSeparator()
        self.root.addChild(self._sep)
        self._colors = []
        self._shown_items = None
        self._build()

    def _build(self):
        self._sep.removeAllChildren()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self._sep.addChild(pick)
        self._colors = []
        n = len(self.palette.items)
        for index, (_name, label) in enumerate(self.palette.items):
            angle = self.palette.sector_angle(index)
            item = coin.SoSeparator()
            move = coin.SoTranslation()
            move.translation.setValue(RADIUS * math.sin(angle), RADIUS * math.cos(angle), 0.0)
            color = coin.SoBaseColor()
            color.rgb = coin.SbColor(*COLOR_IDLE)
            scale = coin.SoScale()
            scale.scaleFactor.setValue(TEXT_SCALE, TEXT_SCALE, TEXT_SCALE)
            text = coin.SoText3()
            text.string = label
            text.justification = coin.SoText3.CENTER
            for node in (move, color, scale, text):
                item.addChild(node)
            self._sep.addChild(item)
            self._colors.append(color)
        self._shown_items = list(self.palette.items)

    def update(self):
        if self._shown_items != self.palette.items:
            self._build()
        self.root.whichChild = coin.SO_SWITCH_ALL if self.palette.is_open else coin.SO_SWITCH_NONE
        for index, color in enumerate(self._colors):
            color.rgb = coin.SbColor(*(COLOR_ACTIVE if index == self.palette.highlighted else COLOR_IDLE))
