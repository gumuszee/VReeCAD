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
"""The scale ruler shown while both grips hold the world (docs/ux-design.md, Navigation).

A line joins the two hands. It is a ruler in the measurement system of the document: ticks stand at round lengths of the model
(as they are at the current scale), labelled with their length, so the line reads as a physical measure. Below the line a plate shows
the scale ratio (`4 : 1`), the length between the hands and the rotation mode. The ruler is drawn in the stage frame on top of
everything (no depth test), so the model never hides it, and every line has a dark outline so it reads on any background."""

import math

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import units
from freecad.BlocksCAD.core.navigation import format_scale
from freecad.BlocksCAD.ui import style

UP = (0.0, 1.0, 0.0)
TARGET_SPACING = 0.07      # metres between labelled ticks
LINE_W = 0.0035
OUTLINE = 0.0016           # extra width of the dark outline on each side
MAJOR_LEN, MINOR_LEN = 0.026, 0.013
LABEL_LIFT = 0.04
LABEL_SIZE = 1.25
LABELS = 24
MAX_MINOR = 160
CHAR_W = 0.0056            # approximate glyph advance, to size the plates behind the labels
PLATE_DEPTH = 0.002
BRIGHT = (0.96, 0.96, 1.0)


class _LineSet:
    """A set of quads drawn as one flat shape."""

    def __init__(self, rgb):
        self.sep = coin.SoSeparator()
        self.sep.addChild(style.color(rgb))
        self._points = coin.SoCoordinate3()
        self._faces = coin.SoFaceSet()
        self.sep.addChild(self._points)
        self.sep.addChild(self._faces)

    def set(self, quads):
        points = [corner for quad in quads for corner in quad]
        self._points.point.setNum(len(points))      # drop the entries of a longer previous set
        self._points.point.setValues(0, len(points), points)
        self._faces.numVertices.setNum(len(quads))
        self._faces.numVertices.setValues(0, len(quads), [4] * len(quads))


class _Label:
    def __init__(self, parent):
        self.switch = coin.SoSwitch()
        self._on = style.Show(self.switch)
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        self._at, self._turn = self.transform.translation, self.transform.rotation
        sep.addChild(self.transform)
        plate_sep = coin.SoSeparator()
        plate_sep.addChild(style.color(style.PLATE))
        move = coin.SoTranslation()
        move.translation.setValue(0.0, 0.0, -PLATE_DEPTH)
        plate_sep.addChild(move)
        self.plate = coin.SoCube()
        self.plate.depth = PLATE_DEPTH
        plate_sep.addChild(self.plate)
        sep.addChild(plate_sep)
        text_sep = coin.SoSeparator()
        move = coin.SoTranslation()
        move.translation.setValue(0.0, 0.0, 0.0005)
        text_sep.addChild(move)
        self.color = style.color(style.TEXT)
        text_sep.addChild(self.color)
        self.scale = style.text_scale()
        text_sep.addChild(self.scale)
        self.text = coin.SoText3()
        self.text.justification = coin.SoText3.CENTER
        text_sep.addChild(self.text)
        sep.addChild(text_sep)
        self.switch.addChild(sep)
        parent.addChild(self.switch)
        self._shown = None

    def show(self, lines, position, rotation, rgb=style.TEXT, factor=1.0):
        """Show up to three lines of text centred on `position`; the plate fits the text."""
        key = (tuple(lines), rgb, factor)
        if key != self._shown:
            self._shown = key
            self.text.string.setNum(len(lines))      # drop the lines of a longer previous text
            self.text.string.setValues(0, len(lines), list(lines))
            self.color.rgb = coin.SbColor(*rgb)
            s = style.TEXT_SCALE * factor
            self.scale.scaleFactor.setValue(s, s, s)
            height = len(lines) * style.LINE_HEIGHT * factor
            self.plate.width = max(len(line) for line in lines) * CHAR_W * factor + 0.012
            self.plate.height = height + 0.008
        self._at.setValue(*position)
        self._turn.setValue(*rotation)
        self._on.set(True)

    def hide(self):
        self._on.set(False)


