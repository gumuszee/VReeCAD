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
"""Coin3D drawing of the palette ring (docs/ux-design.md, Visual style). Flat, unlit, high contrast: panels never depend on the
scene lighting. Sizes are physical: the face edge is `ring.CELL`, label glyphs are about 9 mm tall (Coin's default SoText3 size is
10 units, so a scale of 0.0009 gives that height)."""

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import ring as rg

PLATE = (0.10, 0.11, 0.14)
FACE = (0.20, 0.22, 0.28)
EMPTY = (0.13, 0.14, 0.17)
HOVER = (0.30, 0.45, 0.80)
ACTIVE = (0.95, 0.65, 0.10)
TEXT = (1.0, 1.0, 1.0)
TEXT_ON_ACTIVE = (0.05, 0.05, 0.05)
TEXT_SCALE = 0.0009
LINE_HEIGHT = 0.0105
DEPTH = 0.004


def _cube(w, h, d):
    cube = coin.SoCube()
    cube.width, cube.height, cube.depth = w, h, d
    return cube


class _Cell:
    def __init__(self, parent, x, y, face_label):
        self.sep = coin.SoSeparator()
        move = coin.SoTranslation()
        move.translation.setValue(x, y, 0.0)
        self.sep.addChild(move)
        self.plate_color = coin.SoBaseColor()
        self.plate_color.rgb = coin.SbColor(*(FACE if face_label is not None else EMPTY))
        self.sep.addChild(self.plate_color)
        self.sep.addChild(_cube(rg.CELL, rg.CELL, DEPTH))
        self.text_color = None
        if face_label is not None:
            lines = lay.wrap_label(face_label)
            text_sep = coin.SoSeparator()
            shift = coin.SoTranslation()
            shift.translation.setValue(0.0, (len(lines) - 1) * 0.5 * LINE_HEIGHT - 0.0035, DEPTH * 0.5 + 0.0005)
            text_sep.addChild(shift)
            self.text_color = coin.SoBaseColor()
            self.text_color.rgb = coin.SbColor(*TEXT)
            text_sep.addChild(self.text_color)
            scale = coin.SoScale()
            scale.scaleFactor.setValue(TEXT_SCALE, TEXT_SCALE, TEXT_SCALE)
            text_sep.addChild(scale)
            text = coin.SoText3()
            text.string.setValues(0, len(lines), lines)
            text.justification = coin.SoText3.CENTER
            text_sep.addChild(text)
            self.sep.addChild(text_sep)
        parent.addChild(self.sep)

    def set_state(self, hover, active, has_face):
        color = EMPTY if not has_face else ACTIVE if active else HOVER if hover else FACE
        self.plate_color.rgb = coin.SbColor(*color)
        if self.text_color is not None:
            self.text_color.rgb = coin.SbColor(*(TEXT_ON_ACTIVE if active else TEXT))


class _Page:
    def __init__(self, page, faces, page_count):
        self.switch = coin.SoSwitch()
        self.switch.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        sep.addChild(self.transform)
        plate_color = coin.SoBaseColor()
        plate_color.rgb = coin.SbColor(*PLATE)
        sep.addChild(plate_color)
        backing = coin.SoSeparator()
        move = coin.SoTranslation()
        move.translation.setValue(0.0, 0.012, -DEPTH)
        backing.addChild(move)
        backing.addChild(_cube(rg.GRID_W + 0.02, rg.GRID_H + 0.05, DEPTH))
        sep.addChild(backing)
        title = coin.SoSeparator()
        t_move = coin.SoTranslation()
        t_move.translation.setValue(-rg.GRID_W / 2, rg.GRID_H / 2 + 0.016, DEPTH * 0.5)
        title.addChild(t_move)
        t_color = coin.SoBaseColor()
        t_color.rgb = coin.SbColor(0.7, 0.75, 0.9)
        title.addChild(t_color)
        t_scale = coin.SoScale()
        t_scale.scaleFactor.setValue(TEXT_SCALE, TEXT_SCALE, TEXT_SCALE)
        title.addChild(t_scale)
        t_text = coin.SoText3()
        t_text.string = page.name
        title.addChild(t_text)
        sep.addChild(title)
        # page dots below the grid: the filled one is the page at the front
        self.dots = []
        for i in range(page_count):
            dot_sep = coin.SoSeparator()
            dot_move = coin.SoTranslation()
            dot_move.translation.setValue((i - (page_count - 1) / 2) * 0.014, -(rg.GRID_H / 2 + 0.027), DEPTH * 0.5)
            dot_sep.addChild(dot_move)
            dot_color = coin.SoBaseColor()
            dot_color.rgb = coin.SbColor(0.4, 0.42, 0.5)
            dot_sep.addChild(dot_color)
            dot = coin.SoSphere()
            dot.radius = 0.0035
            dot_sep.addChild(dot)
            sep.addChild(dot_sep)
            self.dots.append(dot_color)
        self.cells = []
        for slot, face_id in enumerate(page.slots):
            col, row = slot % lay.COLS, slot // lay.COLS
            x = (col - (lay.COLS - 1) / 2) * (rg.CELL + rg.GAP)
            y = ((lay.ROWS - 1) / 2 - row) * (rg.CELL + rg.GAP)
            face = faces.get(face_id) if face_id else None
            self.cells.append((_Cell(sep, x, y, face.label if face else None), face))
        self.switch.addChild(sep)


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
        self._pages_sep = coin.SoSeparator()
        sep.addChild(self._pages_sep)
        self.root.addChild(sep)
        self._pages = []
        self._built_for = None

    def build(self, layout, faces):
        """(Re)build the page nodes for a layout; `faces` maps face id to `layout.Face`."""
        self._pages_sep.removeAllChildren()
        self._pages = []
        for page in layout.pages:
            view = _Page(page, faces, len(layout.pages))
            self._pages.append(view)
            self._pages_sep.addChild(view.switch)
        self._built_for = (id(layout), tuple(tuple(p.slots) for p in layout.pages))

    def needs_build(self, layout):
        return self._built_for != (id(layout), tuple(tuple(p.slots) for p in layout.pages))

    def update(self, ring, result, layout, faces, controller, head, active_actions=()):
        if ring.fade <= 0.02:
            self.root.whichChild = coin.SO_SWITCH_NONE
            return
        if self.needs_build(layout):
            self.build(layout, faces)
        self.root.whichChild = coin.SO_SWITCH_ALL
        for index, view in enumerate(self._pages):
            cos = ring.page_cos(index)
            if cos < -0.05:
                view.switch.whichChild = coin.SO_SWITCH_NONE
                continue
            view.switch.whichChild = coin.SO_SWITCH_ALL
            centre, u, v, n = ring.page_frame(index, controller, head)
            # pop in: pages grow from the ring axis while the ring fades in
            if ring.fade < 1.0:
                origin = ring.frame_vectors(controller, head)[0]
                centre = mu.lerp(origin, centre, ring.fade)
            view.transform.translation.setValue(*centre)
            view.transform.rotation.setValue(*mu.quat_from_basis(u, v, n))
            for i, dot in enumerate(view.dots):
                dot.rgb = coin.SbColor(*((0.95, 0.95, 1.0) if i == ring.front_page() else (0.4, 0.42, 0.5)))
            s = 0.5 + 0.5 * ring.fade
            view.transform.scaleFactor.setValue(s, s, s)
            for slot, (cell, face) in enumerate(view.cells):
                hovered = result.hover == (index, slot)
                active = face is not None and face.action in active_actions
                cell.set_state(hovered, active, face is not None)
