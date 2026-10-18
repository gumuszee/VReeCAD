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
picked, the text being typed, and the step of the stick and the sliders (one of `VALUE_STEPS`, from 0.01 mm to 100 mm). The stick up and
down changes the picked value by whole steps, the keypad types an expression that is applied with Enter. Every change goes to the target at once, so the object follows in the scene; the
target keeps the changes of one gesture (a slider drag, a push of the stick, one Enter) in one transaction that `commit` keeps as
one undo step. There is no editing mode: the editor follows whatever object is selected and is simply dropped with it."""

import math
import re
from dataclasses import dataclass
from typing import List, Optional

from freecad.VReeCAD.core import units

UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
UNIT_CYCLE = ("mm", "cm", "m", "in")       # the unit key turns the unit at the end of the text through these
VALUE_STEPS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)   # millimetres: the steps of the stick and of the sliders
ENTRY_KEYS = frozenset("0123456789.+-*/()")
MAX_ENTRY = 40                              # characters

_TOKEN = re.compile(r"\s*(?:(\d+\.?\d*|\.\d+)|([a-zA-Z_][a-zA-Z_0-9]*)|(.))")
SHEET = "Variables"                         # the spreadsheet that holds the variables of a document (`cad/variables.py`)
_NAME = re.compile(r"[^a-z0-9_]+")


def default_unit_mm(system):
    """Millimetres of the unit that a number without a unit is in: the unit of the document's measurement system."""
    return {units.IMPERIAL.name: UNITS["in"], units.METRIC_CM.name: UNITS["cm"], units.METRIC_M.name: UNITS["m"]}.get(system.name, 1.0)


def variable_name(hint, taken):
    """A name for a new variable from `hint` (a label such as "Radius 1"): lower case, letters, digits and underscores, starting with a
    letter, never a unit and never one of `taken`; a number is added to make it unique."""
    base = _NAME.sub("_", hint.lower()).strip("_") or "value"
    if not base[0].isalpha():
        base = "v_" + base
    if base in UNITS:
        base += "_value"
    name, number = base, 1
    while name in taken:
        number += 1
        name = f"{base}{number}"
    return name


def _balanced(text):
    depth = 0
    for char in text:
        depth += (char == "(") - (char == ")")
        if depth < 0:
            return False
    return depth == 0


def pretty_expression(expression):
    """An expression as the panels show it: without the sheet name, the outer brackets and the unit factors (`(Variables.width * 2)` is
    `width * 2` and `(10 * 1 mm)` is `10 mm`)."""
    text = expression.replace(SHEET + ".", "")
    for pattern in (r"\(([\d.]+) \* 1 (mm|cm|m|in|ft)\)", r"\b([\d.]+) \* 1 (mm|cm|m|in|ft)\b"):   # FreeCAD may drop the brackets
        text = re.sub(pattern, r"\1 \2", text)
    while text.startswith("(") and text.endswith(")") and _balanced(text[1:-1]):
        text = text[1:-1]
    return text


def single_variable(expression):
    """The name of the variable when `expression` is nothing but a variable (`Variables.width`), else None."""
    match = re.fullmatch(r"\(*" + re.escape(SHEET) + r"\.([A-Za-z_][A-Za-z_0-9]*)\)*", expression.strip())
    return match.group(1) if match else None


def _num(number):
    return f"{number:.12g}"