class Ruler:
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
        depth = coin.SoDepthBuffer()      # drawn over the model, never hidden by it
        depth.test.setValue(False)
        depth.getField("write").setValue(False)   # `write` is shadowed by SoNode.write in pivy
        sep.addChild(depth)
        sep.addChild(style.font())
        self._outline = _LineSet(style.PLATE)
        self._lines = _LineSet(BRIGHT)
        sep.addChild(self._outline.sep)
        sep.addChild(self._lines.sep)
        self._labels = [_Label(sep) for _ in range(LABELS)]
        self._ratio = _Label(sep)
        self._info = _Label(sep)
        self.root.addChild(sep)

    def hide(self):
        self._show.set(False)

    def update(self, left, right, head, scale, mm_to_stage, system, level, locked=False):
        """Draw the ruler between the hand positions `left` and `right` (stage metres). `scale` is the world scale (stage metres per
        world metre), `mm_to_stage` the stage length of one document millimetre at scale 1, `head` an `input.Pose`."""
        span = mu.sub(right, left)
        distance = mu.length(span)
        if distance < 0.03:
            self.hide()
            return
        self._show.set(True)
        direction = mu.mul(span, 1.0 / distance)
        middle = mu.lerp(left, right, 0.5)
        to_head = mu.sub(head.position, middle)
        view = mu.normalize(to_head) if mu.length(to_head) > 1e-6 else (0.0, 0.0, 1.0)
        side = mu.cross(view, direction)             # in the plane facing the head, across the line
        if mu.length(side) < 1e-6:
            side = mu.cross(UP, direction)
        side = mu.normalize(side)
        head_right = mu.rotate(head.orientation, (1.0, 0.0, 0.0))
        up_dot = mu.dot(side, UP)
        if up_dot < -1e-3 or (abs(up_dot) <= 1e-3 and mu.dot(side, head_right) < 0):
            side = mu.mul(side, -1.0)
        face = mu.quat_multiply(mu.look_at(middle, head.position), mu.quat_from_axis_angle(UP, math.pi))

        k = scale * mm_to_stage                      # stage metres per document millimetre
        length_mm = distance / k
        spec = units.ruler_spec(system, TARGET_SPACING / k)
        minor_mm, divisions = spec.minor_mm, max(1, round(spec.step_mm / spec.minor_mm))
        if length_mm / minor_mm > MAX_MINOR:       # too dense to read: labelled ticks only
            minor_mm, divisions = spec.step_mm, 1
        minors = int(length_mm / minor_mm + 1e-9)
        outline, bright = [], []

        def band(a, b, width):
            w = mu.mul(side, width / 2)
            return (mu.sub(a, w), mu.sub(b, w), mu.add(b, w), mu.add(a, w))

        def along(mm):
            return mu.add(left, mu.mul(direction, mm * k))

        base = band(left, right, LINE_W)
        bright.append(base)
        outline.append(band(mu.sub(left, mu.mul(direction, OUTLINE)), mu.add(right, mu.mul(direction, OUTLINE)), LINE_W + 2 * OUTLINE))
        shown = 0
        for i in range(minors + 1):
            major = i % divisions == 0
            length = MAJOR_LEN if major else MINOR_LEN
            p = along(i * minor_mm)
            tip = mu.add(p, mu.mul(side, length))
            bright.append(_tick(p, tip, direction, LINE_W * 0.6))
            outline.append(_tick(mu.sub(p, mu.mul(side, OUTLINE)), mu.add(tip, mu.mul(side, OUTLINE)), direction,
                                 LINE_W * 0.6 + 2 * OUTLINE))
            if major and shown < LABELS:
                text = "0" if i == 0 else units.format_length(i * minor_mm, system, spec.unit)
                self._labels[shown].show([text], mu.add(p, mu.mul(side, LABEL_LIFT)), face, factor=LABEL_SIZE)
                shown += 1
        for label in self._labels[shown:]:
            label.hide()
        self._outline.set(outline)
        self._lines.set(bright)
        self._ratio.show([format_scale(scale)], mu.sub(middle, mu.mul(side, 0.055)), face, rgb=style.ACTIVE, factor=2.4)
        self._info.show([units.format_length(length_mm, system), mode_text(level, locked)],
                        mu.sub(middle, mu.mul(side, 0.125)), face, rgb=style.TEXT_DIM, factor=1.1)

    def show_single(self, hand, head, scale, level, locked):
        """With one grip there is no span to measure: only the scale ratio and the modes float above the gripping hand."""
        self._show.set(True)
        self._outline.set([])
        self._lines.set([])
        for label in self._labels:
            label.hide()
        face = mu.quat_multiply(mu.look_at(hand, head.position), mu.quat_from_axis_angle(UP, math.pi))
        self._ratio.show([format_scale(scale)], mu.add(hand, (0.0, 0.12, 0.0)), face, rgb=style.ACTIVE, factor=2.4)
        self._info.show([mode_text(level, locked)], mu.add(hand, (0.0, 0.065, 0.0)), face, rgb=style.TEXT_DIM, factor=1.1)


def mode_text(level, locked):
    """The rotation mode and the scale lock as shown on the plate."""
    return ("level" if level else "free orbit") + (", 1 : 1 locked" if locked else "")


def _tick(a, b, direction, width):
    w = mu.mul(direction, width / 2)
    return (mu.sub(a, w), mu.sub(b, w), mu.add(b, w), mu.add(a, w))
