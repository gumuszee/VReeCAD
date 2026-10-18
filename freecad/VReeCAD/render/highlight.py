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
"""Coin3D drawing of what the hand touches and what is selected (docs/ux-design.md, Move tool). The scene graph is in document
millimetres, so a host puts `Highlights.root` where the document scene is.

A highlight draws `cad.picking.Display` geometry: a face as a translucent fill, curves as lines that are bright where they lie in
front of the model and dim where the model hides them (like the outline of the Create preview), a vertex as a cross.

The highlight lies on the surface it marks, so it is drawn a little in front of it (a polygon offset and a depth range that
squeezes its depth towards the viewer); the hover is drawn in front of the selection, because both may mark the same element and
two coplanar highlights would fight each other and flicker."""

from pivy import coin

from freecad.VReeCAD.ui import style

HOVER = ((0.45, 0.72, 1.0), (0.2, 0.34, 0.6))         # (bright, dim)
SELECTED = ((1.0, 0.65, 0.10), (0.5, 0.33, 0.05))
LINE_WIDTH = 4.0
FILL_TRANSPARENCY = 0.5
FILL_OFFSET = 10.0
LINE_OFFSET = 40.0
DEPTH_RANGE = (0.99998, 0.99995)      # far end of the depth range of the selection and of the hover: smaller is nearer to the viewer


class Highlight:
    def __init__(self, colours, level=0):
        """`level` 0 is the selection, 1 the hover: a higher level lies in front of a lower one."""
        bright, dim = colours
        self.root = coin.SoSwitch()
        self.root.whichChild = coin.SO_SWITCH_NONE
        sep = coin.SoSeparator()

        fill = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*bright)
        material.transparency.setValue(FILL_TRANSPARENCY)
        fill.addChild(material)
        transparency = coin.SoTransparencyType()
        transparency.value = coin.SoTransparencyType.BLEND
        fill.addChild(transparency)
        depth = coin.SoDepthBuffer()
        depth.function.setValue(coin.SoDepthBuffer.LEQUAL)
        depth.range.setValue(0.0, DEPTH_RANGE[level])
        depth.getField("write").setValue(False)
        fill.addChild(depth)
        offset = coin.SoPolygonOffset()              # towards the viewer: the fill lies on the face it marks
        offset.factor.setValue(-1.0)
        offset.units.setValue(-FILL_OFFSET * (1 + level))
        offset.styles.setValue(coin.SoPolygonOffset.FILLED)
        fill.addChild(offset)
        self._fill_points = coin.SoCoordinate3()
        fill.addChild(self._fill_points)
        self._fill = coin.SoIndexedFaceSet()
        fill.addChild(self._fill)
        sep.addChild(fill)

        lines = coin.SoSeparator()
        width = coin.SoDrawStyle()
        width.lineWidth = LINE_WIDTH
        lines.addChild(width)
        self._line_points = coin.SoCoordinate3()
        lines.addChild(self._line_points)
        self._lines = coin.SoIndexedLineSet()
        for hidden_pass in (True, False):
            one = coin.SoSeparator()
            test = coin.SoDepthBuffer()
            test.test.setValue(not hidden_pass)
            test.function.setValue(coin.SoDepthBuffer.LEQUAL)
            test.range.setValue(0.0, DEPTH_RANGE[level])
            test.getField("write").setValue(False)
            one.addChild(test)
            if not hidden_pass:                      # the edges of the model lie where the highlight does: pull the highlight forward
                forward = coin.SoPolygonOffset()
                forward.factor.setValue(-1.0)
                forward.units.setValue(-LINE_OFFSET * (1 + level))
                forward.styles.setValue(coin.SoPolygonOffset.LINES)
                one.addChild(forward)
            one.addChild(style.color(dim if hidden_pass else bright))
            one.addChild(self._lines)
            lines.addChild(one)
        sep.addChild(lines)
        self.root.addChild(sep)

    def show(self, displays, marker_half=2.0):
        """Draw a list of `cad.picking.Display`; `marker_half` is the arm of the cross at a vertex in millimetres."""
        fill_points, fill_indices = [], []
        line_points, line_indices = [], []
        for display in displays:
            points, triangles = display.triangles
            base = len(fill_points)
            fill_points += points
            for a, b, c in triangles:
                fill_indices += [base + a, base + b, base + c, -1]
            for curve in display.polylines:
                line_indices += list(range(len(line_points), len(line_points) + len(curve))) + [-1]
                line_points += curve
            for x, y, z in display.markers:
                h = marker_half
                for a, b in (((x - h, y, z), (x + h, y, z)), ((x, y - h, z), (x, y + h, z)), ((x, y, z - h), (x, y, z + h))):
                    line_indices += [len(line_points), len(line_points) + 1, -1]
                    line_points += [a, b]
        self._fill_points.point.setValues(0, len(fill_points), fill_points)
        self._fill_points.point.setNum(len(fill_points))
        self._fill.coordIndex.setValues(0, len(fill_indices), fill_indices)
        self._fill.coordIndex.setNum(len(fill_indices))
        self._line_points.point.setValues(0, len(line_points), line_points)
        self._line_points.point.setNum(len(line_points))
        self._lines.coordIndex.setValues(0, len(line_indices), line_indices)
        self._lines.coordIndex.setNum(len(line_indices))
        self.root.whichChild = coin.SO_SWITCH_ALL if (fill_points or line_points) else coin.SO_SWITCH_NONE

    def hide(self):
        self.root.whichChild = coin.SO_SWITCH_NONE


class Highlights:
    """The hover highlight (what the hand touches) and the selection highlight."""

    def __init__(self):
        self.root = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.root.addChild(light)
        self.selected = Highlight(SELECTED, 0)
        self.hover = Highlight(HOVER, 1)
        self.root.addChild(self.selected.root)
        self.root.addChild(self.hover.root)

    def hide(self):
        self.selected.hide()
        self.hover.hide()
