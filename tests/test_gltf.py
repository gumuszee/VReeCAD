import json
import struct
import unittest

import numpy as np

import support  # noqa: F401
from freecad.VReeCAD import gltf


def make_glb(doc, blob):
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    blob += b"\0" * (-len(blob) % 4)
    total = 12 + 8 + len(body) + 8 + len(blob)
    return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(body), 0x4E4F534A) + body
            + struct.pack("<II", len(blob), 0x004E4942) + blob)


def triangle_glb():
    positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    normals = np.array([[0, 0, 1]] * 3, dtype=np.float32)
    uvs = np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32)
    indices = np.array([0, 1, 2], dtype=np.uint16)
    blob = positions.tobytes() + normals.tobytes() + uvs.tobytes() + indices.tobytes()
    doc = {
        "asset": {"version": "2.0", "generator": "test"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "root", "children": [1], "translation": [1, 2, 3]},
                  {"name": "tri", "mesh": 0, "rotation": [0, 0, 0.7071068, 0.7071068]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
        "materials": [{"name": "m", "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": 3, "type": "SCALAR"}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 36},
            {"buffer": 0, "byteOffset": 72, "byteLength": 24},
            {"buffer": 0, "byteOffset": 96, "byteLength": 6}],
        "buffers": [{"byteLength": len(blob)}],
    }
    return make_glb(doc, blob)


class GltfTest(unittest.TestCase):
    def test_parse_triangle(self):
        asset = gltf.parse_glb(triangle_glb())
        self.assertEqual(asset.generator, "test")
        self.assertEqual(asset.roots, [0])
        self.assertEqual([n.name for n in asset.nodes], ["root", "tri"])
        self.assertEqual(asset.nodes[0].translation, (1.0, 2.0, 3.0))
        self.assertEqual(asset.nodes[0].children, [1])
        prim = asset.meshes[0][0]
        np.testing.assert_array_equal(prim.positions[1], [1, 0, 0])
        np.testing.assert_array_equal(prim.indices, [0, 1, 2])
        self.assertEqual(prim.uvs.shape, (3, 2))
        self.assertEqual(asset.materials[0].base_color, (1, 0, 0, 1))
        self.assertEqual(asset.find_node("tri"), 1)
        self.assertIsNone(asset.find_node("nope"))

    def test_rejects_garbage(self):
        with self.assertRaises(gltf.GltfError):
            gltf.parse_glb(b"not a glb at all, definitely not")
        with self.assertRaises(gltf.GltfError):
            gltf.parse_glb(b"x")

    def test_matrix_node_is_decomposed(self):
        # column-major matrix: scale 2, translation (1, 2, 3)
        matrix = [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 1, 2, 3, 1]
        t, r, s = gltf._decompose(matrix)
        self.assertEqual(t, (1.0, 2.0, 3.0))
        self.assertEqual(s, (2.0, 2.0, 2.0))
        self.assertAlmostEqual(r[3], 1.0)


if __name__ == "__main__":
    unittest.main()
