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
"""The variables of a document (docs/ux-design.md, Variables): named lengths that the values of objects are bound to by expressions.

They live in a spreadsheet named `Variables`, made when the first variable is defined: column A holds the name as text and column B
the length, with the name as its alias, so an expression refers to it as `Variables.width` and the sheet can be edited on the
desktop like any other. Changing the length of a variable recomputes every value bound to it. Nothing here opens a transaction:
the caller does, so a variable and the binding that made it are one undo step. FreeCAD is only used by the functions that run."""

from freecad.BlocksCAD.core.values import SHEET


def sheet(doc, create=False):
    """The spreadsheet of the variables of `doc`, made when `create` says so and there is none; None when there is none."""
    obj = doc.getObject(SHEET)
    if obj is None and create:
        obj = doc.addObject("Spreadsheet::Sheet", SHEET)
        obj.Label = SHEET
    return obj


def _cells(obj):
    return sorted((c for c in obj.getUsedCells() if c.startswith("B") and c[1:].isdigit() and obj.getAlias(c)), key=lambda c: int(c[1:]))


def list_variables(doc):
    """(name, millimetres) of every variable of `doc`, in the order they were defined."""
    obj = sheet(doc)
    if obj is None:
        return []
    result = []
    for cell in _cells(obj):
        value = obj.get(cell)
        result.append((obj.getAlias(cell), float(getattr(value, "Value", value))))
    return result


def define(doc, name, value):
    """Add the variable `name` with `value` millimetres; returns the name. The name must be free."""
    obj = sheet(doc, create=True)
    if any(n == name for n, _ in list_variables(doc)):
        raise ValueError(f"There is a variable {name} already")
    rows = [int(c[1:]) for c in obj.getUsedCells() if c[1:].isdigit()]
    row = max(rows, default=0) + 1
    obj.set(f"A{row}", name)
    obj.set(f"B{row}", f"{value:.12g} mm")
    obj.setAlias(f"B{row}", name)
    doc.recompute()
    return name


def set_value(doc, name, value):
    """Give the variable `name` the length `value` millimetres; everything bound to it follows after the next recompute."""
    obj = sheet(doc)
    for cell in [] if obj is None else _cells(obj):
        if obj.getAlias(cell) == name:
            obj.set(cell, f"{value:.12g} mm")
            return
    raise ValueError(f"There is no variable {name}")