class _Parser:
    """Recursive descent over the tokens; a value is (number, dimension, expression) with dimension 1 for a length (the number is in
    millimetres) and 0 for a plain number. The expression is the same value as text for FreeCAD (`Variables.width * 2`), with every
    length written as a number times a unit so that FreeCAD checks the units; `variables` maps the names that may be used to their
    values in millimetres, and `used` collects the names that were."""

    def __init__(self, text, default_mm=1.0, variables=None):
        self.default_mm = default_mm
        self.variables = variables
        self.used = set()
        self.tokens = []
        position = 0
        text = text.strip()
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None:
                break
            number, word, other = match.groups()
            self.tokens.append(("n", float(number)) if number else ("w", word) if word else ("o", other))
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

    def _plain_to_length(self, value):
        return (value[0] * self.default_mm, 1, f"({value[2]} * {_num(self.default_mm)} mm)")

    def expression(self):
        value = self.term()
        while self.peek() in (("o", "+"), ("o", "-")):
            symbol = self.take()[1]
            sign = 1.0 if symbol == "+" else -1.0
            other = self.term()
            if value[1] != other[1]:       # a plain number next to a length is in the default unit
                value, other = [self._plain_to_length((n, d, e)) if d == 0 else (n, d, e) for n, d, e in (value, other)]
            value = (value[0] + sign * other[0], value[1], f"({value[2]} {symbol} {other[2]})")
        return value

    def term(self):
        value = self.factor()
        while self.peek() in (("o", "*"), ("o", "/")):
            symbol = self.take()[1]
            other = self.factor()
            if symbol == "*":
                if value[1] and other[1]:
                    raise ValueError("A length times a length is not a length")
                value = (value[0] * other[0], value[1] + other[1], f"({value[2]} * {other[2]})")
            else:
                if other[1] > value[1]:
                    raise ValueError("A number divided by a length is not a length")
                if other[0] == 0:
                    raise ValueError("Division by zero")
                value = (value[0] / other[0], value[1] - other[1], f"({value[2]} / {other[2]})")
        return value

    def factor(self):
        kind, text = self.peek()
        if (kind, text) in (("o", "-"), ("o", "+")):
            self.take()
            number, dimension, expression = self.factor()
            return (-number, dimension, f"(-{expression})") if text == "-" else (number, dimension, expression)
        return self.atom()

    def atom(self):
        kind, text = self.take()
        if kind == "n":
            value = (text, 0, _num(text))
        elif (kind, text) == ("o", "("):
            value = self.expression()
            if self.take() != ("o", ")"):
                raise ValueError("Missing )")
        elif kind == "w" and self.variables is not None and text in self.variables:
            self.used.add(text)
            return (self.variables[text], 1, f"{SHEET}.{text}")
        elif kind == "w" and self.variables is not None and text.lower() not in UNITS:
            raise ValueError(f"Unknown variable '{text}'")
        elif kind is None:
            raise ValueError("The expression ends too early")
        else:
            raise ValueError(f"Cannot read '{text}'")
        if self.peek()[0] == "w":
            word = self.take()[1].lower()
            if word not in UNITS:
                raise ValueError(f"Unknown unit '{word}'")
            if value[1]:
                raise ValueError("A length cannot have a unit twice")
            value = (value[0] * UNITS[word], 1, f"({value[2]} * 1 {word})")
        return value


def evaluate_bound(text, default_mm=1.0, variables=None):
    """(length in millimetres, expression) of what `text` types, with `variables` (name to millimetres) usable by name. The expression
    is the text for FreeCAD that binds a property to it, or None when no variable is used (the length is then just a number).
    ValueError with a short message that fits a toast when the text cannot be read."""
    parser = _Parser(text, default_mm, variables)
    number, dimension, expression = parser.parse()
    if dimension not in (0, 1):
        raise ValueError("That is not a length")
    if dimension == 0:
        number, expression = number * default_mm, f"({expression} * {_num(default_mm)} mm)"
    if not math.isfinite(number):
        raise ValueError("That number is too large")
    return number, (expression if parser.used else None)


def evaluate(text, default_mm=1.0):
    """The length in millimetres that `text` types (a plain number is in the unit of `default_mm` millimetres); ValueError with a
    short message that fits a toast when the text cannot be read."""
    return evaluate_bound(text, default_mm)[0]


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
    expression: Optional[str] = None      # the expression of FreeCAD that binds the value (`Variables.width * 2`), None for a plain number


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

    # variables (docs/ux-design.md, Variables); a target without them leaves these as they are
    def variables(self) -> List[tuple]:
        """(name, millimetres) of every variable of the document."""
        return []

    def bind(self, name, expression, value):
        """Bind the field `name` to the expression (whose value is `value`); ValueError with a short message when that is not possible."""
        raise ValueError("Variables are not available")

    def unbind(self, name):
        """Free the field `name` from its expression; it keeps the value it has."""

    def make_variable(self, name, value):
        """Add the variable `name` with `value` (millimetres) to the document."""
        raise ValueError("Variables are not available")


def step_up(value, step):
    """The next multiple of `step` above `value` (a value that is on the grid goes one step up)."""
    return (math.floor(value / step + 1e-9) + 1) * step


def step_down(value, step):
    """The next multiple of `step` below `value`."""
    return (math.ceil(value / step - 1e-9) - 1) * step


