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

import functools

from freecad.VReeCAD.core import mathutil as mu

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


MAX_SEARCH = 7              # a polygon with at most this many corners is cut by looking at every way of cutting it


def _diagonal_inside(flat, i, j):
    """Whether the diagonal from corner i to corner j of the projected polygon `flat` lies inside it (neighbours always do)."""
    n = len(flat)
    if abs(i - j) in (1, n - 1):
        return True
    a, b = flat[i], flat[j]
    for k in range(n):
        l = (k + 1) % n
        if len({i, j, k, l}) < 4:
            continue
        c, d = flat[k], flat[l]
        if _area2(c, d, a) * _area2(c, d, b) < -1e-12 and _area2(a, b, c) * _area2(a, b, d) < -1e-12:
            return False
    middle = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    inside = False
    for k in range(n):
        c, d = flat[k], flat[(k + 1) % n]
        if (c[1] > middle[1]) != (d[1] > middle[1]) and middle[0] < (d[0] - c[0]) * (middle[1] - c[1]) / (d[1] - c[1]) + c[0]:
            inside = not inside
    return inside


def _cuts(count, valid):
    """Every way of cutting the polygon with corners 0 to count - 1 into triangles (i, k, j) with i < k < j by diagonals that `valid` allows."""
    memo = {}

    def cut(i, j):
        if j - i < 2:
            return [()]
        if (i, j) not in memo:
            result = []
            for k in range(i + 1, j):
                if (k - i >= 2 and not valid(i, k)) or (j - k >= 2 and not valid(k, j)):
                    continue
                for left in cut(i, k):
                    for right in cut(k, j):
                        result.append(left + right + ((i, k, j),))
            memo[(i, j)] = result
        return memo[(i, j)]

    return cut(0, count - 1)


def _unit_normal(a, b, c):
    normal = mu.cross(mu.sub(b, a), mu.sub(c, a))
    length = mu.length(normal)
    return mu.mul(normal, 1.0 / length) if length > 0.0 else (0.0, 0.0, 0.0)


def _bending(points, triangles):
    """How much a cut bends the surface: for every diagonal, the angle between its two triangles (1 - cos) times its length."""
    shared = {}
    for t in triangles:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            shared.setdefault((min(a, b), max(a, b)), []).append(t)
    total = 0.0
    for (a, b), pair in shared.items():
        if len(pair) == 2:
            n1, n2 = (_unit_normal(*(points[i] for i in t)) for t in pair)
            total += (1.0 - mu.dot(n1, n2)) * mu.length(mu.sub(points[a], points[b]))
    return total


def _smoothest_cut(points, flat):
    """The cut of a small polygon into triangles that bends the surface least, or None when no cut tiles it. A corner that sticks out of
    a bent polygon gets its edge to the corner below it, whichever way the corners are numbered."""
    area = sum(_area2(flat[0], flat[i], flat[i + 1]) for i in range(1, len(flat) - 1))
    best = None
    for triangles in _cuts(len(points), lambda i, j: _diagonal_inside(flat, i, j)):
        areas = [_area2(flat[a], flat[b], flat[c]) for a, b, c in triangles]
        if min(areas) <= 1e-12 or abs(sum(areas) - area) > 1e-9 * max(1.0, abs(area)):
            continue                                           # a triangle without area, or a cut that does not tile the polygon
        score = (round(_bending(points, triangles), 9), sum(mu.length(mu.sub(points[a], points[c])) for a, _, c in triangles))
        if best is None or score < best[0]:
            best = (score, triangles)
    return None if best is None else best[1]


