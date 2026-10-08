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
"""The value module: the panels of the values carousel, which replaces the palette carousel while an editable object is selected
(docs/ux-design.md, Value panels). No Coin, OpenXR or FreeCAD imports.

The values carousel has two kinds of panels. The **Value** panel is fixed: it stands at the top of every side and holds the readout
of the picked value (its name, and the number or the text being typed, large; it is the text field of the keys), the slider of that
value and the slider of the step. The panels under it can be rearranged like the panels of the palette: **Values** lists every value
of the object (a press picks it), **Number pad** holds the digits with Del, Enter and Unit; **Keys** the rest of the expression
(0, the point, the operators, brackets), the selector of the picked value (Previous value, "Value 2 of 6", Next value) and Clear;
**Variables** the named lengths of the document (eight at a time, a press types the name into the expression) with the keys that
make a variable of the picked value and free it again. The title of the Value panel names the object. There is no editing mode:
selecting another object rebinds the panels, clearing the selection removes the carousel, and every gesture (a slider drag, one
Enter, one push of the stick) is its own undo step.

The slider of the value is **focused** when the pointer comes near it (the tip within a hand's breadth in front of the panel, the
laser over the row): as long as it stays focused the stick of the tool hand steps the picked value, up and down, by one step, while
the tool's own options keep the stick the rest of the time. A slider changes its value only when its bar is pressed and dragged.
`ValueModule` holds the `core.values.ValueEditor` of the selected object and turns what the carousel reports (a face pressed, a
slider dragged, the value slider focused) into editor calls; the controller shows the panels and swaps the carousels."""

import math
from dataclasses import dataclass, field
from typing import List, Optional

from freecad.BlocksCAD.core import snapping, units
from freecad.BlocksCAD.core.values import VALUE_STEPS, ValueEditor, pretty_expression
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui.layout import Face, Layout, Page
from freecad.BlocksCAD.ui.options import FIRST_REPEAT, PUSH_OFF, PUSH_ON, REPEAT

ROW_CHARS = 36                         # the label line of the readout is cut after this many characters
VARIABLE_REFRESH = 0.5                 # seconds between two readings of the variables of the document
FOCUS_HOLD = 0.6                       # seconds the value slider stays focused after the pointer has left it, so the thumb can work the stick
READOUT, VALUE_SLIDER, STEP_SLIDER = "val.readout", "val.slider", "val.step"
SLIDER_IDS = (VALUE_SLIDER, STEP_SLIDER)
PREV, WHICH, NEXT = "val.prev", "val.which", "val.next"
VARIABLES = 8                          # variables shown on the Variables panel at a time
VARIABLE_IDS = tuple(f"var.{i}" for i in range(VARIABLES))
VARIABLE_GROUP = "var.group"
ITEMS = 12                             # faces of the Values panel; with more values the last one is "More values"
ITEM_IDS = tuple(f"val.item.{i}" for i in range(ITEMS))
PAGE_VALUE, PAGE_LIST, PAGE_PAD, PAGE_KEYS, PAGE_VARIABLES = "Value", "Values", "Number pad", "Keys", "Variables"
PAGE_NAMES = (PAGE_VALUE, PAGE_LIST, PAGE_PAD, PAGE_KEYS, PAGE_VARIABLES)
MOVABLE_NAMES = PAGE_NAMES[1:]         # the panels the user can rearrange: the Value panel is fixed at the top of every side
TYPED_CHARS = 30                       # the readout shows at most this many characters of what is typed

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
    "key.makevar": ("Make variable", "makevar", "Make a variable of the picked value (or of what is typed) and bind the value to it"),
    "key.unbind": ("Unbind", "unbind", "Free the picked value from its variable or expression; it keeps its number"),
}
NO_TOOLTIP = frozenset([*(f"key.{d}" for d in "0123456789"), "key.point", "key.minus", "key.plus", "key.times", "key.divide", "key.open", "key.close"])   # symbols that need no words
VALUE_SLOTS = [READOUT, None, None, None, VALUE_SLIDER, None, None, None, STEP_SLIDER, None, None, None]
PAD_SLOTS = ["key.7", "key.8", "key.9", "key.delete", "key.4", "key.5", "key.6", "key.enter", "key.1", "key.2", "key.3", "key.unit"]
KEY_SLOTS = ["key.0", "key.point", "key.minus", "key.plus", "key.times", "key.divide", "key.open", "key.close",
             PREV, WHICH, NEXT, "key.clear"]
VARIABLE_SLOTS = [*VARIABLE_IDS, "key.makevar", "key.unbind", VARIABLE_GROUP, None]
LIST_SLOTS = list(ITEM_IDS)
WIDE_KINDS = ("slider", "readout")     # faces that take a whole row of their panel


