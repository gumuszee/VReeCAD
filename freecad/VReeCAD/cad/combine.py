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
"""Booleans and copies of the selected objects (docs/ux-design.md, Modify panel).

A boolean is a real feature that refers to its sources (`Part::MultiFuse`, `Part::Cut`, `Part::MultiCommon`), so the sources stay
editable and the result follows them. A copy is a copy of the feature with its own properties (the same sizes and placement), moved
aside, never a frozen shape. `plan` and `selected_names` are pure Python; the functions that make features work on a document and
import nothing else from FreeCAD."""

KINDS = ("fuse", "cut", "common")
TYPES = {"fuse": "Part::MultiFuse", "cut": "Part::Cut", "common": "Part::MultiCommon"}
VERBS = {"fuse": "Fuse", "cut": "Cut", "common": "Common"}
GAP = 10.0                 # millimetres between an object and its copy, its mirror image or the next of its pattern
COPY_GAP = GAP


def selected_names(items):
    """The names of the objects selected as a whole, in the order they were selected, each once."""
    names = []
    for name, sub in items:
        if not sub and name not in names:
            names.append(name)
    return names


def plan(kind, names):
    """What a boolean of the objects `names` (the order of the selection) makes: (base, tools), or a text saying what is missing.
    A fuse and a common take every object (the base is the first); in a cut the first object is the base and every other object a
    tool that is taken away from it."""
    if kind not in KINDS:
        raise ValueError(f"unknown boolean '{kind}'")
    if len(names) < 2:
        return f"Select two objects to {kind}" if kind != "cut" else "Select the base first, then the objects to cut away"
    return names[0], list(names[1:])


def sources_of(obj):
    """The objects that `obj` is made from: what it refers to (`OutList`) that has a shape of its own, each once, in the order of the
    feature (the tools of a cut after its base). A spreadsheet of variables or an origin has no shape and is none."""
    result = []
    for source in getattr(obj, "OutList", ()):
        if hasattr(source, "Shape") and source not in result:
            result.append(source)
    return result


def sources(doc, items):
    """The sources of the selected objects (`items`: (name, sub-element name) pairs; a selected face, edge or vertex counts for its
    object), each once, hidden ones included. Returns (text for a toast, names of the sources), the names empty when there is none."""
    names = []
    for name, _ in items:
        if name not in names and doc.getObject(name) is not None:
            names.append(name)
    if not names:
        return "Select a feature first", []
    found = []
    for name in names:
        for source in sources_of(doc.getObject(name)):
            if source.Name not in found:
                found.append(source.Name)
    if not found:
        return ("This object has no sources" if len(names) == 1 else "These objects have no sources"), []
    hidden = sum(1 for name in found if not getattr(doc.getObject(name), "Visibility", True))
    text = "Sources: " + ", ".join(doc.getObject(name).Label for name in found[:3]) + ("" if len(found) <= 3 else f" and {len(found) - 3} more")
    return text + (f" ({hidden} hidden)" if hidden else ""), found


def hide(obj):
    view = getattr(obj, "ViewObject", None)
    if view is not None:
        view.Visibility = False


def sound(obj):
    return obj.isValid() and not obj.Shape.isNull() and obj.Shape.Volume > 0.0


def combine(doc, kind, items):
    """Make the boolean `kind` of the selected whole objects (`items`: (name, sub-element name) pairs) in one transaction, so one
    undo step takes it back. The sources are hidden, not changed. Returns (text for a toast, name of the new object or None)."""
    names = [n for n in selected_names(items) if doc.getObject(n) is not None]
    result = plan(kind, names)
    if isinstance(result, str):
        return result, None
    base, tools = result
    label = VERBS[kind]
    doc.openTransaction(f"{label} {len(names)} objects")
    try:
        if kind == "cut":
            if len(tools) > 1:
                tool = doc.addObject(TYPES["fuse"], "Tools")
                tool.Shapes = [doc.getObject(n) for n in tools]
                doc.recompute()
                tool_obj, hidden = tool, [tool]
            else:
                tool_obj, hidden = doc.getObject(tools[0]), []
            obj = doc.addObject(TYPES["cut"], "Cut")
            obj.Base, obj.Tool = doc.getObject(base), tool_obj
        else:
            obj = doc.addObject(TYPES[kind], label)
            obj.Shapes = [doc.getObject(n) for n in names]
            hidden = []
        doc.recompute()
        if not sound(obj):
            raise ValueError("nothing is left" if kind != "fuse" else "FreeCAD could not fuse them")
        for name in names:
            hide(doc.getObject(name))
        for extra in hidden:
            hide(extra)
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"{label} failed: {error}", None
    return f"{label}: {len(names)} objects", obj.Name


def copy_objects(doc, items, gap=COPY_GAP):
    """Copy the selected whole objects, each with the features it depends on, in one transaction. The copy of an object lies beside
    it, one length of its box along X plus `gap` away: the features at the bottom of the copy (those that depend on nothing) are
    moved, so booleans of copies follow. Returns (text for a toast, names of the copies)."""
    import FreeCAD as App
    names = [n for n in selected_names(items) if doc.getObject(n) is not None]
    if not names:
        return ("Select a whole object to copy" if items else "Nothing selected"), []
    doc.openTransaction("Copy " + (doc.getObject(names[0]).Label if len(names) == 1 else f"{len(names)} objects"))
    copies = []
    try:
        for name in names:
            source = doc.getObject(name)
            shift = App.Vector(source.Shape.BoundBox.XLength + gap, 0.0, 0.0)
            made = doc.copyObject(source, True)            # the copy, with copies of the features it is built from
            family = {obj.Name: obj for obj in [made] + list(made.OutListRecursive)}
            for obj in family.values():
                if not obj.OutList and hasattr(obj, "Placement"):
                    obj.Placement = App.Placement(obj.Placement.Base + shift, obj.Placement.Rotation)
            copies.append(made)
        doc.recompute()
        doc.commitTransaction()
    except Exception as error:
        doc.abortTransaction()
        doc.recompute()
        return f"Copy failed: {error}", []
    count = len(copies)
    return (f"Copied {doc.getObject(names[0]).Label}" if count == 1 else f"Copied {count} objects"), [c.Name for c in copies]
