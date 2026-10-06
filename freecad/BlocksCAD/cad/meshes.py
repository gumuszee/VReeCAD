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
"""Meshes for the preview of a primitive (docs/ux-design.md, Create tool). Pure Python, no FreeCAD or Coin imports.

The preview must change at every step of a drag, so its mesh is built here from the same sizing rules as the feature
(`primitives.parameters`) instead of being tessellated by OpenCASCADE: the triangulation is the same at every size (nothing
flickers), building it takes a few milliseconds (a torus included), and the vertices carry exact normals for shading. The
features themselves are made by FreeCAD; the preview is polygonal, with the segment counts below.

`build` returns a `Mesh`: points and normals (one normal per point), triangles wound counter-clockwise seen from outside, and
`outline`, polylines along the characteristic edges (circles, seams, box edges) that are drawn as lines over the shaded body."""

import math
from dataclasses import dataclass, field
from typing import List, Tuple

from freecad.BlocksCAD.cad import primitives as prim
from freecad.BlocksCAD.core import mathutil as mu

ROUND = 48              # segments around a cylinder, a cone and the big circle of a torus
SPHERE_RINGS = 18
SPHERE_SEGMENTS = 36
TUBE = 16               # segments around the tube of a torus


@dataclass
class Mesh:
    points: List[Tuple[float, float, float]] = field(default_factory=list)
    normals: List[Tuple[float, float, float]] = field(default_factory=list)
    triangles: List[Tuple[int, int, int]] = field(default_factory=list)
    outline: List[List[Tuple[float, float, float]]] = field(default_factory=list)


def volume(mesh):
    """The signed volume enclosed by the mesh (positive when the triangles face outwards)."""
    total = 0.0
    for a, b, c in mesh.triangles:
        total += mu.dot(mesh.points[a], mu.cross(mesh.points[b], mesh.points[c]))
    return total / 6.0


class _Builder:
    def __init__(self, centre):
        self.mesh = Mesh()
        self.centre = centre

    def vertex(self, point, normal):
        self.mesh.points.append(tuple(point))
        self.mesh.normals.append(tuple(normal))
        return len(self.mesh.points) - 1

    def tri(self, a, b, c):
        """A triangle wound to agree with the normals of its vertices; a degenerate one is dropped."""
        p, n = self.mesh.points, self.mesh.normals
        face = mu.cross(mu.sub(p[b], p[a]), mu.sub(p[c], p[a]))
        if mu.length(face) < 1e-9:
            return
        if mu.dot(face, mu.add(n[a], mu.add(n[b], n[c]))) < 0:
            b, c = c, b
        self.mesh.triangles.append((a, b, c))

    def flat(self, corners):
        """A flat convex polygon, its normal pointing away from the centre of the shape."""
        normal = (0.0, 0.0, 0.0)
        for i, p in enumerate(corners):                      # the sum of the edge terms gives the polygon normal
            q = corners[(i + 1) % len(corners)]
            normal = mu.add(normal, ((p[1] - q[1]) * (p[2] + q[2]), (p[2] - q[2]) * (p[0] + q[0]), (p[0] - q[0]) * (p[1] + q[1])))
        normal = mu.normalize(normal)
        middle = mu.mul(tuple(map(sum, zip(*corners))), 1.0 / len(corners))
        if mu.dot(normal, mu.sub(middle, self.centre)) < 0:
            normal = mu.mul(normal, -1.0)
        ids = [self.vertex(p, normal) for p in corners]
        for i in range(1, len(ids) - 1):
            self.tri(ids[0], ids[i], ids[i + 1])

    def fan(self, centre, ring, normal):
        """A disc: the vertices of `ring` joined to its `centre`, all with `normal`."""
        middle = self.vertex(centre, normal)
        ids = [self.vertex(p, normal) for p in ring]
        for i in range(len(ids)):
            self.tri(middle, ids[i], ids[(i + 1) % len(ids)])

    def grid(self, rows):
        """Triangles between neighbouring rows of vertex ids; a row wraps round."""
        for r in range(len(rows) - 1):
            a, b = rows[r], rows[r + 1]
            for i in range(len(a)):
                j = (i + 1) % len(a)
                self.tri(a[i], a[j], b[i])
                self.tri(a[j], b[j], b[i])


