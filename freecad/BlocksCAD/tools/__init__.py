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
"""Tools: one class per modelling tool, a registry, and a manager that dispatches the per-frame `InputFrame`.

A tool sees only the `InputFrame` and the services in its `ToolContext`; it never touches OpenXR.
"""

from freecad.BlocksCAD.tools.base import Tool, ToolContext
from freecad.BlocksCAD.tools.registry import register, create, names, label_of, hint_of
from freecad.BlocksCAD.tools.manager import ToolManager

__all__ = ["Tool", "ToolContext", "ToolManager", "register", "create", "names", "label_of", "hint_of"]
