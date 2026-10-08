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
"""Coin3D drawing of the preview of a shape that is being made (docs/design.md, Interaction design): a lit translucent body, the
outline curves of the shape, the outline of the box a drag spans, and a cross at the snapped point where a press would start.
The scene graph is in document millimetres, so a host puts `Ghost.root` where the document scene is (under the navigation and
document transforms).

Depth is easy to misjudge with a flat translucent shape, so the body is lit and only its front faces are drawn (one layer, no
internal geometry; it writes no depth, so the layers never fight), and the outline curves are drawn twice: bright where they
lie in front of the model and dim where they are hidden by it."""

from pivy import coin

from freecad.BlocksCAD.ui import style

BODY = (0.35, 0.65, 1.0)
BODY_TRANSPARENCY = 0.4
EDGE = (0.92, 0.96, 1.0)
EDGE_HIDDEN = (0.25, 0.4, 0.65)
EDGE_WIDTH = 2.0
OUTLINE = (0.95, 0.65, 0.10)
MARKER = (0.95, 0.65, 0.10)
ACQUIRED = (0.35, 0.85, 0.95)        # the cross on a point that inference has acquired
GUIDE_COLOURS = {0: (0.95, 0.35, 0.35), 1: (0.40, 0.85, 0.40), 2: (0.45, 0.60, 1.0), 3: (0.85, 0.85, 0.85), -1: MARKER}   # X, Y and Z of the document, a direction of a face, a point
GUIDE_WIDTH = 2.0
GUIDE_DIM = 0.45          # the part of a guide that lies behind the model is this much darker

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
        shaded = coin.SoLightModel()
        shaded.model = coin.SoLightModel.PHONG
        body.addChild(shaded)
        material = coin.SoMaterial()
        material.diffuseColor.setValue(*BODY)
        material.ambientColor.setValue(*(0.6 * c for c in BODY))
        material.specularColor.setValue(0.35, 0.35, 0.35)
        material.shininess.setValue(0.3)
        material.transparency.setValue(BODY_TRANSPARENCY)
        body.addChild(material)
        transparency = coin.SoTransparencyType()
        transparency.value = coin.SoTransparencyType.BLEND
        body.addChild(transparency)
        depth = coin.SoDepthBuffer()              # test against the model, write nothing: translucent layers never fight
        depth.test.setValue(True)
        depth.getField("write").setValue(False)
        body.addChild(depth)
        hints = coin.SoShapeHints()               # a closed solid with outward counter-clockwise faces: only the front is drawn
        hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
        hints.shapeType = coin.SoShapeHints.SOLID
        hints.faceType = coin.SoShapeHints.CONVEX
        body.addChild(hints)
        self._body_points = coin.SoCoordinate3()
        body.addChild(self._body_points)
        self._body_normals = coin.SoNormal()
        body.addChild(self._body_normals)
        binding = coin.SoNormalBinding()
        binding.value = coin.SoNormalBinding.PER_VERTEX_INDEXED
        body.addChild(binding)
        self._body_faces = coin.SoIndexedFaceSet()
        body.addChild(self._body_faces)
        self._body.addChild(body)
        self.root.addChild(self._body)

        self._edges = coin.SoSwitch()
        self._edges.whichChild = coin.SO_SWITCH_NONE
        edges = coin.SoSeparator()
        style_node = coin.SoDrawStyle()
        style_node.lineWidth = EDGE_WIDTH
        edges.addChild(style_node)
        self._edge_points = coin.SoCoordinate3()
        edges.addChild(self._edge_points)
        self._edge_lines = coin.SoIndexedLineSet()
        for hidden_pass in (True, False):          # the dim pass has no depth test, the bright one over it only where nothing is in front
            sep = coin.SoSeparator()
            depth_pass = coin.SoDepthBuffer()
            depth_pass.test.setValue(not hidden_pass)
            depth_pass.getField("write").setValue(False)
            sep.addChild(depth_pass)
            sep.addChild(style.color(EDGE_HIDDEN if hidden_pass else EDGE))
            sep.addChild(self._edge_lines)
            edges.addChild(sep)
        self._edges.addChild(edges)
        self.root.addChild(self._edges)

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

        self._acquired = coin.SoSwitch()             # the points that inference has acquired: a cross on each, over the model
        self._acquired.whichChild = coin.SO_SWITCH_NONE
        acquired = coin.SoSeparator()
        acquired.addChild(_no_depth_test())
        acquired.addChild(style.color(ACQUIRED))
        self._acquired_points = coin.SoCoordinate3()
        acquired.addChild(self._acquired_points)
        self._acquired_lines = coin.SoIndexedLineSet()
        acquired.addChild(self._acquired_lines)
        self._acquired.addChild(acquired)
        self.root.addChild(self._acquired)

        self._guides = coin.SoSwitch()               # one line set per kind of guide, each drawn dim behind the model and bright in front
        self._guides.whichChild = coin.SO_SWITCH_NONE
        self._guide_sets = {}
        guides = coin.SoSeparator()
        guide_style = coin.SoDrawStyle()
        guide_style.lineWidth = GUIDE_WIDTH
        guides.addChild(guide_style)
        for key, colour in GUIDE_COLOURS.items():
            points, lines = coin.SoCoordinate3(), coin.SoIndexedLineSet()
            guides.addChild(points)
            for hidden_pass in (True, False):
                sep = coin.SoSeparator()
                depth_pass = coin.SoDepthBuffer()
                depth_pass.test.setValue(not hidden_pass)
                depth_pass.getField("write").setValue(False)
                sep.addChild(depth_pass)
                sep.addChild(style.color(tuple(c * GUIDE_DIM for c in colour) if hidden_pass else colour))
                sep.addChild(lines)
                guides.addChild(sep)
            self._guide_sets[key] = (points, lines)
        self._guides.addChild(guides)
        self.root.addChild(self._guides)

    def show_marker(self, point, half):
        """A cross with arms of `half` millimetres at `point`."""
        h = half
        self._marker_points.point.setValues(0, 6, [(-h, 0, 0), (h, 0, 0), (0, -h, 0), (0, h, 0), (0, 0, -h), (0, 0, h)])
        self._marker_move.translation.setValue(*point)
        self._marker.whichChild = coin.SO_SWITCH_ALL

    def hide_marker(self):
        self._marker.whichChild = coin.SO_SWITCH_NONE

    def show_acquired(self, points, half):
        """A cross with arms of `half` millimetres on each acquired point (inference); nothing for an empty list."""
        if not points:
            self.hide_acquired()
            return
        coords, indices = [], []
        for a in points:
            base = len(coords)
            coords += [(a[0] - half, a[1], a[2]), (a[0] + half, a[1], a[2]), (a[0], a[1] - half, a[2]), (a[0], a[1] + half, a[2]),
                       (a[0], a[1], a[2] - half), (a[0], a[1], a[2] + half)]
            indices += [base, base + 1, -1, base + 2, base + 3, -1, base + 4, base + 5, -1]
        self._acquired_points.point.setValues(0, len(coords), coords)
        self._acquired_points.point.setNum(len(coords))
        self._acquired_lines.coordIndex.setValues(0, len(indices), indices)
        self._acquired_lines.coordIndex.setNum(len(indices))
        self._acquired.whichChild = coin.SO_SWITCH_ALL

    def hide_acquired(self):
        self._acquired.whichChild = coin.SO_SWITCH_NONE

    def show_guides(self, guides, half):
        """The alignment guides (`core.guides.Guide`): a line from the anchor to the point of every axis guide and a cross with arms of
        `half` millimetres on every anchor, a point guide is the cross alone. Nothing is drawn for an empty list."""
        if not guides:
            self.hide_guides()
            return
        for key, (points, lines) in self._guide_sets.items():
            coords, indices = [], []
            for guide in (g for g in guides if g.axis == key):
                a, b = guide.anchor, guide.point
                base = len(coords)
                if guide.kind == "axis":
                    coords += [a, b]
                    indices += [base, base + 1, -1]
                    base = len(coords)
                coords += [(a[0] - half, a[1], a[2]), (a[0] + half, a[1], a[2]), (a[0], a[1] - half, a[2]), (a[0], a[1] + half, a[2]),
                           (a[0], a[1], a[2] - half), (a[0], a[1], a[2] + half)]
                indices += [base, base + 1, -1, base + 2, base + 3, -1, base + 4, base + 5, -1]
            points.point.setValues(0, len(coords), coords)
            points.point.setNum(len(coords))
            lines.coordIndex.setValues(0, len(indices), indices)
            lines.coordIndex.setNum(len(indices))
        self._guides.whichChild = coin.SO_SWITCH_ALL

    def hide_guides(self):
        self._guides.whichChild = coin.SO_SWITCH_NONE

    def show_shape(self, mesh):
        """The body and the outline curves of a `cad.meshes.Mesh`."""
        indices = []
        for a, b, c in mesh.triangles:
            indices += [a, b, c, -1]
        self._body_points.point.setValues(0, len(mesh.points), mesh.points)
        self._body_points.point.setNum(len(mesh.points))
        self._body_normals.vector.setValues(0, len(mesh.normals), mesh.normals)
        self._body_normals.vector.setNum(len(mesh.normals))
        self._body_faces.coordIndex.setValues(0, len(indices), indices)
        self._body_faces.coordIndex.setNum(len(indices))
        self._body_faces.normalIndex.setValues(0, len(indices), indices)
        self._body_faces.normalIndex.setNum(len(indices))
        points, lines = [], []
        for curve in mesh.outline:
            lines += list(range(len(points), len(points) + len(curve))) + [-1]
            points += curve
        self._edge_points.point.setValues(0, len(points), points)
        self._edge_points.point.setNum(len(points))
        self._edge_lines.coordIndex.setValues(0, len(lines), lines)
        self._edge_lines.coordIndex.setNum(len(lines))
        self._body.whichChild = coin.SO_SWITCH_ALL
        self._edges.whichChild = coin.SO_SWITCH_ALL

    def show_box(self, lo, size):
        """The outline of the box with lowest corner `lo` and edge lengths `size`."""
        corners = [(lo[0] + i * size[0], lo[1] + j * size[1], lo[2] + k * size[2]) for k in (0, 1) for j in (0, 1) for i in (0, 1)]
        self._box_points.point.setValues(0, 8, corners)
        self._box.whichChild = coin.SO_SWITCH_ALL

    def hide_shape(self):
        self._body.whichChild = coin.SO_SWITCH_NONE
        self._edges.whichChild = coin.SO_SWITCH_NONE
        self._box.whichChild = coin.SO_SWITCH_NONE

    def hide(self):
        self.hide_shape()
        self.hide_marker()
        self.hide_guides()
        self.hide_acquired()