def _circle(centre, radius, z, count=ROUND, closed=True):
    points = [(centre[0] + radius * math.cos(2 * math.pi * i / count), centre[1] + radius * math.sin(2 * math.pi * i / count), z)
              for i in range(count)]
    return points + points[:1] if closed else points


def _box(lo, size):
    x0, y0, z0 = lo
    x1, y1, z1 = x0 + size[0], y0 + size[1], z0 + size[2]
    b = _Builder((x0 + size[0] / 2, y0 + size[1] / 2, z0 + size[2] / 2))
    c = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]       # index = x + 2 y + 4 z
    for face in ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)):
        b.flat([c[i] for i in face])
    edges = ((0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7))
    b.mesh.outline = [[c[i], c[j]] for i, j in edges]
    return b.mesh


def _revolved(spec, top_radius):
    """A cylinder (`top_radius` equal to the radius) or a cone (0) standing on the bottom of its box."""
    cx, cy, z0 = spec.position
    r, h = spec.props.get("Radius", spec.props.get("Radius1")), spec.props["Height"]
    b = _Builder((cx, cy, z0 + h / 2))
    slope = (r - top_radius) / h
    bottom, top = [], []
    for i in range(ROUND):
        a = 2 * math.pi * i / ROUND
        normal = mu.normalize((math.cos(a), math.sin(a), slope))
        bottom.append(b.vertex((cx + r * math.cos(a), cy + r * math.sin(a), z0), normal))
        if top_radius > 0:
            top.append(b.vertex((cx + top_radius * math.cos(a), cy + top_radius * math.sin(a), z0 + h), normal))
        else:                                    # a cone: the apex is one vertex per segment, each with the normal of its segment
            mid = a + math.pi / ROUND
            top.append(b.vertex((cx, cy, z0 + h), mu.normalize((math.cos(mid), math.sin(mid), slope))))
    b.grid([bottom, top])
    b.fan((cx, cy, z0), _circle((cx, cy), r, z0, closed=False), (0.0, 0.0, -1.0))
    if top_radius > 0:
        b.fan((cx, cy, z0 + h), _circle((cx, cy), top_radius, z0 + h, closed=False), (0.0, 0.0, 1.0))
    quarter = ((1, 0), (0, 1), (-1, 0), (0, -1))
    outline = [_circle((cx, cy), r, z0)]
    if top_radius > 0:
        outline.append(_circle((cx, cy), top_radius, z0 + h))
        outline += [[(cx + d * r, cy + e * r, z0), (cx + d * top_radius, cy + e * top_radius, z0 + h)] for d, e in quarter]
    else:
        outline += [[(cx + d * r, cy + e * r, z0), (cx, cy, z0 + h)] for d, e in quarter]
    b.mesh.outline = outline
    return b.mesh


def _sphere(spec):
    cx, cy, cz = spec.position
    r = spec.props["Radius"]
    b = _Builder((cx, cy, cz))
    rows = []
    for j in range(SPHERE_RINGS + 1):
        phi = math.pi * j / SPHERE_RINGS
        row = []
        for i in range(SPHERE_SEGMENTS):
            theta = 2 * math.pi * i / SPHERE_SEGMENTS
            n = (math.sin(phi) * math.cos(theta), math.sin(phi) * math.sin(theta), math.cos(phi))
            row.append(b.vertex((cx + r * n[0], cy + r * n[1], cz + r * n[2]), n))
        rows.append(row)
    b.grid(rows)
    around = [(math.cos(2 * math.pi * i / ROUND), math.sin(2 * math.pi * i / ROUND)) for i in range(ROUND + 1)]
    b.mesh.outline = [[(cx + r * c, cy + r * s, cz) for c, s in around],
                      [(cx + r * c, cy, cz + r * s) for c, s in around],
                      [(cx, cy + r * c, cz + r * s) for c, s in around]]
    return b.mesh


