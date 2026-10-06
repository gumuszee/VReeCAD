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
"""Sim backend: a scripted head and two controllers without a headset (docs/design.md, Test strategy).

`SimInput` produces `InputFrame`s from poses and button values that a script sets, with the same edge detection as the
OpenXR backend. `SimSession` adds a Coin scene (the FreeCAD document scene, generated controller shapes at the hand poses)
and renders it offscreen from the head or either eye, so a test can "move in VR space" and photograph the result.

Stage frame: metres, Y up, the head looks along -Z. The document scene is placed like in the headset: millimetres to
metres and Z up to Y up.
"""

import math

from freecad.BlocksCAD.input import HandInput, InputFrame, InputTracker, Pose

IPD = 0.064  # metres between the eyes


def quat_from_axis_angle(axis, angle):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    s = math.sin(angle / 2) / n
    return (x * s, y * s, z * s, math.cos(angle / 2))


def quat_multiply(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


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


def look_at(position, target, up=(0.0, 1.0, 0.0)):
    """Orientation (x, y, z, w) whose -Z axis points from `position` to `target`."""
    f = tuple(t - p for t, p in zip(target, position))
    fl = math.sqrt(sum(c * c for c in f)) or 1.0
    f = tuple(c / fl for c in f)
    # camera axes: z = -f, x = up x z, y = z x x
    z = tuple(-c for c in f)
    x = (up[1] * z[2] - up[2] * z[1], up[2] * z[0] - up[0] * z[2], up[0] * z[1] - up[1] * z[0])
    xl = math.sqrt(sum(c * c for c in x))
    if xl < 1e-9:  # looking along the up axis
        x = (1.0, 0.0, 0.0)
        xl = 1.0
    x = tuple(c / xl for c in x)
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
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


class SimInput:
    """Scripted input source; `frame()` advances the clock and returns an `InputFrame` with edges."""

    HAND_FIELDS = ("trigger", "grip", "stick", "stick_click", "button1", "button2", "menu")

    def __init__(self, profile="/interaction_profiles/valve/frame_controller_valve"):
        self.profile = profile
        self.time = 0.0
        self.head = Pose((0.0, 1.6, 0.0), (0.0, 0.0, 0.0, 1.0), True)
        self.hands = [HandInput(), HandInput()]
        self.set_hand(0, position=(-0.25, 1.2, -0.35))
        self.set_hand(1, position=(0.25, 1.2, -0.35))
        self._tracker = InputTracker()

    def set_head(self, position=None, orientation=None, look_at_point=None):
        pos = tuple(position) if position is not None else self.head.position
        if look_at_point is not None:
            orientation = look_at(pos, look_at_point)
        ori = tuple(orientation) if orientation is not None else self.head.orientation
        self.head = Pose(pos, ori, True)

    def set_hand(self, hand, position=None, orientation=None, point_at=None, **inputs):
        """Pose and input values of one hand (0 = left, 1 = right). `point_at` aims the controller (-Z) at a stage point."""
        h = self.hands[hand]
        pos = tuple(position) if position is not None else h.aim.position
        if point_at is not None:
            orientation = look_at(pos, point_at)
        ori = tuple(orientation) if orientation is not None else h.aim.orientation
        h.aim = Pose(pos, ori, True)
        h.grip_pose = Pose(pos, ori, True)
        for name, value in inputs.items():
            if name not in self.HAND_FIELDS:
                raise ValueError(f"unknown input '{name}'")
            setattr(h, name, value)

    def frame(self, dt=1.0 / 72.0):
        self.time += dt
        frame = InputFrame(time=self.time, head=self.head, profile=self.profile)
        frame.hands = tuple(HandInput(**{f: getattr(h, f) for f in (
            "aim", "grip_pose", "trigger", "grip", "stick", "stick_click", "button1", "button2", "menu")}) for h in self.hands)
        return self._tracker.update(frame)


class SimSession:
    """Input plus a renderable scene. `document_scene` is the FreeCAD scene graph (millimetres, Z up) or None."""

    def __init__(self, document_scene=None, profile="/interaction_profiles/valve/frame_controller_valve"):
        from pivy import coin
        from freecad.BlocksCAD.render.controller_shape import build_fallback
        self._coin = coin
        self.input = SimInput(profile)
        self.last_frame = None
        self.scene = coin.SoSeparator()
        self.scene.ref()
        environment = coin.SoEnvironment()
        environment.ambientIntensity = 0.7
        self.scene.addChild(environment)
        light = coin.SoDirectionalLight()
        light.direction.setValue(-0.4, -0.8, -0.6)
        self.scene.addChild(light)
        if document_scene is not None:
            doc = coin.SoSeparator()
            xf = coin.SoTransform()
            xf.scaleFactor.setValue(0.001, 0.001, 0.001)
            xf.rotation.setValue(coin.SbRotation(coin.SbVec3f(1, 0, 0), -math.pi / 2))
            doc.addChild(xf)
            doc.addChild(document_scene)
            self.scene.addChild(doc)
        self.hand_transforms = []
        self.hand_models = []
        for side in ("left", "right"):
            sep = coin.SoSeparator()
            xf = coin.SoTransform()
            sep.addChild(xf)
            model = build_fallback(side)
            sep.addChild(model.root)
            self.scene.addChild(sep)
            self.hand_transforms.append(xf)
            self.hand_models.append(model)

    def frame(self, dt=1.0 / 72.0):
        """Advance the simulated time, pose the controller models and return the `InputFrame`."""
        from freecad.BlocksCAD.render.controller_shape import animate
        frame = self.input.frame(dt)
        for hand, xf in enumerate(self.hand_transforms):
            aim = frame.hands[hand].aim
            xf.translation.setValue(*aim.position)
            xf.rotation.setValue(*aim.orientation)
            animate(self.hand_models[hand], frame.hands[hand])
        self.last_frame = frame
        return frame

    def render(self, eye="head", size=(1024, 768), fov=1.2, **kwargs):
        """Render from the head (`eye` = "head", "left" or "right") and return a QImage."""
        from freecad.BlocksCAD.render import offscreen
        head = self.input.head
        offset = {"head": 0.0, "left": -IPD / 2, "right": IPD / 2}[eye]
        pos = tuple(p + o for p, o in zip(head.position, rotate(head.orientation, (offset, 0.0, 0.0))))
        return offscreen.render(self.scene, pos, orientation=head.orientation, size=size, fov=fov,
                                near=0.02, far=200.0, headlight=False, **kwargs)

    def render_stereo(self, size=(960, 960), **kwargs):
        """Side by side image like the headset mirror: left eye, right eye."""
        from PySide6 import QtGui
        left = self.render("left", size, **kwargs)
        right = self.render("right", size, **kwargs)
        both = QtGui.QImage(size[0] * 2, size[1], QtGui.QImage.Format_RGB888)
        painter = QtGui.QPainter(both)
        painter.drawImage(0, 0, left)
        painter.drawImage(size[0], 0, right)
        painter.end()
        return both

    def close(self):
        self.scene.unref()
