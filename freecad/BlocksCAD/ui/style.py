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

import colorsys
import zlib
from dataclasses import dataclass

from pivy import coin

PLATE = (0.10, 0.11, 0.14)
PLATE_LIT = (0.15, 0.17, 0.23)
FACE = (0.20, 0.22, 0.28)
EMPTY = (0.13, 0.14, 0.17)
PICKED = (0.27, 0.31, 0.44)       # the slider of the value that is picked
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
PANEL_TEXT = 0.8              # the text of the panels of the carousel is this fraction of `TEXT_SCALE`


@dataclass(frozen=True)
class Palette:
    """The colours of one panel of the carousel: the plate behind it, its title bar, its faces, the slot of a missing face."""
    plate: tuple = PLATE
    plate_lit: tuple = PLATE_LIT
    title: tuple = PLATE
    face: tuple = FACE
    empty: tuple = EMPTY
    picked: tuple = PICKED
    title_text: tuple = TEXT_DIM
    groove: tuple = GROOVE


def luminance(rgb):
    """Relative luminance of an sRGB colour (0 to 1)."""
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _with_luminance(hue, saturation, level):
    """The colour of a hue and saturation whose luminance is `level`."""
    low, high = 0.0, 1.0
    for _ in range(24):
        value = (low + high) / 2
        if luminance(colorsys.hsv_to_rgb(hue, saturation, value)) < level:
            low = value
        else:
            high = value
    return tuple(round(c, 4) for c in colorsys.hsv_to_rgb(hue, saturation, high))


def tinted(hue):
    """The dark, muted palette of a hue (0 to 1): every colour of the grey default tinted to the hue at the luminance of the
    original, so a panel is told apart at a glance while white text, the hover blue and the active orange keep the contrast they
    have on the default panel."""
    def tint(grey, saturation):
        return _with_luminance(hue, saturation, luminance(grey))
    middle = tuple((a + b) / 2 for a, b in zip(PLATE, PLATE_LIT))
    return Palette(plate=tint(PLATE, 0.55), plate_lit=tint(PLATE_LIT, 0.52), title=tint(middle, 0.55),
                   face=tint(FACE, 0.50), empty=tint(EMPTY, 0.50), picked=tint(PICKED, 0.45), title_text=tint(TEXT_DIM, 0.18),
                   groove=tint(GROOVE, 0.18))


DEFAULT_PALETTE = Palette()
PANEL_HUES = {"Tools": 0.38, "Edit": 0.92, "View": 0.11, "Session": 0.50}   # the default panels, green, rose, ochre, teal
SPARE_HUES = (0.75, 0.02, 0.25, 0.45, 0.62)                                  # panels of other names take one of these by their name


def panel_palette(name, plain=False):
    """The palette of the panel called `name`: the tint of the default panels, a tint picked by the name for any other panel and the
    grey default for a `plain` panel (the panels of the value module)."""
    if plain:
        return DEFAULT_PALETTE
    hue = PANEL_HUES.get(name)
    if hue is None:
        hue = SPARE_HUES[zlib.crc32(name.encode("utf-8")) % len(SPARE_HUES)]
    return tinted(hue)


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


class Paint:
    """A `SoBaseColor` that is written only when the colour changes: every write notifies the scene graph, which drops the render
    caches above it, and a pivy field write costs about 20 microseconds."""

    def __init__(self, rgb):
        self.node = color(rgb)
        self._field = self.node.rgb
        self.rgb = tuple(rgb)

    def set(self, rgb):
        if rgb != self.rgb:
            self.rgb = rgb
            self._field.setValue(*rgb)


def text_scale(factor=1.0):
    node = coin.SoScale()
    s = TEXT_SCALE * factor
    node.scaleFactor.setValue(s, s, s)
    return node
