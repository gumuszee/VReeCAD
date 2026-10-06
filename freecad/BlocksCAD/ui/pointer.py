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


class TipMarker:
    """The tip of a controller in tip mode (docs/ux-design.md, Pointer): a small sphere at the tip on a thin stem that joins it to the
    controller, drawn on top of the scene. The sphere is highlighted while it touches something."""
    STEM_RADIUS = 0.001
    TIP_RADIUS = 0.006

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
        stem = coin.SoSeparator()
        stem.addChild(style.color((0.4, 0.5, 0.65)))
        self._stem_xf = coin.SoTransform()
        stem.addChild(self._stem_xf)
        self._stem = coin.SoCylinder()
        self._stem.radius = self.STEM_RADIUS
        stem.addChild(self._stem)
        sep.addChild(stem)
        tip = coin.SoSeparator()
        self._color = style.color(IDLE)
        tip.addChild(self._color)
        self._tip_xf = coin.SoTranslation()
        tip.addChild(self._tip_xf)
        sphere = coin.SoSphere()
        sphere.radius = self.TIP_RADIUS
        tip.addChild(sphere)
        sep.addChild(tip)
        self.root.addChild(sep)

    def hide(self):
        self.root.whichChild = coin.SO_SWITCH_NONE

    def show(self, start, tip, touching=False):
        """Draw the tip at `tip` with its stem from `start` (the controller)."""
        span = mu.sub(tip, start)
        length = mu.length(span)
        if length > 1e-3:
            direction = mu.mul(span, 1.0 / length)
            self._stem.height = length
            self._stem_xf.translation.setValue(*mu.add(start, mu.mul(span, 0.5)))
            self._stem_xf.rotation.setValue(*mu.quat_between((0.0, 1.0, 0.0), direction))
            self._stem_xf.scaleFactor.setValue(1.0, 1.0, 1.0)
        else:
            self._stem.height = 1e-4
        self._tip_xf.translation.setValue(*tip)
        self._color.rgb = coin.SbColor(*(HIT if touching else IDLE))
        self.root.whichChild = coin.SO_SWITCH_ALL
