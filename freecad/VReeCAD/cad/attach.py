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
"""Attaching one object to a face of another (docs/ux-design.md, Shape panel).

An attached object has its placement computed by FreeCAD's Attacher (`AttachmentSupport` = the face, `MapMode` = FlatFace, the rest in
`AttachmentOffset`), so it follows the other object when that is moved or resized: the alignment is a property, never a baked
placement. `attach` mates a face of the moving object with a face of the target (the faces lie against each other and their centres
coincide); `detach` turns the attachment off and keeps the object where it is. `plan` is pure Python; the functions that touch a document
import FreeCAD when they run."""

from freecad.VReeCAD.cad import edit
from freecad.VReeCAD.cad.combine import sound


def face_number(sub):
    """The number of the face named `Face<n>` (1 based), or None for any other sub-element name."""
    if sub.startswith("Face") and sub[4:].isdigit():
        return int(sub[4:])
    return None


def plan(items):
    """What an attach of the selected `items` ((object name, sub-element name) pairs) makes: ((moving object, face), (target object,
    face)) from the first two selected faces, or a text saying what is missing. The face selected first belongs to the object that
    moves, the face selected second to the object it is attached to."""
    faces = []
    for name, sub in items:
        if face_number(sub) is not None and (name, sub) not in faces:
            faces.append((name, sub))
    if len(faces) < 2:
        return "Select a face of the object to move, then the face to attach it to"
    if faces[0][0] == faces[1][0]:
        return "Select faces of two different objects"
    return faces[0], faces[1]


def _planar(face):
    import Part
    return isinstance(face.Surface, Part.Plane)


def _face_frame(obj, sub):
    """(centre, outward normal) of a flat face of the object in document millimetres, or None when the face is not flat."""
    face = obj.Shape.getElement(sub)
    if not _planar(face):
        return None
    u, v = face.Surface.parameter(face.CenterOfMass)
    return face.CenterOfMass, face.normalAt(u, v)


def mated_placement(placement, centre, normal, target_centre, target_normal):
    """The placement for an object (now at `placement`) whose face with the centre and outward normal is turned to lie against the
    face of the target and moved so that the centres coincide."""
    import FreeCAD as App
    turn = App.Placement(App.Vector(), App.Rotation(normal, target_normal * -1.0))
    return (App.Placement(target_centre, App.Rotation()) * turn *
            App.Placement(centre * -1.0, App.Rotation()) * placement)


def make_attachable(obj):
    """Give an object that cannot be attached yet (a block, a boolean, an extrusion) the attachment extension of FreeCAD."""
    if "AttachmentSupport" not in obj.PropertiesList:
        obj.addExtension("Part::AttachExtensionPython")


def attach(doc, items):
    """Attach the object of the face selected first to the face selected second, in one transaction. Returns (text for a toast, name of
    the attached object or None)."""
    import FreeCAD as App
    result = plan(items)
    if isinstance(result, str):
        return result, None
    (move_name, move_sub), (target_name, target_sub) = result
    mover, target = doc.getObject(move_name), doc.getObject(target_name)
    if mover is None or target is None:
        return "Select faces first", None
    if mover in target.OutListRecursive:
        return f"{target.Label} is built from {mover.Label}: attach the other way round", None
    own, other = _face_frame(mover, move_sub), _face_frame(target, target_sub)
    if own is None or other is None:
        return "Attach needs flat faces", None
    wanted = mated_placement(mover.Placement, own[0], own[1], other[0], other[1])
    doc.openTransaction(f"Attach {mover.Label}")
    try:
        make_attachable(mover)
        mover.AttachmentSupport = [(target, target_sub)]
        mover.MapMode = "FlatFace"
        mover.AttachmentOffset = App.Placement()
        doc.recompute()
        mover.AttachmentOffset = mover.Placement.inverse() * wanted           # the frame of the face with no offset is the placement now
        doc.recompute()
        if not mover.isValid() or not sound(mover):
            raise ValueError("FreeCAD could not attach it")
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"Attach failed: {error}", None
    return f"Attached {mover.Label} to {target.Label}", mover.Name


def detach(doc, items):
    """Turn the attachment of the selected objects off in one transaction; they stay where they are. Returns (text for a toast, names
    of the detached objects)."""
    names = []
    for name, _ in items:
        obj = doc.getObject(name)
        if obj is not None and edit.attached(obj) and name not in names:
            names.append(name)
    if not names:
        return ("Nothing selected is attached" if items else "Nothing selected"), []
    doc.openTransaction("Detach " + (doc.getObject(names[0]).Label if len(names) == 1 else f"{len(names)} objects"))
    for name in names:
        obj = doc.getObject(name)
        placement = obj.Placement
        obj.MapMode = "Deactivated"
        obj.AttachmentSupport = []
        obj.AttachmentOffset = type(placement)()
        obj.Placement = placement
    doc.recompute()
    doc.commitTransaction()
    return (f"Detached {doc.getObject(names[0]).Label}" if len(names) == 1 else f"Detached {len(names)} objects"), names
