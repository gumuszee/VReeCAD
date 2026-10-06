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
"""The inherited interaction modes as registered tools.

Each tool calls the corresponding `interact_*` method of the XR widget (`ctx.host`), which reads the controller state
that the widget keeps. They are replaced by new tools milestone by milestone (docs/design.md).
"""

from freecad.BlocksCAD.tools.base import Tool
from freecad.BlocksCAD.tools.registry import register


class _HostMethodTool(Tool):
    method = ""

    def update(self, frame):
        getattr(self.ctx.host, self.method)()


@register
class TeleportTool(_HostMethodTool):
    name = "teleport"
    label = "Teleport"
    hint = "Pick a teleport destination"
    method = "check_teleport_jump"


@register
class LineBuilderTool(_HostMethodTool):
    name = "line_builder"
    label = "Line"
    hint = "Draw lines and faces"
    method = "interact_line_builder"


@register
class CubeBuilderTool(_HostMethodTool):
    name = "cube_builder"
    label = "Cube"
    hint = "Click and drag to build a cube"
    method = "interact_cube_builder"


@register
class SelectTool(_HostMethodTool):
    name = "select_mode"
    label = "Select"
    hint = "Select and edit"
    method = "interact_select_mode"


@register
class DragTool(_HostMethodTool):
    name = "drag_mode"
    label = "Drag"
    hint = "Pick an element to drag"
    method = "interact_drag_mode"


@register
class WorkingPlaneTool(_HostMethodTool):
    name = "working_plane"
    label = "Working plane"
    hint = "Set the working plane"
    method = "interact_working_plane"
