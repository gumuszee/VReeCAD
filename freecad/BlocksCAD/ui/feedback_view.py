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
"""Coin3D drawing of the small messages (docs/ux-design.md, Toasts, tooltips and readouts): toasts in front of the head, the
tooltip of a face, the readout of a tool option next to the tool hand, and the padlock over the A button. The text ones are
`LabelPlate`s, drawn over the model in the colours and font of the palette."""

import math
import textwrap

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import style
from freecad.BlocksCAD.ui.ring_view import DEPTH

PAD = 0.016             # plate margin left and right of the text
HEIGHT = 0.03           # plate height of one line
LINE_PITCH = 0.0108     # metres between the lines of a text of several lines (the font at the interface text size)
TOOLTIP_CHARS = 36      # a tooltip is broken into lines of about this many characters
TOAST_DISTANCE = 0.8    # metres in front of the head
TOAST_DROP = 0.2        # metres below the line of sight
TOAST_SCALE = 1.5      # toasts are larger than the other labels: they are read at a distance
TOAST_PITCH = 0.06      # metres between stacked toasts
WRIST_SCALE = 0.6       # toasts on the wrist are smaller: they are read at arm's length
WRIST_PITCH = 0.028     # metres between stacked toasts on the wrist
TOOLTIP_LIFT = 0.045    # metres above the centre of a face
TOOLTIP_FRONT = 0.01875  # metres in front of the panel, towards the head
HELP_SCALE = 0.6        # the controls cards are read at arm's length like the toasts on the wrist
HELP_PITCH = 0.03       # metres between the lines of a controls card (at the scale of the card)
HELP_LINES = 8          # the most lines a card holds, the title not counted


class _Placement:
    """The fields of a `SoTransform` that puts a flat label in space, written only when the place changes."""

    def __init__(self, transform):
        self._at, self._turn, self._scale = transform.translation, transform.rotation, transform.scaleFactor
        self._key = None

    def set(self, centre, right, up, scale):
        key = (centre, right, up, scale)
        if key != self._key:
            self._key = key
            self._at.setValue(*centre)
            self._turn.setValue(*mu.quat_from_basis(right, up, mu.cross(right, up)))
            self._scale.setValue(scale, scale, scale)


class LockIcon:
    """A padlock on a small dark plate, open or closed: the hint over the button that locks a grab to the grid and the angles. It
    lies in the plane of the top of the controller over the button and turns with the controller. Closed is orange (locked),
    open is dim."""
    SIZE = 0.034
    SCALE = 0.42             # the drawing is made 3.4 cm wide and shown at this fraction: about 14 mm

    def __init__(self):
        self.root = coin.SoSwitch()
        self._show = style.Show(self.root)
        sep = coin.SoSeparator()
        transform = coin.SoTransform()
        self._transform = transform
        self._place = _Placement(transform)
        sep.addChild(transform)
        sep.addChild(style.color(style.PLATE))
        plate = coin.SoCube()
        plate.width = plate.height = self.SIZE
        plate.depth = DEPTH
        sep.addChild(plate)
        self._states = coin.SoSwitch()               # 0: open, 1: closed
        for closed in (False, True):
            one = coin.SoSeparator()
            colour = style.ACTIVE if closed else style.TEXT_DIM
            one.addChild(style.color(colour))
            body_move = coin.SoTranslation()
            body_move.translation.setValue(0.0, -0.0045, DEPTH * 0.5 + 0.0004)
            one.addChild(body_move)
            body = coin.SoCube()
            body.width, body.height, body.depth = 0.017, 0.012, DEPTH
            one.addChild(body)
            shackle = coin.SoSeparator()
            width = coin.SoDrawStyle()
            width.lineWidth = 3.0
            shackle.addChild(width)
            lift = 0.0 if closed else 0.0045                    # an open padlock has its shackle raised and swung aside
            arc = [(0.0055 * math.cos(math.pi * i / 12) - (0.0 if closed else 0.002), 0.006 + lift + 0.0055 * math.sin(math.pi * i / 12), 0.0)
                   for i in range(13)]
            coords = coin.SoCoordinate3()
            legs = [(arc[0][0], 0.006 + (0.0 if closed else lift), 0.0)] + arc + [(arc[-1][0], 0.006 + (0.0 if closed else 0.0), 0.0)]
            coords.point.setValues(0, len(legs), legs)
            shackle.addChild(coords)
            line = coin.SoLineSet()
            line.numVertices.setValue(len(legs))
            shackle.addChild(line)
            one.addChild(shackle)
            self._states.addChild(one)
        sep.addChild(self._states)
        self._closed = self._states.whichChild
        self._closed_now = None
        self.root.addChild(sep)

    def place(self, centre, right, up, closed):
        self._place.set(centre, right, up, self.SCALE)
        if closed != self._closed_now:
            self._closed_now = closed
            self._closed.setValue(1 if closed else 0)
        self._show.set(True)

    def hide(self):
        self._show.set(False)


