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
"""Fixing: a fixed thing is held in place as a constraint (docs/ux-design.md, Fixing). The B button of the tool hand fixes or releases
what a gesture holds: a body (Move tool), a point of a block (Points tool) or a point of a sketch (Sketch tool, as Sketcher constraints:
`cad/sketching.py`). This module is the fixing of a body. A fixed body is never moved by the tools, and neither is a body that a fixed
body is attached to (`AttachmentSupport`): moving the support would carry the fixed body with it, so the fixed one holds the support
too (the transitive kinematics). The functions take FreeCAD objects but import nothing from FreeCAD."""

PROPERTY = "VReeCADFixed"


def is_fixed(obj):
    return bool(getattr(obj, PROPERTY, False))


def set_fixed(obj, value):
    """Fix or release a body; the property is made when the body is first fixed (the caller owns the transaction)."""
    if PROPERTY not in obj.PropertiesList:
        obj.addProperty("App::PropertyBool", PROPERTY, "VReeCAD", "Held in place: the VR tools do not move it")
    setattr(obj, PROPERTY, bool(value))


def _attached_to(child, parent):
    """Whether `child` is attached to a face (or another element) of `parent`."""
    support = getattr(child, "AttachmentSupport", None) or ()
    try:
        return any(getattr(entry[0], "Name", None) == parent.Name for entry in support)
    except (TypeError, IndexError):
        return False


def blocker(obj, _seen=None):
    """The fixed body that would have to move if `obj` moved, or None: `obj` itself when it is fixed, else a fixed body attached to it,
    or attached to something attached to it."""
    seen = _seen if _seen is not None else set()
    if obj.Name in seen:
        return None
    seen.add(obj.Name)
    if is_fixed(obj):
        return obj
    for child in getattr(obj, "InList", ()):
        if _attached_to(child, obj):
            found = blocker(child, seen)
            if found is not None:
                return found
    return None
