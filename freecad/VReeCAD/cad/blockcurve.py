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
"""Curved edges of a Block: cubic Bezier curves in space (docs/ux-design.md, Points tool). Pure Python, no FreeCAD imports.

An edge of a block between points `a` and `b` (`a` < `b`) is a straight line unless the block carries handles for it. The handles of
a curved edge are two vectors, one at each end: the offset from the point to the inner control point of the cubic curve, the way
the handles of a path look in a vector drawing program. They are offsets, so they move with their points. The handles are stored as
`handles[(a, b)] = (offset at a, offset at b)`; an edge without an entry is straight and an entry that equals the straight line
is not kept. A face with a curved edge is a patch spanned by its edge curves (`face_poles`): a Coons patch of degree three in both
directions, so the faces on both sides of an edge meet along exactly the same curve. A face of three or four points is one patch; a
face of more points is cut into triangles (`blockgeom.face_triangles`) and each triangle is a patch whose sides are the curves of the
edges of the face and straight lines inside it (`face_patches`).

A point can be **smooth**: `smooth` is a set of triples (p, a, b) with a < b, meaning that the handles of the edges p-a and p-b at the
point p lie on one line, pointing away from each other (the point sits in the middle of a smooth path); the lengths of the handles
stay free. `enforce_edge` and `enforce_moved` bring the partner handle back onto the line after a handle or a point has been moved.
The functions return new values and never change their arguments."""

from freecad.VReeCAD.cad import blockgeom
from freecad.VReeCAD.core import mathutil as mu

SAME = 1e-6                 # millimetres: handles that differ from the straight line by less than this are the straight line
MIN_T = 0.15                # a bend grabs an edge no nearer to an end than this fraction of the curve
SAMPLES = 32                # segments of the polyline that stands for a curve where it is measured


def key(a, b):
    return (a, b) if a < b else (b, a)


def straight_handles(pa, pb):
    """The handle offsets (at `pa`, at `pb`) of the straight line from `pa` to `pb`: a third of it from each end."""
    d = mu.mul(mu.sub(pb, pa), 1.0 / 3.0)
    return d, mu.mul(d, -1.0)


def to_text(handles):
    """The handles as strings, one per curved edge: "a b ax ay az bx by bz" (the form a FreeCAD property keeps)."""
    rows = []
    for (a, b), (ha, hb) in sorted(handles.items()):
        rows.append(" ".join([str(a), str(b)] + [repr(float(c)) for c in ha + hb]))
    return rows


def from_text(texts):
    handles = {}
    for text in texts:
        parts = text.split()
        if len(parts) != 8:
            continue
        a, b = int(parts[0]), int(parts[1])
        values = [float(c) for c in parts[2:]]
        handles[key(a, b)] = (tuple(values[:3]), tuple(values[3:]))
    return handles


def usable(handles, faces, count):
    """The handles of the edges that the faces have (and whose points exist): a handle of an edge that is gone is left out."""
    edges = set(blockgeom.edges(faces))
    return {k: v for k, v in handles.items() if k in edges and k[1] < count}


def poles(vertices, handles, a, b):
    """The four control points of the edge from point `a` to point `b` (the curve runs from `a`), straight when it has no handles."""
    pa, pb = tuple(vertices[a]), tuple(vertices[b])
    k = key(a, b)
    if k in handles:
        ha, hb = handles[k] if a < b else handles[k][::-1]
    else:
        ha, hb = straight_handles(pa, pb)
    return [pa, mu.add(pa, ha), mu.add(pb, hb), pb]


def store_edge(handles, vertices, a, b, curve):
    """`handles` with the edge from `a` to `b` given by the control points `curve` (that run from `a`); the straight line removes it."""
    result = dict(handles)
    ha, hb = mu.sub(curve[1], curve[0]), mu.sub(curve[2], curve[3])
    straight = straight_handles(tuple(vertices[a]), tuple(vertices[b]))
    if mu.length(mu.sub(ha, straight[0])) <= SAME and mu.length(mu.sub(hb, straight[1])) <= SAME:
        result.pop(key(a, b), None)
    else:
        result[key(a, b)] = (ha, hb) if a < b else (hb, ha)
    return result


def point_at(curve, t):
    """The point of the cubic curve with control points `curve` at parameter `t` (0 to 1)."""
    s = 1.0 - t
    weights = (s * s * s, 3.0 * s * s * t, 3.0 * s * t * t, t * t * t)
    return tuple(sum(w * p[i] for w, p in zip(weights, curve)) for i in range(3))


def sample(curve, count=SAMPLES):
    return [point_at(curve, i / count) for i in range(count + 1)]


def split_curve(curve, t):
    """(first part, second part): the control points of the two curves that the point at `t` cuts the curve into (de Casteljau)."""
    p0, p1, p2, p3 = curve
    a, b, c = mu.lerp(p0, p1, t), mu.lerp(p1, p2, t), mu.lerp(p2, p3, t)
    d, e = mu.lerp(a, b, t), mu.lerp(b, c, t)
    m = mu.lerp(d, e, t)
    return [p0, a, d, m], [m, e, c, p3]


