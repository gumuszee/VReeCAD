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
"""The laser of the tool hand while the palette carousel is shown: a thin beam from the controller to the point it hits (or a fixed
length ahead when it hits nothing) and a dot at the hit point. Drawn on top of the scene so it is never lost behind a panel."""

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import style

FREE_LENGTH = 0.6      # metres of beam when nothing is hit
BEAM_RADIUS = 0.0016
DOT_RADIUS = 0.006
IDLE = (0.55, 0.75, 1.0)
HIT = (1.0, 0.9, 0.4)


class Pointer:
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
        depth = coin.SoDepthBuffer()
        depth.test.setValue(False)
        depth.getField("write").setValue(False)
        sep.addChild(depth)
        self._color = style.color(IDLE)
        sep.addChild(self._color)
        beam = coin.SoSeparator()
        self._beam_xf = coin.SoTransform()
        beam.addChild(self._beam_xf)
        self._beam = coin.SoCylinder()
        self._beam.radius = BEAM_RADIUS
        beam.addChild(self._beam)
        sep.addChild(beam)
        dot = coin.SoSeparator()
        self._dot_xf = coin.SoTranslation()
        dot.addChild(self._dot_xf)
        self._dot = coin.SoSphere()
        self._dot.radius = DOT_RADIUS
        dot.addChild(self._dot)
        self._dot_switch = coin.SoSwitch()
        self._dot_switch.addChild(dot)
        sep.addChild(self._dot_switch)
        self.root.addChild(sep)

    def hide(self):
        self.root.whichChild = coin.SO_SWITCH_NONE

    def show(self, origin, direction, end=None):
        """Draw the beam from `origin` along `direction` (unit vector), ending at the point `end` when it hits something."""
        length = mu.length(mu.sub(end, origin)) if end is not None else FREE_LENGTH
        if length < 1e-3:
            self.hide()
            return
        middle = mu.add(origin, mu.mul(direction, length / 2))
        self._beam.height = length
        self._beam_xf.translation.setValue(*middle)
        self._beam_xf.rotation.setValue(*mu.quat_between((0.0, 1.0, 0.0), direction))
        self._color.rgb = coin.SbColor(*(HIT if end is not None else IDLE))
        self._dot_switch.whichChild = coin.SO_SWITCH_ALL if end is not None else coin.SO_SWITCH_NONE
        if end is not None:
            self._dot_xf.translation.setValue(*end)
        self.root.whichChild = coin.SO_SWITCH_ALL
