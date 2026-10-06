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
"""The look shared by every 3D element of the interface (docs/ux-design.md, Visual style): colours, the font and text sizes.
Text is `SoText3` (glyph outlines) at a fixed physical size: Coin's default glyph is 10 units high, so `TEXT_SCALE` 0.0009 gives
glyphs of about 9 mm. Everything is unlit so it never depends on the scene lighting."""

from pivy import coin

PLATE = (0.10, 0.11, 0.14)
PLATE_LIT = (0.15, 0.17, 0.23)
FACE = (0.20, 0.22, 0.28)
EMPTY = (0.13, 0.14, 0.17)
HOVER = (0.30, 0.45, 0.80)
ACTIVE = (0.95, 0.65, 0.10)
GRAB = (0.95, 0.65, 0.10)
DROP = (0.18, 0.36, 0.24)
TEXT = (1.0, 1.0, 1.0)
TEXT_DIM = (0.7, 0.75, 0.9)
TEXT_ON_ACTIVE = (0.05, 0.05, 0.05)
GROOVE = (0.4, 0.42, 0.5)

FONT = "Segoe UI:Bold"       # falls back to Coin's default font where the family is missing
TEXT_SCALE = 0.0009           # label glyphs, about 9 mm
LINE_HEIGHT = 0.0105


def invert(rgb):
    """The colour with every channel inverted."""
    return tuple(1.0 - c for c in rgb)


def font():
    node = coin.SoFont()
    node.name = FONT
    return node


def color(rgb):
    node = coin.SoBaseColor()
    node.rgb = coin.SbColor(*rgb)
    return node


def text_scale(factor=1.0):
    node = coin.SoScale()
    s = TEXT_SCALE * factor
    node.scaleFactor.setValue(s, s, s)
    return node
