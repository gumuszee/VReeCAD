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
"""Mapping between the stage (tracking space, metres, Y up) and the document (millimetres, Z up). No FreeCAD imports.

The document scene sits under the navigation transform and the document transform: the document transform scales millimetres to
metres (`mm_to_stage`, 0.001) and turns Z up into Y up (a quarter turn about X); the navigation transform is the `WorldPose` of
the grip navigation. These functions are the inverse and the forward of that chain, so a controller position can be turned into
a document position and a document position into a point to draw at."""

import math

from freecad.VReeCAD.core import mathutil as mu

Z_UP = mu.quat_from_axis_angle((1.0, 0.0, 0.0), -math.pi / 2)    # the document transform's rotation
MM_TO_STAGE = 0.001


def to_document(world, point, mm_to_stage=MM_TO_STAGE):
    """The document position (millimetres) of a stage point, for a `navigation.WorldPose`."""
    local = world.to_world(point)
    return mu.mul(mu.rotate(mu.quat_conjugate(Z_UP), local), 1.0 / mm_to_stage)


def to_stage(world, point_mm, mm_to_stage=MM_TO_STAGE):
    """The stage position of a document point (millimetres)."""
    return world.to_stage(mu.rotate(Z_UP, mu.mul(point_mm, mm_to_stage)))


def orientation_to_document(world, orientation):
    """The orientation (quaternion x, y, z, w) of a stage pose in document axes."""
    return mu.quat_multiply(mu.quat_conjugate(Z_UP), mu.quat_multiply(mu.quat_conjugate(world.rotation), orientation))
