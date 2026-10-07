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
"""Joints between two faces, made with FreeCAD's Assembly (docs/ux-design.md, Shape panel).

A joint is a real `App::FeaturePython` of the Assembly workbench in the `Joints` group of an `Assembly::AssemblyObject`; the two objects it
connects are children of that assembly, and one of them is grounded (a `GroundedJoint`) so that the other can be solved against it.
The kinds are the Assembly joint types `Fixed` (the faces lie against each other), `Revolute` (a hinge about the axis through the face
centres), `Slider` (a slide along that axis) and `Ball` (the face centres meet and the objects turn freely). `assembly_of` finds the
assembly of an object; `solve` lets the solver move the parts of an assembly back to a position its joints allow. `plan` and `KINDS` are
pure Python; the functions that touch a document import FreeCAD and the Assembly module when they run."""

import os
import sys

from freecad.BlocksCAD.cad import edit
from freecad.BlocksCAD.cad.attach import plan

KINDS = ("Fixed", "Revolute", "Slider", "Ball")
ASSEMBLY = "Assembly::AssemblyObject"


def modules():
    """The Assembly workbench modules (`UtilsAssembly`, `JointObject`); their folder is put on the path when it is not there yet."""
    import FreeCAD as App
    try:
        import JointObject
        import UtilsAssembly
    except ImportError:
        folder = os.path.join(App.getResourceDir(), "Mod", "Assembly")
        if folder not in sys.path:
            sys.path.append(folder)
        import JointObject
        import UtilsAssembly
    return JointObject, UtilsAssembly


def assembly_of(obj):
    """The assembly that holds the object, or None."""
    for parent, _ in getattr(obj, "Parents", []) or []:
        if parent.TypeId == ASSEMBLY:
            return parent
    return None


def solve(obj):
    """Let the solver of the assembly of the object bring its parts to a position the joints allow; returns whether it succeeded. Objects
    outside an assembly, and assemblies without joints, are left alone."""
    assembly = assembly_of(obj)
    if assembly is None:
        return True
    return assembly.solve() == 0


def joints_of(assembly, obj):
    """The joints (not the grounding ones) in the assembly that connect the object."""
    _, UtilsAssembly = modules()
    found = []
    for joint in UtilsAssembly.getJointGroup(assembly).Group:
        if not hasattr(joint, "JointType") or getattr(joint, "Reference1", None) is None:
            continue
        if any(ref is not None and ref[0].Name == obj.Name for ref in (joint.Reference1, joint.Reference2)):
            found.append(joint)
    return found


def _find_assembly(doc):
    found = doc.findObjects(ASSEMBLY)
    return found[0] if found else None


def make(doc, items, kind):
    """Connect the object of the face selected first with the object of the face selected second by a joint of `kind`, in one
    transaction (one undo step). The objects join the assembly of the document (made when there is none) and the second object is grounded
    unless it is held already. Returns (text for a toast, name of the moved object or None)."""
    if kind not in KINDS:
        raise ValueError(f"unknown joint '{kind}'")
    result = plan(items)
    if isinstance(result, str):
        return result, None
    (move_name, move_sub), (target_name, target_sub) = result
    mover, target = doc.getObject(move_name), doc.getObject(target_name)
    if mover is None or target is None:
        return "Select faces first", None
    if edit.attached(mover) or edit.attached(target):
        return "Detach it first: an attached object cannot be jointed", None
    if mover in target.OutListRecursive or target in mover.OutListRecursive:
        return "A joint needs two separate objects", None
    JointObject, UtilsAssembly = modules()
    doc.openTransaction(f"{kind} joint {mover.Label}")
    try:
        assembly = _find_assembly(doc)
        if assembly is None:
            assembly = doc.addObject(ASSEMBLY, "Assembly")
        for obj in (target, mover):
            if not assembly.hasObject(obj):
                assembly.addObject(obj)
        doc.recompute()
        group = UtilsAssembly.getJointGroup(assembly)
        if not assembly.isPartConnected(target):
            ground = group.newObject("App::FeaturePython", "GroundedJoint")
            JointObject.GroundedJoint(ground, target)
            if ground.ViewObject is not None:
                JointObject.ViewProviderGroundedJoint(ground.ViewObject)
        joint = group.newObject("App::FeaturePython", "Joint")
        joint.Label = f"{kind} {mover.Label}"
        JointObject.Joint(joint, JointObject.JointTypes.index(kind))
        if joint.ViewObject is not None:
            JointObject.ViewProviderJoint(joint.ViewObject)
        joint.Proxy.setJointConnectors(joint, [[target, [target_sub, target_sub]], [mover, [move_sub, move_sub]]])
        doc.recompute()
        if assembly.solve() != 0 or not mover.isValid():
            raise ValueError("the solver could not satisfy it")
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"{kind} joint failed: {error}", None
    return f"{kind} joint: {mover.Label} to {target.Label}", mover.Name


def remove(doc, items):
    """Delete the joints of the selected objects in one transaction (the objects stay where they are, in the assembly). Returns (text for
    a toast, number of joints removed)."""
    removed = []
    for name, _ in items:
        obj = doc.getObject(name)
        assembly = assembly_of(obj) if obj is not None else None
        if assembly is not None:
            for joint in joints_of(assembly, obj):
                if joint.Name not in removed:
                    removed.append(joint.Name)
    if not removed:
        return ("Nothing selected is jointed" if items else "Nothing selected"), 0
    doc.openTransaction("Remove joints")
    for name in removed:
        if doc.getObject(name) is not None:
            doc.removeObject(name)
    doc.recompute()
    doc.commitTransaction()
    return f"Removed {len(removed)} joint" + ("" if len(removed) == 1 else "s"), len(removed)
