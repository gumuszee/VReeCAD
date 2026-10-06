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
"""Coin3D drawing of the palette carousel (docs/ux-design.md, Visual style). Flat, unlit, high contrast: panels never depend on
the scene lighting. Sizes are physical: the face edge is `ring.CELL`, label glyphs are about 9 mm tall (`style.TEXT_SCALE`)."""

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import ring as rg
from freecad.BlocksCAD.ui import style

DEPTH = 0.004
MAX_DOTS = 8
TITLE_H = rg.TITLE_Y[1] - rg.TITLE_Y[0]
TITLE_CENTRE = (rg.TITLE_Y[0] + rg.TITLE_Y[1]) / 2


def _cube(w, h, d):
    cube = coin.SoCube()
    cube.width, cube.height, cube.depth = w, h, d
    return cube


def _at(x, y, z):
    move = coin.SoTranslation()
    move.translation.setValue(x, y, z)
    return move


def _plate(parent, w, h, rgb, x=0.0, y=0.0, z=0.0):
    sep = coin.SoSeparator()
    sep.addChild(_at(x, y, z))
    material = style.color(rgb)
    sep.addChild(material)
    sep.addChild(_cube(w, h, DEPTH))
    parent.addChild(sep)
    return material


def _text(parent, lines, x, y, z, rgb, justification=coin.SoText3.CENTER, factor=1.0):
    """Text lines centred vertically around y; returns the colour node."""
    sep = coin.SoSeparator()
    sep.addChild(_at(x, y + (len(lines) - 1) * 0.5 * style.LINE_HEIGHT * factor - 0.0035 * factor, z))
    material = style.color(rgb)
    sep.addChild(material)
    sep.addChild(style.text_scale(factor))
    text = coin.SoText3()
    text.string.setValues(0, len(lines), lines)
    text.justification = justification
    sep.addChild(text)
    parent.addChild(sep)
    return material


class _Cell:
    def __init__(self, parent, x, y, face_label):
        self.sep = coin.SoSeparator()
        self.sep.addChild(_at(x, y, 0.0))
        self.plate_color = _plate(self.sep, rg.CELL, rg.CELL, style.FACE if face_label is not None else style.EMPTY)
        self.text_color = None
        if face_label is not None:
            self.text_color = _text(self.sep, lay.wrap_label(face_label), 0.0, 0.0, DEPTH * 0.5 + 0.0005, style.TEXT)
        parent.addChild(self.sep)

    def set_state(self, hover, active, has_face):
        color = style.EMPTY if not has_face else style.ACTIVE if active else style.HOVER if hover else style.FACE
        self.plate_color.rgb = coin.SbColor(*color)
        if self.text_color is not None:
            self.text_color.rgb = coin.SbColor(*(style.TEXT_ON_ACTIVE if active else style.TEXT))


class _Panel:
    """One panel (page) in its own coordinates: x right, y up, z out of the panel."""

    def __init__(self, page, faces):
        self.switch = coin.SoSwitch()
        self.switch.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        sep.addChild(self.transform)
        self.back_color = _plate(sep, rg.PANEL_W, rg.PANEL_H, style.PLATE, 0.0, 0.0, -DEPTH)
        self.title_color = _plate(sep, rg.GRID_W, TITLE_H, style.PLATE, 0.0, TITLE_CENTRE, 0.0)
        _text(sep, [page.name], -rg.GRID_W / 2 + 0.008, TITLE_CENTRE, DEPTH * 0.5 + 0.0005, style.TEXT_DIM,
              coin.SoText3.LEFT)
        for i in (-1, 0, 1):   # grooves: the title bar is the handle for lifting the panel
            _plate(sep, 0.016, 0.0016, style.DOT, rg.GRID_W / 2 - 0.016, TITLE_CENTRE + i * 0.006, DEPTH * 0.5)
        self.dots = []
        for _ in range(MAX_DOTS):
            dot_switch = coin.SoSwitch()
            dot_switch.whichChild = coin.SO_SWITCH_NONE
            dot_sep = coin.SoSeparator()
            move = _at(0.0, rg.DOT_Y, DEPTH * 0.5)
            dot_sep.addChild(move)
            material = style.color(style.DOT)
            dot_sep.addChild(material)
            sphere = coin.SoSphere()
            sphere.radius = 0.0035
            dot_sep.addChild(sphere)
            dot_switch.addChild(dot_sep)
            sep.addChild(dot_switch)
            self.dots.append((dot_switch, move, material))
        self.cells = []
        for slot, face_id in enumerate(page.slots):
            col, row = slot % lay.COLS, slot // lay.COLS
            x = (col - (lay.COLS - 1) / 2) * (rg.CELL + rg.GAP)
            y = ((lay.ROWS - 1) / 2 - row) * (rg.CELL + rg.GAP)
            face = faces.get(face_id) if face_id else None
            self.cells.append((_Cell(sep, x, y, face.label if face else None), face))
        self.switch.addChild(sep)

    def set_dots(self, count, current):
        count = min(count, MAX_DOTS)
        for i, (dot_switch, move, material) in enumerate(self.dots):
            dot_switch.whichChild = coin.SO_SWITCH_ALL if i < count and count > 1 else coin.SO_SWITCH_NONE
            move.translation.setValue((i - (count - 1) / 2) * 0.014, rg.DOT_Y, DEPTH * 0.5)
            material.rgb = coin.SbColor(*(style.DOT_ON if i == current else style.DOT))


