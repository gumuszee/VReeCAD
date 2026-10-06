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
"""Tool base class and the services a tool may use."""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ToolContext:
    """Services handed to every tool. Fields are filled by the host (the XR widget or the Sim session).

    host:     the object that owns the scene, for the inherited tools that still call back into it
    haptic:   callable (hand, amplitude, duration_s) or None
    dominant: index of the tool hand (0 = left, 1 = right)
    """
    host: Any = None
    haptic: Optional[Callable] = None
    dominant: int = 1
    services: dict = field(default_factory=dict)

    @property
    def off_hand(self) -> int:
        return 1 - self.dominant


class Tool:
    """Subclass, set `name` (unique, lower case) and `label`, and register with `@register`."""

    name = ""
    label = ""

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx

    def activate(self):
        """Called when the tool becomes the active tool."""

    def deactivate(self):
        """Called when another tool replaces it; discard any uncommitted gesture state here."""

    def update(self, frame):
        """Called once per frame with the current `InputFrame` while the tool is active."""
