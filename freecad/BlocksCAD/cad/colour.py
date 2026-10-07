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
"""The colour of the selected objects (docs/ux-design.md, Modify panel).

Each press of the Colour face gives the selected objects the next colour of a fixed palette. A colour is a property of the view of
an object (`ShapeColor`), not of its shape, so it is not part of the undo history of the document. `next_colour` is pure Python."""

PALETTE = (
    ("Grey", (0.80, 0.80, 0.80)),
    ("Red", (0.86, 0.26, 0.24)),
    ("Orange", (0.95, 0.60, 0.15)),
    ("Yellow", (0.95, 0.85, 0.25)),
    ("Green", (0.30, 0.70, 0.35)),
    ("Blue", (0.28, 0.50, 0.90)),
    ("Violet", (0.60, 0.40, 0.85)),
    ("White", (1.00, 1.00, 1.00)),
)
TOLERANCE = 0.02


def next_colour(current):
    """(name, rgb) of the palette colour after `current` (an rgb triple); the first when `current` is not in the palette."""
    for i, (_, rgb) in enumerate(PALETTE):
        if all(abs(a - b) <= TOLERANCE for a, b in zip(rgb, current[:3])):
            return PALETTE[(i + 1) % len(PALETTE)]
    return PALETTE[0]


def cycle(doc, items):
    """Give the selected objects (whole or by an element of them) the next colour; each object goes on from its own colour. Returns
    the text for a toast."""
    names = []
    for name, _ in items:
        if name not in names and doc.getObject(name) is not None:
            names.append(name)
    views = [(doc.getObject(n).Label, doc.getObject(n).ViewObject) for n in names if getattr(doc.getObject(n), "ViewObject", None) is not None]
    if not views:
        return "Nothing selected" if not items else "Nothing to colour"
    colours = set()
    for _, view in views:
        name, rgb = next_colour(tuple(view.ShapeColor)[:3])
        view.ShapeColor = rgb
        colours.add(name)
    label = views[0][0] if len(views) == 1 else f"{len(views)} objects"
    return f"{label}: {colours.pop() if len(colours) == 1 else 'colours'}"
