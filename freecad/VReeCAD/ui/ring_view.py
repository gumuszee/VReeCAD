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
the scene lighting. Sizes are physical: the face edge is `ring.CELL`, label glyphs are about 7 mm tall (`style.PANEL_TEXT`).

The scene graph is built to cost the renderer as little as possible, because the carousel is drawn twice a frame for the headset:
the carousel hangs under one transform that follows the controller, so a moving hand writes one node; the panels stand in the frame
of the carousel and are placed only when the carousel turns or fades; all the flat rectangles of a panel (plate, title bar, faces,
tracks) are one face set with a colour per rectangle, so a panel is a handful of draw calls plus its texts; panels that show their
back, and panels whose input has not changed since the last frame, cost nothing. Every colour is written only when it changes, so a
still carousel costs the scene graph nothing."""

from pivy import coin

from freecad.VReeCAD.core import mathutil as mu
from freecad.VReeCAD.ui import layout as lay
from freecad.VReeCAD.ui import ring as rg
from freecad.VReeCAD.ui import style
from freecad.VReeCAD.ui import value_module

DEPTH = 0.004
TITLE_H = rg.TITLE_Y[1] - rg.TITLE_Y[0]
TEXT_LIFT = DEPTH * 0.5 + 0.0005      # text lies this far in front of the plane of the plates
MARKER_LIFT = 0.003
RAISE = 0.005                         # a hovered, active or dragged face stands this far (0.5 cm) in front of its panel


def _at(x, y, z):
    move = coin.SoTranslation()
    move.translation.setValue(x, y, z)
    return move


class _Plate:
    """One rectangle of a `_Plates`: `set` changes its colour, `move` its place."""
    __slots__ = ("owner", "index", "rgb")

    def __init__(self, owner, index, rgb):
        self.owner, self.index, self.rgb = owner, index, rgb

    def set(self, rgb):
        if rgb != self.rgb:
            self.rgb = rgb
            self.owner.rgb[self.index] = rgb
            self.owner.dirty = True

    def move(self, x, y):
        self.owner.move(self.index, x, y)

    def lift(self, z):
        self.owner.lift(self.index, z)


class _Plates:
    """The flat rectangles of one panel (or a ghost) in one face set: one draw call, a colour for each rectangle. A rectangle lies in
    the plane `z` in front of the panel and has only a front, which is all that is ever seen of it (a panel seen from behind shows
    its back plate). `add` all of them, then hang `build()` in the scene."""

    def __init__(self):
        self.rects = []          # (width, height, x, y, z)
        self.rgb = []
        self.dirty = False
        self._points = self._colours = None

    def add(self, w, h, rgb, x=0.0, y=0.0, z=0.0):
        self.rects.append((w, h, x, y, z))
        rgb = tuple(rgb)
        self.rgb.append(rgb)
        return _Plate(self, len(self.rects) - 1, rgb)

    @staticmethod
    def _corners(w, h, x, y, z):
        return [(x - w / 2, y - h / 2, z), (x + w / 2, y - h / 2, z), (x + w / 2, y + h / 2, z), (x - w / 2, y + h / 2, z)]

    def build(self):
        count = len(self.rects)
        sep = style.cached(coin.SoSeparator())
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, 4 * count, [p for rect in self.rects for p in self._corners(*rect)])
        sep.addChild(coords)
        binding = coin.SoMaterialBinding()
        binding.value = coin.SoMaterialBinding.PER_FACE
        sep.addChild(binding)
        colours = coin.SoBaseColor()
        colours.rgb.setValues(0, count, self.rgb)
        sep.addChild(colours)
        faces = coin.SoFaceSet()
        faces.numVertices.setValues(0, count, [4] * count)
        sep.addChild(faces)
        self._points, self._colours = coords.point, colours.rgb
        return sep

    def move(self, index, x, y):
        w, h, _, _, z = self.rects[index]
        self.rects[index] = (w, h, x, y, z)
        self._points.setValues(4 * index, 4, self._corners(w, h, x, y, z))

    def lift(self, index, z):
        w, h, x, y, old = self.rects[index]
        if z != old:
            self.rects[index] = (w, h, x, y, z)
            self._points.setValues(4 * index, 4, self._corners(w, h, x, y, z))

    def flush(self):
        """Write the colours that changed since the last flush (one write for all of them)."""
        if self.dirty:
            self.dirty = False
            self._colours.setValues(0, len(self.rgb), self.rgb)


def _text(parent, lines, x, y, z, rgb, justification=coin.SoText3.CENTER, factor=1.0):
    """Text lines centred vertically around y; returns the text node."""
    sep = style.cached(coin.SoSeparator())
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


class _Place:
    """A transform that puts a panel (or a ghost) in the frame of the carousel and grows it from the axis while the carousel fades in.
    It is written only when the place changes, that is when the carousel turns or fades."""

    def __init__(self, parent):
        transform = coin.SoTransform()
        parent.addChild(transform)
        self._move, self._turn, self._scale = transform.translation, transform.rotation, transform.scaleFactor
        self._key = None

    def set(self, pose, fade):
        key = (pose.lcentre, pose.lu, fade)
        if key != self._key:
            self._key = key
            self._move.setValue(*(pose.lcentre if fade >= 1.0 else mu.mul(pose.lcentre, fade)))
            self._turn.setValue(*mu.quat_from_basis(pose.lu, pose.lv, pose.ln))
            size = 0.5 + 0.5 * fade
            self._scale.setValue(size, size, size)


class _Cell:
    """A face of a panel: its rectangle is in the plates of the panel, its text is a node of its own."""

    def __init__(self, parent, x, y, face_label, palette, plates, base=None):
        self.palette = palette
        self.base = base if base is not None else palette.face          # the colour of the face at rest: a face may wear a colour of its own
        self.x, self.y = x, y
        self.plate = plates.add(rg.CELL, rg.CELL, self.base if face_label is not None else palette.empty, x, y, DEPTH * 0.5)
        self.raised = False
        self.text_color = None
        self.label = face_label
        if face_label is not None:
            text_sep = style.cached(coin.SoSeparator())
            self._text_move = _at(x, y, TEXT_LIFT)
            self._text_at = self._text_move.translation
            text_sep.addChild(self._text_move)
            self.text_color = style.Paint(style.TEXT)
            text_sep.addChild(self.text_color.node)
            text_sep.addChild(style.text_scale(style.PANEL_TEXT))
            self._text = coin.SoText3()
            self._text.justification = coin.SoText3.CENTER
            self._string = self._text.string
            text_sep.addChild(self._text)
            parent.addChild(text_sep)
            self._write(face_label)

    def _write(self, label):
        lines = lay.wrap_label(label)
        self._text_y = self.y + ((len(lines) - 1) * 0.5 * style.LINE_HEIGHT - 0.0035) * style.PANEL_TEXT
        self._text_at.setValue(self.x, self._text_y, TEXT_LIFT + (RAISE if self.raised else 0.0))
        self._string.setNum(len(lines))
        self._string.setValues(0, len(lines), lines)

    def set_label(self, label):
        """Change the text of the face (faces that show a value)."""
        if self.text_color is not None and label != self.label:
            self.label = label
            self._write(label)

    def set_state(self, hover, active, has_face, lifted=False, target=False, inert=False):
        """`lifted`: the face is held in the hand (its place is dimmed); `target`: a lifted face would land here; `inert`: the face
        only shows something, it is never lit by the pointer."""
        color = (self.palette.empty if not has_face or lifted else style.GRAB if target else self.palette.picked if inert
                 else style.ACTIVE if active else style.HOVER if hover else self.base)
        self.plate.set(color)
        raised = has_face and not lifted and not inert and (hover or active or target)
        if raised != self.raised:
            self.raised = raised
            lift = RAISE if raised else 0.0
            self.plate.lift(DEPTH * 0.5 + lift)
            if self.text_color is not None:
                self._text_at.setValue(self.x, self._text_y, TEXT_LIFT + lift)
        if self.text_color is not None:
            self.text_color.set(style.TEXT_ON_ACTIVE if (active or target) and not lifted
                                else style.TEXT_DIM if lifted else style.TEXT)


class _SliderRow:
    """A slider on a whole row of the grid: the label, the track and the handle."""
    TRACK_H = 0.003
    TRACK_Y = -0.009
    HANDLE = (0.007, 0.019)

    def __init__(self, parent, y, palette, plates, grid_w=rg.GRID_W):
        self.low, self.high = -grid_w / 2 + rg.SLIDER_PAD, grid_w / 2 - rg.SLIDER_PAD
        self.palette = palette
        self.y = y
        self.grid_w = grid_w
        self.plate_color = plates.add(grid_w, rg.CELL, palette.face, 0.0, y, DEPTH * 0.5)
        self.track_color = plates.add(self.high - self.low, self.TRACK_H, palette.plate, 0.0, y + self.TRACK_Y, DEPTH)
        self.handle_color = plates.add(self.HANDLE[0], self.HANDLE[1], style.TEXT, self.low, y + self.TRACK_Y, DEPTH * 1.5)
        self._handle_x = self.low
        label = style.cached(coin.SoSeparator())
        move = _at(-grid_w / 2 + 0.009, y + 0.008, TEXT_LIFT)
        self._label_at = move.translation
        self.raised = False
        label.addChild(move)
        label.addChild(style.color(style.TEXT))
        label.addChild(style.text_scale(style.PANEL_TEXT * 1.1))
        self.text = coin.SoText3()
        self.text.justification = coin.SoText3.LEFT
        self._string = self.text.string
        label.addChild(self.text)
        parent.addChild(label)
        self.label = None

    def set(self, fraction, label, hovered, dragged, picked=False, bar_hot=False):
        x = self.low + fraction * (self.high - self.low)
        if x != self._handle_x:
            self._handle_x = x
            self.handle_color.move(x, self.y + self.TRACK_Y)
        if label != self.label:
            self.label = label
            self._string.setValue(label)
        self.plate_color.set(style.HOVER if hovered else self.palette.picked if picked else self.palette.face)
        self.handle_color.set(style.ACTIVE if dragged else style.TEXT)
        self.track_color.set(style.TEXT if bar_hot else self.palette.plate)
        raised = hovered or dragged or bar_hot
        if raised != self.raised:
            self.raised = raised
            lift = RAISE if raised else 0.0
            self.plate_color.lift(DEPTH * 0.5 + lift)
            self.track_color.lift(DEPTH + lift)
            self.handle_color.lift(DEPTH * 1.5 + lift)
            self._label_at.setValue(-self.grid_w / 2 + 0.009, self.y + 0.008, TEXT_LIFT + lift)


class _ReadoutRow:
    """The readout of the picked value on a whole row of the grid: its name in small letters over its number in large ones (smaller
    when the text is long). Text that is being typed is shown on an active plate, so it cannot be mistaken for the value."""
    SMALL_Y, LARGE_Y = 0.0095, -0.0125         # baselines of the two lines, from the centre of the row
    SMALL = 0.7
    LARGE = ((14, 1.9), (21, 1.3), (999, 0.88))    # (longest text, size) for the large line

    def __init__(self, parent, y, palette, plates, grid_w=rg.GRID_W):
        self.palette = palette
        self.plate_color = plates.add(grid_w, rg.CELL, palette.picked, 0.0, y, DEPTH * 0.5)
        x = -grid_w / 2 + 0.009
        self.small, self.small_color, _ = self._line(parent, x, y + self.SMALL_Y, self.SMALL)
        self.large, self.large_color, self._large_scale = self._line(parent, x, y + self.LARGE_Y, self.LARGE[0][1])
        self.texts = (None, None)
        self.typing = None
        self._size = self.LARGE[0][1]

    @staticmethod
    def _line(parent, x, y, size):
        line = style.cached(coin.SoSeparator())
        line.addChild(_at(x, y, TEXT_LIFT))
        paint = style.Paint(style.TEXT)
        line.addChild(paint.node)
        scale = style.text_scale(size)
        line.addChild(scale)
        text = coin.SoText3()
        text.justification = coin.SoText3.LEFT
        line.addChild(text)
        parent.addChild(line)
        return text.string, paint, scale.scaleFactor

    def set(self, small, large, typing):
        if (small, large) != self.texts:
            if small != self.texts[0]:
                self.small.setValue(small)
            if large != self.texts[1]:
                self.large.setValue(large)
                size = next(size for longest, size in self.LARGE if len(large) <= longest)
                if size != self._size:
                    self._size = size
                    self._large_scale.setValue(style.TEXT_SCALE * size, style.TEXT_SCALE * size, style.TEXT_SCALE * size)
            self.texts = (small, large)
        if typing != self.typing:
            self.typing = typing
            self.plate_color.set(style.ACTIVE if typing else self.palette.picked)
            self.small_color.set(style.TEXT_ON_ACTIVE if typing else style.TEXT)
            self.large_color.set(style.TEXT_ON_ACTIVE if typing else style.TEXT)


class _Panel:
    """One panel (page) in its own coordinates: x right, y up, z out of the panel."""

    def __init__(self, page, faces):
        self.switch = coin.SoSwitch()
        self.shown = style.Show(self.switch)
        self.palette = style.panel_palette(page.name, page.name in value_module.PAGE_NAMES, page.hue)
        palette = self.palette
        outer = coin.SoSeparator()
        self.place = _Place(outer)
        back = _Plates()                        # the plate behind everything: all that shows when the panel is seen from behind
        dim = rg.dims(page.cols, page.rows)
        centre = dim.title_centre
        self.back_color = back.add(dim.panel_w, dim.panel_h, palette.plate, 0.0, 0.0, -DEPTH * 0.5)
        self._back = back
        outer.addChild(back.build())
        # everything in front of the plate: seen from behind it is hidden by the plate, so it is not drawn then
        self.front = coin.SoSwitch()
        self.front.whichChild = coin.SO_SWITCH_ALL
        self.facing = True
        self._front_show = style.Show(self.front, True)
        sep = style.cached(coin.SoSeparator())
        self.front.addChild(sep)
        outer.addChild(self.front)
        self.plates = _Plates()
        self.title_color = self.plates.add(dim.grid_w, TITLE_H, palette.title, 0.0, centre, DEPTH * 0.5)
        self.grooves = [self.plates.add(0.012, 0.0012, palette.groove, dim.grid_w / 2 - 0.012, centre + i * 0.0045, DEPTH)
                        for i in (-1, 0, 1)]        # grooves: the title bar is the handle for lifting the panel, a tap on them opens its editor
        self.menu_hover = False
        plates_at = sep.getNumChildren()
        sep.addChild(coin.SoSeparator())         # the place of the plates, which are built once every row has added its rectangles
        self.title = _text(sep, [page.name], -dim.grid_w / 2 + 0.006, centre, TEXT_LIFT, palette.title_text,
                           coin.SoText3.LEFT, style.PANEL_TEXT)
        self._title_string = self.title.string
        self.title_text = page.name
        self.hide_state = 0                      # the hide slot in the title bar: 0 none, 1 offered while a face is lifted, 2 the face is over it
        hide_x = (dim.hide_x[0] + dim.hide_x[1]) / 2
        self.hide_color = self.plates.add(dim.hide_x[1] - dim.hide_x[0], TITLE_H - 0.004, palette.title, hide_x, centre, DEPTH)
        self._hide_text = _text(sep, [""], hide_x, centre, TEXT_LIFT, style.TEXT, coin.SoText3.CENTER, style.PANEL_TEXT)
        self._hide_string = self._hide_text.string
        self.cells = []
        self.sliders = {}          # row of the grid -> (slider view, face id)
        self.readouts = {}         # row of the grid -> (readout view, face id)
        for row in range(page.rows):
            face = faces.get(page.slots[row * page.cols]) if page.slots[row * page.cols] else None
            y = ((page.rows - 1) / 2 - row) * (rg.CELL + rg.GAP) + rg.GRID_Y
            if face is not None and face.kind == "slider":
                self.sliders[row] = (_SliderRow(sep, y, palette, self.plates, dim.grid_w), face.id)
            elif face is not None and face.kind == "readout":
                self.readouts[row] = (_ReadoutRow(sep, y, palette, self.plates, dim.grid_w), face.id)
        for slot, face_id in enumerate(page.slots):
            col, row = slot % page.cols, slot // page.cols
            x = (col - (page.cols - 1) / 2) * (rg.CELL + rg.GAP)
            y = ((page.rows - 1) / 2 - row) * (rg.CELL + rg.GAP) + rg.GRID_Y
            face = faces.get(face_id) if face_id else None
            if row in self.sliders or row in self.readouts:    # the row belongs to its slider or readout
                self.cells.append((None, None))
                continue
            base = None
            if face is not None and face.swatch is not None:
                base = face.swatch
            elif face is not None and face.tint is not None:
                base = style.tinted(face.tint).face
            self.cells.append((_Cell(sep, x, y, face.label if face else None, palette, self.plates, base), face))
        sep.replaceChild(plates_at, self.plates.build())
        self.switch.addChild(outer)
        self.key = None            # what the contents were last made for (`RingView.update`)
        self.cols = page.cols

    def set_facing(self, facing):
        """Draw the contents of the panel only while the head is in front of its plate."""
        if facing != self.facing:
            self.facing = facing
            self._front_show.set(facing)

    def set_menu_hover(self, hovered):
        if hovered != self.menu_hover:
            self.menu_hover = hovered
            for groove in self.grooves:
                groove.set(style.HOVER if hovered else self.palette.groove)

    def set_hide_slot(self, state):
        """Show the hide slot (an X in the title bar) while a face is lifted, lit while the face is over it."""
        if state != self.hide_state:
            self.hide_state = state
            self.hide_color.set(self.palette.title if state == 0 else style.HOVER if state == 2 else style.DROP)
            self._hide_string.setValue("X" if state else "")

    def set_title(self, text):
        if text != self.title_text:
            self.title_text = text
            self._title_string.setValue(text)

    def flush(self):
        self._back.flush()
        self.plates.flush()


class _Ghost:
    """The empty side at the end of the carousel while something is lifted: a panel dropped on it gets a side of its own, a face
    dropped on it is hidden."""
    PANEL_LABEL = "Drop here"

    def __init__(self):
        self.switch = coin.SoSwitch()
        self.shown = style.Show(self.switch)
        sep = coin.SoSeparator()
        self.place = _Place(sep)
        self.plates = _Plates()
        self.color = self.plates.add(rg.PANEL_W, rg.PANEL_H, style.DROP, 0.0, 0.0, -DEPTH * 0.5)
        sep.addChild(self.plates.build())
        self.text = _text(sep, [self.PANEL_LABEL], 0.0, 0.0, 0.0005, style.TEXT, factor=1.2)
        self._string = self.text.string
        self.label = self.PANEL_LABEL
        self.switch.addChild(sep)

    def set_label(self, label):
        if label != self.label:
            self.label = label
            self._string.setValue(label)


class _Card:
    """The lifted panel that follows the ray."""

    def __init__(self):
        self.switch = coin.SoSwitch()
        self.shown = style.Show(self.switch)
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        self._move, self._turn = self.transform.translation, self.transform.rotation
        sep.addChild(self.transform)
        plates = _Plates()
        plates.add(0.11, 0.032, style.GRAB, 0.0, 0.0, DEPTH * 0.5)
        sep.addChild(plates.build())
        self.text = coin.SoText3()
        self._string = self.text.string
        text_sep = style.cached(coin.SoSeparator())
        text_sep.addChild(_at(0.0, -0.0035, TEXT_LIFT))
        text_sep.addChild(style.color(style.TEXT_ON_ACTIVE))
        text_sep.addChild(style.text_scale())
        self.text.justification = coin.SoText3.CENTER
        text_sep.addChild(self.text)
        sep.addChild(text_sep)
        self.switch.addChild(sep)
        self.label = None

    def show(self, label, point, rotation):
        if label != self.label:
            self.label = label
            self._string.setValue(label)
        self._move.setValue(*point)
        self._turn.setValue(*rotation)
        self.shown.set(True)


class _Marker:
    """The bar that shows where the lifted panel goes: beside the panel under the ray (left or right) or as a new row (above or below)."""
    BAR = 0.008

    def __init__(self):
        self.switch = coin.SoSwitch()
        self.shown = style.Show(self.switch)
        sep = coin.SoSeparator()
        self.transform = coin.SoTransform()
        self._move, self._turn = self.transform.translation, self.transform.rotation
        sep.addChild(self.transform)
        sep.addChild(style.color(style.GRAB))
        self.bar = coin.SoCube()
        self.bar.depth = DEPTH
        self._width, self._height = self.bar.width, self.bar.height
        sep.addChild(self.bar)
        self.switch.addChild(sep)
        self._key = None

    def show(self, pose, zone, fade):
        key = (pose.lcentre, pose.lu, zone, fade, pose.dims.cols, pose.dims.rows)
        if key != self._key:
            self._key = key
            d = pose.dims
            half = (d.panel_w / 2 + rg.PANEL_GAP / 2, d.panel_h / 2 + rg.PANEL_GAP / 2)
            x, y, w, h = {"left": (-half[0], 0.0, self.BAR, d.panel_h), "right": (half[0], 0.0, self.BAR, d.panel_h),
                          "above": (0.0, half[1], d.panel_w, self.BAR), "below": (0.0, -half[1], d.panel_w, self.BAR)}[zone]
            self._width.setValue(w)
            self._height.setValue(h)
            centre = mu.add(pose.lcentre, mu.add(mu.mul(pose.lu, x), mu.mul(pose.lv, y)))
            centre = mu.add(centre, mu.mul(pose.ln, MARKER_LIFT))
            self._move.setValue(*(centre if fade >= 1.0 else mu.mul(centre, fade)))
            self._turn.setValue(*mu.quat_from_basis(pose.lu, pose.lv, pose.ln))
        self.shown.set(True)


class RingView:
    def __init__(self):
        self.root = coin.SoSwitch()
        self._show = style.Show(self.root)
        sep = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        sep.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        sep.addChild(light)
        sep.addChild(style.font())
        self._carousel = coin.SoSeparator()      # everything that turns with the controller: one transform places all of it
        frame = coin.SoTransform()
        self._frame_at, self._frame_turn = frame.translation, frame.rotation
        self._frame_key = None
        self._carousel.addChild(frame)
        self._panels_sep = coin.SoSeparator()
        self._carousel.addChild(self._panels_sep)
        self._ghosts = {}                # side -> ghost slot of an empty side
        self._ghost_sep = coin.SoSeparator()
        self._carousel.addChild(self._ghost_sep)
        self._marker = _Marker()
        self._carousel.addChild(self._marker.switch)
        sep.addChild(self._carousel)
        self._card = _Card()                     # in the room: it follows the ray
        sep.addChild(self._card.switch)
        self.root.addChild(sep)
        self._panels = []
        self._built_for = None
        self._data = None

    @staticmethod
    def _signature(layout):
        return id(layout), tuple((p.name, tuple(p.slots), p.hue, p.cols) for p in layout.pages)

    def build(self, layout, faces):
        """(Re)build the panel nodes for a layout; `faces` maps face id to `layout.Face`."""
        self._panels_sep.removeAllChildren()
        self._panels = []
        for page in layout.pages:
            view = _Panel(page, faces)
            self._panels.append(view)
            self._panels_sep.addChild(view.switch)
        self._built_for = self._signature(layout)
        self._data = None

    def needs_build(self, layout):
        return self._built_for != self._signature(layout)

    def _refresh(self, view, index, name, ring, result, active_actions, labels, sliders, titles, readouts):
        """The contents of one panel: titles, sliders, readouts and the state of each face."""
        view.set_title((titles or {}).get(name, name))
        for row, (slider_view, face_id) in view.sliders.items():
            fraction, text, *picked = (sliders or {}).get(face_id, (0.0, "-"))
            hovered = result.hover == (index, row * view.cols)
            slider_view.set(fraction, text, hovered, hovered and ring.slider_drag is not None, bool(picked and picked[0]),
                            result.bar_hover == (index, row * view.cols))
        for row, (readout_view, face_id) in view.readouts.items():
            readout_view.set(*(readouts or {}).get(face_id, ("-", "-", False)))
        for slot, (cell, face) in enumerate(view.cells):
            if cell is None:
                continue
            hovered = result.hover == (index, slot)
            active = face is not None and face.action in active_actions
            if face is not None and labels and face.id in labels:
                cell.set_label(labels[face.id])
            cell.set_state(hovered, active, face is not None, result.lifted_face == (index, slot),
                           result.face_target == (index, slot), face is not None and face.kind == "display")

    def update(self, ring, result, layout, faces, head, active_actions=(), labels=None, sliders=None, titles=None, readouts=None):
        if ring.fade <= 0.02:
            self._show.set(False)
            return
        if self.needs_build(layout):
            self.build(layout, faces)
        self._show.set(True)
        frame = ring.frame
        key = (frame.origin, frame.orientation)
        if key != self._frame_key:
            self._frame_key = key
            self._frame_at.setValue(*frame.origin)
            self._frame_turn.setValue(*frame.orientation)
        fade = ring.fade
        # the head in the frame of the carousel: whether a panel faces it is then a dot product with no panel pose worked out
        d = mu.sub(head, frame.origin)
        head_local = (mu.dot(d, frame.right), mu.dot(d, frame.up), mu.dot(d, frame.back))
        data = (frozenset(active_actions), dict(labels or {}), dict(sliders or {}), dict(titles or {}), dict(readouts or {}))
        same = data == self._data
        self._data = data
        hover, hover_title, lifted_face, face_target = result.hover, result.hover_title, result.lifted_face, result.face_target
        drag = ring.slider_drag is not None
        for index, view in enumerate(self._panels):
            pose = ring.poses.get(index)
            if pose is None:
                view.shown.set(False)
                continue
            view.shown.set(True)
            view.place.set(pose, fade)
            under_ray = result.drop_marker is not None and result.drop_marker[0] == index
            view.back_color.set(view.palette.plate_lit if under_ray else view.palette.plate)
            lc, ln = pose.lcentre, pose.ln
            facing = (head_local[0] - lc[0]) * ln[0] + (head_local[1] - lc[1]) * ln[1] + (head_local[2] - lc[2]) * ln[2] > 0.0
            view.set_facing(facing)
            if facing:                                     # seen from behind: only the plate shows
                state = (hover[1] if hover is not None and hover[0] == index else None, hover_title == index,
                         lifted_face[1] if lifted_face is not None and lifted_face[0] == index else None,
                         face_target[1] if face_target is not None and face_target[0] == index else None,
                         result.bar_hover[1] if result.bar_hover is not None and result.bar_hover[0] == index else None,
                         drag, result.menu_hover == index, 2 if result.hide_page == index else 1 if lifted_face is not None else 0)
                if not same or state != view.key:
                    view.key = state
                    view.set_menu_hover(state[-2])
                    view.set_hide_slot(state[-1])
                    view.title_color.set(style.HOVER if hover_title == index else view.palette.title)
                    self._refresh(view, index, layout.pages[index].name, ring, result, active_actions, labels, sliders, titles, readouts)
            else:
                view.key = None
            view.flush()
        for side, ghost_view in self._ghosts.items():
            if side not in ring.ghosts:
                ghost_view.shown.set(False)
        for side, ghost in ring.ghosts.items():
            if side not in self._ghosts:
                self._ghosts[side] = _Ghost()
                self._ghost_sep.addChild(self._ghosts[side].switch)
            view = self._ghosts[side]
            view.shown.set(True)
            view.place.set(ghost, fade)
            view.set_label(_Ghost.PANEL_LABEL)
            over = result.drop_marker is not None and result.drop_marker[0] is None and result.drop_marker[2] == side
            view.color.set(style.HOVER if over else style.DROP)
            view.plates.flush()
        marker = result.drop_marker
        if marker is not None and marker[0] is not None and marker[0] in ring.poses:
            self._marker.show(ring.poses[marker[0]], marker[1], fade)
        else:
            self._marker.shown.set(False)
        card = None
        if result.lifted is not None:
            card = layout.pages[result.lifted].name
        elif result.lifted_face is not None:
            face = faces.get(layout.face_at(*result.lifted_face))
            card = (labels or {}).get(face.id, face.label) if face is not None else None
        if card is not None and result.lift_point is not None:
            up = (0.0, 1.0, 0.0)
            point = mu.add(result.lift_point, mu.mul(up, 0.04))
            self._card.show(card, point, mu.quat_multiply(mu.look_at(point, head), mu.quat_from_axis_angle(up, 3.141592653589793)))
        else:
            self._card.shown.set(False)
