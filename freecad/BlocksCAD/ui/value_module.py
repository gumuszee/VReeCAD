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
"""The value module: four panels on a carousel side of their own that follow the selection (docs/ux-design.md, Value panels). No
Coin, OpenXR or FreeCAD imports.

While an editable object is selected the carousel of the palette hand has one more side with four ordinary panels, so they are
pointed at, hovered and pressed with the laser or the tip like the others: **Values** holds three sliders (the values of the
object, three at a time), **Number pad** the digits with Del, Enter and Unit, **Keys** the rest (0, the point, the operators,
brackets, Clear, the step and the next three values) and **Variables** the named lengths of the document (eight at a time, a press
types the name into the expression) with the keys that make a variable of the picked value and free it again. The title of the
Values panel names the object and the title of the Number pad shows the picked value and what is being typed. There is no editing mode: selecting another object rebinds the panels, clearing
the selection removes them, and every gesture (a slider drag, one Enter, one push of the stick) is its own undo step.

A slider is **focused** when the pointer comes near it (the tip within a hand's breadth in front of the panel, the laser over the
row): that picks its value, and as long as it stays focused the stick of the tool hand steps it, up and down, by one step, while the
tool's own options keep the stick the rest of the time. A slider changes its value only when its bar is pressed and dragged.
`ValueModule` holds the `core.values.ValueEditor` of the selected object and turns what the carousel reports (a face pressed, a
slider dragged, a slider focused) into editor calls; the controller adds and removes the pages."""

import math
from dataclasses import dataclass, field
from typing import List, Optional

from freecad.BlocksCAD.core import snapping, units
from freecad.BlocksCAD.core.values import ValueEditor, pretty_expression
from freecad.BlocksCAD.ui.layout import Face, Page
from freecad.BlocksCAD.ui.options import FIRST_REPEAT, PUSH_OFF, PUSH_ON, REPEAT

ROW_CHARS = 36                         # the text of a slider row is cut after this many characters
VARIABLE_REFRESH = 0.5                 # seconds between two readings of the variables of the document
FOCUS_HOLD = 0.6                       # seconds a slider stays focused after the pointer has left it, so the thumb can work the stick
SLIDERS = 3                            # sliders on the Values panel: the rows of a panel
SLIDER_IDS = tuple(f"val.{i}" for i in range(SLIDERS))
GROUP = "key.group"
VARIABLES = 8                          # variables shown on the Variables panel at a time
VARIABLE_IDS = tuple(f"var.{i}" for i in range(VARIABLES))
VARIABLE_GROUP = "var.group"
PAGE_VALUES, PAGE_PAD, PAGE_KEYS, PAGE_VARIABLES = "Values", "Number pad", "Keys", "Variables"
PAGE_NAMES = (PAGE_VALUES, PAGE_PAD, PAGE_KEYS, PAGE_VARIABLES)
TITLE_CHARS = 34                       # the title of the Number pad shows at most this many characters of what is typed

# face id -> (label, key of the editor, tooltip)
KEYS = {
    **{f"key.{d}": (d, d, "") for d in "0123456789"},
    "key.point": (".", ".", "Decimal point"),
    "key.minus": ("-", "-", "Minus"),
    "key.plus": ("+", "+", "Plus"),
    "key.times": ("*", "*", "Times"),
    "key.divide": ("/", "/", "Divided by"),
    "key.open": ("(", "(", "Open bracket"),
    "key.close": (")", ")", "Close bracket"),
    "key.delete": ("Del", "back", "Delete the last character"),
    "key.unit": ("Unit", "unit", "Turn the unit at the end: mm, cm, m, in"),
    "key.enter": ("Enter", "enter", "Apply what is typed to the picked value"),
    "key.clear": ("Clear", "clear", "Throw away what is typed"),
    "key.step": ("Step", "step", "Step of the stick and of the sliders"),
    "key.makevar": ("Make variable", "makevar", "Make a variable of the picked value (or of what is typed) and bind the value to it"),
    "key.unbind": ("Unbind", "unbind", "Free the picked value from its variable or expression; it keeps its number"),
}
PAD_SLOTS = ["key.7", "key.8", "key.9", "key.delete", "key.4", "key.5", "key.6", "key.enter", "key.1", "key.2", "key.3", "key.unit"]
KEY_SLOTS = ["key.0", "key.point", "key.minus", "key.plus", "key.times", "key.divide", "key.open", "key.close",
             "key.step", GROUP, "key.clear", None]
