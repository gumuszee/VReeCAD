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

The change is made of real features, so it stays parametric. Where the face is a face that a size of the object moves (an end of a
box, a cylinder or a cone along its axis, an end of the extrusion of a sketch), that size is changed and nothing is added (`plan_direct`);
a size that is bound to an expression, or a change that would leave the object without volume, is not changed that way. Otherwise a
`PartDesign::SubShapeBinder` follows the face, a `Part::Extrusion` of
the binder along the normal of the face has the distance as its `LengthFwd` (the number that the value of the feature carries), and
the result is a `Part::MultiFuse` of the solid and the extrusion (a push, the face moves out) or a `Part::Cut` of the extrusion
from the solid (a pull, the face moves in). Changing the length of the extrusion later changes the result.

`snapped` and `describe` are pure Python. The functions that touch FreeCAD import it when they run."""

from freecad.VReeCAD.cad import combine
from freecad.VReeCAD.core import mathutil as mu
from freecad.VReeCAD.core import snapping

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


BOX_SIZES = ("Length", "Width", "Height")
SIDE = 0.999            # the cosine of the angle within which a face normal counts as along an axis


def _along(normal, axis):
    """The sign (1 or -1) of `normal` along the unit vector `axis` when it runs along it, else 0."""
    c = mu.dot(normal, axis)
    return 1 if c > SIDE else -1 if c < -SIDE else 0


def plan_direct(type_id, values, rotation, normal, distance, direction=None):
    """What pushing a face with the outward `normal` by `distance` changes in the object itself, as ({size: new value}, shift of the
    base of its placement in the document millimetres or None), or None when no size moves that face. `values` holds the sizes of
    the object (`Length`, `Width` and `Height` of a box, `Height` of a cylinder or a cone, `LengthFwd` and `LengthRev` of an
    extrusion), `rotation` its placement as (x, y, z, w) and `direction` the direction of an extrusion in the document. A new size of
    nothing or less is no plan."""
    if type_id == "Part::Extrusion":
        if direction is None:
            return None
        sign = _along(normal, direction)
        if sign == 0:
            return None
        name = "LengthFwd" if sign > 0 else "LengthRev"
        new = values[name] + distance
        return ({name: new}, None) if new > 1e-6 else None
    if type_id == "Part::Box":
        axes = {name: i for i, name in enumerate(BOX_SIZES)}
    elif type_id in ("Part::Cylinder", "Part::Cone"):
        axes = {"Height": 2}
    else:
        return None
    for name, i in axes.items():
        unit = tuple(1.0 if j == i else 0.0 for j in range(3))
        sign = _along(normal, mu.rotate(rotation, unit))
        if sign == 0:
            continue
        new = values[name] + distance
        if new <= 1e-6:
            return None
        return {name: new}, (mu.mul(normal, distance) if sign < 0 else None)   # the low end moves: the base goes with it
    return None


def _direct(obj, normal, distance):
    """`plan_direct` for the FreeCAD object `obj`, or None when it cannot be changed that way (no plan, a size or the placement bound
    to an expression, an extrusion that is not straight out of a sketch)."""
    type_id = getattr(obj, "TypeId", "")
    bound = [path for path, _ in getattr(obj, "ExpressionEngine", [])]
    q = obj.Placement.Rotation.Q
    rotation = (q[0], q[1], q[2], q[3])
    direction, values = None, {}
    if type_id == "Part::Extrusion":
        base = obj.Base
        if (getattr(base, "TypeId", "") != "Sketcher::SketchObject" or obj.DirMode != "Normal" or obj.Symmetric or obj.TaperAngle != 0.0
                or obj.TaperAngleRev != 0.0):
            return None
        sq = base.Placement.Rotation.Q
        direction = mu.rotate((sq[0], sq[1], sq[2], sq[3]), (0.0, 0.0, 1.0))
        values = {"LengthFwd": float(obj.LengthFwd), "LengthRev": float(obj.LengthRev)}
    elif type_id in ("Part::Box", "Part::Cylinder", "Part::Cone"):
        values = {name: float(getattr(obj, name).Value) for name in (BOX_SIZES if type_id == "Part::Box" else ("Height",))}
    plan = plan_direct(type_id, values, rotation, normal, distance, direction)
    if plan is None:
        return None
    changes, shift = plan
    if any(name in bound for name in changes) or (shift is not None and any(path.startswith("Placement") for path in bound)):
        return None
    return plan


def _apply_direct(doc, obj, plan, distance):
    """Make `plan` in one transaction; returns the text for a toast, or None when the object is no sound solid afterwards (the change
    is taken back)."""
    import FreeCAD as App
    changes, shift = plan
    doc.openTransaction(f"{'Push' if distance > 0 else 'Pull'} {obj.Label}")
    try:
        for name, value in changes.items():
            setattr(obj, name, float(value))
        if shift is not None:
            moved = obj.Placement.copy()
            moved.Base = moved.Base + App.Vector(*shift)
            obj.Placement = moved
        doc.recompute()
        if not combine.sound(obj):
            raise ValueError("no solid is left")
    except Exception:
        doc.abortTransaction()
        doc.recompute()
        return None
    doc.commitTransaction()
    return f"{'Pushed' if distance > 0 else 'Pulled'} {obj.Label} by {abs(distance):g} mm"


def preview_mesh(obj, sub, distance, deflection=0.5):
    """A `cad.meshes.Mesh` of the volume the face sweeps for the distance (flat shaded, in document millimetres), or None."""
    from freecad.VReeCAD.cad.meshes import Mesh
    from freecad.VReeCAD.core import mathutil as mu
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
    plan = _direct(obj, face_info(obj, sub)[1], distance)
    if plan is not None:
        text = _apply_direct(doc, obj, plan, distance)
        if text is not None:
            return text, obj.Name
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
