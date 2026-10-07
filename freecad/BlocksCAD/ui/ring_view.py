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
the scene lighting. Sizes are physical: the face edge is `ring.CELL`, label glyphs are about 7 mm tall (`style.PANEL_TEXT`). Every
colour node is a `style.Paint` that is written only when the colour changes, so a still carousel costs the scene graph nothing."""

from pivy import coin

from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import ring as rg
from freecad.BlocksCAD.ui import style
from freecad.BlocksCAD.ui import value_module

DEPTH = 0.004
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
    paint = style.Paint(rgb)
    sep.addChild(paint.node)
    sep.addChild(_cube(w, h, DEPTH))
    parent.addChild(sep)
    return paint


def _text(parent, lines, x, y, z, rgb, justification=coin.SoText3.CENTER, factor=1.0):
    """Text lines centred vertically around y; returns the text node."""
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
    return text


def _placement(owner, parent):
    """Give `owner` a transform under `parent` and the fields `RingView._place` writes (looking a pivy field up costs about 20
    microseconds, so they are looked up once)."""
    transform = coin.SoTransform()
    parent.addChild(transform)
    owner.move, owner.turn, owner.scale, owner.size = transform.translation, transform.rotation, transform.scaleFactor, None


class _Cell:
    def __init__(self, parent, x, y, face_label, palette):
        self.sep = coin.SoSeparator()
        self.sep.addChild(_at(x, y, 0.0))
        self.palette = palette
        self.plate_color = _plate(self.sep, rg.CELL, rg.CELL, palette.face if face_label is not None else palette.empty)
        self.text_color = None
        self.label = face_label
        if face_label is not None:
            text_sep = coin.SoSeparator()
            self._text_move = _at(0.0, 0.0, DEPTH * 0.5 + 0.0005)
            text_sep.addChild(self._text_move)
            self.text_color = style.Paint(style.TEXT)
            text_sep.addChild(self.text_color.node)
            text_sep.addChild(style.text_scale(style.PANEL_TEXT))
            self._text = coin.SoText3()
            self._text.justification = coin.SoText3.CENTER
            text_sep.addChild(self._text)
            self.sep.addChild(text_sep)
            self._write(face_label)
        parent.addChild(self.sep)

    def _write(self, label):
        lines = lay.wrap_label(label)
        self._text_move.translation.setValue(0.0, ((len(lines) - 1) * 0.5 * style.LINE_HEIGHT - 0.0035) * style.PANEL_TEXT,
                                             DEPTH * 0.5 + 0.0005)
        self._text.string.setNum(len(lines))
        self._text.string.setValues(0, len(lines), lines)

    def set_label(self, label):
        """Change the text of the face (faces that show a value)."""
        if self.text_color is not None and label != self.label:
            self.label = label
            self._write(label)

    def set_state(self, hover, active, has_face, lifted=False, target=False):
        """`lifted`: the face is held in the hand (its place is dimmed); `target`: a lifted face would land here."""
        color = (self.palette.empty if not has_face or lifted else style.GRAB if target else style.ACTIVE if active
                 else style.HOVER if hover else self.palette.face)
        self.plate_color.set(color)
        if self.text_color is not None:
            self.text_color.set(style.TEXT_ON_ACTIVE if (active or target) and not lifted
                                else style.TEXT_DIM if lifted else style.TEXT)


class _SliderRow:
    """A slider on a whole row of the grid: the label, the track and the handle."""
    TRACK_H = 0.003
    TRACK_Y = -0.009
    HANDLE = (0.007, 0.019)

    def __init__(self, parent, y, palette):
        self.low, self.high = -rg.GRID_W / 2 + rg.SLIDER_PAD, rg.GRID_W / 2 - rg.SLIDER_PAD
        self.palette = palette
        self.sep = coin.SoSeparator()
        self.sep.addChild(_at(0.0, y, 0.0))
        self.plate_color = _plate(self.sep, rg.GRID_W, rg.CELL, palette.face)
        self.track_color = _plate(self.sep, self.high - self.low, self.TRACK_H, palette.plate, 0.0, self.TRACK_Y, DEPTH * 0.5)
        handle = coin.SoSeparator()
        self._handle_move = coin.SoTranslation()
        self._handle_at = self._handle_move.translation
        self._handle_x = None
        handle.addChild(self._handle_move)
        self.handle_color = style.Paint(style.TEXT)
        handle.addChild(self.handle_color.node)
        handle.addChild(_cube(self.HANDLE[0], self.HANDLE[1], DEPTH))
        self.sep.addChild(handle)
        label = coin.SoSeparator()
        label.addChild(_at(-rg.GRID_W / 2 + 0.009, 0.008, DEPTH * 0.5 + 0.0005))
        label.addChild(style.color(style.TEXT))
        label.addChild(style.text_scale(style.PANEL_TEXT * 1.1))
        self.text = coin.SoText3()
        self.text.justification = coin.SoText3.LEFT
        label.addChild(self.text)
        self.sep.addChild(label)
        self.label = None
        parent.addChild(self.sep)

    def set(self, fraction, label, hovered, dragged, picked=False, bar_hot=False):
        x = self.low + fraction * (self.high - self.low)
        if x != self._handle_x:
            self._handle_x = x
            self._handle_at.setValue(x, self.TRACK_Y, DEPTH)
        if label != self.label:
            self.label = label
            self.text.string = label
        self.plate_color.set(style.HOVER if hovered else self.palette.picked if picked else self.palette.face)
        self.handle_color.set(style.ACTIVE if dragged else style.TEXT)
        self.track_color.set(style.TEXT if bar_hot else self.palette.plate)


class _Panel:
    """One panel (page) in its own coordinates: x right, y up, z out of the panel."""

    def __init__(self, page, faces):
        self.switch = coin.SoSwitch()
        self.switch.whichChild = coin.SO_SWITCH_NONE
        self.palette = style.panel_palette(page.name, page.name in value_module.PAGE_NAMES)
        palette = self.palette
        outer = coin.SoSeparator()
        _placement(self, outer)
        self.back_color = _plate(outer, rg.PANEL_W, rg.PANEL_H, palette.plate, 0.0, 0.0, -DEPTH)
        # everything in front of the plate: seen from behind it is hidden by the plate, so it is not drawn then
        self.front = coin.SoSwitch()
        self.front.whichChild = coin.SO_SWITCH_ALL
        self.facing = True
        sep = coin.SoSeparator()
        self.front.addChild(sep)
        outer.addChild(self.front)
        self.title_color = _plate(sep, rg.GRID_W, TITLE_H, palette.title, 0.0, TITLE_CENTRE, 0.0)
        self.title = _text(sep, [page.name], -rg.GRID_W / 2 + 0.006, TITLE_CENTRE, DEPTH * 0.5 + 0.0005, palette.title_text,
                           coin.SoText3.LEFT, style.PANEL_TEXT)
        self.title_text = page.name
        for i in (-1, 0, 1):   # grooves: the title bar is the handle for lifting the panel
            _plate(sep, 0.012, 0.0012, palette.groove, rg.GRID_W / 2 - 0.012, TITLE_CENTRE + i * 0.0045, DEPTH * 0.5)
        self.cells = []
        self.sliders = {}          # row of the grid -> (slider view, face id)
        for row in range(lay.ROWS):
            face = faces.get(page.slots[row * lay.COLS]) if page.slots[row * lay.COLS] else None
            if face is not None and face.kind == "slider":
                y = ((lay.ROWS - 1) / 2 - row) * (rg.CELL + rg.GAP) + rg.GRID_Y
                self.sliders[row] = (_SliderRow(sep, y, palette), face.id)
        for slot, face_id in enumerate(page.slots):
            col, row = slot % lay.COLS, slot // lay.COLS
            x = (col - (lay.COLS - 1) / 2) * (rg.CELL + rg.GAP)
            y = ((lay.ROWS - 1) / 2 - row) * (rg.CELL + rg.GAP) + rg.GRID_Y
            face = faces.get(face_id) if face_id else None
            if row in self.sliders:                      # the row belongs to its slider
                self.cells.append((None, None))
                continue
            self.cells.append((_Cell(sep, x, y, face.label if face else None, palette), face))
        self.switch.addChild(outer)

    def set_facing(self, facing):
        """Draw the contents of the panel only while the head is in front of its plate."""
        if facing != self.facing:
            self.facing = facing
            self.front.whichChild = coin.SO_SWITCH_ALL if facing else coin.SO_SWITCH_NONE


class _Ghost:
    """The empty side at the end of the carousel while something is lifted: a panel dropped on it gets a side of its own, a face
    dropped on it is hidden."""
    PANEL_LABEL, FACE_LABEL = "Drop here", "Hide face"

    def __init__(self):
        self.switch = coin.SoSwitch()
        self.switch.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()
        _placement(self, sep)
        self.color = _plate(sep, rg.PANEL_W, rg.PANEL_H, style.DROP, 0.0, 0.0, -DEPTH)
        self.text = _text(sep, [self.PANEL_LABEL], 0.0, 0.0, 0.0005, style.TEXT, factor=1.2)
        self.label = self.PANEL_LABEL
        self.switch.addChild(sep)

    def set_label(self, label):
        if label != self.label:
            self.label = label
            self.text.string = label


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
    def _place(view, pose, origin, fade):
        """Place a panel (or a ghost); it grows from the carousel axis while the carousel fades in."""
        centre = pose.centre if fade >= 1.0 else mu.lerp(origin, pose.centre, fade)
        view.move.setValue(*centre)
        view.turn.setValue(*mu.quat_from_basis(pose.u, pose.v, pose.n))
        s = 0.5 + 0.5 * fade
        if s != view.size:
            view.size = s
            view.scale.setValue(s, s, s)

    def update(self, ring, result, layout, faces, head, active_actions=(), labels=None, sliders=None, titles=None):
        if ring.fade <= 0.02:
            self.root.whichChild = coin.SO_SWITCH_NONE
            return
        if self.needs_build(layout):
            self.build(layout, faces)
        self.root.whichChild = coin.SO_SWITCH_ALL
        for index, view in enumerate(self._panels):
            pose = ring.poses.get(index)
            if pose is None:
                view.switch.whichChild = coin.SO_SWITCH_NONE
                continue
            view.switch.whichChild = coin.SO_SWITCH_ALL
            self._place(view, pose, ring.origin, ring.fade)
            under_ray = result.drop_marker is not None and result.drop_marker[0] == index
            view.back_color.set(view.palette.plate_lit if under_ray else view.palette.plate)
            view.set_facing(mu.dot(mu.sub(head, pose.centre), pose.n) > 0.0)
            if not view.facing:
                continue                                   # seen from behind: only the plate shows
            view.title_color.set(style.HOVER if result.hover_title == index else view.palette.title)
            text = (titles or {}).get(layout.pages[index].name, layout.pages[index].name)
            if text != view.title_text:
                view.title_text = text
                view.title.string = text
            for row, (slider_view, face_id) in view.sliders.items():
                fraction, text, *picked = (sliders or {}).get(face_id, (0.0, "-"))
                hovered = result.hover == (index, row * lay.COLS)
                slider_view.set(fraction, text, hovered, hovered and ring.slider_drag is not None, bool(picked and picked[0]),
                                result.bar_hover == (index, row * lay.COLS))
            for slot, (cell, face) in enumerate(view.cells):
                if cell is None:
                    continue
                hovered = result.hover == (index, slot)
                active = face is not None and face.action in active_actions
                if face is not None and labels and face.id in labels:
                    cell.set_label(labels[face.id])
                cell.set_state(hovered, active, face is not None, result.lifted_face == (index, slot),
                               result.face_target == (index, slot))
        for side, ghost_view in self._ghosts.items():
            if side not in ring.ghosts:
                ghost_view.switch.whichChild = coin.SO_SWITCH_NONE
        for side, ghost in ring.ghosts.items():
            if side not in self._ghosts:
                self._ghosts[side] = _Ghost()
                self._ghost_sep.addChild(self._ghosts[side].switch)
            view = self._ghosts[side]
            view.switch.whichChild = coin.SO_SWITCH_ALL
            self._place(view, ghost, ring.origin, ring.fade)
            view.set_label(_Ghost.FACE_LABEL if result.lifted_face is not None else _Ghost.PANEL_LABEL)
            over = result.drop_marker is not None and result.drop_marker[0] is None and result.drop_marker[2] == side
            view.color.set(style.HOVER if over else style.DROP)
        marker = result.drop_marker
        if marker is not None and marker[0] is not None and marker[0] in ring.poses:
            self._marker.show(ring.poses[marker[0]], marker[1], ring.origin, ring.fade)
        else:
            self._marker.switch.whichChild = coin.SO_SWITCH_NONE
        card = None
        if result.lifted is not None:
            card = layout.pages[result.lifted].name
        elif result.lifted_face is not None:
            face = faces.get(layout.face_at(*result.lifted_face))
            card = (labels or {}).get(face.id, face.label) if face is not None else None
        if card is not None and result.lift_point is not None:
            self._card.switch.whichChild = coin.SO_SWITCH_ALL
            self._card.text.string = card
            up = (0.0, 1.0, 0.0)
            point = mu.add(result.lift_point, mu.mul(up, 0.04))
            self._card.transform.translation.setValue(*point)
            self._card.transform.rotation.setValue(*mu.quat_multiply(mu.look_at(point, head), mu.quat_from_axis_angle(up, 3.141592653589793)))
        else:
            self._card.switch.whichChild = coin.SO_SWITCH_NONE
