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
"""Coin3D drawing of the preview of a shape that is being made (docs/design.md, Interaction design): a translucent ghost of the
shape, the outline of the box a drag spans, and a cross at the snapped point where a press would start. The scene graph is in
document millimetres, so a host puts `Ghost.root` where the document scene is (under the navigation and document transforms)."""

from pivy import coin

from freecad.BlocksCAD.ui import style

BODY = (0.35, 0.65, 1.0)
BODY_TRANSPARENCY = 0.55
OUTLINE = (0.95, 0.65, 0.10)
MARKER = (0.95, 0.65, 0.10)

_EDGES = ((0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7))


def _no_depth_test():
    depth = coin.SoDepthBuffer()
    depth.test.setValue(False)
    depth.getField("write").setValue(False)
    return depth


class Ghost:
    def __init__(self):
        self.root = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.root.addChild(pick)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        self.root.addChild(light)

        self._body = coin.SoSwitch()
        self._body.whichChild = coin.SO_SWITCH_NONE
        body = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*BODY)
        material.transparency.setValue(BODY_TRANSPARENCY)
        body.addChild(material)
        transparency = coin.SoTransparencyType()
        transparency.value = coin.SoTransparencyType.BLEND
        body.addChild(transparency)
        self._body_points = coin.SoCoordinate3()
        body.addChild(self._body_points)
        self._body_faces = coin.SoIndexedFaceSet()
        body.addChild(self._body_faces)
        self._body.addChild(body)
        self.root.addChild(self._body)

        self._box = coin.SoSwitch()
        self._box.whichChild = coin.SO_SWITCH_NONE
        box = coin.SoSeparator()
        box.addChild(style.color(OUTLINE))
        self._box_points = coin.SoCoordinate3()
        box.addChild(self._box_points)
        lines = coin.SoIndexedLineSet()
        indices = []
        for a, b in _EDGES:
            indices += [a, b, -1]
        lines.coordIndex.setValues(0, len(indices), indices)
        box.addChild(lines)
        self._box.addChild(box)
        self.root.addChild(self._box)

        self._marker = coin.SoSwitch()
        self._marker.whichChild = coin.SO_SWITCH_NONE
        marker = coin.SoSeparator()
        marker.addChild(_no_depth_test())        # always visible: it tells where a press would start
        marker.addChild(style.color(MARKER))
        self._marker_move = coin.SoTranslation()
        marker.addChild(self._marker_move)
        self._marker_points = coin.SoCoordinate3()
        marker.addChild(self._marker_points)
        cross = coin.SoIndexedLineSet()
        cross.coordIndex.setValues(0, 9, [0, 1, -1, 2, 3, -1, 4, 5, -1])
        marker.addChild(cross)
        self._marker.addChild(marker)
        self.root.addChild(self._marker)

    def show_marker(self, point, half):
        """A cross with arms of `half` millimetres at `point`."""
        h = half
        self._marker_points.point.setValues(0, 6, [(-h, 0, 0), (h, 0, 0), (0, -h, 0), (0, h, 0), (0, 0, -h), (0, 0, h)])
        self._marker_move.translation.setValue(*point)
        self._marker.whichChild = coin.SO_SWITCH_ALL

    def hide_marker(self):
        self._marker.whichChild = coin.SO_SWITCH_NONE

    def show_shape(self, points, triangles):
        """The translucent body: `points` are (x, y, z) tuples, `triangles` index them."""
        indices = []
        for a, b, c in triangles:
            indices += [a, b, c, -1]
        self._body_points.point.setValues(0, len(points), points)
        self._body_points.point.setNum(len(points))
        self._body_faces.coordIndex.setValues(0, len(indices), indices)
        self._body_faces.coordIndex.setNum(len(indices))
        self._body.whichChild = coin.SO_SWITCH_ALL

    def show_box(self, lo, size):
        """The outline of the box with lowest corner `lo` and edge lengths `size`."""
        corners = [(lo[0] + i * size[0], lo[1] + j * size[1], lo[2] + k * size[2]) for k in (0, 1) for j in (0, 1) for i in (0, 1)]
        self._box_points.point.setValues(0, 8, corners)
        self._box.whichChild = coin.SO_SWITCH_ALL

    def hide_shape(self):
        self._body.whichChild = coin.SO_SWITCH_NONE
        self._box.whichChild = coin.SO_SWITCH_NONE

    def hide(self):
        self.hide_shape()
        self.hide_marker()
