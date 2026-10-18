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

Each press of the Colour button gives the selected objects the next colour of a fixed palette, in one undo step. The colour lives in the
property `VReeCADColour` of each object, which the undo history of the document keeps, and the view of the object (`ShapeColor`)
follows it: `cycle` sets both, and `sync` brings every view to its property after an undo or a redo. `next_colour` is pure Python."""

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
SWATCHES = PALETTE + (                 # the colours of the Colour panel of the values carousel: the palette and four more
    ("Teal", (0.20, 0.65, 0.65)),
    ("Pink", (0.92, 0.50, 0.70)),
    ("Brown", (0.50, 0.33, 0.20)),
    ("Black", (0.12, 0.12, 0.12)),
)


def next_colour(current):
    """(name, rgb) of the palette colour after `current` (an rgb triple); the first when `current` is not in the palette."""
    for i, (_, rgb) in enumerate(PALETTE):
        if all(abs(a - b) <= TOLERANCE for a, b in zip(rgb, current[:3])):
            return PALETTE[(i + 1) % len(PALETTE)]
    return PALETTE[0]


PROPERTY = "VReeCADColour"


def _views(doc, items):
    names = []
    for name, _ in items:
        if name not in names and doc.getObject(name) is not None:
            names.append(name)
    objects = [doc.getObject(n) for n in names if getattr(doc.getObject(n), "ViewObject", None) is not None]
    return [o for o in objects if hasattr(o.ViewObject, "ShapeColor")]          # a body, a group or a spreadsheet has no colour of its own


def _close(a, b):
    return all(abs(x - y) <= 1e-4 for x, y in zip(tuple(a)[:3], tuple(b)[:3]))


def cycle(doc, items):
    """Give the selected objects (whole or by an element of them) the next colour; each object goes on from its own colour. One undo
    step. Returns the text for a toast."""
    return _apply(doc, items, lambda current: next_colour(current))


def set_colour(doc, items, index):
    """Give the selected objects the colour `index` of `SWATCHES`, in one undo step. Returns the text for a toast."""
    chosen = SWATCHES[index]
    return _apply(doc, items, lambda current: chosen)


def _apply(doc, items, choose):
    objects = _views(doc, items)
    if not objects:
        return "Nothing selected" if not items else "Nothing to colour"
    for obj in objects:                    # the property starts with the colour the object has, outside the undo step
        if PROPERTY not in obj.PropertiesList:
            obj.addProperty("App::PropertyColor", PROPERTY, "VReeCAD", "Colour given in the VR viewer")
            setattr(obj, PROPERTY, tuple(obj.ViewObject.ShapeColor)[:3])
    colours = set()
    doc.openTransaction("Colour")
    try:
        for obj in objects:
            name, rgb = choose(tuple(getattr(obj, PROPERTY))[:3])
            setattr(obj, PROPERTY, rgb)
            obj.ViewObject.ShapeColor = rgb
            colours.add(name)
    except Exception:
        doc.abortTransaction()
        raise
    doc.commitTransaction()
    label = objects[0].Label if len(objects) == 1 else f"{len(objects)} objects"
    return f"{label}: {colours.pop() if len(colours) == 1 else 'colours'}"


def sync(doc):
    """Bring the view of every object that has been coloured to the colour of its property (after an undo or a redo)."""
    for obj in doc.Objects:
        view = getattr(obj, "ViewObject", None)
        if view is not None and PROPERTY in obj.PropertiesList and not _close(view.ShapeColor, getattr(obj, PROPERTY)):
            view.ShapeColor = tuple(getattr(obj, PROPERTY))[:3]