_MEASURE = None


def text_width(text):
    """The width in metres of the longest line of `text` (lines separated by newlines) in the interface font at the interface size."""
    global _MEASURE
    if _MEASURE is None:
        root = coin.SoSeparator()
        root.addChild(style.text_scale())
        node = coin.SoText3()
        root.addChild(node)
        _MEASURE = (root, node, coin.SoGetBoundingBoxAction(coin.SbViewportRegion(100, 100)))
    root, node, action = _MEASURE
    lines = text.split("\n")
    node.string.setValues(0, len(lines), lines)
    node.string.setNum(len(lines))                      # setValues keeps the lines after the last one it sets
    action.apply(root)
    box = action.getBoundingBox()
    return box.getMax().getValue()[0] - box.getMin().getValue()[0] if not box.isEmpty() else 0.0


class LabelPlate:
    """A plate that fits its text, one line or several (separated by newlines). `place` puts it in space; `hide` removes it."""

    def __init__(self, rgb=style.PLATE, text_rgb=style.TEXT):
        self.root = coin.SoSwitch()
        self._show = style.Show(self.root)
        sep = coin.SoSeparator()
        transform = coin.SoTransform()
        self._transform = transform
        self._place = _Placement(transform)
        sep.addChild(transform)
        sep.addChild(style.color(rgb))
        self._plate = coin.SoCube()
        self._plate.height, self._plate.depth = HEIGHT, DEPTH
        self._plate_width = self._plate.width
        sep.addChild(self._plate)
        text = style.cached(coin.SoSeparator())
        move = coin.SoTranslation()
        self._move = move.translation
        move.translation.setValue(0.0, -0.0035, DEPTH * 0.5 + 0.0005)
        text.addChild(move)
        text.addChild(style.color(text_rgb))
        text.addChild(style.text_scale())
        self._text = coin.SoText3()
        self._text.justification = coin.SoText3.CENTER
        self._string = self._text.string
        text.addChild(self._text)
        sep.addChild(text)
        self.root.addChild(sep)
        self._plate_height = self._plate.height
        self.label = None
        self._width = 0.0
        self.lines = 1

    def set_text(self, text, width=0.0):
        """The text of the plate; the plate is as wide as `width` metres of text when the text is narrower (so the lines of a card are as
        wide as its longest)."""
        if text != self.label or width != self._width:
            self.label, self._width = text, width
            lines = text.split("\n")
            self.lines = len(lines)
            extra = (self.lines - 1) * LINE_PITCH
            self._string.setValues(0, self.lines, lines)
            self._string.setNum(self.lines)
            self._move.setValue(0.0, extra / 2.0 - 0.0035, DEPTH * 0.5 + 0.0005)      # the block of lines is centred on the plate
            self._plate_height.setValue(HEIGHT + extra)
            self._plate_width.setValue(max(text_width(text), width) + 2 * PAD)

    def place(self, centre, right, up, scale=1.0):
        self._place.set(centre, right, up, scale)
        self._show.set(True)

    def hide(self):
        self._show.set(False)


class HelpCard:
    """The controls card of one controller: a title and up to `HELP_LINES` lines on plates of one width, stacked downwards from the
    title, facing the head."""

    def __init__(self):
        self.title = LabelPlate(style.ACTIVE, style.TEXT_ON_ACTIVE)
        self.lines = [LabelPlate(style.FACE) for _ in range(HELP_LINES)]

    @property
    def plates(self):
        return [self.title] + self.lines

    def update(self, card, right, up):
        """`card`: (centre of the title, title, lines) or None to hide it; `right` and `up` are the axes of the plates."""
        if card is None:
            for plate in self.plates:
                plate.hide()
            return
        centre, title, lines = card
        lines = lines[:HELP_LINES]
        width = max(text_width(text) for text in [title] + lines)
        self.title.set_text(title, width)
        self.title.place(centre, right, up, HELP_SCALE)
        for i, plate in enumerate(self.lines):
            if i < len(lines):
                plate.set_text(lines[i], width)
                plate.place(mu.add(centre, mu.mul(up, -(i + 1) * HELP_PITCH * HELP_SCALE)), right, up, HELP_SCALE)
            else:
                plate.hide()


