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
"""Owns the tool instances and the active tool; dispatches frames."""

from freecad.VReeCAD.tools import registry


class ToolManager:
    def __init__(self, ctx):
        self.ctx = ctx
        self._instances = {}
        self.active_name = None

    @property
    def active(self):
        return self._instances.get(self.active_name)

    def activate(self, name):
        """Make `name` the active tool (deactivates the previous one). Unknown names raise KeyError."""
        if name not in registry.names():
            raise KeyError(name)
        if name == self.active_name:
            return self.active
        if self.active is not None:
            self.active.deactivate()
        if name not in self._instances:
            self._instances[name] = registry.create(name, self.ctx)
        self.active_name = name
        self._instances[name].activate()
        return self._instances[name]

    def update(self, frame):
        tool = self.active
        if tool is not None and frame is not None:      # the first frames come before any input was read
            tool.update(frame)
