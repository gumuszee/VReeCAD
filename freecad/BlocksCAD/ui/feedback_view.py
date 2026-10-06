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
tooltip of a face, the readout of a tool option next to the tool hand. All are `LabelPlate`s, drawn over the model in the
colours and font of the palette."""

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import style
from freecad.BlocksCAD.ui.ring_view import DEPTH

CHAR_WIDTH = 0.0062     # metres per character of a label (Segoe UI Bold at the interface text size)
PAD = 0.016             # plate margin left and right of the text
HEIGHT = 0.03           # plate height of one line
TOAST_DISTANCE = 0.8    # metres in front of the head
TOAST_DROP = 0.2        # metres below the line of sight
TOAST_SCALE = 1.5      # toasts are larger than the other labels: they are read at a distance
TOAST_PITCH = 0.06      # metres between stacked toasts
READOUT_LIFT = 0.07     # metres above the pointer of the tool hand
TOOLTIP_LIFT = 0.045    # metres above the centre of a face


class LabelPlate:
    """A plate that fits one line of text. `place` puts it in space; `hide` removes it."""

    def __init__(self, rgb=style.PLATE, text_rgb=style.TEXT):
        self.root = coin.SoSwitch()
        self.root.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        self._transform = coin.SoTransform()
        sep.addChild(self._transform)
        sep.addChild(style.color(rgb))
        self._plate = coin.SoCube()
        self._plate.height, self._plate.depth = HEIGHT, DEPTH
        sep.addChild(self._plate)
        text = coin.SoSeparator()
        move = coin.SoTranslation()
        move.translation.setValue(0.0, -0.0035, DEPTH * 0.5 + 0.0005)
        text.addChild(move)
        text.addChild(style.color(text_rgb))
        text.addChild(style.text_scale())
        self._text = coin.SoText3()
        self._text.justification = coin.SoText3.CENTER
        text.addChild(self._text)
        sep.addChild(text)
        self.root.addChild(sep)
        self.label = None

    def set_text(self, text):
        if text != self.label:
            self.label = text
            self._text.string = text
            self._plate.width = len(text) * CHAR_WIDTH + 2 * PAD

    def place(self, centre, right, up, scale=1.0):
        self._transform.translation.setValue(*centre)
        self._transform.rotation.setValue(*mu.quat_from_basis(right, up, mu.cross(right, up)))
        self._transform.scaleFactor.setValue(scale, scale, scale)
        self.root.whichChild = coin.SO_SWITCH_ALL

    def hide(self):
        self.root.whichChild = coin.SO_SWITCH_NONE


def head_axes(head):
    """(right, up, forward) of a head pose."""
    q = head.orientation
    return mu.rotate(q, (1.0, 0.0, 0.0)), mu.rotate(q, (0.0, 1.0, 0.0)), mu.rotate(q, (0.0, 0.0, -1.0))


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
        for plate in self._toasts + [self._tooltip, self._readout]:
            self.root.addChild(plate.root)

    def update(self, head, toasts, tooltip=None, readout=None):
        """`toasts`: the `toast.Toast`s to draw, oldest first. `tooltip`: (text, centre of the face, u, v of its panel) or None.
        `readout`: (text, position of the tool hand's pointer) or None."""
        right, up, forward = head_axes(head)
        base = mu.add(head.position, mu.add(mu.mul(forward, TOAST_DISTANCE), mu.mul(up, -TOAST_DROP)))
        shown = list(toasts)[-len(self._toasts):]
        for i, plate in enumerate(self._toasts):
            if i < len(shown):
                plate.set_text(shown[i].text)
                height = (len(shown) - 1 - i) * TOAST_PITCH      # the newest at the bottom
                plate.place(mu.add(base, mu.mul(up, height)), right, up, max(shown[i].scale * TOAST_SCALE, 0.01))
            else:
                plate.hide()
        if tooltip is not None:
            text, centre, u, v = tooltip
            self._tooltip.set_text(text)
            self._tooltip.place(mu.add(centre, mu.mul(v, TOOLTIP_LIFT)), u, v)
        else:
            self._tooltip.hide()
        if readout is not None:
            text, position = readout
            self._readout.set_text(text)
            self._readout.place(mu.add(position, mu.mul(up, READOUT_LIFT)), right, up)
        else:
            self._readout.hide()
