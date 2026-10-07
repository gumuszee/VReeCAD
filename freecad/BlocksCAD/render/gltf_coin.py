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
"""Builds a Coin3D scene from a parsed glTF `Asset` (freecad.BlocksCAD.gltf).

Every glTF node becomes `SoSwitch { SoSeparator { SoTransform, <mesh>, <children> } }`, so a node (and its subtree) can be
hidden and posed by name, which is what animatable render-model nodes need. Texture coordinates are used as stored:
glTF has its origin at the top-left of the image and the decoded rows are passed top row first, so no flip is applied.
"""

import numpy as np
from pivy import coin

from freecad.BlocksCAD import gltf


class ModelPart:
    """Handles of one glTF node inside the built scene."""

    def __init__(self, name, switch, transform):
        self.name = name
        self.switch = switch
        self.transform = transform
        self._base = (transform.translation.getValue().getValue(), transform.rotation.getValue().getValue(),
                      transform.scaleFactor.getValue().getValue())
        # the fields are looked up once (a pivy field lookup costs about 20 microseconds) and written only when the value changes: a
        # write drops the render caches above the node, and most parts of a controller stand still from one frame to the next
        self._visible_field = switch.whichChild
        self._move, self._turn = transform.translation, transform.rotation
        self._visible = True
        self._moved = self._base[0]
        self._turned = self._base[1]

    def set_visible(self, visible):
        if visible != self._visible:
            self._visible = visible
            self._visible_field.setValue(coin.SO_SWITCH_ALL if visible else coin.SO_SWITCH_NONE)

    def _move_to(self, position):
        position = tuple(position)
        if position != self._moved:
            self._moved = position
            self._move.setValue(*position)

    def _turn_to(self, orientation):
        orientation = tuple(orientation)
        if orientation != self._turned:
            self._turned = orientation
            self._turn.setValue(*orientation)

    def set_pose(self, position, orientation):
        """Pose relative to the parent node (what XrRenderModelNodeStateEXT carries)."""
        self._move_to(position)
        self._turn_to(orientation)

    def offset(self, dx, dy, dz):
        """Translate from the node's base position (used by generated shapes)."""
        base = self._base[0]
        self._move_to((base[0] + dx, base[1] + dy, base[2] + dz))

    def reset_pose(self):
        self._move_to(self._base[0])
        self._turn_to(self._base[1])


class Model:
    def __init__(self, root, parts):
        self.root = root          # SoSeparator
        self.parts = parts        # name -> ModelPart (named nodes)

    def part(self, name):
        return self.parts.get(name)


def _texture_node(image, cache):
    """SoTexture2 of an embedded PNG/JPEG, decoded once per distinct content and shared by every mesh that uses it."""
    key = hash(image.data)
    if key not in cache:
        from PySide6 import QtGui
        qimg = QtGui.QImage.fromData(image.data)
        if qimg.isNull():
            cache[key] = None
        else:
            qimg = qimg.convertToFormat(QtGui.QImage.Format_RGBA8888)
            w, h = qimg.width(), qimg.height()
            tex = coin.SoTexture2()
            tex.image.setValue(coin.SbVec2s(w, h), 4, bytes(qimg.constBits())[: w * h * 4])
            tex.model = coin.SoTexture2.MODULATE
            tex.ref()  # the cache keeps the node alive while parts share it
            cache[key] = tex
    return cache[key]


def _mesh_nodes(prim, material, image_cache, asset):
    sep = coin.SoSeparator()
    mat = coin.SoMaterial()
    color = material.base_color if material else (0.7, 0.7, 0.7, 1.0)
    mat.diffuseColor.setValue(color[0], color[1], color[2])
    mat.specularColor.setValue(0.25, 0.25, 0.25)
    mat.shininess.setValue(max(0.05, 1.0 - material.roughness) if material else 0.3)
    sep.addChild(mat)

    tex = None
    if material is not None and material.image is not None and prim.uvs is not None:
        tex = _texture_node(asset.images[material.image], image_cache)
    if tex is not None:
        sep.addChild(tex)

    hints = coin.SoShapeHints()
    hints.vertexOrdering = coin.SoShapeHints.COUNTERCLOCKWISE
    hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
    sep.addChild(hints)

    coords = coin.SoCoordinate3()
    coords.point.setValues(0, prim.positions.shape[0], np.ascontiguousarray(prim.positions, dtype=np.float32))
    sep.addChild(coords)
    if prim.normals is not None:
        normals = coin.SoNormal()
        normals.vector.setValues(0, prim.normals.shape[0], np.ascontiguousarray(prim.normals, dtype=np.float32))
        sep.addChild(normals)
        binding = coin.SoNormalBinding()
        binding.value = coin.SoNormalBinding.PER_VERTEX_INDEXED
        sep.addChild(binding)
    if tex is not None:
        uv = coin.SoTextureCoordinate2()
        uv.point.setValues(0, prim.uvs.shape[0], np.ascontiguousarray(prim.uvs, dtype=np.float32))
        sep.addChild(uv)
        tbind = coin.SoTextureCoordinateBinding()
        tbind.value = coin.SoTextureCoordinateBinding.PER_VERTEX_INDEXED
        sep.addChild(tbind)

    tri = prim.indices.reshape(-1, 3).astype(np.int32)
    face_indices = np.concatenate([tri, np.full((tri.shape[0], 1), -1, dtype=np.int32)], axis=1).reshape(-1)
    faces = coin.SoIndexedFaceSet()
    faces.coordIndex.setValues(0, face_indices.shape[0], face_indices)
    sep.addChild(faces)
    return sep


def build_model(asset, image_cache=None):
    """Build the Coin scene of a parsed `gltf.Asset`; returns a `Model`."""
    if image_cache is None:
        image_cache = {}
    root = coin.SoSeparator()
    root.ref()
    parts = {}

    def build(index):
        node = asset.nodes[index]
        switch = coin.SoSwitch()
        switch.whichChild = coin.SO_SWITCH_ALL
        sep = coin.SoSeparator()
        transform = coin.SoTransform()
        transform.translation.setValue(*node.translation)
        transform.rotation.setValue(*node.rotation)
        transform.scaleFactor.setValue(*node.scale)
        sep.addChild(transform)
        if node.mesh is not None:
            for prim in asset.meshes[node.mesh]:
                material = asset.materials[prim.material] if prim.material is not None else None
                sep.addChild(_mesh_nodes(prim, material, image_cache, asset))
        for child in node.children:
            sep.addChild(build(child))
        switch.addChild(sep)
        if node.name:
            parts[node.name] = ModelPart(node.name, switch, transform)
        return switch

    for index in asset.roots:
        root.addChild(build(index))
    return Model(root, parts)


def load_glb(data, image_cache=None):
    """Parse GLB bytes and build the scene."""
    return build_model(gltf.parse_glb(data), image_cache)
