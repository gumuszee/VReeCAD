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
"""The faces and the default layout. Tool faces are generated from the tool registry; the other faces are fixed.
Action ids: "tool:<name>", "view:reset", "overlay:toggle", "plane:toggle", "scene:reload", "doc:undo", "doc:redo", "doc:delete",
"app:close", and, handled by the UI controller itself, "layout:reset", "layout:show_hidden" and "pointer:mode".
A slider is a face of kind "slider" (action "slider:<setting>"): it takes a whole row of its panel, so it sits in the first slot of a
row and the other slots of that row stay empty. `SLIDERS` holds the range and step of each slider by face id."""

from dataclasses import dataclass

from freecad.BlocksCAD.ui.layout import Face, Layout, Page


@dataclass(frozen=True)
class Slider:
    attr: str        # the `settings.Settings` field the slider sets
    low: float
    high: float
    step: float

    def value(self, along):
        """The value for a position along the track (0 to 1), rounded to the step."""
        along = min(max(along, 0.0), 1.0)
        return round(round((self.low + along * (self.high - self.low)) / self.step) * self.step, 6)

    def fraction(self, value):
        """The position along the track (0 to 1) of a value."""
        return min(max((value - self.low) / (self.high - self.low), 0.0), 1.0)


SLIDERS = {
    "pointer.angle": Slider("tip_angle", -30.0, 60.0, 1.0),
    "pointer.length": Slider("tip_length", 0.0, 0.2, 0.005),
}


def build_faces(tool_names, tool_label):
    """Map of face id to `Face` for every known face."""
    faces = [Face(f"tool.{name}", tool_label(name), f"tool:{name}") for name in tool_names]
    faces += [
        Face("view.reset", "Reset view", "view:reset"),
        Face("view.overlay", "Overlays", "overlay:toggle"),
        Face("view.reload", "Reload scene", "scene:reload"),
        Face("view.plane", "Work plane", "plane:toggle"),
        Face("view.layout", "Reset layout", "layout:reset"),
        Face("view.hidden", "Show hidden", "layout:show_hidden"),
        Face("doc.undo", "Undo", "doc:undo"),
        Face("doc.redo", "Redo", "doc:redo"),
        Face("doc.delete", "Delete", "doc:delete"),
        Face("app.close", "Close VR", "app:close"),
        Face("pointer.mode", "Pointer", "pointer:mode"),
        Face("pointer.angle", "Angle", "slider:tip_angle", "slider"),
        Face("pointer.length", "Length", "slider:tip_length", "slider"),
    ]
    return {face.id: face for face in faces}


def default_layout(tool_names):
    return Layout([
        Page("Tools", [f"tool.{name}" for name in tool_names]),
        Page("Edit", ["doc.undo", "doc.redo", "doc.delete"]),
        Page("View", ["view.reset", "view.overlay", "view.plane", "view.reload", "view.layout", "view.hidden"]),
        Page("Session", ["pointer.mode", "app.close", None, None,
                         "pointer.angle", None, None, None,
                         "pointer.length"]),
    ])