def _torus(spec):
    cx, cy, cz = spec.position
    big, small = spec.props["Radius1"], spec.props["Radius2"]
    b = _Builder((cx, cy, cz))
    rows = []
    for i in range(ROUND):
        u = 2 * math.pi * i / ROUND
        row = []
        for j in range(TUBE):
            v = 2 * math.pi * j / TUBE
            ring = big + small * math.cos(v)
            row.append(b.vertex((cx + ring * math.cos(u), cy + ring * math.sin(u), cz + small * math.sin(v)),
                                (math.cos(v) * math.cos(u), math.cos(v) * math.sin(u), math.sin(v))))
        rows.append(row)
    for i in range(ROUND):
        a, c = rows[i], rows[(i + 1) % ROUND]
        for j in range(TUBE):
            k = (j + 1) % TUBE
            b.tri(a[j], c[j], a[k])
            b.tri(c[j], c[k], a[k])

    def section(u):
        ring = [big + small * math.cos(2 * math.pi * j / TUBE) for j in range(TUBE + 1)]
        return [(cx + ring[j] * math.cos(u), cy + ring[j] * math.sin(u), cz + small * math.sin(2 * math.pi * j / TUBE))
                for j in range(TUBE + 1)]

    b.mesh.outline = [_circle((cx, cy), big + small, cz), _circle((cx, cy), big - small, cz), section(0.0), section(math.pi / 2)]
    return b.mesh


def _wedge(lo, size):
    """A ramp: the triangle (y0, z0), (y1, z0), (y1, z1) in the YZ plane, extruded along X; it rises towards +Y."""
    x0, y0, z0 = lo
    x1, y1, z1 = x0 + size[0], y0 + size[1], z0 + size[2]
    b = _Builder((x0 + size[0] / 2, y0 + 2 * size[1] / 3, z0 + size[2] / 3))
    a0, b0, c0 = (x0, y0, z0), (x0, y1, z0), (x0, y1, z1)
    a1, b1, c1 = (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)
    for face in ((a0, b0, c0), (a1, b1, c1), (a0, b0, b1, a1), (b0, c0, c1, b1), (a0, c0, c1, a1)):
        b.flat(list(face))
    b.mesh.outline = [[a0, b0, c0, a0], [a1, b1, c1, a1], [a0, a1], [b0, b1], [c0, c1]]
    return b.mesh


def _prism(spec):
    cx, cy, z0 = spec.position
    r, h, sides = spec.props["Circumradius"], spec.props["Height"], int(spec.props["Polygon"])
    b = _Builder((cx, cy, z0 + h / 2))
    low = _circle((cx, cy), r, z0, sides, closed=False)
    high = [(x, y, z0 + h) for x, y, _ in low]
    b.flat(low)
    b.flat(high)
    for i in range(sides):
        j = (i + 1) % sides
        b.flat([low[i], low[j], high[j], high[i]])
    b.mesh.outline = [low + low[:1], high + high[:1]] + [[low[i], high[i]] for i in range(sides)]
    return b.mesh


def build(shape, lo, size) -> Mesh:
    """The preview mesh of `shape` fitted into the box with lowest corner `lo` and edge lengths `size` (document millimetres)."""
    spec = prim.parameters(shape, lo, size)
    if shape == "Box":
        return _box(lo, size)
    if shape == "Cylinder":
        return _revolved(spec, spec.props["Radius"])
    if shape == "Cone":
        return _revolved(spec, 0.0)
    if shape == "Sphere":
        return _sphere(spec)
    if shape == "Torus":
        return _torus(spec)
    if shape == "Wedge":
        return _wedge(lo, size)
    return _prism(spec)