VARIABLE_SLOTS = [*VARIABLE_IDS, "key.makevar", "key.unbind", VARIABLE_GROUP, None]
VALUE_SLOTS = [SLIDER_IDS[0], None, None, None, SLIDER_IDS[1], None, None, None, SLIDER_IDS[2], None, None, None]


def faces():
    """Map of face id to `layout.Face` for every face of the module."""
    result = {fid: Face(fid, label, f"values:{fid}", tip=tip) for fid, (label, _, tip) in KEYS.items()}
    result[GROUP] = Face(GROUP, "More values", f"values:{GROUP}", tip="Show the next three values on the sliders")
    for fid in SLIDER_IDS:
        result[fid] = Face(fid, "Value", f"values:{fid}", "slider", "Come close to pick a value, press the bar and drag, or use the stick")
    for fid in VARIABLE_IDS:
        result[fid] = Face(fid, "Variable", f"values:{fid}", tip="Type this variable into the expression")
    result[VARIABLE_GROUP] = Face(VARIABLE_GROUP, "More variables", f"values:{VARIABLE_GROUP}", tip="Show the next variables")
    return result


def pages(side):
    """The four panels on carousel side `side`: Values at the bottom (nearest the user), the Number pad above it, Keys and Variables above."""
    return [Page(PAGE_VALUES, list(VALUE_SLOTS), side, 0), Page(PAGE_PAD, list(PAD_SLOTS), side, 1), Page(PAGE_KEYS, list(KEY_SLOTS), side, 2),
            Page(PAGE_VARIABLES, list(VARIABLE_SLOTS), side, 3)]


def nice_ceiling(value):
    """The smallest of 1, 2, 5, 10, 20, 50 ... that is at least `value`."""
    value = max(value, 1e-9)
    exponent = math.floor(math.log10(value))
    for mantissa in (1, 2, 5, 10):
        if mantissa * 10.0 ** exponent >= value * (1 - 1e-12):
            return mantissa * 10.0 ** exponent
    return 10.0 ** (exponent + 1)


@dataclass
class ModuleResult:
    open: bool = False                      # false when there is nothing bound or the object is gone
    message: Optional[str] = None           # text for a toast
    haptics: List[tuple] = field(default_factory=list)       # (hand, amplitude, duration_s)