def _folded_cut(points):
    """The cut of a small polygon that bends the surface least when no cut tiles its projection (the polygon is so bent that its outline
    crosses itself seen along its normal): every way of cutting it counts, whatever the diagonals do in the projection, as long as no
    triangle is flat or turned against the polygon. None when there is none."""
    normal, _ = newell(points)
    best = None
    for triangles in _cuts(len(points), lambda i, j: True):
        normals = [_unit_normal(*(points[i] for i in t)) for t in triangles]
        if any(mu.length(n) == 0.0 for n in normals):
            continue
        turned = sum(1 for n in normals if mu.dot(n, normal) < 0.0)
        score = (turned, round(_bending(points, triangles), 9))
        if best is None or score < best[0]:
            best = (score, triangles)
    return None if best is None else best[1]


def triangulate(points):
    """The triangles of `_triangulate` for the corners `points` (kept for the last polygons: a frame asks again and again)."""
    return list(_triangulate(tuple(tuple(p) for p in points)))


@functools.lru_cache(maxsize=1024)
def _triangulate(points):
    """Triangles (index triples into `points`, counter-clockwise like the polygon) that tile a polygon with three or more corners. A
    polygon of up to `MAX_SEARCH` corners is cut the way that bends the surface least (`_smoothest_cut`); a larger one, or one that
    cut cannot tile, by ear clipping in the best-fit plane of the corners. A flat or a slightly bent polygon of any shape works; a
    polygon without area gives no triangles."""
    count = len(points)
    if count < 3:
        return []
    if count == 3:
        return [(0, 1, 2)]
    flat = _project(points)
    if count <= MAX_SEARCH:
        cut = _smoothest_cut(points, flat) or _folded_cut(points)
        if cut is not None:
            return list(cut)
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


def _segment_hits_triangle(p, q, a, b, c, eps=1e-9):
    """Whether the segment from p to q passes through the inside of the triangle abc (Moeller and Trumbore, ends and edges excluded)."""
    direction = mu.sub(q, p)
    edge1, edge2 = mu.sub(b, a), mu.sub(c, a)
    h = mu.cross(direction, edge2)
    det = mu.dot(edge1, h)
    if abs(det) < eps:
        return False
    f = 1.0 / det
    s = mu.sub(p, a)
    u = f * mu.dot(s, h)
    if u <= eps or u >= 1.0 - eps:
        return False
    cross = mu.cross(s, edge1)
    v = f * mu.dot(direction, cross)
    if v <= eps or u + v >= 1.0 - eps:
        return False
    t = f * mu.dot(edge2, cross)
    return eps < t < 1.0 - eps


def faces_cross(vertices, faces):
    """Whether two triangles of the faces pass through each other (triangles that share a point are left alone): such a block is no
    solid, whatever the faces say."""
    triangles = [t for face in faces for t in face_triangles(vertices, face)]
    for i, t in enumerate(triangles):
        for u in triangles[i + 1:]:
            if set(t) & set(u):
                continue
            a, b, c = (vertices[k] for k in t)
            d, e, f = (vertices[k] for k in u)
            if (any(_segment_hits_triangle(p, q, a, b, c) for p, q in ((d, e), (e, f), (f, d)))
                    or any(_segment_hits_triangle(p, q, d, e, f) for p, q in ((a, b), (b, c), (c, a)))):
                return True
    return False


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
        triangles = face_triangles(vertices, face)
        if mu.length(newell(pts)[0]) == 0.0 or not triangles:
            return "A face has no area"
        if len(triangles) != len(face) - 2:
            return "A face folds over itself"
    volume = signed_volume(vertices, faces)
    if volume <= DEGENERATE:
        return "The block has no volume" if abs(volume) <= DEGENERATE else "The block is inside out"
    if faces_cross(vertices, faces):
        return "The faces cross each other"
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


def inner_point_on_segment(point, a, b, margin=1.0):
    """The point of the segment from `a` to `b` nearest to `point`, kept at least `margin` millimetres (a tenth of the segment at most)
    from both ends, so a point that splits an edge never lies on a corner."""
    ab = mu.sub(b, a)
    length = mu.length(ab)
    if length == 0.0:
        return a
    t, _, _ = nearest_on_segment(point, a, b)
    keep = min(margin, length * 0.1) / length
    return mu.add(a, mu.mul(ab, min(max(t, keep), 1.0 - keep)))


