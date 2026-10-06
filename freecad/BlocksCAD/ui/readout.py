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
"""A small floating text readout facing the user (scale while navigating with two grips, later values and toasts).
Lives in the stage frame; `place` positions it and turns it towards the head."""

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu

TEXT_HEIGHT = 0.03  # metres of glyph height


class Readout:
    def __init__(self, color=(1.0, 0.85, 0.2)):
        self.root = coin.SoSwitch()
        self.root.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        sep.addChild(pick)
        self._xf = coin.SoTransform()
        sep.addChild(self._xf)
        material = coin.SoBaseColor()
        material.rgb = coin.SbColor(*color)
        sep.addChild(material)
        scale = coin.SoScale()
        scale.scaleFactor.setValue(TEXT_HEIGHT, TEXT_HEIGHT, TEXT_HEIGHT)
        sep.addChild(scale)
        self._text = coin.SoText3()
        self._text.justification = coin.SoText3.CENTER
        sep.addChild(self._text)
        self.root.addChild(sep)

    def show(self, text, position, head_position):
        """Show `text` at `position`, turned towards `head_position` (stage coordinates)."""
        self._text.string = text
        self._xf.translation.setValue(*position)
        # SoText3 faces +Z; turn that axis towards the head, keeping the text upright
        q = mu.look_at(position, head_position)
        self._xf.rotation.setValue(*mu.quat_multiply(q, mu.quat_from_axis_angle((0, 1, 0), 3.141592653589793)))
        self.root.whichChild = coin.SO_SWITCH_ALL

    def hide(self):
        self.root.whichChild = coin.SO_SWITCH_NONE
