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
"""Entering and adjusting the values of an object (docs/ux-design.md, Value panels). No Coin, OpenXR or FreeCAD imports.

`evaluate` reads what the keypad types: numbers with the operators + - * / and brackets and the units mm, cm, m, in and ft, so
"2 * (3 cm + 4)" is a length. `ValueEditor` is the state of the panel: the values of one object (`ValueTarget`), the value that is
picked, the text being typed, and the step of the stick. The stick up and down changes the picked value by whole steps, the keypad
types an expression that is applied with Enter. Every change goes to the target at once, so the object follows in the scene; the
target keeps the changes of one gesture (a slider drag, a push of the stick, one Enter) in one transaction that `commit` keeps as
one undo step. There is no editing mode: the editor follows whatever object is selected and is simply dropped with it."""

import math
import re
from dataclasses import dataclass
from typing import List, Optional

from freecad.BlocksCAD.core import snapping, units

UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
UNIT_CYCLE = ("mm", "cm", "m", "in")       # the unit key turns the unit at the end of the text through these
ENTRY_KEYS = frozenset("0123456789.+-*/()")
MAX_ENTRY = 40                              # characters

_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*|\.\d+)|([a-zA-Z]+)|(.))")


def default_unit_mm(system):
    """Millimetres of the unit that a number without a unit is in: the unit of the document's measurement system."""
    return {units.IMPERIAL.name: UNITS["in"], units.METRIC_CM.name: UNITS["cm"], units.METRIC_M.name: UNITS["m"]}.get(system.name, 1.0)


class _Parser:
    """Recursive descent over the tokens; a value is (number, dimension) with dimension 1 for a length (the number is in
    millimetres) and 0 for a plain number."""

    def __init__(self, text, default_mm=1.0):
        self.default_mm = default_mm
        self.tokens = []
        position = 0
        text = text.strip()
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None:
                break
            number, word, other = match.groups()
            self.tokens.append(("n", float(number)) if number else ("w", word.lower()) if word else ("o", other))
            position = match.end()
        self.index = 0

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.index += 1
        return token

    def parse(self):
        if not self.tokens:
            raise ValueError("Nothing typed")
        value = self.expression()
        if self.peek()[0] is not None:
            raise ValueError(f"Cannot read '{self.peek()[1]}'")
        return value

    def expression(self):
        value = self.term()
        while self.peek() in (("o", "+"), ("o", "-")):
            sign = 1.0 if self.take()[1] == "+" else -1.0
            other = self.term()
            if value[1] != other[1]:       # a plain number next to a length is in the default unit
                value, other = [(n * self.default_mm, 1) if d == 0 else (n, d) for n, d in (value, other)]
            value = (value[0] + sign * other[0], value[1])
        return value

    def term(self):
        value = self.factor()
        while self.peek() in (("o", "*"), ("o", "/")):
            multiply = self.take()[1] == "*"
            other = self.factor()
            if multiply:
                if value[1] and other[1]:
                    raise ValueError("A length times a length is not a length")
                value = (value[0] * other[0], value[1] + other[1])
            else:
                if other[1] > value[1]:
                    raise ValueError("A number divided by a length is not a length")
                if other[0] == 0:
                    raise ValueError("Division by zero")
                value = (value[0] / other[0], value[1] - other[1])
        return value

    def factor(self):
        kind, text = self.peek()
        if (kind, text) in (("o", "-"), ("o", "+")):
            self.take()
            number, dimension = self.factor()
            return (-number if text == "-" else number, dimension)
        return self.atom()

    def atom(self):
        kind, text = self.take()
        if kind == "n":
            value = (text, 0)
        elif (kind, text) == ("o", "("):
            value = self.expression()
            if self.take() != ("o", ")"):
                raise ValueError("Missing )")
        elif kind is None:
            raise ValueError("The expression ends too early")
        else:
            raise ValueError(f"Cannot read '{text}'")
        if self.peek()[0] == "w":
            word = self.take()[1]
            if word not in UNITS:
                raise ValueError(f"Unknown unit '{word}'")
            if value[1]:
                raise ValueError("A length cannot have a unit twice")
            value = (value[0] * UNITS[word], 1)
        return value


def evaluate(text, default_mm=1.0):
    """The length in millimetres that `text` types (a plain number is in the unit of `default_mm` millimetres); ValueError with a
    short message that fits a toast when the text cannot be read."""
    number, dimension = _Parser(text, default_mm).parse()
    if dimension not in (0, 1):
        raise ValueError("That is not a length")
    result = number * default_mm if dimension == 0 else number
    if not math.isfinite(result):
        raise ValueError("That number is too large")
    return result


def cycle_unit(text):
    """`text` with the unit at its end turned to the next one (mm, cm, m, in); a text without a unit gets mm."""
    match = re.search(r"\s*([a-zA-Z]+)\s*$", text)
    if match is None or match.group(1).lower() not in UNIT_CYCLE:
        return (text.rstrip() + " mm") if text.strip() and text.rstrip()[-1] not in "+-*/(" else text
    index = (UNIT_CYCLE.index(match.group(1).lower()) + 1) % len(UNIT_CYCLE)
    return text[:match.start()] + " " + UNIT_CYCLE[index]


