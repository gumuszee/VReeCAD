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
"""Generated controller shape used when the runtime provides no controller model (docs/controller-models.md).

Built from Coin primitives, no assets. It uses the frame of the runtime models (metres; the head at the origin, the handle
extending along +Z, so the tool direction is -Z) and the same part names (`trigger`, `thumbstick`, `button_a`, ...), so the code that
animates a runtime model also animates this one.
"""

from pivy import coin

from freecad.BlocksCAD.render.gltf_coin import Model, ModelPart


def _part(parts, name, parent, color, shape, translation, rotation=(0, 0, 0, 1)):
    switch = coin.SoSwitch()
    switch.whichChild = coin.SO_SWITCH_ALL
    sep = coin.SoSeparator()
    transform = coin.SoTransform()
    transform.translation.setValue(*translation)
    transform.rotation.setValue(*rotation)
    sep.addChild(transform)
    material = coin.SoMaterial()
    material.diffuseColor.setValue(*color)
    sep.addChild(material)
    sep.addChild(shape)
    switch.addChild(sep)
    parent.addChild(switch)
    parts[name] = ModelPart(name, switch, transform)
    return sep


def _cube(w, h, d):
    cube = coin.SoCube()
    cube.width, cube.height, cube.depth = w, h, d
    return cube


def _cylinder(radius, height):
    cyl = coin.SoCylinder()
    cyl.radius, cyl.height = radius, height
    return cyl


def _sphere(radius):
    sph = coin.SoSphere()
    sph.radius = radius
    return sph


def build_fallback(side="right"):
    """Return a `Model` of a generic controller; `side` is "left" or "right" (the right one has the A/B buttons)."""
    root = coin.SoSeparator()
    root.ref()
    parts = {}
    dark, grey, accent = (0.16, 0.16, 0.18), (0.32, 0.32, 0.36), (0.25, 0.55, 0.9)
    _part(parts, "body", root, dark, _cylinder(0.022, 0.12), (0.0, -0.02, 0.10), (1, 0, 0, 0.7071))  # handle along Z
    _part(parts, "head", root, dark, _cylinder(0.04, 0.02), (0.0, 0.0, 0.04))
    _part(parts, "trigger", root, grey, _cube(0.012, 0.03, 0.012), (0.0, -0.03, 0.06))
    _part(parts, "button_grip", root, grey, _cube(0.012, 0.04, 0.03), (0.0, -0.03, 0.12))
    _part(parts, "thumbstick", root, accent, _sphere(0.009), (0.0, 0.016, 0.045))
    for name, x, z in (("button_a" if side == "right" else "button_x", 0.02, 0.03),
                       ("button_b" if side == "right" else "button_y", 0.025, 0.045)):
        _part(parts, name, root, accent, _cylinder(0.005, 0.004), (x if side == "right" else -x, 0.012, z))
    # a marker in the tool direction so the aim axis is visible in renders
    _part(parts, "tip", root, (0.9, 0.2, 0.2), _sphere(0.004), (0.0, 0.0, -0.01))
    return Model(root, parts)


def animate(model, hand):
    """Move the parts of a generated shape from an `input.HandInput` (the runtime provides this animation for its own models)."""
    trigger = model.part("trigger")
    if trigger:
        trigger.offset(0.0, 0.0, 0.008 * hand.trigger)
    grip = model.part("button_grip")
    if grip:
        grip.offset(0.004 * hand.grip, 0.0, 0.0)
    stick = model.part("thumbstick")
    if stick:
        stick.offset(0.008 * hand.stick[0], -0.003 if hand.stick_click else 0.0, -0.008 * hand.stick[1])
    for name, pressed in (("button_a", hand.button1), ("button_x", hand.button1),
                          ("button_b", hand.button2), ("button_y", hand.button2)):
        part = model.part(name)
        if part:
            part.offset(0.0, -0.003 if pressed else 0.0, 0.0)
