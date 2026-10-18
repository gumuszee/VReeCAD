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
"""The buttons and the default layout. Tool buttons are generated from the tool registry; the other buttons are fixed.
Action ids: "tool:<name>", "view:reset", "scene:reload", "doc:undo", "doc:redo", "doc:delete", "doc:fuse", "doc:cut", "doc:common",
"doc:copy", "doc:fillet", "doc:chamfer", "doc:attach", "doc:detach", "doc:joint_<kind>", "doc:unjoint", "doc:mirror_<axis>", "doc:pattern_<axis>", "doc:colour", "doc:extrude", "doc:sources", "app:close", "settings:snapping", and, handled by the UI controller itself,
"layout:reset", "layout:show_hidden", "help:toggle", "hands:swap" and "pointer:mode".
A slider is a button of kind "slider" (action "slider:<setting>"): it takes a whole row of its panel, so it sits in the first slot of a
row and the other slots of that row stay empty. `SLIDERS` holds the range and step of each slider by button id."""

from dataclasses import dataclass
from typing import Tuple

from freecad.VReeCAD.core import snapping
from freecad.VReeCAD.ui.layout import Button, Layout, Page


@dataclass(frozen=True)
class Slider:
    attr: str        # the `settings.Settings` field the slider sets
    low: float = 0.0
    high: float = 1.0
    step: float = 1.0
    choices: Tuple[float, ...] = ()      # a slider over a list of values (the grid steps): they are spread evenly along the track

    def value(self, along):
        """The value for a position along the track (0 to 1), rounded to the step or the nearest of the choices."""
        along = min(max(along, 0.0), 1.0)
        if self.choices:
            return self.choices[round(along * (len(self.choices) - 1))]
        return round(round((self.low + along * (self.high - self.low)) / self.step) * self.step, 6)

    def fraction(self, value):
        """The position along the track (0 to 1) of a value."""
        if self.choices:
            return min(range(len(self.choices)), key=lambda i: abs(self.choices[i] - value)) / max(len(self.choices) - 1, 1)
        return min(max((value - self.low) / (self.high - self.low), 0.0), 1.0)


SLIDERS = {
    "pointer.angle": Slider("tip_angle", -30.0, 60.0, 1.0),
    "pointer.length": Slider("tip_length", 0.0, 0.2, 0.005),
    "settings.grid": Slider("grid", choices=snapping.GRID_STEPS),
    "settings.angle": Slider("angle", choices=snapping.ANGLE_STEPS),
}