class _Ghost:
    """The empty slot at the end of a side that a lifted panel can be dropped on."""

    def __init__(self):
        self.switch = coin.SoSwitch()
        self.switch.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        sep.addChild(self.transform)
        self.color = _plate(sep, rg.PANEL_W, rg.PANEL_H, style.DROP, 0.0, 0.0, -DEPTH)
        _text(sep, ["Drop here"], 0.0, 0.0, 0.0005, style.TEXT, factor=1.2)
        self.switch.addChild(sep)


class _Card:
    """The lifted panel that follows the ray."""

    def __init__(self):
        self.switch = coin.SoSwitch()
        self.switch.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        sep.addChild(self.transform)
        _plate(sep, 0.11, 0.032, style.GRAB)
        self.text = coin.SoText3()
        text_sep = coin.SoSeparator()
        text_sep.addChild(_at(0.0, -0.0035, DEPTH * 0.5 + 0.0005))
        text_sep.addChild(style.color(style.TEXT_ON_ACTIVE))
        text_sep.addChild(style.text_scale())
        self.text.justification = coin.SoText3.CENTER
        text_sep.addChild(self.text)
        sep.addChild(text_sep)
        self.switch.addChild(sep)


class _Marker:
    """The bar that shows where the lifted panel goes: beside the panel under the ray (left or right) or as a new row (above or below)."""
    BAR = 0.008

    def __init__(self):
        self.switch = coin.SoSwitch()
        self.switch.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        sep.addChild(self.transform)
        sep.addChild(style.color(style.GRAB))
        self.bar = coin.SoCube()
        self.bar.depth = DEPTH
        sep.addChild(self.bar)
        self.switch.addChild(sep)

    def show(self, pose, zone, origin, fade):
        half = (rg.PANEL_W / 2 + rg.PANEL_GAP / 2, rg.PANEL_H / 2 + rg.PANEL_GAP / 2)
        x, y, w, h = {"left": (-half[0], 0.0, self.BAR, rg.PANEL_H), "right": (half[0], 0.0, self.BAR, rg.PANEL_H),
                      "above": (0.0, half[1], rg.PANEL_W, self.BAR), "below": (0.0, -half[1], rg.PANEL_W, self.BAR)}[zone]
        self.bar.width, self.bar.height = w, h
        centre = mu.add(pose.centre, mu.add(mu.mul(pose.u, x), mu.mul(pose.v, y)))
        centre = mu.add(centre, mu.mul(pose.n, 0.003))
        if fade < 1.0:
            centre = mu.lerp(origin, centre, fade)
        self.transform.translation.setValue(*centre)
        self.transform.rotation.setValue(*mu.quat_from_basis(pose.u, pose.v, pose.n))
        self.switch.whichChild = coin.SO_SWITCH_ALL


