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
"""Headless rendering of a Coin3D scene to an image (SoOffscreenRenderer + Qt).

Needs a running FreeCAD GUI process (an OpenGL context). FreeCAD's Coin has no image-writer plugin, so the raw RGB
buffer is converted to a QImage and saved through Qt.
"""

from pivy import coin
from PySide6 import QtGui


def render(scene, position, target=None, orientation=None, up=(0.0, 1.0, 0.0), size=(1024, 768),
           fov=0.9, near=0.01, far=1000.0, background=(0.12, 0.12, 0.14), headlight=True, ambient=0.6):
    """Render `scene` (an SoNode) from a camera and return a QImage.

    The camera looks at `target`, or uses `orientation` (quaternion x, y, z, w; camera looks along -Z).
    `fov` is the vertical field of view in radians.
    """
    cam = coin.SoPerspectiveCamera()
    cam.position.setValue(*position)
    if orientation is not None:
        cam.orientation.setValue(*orientation)
    else:
        cam.pointAt(coin.SbVec3f(*target), coin.SbVec3f(*up))
    cam.heightAngle = fov
    cam.nearDistance = near
    cam.farDistance = far
    cam.aspectRatio = size[0] / size[1]

    root = coin.SoSeparator()
    root.ref()
    root.addChild(cam)
    if headlight:
        environment = coin.SoEnvironment()
        environment.ambientIntensity = ambient
        root.addChild(environment)
        light = coin.SoDirectionalLight()
        light.direction.setValue(-0.4, -0.8, -0.6)
        root.addChild(light)
        fill = coin.SoDirectionalLight()
        fill.direction.setValue(0.5, 0.3, 0.8)
        fill.intensity = 0.4
        root.addChild(fill)
    root.addChild(scene)

    renderer = coin.SoOffscreenRenderer(coin.SbViewportRegion(size[0], size[1]))
    renderer.setBackgroundColor(coin.SbColor(*background))
    try:
        if not renderer.render(root):
            raise RuntimeError("SoOffscreenRenderer.render failed")
        w, h = size
        image = QtGui.QImage(renderer.getBuffer(), w, h, w * 3, QtGui.QImage.Format_RGB888)
        return image.mirrored(False, True).copy()  # GL rows are bottom-up; copy detaches from the renderer buffer
    finally:
        root.unref()


def save(image, path):
    if not image.save(path):
        raise RuntimeError(f"cannot save {path}")
    return path
