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
"""Editing the features that the primitives make: their placement, their size parameters and their removal (docs/ux-design.md, Move tool).

Scaling an object changes the size properties of its feature, never its geometry, so the model stays parametric: the properties
that set the size of each primitive are listed in `SIZE_PROPERTIES`, and `scaled_values` is pure Python. The functions that touch
a FreeCAD object import FreeCAD when they run."""

from freecad.VReeCAD.core import snapping

MIN_SIZE = 0.1     # millimetres: the smallest size of a scaled object when no grid rounds it

SIZE_PROPERTIES = {
    "Part::Box": ("Length", "Width", "Height"),
    "Part::Cylinder": ("Radius", "Height"),
    "Part::Cone": ("Radius1", "Radius2", "Height"),
    "Part::Sphere": ("Radius",),
    "Part::Torus": ("Radius1", "Radius2"),
    "Part::Wedge": ("Xmax", "Ymax", "Zmax", "X2max"),
    "Part::Prism": ("Circumradius", "Height"),
    "Part::Extrusion": ("LengthFwd",),         # an extruded sketch: how far it is pulled
}


def scalable(type_id):
    """Whether the size of a feature of this type can be scaled."""
    return type_id in SIZE_PROPERTIES


def scaled_values(type_id, values, factor, grid=None):
    """The size properties of a feature (`values`: name to millimetres) scaled by `factor`. With a `grid` each is rounded to it and
    at least one step long, without one the sizes are free (at least `MIN_SIZE`); a property that is zero stays zero. The tube of a
    torus stays thinner than its ring."""
    result = {}
    for name in SIZE_PROPERTIES[type_id]:
        value = values[name]
        if value == 0:
            result[name] = 0.0
        elif grid:
            result[name] = max(grid, snapping.snap(value * factor, grid))
        else:
            result[name] = max(MIN_SIZE, value * factor)
    if type_id == "Part::Torus" and result["Radius2"] >= result["Radius1"]:
        result["Radius1"] = result["Radius2"] + (grid or MIN_SIZE)
    return result


def size_values(obj):
    """The size properties of a feature as numbers (millimetres)."""
    return {name: float(getattr(getattr(obj, name), "Value", getattr(obj, name))) for name in SIZE_PROPERTIES[obj.TypeId]}


def set_size(obj, values):
    for name, value in values.items():
        setattr(obj, name, value)


def placement(obj):
    """(base, rotation quaternion x, y, z, w) of an object in document millimetres."""
    p = obj.Placement
    q = p.Rotation.Q
    return tuple(p.Base), (q[0], q[1], q[2], q[3])


def attached(obj):
    """Whether the placement of the object is computed from an attachment (`cad/attach.py`)."""
    return bool(getattr(obj, "AttachmentSupport", None)) and getattr(obj, "MapMode", "Deactivated") != "Deactivated"


def set_placement(obj, base, rotation):
    """Put the object at the position and rotation in document millimetres. The placement of an attached object is computed by the
    attacher, so it is the offset from the frame of its support that changes (and the document recomputes at once). The part of an
    assembly is brought back to a position its joints allow (`cad/joints.py`)."""
    import FreeCAD as App
    wanted = App.Placement(App.Vector(*base), App.Rotation(*rotation))
    if attached(obj):
        frame = obj.Placement * obj.AttachmentOffset.inverse()
        obj.AttachmentOffset = frame.inverse() * wanted
        obj.Document.recompute()
    else:
        obj.Placement = wanted
        from freecad.VReeCAD.cad import joints
        joints.solve(obj)


def delete_objects(doc, items):
    """Delete the objects among the selected `items` ((object name, sub-element name) pairs) in one transaction, so one undo step
    brings them back. Only objects selected as a whole go: a selected face, edge or vertex is not an object and is left alone.
    Returns the text for a toast."""
    names = []
    for name, sub in items:
        if not sub and name not in names and doc.getObject(name) is not None:
            names.append(name)
    if not names:
        return "Select a whole object to delete" if items else "Nothing selected"
    labels = [doc.getObject(name).Label for name in names]
    doc.openTransaction("Delete " + (labels[0] if len(labels) == 1 else f"{len(labels)} objects"))
    for name in names:
        if doc.getObject(name) is not None:                 # an object that went with another one is gone already
            doc.removeObject(name)
    doc.commitTransaction()
    doc.recompute()
    return f"Deleted {labels[0]}" if len(labels) == 1 else f"Deleted {len(labels)} objects"
