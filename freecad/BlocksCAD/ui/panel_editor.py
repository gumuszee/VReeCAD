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
"""The panel editor: rename a panel and give it a colour (docs/ux-design.md, Panel editor). No Coin, OpenXR or FreeCAD imports.

OpenXR has no keyboard, so the editor is a carousel of its own made of ordinary panels, wider than the usual ones because panels stand
next to each other: a keyboard of three panels in a row (A to L, M to X, Y to 9, so that every row of keys reads across the three), over
it the **Name** panel (the text field, space, delete, clear, case, OK and Cancel) and the **Colour** panel (Auto and eleven hues). The
panels are tinted with the hue that is chosen, so the colour is seen before OK. `PanelEditor` holds what is typed and chosen and
turns a pressed face into a change; the controller shows the pages and applies the result to the layout."""

from dataclasses import dataclass
from typing import Optional

from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui.layout import Face, Layout, Page

NAME_LIMIT = 16                         # characters of a name: it has to fit the title bar of a panel
READOUT = "ed.readout"
KEY_ROWS = ("ABCDEFGHIJKL", "MNOPQRSTUVWX", "YZ0123456789")      # the keyboard, three panels of four keys across
HUES = (("Auto", None), ("Green", 0.38), ("Rose", 0.92), ("Ochre", 0.11), ("Violet", 0.68), ("Teal", 0.50), ("Lime", 0.30),
        ("Red", 0.02), ("Blue", 0.62), ("Purple", 0.78), ("Orange", 0.06), ("Mint", 0.44))
HUE_IDS = tuple(f"ed.hue.{i}" for i in range(len(HUES)))
PAGE_KEYS = ("A to L", "M to X", "Y to 9")
PAGE_NAME, PAGE_COLOUR = "Name", "Colour"
PAGE_NAMES = PAGE_KEYS + (PAGE_NAME, PAGE_COLOUR)
SPACE, BACK, CLEAR, CASE, OK, CANCEL = "ed.space", "ed.back", "ed.clear", "ed.case", "ed.ok", "ed.cancel"
NAME_SLOTS = [READOUT, None, None, None, SPACE, BACK, CLEAR, CASE, OK, CANCEL, None, None]


def key_id(char):
    return f"ed.key.{char.lower()}"


def faces():
    """Map of face id to `layout.Face` for every face of the editor."""
    result = {}
    for row in KEY_ROWS:
        for char in row:
            result[key_id(char)] = Face(key_id(char), char, f"editor:{key_id(char)}")
    result[READOUT] = Face(READOUT, "Name", f"editor:{READOUT}", "readout", "The name of the panel")
    result[SPACE] = Face(SPACE, "Space", f"editor:{SPACE}", tip="A space")
    result[BACK] = Face(BACK, "Delete", f"editor:{BACK}", tip="Delete the last character")
    result[CLEAR] = Face(CLEAR, "Clear", f"editor:{CLEAR}", tip="Throw the name away")
    result[CASE] = Face(CASE, "Case", f"editor:{CASE}", tip="Capitals or small letters (a capital starts every word)")
    result[OK] = Face(OK, "OK", f"editor:{OK}", tip="Rename the panel and give it the colour")
    result[CANCEL] = Face(CANCEL, "Cancel", f"editor:{CANCEL}", tip="Leave the panel as it is")
    for fid, (label, _) in zip(HUE_IDS, HUES):
        result[fid] = Face(fid, label, f"editor:{fid}", tip="Give the panel this colour" if label != "Auto" else "The colour that the name gives the panel")
    return result


def pages():
    """The pages of the editor on one side: the keyboard in the bottom row, the Name and the Colour panel above it."""
    keys = []
    for k, title in enumerate(PAGE_KEYS):
        slots = [key_id(char) for row in KEY_ROWS for char in row[k * 4:(k + 1) * 4]]
        keys.append(Page(title, slots, 0, 0))
    return keys + [Page(PAGE_NAME, list(NAME_SLOTS), 0, 1), Page(PAGE_COLOUR, list(HUE_IDS), 0, 1)]


def layout(hue):
    """The layout of the editor, every panel tinted with `hue`."""
    result = Layout(pages())
    for page in result.pages:
        page.hue = hue
    return result


@dataclass
class EditorResult:
    done: bool = False                      # OK or Cancel was pressed
    applied: bool = False                   # OK: the controller applies `name` and `hue`
    message: Optional[str] = None           # text for a toast


class PanelEditor:
    def __init__(self, page, name, hue):
        """Edit the panel with index `page` that is called `name` and has the hue `hue` (None: the colour its name gives it)."""
        self.page, self.name0, self.hue0 = page, name, hue
        self.text = name
        self.hue_index = next((i for i in range(1, len(HUES)) if hue is not None and abs(HUES[i][1] - hue) < 1e-6), 0)
        self.hue = HUES[self.hue_index][1]       # a hue that is none of the choices is the colour of the name
        self.caps = False
        self.faces = faces()

    @property
    def upper(self):
        """Whether the next letter is a capital: after a space, at the start, or with the case on."""
        return self.caps or not self.text or self.text.endswith(" ")

    def preview_hue(self):
        """The hue the panels of the editor are tinted with: the chosen one, or the one the typed name gives."""
        return self.hue if self.hue is not None else lay.default_hue(self.text or self.name0)

    def result(self):
        """(name, hue) as they stand."""
        return self.text.strip(), self.hue

    def labels(self):
        """Face id -> the label of the faces that change: the letters (capitals or small), the case key."""
        labels = {}
        for row in KEY_ROWS:
            for char in row:
                labels[key_id(char)] = char.upper() if self.upper else char.lower()
        labels[CASE] = "ABC" if self.caps else "abc"
        return labels

    def readouts(self):
        return {READOUT: ("Name", self.text + "|", True)}

    def lit_actions(self):
        """The actions of the faces that are lit: the chosen colour, the case key while the capitals are on."""
        lit = {self.faces[HUE_IDS[self.hue_index]].action}
        if self.caps:
            lit.add(self.faces[CASE].action)
        return frozenset(lit)

    def activate(self, face_id) -> EditorResult:
        """A face of the editor was pressed."""
        result = EditorResult()
        if face_id.startswith("ed.key."):
            if len(self.text) >= NAME_LIMIT:
                result.message = f"A name has at most {NAME_LIMIT} characters"
                return result
            char = face_id[len("ed.key."):]
            self.text += char.upper() if (self.upper and char.isalpha()) else char
        elif face_id == SPACE:
            if self.text and not self.text.endswith(" ") and len(self.text) < NAME_LIMIT:
                self.text += " "
        elif face_id == BACK:
            self.text = self.text[:-1]
        elif face_id == CLEAR:
            self.text = ""
        elif face_id == CASE:
            self.caps = not self.caps
        elif face_id in HUE_IDS:
            self.hue_index = HUE_IDS.index(face_id)
            self.hue = HUES[self.hue_index][1]
        elif face_id == CANCEL:
            result.done = True
        elif face_id == OK:
            if not self.text.strip():
                result.message = "A name needs a letter"
            else:
                result.done = result.applied = True
        return result