def split_edge(vertices, handles, a, b, index, t):
    """The handles after the edge from `a` to `b` was cut at parameter `t` (measured from `a`) by the new point `index`, which sits on
    the curve (the vertices include it). The edge gives way to the edges `a`-`index` and `index`-`b`, that together are the same curve."""
    curve = poles(vertices[:index], handles, a, b)
    first, second = split_curve(curve, t)
    result = {k: v for k, v in handles.items() if k != key(a, b)}
    result = store_edge(result, vertices, a, index, first)
    return store_edge(result, vertices, index, b, second)


def renumber_after_removal(handles, removed):
    """The handles after point `removed` left the block: the edges of that point are gone, the points after it are numbered one lower."""
    result = {}
    for (a, b), value in handles.items():
        if removed in (a, b):
            continue
        result[(a - 1 if a > removed else a, b - 1 if b > removed else b)] = value
    return result


def nearest_on_curve(curve, point, count=SAMPLES):
    """(distance, t, nearest point) of `point` to the curve, measured to a polyline of `count` segments."""
    best = None
    line = sample(curve, count)
    for i in range(count):
        t, nearest, d = blockgeom.nearest_on_segment(point, line[i], line[i + 1])
        if best is None or d < best[0]:
            best = (d, (i + t) / count, nearest)
    return best


def nearest_edge(vertices, faces, handles, point):
    """(distance, (a, b), t, nearest point) of the edge nearest to `point`, the curved ones measured along their curve (`t` runs from
    the lower to the higher number of the pair along the curve); None for a block without edges. Like `blockgeom.nearest_edge`, which
    it equals when no edge is curved."""
    best = None
    for a, b in blockgeom.edges(faces):
        if (a, b) in handles:
            d, t, nearest = nearest_on_curve(poles(vertices, handles, a, b), point)
        else:
            t, nearest, d = blockgeom.nearest_on_segment(point, vertices[a], vertices[b])
        if best is None or d < best[0]:
            best = (d, (a, b), t, nearest)
    for a, b in blockgeom.diagonals(vertices, faces):
        t, nearest, d = blockgeom.nearest_on_segment(point, vertices[a], vertices[b])
        if best is None or d < best[0]:
            best = (d, (a, b), t, nearest)
    return best


def bend_through(curve, t, target):
    """The curve with its two inner control points moved the least that makes it pass through `target` at parameter `t` (kept between
    `MIN_T` and 1 - `MIN_T`): dragging the curve itself, the way a path is bent in a vector drawing program. Its ends stay."""
    t = min(max(t, MIN_T), 1.0 - MIN_T)
    s = 1.0 - t
    w1, w2 = 3.0 * s * s * t, 3.0 * s * t * t
    delta = mu.sub(target, point_at(curve, t))
    k = 1.0 / (w1 * w1 + w2 * w2)
    return [curve[0], mu.add(curve[1], mu.mul(delta, w1 * k)), mu.add(curve[2], mu.mul(delta, w2 * k)), curve[3]]


def clamp_t(t):
    return min(max(t, MIN_T), 1.0 - MIN_T)


def face_has_curve(handles, face):
    return any(key(face[k], face[(k + 1) % len(face)]) in handles for k in range(len(face)))


