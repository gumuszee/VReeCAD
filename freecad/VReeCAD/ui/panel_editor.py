"""The panel editor: rename a panel, give it a colour and a size (docs/ux-design.md, Panel editor). No Coin, OpenXR or FreeCAD imports.

OpenXR has no keyboard, so the editor is a carousel of its own made of ordinary panels, one of them with a grid of its own (a panel may
have any number of columns and rows): a **keyboard** of 10 columns and 4 rows in the QWERTY order, ortholinear because the buttons stand on
a grid (digits, the three letter rows, and Delete, Case, Space and Clear), over it the **Name** panel (the text field, the size of the
panel being edited, OK and Cancel) and the **Colour** panel (Auto and eleven hues, each button in the colour it gives). The panels are
tinted with the hue that is chosen, so the colour is seen before OK. `PanelEditor` holds what is typed and chosen and turns a pressed
button into a change; the controller shows the pages and applies the result to the layout."""

from dataclasses import dataclass
from typing import Optional

from freecad.VReeCAD.ui import layout as lay
from freecad.VReeCAD.ui.layout import Button, Layout, Page

NAME_LIMIT = 16                         # characters of a name: it has to fit the title bar of a panel
READOUT = "ed.readout"
SPACE, BACK, CLEAR, CASE, OK, CANCEL = "ed.space", "ed.back", "ed.clear", "ed.case", "ed.ok", "ed.cancel"
SIZE_IDS = ("ed.cols_dec", "ed.cols_inc", "ed.rows_dec", "ed.rows_inc")
KEYBOARD_COLS = 10
KEY_ROWS = ("1234567890", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM")      # the keys, row by row, ortholinear
HUES = (("Auto", None), ("Green", 0.38), ("Rose", 0.92), ("Ochre", 0.11), ("Violet", 0.68), ("Teal", 0.50), ("Lime", 0.30),
        ("Red", 0.02), ("Blue", 0.62), ("Purple", 0.78), ("Orange", 0.06), ("Mint", 0.44))
HUE_IDS = tuple(f"ed.hue.{i}" for i in range(len(HUES)))
PAGE_KEYBOARD, PAGE_NAME, PAGE_COLOUR, PAGE_PREVIEW = "Keyboard", "Name", "Colour", "Preview"
PAGE_NAMES = (PAGE_KEYBOARD, PAGE_NAME, PAGE_COLOUR, PAGE_PREVIEW)
NAME_SLOTS = [READOUT, None, None, None, *SIZE_IDS, OK, CANCEL, None, None]


def key_id(char):
    return f"ed.key.{char.lower()}"


KEYBOARD = [[key_id(c) for c in row] for row in KEY_ROWS]                # the button ids of the keyboard, row by row
KEYBOARD[2].append(BACK)                                                 # the rows are filled up with the keys that are no letters
KEYBOARD[3] += [CASE, SPACE, CLEAR]


def buttons():
    """Map of button id to `layout.Button` for every button of the editor."""
    result = {}
    for row in KEY_ROWS:
        for char in row:
            result[key_id(char)] = Button(key_id(char), char, f"editor:{key_id(char)}")
    result[READOUT] = Button(READOUT, "Name", f"editor:{READOUT}", "readout", "The name of the panel")
    result[SPACE] = Button(SPACE, "Space", f"editor:{SPACE}", tip="A space")
    result[BACK] = Button(BACK, "Delete", f"editor:{BACK}", tip="Delete the last character")
    result[CLEAR] = Button(CLEAR, "Clear", f"editor:{CLEAR}", tip="Throw the name away")
    result[CASE] = Button(CASE, "Case", f"editor:{CASE}", tip="Capitals or small letters (a capital starts every word)")
    result[OK] = Button(OK, "OK", f"editor:{OK}", tip="Rename the panel, give it the colour and the size")
    result[CANCEL] = Button(CANCEL, "Cancel", f"editor:{CANCEL}", tip="Leave the panel as it is")
    for fid, label, tip in zip(SIZE_IDS, ("Cols -", "Cols +", "Rows -", "Rows +"),
                               ("One column fewer: its buttons have to be moved away first", "One more column of buttons",
                                "One row fewer: its buttons have to be moved away first", "One more row of buttons")):
        result[fid] = Button(fid, label, f"editor:{fid}", tip=tip)
    for fid, (label, hue) in zip(HUE_IDS, HUES):
        result[fid] = Button(fid, label if hue is None else "", f"editor:{fid}", tint=hue,
                           tip="Give the panel this colour" if hue is not None else "The colour that the name gives the panel")
    return result


def pages():
    """The pages of the editor on one side: the keyboard in the bottom row, the Name and the Colour panel above it."""
    keys = Page(PAGE_KEYBOARD, [f for row in KEYBOARD for f in row] + [None] * (KEYBOARD_COLS * len(KEYBOARD) - sum(len(r) for r in KEYBOARD)),
                0, 0, cols=KEYBOARD_COLS, rows=len(KEYBOARD))
    return [keys, Page(PAGE_NAME, list(NAME_SLOTS), 0, 1), Page(PAGE_COLOUR, list(HUE_IDS), 0, 1)]


def layout(hue, preview=None):
    """The layout of the editor, every panel tinted with `hue`; with a `preview` page (`PanelEditor.preview_page`) it stands above the
    Name and Colour panels."""
    result = Layout(pages() + ([preview] if preview is not None else []))
    for page in result.pages:
        if page.name != PAGE_PREVIEW:
            page.hue = hue
    return result


@dataclass
class EditorResult:
    done: bool = False                      # OK or Cancel was pressed
    applied: bool = False                   # OK: the controller applies the name, the hue and the size
    message: Optional[str] = None           # text for a toast


class PanelEditor:
    def __init__(self, page, name, hue, cols=lay.COLS, rows=lay.ROWS, slots=()):
        """Edit the panel with index `page` that is called `name`, has the hue `hue` (None: the colour its name gives it) and a grid of
        `cols` columns and `rows` rows holding `slots` (a size that would cut off a button is refused)."""
        self.page, self.name0, self.hue0 = page, name, hue
        self.text = name
        self.hue_index = next((i for i in range(1, len(HUES)) if hue is not None and abs(HUES[i][1] - hue) < 1e-6), 0)
        self.hue = HUES[self.hue_index][1]       # a hue that is none of the choices is the colour of the name
        self.caps = False
        self._probe = Page(name, list(slots), cols=cols, rows=rows)      # the panel as the editor has it: the sizes are tried on it
        self.buttons = buttons()

    @property
    def size(self):
        return self._probe.cols, self._probe.rows

    def preview_page(self):
        """The panel as it will be with the size, the colour and the buttons chosen so far: a page that stands above the editor panels
        (its buttons are for show, pressing them does nothing; its title is the name typed, see `titles`)."""
        return Page(PAGE_PREVIEW, list(self._probe.slots), 0, 2, self.preview_hue(), self._probe.cols, self._probe.rows)

    def titles(self):
        """Page name -> the text of its title bar for the pages that show something typed: the preview wears the name."""
        return {PAGE_PREVIEW: self.text or self.name0}

    def key(self):
        """What the layout of the editor depends on: it is made again when this changes."""
        return (self.preview_hue(), self.size, tuple(self._probe.slots))

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
        """Button id -> the label of the buttons that change: the letters (capitals or small), the case key."""
        labels = {}
        for row in KEY_ROWS:
            for char in row:
                labels[key_id(char)] = char.upper() if self.upper else char.lower()
        labels[CASE] = "ABC" if self.caps else "abc"
        for index, fid in enumerate(HUE_IDS):
            if index == self.hue_index and index:
                labels[fid] = "*"                                            # the chosen colour is marked: the button stays in its colour
        return labels

    def readouts(self):
        cols, rows = self.size
        return {READOUT: (f"Name, panel of {cols} x {rows} buttons", self.text + "|", True)}

    def lit_actions(self):
        """The actions of the buttons that are lit: the case key while the capitals are on."""
        return frozenset([self.buttons[CASE].action]) if self.caps else frozenset()

    def activate(self, button_id) -> EditorResult:
        """A button of the editor was pressed."""
        result = EditorResult()
        if button_id.startswith("ed.key."):
            if len(self.text) >= NAME_LIMIT:
                result.message = f"A name has at most {NAME_LIMIT} characters"
                return result
            char = button_id[len("ed.key."):]
            self.text += char.upper() if (self.upper and char.isalpha()) else char
        elif button_id == SPACE:
            if self.text and not self.text.endswith(" ") and len(self.text) < NAME_LIMIT:
                self.text += " "
        elif button_id == BACK:
            self.text = self.text[:-1]
        elif button_id == CLEAR:
            self.text = ""
        elif button_id == CASE:
            self.caps = not self.caps
        elif button_id in HUE_IDS:
            self.hue_index = HUE_IDS.index(button_id)
            self.hue = HUES[self.hue_index][1]
        elif button_id in SIZE_IDS:
            cols, rows = self.size
            cols += {"ed.cols_dec": -1, "ed.cols_inc": 1}.get(button_id, 0)
            rows += {"ed.rows_dec": -1, "ed.rows_inc": 1}.get(button_id, 0)
            if not self._probe.resize(cols, rows):
                result.message = ("The panel is as large as it can be" if (cols > self._probe.cols or rows > self._probe.rows)
                                  else "Buttons stand there: move them away first")
        elif button_id == CANCEL:
            result.done = True
        elif button_id == OK:
            if not self.text.strip():
                result.message = "A name needs a letter"
            else:
                result.done = result.applied = True
        return result