def faces():
    """Map of face id to `layout.Face` for every face of the module."""
    result = {fid: Face(fid, label, f"values:{fid}", tip=tip) for fid, (label, _, tip) in KEYS.items()}
    result[READOUT] = Face(READOUT, "Value", f"values:{READOUT}", "readout", "The picked value, and what is typed for it")
    result[VALUE_SLIDER] = Face(VALUE_SLIDER, "Value", f"values:{VALUE_SLIDER}", "slider",
                                "Come close to use the stick, press the bar and drag to set the picked value")
    result[STEP_SLIDER] = Face(STEP_SLIDER, "Step", f"values:{STEP_SLIDER}", "slider", "Press the bar and drag to set the step of the stick and of the value slider")
    result[PREV] = Face(PREV, "Previous value", f"values:{PREV}", tip="Pick the previous value of the object")
    result[NEXT] = Face(NEXT, "Next value", f"values:{NEXT}", tip="Pick the next value of the object")
    result[WHICH] = Face(WHICH, "Value", f"values:{WHICH}", "display", "Which value of the object is picked")
    for fid in VARIABLE_IDS:
        result[fid] = Face(fid, "Variable", f"values:{fid}", tip="Type this variable into the expression")
    result[VARIABLE_GROUP] = Face(VARIABLE_GROUP, "More variables", f"values:{VARIABLE_GROUP}", tip="Show the next variables")
    for fid in ITEM_IDS:
        result[fid] = Face(fid, "Value", f"values:{fid}", tip="Pick this value")
    return result


def default_layout():
    """The panels the user can rearrange, as they stand to begin with: the Values panel alone on the front side, the keys on the next
    (the Number pad over Keys over Variables; rows count from the bottom, nearest the user)."""
    return Layout([Page(PAGE_LIST, list(LIST_SLOTS), 0, 0), Page(PAGE_VARIABLES, list(VARIABLE_SLOTS), 1, 0),
                   Page(PAGE_KEYS, list(KEY_SLOTS), 1, 1), Page(PAGE_PAD, list(PAD_SLOTS), 1, 2)])


def complete(layout):
    """A saved layout of the values carousel made fit to use: the Value panel is never part of it (it is added to every side), and a
    panel that is missing comes back on a side of its own."""
    pages = [p for p in layout.pages if p.name in MOVABLE_NAMES]
    present = {p.name for p in pages}
    for page in default_layout().pages:
        if page.name not in present:
            pages.append(Page(page.name, page.slots))          # no side: the panel gets one of its own
    return Layout(pages)


def shown_layout(layout):
    """The layout the carousel draws for the movable `layout`: the same panels, and above the top row of every side a Value panel
    (page indexes from `len(layout.pages)` on, in the order of the sides)."""
    pages = list(layout.pages)
    for side, rows in enumerate(layout.sides()):
        pages.append(Page(PAGE_VALUE, list(VALUE_SLOTS), side, len(rows)))
    return Layout(pages)


def load_layout(known_faces, path=None):
    """The user's saved layout of the values carousel, or the default one when there is none or it cannot be read."""
    return complete(lay.load_layout(default_layout(), known_faces, path or user_layout_path()))