class ValueEditor:
    """The state of the value panels for one `ValueTarget`. Keys: the characters of `ENTRY_KEYS`, "back", "clear", "unit", "enter"
    (apply the typed text and keep it). `message` is the last thing to tell the
    user (None when everything went well); `dirty` says there are changes that `commit` has not kept yet."""

    def __init__(self, target, system=units.METRIC_MM, step=10.0):
        self.target = target
        self.system = system
        self.default_mm = default_unit_mm(system)
        self.fields = target.fields()
        self.selected = 0
        self.entry = None              # the text being typed, None when nothing is
        self.step_index = min(range(len(VALUE_STEPS)), key=lambda i: abs(math.log(VALUE_STEPS[i] / step)))
        self.message = None
        self.dirty = False             # a value was changed and not kept yet
        self.variables = target.variables()      # (name, millimetres) of the variables that an expression may use

    @property
    def step(self):
        return VALUE_STEPS[self.step_index]

    @property
    def field(self):
        return self.fields[self.selected]

    def text_of(self, field):
        """The value as text; a zero is in the unit of the system that suits a length of 100 mm (not in micrometres)."""
        unit = units.unit_for(self.system, 100.0) if field.value == 0 else None
        return units.format_length(field.value, self.system, unit, self.step)

    def select(self, index):
        """Pick a value (clamped); typing starts again."""
        index = min(max(index, 0), len(self.fields) - 1)
        if index != self.selected:
            self.selected, self.entry = index, None
            return True
        return False

    def select_next(self, direction):
        """Pick the next (+1) or previous (-1) value, round the ends; returns whether another value is picked."""
        return self.select((self.selected + direction) % len(self.fields))

    def set_step(self, index):
        """Choose the step `VALUE_STEPS[index]` (clamped); returns whether it changed."""
        index = min(max(index, 0), len(VALUE_STEPS) - 1)
        changed = index != self.step_index
        self.step_index = index
        return changed

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
            value, expression = evaluate_bound(self.entry, self.default_mm, dict(self.variables))
        except ValueError as error:
            self.message = str(error)
            return False
        self.entry = None
        if expression is None:
            self._apply(value)
        else:
            self._bind(expression, value)
        return True

    def _bind(self, expression, value):
        """Bind the picked value to an expression that uses variables; returns whether the object took it."""
        field = self.field
        if field.low is not None and value < field.low - 1e-9:
            self.message = f"{field.label} cannot be that small"
            return False
        try:
            self.target.bind(field.name, expression, value)
        except ValueError as error:
            self.message = str(error)
            return False
        self.fields = self.target.fields()
        self.dirty = True
        self.message = f"{field.label} = {pretty_expression(expression)}"
        return True

    def _make_variable(self):
        """Turn the picked value (or what is typed) into a variable and bind the value to it."""
        field = self.field
        if self.entry is None and field.expression is not None and single_variable(field.expression) is not None:
            self.message = f"{field.label} is bound to {single_variable(field.expression)} already"
            return False
        value = field.value
        if self.entry is not None:
            try:
                value, expression = evaluate_bound(self.entry, self.default_mm, dict(self.variables))
            except ValueError as error:
                self.message = str(error)
                return False
            if expression is not None:
                self.message = "Type a plain value to make a variable"
                return False
        if field.low is not None and value < field.low - 1e-9:
            self.message = f"{field.label} cannot be that small"
            return False
        hint = field.label if len(field.label) > 1 else "position " + field.label
        name = variable_name(hint, {n for n, _ in self.variables})
        try:
            self.target.make_variable(name, value)
            self.target.bind(field.name, f"{SHEET}.{name}", value)
        except ValueError as error:
            self.target.cancel()
            self.dirty = False
            self.message = str(error)
            return False
        self.entry = None
        self.variables = self.target.variables()
        self.fields = self.target.fields()
        self.dirty = True
        self.message = f"Variable {name} = {self.text_of(self.field)}"
        return True

    def _unbind(self):
        field = self.field
        if field.expression is None:
            self.message = f"{field.label} is not bound"
            return False
        self.target.unbind(field.name)
        self.fields = self.target.fields()
        self.dirty = True
        self.message = f"{field.label} is a number again"
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
        elif key.startswith("var:"):
            name = key[4:]
            if name not in dict(self.variables):
                return False
            self.entry = self.entry or ""
            if len(self.entry) + len(name) > MAX_ENTRY:
                return False
            if self.entry and (self.entry[-1].isalnum() or self.entry[-1] == "_"):
                self.entry += " "
            self.entry += name
        elif key == "makevar":
            self._make_variable()
            self.commit()
        elif key == "unbind":
            self._unbind()
            self.commit()
        else:
            raise ValueError(f"unknown key '{key}'")
        return True

    def refresh(self):
        """Read the values of the object again (it may have been moved or edited elsewhere); the picked value stays picked."""
        self.fields = self.target.fields()
        self.selected = min(self.selected, len(self.fields) - 1)

    def refresh_variables(self):
        """Read the variables of the document again (they may have been edited elsewhere)."""
        self.variables = self.target.variables()

    def commit(self):
        """Keep the changes made since the last commit as one undo step."""
        if self.dirty:
            self.dirty = False
            self.target.commit()
