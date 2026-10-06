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
"""Measurement systems for rulers and readouts. Lengths are millimetres (the FreeCAD document unit). No FreeCAD imports.

A `MeasureSystem` is a list of units, each applying from a threshold length upwards, so a length is shown in the unit that
keeps its number readable. `system_for` maps the name of a FreeCAD document unit system (the `UnitSystem` property of a document,
for example "Imperial decimal (in, lb)") to one of the systems below.
"""

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Unit:
    symbol: str
    mm: float          # length of one unit in millimetres


@dataclass(frozen=True)
class MeasureSystem:
    name: str
    steps: Tuple[Tuple[float, Unit], ...]   # (smallest length in mm shown in the unit, unit), ascending


UM, MM, CM, M, KM = Unit("µm", 0.001), Unit("mm", 1.0), Unit("cm", 10.0), Unit("m", 1000.0), Unit("km", 1e6)
THOU, INCH, FOOT, MILE = Unit("thou", 0.0254), Unit("in", 25.4), Unit("ft", 304.8), Unit("mi", 1609344.0)

METRIC_MM = MeasureSystem("metric (mm)", ((0.0, UM), (1.0, MM), (1000.0, M), (1e6, KM)))
METRIC_CM = MeasureSystem("metric (cm)", ((0.0, UM), (1.0, MM), (10.0, CM), (1000.0, M), (1e6, KM)))
METRIC_M = MeasureSystem("metric (m)", ((0.0, UM), (1.0, MM), (100.0, M), (1e6, KM)))
IMPERIAL = MeasureSystem("imperial", ((0.0, THOU), (2.54, INCH), (304.8, FOOT), (1609344.0, MILE)))


def system_for(unit_system_name):
    """The measure system for the name of a FreeCAD document unit system; unknown or empty names give millimetres."""
    name = (unit_system_name or "").lower()
    if "building us" in name or "imperial" in name or "us customary" in name:
        return IMPERIAL
    if "building euro" in name:
        return METRIC_CM
    if name.startswith("mks") or "meter decimal" in name:
        return METRIC_M
    return METRIC_MM


def unit_for(system, length_mm):
    """The unit in which `length_mm` is shown."""
    length = abs(length_mm)
    chosen = system.steps[0][1]
    for threshold, unit in system.steps:
        if length >= threshold:
            chosen = unit
    return chosen


def nice_step(target):
    """The value of the series 1, 2, 5, 10, 20, 50, ... that is nearest to `target` on a logarithmic scale."""
    if target <= 0:
        raise ValueError("target must be positive")
    exponent = math.floor(math.log10(target))
    best = None
    for exp in (exponent, exponent + 1):
        for mantissa in (1, 2, 5):
            value = mantissa * 10.0 ** exp
            error = abs(math.log(value / target))
            if best is None or error < best[0]:
                best = (error, mantissa, exp)
    return best[1] * 10.0 ** best[2]


def format_number(value):
    """About three significant digits, without trailing zeros: 142, 14.2, 1.42, 0.5."""
    a = abs(value)
    digits = 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 1 else 3
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def format_length(length_mm, system, unit=None):
    """"142 mm", "1.25 m" ...; `unit` forces a unit, otherwise the one that suits the length."""
    unit = unit or unit_for(system, length_mm)
    return f"{format_number(length_mm / unit.mm)} {unit.symbol}"


@dataclass(frozen=True)
class RulerSpec:
    unit: Unit        # the unit of the tick labels
    step_mm: float    # distance of the labelled ticks
    minor_mm: float   # distance of the unlabelled ticks


def ruler_spec(system, target_step_mm):
    """Tick spacing close to `target_step_mm` that falls on round numbers of the unit of the system."""
    unit = unit_for(system, target_step_mm)
    in_unit = nice_step(target_step_mm / unit.mm)
    mantissa = round(in_unit / 10.0 ** math.floor(math.log10(in_unit)))
    divisions = {1: 10, 2: 4, 5: 5}[mantissa]
    step_mm = in_unit * unit.mm
    return RulerSpec(unit, step_mm, step_mm / divisions)