def coons(bottom, top, left, right):
    """The 4 by 4 control points `P[i][j]` (i along u, j along v) of the bicubic Coons patch between four cubic curves: `bottom` and `top`
    run along u at v = 0 and v = 1, `left` and `right` along v at u = 0 and u = 1; their ends must meet."""
    blend = (1.0, 2.0 / 3.0, 1.0 / 3.0, 0.0)            # the linear blend 1 - x written in the cubic Bernstein basis
    grid = [[None] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            s, t = i / 3.0, j / 3.0
            ruled_v = mu.add(mu.mul(bottom[i], blend[j]), mu.mul(top[i], 1.0 - blend[j]))
            ruled_u = mu.add(mu.mul(left[j], blend[i]), mu.mul(right[j], 1.0 - blend[i]))
            corners = mu.add(mu.add(mu.mul(bottom[0], (1 - s) * (1 - t)), mu.mul(bottom[3], s * (1 - t))),
                             mu.add(mu.mul(top[0], (1 - s) * t), mu.mul(top[3], s * t)))
            grid[i][j] = mu.sub(mu.add(ruled_v, ruled_u), corners)
    return grid


def face_poles(vertices, handles, face):
    """The 4 by 4 control points of the patch of a face of three or four points (counter-clockwise from outside, so the patch looks
    out), or None for another number of points. A triangle is a patch with one side shrunk to its last point."""
    if len(face) == 4:
        a, b, c, d = face
        return coons(poles(vertices, handles, a, b), poles(vertices, handles, d, c),
                     poles(vertices, handles, a, d), poles(vertices, handles, b, c))
    if len(face) == 3:
        a, b, c = face
        return coons(poles(vertices, handles, a, b), [tuple(vertices[c])] * 4,
                     poles(vertices, handles, a, c), poles(vertices, handles, b, c))
    return None


def face_patches(vertices, handles, face):
    """The control point grids of the patches of a face (counter-clockwise from outside): one for a face of three or four points, one
    for every triangle of a face of more points; the edges of the face are curves where they have handles, the lines inside it are
    straight. Empty for a face without area."""
    if len(face) in (3, 4):
        return [face_poles(vertices, handles, face)]
    return [face_poles(vertices, handles, triangle) for triangle in blockgeom.face_triangles(vertices, face)]


# smooth points
def smooth_to_text(smooth):
    return [" ".join(str(i) for i in triple) for triple in sorted(smooth)]


def smooth_from_text(texts):
    found = set()
    for text in texts:
        parts = text.split()
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            p, a, b = (int(part) for part in parts)
            found.add((p,) + tuple(sorted((a, b))))
    return found


def usable_smooth(smooth, faces, count):
    """The smooth points whose three points exist and whose two edges are edges of the faces."""
    edges = set(blockgeom.edges(faces))
    return {t for t in smooth if max(t) < count and key(t[0], t[1]) in edges and key(t[0], t[2]) in edges}


def smooth_pair(smooth, p, q):
    """The point `r` such that the edges p-q and p-r are kept on one line at p, or None."""
    for point, a, b in smooth:
        if point == p and q in (a, b):
            return b if q == a else a
    return None


def end_handle(vertices, handles, p, q):
    """The handle (offset) at point `p` of the edge from `p` to `q`, the third of the line when the edge is straight."""
    curve = poles(vertices, handles, p, q)
    return mu.sub(curve[1], curve[0])


def with_end_handle(vertices, handles, p, q, offset):
    """`handles` with the handle at `p` of the edge p-q set to `offset`."""
    curve = poles(vertices, handles, p, q)
    curve[1] = mu.add(curve[0], offset)
    return store_edge(handles, vertices, p, q, curve)


def align_partner(vertices, handles, p, driver, partner):
    """`handles` with the handle at `p` of the edge p-`partner` turned to point away from the handle of the edge p-`driver`, its length
    kept; unchanged when the driver has no length."""
    held = end_handle(vertices, handles, p, driver)
    length = mu.length(held)
    if length < SAME:
        return handles
    other = mu.length(end_handle(vertices, handles, p, partner))
    return with_end_handle(vertices, handles, p, partner, mu.mul(held, -(other if other >= SAME else length) / length))


def enforce_edge(vertices, handles, smooth, a, b):
    """`handles` after the handles of the edge a-b changed: at each end that is a smooth point the other edge of the pair follows."""
    for p, q in ((a, b), (b, a)):
        partner = smooth_pair(smooth, p, q)
        if partner is not None:
            handles = align_partner(vertices, handles, p, q, partner)
    return handles


def enforce_moved(vertices, handles, smooth, moved):
    """`handles` after point `moved` changed place: at every smooth point that it belongs to the pair is on one line again. When the
    point itself moved, the edge with a handle of its own drives, else the first."""
    for p, a, b in sorted(smooth):
        if moved == a:
            handles = align_partner(vertices, handles, p, b, a)
        elif moved == b:
            handles = align_partner(vertices, handles, p, a, b)
        elif moved == p:
            driver, partner = (b, a) if key(p, b) in handles and key(p, a) not in handles else (a, b)
            handles = align_partner(vertices, handles, p, driver, partner)
    return handles


def split_smooth(smooth, a, b, index, curved):
    """The smooth points after the edge a-b was cut by the new point `index`: the pairs that used the edge use the half next to their
    point; the new point is smooth when the edge was curved (the halves of a curve meet on one line)."""
    result = set()
    for p, x, y in smooth:
        if p == a and b in (x, y):
            x, y = (index if x == b else x), (index if y == b else y)
        elif p == b and a in (x, y):
            x, y = (index if x == a else x), (index if y == a else y)
        result.add((p,) + tuple(sorted((x, y))))
    if curved:
        result.add((index,) + tuple(sorted((a, b))))
    return result


def renumber_smooth_after_removal(smooth, removed):
    result = set()
    for triple in smooth:
        if removed in triple:
            continue
        p, a, b = (i - 1 if i > removed else i for i in triple)
        result.add((p,) + tuple(sorted((a, b))))
    return result


def make_smooth(vertices, handles, smooth, p, driver, partner):
    """(handles, smooth) with the edges p-`driver` and p-`partner` smooth at p: the partner handle is turned onto the line of the driver
    handle. A smooth pair that had either edge at p is replaced."""
    rest = {t for t in smooth if not (t[0] == p and (driver in t[1:] or partner in t[1:]))}
    rest.add((p,) + tuple(sorted((driver, partner))))
    return align_partner(vertices, handles, p, driver, partner), rest