def build_buttons(tool_names, tool_label, tool_hint=None):
    """Map of button id to `Button` for every known button; `tool_hint` maps a tool name to the tooltip of its button."""
    buttons = [Button(f"tool.{name}", tool_label(name), f"tool:{name}", tip=tool_hint(name) if tool_hint else "") for name in tool_names]
    buttons += [
        Button("view.reset", "Reset view", "view:reset", tip="Back to the home view at 1 : 1"),
        Button("view.reload", "Reload scene", "scene:reload", tip="Rebuild the scene from the document"),
        Button("view.layout", "Reset layout", "layout:reset", tip="Restore the default panels and buttons"),
        Button("view.hidden", "Show hidden", "layout:show_hidden", tip="Put the hidden buttons back on the panels"),
        Button("doc.undo", "Undo", "doc:undo", tip="Undo the last change"),
        Button("doc.redo", "Redo", "doc:redo", tip="Redo the last undone change"),
        Button("doc.delete", "Delete", "doc:delete", tip="Delete the selected objects"),
        Button("doc.fuse", "Fuse", "doc:fuse", tip="Join the selected objects into one"),
        Button("doc.cut", "Cut", "doc:cut", tip="Cut the objects selected after the first away from the first"),
        Button("doc.common", "Common", "doc:common", tip="Keep what the selected objects share"),
        Button("doc.copy", "Copy", "doc:copy", tip="Copy the selected objects, with their parameters, beside themselves"),
        Button("doc.mirror_x", "Mirror X", "doc:mirror_x", tip="Mirror the selected objects across a plane beside them along X"),
        Button("doc.mirror_y", "Mirror Y", "doc:mirror_y", tip="Mirror the selected objects across a plane beside them along Y"),
        Button("doc.mirror_z", "Mirror Z", "doc:mirror_z", tip="Mirror the selected objects across a plane beside them along Z"),
        Button("doc.pattern_x", "Pattern X", "doc:pattern_x", tip="Repeat the selected objects three times along X"),
        Button("doc.pattern_y", "Pattern Y", "doc:pattern_y", tip="Repeat the selected objects three times along Y"),
        Button("doc.pattern_z", "Pattern Z", "doc:pattern_z", tip="Repeat the selected objects three times along Z"),
        Button("doc.colour", "Colour", "doc:colour", tip="Give the selected objects the next colour"),
        Button("doc.fillet", "Fillet", "doc:fillet", tip="Round the selected edges"),
        Button("doc.chamfer", "Chamfer", "doc:chamfer", tip="Cut the selected edges off at an angle"),
        Button("doc.attach", "Attach", "doc:attach", tip="Attach the object of the first selected face to the second selected face"),
        Button("doc.detach", "Detach", "doc:detach", tip="Let the selected attached objects go, where they are"),
        Button("doc.joint_fixed", "Fixed joint", "doc:joint_fixed", tip="Join the first selected face to the second so they cannot move apart"),
        Button("doc.joint_revolute", "Hinge", "doc:joint_revolute", tip="Let the object of the first selected face turn about the axis through the two face centres"),
        Button("doc.joint_slider", "Slider", "doc:joint_slider", tip="Let the object of the first selected face slide along the axis through the two face centres"),
        Button("doc.joint_ball", "Ball joint", "doc:joint_ball", tip="Join the face centres and let the object turn freely about them"),
        Button("doc.unjoint", "Unjoint", "doc:unjoint", tip="Remove the joints of the selected objects"),
        Button("doc.extrude", "Extrude", "doc:extrude", tip="Extrude the selected sketches into solids"),
        Button("doc.sources", "Sources", "doc:sources", tip="Select what the selected feature is made from, also the hidden objects: their sizes are values"),
        Button("app.close", "Close VR", "app:close", tip="Close the VR viewer"),
        Button("pointer.mode", "Pointer", "pointer:mode", tip="Switch between laser and tip"),
        Button("pointer.hands", "Tool hand", "hands:swap", tip="Hold the tools in the other hand and the palette in this one"),
        Button("pointer.submm", "Small lengths", "units:submm", tip="Write lengths under 1 mm as decimals of a millimetre or as micrometres"),
        Button("settings.tutorial", "Tutorial", "help:toggle", tip="Show what the buttons of the controllers do"),
        Button("pointer.angle", "Angle", "slider:tip_angle", "slider", "Hold the trigger and drag"),
        Button("pointer.length", "Length", "slider:tip_length", "slider", "Hold the trigger and drag"),
        Button("settings.snapping", "Snapping", "settings:snapping", tip="Line points up with every point of the model (Guides) or only with those near the hand and those it has dwelt on (Inference)"),
        Button("settings.grid", "Grid", "slider:grid", "slider", "The grid step of every tool: hold the trigger and drag"),
        Button("settings.angle", "Angle step", "slider:angle", "slider", "The angle step of a locked turn: hold the trigger and drag"),
    ]
    return {button.id: button for button in buttons}


def default_layout(tool_names):
    return Layout([
        Page("Tools", [f"tool.{name}" for name in tool_names]),
        Page("Edit", ["doc.undo", "doc.redo", "doc.delete"]),
        Page("Modify", ["doc.fuse", "doc.cut", "doc.common", "doc.copy",
                        "doc.mirror_x", "doc.mirror_y", "doc.mirror_z", "doc.colour",
                        "doc.pattern_x", "doc.pattern_y", "doc.pattern_z"]),
        Page("Shape", ["doc.extrude", "doc.fillet", "doc.chamfer", "doc.attach", "doc.detach",
                       "doc.joint_fixed", "doc.joint_revolute", "doc.joint_slider", "doc.joint_ball", "doc.unjoint", "doc.sources"]),
        Page("View", ["view.reset", "view.reload", "view.layout", "view.hidden", "app.close"]),
        Page("Pointer", ["pointer.mode", None, None, None,
                         "pointer.angle", None, None, None,
                         "pointer.length"]),
        Page("Settings", ["pointer.hands", "pointer.submm", "settings.tutorial", "settings.snapping",
                          "settings.grid", None, None, None,
                          "settings.angle"]),
    ])


def migrate(layout, default):
    """Bring a saved layout up to the panels of `default`: the panel that held the pointer buttons gets the pointer panel's own place when
    the layout has none (the buttons move there), and the buttons that the layout lacks come back through `Layout.add_missing`."""
    pointer = next((p for p in default.pages if p.name == "Pointer"), None)
    if layout.version >= 5 or pointer is None or any(p.name == "Pointer" for p in layout.pages):
        return False                                    # a layout of version 5 may have a panel renamed: its panels are what the user made
    moved = [f for f in pointer.slots if f]
    kept = Page("Pointer", [None if f in layout.hidden else f for f in pointer.slots])
    for page in layout.pages:
        page.slots = [None if f in moved else f for f in page.slots]
    layout.pages.append(kept)
    layout.normalize()
    return True
