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
"""Where a button of a controller model is (docs/ux-design.md, Grab tool). The hint over the A button needs the position of the
button of whichever model is shown, the model the runtime provides or the generated one, so it is taken from the geometry of the
named part of the model: the middle of the part, at its top, in the frame of the model."""

from pivy import coin

BUTTON_PARTS = ("button_a", "button_x")       # `button1` of the right and of the left Steam Frame and Touch controller


def button_anchor(model, names=BUTTON_PARTS, lift=0.0):
    """(x, y, z) in the frame of `model` (`render.gltf_coin.Model`) of the top of the first of the named parts, `lift` metres above it;
    None when the model has none of them."""
    for name in names:
        part = model.part(name)
        if part is None:
            continue
        action = coin.SoGetBoundingBoxAction(coin.SbViewportRegion())
        action.apply(part.switch)
        box = action.getBoundingBox()
        if box.isEmpty():
            continue
        low, high = box.getMin().getValue(), box.getMax().getValue()
        return ((low[0] + high[0]) / 2, high[1] + lift, (low[2] + high[2]) / 2)
    return None
