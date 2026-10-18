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
"""Combining a touched element with the selection. No FreeCAD or Coin imports.

A selection is a list of (object name, sub-element name) pairs, the sub-element name empty for a whole object, in the order the
elements were selected. `combine` returns the list after an element has been touched in one of the three operations of the Select
tool: "Replace" (the element alone), "Add" (appended unless it is there) and "Remove" (taken out; removing a whole object takes out
every element of it)."""

REPLACE, ADD, REMOVE = "Replace", "Add", "Remove"
OPERATIONS = (REPLACE, ADD, REMOVE)


def combine(current, item, operation):
    """The selection after `item` (name, sub) was touched while `operation` was chosen; `current` is not changed."""
    current = list(current)
    if operation == ADD:
        return current if item in current else current + [item]
    if operation == REMOVE:
        name, sub = item
        return [i for i in current if i != item and (sub or i[0] != name)]
    return [item]
