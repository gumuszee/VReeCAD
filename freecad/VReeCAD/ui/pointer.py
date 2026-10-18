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

from freecad.VReeCAD.core import mathutil as mu
from freecad.VReeCAD.ui import style

FREE_LENGTH = 0.6      # metres of beam when nothing is hit
BEAM_RADIUS = 0.0016
DOT_RADIUS = 0.006
IDLE = (0.55, 0.75, 1.0)
HIT = (1.0, 0.9, 0.4)
STEM = (0.4, 0.5, 0.65)


class Pointer:
    def __init__(self):
        self.root = coin.SoSwitch()
        self._show = style.Show(self.root)
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
        self._color = style.Paint(IDLE)
        sep.addChild(self._color.node)
        beam = coin.SoSeparator()
        beam_xf = coin.SoTransform()
        self._beam_at, self._beam_turn = beam_xf.translation, beam_xf.rotation
        beam.addChild(beam_xf)
        self._beam = coin.SoCylinder()
        self._beam.radius = BEAM_RADIUS
        self._beam_height = self._beam.height
        beam.addChild(self._beam)
        sep.addChild(beam)
        dot = coin.SoSeparator()
        dot_xf = coin.SoTranslation()
        self._dot_at = dot_xf.translation
        dot.addChild(dot_xf)
        self._dot = coin.SoSphere()
        self._dot.radius = DOT_RADIUS
        dot.addChild(self._dot)
        self._dot_switch = coin.SoSwitch()
        self._dot_switch.addChild(dot)
        self._dot_show = style.Show(self._dot_switch)
        sep.addChild(self._dot_switch)
        self.root.addChild(sep)

    def hide(self):
        self._show.set(False)

    def show(self, origin, direction, end=None):
        """Draw the beam from `origin` along `direction` (unit vector), ending at the point `end` when it hits something."""
        length = mu.length(mu.sub(end, origin)) if end is not None else FREE_LENGTH
        if length < 1e-3:
            self.hide()
            return
        middle = mu.add(origin, mu.mul(direction, length / 2))
        self._beam_height.setValue(length)
        self._beam_at.setValue(*middle)
        self._beam_turn.setValue(*mu.quat_between((0.0, 1.0, 0.0), direction))
        self._color.set(HIT if end is not None else IDLE)
        self._dot_show.set(end is not None)
        if end is not None:
            self._dot_at.setValue(*end)
        self._show.set(True)


class _TipShape:
    """The cone and the sphere of a tip in one depth setting. `visible` colours the parts that lie in front of the scene (depth
    test on), the other pass draws the same shape without a depth test in the inverted colours: it shows wherever the tip is behind
    or inside something."""

    def __init__(self, depth_test, invert):
        self.sep = coin.SoSeparator()
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.sep.addChild(light)
        depth = coin.SoDepthBuffer()
        depth.test.setValue(depth_test)
        depth.getField("write").setValue(False)
        self.sep.addChild(depth)
        self.invert = invert
        stem = coin.SoSeparator()
        self._stem_color = style.color(self._shade(STEM))
        stem.addChild(self._stem_color)
        stem_xf = coin.SoTransform()
        self._stem_at, self._stem_turn = stem_xf.translation, stem_xf.rotation
        stem.addChild(stem_xf)
        self._stem = coin.SoCone()           # the apex is at +Y: it is turned to point at the tip
        self._stem.bottomRadius = TipMarker.BASE_RADIUS
        self._stem_height = self._stem.height
        stem.addChild(self._stem)
        self.sep.addChild(stem)
        tip = coin.SoSeparator()
        self._color = style.Paint(self._shade(IDLE))
        tip.addChild(self._color.node)
        tip_xf = coin.SoTranslation()
        self._tip_at = tip_xf.translation
        tip.addChild(tip_xf)
        sphere = coin.SoSphere()
        sphere.radius = TipMarker.TIP_RADIUS
        tip.addChild(sphere)
        self.sep.addChild(tip)

    def _shade(self, rgb):
        return style.invert(rgb) if self.invert else rgb

    def show(self, start, tip, touching):
        span = mu.sub(tip, start)
        length = mu.length(span)
        if length > 1e-3:
            direction = mu.mul(span, 1.0 / length)
            self._stem_height.setValue(length)
            self._stem_at.setValue(*mu.add(start, mu.mul(span, 0.5)))
            self._stem_turn.setValue(*mu.quat_between((0.0, 1.0, 0.0), direction))
        else:
            self._stem_height.setValue(1e-4)
        self._tip_at.setValue(*tip)
        self._color.set(self._shade(HIT if touching else IDLE))


class TipMarker:
    """The tip of a controller in tip mode (docs/ux-design.md, Pointer): a thin cone that narrows from the controller to the tip and a
    small sphere at the tip, drawn over the scene so the tip is never lost. The sphere is highlighted while it touches something.
    The parts of the tip that lie behind or inside the model or a panel are drawn in the inverted colours, so the colour tells whether
    the tip is in front of or in contact with what it should act on."""
    BASE_RADIUS = 0.004
    TIP_RADIUS = 0.0035

    def __init__(self):
        self.root = coin.SoSwitch()
        self._show = style.Show(self.root)
        sep = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        sep.addChild(pick)
        # the inverted pass first (no depth test: always there), the normal pass over it (depth test: only where nothing is in front)
        self._passes = [_TipShape(False, True), _TipShape(True, False)]
        for shape in self._passes:
            sep.addChild(shape.sep)
        self.root.addChild(sep)

    def hide(self):
        self._show.set(False)

    def show(self, start, tip, touching=False):
        """Draw the tip at `tip` with its cone from `start` (the controller)."""
        for shape in self._passes:
            shape.show(start, tip, touching)
        self._show.set(True)
