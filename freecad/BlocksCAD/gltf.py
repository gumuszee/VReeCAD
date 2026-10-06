# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""Minimal GLB (binary glTF 2.0) reader: node tree, triangle meshes, base-colour materials and embedded images.

Scope is what runtime-provided controller models use (docs/controller-models.md): triangle primitives with
POSITION / NORMAL / TEXCOORD_0, unsigned integer indices, embedded PNG/JPEG images, node TRS transforms.
Not supported (raises or ignored): sparse accessors, skins, morph targets, animations, cameras, glTF extensions.
No FreeCAD, Coin or Qt imports; only numpy.
"""

import json
import struct
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

_COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NORMALIZE = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}

_GLB_MAGIC = 0x46546C67
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942


class GltfError(ValueError):
    pass


@dataclass
class Primitive:
    positions: np.ndarray                  # (N, 3) float32
    indices: np.ndarray                    # (M,) uint32, M % 3 == 0
    normals: Optional[np.ndarray] = None   # (N, 3) float32
    uvs: Optional[np.ndarray] = None       # (N, 2) float32
    material: Optional[int] = None


@dataclass
class Material:
    name: str = ""
    base_color: tuple = (1.0, 1.0, 1.0, 1.0)
    image: Optional[int] = None            # index into Asset.images
    metallic: float = 0.0
    roughness: float = 0.5


@dataclass
class Image:
    data: bytes
    mime: str = ""


@dataclass
class Node:
    name: str = ""
    children: List[int] = field(default_factory=list)
    mesh: Optional[int] = None
    translation: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0, 1.0)  # x, y, z, w
    scale: tuple = (1.0, 1.0, 1.0)


@dataclass
class Asset:
    nodes: List[Node]
    meshes: List[List[Primitive]]
    materials: List[Material]
    images: List[Image]
    roots: List[int]
    generator: str = ""

    def find_node(self, name):
        for index, node in enumerate(self.nodes):
            if node.name == name:
                return index
        return None


def _decompose(matrix):
    """TRS of a column-major 4x4 glTF matrix (no shear assumed)."""
    m = np.array(matrix, dtype=np.float64).reshape(4, 4).T  # row-major, column vectors
    translation = tuple(float(v) for v in m[:3, 3])
    sx, sy, sz = (float(np.linalg.norm(m[:3, i])) for i in range(3))
    rot = m[:3, :3] / np.array([sx or 1.0, sy or 1.0, sz or 1.0])
    trace = rot[0, 0] + rot[1, 1] + rot[2, 2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        q = ((rot[2, 1] - rot[1, 2]) * s, (rot[0, 2] - rot[2, 0]) * s, (rot[1, 0] - rot[0, 1]) * s, 0.25 / s)
    elif rot[0, 0] > rot[1, 1] and rot[0, 0] > rot[2, 2]:
        s = 2.0 * np.sqrt(1.0 + rot[0, 0] - rot[1, 1] - rot[2, 2])
        q = (0.25 * s, (rot[0, 1] + rot[1, 0]) / s, (rot[0, 2] + rot[2, 0]) / s, (rot[2, 1] - rot[1, 2]) / s)
    elif rot[1, 1] > rot[2, 2]:
        s = 2.0 * np.sqrt(1.0 + rot[1, 1] - rot[0, 0] - rot[2, 2])
        q = ((rot[0, 1] + rot[1, 0]) / s, 0.25 * s, (rot[1, 2] + rot[2, 1]) / s, (rot[0, 2] - rot[2, 0]) / s)
    else:
        s = 2.0 * np.sqrt(1.0 + rot[2, 2] - rot[0, 0] - rot[1, 1])
        q = ((rot[0, 2] + rot[2, 0]) / s, (rot[1, 2] + rot[2, 1]) / s, 0.25 * s, (rot[1, 0] - rot[0, 1]) / s)
    return translation, tuple(float(v) for v in q), (sx, sy, sz)


def _split_glb(data):
    if len(data) < 20:
        raise GltfError("not a GLB: too short")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != _GLB_MAGIC:
        raise GltfError("not a GLB: bad magic")
    if version != 2:
        raise GltfError(f"unsupported GLB version {version}")
    json_part, bin_part = None, b""
    offset = 12
    end = min(length, len(data))
    while offset + 8 <= end:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        body = data[offset + 8: offset + 8 + chunk_length]
        if chunk_type == _CHUNK_JSON:
            json_part = json.loads(body.decode("utf-8"))
        elif chunk_type == _CHUNK_BIN and not bin_part:
            bin_part = bytes(body)
        offset += 8 + chunk_length
    if json_part is None:
        raise GltfError("GLB has no JSON chunk")
    return json_part, bin_part


class _Reader:
    def __init__(self, doc, blob):
        self.doc = doc
        self.blob = blob

    def buffer_view(self, index):
        view = self.doc["bufferViews"][index]
        if view.get("buffer", 0) != 0:
            raise GltfError("external or multiple buffers are not supported")
        start = view.get("byteOffset", 0)
        return self.blob[start: start + view["byteLength"]], view.get("byteStride")

    def accessor(self, index, as_float=False):
        acc = self.doc["accessors"][index]
        if "sparse" in acc:
            raise GltfError("sparse accessors are not supported")
        dtype = np.dtype(_COMPONENT[acc["componentType"]])
        width = _WIDTH[acc["type"]]
        count = acc["count"]
        if "bufferView" not in acc:
            return np.zeros((count, width), dtype=np.float32 if as_float else dtype)
        raw, stride = self.buffer_view(acc["bufferView"])
        offset = acc.get("byteOffset", 0)
        element = dtype.itemsize * width
        stride = stride or element
        if stride == element:
            arr = np.frombuffer(raw, dtype=dtype, count=count * width, offset=offset).reshape(count, width)
        else:
            rows = [np.frombuffer(raw, dtype=dtype, count=width, offset=offset + i * stride) for i in range(count)]
            arr = np.array(rows).reshape(count, width)
        if as_float:
            arr = arr.astype(np.float32)
            if acc.get("normalized") and acc["componentType"] in _NORMALIZE:
                arr = np.maximum(arr / _NORMALIZE[acc["componentType"]], -1.0)
        return arr


def parse_glb(data):
    """Parse GLB bytes into an `Asset`."""
    doc, blob = _split_glb(data)
    reader = _Reader(doc, blob)

    images = []
    for img in doc.get("images", []):
        if "bufferView" not in img:
            raise GltfError("only embedded (bufferView) images are supported")
        raw, _ = reader.buffer_view(img["bufferView"])
        images.append(Image(bytes(raw), img.get("mimeType", "")))

    textures = doc.get("textures", [])
    materials = []
    for mat in doc.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        image = None
        tex = pbr.get("baseColorTexture")
        if tex is not None and tex["index"] < len(textures):
            image = textures[tex["index"]].get("source")
        materials.append(Material(
            name=mat.get("name", ""),
            base_color=tuple(pbr.get("baseColorFactor", (1.0, 1.0, 1.0, 1.0))),
            image=image,
            metallic=float(pbr.get("metallicFactor", 1.0)),
            roughness=float(pbr.get("roughnessFactor", 1.0)),
        ))

    meshes = []
    for mesh in doc.get("meshes", []):
        prims = []
        for prim in mesh["primitives"]:
            mode = prim.get("mode", 4)
            if mode != 4:
                continue  # only triangle lists
            attrs = prim["attributes"]
            positions = reader.accessor(attrs["POSITION"], as_float=True)
            normals = reader.accessor(attrs["NORMAL"], as_float=True) if "NORMAL" in attrs else None
            uvs = reader.accessor(attrs["TEXCOORD_0"], as_float=True) if "TEXCOORD_0" in attrs else None
            if "indices" in prim:
                indices = reader.accessor(prim["indices"]).reshape(-1).astype(np.uint32)
            else:
                indices = np.arange(len(positions), dtype=np.uint32)
            indices = indices[: (len(indices) // 3) * 3]
            prims.append(Primitive(positions, indices, normals, uvs, prim.get("material")))
        meshes.append(prims)

    nodes = []
    for node in doc.get("nodes", []):
        if "matrix" in node:
            translation, rotation, scale = _decompose(node["matrix"])
        else:
            translation = tuple(node.get("translation", (0.0, 0.0, 0.0)))
            rotation = tuple(node.get("rotation", (0.0, 0.0, 0.0, 1.0)))
            scale = tuple(node.get("scale", (1.0, 1.0, 1.0)))
        nodes.append(Node(node.get("name", ""), list(node.get("children", [])), node.get("mesh"),
                          translation, rotation, scale))

    scenes = doc.get("scenes", [])
    if scenes:
        roots = list(scenes[doc.get("scene", 0)].get("nodes", []))
    else:
        children = {c for n in nodes for c in n.children}
        roots = [i for i in range(len(nodes)) if i not in children]

    return Asset(nodes, meshes, materials, images, roots, doc.get("asset", {}).get("generator", ""))
