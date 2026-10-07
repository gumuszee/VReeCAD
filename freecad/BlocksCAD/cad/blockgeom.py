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
"""The geometry of a Block, a polyhedron made of points (docs/ux-design.md, Points tool). Pure Python, no FreeCAD imports.

A block is a list of vertices (document millimetres) and a list of faces, each a tuple of vertex indices that runs counter-clockwise
seen from outside. A face may have any number of corners and need not be flat: a face that is not flat is built from triangles
(`triangulate`), so moving one vertex never breaks the solid. `validate` says whether the faces close into a solid (every edge is
shared by exactly two faces that run along it in opposite directions) with a positive volume. The functions return new lists and
never change their arguments."""

from freecad.BlocksCAD.core import mathutil as mu

FLAT = 1e-6                 # millimetres: a face whose corners are no further than this from their plane is flat
DEGENERATE = 1e-9           # squared millimetres: a triangle smaller than this has no area


def box(lo, size):
    """(vertices, faces) of the axis-aligned box with lowest corner `lo` and edge lengths `size`."""
    x, y, z = lo
    dx, dy, dz = size
    vertices = [(x, y, z), (x + dx, y, z), (x + dx, y + dy, z), (x, y + dy, z),
                (x, y, z + dz), (x + dx, y, z + dz), (x + dx, y + dy, z + dz), (x, y + dy, z + dz)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return vertices, faces


def newell(points):
    """(unit normal, centroid) of a polygon; the normal points to the side the corners run counter-clockwise."""
    normal = (0.0, 0.0, 0.0)
    for i, p in enumerate(points):
        q = points[(i + 1) % len(points)]
        normal = mu.add(normal, ((p[1] - q[1]) * (p[2] + q[2]), (p[2] - q[2]) * (p[0] + q[0]), (p[0] - q[0]) * (p[1] + q[1])))
    centroid = mu.mul(tuple(map(sum, zip(*points))), 1.0 / len(points))
    return mu.normalize(normal), centroid


def flatness(points):
    """The largest distance of a corner of a polygon from its plane (0 for a triangle)."""
    if len(points) <= 3:
        return 0.0
    normal, centroid = newell(points)
    return max(abs(mu.dot(mu.sub(p, centroid), normal)) for p in points)


def is_flat(points, tolerance=FLAT):
    return flatness(points) <= tolerance


def _project(points):
    """The corners of a polygon as 2D points in its plane, counter-clockwise seen along its normal."""
    normal, _ = newell(points)
    helper = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = mu.normalize(mu.cross(helper, normal))
    v = mu.cross(normal, u)
    return [(mu.dot(p, u), mu.dot(p, v)) for p in points]


def _area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _inside(p, a, b, c):
    return _area2(a, b, p) >= -1e-12 and _area2(b, c, p) >= -1e-12 and _area2(c, a, p) >= -1e-12


def triangulate(points):
    """Triangles (index triples into `points`, counter-clockwise like the polygon) that tile a polygon with three or more corners, by
    ear clipping in the best-fit plane of the corners. A flat or a slightly bent polygon of any shape works; a polygon without area
    gives no triangles."""
    count = len(points)
    if count < 3:
        return []
    if count == 3:
        return [(0, 1, 2)]
    flat = _project(points)
    order = list(range(count))
    triangles = []
    guard = count * count
    while len(order) > 3 and guard > 0:
        guard -= 1
        for k, i in enumerate(order):
            prev, nxt = order[k - 1], order[(k + 1) % len(order)]
            a, b, c = flat[prev], flat[i], flat[nxt]
            if _area2(a, b, c) <= 1e-12:
                continue                                   # a reflex or a flat corner is not an ear
            if any(_inside(flat[j], a, b, c) for j in order if j not in (prev, i, nxt)):
                continue
            triangles.append((prev, i, nxt))
            order.pop(k)
            break
        else:
            break                                          # no ear is left: the rest has no area or crosses itself
    if len(order) == 3 and _area2(*(flat[j] for j in order)) > 1e-12:
        triangles.append(tuple(order))
    return triangles


def face_triangles(vertices, face):
    """Triangles of a face as triples of vertex indices (the face itself when it is one)."""
    return [tuple(face[i] for i in t) for t in triangulate([vertices[i] for i in face])]


def signed_volume(vertices, faces):
    """The volume the faces enclose; positive when they run counter-clockwise seen from outside."""
    total = 0.0
    for face in faces:
        for a, b, c in face_triangles(vertices, face):
            total += mu.dot(vertices[a], mu.cross(vertices[b], vertices[c]))
    return total / 6.0


def validate(vertices, faces):
    """None when the faces close into a solid with a positive volume, else a short text that says what is wrong."""
    if len(vertices) < 4:
        return "A block needs at least four points"
    if len(faces) < 4:
        return "A block needs at least four faces"
    directed = {}
    for face in faces:
        if len(face) < 3 or len(set(face)) != len(face):
            return "A face needs three different points"
        if any(not 0 <= i < len(vertices) for i in face):
            return "A face uses a point that does not exist"
        for k, a in enumerate(face):
            edge = (a, face[(k + 1) % len(face)])
            directed[edge] = directed.get(edge, 0) + 1
    for (a, b), n in directed.items():
        if n != 1 or directed.get((b, a)) != 1:
            return "The faces do not close into a solid"
    for face in faces:
        pts = [vertices[i] for i in face]
        if mu.length(newell(pts)[0]) == 0.0 or not face_triangles(vertices, face):
            return "A face has no area"
    volume = signed_volume(vertices, faces)
    if volume <= DEGENERATE:
        return "The block has no volume" if abs(volume) <= DEGENERATE else "The block is inside out"
    return None


def edges(faces):
    """The edges of a block as sorted index pairs, each once, in order of appearance."""
    seen, result = set(), []
    for face in faces:
        for k, a in enumerate(face):
            key = tuple(sorted((a, face[(k + 1) % len(face)])))
            if key not in seen:
                seen.add(key)
                result.append(key)
    return result


def nearest_on_segment(point, a, b):
    """(t, nearest point, distance) of `point` to the segment from `a` to `b`; t runs from 0 at `a` to 1 at `b`."""
    ab = mu.sub(b, a)
    length2 = mu.dot(ab, ab)
    t = 0.0 if length2 == 0 else min(max(mu.dot(mu.sub(point, a), ab) / length2, 0.0), 1.0)
    nearest = mu.add(a, mu.mul(ab, t))
    return t, nearest, mu.length(mu.sub(point, nearest))


def nearest_vertex(vertices, point):
    """(distance, index) of the vertex nearest to `point`, or (None, -1)."""
    best, index = None, -1
    for i, v in enumerate(vertices):
        d = mu.length(mu.sub(point, v))
        if best is None or d < best:
            best, index = d, i
    return best, index


def nearest_edge(vertices, faces, point):
    """(distance, (a, b), t, nearest point) of the edge nearest to `point`, or None when the block has no edges. `t` runs from the
    lower to the higher index of the pair."""
    best = None
    for a, b in edges(faces):
        t, nearest, d = nearest_on_segment(point, vertices[a], vertices[b])
        if best is None or d < best[0]:
            best = (d, (a, b), t, nearest)
    return best


def split_edge(vertices, faces, a, b, point):
    """Add a vertex at `point` on the edge between `a` and `b`: it joins both faces that share the edge. Returns (vertices, faces, index
    of the new vertex)."""
    index = len(vertices)
    result = []
    touched = 0
    for face in faces:
        face = list(face)
        for k in range(len(face)):
            if {face[k], face[(k + 1) % len(face)]} == {a, b}:
                face.insert(k + 1, index)
                touched += 1
                break
        result.append(tuple(face))
    if touched != 2:
        raise ValueError("That is not an edge of the block")
    return list(vertices) + [tuple(point)], result, index


def move_vertex(vertices, index, point):
    """The vertices with vertex `index` at `point`."""
    moved = list(vertices)
    moved[index] = tuple(point)
    return moved


def face_planes(vertices, faces, index):
    """The planes that vertex `index` has to stay in for every face that has it to stay flat, as (unit normal, a point) pairs: for a face
    of four or more corners the plane of its other corners (the best fit of them when there are more than three). A triangle sets no
    plane, and neither do other corners that lie on a line."""
    planes = []
    for face in faces:
        if index not in face or len(face) < 4:
            continue
        others = [vertices[i] for i in face if i != index]
        normal, centroid = newell(others)
        if mu.length(normal) > 0.5:                       # `newell` gives the zero vector for corners without area
            planes.append((normal, centroid))
    return planes


def _solve(matrix, rhs):
    """The solution of the small linear system `matrix` y = `rhs` by elimination with the largest pivot."""
    n = len(rhs)
    rows = [list(matrix[i]) + [rhs[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(n):
            if r != col:
                factor = rows[r][col] / rows[col][col]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[col])]
    return [rows[i][n] / rows[i][i] for i in range(n)]


def constrain_to_planes(point, planes):
    """The point nearest to `point` that lies in all the `planes` ((unit normal, a point) pairs): the point itself with no plane, in
    the plane with one, on the line with two, the one corner with three. A plane that runs along one that is kept already is left out."""
    kept, basis = [], []
    for normal, origin in planes:
        residual = normal
        for q in basis:
            residual = mu.sub(residual, mu.mul(q, mu.dot(residual, q)))
        if mu.length(residual) < 1e-6:
            continue
        basis.append(mu.mul(residual, 1.0 / mu.length(residual)))
        kept.append((normal, mu.dot(normal, origin)))
        if len(kept) == 3:
            break
    if not kept:
        return tuple(point)
    gram = [[mu.dot(a[0], b[0]) for b in kept] for a in kept]
    gap = [mu.dot(n, point) - d for n, d in kept]
    weights = _solve(gram, gap)
    result = tuple(point)
    for (normal, _), w in zip(kept, weights):
        result = mu.sub(result, mu.mul(normal, w))
    return result


def faces_to_text(faces):
    """A list of faces as strings of indices ("0 3 2 1"), the form a FreeCAD property keeps."""
    return [" ".join(str(i) for i in face) for face in faces]


def faces_from_text(texts):
    return [tuple(int(i) for i in text.split()) for text in texts]


def bounds(vertices):
    """(lowest corner, highest corner) of the box around the vertices."""
    return tuple(min(v[i] for v in vertices) for i in range(3)), tuple(max(v[i] for v in vertices) for i in range(3))