@dataclass
class Field:
    """One value of an object: `value` in millimetres, allowed from `low` to `high` (None for no limit)."""
    name: str
    label: str
    value: float
    low: Optional[float] = None
    high: Optional[float] = None


class ValueTarget:
    """What a `ValueEditor` edits; `cad.values.ObjectValues` is the one for FreeCAD objects. Subclass in tests."""
    title = ""

    def fields(self) -> List[Field]:
        raise NotImplementedError

    def set(self, name, value):
        """Apply `value` (millimetres) to the field `name`; ValueError with a short message when the object cannot take it."""
        raise NotImplementedError

    def commit(self):
        """Keep every change made by `set` as one undo step."""

    def cancel(self):
        """Take every change made by `set` back."""


def step_up(value, step):
    """The next multiple of `step` above `value` (a value that is on the grid goes one step up)."""
    return (math.floor(value / step + 1e-9) + 1) * step


def step_down(value, step):
    """The next multiple of `step` below `value`."""
    return (math.ceil(value / step - 1e-9) - 1) * step


class ValueEditor:
    """The state of the value panels for one `ValueTarget`. Keys: the characters of `ENTRY_KEYS`, "back", "clear", "unit", "enter"
    (apply the typed text and keep it), "step+", "step-" and "step" (the next step, round). `message` is the last thing to tell the
    user (None when everything went well); `dirty` says there are changes that `commit` has not kept yet."""

    def __init__(self, target, system=units.METRIC_MM, step=10.0):
        self.target = target
        self.system = system
        self.default_mm = default_unit_mm(system)
        self.fields = target.fields()
        self.selected = 0
        self.entry = None              # the text being typed, None when nothing is
        self.step_index = min(range(len(snapping.GRID_STEPS)), key=lambda i: abs(snapping.GRID_STEPS[i] - step))
        self.message = None
        self.dirty = False             # a value was changed and not kept yet

    @property
    def step(self):
        return snapping.GRID_STEPS[self.step_index]

    @property
    def field(self):
        return self.fields[self.selected]

    def text_of(self, field):
        """The value as text; a zero is in the unit of the system that suits a length of 100 mm (not in micrometres)."""
        unit = units.unit_for(self.system, 100.0) if field.value == 0 else None
        return units.format_length(field.value, self.system, unit)

    def select(self, index):
        """Pick a value (clamped); typing starts again."""
        index = min(max(index, 0), len(self.fields) - 1)
        if index != self.selected:
            self.selected, self.entry = index, None
            return True
        return False

    def _apply(self, value):
        """Set the picked field; returns whether the object took it."""
        field = self.field
        if field.low is not None:
            value = max(value, field.low)
        if field.high is not None:
            value = min(value, field.high)
        value = round(value, 9)
        if value == field.value:
            return False
        try:
            self.target.set(field.name, value)
        except ValueError as error:
            self.message = str(error)
            return False
        self.fields = self.target.fields()
        self.dirty = True
        return True

    def set_value(self, index, value):
        """Pick a value and set it (a slider): returns whether it changed."""
        self.select(index)
        self.message, self.entry = None, None
        return self._apply(value)

    def nudge(self, direction):
        """The stick up (+1) or down (-1): the picked value moves to the next multiple of the step. Returns whether it changed."""
        self.message, self.entry = None, None
        value = self.field.value
        return self._apply(step_up(value, self.step) if direction > 0 else step_down(value, self.step))

    def _enter(self):
        if self.entry is None:
            return False
        try:
            value = evaluate(self.entry, self.default_mm)
        except ValueError as error:
            self.message = str(error)
            return False
        self.entry = None
        self._apply(value)
        return True

    def key(self, key):
        """One key of the keypad; returns whether something changed (a haptic tick is due)."""
        self.message = None
        if key in ENTRY_KEYS:
            if self.entry is None:
                self.entry = ""
            if len(self.entry) >= MAX_ENTRY:
                return False
            self.entry += key
        elif key == "back":
            if self.entry is None:
                return False
            self.entry = self.entry[:-1] or None
        elif key == "clear":
            self.entry = None
        elif key == "unit":
            if self.entry is None:
                self.entry = ""
            self.entry = cycle_unit(self.entry)
        elif key == "enter":
            self._enter()
            self.commit()
        elif key in ("step+", "step-"):
            index = self.step_index + (1 if key == "step+" else -1)
            if not 0 <= index < len(snapping.GRID_STEPS):
                return False
            self.step_index = index
        elif key == "step":                      # the next step, the smallest again after the largest
            self.step_index = (self.step_index + 1) % len(snapping.GRID_STEPS)
        else:
            raise ValueError(f"unknown key '{key}'")
        return True

    def refresh(self):
        """Read the values of the object again (it may have been moved or edited elsewhere); the picked value stays picked."""
        self.fields = self.target.fields()
        self.selected = min(self.selected, len(self.fields) - 1)

    def commit(self):
        """Keep the changes made since the last commit as one undo step."""
        if self.dirty:
            self.dirty = False
            self.target.commit()