class RingView:
    def __init__(self):
        self.root = coin.SoSwitch()
        self.root.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        sep.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        sep.addChild(light)
        sep.addChild(style.font())
        self._panels_sep = coin.SoSeparator()
        sep.addChild(self._panels_sep)
        self._ghosts = {}                # side -> ghost slot of an empty side
        self._ghost_sep = coin.SoSeparator()
        sep.addChild(self._ghost_sep)
        self._marker = _Marker()
        self._card = _Card()
        sep.addChild(self._marker.switch)
        sep.addChild(self._card.switch)
        self.root.addChild(sep)
        self._panels = []
        self._built_for = None

    @staticmethod
    def _signature(layout):
        return id(layout), tuple((p.name, tuple(p.slots)) for p in layout.pages)

    def build(self, layout, faces):
        """(Re)build the panel nodes for a layout; `faces` maps face id to `layout.Face`."""
        self._panels_sep.removeAllChildren()
        self._panels = []
        for page in layout.pages:
            view = _Panel(page, faces)
            self._panels.append(view)
            self._panels_sep.addChild(view.switch)
        self._built_for = self._signature(layout)

    def needs_build(self, layout):
        return self._built_for != self._signature(layout)

    @staticmethod
    def _place(transform, pose, origin, fade):
        """Place a panel; it grows from the carousel axis while the carousel fades in."""
        centre = pose.centre if fade >= 1.0 else mu.lerp(origin, pose.centre, fade)
        transform.translation.setValue(*centre)
        transform.rotation.setValue(*mu.quat_from_basis(pose.u, pose.v, pose.n))
        s = 0.5 + 0.5 * fade
        transform.scaleFactor.setValue(s, s, s)

    def update(self, ring, result, layout, faces, head, active_actions=()):
        if ring.fade <= 0.02:
            self.root.whichChild = coin.SO_SWITCH_NONE
            return
        if self.needs_build(layout):
            self.build(layout, faces)
        self.root.whichChild = coin.SO_SWITCH_ALL
        sides = ring.display_sides()
        for index, view in enumerate(self._panels):
            pose = ring.poses.get(index)
            if pose is None:
                view.switch.whichChild = coin.SO_SWITCH_NONE
                continue
            view.switch.whichChild = coin.SO_SWITCH_ALL
            self._place(view.transform, pose, ring.origin, ring.fade)
            view.set_dots(len(sides), pose.side)
            title = style.HOVER if result.hover_title == index else style.PLATE
            view.title_color.rgb = coin.SbColor(*title)
            under_ray = result.drop_marker is not None and result.drop_marker[0] == index
            view.back_color.rgb = coin.SbColor(*(style.PLATE_LIT if under_ray else style.PLATE))
            for slot, (cell, face) in enumerate(view.cells):
                hovered = result.hover == (index, slot)
                active = face is not None and face.action in active_actions
                cell.set_state(hovered, active, face is not None)
        for side, ghost_view in self._ghosts.items():
            if side not in ring.ghosts:
                ghost_view.switch.whichChild = coin.SO_SWITCH_NONE
        for side, ghost in ring.ghosts.items():
            if side not in self._ghosts:
                self._ghosts[side] = _Ghost()
                self._ghost_sep.addChild(self._ghosts[side].switch)
            view = self._ghosts[side]
            view.switch.whichChild = coin.SO_SWITCH_ALL
            self._place(view.transform, ghost, ring.origin, ring.fade)
            over = result.drop_marker is not None and result.drop_marker[0] is None and result.drop_marker[2] == side
            view.color.rgb = coin.SbColor(*(style.HOVER if over else style.DROP))
        marker = result.drop_marker
        if marker is not None and marker[0] is not None and marker[0] in ring.poses:
            self._marker.show(ring.poses[marker[0]], marker[1], ring.origin, ring.fade)
        else:
            self._marker.switch.whichChild = coin.SO_SWITCH_NONE
        if result.lifted is not None and result.lift_point is not None:
            self._card.switch.whichChild = coin.SO_SWITCH_ALL
            self._card.text.string = layout.pages[result.lifted].name
            up = (0.0, 1.0, 0.0)
            point = mu.add(result.lift_point, mu.mul(up, 0.04))
            self._card.transform.translation.setValue(*point)
            self._card.transform.rotation.setValue(*mu.quat_multiply(mu.look_at(point, head), mu.quat_from_axis_angle(up, 3.141592653589793)))
        else:
            self._card.switch.whichChild = coin.SO_SWITCH_NONE
