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
"""Plain tuple vector and quaternion math (no numpy, no Coin). Vectors are (x, y, z), quaternions (x, y, z, w)."""

import math

IDENTITY_QUAT = (0.0, 0.0, 0.0, 1.0)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def normalize(a):
    n = length(a)
    return (0.0, 0.0, 0.0) if n < 1e-12 else (a[0] / n, a[1] / n, a[2] / n)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def quat_from_axis_angle(axis, angle):
    x, y, z = normalize(axis) if length(axis) > 0 else (0.0, 0.0, 1.0)
    s = math.sin(angle / 2)
    return (x * s, y * s, z * s, math.cos(angle / 2))


def quat_multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quat_conjugate(q):
    return (-q[0], -q[1], -q[2], q[3])


def quat_normalize(q):
    n = math.sqrt(sum(c * c for c in q))
    return IDENTITY_QUAT if n < 1e-12 else tuple(c / n for c in q)


def quat_slerp(a, b, t):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = tuple(-c for c in b), -d
    if d > 0.9995:
        return quat_normalize(tuple(x + (y - x) * t for x, y in zip(a, b)))
    theta = math.acos(min(1.0, d))
    s = math.sin(theta)
    wa, wb = math.sin((1 - t) * theta) / s, math.sin(t * theta) / s
    return tuple(wa * x + wb * y for x, y in zip(a, b))


def rotate(q, v):
    """Rotate vector v by quaternion q."""
    qx, qy, qz, qw = q
    vx, vy, vz = v
    tx = 2 * (qy * vz - qz * vy)
    ty = 2 * (qz * vx - qx * vz)
    tz = 2 * (qx * vy - qy * vx)
    return (vx + qw * tx + (qy * tz - qz * ty),
            vy + qw * ty + (qz * tx - qx * tz),
            vz + qw * tz + (qx * ty - qy * tx))


def quat_between(a, b):
    """Shortest rotation taking direction a to direction b."""
    a, b = normalize(a), normalize(b)
    d = dot(a, b)
    if d < -0.999999:  # opposite: any perpendicular axis
        axis = cross((1.0, 0.0, 0.0), a)
        if length(axis) < 1e-6:
            axis = cross((0.0, 1.0, 0.0), a)
        return quat_from_axis_angle(axis, math.pi)
    c = cross(a, b)
    return quat_normalize((c[0], c[1], c[2], 1.0 + d))


def yaw_between(a, b, up=(0.0, 1.0, 0.0)):
    """Signed angle (radians, right-handed about `up`) from direction a to direction b, both projected on the plane normal to `up`.
    Returns 0.0 when either projection is degenerate."""
    up = normalize(up)
    pa = sub(a, mul(up, dot(a, up)))
    pb = sub(b, mul(up, dot(b, up)))
    if length(pa) < 1e-9 or length(pb) < 1e-9:
        return 0.0
    return math.atan2(dot(up, cross(pa, pb)), dot(pa, pb))


def quat_from_basis(x, y, z):
    """Quaternion of the rotation whose columns are the orthonormal axes x, y, z."""
    m00, m01, m02 = x[0], y[0], z[0]
    m10, m11, m12 = x[1], y[1], z[1]
    m20, m21, m22 = x[2], y[2], z[2]
    trace = m00 + m11 + m22
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        return ((m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s, 0.25 / s)
    if m00 > m11 and m00 > m22:
        s = 2.0 * math.sqrt(1.0 + m00 - m11 - m22)
        return (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    if m11 > m22:
        s = 2.0 * math.sqrt(1.0 + m11 - m00 - m22)
        return ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    s = 2.0 * math.sqrt(1.0 + m22 - m00 - m11)
    return ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)


def look_at(position, target, up=(0.0, 1.0, 0.0)):
    """Orientation (x, y, z, w) whose -Z axis points from `position` to `target`."""
    f = normalize(sub(target, position))
    z = mul(f, -1.0)
    x = cross(up, z)
    if length(x) < 1e-9:  # looking along the up axis
        x = (1.0, 0.0, 0.0)
    x = normalize(x)
    return quat_from_basis(x, cross(z, x), z)