class ValueModule:
    def __init__(self, tool_hand=1):
        self.hand = tool_hand
        self.editor: Optional[ValueEditor] = None
        self.key = None                     # what the editor is bound to (the selected object)
        self.group = 0                      # the sliders show the values 3 * group to 3 * group + 2
        self.variable_group = 0             # the Variables panel shows the variables 8 * variable_group and the next seven
        self._variable_age = 0.0
        self.faces = faces()
        self.step = 10.0                    # the step of the stick and the sliders, kept from one object to the next
        self._ranges = {}                   # value index -> (lowest, highest) of its slider
        self._range_step = None
        self._focus = None                  # the slider that has the pointer close, or had it a moment ago
        self._focus_age = 0.0
        self._dir = 0                       # direction of the stick up and down: 1, -1 or 0
        self._repeat = 0.0
        self._pending_message = None

    @property
    def is_open(self):
        return self.editor is not None

    @property
    def engaged(self):
        """A slider is focused: the stick of the tool hand belongs to the value panels."""
        return self.editor is not None and self._focus is not None and self._focus_age < FOCUS_HOLD

    def open(self, editor, key=None):
        """Bind the panels to the editor of an object; `key` names the object."""
        self.close()
        self.editor, self.key = editor, key
        self.group, self.variable_group, self._ranges, self._range_step = 0, 0, {}, None
        self._focus, self._dir = None, 0
        self._refresh_ranges(False)

    def close(self):
        """Unbind the panels; changes that were not kept yet are kept."""
        if self.editor is not None:
            try:
                self.editor.commit()
            except Exception as error:      # the object may be gone: there is nothing to keep
                print(f"BlocksCAD: cannot keep the last edit: {error}")
            self.step = self.editor.step
            self.editor, self.key = None, None

    # the sliders
    @property
    def groups(self):
        return max(1, math.ceil(len(self.editor.fields) / SLIDERS)) if self.editor is not None else 1

    def slider_field(self, slider):
        """Index of the value that slider `slider` (0 to 2) shows, or None when it shows none."""
        if self.editor is None:
            return None
        index = self.group * SLIDERS + slider
        return index if index < len(self.editor.fields) else None

    def _range_for(self, index):
        value, step = self.editor.fields[index], self.editor.step
        hi = nice_ceiling(max(2.0 * abs(value.value), 10.0 * step))
        return (-hi if value.low is None else 0.0), hi

    def _refresh_ranges(self, dragging):
        """Give every value a slider range: from 0 (a size) or from minus the top (a position) to a round number of at least twice the
        value and ten steps. A range is only ever recomputed while no slider is dragged, so the handle does not jump under the hand."""
        editor = self.editor
        if self._range_step != editor.step and not dragging:
            self._ranges, self._range_step = {}, editor.step
        for index, value in enumerate(editor.fields):
            span = self._ranges.get(index)
            outside = span is not None and not span[0] - 1e-9 <= value.value <= span[1] + 1e-9
            if span is None or (outside and not dragging):
                self._ranges[index] = self._range_for(index)

    def slider_states(self):
        """face id -> (position along the track 0 to 1, text, picked) of the three sliders."""
        states = {}
        for slider, fid in enumerate(SLIDER_IDS):
            index = self.slider_field(slider)
            if index is None:
                states[fid] = (0.0, "-", False)
                continue
            value = self.editor.fields[index]
            low, high = self._ranges[index]
            fraction = min(max((value.value - low) / (high - low), 0.0), 1.0)
            text = f"{value.label} {self.editor.text_of(value)}"
            if value.expression:
                text = f"{text} = {pretty_expression(value.expression)}"
                text = text if len(text) <= ROW_CHARS else text[:ROW_CHARS - 3] + "..."
            states[fid] = (fraction, text, index == self.editor.selected)
        return states

    def set_focus(self, slider):
        """The pointer is close to slider `slider` (0 to 2): its value is picked and the stick works on it for a while."""
        index = self.slider_field(slider)
        if index is None:
            return
        self._focus, self._focus_age = slider, 0.0
        self.editor.select(index)

    def drag(self, slider, along):
        """A slider was dragged to `along` (0 to 1) of its track: set the value to the nearest step. Returns whether it changed."""
        index = self.slider_field(slider)
        if index is None:
            return False
        low, high = self._ranges[index]
        return self.editor.set_value(index, snapping.snap(low + min(max(along, 0.0), 1.0) * (high - low), self.editor.step))

    def end_drag(self):
        """A slider was let go: what the drag changed is one undo step."""
        if self.editor is not None:
            self.editor.commit()

    # the keys and the titles
    def labels(self):
        """Face id -> the text of the faces that show a value."""
        if self.editor is None:
            return {}
        labels = {"key.step": f"Step {units.format_length(self.editor.step, self.editor.system)}"}
        for slot, fid in enumerate(VARIABLE_IDS):
            entry = self.variable_at(slot)
            labels[fid] = "-" if entry is None else f"{entry[0]} {units.format_length(entry[1], self.editor.system)}"
        return labels

    def variable_at(self, slot):
        """(name, millimetres) of the variable on slot `slot` (0 to 7) of the Variables panel, or None when it shows none."""
        if self.editor is None:
            return None
        index = self.variable_group * VARIABLES + slot
        return self.editor.variables[index] if index < len(self.editor.variables) else None

    def titles(self):
        """Page name -> title bar text for the panels of the module."""
        if self.editor is None:
            return {}
        editor = self.editor
        picked = editor.field
        if editor.entry is not None:
            typed = editor.entry[-TITLE_CHARS:] if len(editor.entry) <= TITLE_CHARS else "..." + editor.entry[-(TITLE_CHARS - 3):]
            text = f"{picked.label}: {typed}|"
        else:
            text = f"{picked.label}: {editor.text_of(picked)}"
        return {PAGE_VALUES: editor.target.title, PAGE_PAD: text}

    def activate(self, face_id):
        """A face of the module was pressed; returns whether something changed."""
        editor = self.editor
        if editor is None:
            return False
        if face_id == GROUP:
            self.group = (self.group + 1) % self.groups
            return editor.select(self.group * SLIDERS) or True
        if face_id == VARIABLE_GROUP:
            count = max(1, math.ceil(len(editor.variables) / VARIABLES))
            self.variable_group = (self.variable_group + 1) % count
            return True
        if face_id in VARIABLE_IDS:
            entry = self.variable_at(VARIABLE_IDS.index(face_id))
            return entry is not None and editor.key(f"var:{entry[0]}")
        if face_id not in KEYS:
            return False
        changed = editor.key(KEYS[face_id][1])
        self._pending_message = editor.message or self._pending_message
        self.variable_group = min(self.variable_group, max(0, math.ceil(len(editor.variables) / VARIABLES) - 1))
        return changed

    # the stick
    def _nudge(self, direction, result):
        if self.editor.nudge(direction):
            result.haptics.append((self.hand, 0.12, 0.012))
        elif self.editor.message:
            result.haptics.append((self.hand, 0.5, 0.05))

    def _stick(self, frame, hand, result, active):
        """Up and down step the picked value while a slider is focused; a push that ends keeps what it changed as one undo step."""
        x, y = hand.stick
        push = 0.0 if (not active or any(h.down("grip") for h in frame.hands)) else y
        if abs(push) <= PUSH_OFF:
            direction = 0
        elif abs(push) >= PUSH_ON:
            direction = 1 if push > 0 else -1
        else:
            direction = self._dir
        if direction != self._dir:
            self._dir = direction
            if direction:
                self._repeat = FIRST_REPEAT
                self._nudge(direction, result)
            else:
                self.editor.commit()
        elif direction:
            self._repeat -= frame.dt
            if self._repeat <= 0.0:
                self._repeat += REPEAT
                self._nudge(direction, result)

    def update(self, frame, dragging=False, blocked=False) -> ModuleResult:
        """One frame: the stick of the tool hand and the object's values read again. `dragging` says a slider is being dragged,
        `blocked` that the tool is busy with the document (a grab) and the panels must not open a transaction."""
        result = ModuleResult()
        editor = self.editor
        if editor is None:
            return result
        try:
            editor.refresh()
        except Exception:                   # the object is gone (deleted, or its document closed)
            self.editor, self.key = None, None
            return result
        self._focus_age += frame.dt
        self._variable_age += frame.dt
        if self._variable_age >= VARIABLE_REFRESH:
            self._variable_age = 0.0
            try:
                editor.refresh_variables()
            except Exception:                   # the document is going away
                pass
        if blocked:
            editor.commit()
        self._stick(frame, frame.hands[self.hand], result, self.engaged and not blocked)
        self._refresh_ranges(dragging)
        result.message, editor.message = editor.message or self._pending_message, None
        self._pending_message = None
        result.open = True
        return result
