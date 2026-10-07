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
"""Parametric primitives: a box, cylinder, cone, sphere, torus, wedge or hexagonal prism fitted into an axis-aligned box.

`parameters` turns a shape and the box (lowest corner and size, document millimetres) into the properties and the placement of a
FreeCAD feature (`Part::Box`, `Part::Cylinder`, ...). It is pure Python, so the sizing rules are unit tested without FreeCAD.
`create` makes the feature in one transaction (one undo step); the preview mesh is built by `meshes.build` from the same
parameters. FreeCAD is imported inside the functions that need it."""

from dataclasses import dataclass, field
from typing import Dict, Tuple

SHAPES = ("Box", "Cylinder", "Cone", "Sphere", "Torus", "Wedge", "Prism")
BLOCK = "Block"        # a box shaped solid made of points (`cad/block.py`); it is not a primitive of FreeCAD and is made by `create`
PRISM_SIDES = 6
TORUS_TUBE = 0.2       # tube radius of a torus as a fraction of the smaller side of its box


@dataclass
class Spec:
    type: str                                   # FreeCAD type id, "Part::Box" ...
    name: str                                   # object name stem
    props: Dict[str, float]
    position: Tuple[float, float, float]        # placement of the feature (document millimetres)
    rotation: Tuple[Tuple[float, float, float], float] = ((0.0, 0.0, 1.0), 0.0)   # axis and angle in degrees
    extra: Dict[str, float] = field(default_factory=dict)


def parameters(shape, lo, size) -> Spec:
    """The feature that fits `shape` into the box with lowest corner `lo` and edge lengths `size`."""
    (x, y, z), (sx, sy, sz) = lo, size
    cx, cy, cz = x + sx / 2, y + sy / 2, z + sz / 2
    flat = min(sx, sy)
    if shape == "Box":
        return Spec("Part::Box", "Box", {"Length": sx, "Width": sy, "Height": sz}, (x, y, z))
    if shape == "Cylinder":
        return Spec("Part::Cylinder", "Cylinder", {"Radius": flat / 2, "Height": sz}, (cx, cy, z))
    if shape == "Cone":
        return Spec("Part::Cone", "Cone", {"Radius1": flat / 2, "Radius2": 0.0, "Height": sz}, (cx, cy, z))
    if shape == "Sphere":
        return Spec("Part::Sphere", "Sphere", {"Radius": min(sx, sy, sz) / 2}, (cx, cy, cz))
    if shape == "Torus":
        tube = min(sz / 2, flat * TORUS_TUBE)
        return Spec("Part::Torus", "Torus", {"Radius1": flat / 2 - tube, "Radius2": tube}, (cx, cy, cz))
    if shape == "Wedge":
        # a ramp that rises towards +Y: the feature stands on its side (its Y axis is the height), turned a quarter about X
        props = {"Xmin": 0.0, "Xmax": sx, "Ymin": 0.0, "Ymax": sz, "Zmin": 0.0, "Zmax": sy,
                 "X2min": 0.0, "X2max": sx, "Z2min": 0.0, "Z2max": 0.0}
        return Spec("Part::Wedge", "Wedge", props, (x, y + sy, z), ((1.0, 0.0, 0.0), 90.0))
    if shape == "Prism":
        return Spec("Part::Prism", "Prism", {"Polygon": PRISM_SIDES, "Circumradius": flat / 2, "Height": sz}, (cx, cy, z))
    raise ValueError(f"unknown shape '{shape}'")


def describe(shape, size, format_length):
    """Text with the box a shape is fitted into, for example "Box: 10 mm x 20 mm x 5 mm"."""
    return f"{shape}: " + " x ".join(format_length(s) for s in size)


def _placement(spec):
    import FreeCAD as App
    return App.Placement(App.Vector(*spec.position), App.Rotation(App.Vector(*spec.rotation[0]), spec.rotation[1]))


def create(doc, shape, lo, size):
    """Make the feature in `doc` inside one transaction (one undo step) and return it."""
    if shape == BLOCK:
        from freecad.BlocksCAD.cad import block
        return block.create(doc, lo, size)
    spec = parameters(shape, lo, size)
    doc.openTransaction(f"Create {shape}")
    try:
        obj = doc.addObject(spec.type, spec.name)
        for name, value in spec.props.items():
            setattr(obj, name, value)
        obj.Placement = _placement(spec)
        doc.recompute()
        if not obj.isValid() or obj.Shape.isNull() or obj.Shape.Volume <= 0.0:
            raise ValueError(f"FreeCAD could not make a {shape} of {tuple(size)}")
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        raise
    return obj
