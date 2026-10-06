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
Action ids: "tool:<name>", "view:reset", "overlay:toggle", "plane:toggle", "scene:reload", "doc:undo", "doc:redo", "doc:delete", "app:close", and "layout:reset", "pointer:mode", "pointer:angle+", "pointer:angle-", "pointer:length+", "pointer:length-" (handled by the UI
controller itself)."""

from freecad.BlocksCAD.ui.layout import Face, Layout, Page


def build_faces(tool_names, tool_label):
    """Map of face id to `Face` for every known face."""
    faces = [Face(f"tool.{name}", tool_label(name), f"tool:{name}") for name in tool_names]
    faces += [
        Face("view.reset", "Reset view", "view:reset"),
        Face("view.overlay", "Overlays", "overlay:toggle"),
        Face("view.reload", "Reload scene", "scene:reload"),
        Face("view.plane", "Work plane", "plane:toggle"),
        Face("view.layout", "Reset layout", "layout:reset"),
        Face("doc.undo", "Undo", "doc:undo"),
        Face("doc.redo", "Redo", "doc:redo"),
        Face("doc.delete", "Delete", "doc:delete"),
        Face("app.close", "Close VR", "app:close"),
        Face("pointer.mode", "Pointer", "pointer:mode"),
        Face("pointer.angle_up", "Angle +", "pointer:angle+"),
        Face("pointer.angle_down", "Angle -", "pointer:angle-"),
        Face("pointer.length_up", "Length +", "pointer:length+"),
        Face("pointer.length_down", "Length -", "pointer:length-"),
    ]
    return {face.id: face for face in faces}


def default_layout(tool_names):
    return Layout([
        Page("Tools", [f"tool.{name}" for name in tool_names]),
        Page("Edit", ["doc.undo", "doc.redo", "doc.delete"]),
        Page("View", ["view.reset", "view.overlay", "view.plane", "view.reload", "view.layout"]),
        Page("Session", ["pointer.mode", "pointer.angle_up", "pointer.angle_down", "pointer.length_up", "pointer.length_down",
                         "app.close"]),
    ])