def coincident(vertices, index, point, tolerance=1e-6):
    """The index of another vertex that lies at `point` (within `tolerance` millimetres), or None: two points at one place make no solid."""
    for i, v in enumerate(vertices):
        if i != index and mu.length(mu.sub(v, point)) <= tolerance:
            return i
    return None


def nearest_vertex(vertices, point):
    """(distance, index) of the vertex nearest to `point`, or (None, -1)."""
    best, index = None, -1
    for i, v in enumerate(vertices):
        d = mu.length(mu.sub(point, v))
        if best is None or d < best:
            best, index = d, i
    return best, index


def diagonals(vertices, faces):
    """The sorted index pairs that cut the faces that are not flat into triangles, each once: they show as edges on the solid, though
    they belong to no face's outline (`cut_face` makes one an edge of the block)."""
    found = set()
    for face in faces:
        if len(face) <= 3 or is_flat([vertices[i] for i in face]):
            continue
        outline = {frozenset((face[k], face[(k + 1) % len(face)])) for k in range(len(face))}
        for t in face_triangles(vertices, face):
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                if frozenset((a, b)) not in outline:
                    found.add((min(a, b), max(a, b)))
    return sorted(found)


def cut_face(faces, a, b):
    """The faces with the face that has the corners `a` and `b` apart from each other cut in two along the line between them, so that
    the line is an edge of both halves; ValueError when no face has them so."""
    result = list(faces)
    for n, face in enumerate(result):
        if a in face and b in face:
            i, j = sorted((face.index(a), face.index(b)))
            if j - i < 2 or (i == 0 and j == len(face) - 1):
                continue                                          # neighbours: the line is an edge already
            result[n:n + 1] = [tuple(face[i:j + 1]), tuple(face[j:] + face[:i + 1])]
            return result
    raise ValueError("That is not an edge of the block")


def nearest_edge(vertices, faces, point):
    """(distance, (a, b), t, nearest point) of the edge nearest to `point`, or None when the block has no edges. `t` runs from the
    lower to the higher index of the pair. The lines that cut a bent face into triangles count as edges."""
    best = None
    for a, b in edges(faces) + diagonals(vertices, faces):
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


def remove_vertex(vertices, faces, index):
    """The block without vertex `index`: every face that has it loses that corner (a triangle disappears), and the hole that the
    corner leaves, a cap made of the corners next to it, becomes a face of its own (a corner of a box is cut off, a point that splits
    an edge only vanishes). The vertices after it are numbered one lower. Returns (vertices, faces); ValueError when the point is no
    corner of a closed star of faces. Whether the result is a solid is for `validate` to say."""
    pairs = []                                       # (corner before, corner after) of the point in each face that has it
    kept = []
    for face in faces:
        if index not in face:
            kept.append(tuple(face))
            continue
        k = face.index(index)
        pairs.append((face[k - 1], face[(k + 1) % len(face)]))
        rest = tuple(c for c in face if c != index)
        if len(rest) >= 3:
            kept.append(rest)
    if len(pairs) < 2:
        raise ValueError("That point has no faces")
    after = {succ: pred for pred, succ in pairs}     # the edges of the cap run the other way round: from the corner after to the one before
    if len(after) != len(pairs):
        raise ValueError("That point cannot be removed")
    ring = [pairs[0][1]]
    current = after[ring[0]]
    while current != ring[0]:
        ring.append(current)
        current = after.get(current)
        if current is None or len(ring) > len(pairs):
            raise ValueError("That point cannot be removed")
    if len(ring) != len(pairs):
        raise ValueError("That point cannot be removed")
    if len(ring) >= 3:
        kept.append(tuple(ring))

    def number(i):
        return i - 1 if i > index else i
    return [v for k, v in enumerate(vertices) if k != index], [tuple(number(i) for i in face) for face in kept]


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
