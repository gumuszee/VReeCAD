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
"""Pushing and pulling a flat face of a solid (docs/ux-design.md, Push/Pull tool).

The change is made of real features, so it stays parametric. A `PartDesign::SubShapeBinder` follows the face, a `Part::Extrusion` of
the binder along the normal of the face has the distance as its `LengthFwd` (the number that the value of the feature carries), and
the result is a `Part::MultiFuse` of the solid and the extrusion (a push, the face moves out) or a `Part::Cut` of the extrusion
from the solid (a pull, the face moves in). Changing the length of the extrusion later changes the result.

`snapped` and `describe` are pure Python. The functions that touch FreeCAD import it when they run."""

from freecad.BlocksCAD.cad import combine
from freecad.BlocksCAD.core import snapping

MIN_STEPS = 1        # a distance shorter than this many grid steps is a tap, not a push


def snapped(distance, grid):
    """The distance rounded to the grid (a distance of less than one step is none)."""
    value = snapping.snap(distance, grid)
    return 0.0 if abs(value) < MIN_STEPS * grid - 1e-9 else value


def describe(distance, format_length):
    if distance == 0:
        return "Push or pull: 0"
    return f"{'Push' if distance > 0 else 'Pull'}: {format_length(abs(distance))}"


def face_info(obj, sub):
    """(centre, outward normal) of the flat face `sub` of `obj` in document millimetres, or None when it is not a flat face."""
    import Part
    try:
        face = obj.Shape.getElement(sub)
    except Exception:
        return None
    if face.ShapeType != "Face" or not isinstance(face.Surface, Part.Plane):
        return None
    u, v = face.Surface.parameter(face.CenterOfMass)
    normal = face.normalAt(u, v)
    centre = face.CenterOfMass
    return (centre.x, centre.y, centre.z), (normal.x, normal.y, normal.z)


def preview_mesh(obj, sub, distance, deflection=0.5):
    """A `cad.meshes.Mesh` of the volume the face sweeps for the distance (flat shaded, in document millimetres), or None."""
    from freecad.BlocksCAD.cad.meshes import Mesh
    from freecad.BlocksCAD.core import mathutil as mu
    import FreeCAD as App
    info = face_info(obj, sub)
    if info is None or distance == 0:
        return None
    face = obj.Shape.getElement(sub)
    solid = face.extrude(App.Vector(*mu.mul(info[1], distance)))
    points, triangles = solid.tessellate(deflection)
    mesh = Mesh()
    for a, b, c in triangles:
        corners = [tuple(points[i]) for i in (a, b, c)]
        normal = mu.normalize(mu.cross(mu.sub(corners[1], corners[0]), mu.sub(corners[2], corners[0])))
        first = len(mesh.points)
        mesh.points += corners
        mesh.normals += [normal] * 3
        mesh.triangles.append((first, first + 1, first + 2))
    for edge in solid.Edges:
        mesh.outline.append([tuple(p) for p in edge.discretize(Deflection=deflection)])
    return mesh


def apply(doc, name, sub, distance):
    """Push (positive distance) or pull (negative) the flat face `sub` of the object `name` in one transaction, so one undo step
    takes it back. Returns (text for a toast, name of the result or None)."""
    obj = doc.getObject(name)
    if obj is None or face_info(obj, sub) is None:
        return "Only flat faces can be pushed or pulled", None
    if distance == 0:
        return "Nothing to push", None
    doc.openTransaction(f"{'Push' if distance > 0 else 'Pull'} {obj.Label} {sub}")
    try:
        binder = doc.addObject("PartDesign::SubShapeBinder", "Face")
        binder.Support = [(obj, sub)]
        doc.recompute()
        extrusion = doc.addObject("Part::Extrusion", "Extrude")
        extrusion.Base = binder
        extrusion.DirMode = "Normal"
        extrusion.LengthFwd = float(distance)
        extrusion.Solid = True
        doc.recompute()
        if not combine.sound(extrusion):
            raise ValueError("FreeCAD could not extrude the face")
        if distance > 0:
            result = doc.addObject("Part::MultiFuse", "Push")
            result.Shapes = [obj, extrusion]
        else:
            result = doc.addObject("Part::Cut", "Pull")
            result.Base, result.Tool = obj, extrusion
        doc.recompute()
        if not combine.sound(result):
            raise ValueError("nothing is left")
        for hidden in (obj, binder, extrusion):
            combine.hide(hidden)
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"{'Push' if distance > 0 else 'Pull'} failed: {error}", None
    return f"{'Pushed' if distance > 0 else 'Pulled'} {obj.Label} by {abs(distance):g} mm", result.Name