def head_axes(head):
    """(right, up, forward) of a head pose."""
    q = head.orientation
    return mu.rotate(q, (1.0, 0.0, 0.0)), mu.rotate(q, (0.0, 1.0, 0.0)), mu.rotate(q, (0.0, 0.0, -1.0))


def billboard_axes(position, eye, up_hint):
    """(right, up) of a plate at `position` that faces `eye` and stands upright as far as `up_hint` allows."""
    normal = mu.sub(eye, position)
    if mu.length(normal) < 1e-6:
        return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    normal = mu.normalize(normal)
    right = mu.cross(up_hint, normal)
    if mu.length(right) < 1e-6:                  # looking straight along the hint: keep any upright plate
        right = mu.cross((0.0, 1.0, 0.0) if abs(normal[1]) < 0.99 else (1.0, 0.0, 0.0), normal)
    right = mu.normalize(right)
    return right, mu.cross(normal, right)


class FeedbackView:
    """The toasts, the tooltip and the readout; one scene node for all three."""

    def __init__(self, max_toasts=3):
        self.root = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.root.addChild(light)
        depth = coin.SoDepthBuffer()      # drawn over the model, never hidden by it
        depth.test.setValue(False)
        depth.getField("write").setValue(False)
        self.root.addChild(depth)
        self.root.addChild(style.font())
        self._toasts = [LabelPlate(style.FACE) for _ in range(max_toasts)]
        self._tooltip = LabelPlate(style.PLATE, style.TEXT)
        self._readout = LabelPlate(style.GRAB, style.TEXT_ON_ACTIVE)
        self._lock = LockIcon()
        self._cards = [HelpCard(), HelpCard()]
        for plate in self._toasts + [self._tooltip, self._readout, self._lock] + self._cards[0].plates + self._cards[1].plates:
            self.root.addChild(plate.root)

    def update(self, head, toasts, tooltip=None, readout=None, lock=None, wrist=None, cards=None):
        """`toasts`: the `toast.Toast`s to draw, oldest first. `tooltip`: (text, centre of the face, u, v of its panel) or None.
        `readout`: the text of the readout of a gesture or a tool option, or None; it hangs on the wrist like the toasts, at the bottom of the
        stack (the toasts stand above it), so it never covers what the hand works on. `lock`: (position, right, up, locked) of the padlock on the controller, or None.
        `wrist`: the point on the controller where the toasts are attached, or None to show them in front of the head.
        `cards`: up to two (centre of the title, title, lines) of the controls cards, or None."""
        right, up, forward = head_axes(head)
        if wrist is not None:
            base = wrist
            toast_scale, pitch = WRIST_SCALE, WRIST_PITCH
            toast_right, toast_up = billboard_axes(wrist, head.position, up)
        else:
            base = mu.add(head.position, mu.add(mu.mul(forward, TOAST_DISTANCE), mu.mul(up, -TOAST_DROP)))
            toast_scale, pitch = TOAST_SCALE, TOAST_PITCH
            toast_right, toast_up = right, up
        shown = list(toasts)[-len(self._toasts):]
        first = pitch if readout is not None else 0.0      # the toasts stand one place higher while the readout is shown
        for i, plate in enumerate(self._toasts):
            if i < len(shown):
                plate.set_text(shown[i].text)
                height = first + (len(shown) - 1 - i) * pitch      # the newest at the bottom
                plate.place(mu.add(base, mu.mul(toast_up, height)), toast_right, toast_up, max(shown[i].scale * toast_scale, 0.01))
            else:
                plate.hide()
        if tooltip is not None:
            text, centre, u, v = tooltip
            self._tooltip.set_text("\n".join(textwrap.wrap(text, TOOLTIP_CHARS)))
            lift = TOOLTIP_LIFT + (self._tooltip.lines - 1) * LINE_PITCH / 2.0       # the bottom edge stays where a one line tooltip has it
            normal = mu.cross(u, v)
            if mu.dot(normal, mu.sub(head.position, centre)) < 0.0:
                normal = mu.mul(normal, -1.0)
            self._tooltip.place(mu.add(mu.add(centre, mu.mul(v, lift)), mu.mul(normal, TOOLTIP_FRONT)), u, v)
        else:
            self._tooltip.hide()
        if readout is not None:
            self._readout.set_text(readout)
            self._readout.place(base, toast_right, toast_up, toast_scale)
        else:
            self._readout.hide()
        if lock is not None:
            self._lock.place(lock[0], lock[1], lock[2], lock[3])
        else:
            self._lock.hide()
        cards = list(cards or [])
        for i, view in enumerate(self._cards):
            if i < len(cards):
                card_right, card_up = billboard_axes(cards[i][0], head.position, up)
                view.update(cards[i], card_right, card_up)
            else:
                view.update(None, right, up)