def user_layout_path():
    return lay.user_layout_path("values_layout")


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
        self.variable_group = 0             # the Variables panel shows the variables 8 * variable_group and the next seven
        self.item_group = 0                 # the Values panel shows the values from page_size * item_group on
        self._seen_selected = None          # the picked value the Values panel last followed
        self._variable_age = 0.0
        self.faces = faces()
        self.step = 10.0                    # the step of the stick and the value slider, kept from one object to the next
        self._ranges = {}                   # value index -> (lowest, highest) of the value slider while that value is picked
        self._range_step = None
        self._focus = False                 # the value slider has the pointer close, or had it a moment ago
        self._focus_age = 0.0
        self._dir = 0                       # direction of the stick up and down: 1, -1 or 0
        self._repeat = 0.0
        self._pending_message = None

    @property
    def is_open(self):
        return self.editor is not None

    @property
    def engaged(self):
        """The value slider is focused: the stick of the tool hand belongs to the value panels."""
        return self.editor is not None and self._focus and self._focus_age < FOCUS_HOLD

    def open(self, editor, key=None):
        """Bind the panels to the editor of an object; `key` names the object."""
        self.close()
        self.editor, self.key = editor, key
        self.variable_group, self.item_group, self._seen_selected, self._ranges, self._range_step = 0, 0, None, {}, None
        self._focus, self._dir = False, 0
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

    def _range_text(self, low, high):
        """The ends of the track as text: "0 to 200 mm", "-100 to 100 mm"."""
        unit = units.unit_for(self.editor.system, high)
        return f"{units.format_number(low / unit.mm)} to {units.format_length(high, self.editor.system, unit)}"

    def slider_states(self):
        """face id -> (position along the track 0 to 1, text, picked) of the value slider (the track runs over the values it can take
        and its text says where it begins and ends) and of the step slider."""
        editor = self.editor
        low, high = self._ranges[editor.selected]
        fraction = min(max((editor.field.value - low) / (high - low), 0.0), 1.0)
        step = editor.step_index / (len(VALUE_STEPS) - 1)
        return {VALUE_SLIDER: (fraction, self._range_text(low, high), True),
                STEP_SLIDER: (step, f"Step {units.format_length(editor.step, editor.system)}", False)}

    def readouts(self):
        """face id -> (small line, large line, typing) of the readout: the name of the picked value (and the expression it is bound to)
        over its number, or while text is typed the text with a cursor, which Enter applies."""
        editor = self.editor
        picked = editor.field
        if editor.entry is not None:
            typed = editor.entry if len(editor.entry) <= TYPED_CHARS else "..." + editor.entry[-(TYPED_CHARS - 3):]
            return {READOUT: (f"{picked.label}, Enter applies", typed + "|", True)}
        small = picked.label
        if picked.expression:
            small = f"{small} = {pretty_expression(picked.expression)}"
            small = small if len(small) <= ROW_CHARS else small[:ROW_CHARS - 3] + "..."
        return {READOUT: (small, editor.text_of(picked), False)}

    def set_focus(self, face_id):
        """The pointer is close to the slider `face_id`: for the value slider the stick works on the picked value for a while."""
        if face_id == VALUE_SLIDER:
            self._focus, self._focus_age = True, 0.0

    def drag(self, face_id, along):
        """A slider was dragged to `along` (0 to 1) of its track: the value slider sets the picked value to the nearest step, the step
        slider takes the nearest of the steps. Returns whether it changed."""
        along = min(max(along, 0.0), 1.0)
        if face_id == STEP_SLIDER:
            return self.editor.set_step(round(along * (len(VALUE_STEPS) - 1)))
        if face_id != VALUE_SLIDER:
            return False
        low, high = self._ranges[self.editor.selected]
        return self.editor.set_value(self.editor.selected, snapping.snap(low + along * (high - low), self.editor.step))

    def end_drag(self):
        """A slider was let go: what the drag changed is one undo step."""
        if self.editor is not None:
            self.editor.commit()

    # the keys and the labels
    def labels(self):
        """Face id -> the text of the faces that show a value."""
        if self.editor is None:
            return {}
        count = len(self.editor.fields)
        labels = {PREV: "Previous value" if count > 1 else "-", NEXT: "Next value" if count > 1 else "-",
                  WHICH: f"Value {self.editor.selected + 1} of {count}"}
        for slot, fid in enumerate(VARIABLE_IDS):
            entry = self.variable_at(slot)
            labels[fid] = "-" if entry is None else f"{entry[0]} {units.format_length(entry[1], self.editor.system)}"
        for slot, fid in enumerate(ITEM_IDS):
            index = self.item_at(slot)
            if index is None:
                labels[fid] = "More values" if self._paged and slot == ITEMS - 1 else "-"
            else:
                field = self.editor.fields[index]
                labels[fid] = f"{field.label} {self.editor.text_of(field)}"
        return labels

    @property
    def _paged(self):
        """There are more values than the Values panel has faces: its last face then shows the next page of values."""
        return self.editor is not None and len(self.editor.fields) > ITEMS

    @property
    def page_size(self):
        return ITEMS - 1 if self._paged else ITEMS

    def item_at(self, slot):
        """Index of the value on face `slot` (0 to 11) of the Values panel, or None when the face shows none."""
        if self.editor is None or slot >= self.page_size:
            return None
        index = self.item_group * self.page_size + slot
        return index if index < len(self.editor.fields) else None

    def picked_actions(self):
        """Actions of the faces that are lit: the face of the Values panel that shows the picked value."""
        if self.editor is None:
            return frozenset()
        slot = self.editor.selected - self.item_group * self.page_size
        return frozenset([self.faces[ITEM_IDS[slot]].action]) if 0 <= slot < self.page_size else frozenset()

    def variable_at(self, slot):
        """(name, millimetres) of the variable on slot `slot` (0 to 7) of the Variables panel, or None when it shows none."""
        if self.editor is None:
            return None
        index = self.variable_group * VARIABLES + slot
        return self.editor.variables[index] if index < len(self.editor.variables) else None

    def titles(self):
        """Page name -> title bar text for the panels of the module: the Value panel names the object."""
        return {} if self.editor is None else {PAGE_VALUE: self.editor.target.title}

    def activate(self, face_id):
        """A face of the module was pressed; returns whether something changed."""
        editor = self.editor
        if editor is None:
            return False
        if face_id in (PREV, NEXT):
            return editor.select_next(1 if face_id == NEXT else -1)
        if face_id == VARIABLE_GROUP:
            count = max(1, math.ceil(len(editor.variables) / VARIABLES))
            self.variable_group = (self.variable_group + 1) % count
            return True
        if face_id in ITEM_IDS:
            slot = ITEM_IDS.index(face_id)
            if self._paged and slot == ITEMS - 1:
                self.item_group = (self.item_group + 1) % math.ceil(len(editor.fields) / self.page_size)
                return True
            index = self.item_at(slot)
            return index is not None and editor.select(index)
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
        if editor.selected != self._seen_selected:         # the Values panel shows the page of the picked value
            self._seen_selected = editor.selected
            self.item_group = editor.selected // self.page_size
        self.item_group = min(self.item_group, max(0, math.ceil(len(editor.fields) / self.page_size) - 1))
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
