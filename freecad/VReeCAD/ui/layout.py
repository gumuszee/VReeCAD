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
"""Faces, pages and the palette layout (docs/ux-design.md, Layout and customization). Pure data, JSON serializable.

A `Face` is a button: id, label and an action id such as "tool:teleport" or "view:reset". A `Page` is a panel: a grid of slots
(COLS x ROWS), each holding a face id or None. The panels stand on the sides of the carousel around the palette controller. A side
holds rows of panels: `Page.side` is the side, `Page.row` the row on it (0 is the bottom row, nearest the user, higher rows are
further forward), and the order of the pages in the layout is the order inside a row, left to right. The `Layout` is the ordered
list of pages plus the ids of the faces the user has hidden; panels and faces are the parts the user can rearrange."""

import json
import os
import zlib
from dataclasses import dataclass, field
from typing import List, Optional

COLS, ROWS = 4, 3          # the grid of a panel to begin with; a panel may have more columns and rows (`Page.cols`, `Page.rows`)
SLOTS = COLS * ROWS
MAX_COLS, MAX_ROWS = 12, 8
RENAMED_FACES = {"tool.grab": "tool.move", "view.controls": "settings.tutorial"}    # ids that saved layouts and settings may hold, and the faces they stand for
RENAMED_PAGES = {"Session": "Settings"}       # names of panels that saved layouts may hold, and the panels they stand for


PANEL_HUES = {"Tools": 0.38, "Edit": 0.92, "View": 0.11, "Modify": 0.68, "Settings": 0.50, "Pointer": 0.30}   # the default panels, green, rose, ochre, violet, teal, lime
SPARE_HUES = (0.75, 0.02, 0.25, 0.45, 0.62)                                  # panels of other names take one of these by their name
VERSION = 5                                                                  # the version of the layout file that `to_json` writes


def default_hue(name):
    """The hue (0 to 1) of the tint of the panel called `name` when the user has chosen none."""
    hue = PANEL_HUES.get(name)
    return hue if hue is not None else SPARE_HUES[zlib.crc32(name.encode("utf-8")) % len(SPARE_HUES)]


def current_face(face_id):
    """The id of the face that a saved id stands for."""
    return RENAMED_FACES.get(face_id, face_id)


@dataclass(frozen=True)
class Face:
    id: str
    label: str
    action: str
    kind: str = "button"   # "button", "slider" or "readout" (these two take a whole row of their panel) or "display" (a cell that only shows a text)
    tip: str = ""          # one line shown as a tooltip while the face is hovered
    swatch: Optional[tuple] = None  # an rgb triple: the face is drawn in exactly this colour (the colour swatches of the values carousel)
    tint: Optional[float] = None   # a hue (0 to 1): the face is drawn in the colour that a panel of this hue gives its faces (the colours of the panel editor)


@dataclass
class Page:
    name: str
    slots: List[Optional[str]] = field(default_factory=lambda: [None] * SLOTS)
    side: Optional[int] = None   # carousel side; None puts the page on a side of its own
    row: Optional[int] = None    # row on the side; None puts the page in the bottom row
    hue: Optional[float] = None  # the tint the user gave the panel (0 to 1); None leaves it to the name (`default_hue`)
    cols: int = COLS             # the faces stand in a grid of `cols` columns and `rows` rows, row by row; the panel grows with it
    rows: int = ROWS
    pinned: bool = False         # a panel that does not stand on a side: the ring puts it at a fixed place that does not turn with the carousel (not saved)

    def __post_init__(self):
        self.cols = min(max(int(self.cols), 1), MAX_COLS)
        self.rows = min(max(int(self.rows), 1), MAX_ROWS)
        count = self.cols * self.rows
        self.slots = (list(self.slots) + [None] * count)[:count]

    def resize(self, cols, rows):
        """Give the panel a grid of `cols` columns and `rows` rows: every face keeps its row and column. Returns whether it was done;
        nothing changes when the size is out of range or would cut off a face (a slider keeps its row only while its row is there)."""
        if not (1 <= cols <= MAX_COLS and 1 <= rows <= MAX_ROWS):
            return False
        cells = {(i // self.cols, i % self.cols): f for i, f in enumerate(self.slots) if f}
        if any(r >= rows or c >= cols for r, c in cells):
            return False
        self.cols, self.rows = cols, rows
        self.slots = [cells.get((i // cols, i % cols)) for i in range(cols * rows)]
        return True


def _slider_row(page, slot, wide):
    """Whether a slot lies in a row of its page that belongs to a slider (`wide` holds the ids of the sliders)."""
    first = page.slots[slot // page.cols * page.cols]
    return first is not None and first in wide


def without_page(sides, page):
    """The structure `sides` (side -> rows -> page indexes) as it is drawn while `page` is lifted off it: the page is gone, rows that
    become empty are gone, a side that becomes empty stays (as a place to drop the page back)."""
    return [[row for row in ([i for i in r if i != page] for r in side) if row] for side in sides]


@dataclass
class Layout:
    pages: List[Page] = field(default_factory=list)
    hidden: List[str] = field(default_factory=list)   # faces taken off the panels by the user; they stay out of `add_missing`
    version: int = VERSION                            # the version of the file the layout was read from (`from_json`); layouts made in code are current

    def __post_init__(self):
        self.normalize()

    def normalize(self):
        """Number the sides 0, 1, 2 ... in carousel order and the rows of each side 0, 1, 2 ...; a page without a side gets one of
        its own, a page without a row goes to the bottom row."""
        pages = [p for p in self.pages if not p.pinned]                  # a pinned panel is on no side
        free = max([p.side for p in pages if p.side is not None], default=-1) + 1
        for page in pages:
            if page.side is None:
                page.side, free = free, free + 1
            if page.row is None:
                page.row = 0
        side_rank = {side: i for i, side in enumerate(sorted({p.side for p in pages}))}
        row_rank = {}
        for side in side_rank:
            for i, row in enumerate(sorted({p.row for p in pages if p.side == side})):
                row_rank[(side, row)] = i
        for page in pages:
            page.row = row_rank[(page.side, page.row)]
            page.side = side_rank[page.side]

    def sides(self):
        """The pages (as indexes) on each carousel side: side -> rows from the bottom up -> pages from left to right."""
        result = [[] for _ in range(1 + max([p.side for p in self.pages if not p.pinned], default=-1))]
        for index, page in enumerate(self.pages):
            if page.pinned:
                continue
            rows = result[page.side]
            while len(rows) <= page.row:
                rows.append([])
            rows[page.row].append(index)
        return result

    def move_page(self, page, side, row=0, before=None, new_row=False):
        """Move a page. Indexes refer to the structure as drawn without the page (`without_page`): `side` equal to the number of
        sides makes a new side at the end; `row` is a row of the side; the page goes in front of the page `before` of that row or
        to its end; with `new_row` it forms a new row inserted at index `row`. Returns the new index of the page."""
        structure = without_page(self.sides(), page)
        if side >= len(structure):
            structure.append([[page]])
        else:
            rows = structure[side]
            if new_row or not rows:
                rows.insert(min(row, len(rows)), [page])
            else:
                target = rows[min(row, len(rows) - 1)]
                target.insert(target.index(before) if before in target else len(target), page)
        order = []
        side_id = 0
        for rows in structure:
            if not rows:
                continue
            for row_id, pages_in_row in enumerate(rows):
                for index in pages_in_row:
                    self.pages[index].side, self.pages[index].row = side_id, row_id
                    order.append(index)
            side_id += 1
        self.pages = [self.pages[i] for i in order]
        return order.index(page)

    def add_missing(self, default, wide=()):
        """Place the faces of the `default` layout that this layout lacks (faces added since it was saved) in the first free slot of
        the page of the same name, else of the first page with room. Faces in `wide` (sliders) need a whole free row and go in its
        first slot. Returns whether anything was added."""
        present = {f for p in self.pages for f in p.slots if f} | set(self.hidden)
        changed = False
        wanted = [(default_page, face) for default_page in default.pages for face in default_page.slots if face]
        wanted.sort(key=lambda pair: pair[1] not in wide)             # the sliders first: they need a whole free row
        for default_page, face in wanted:
            if face in present:
                continue
            home = [p for p in self.pages if p.name == default_page.name]
            for page in home + self.pages:
                if face in wide:
                    rows = [r for r in range(page.rows) if all(s is None for s in page.slots[r * page.cols:(r + 1) * page.cols])]
                    slot = rows[0] * page.cols if rows else None
                else:
                    free = [i for i, f in enumerate(page.slots) if f is None and not _slider_row(page, i, wide)]
                    slot = free[0] if free else None
                if slot is not None:
                    page.slots[slot] = face
                    present.add(face)
                    changed = True
                    break
        return changed

    def face_at(self, page, slot):
        return self.pages[page].slots[slot]

    def swap(self, page_a, slot_a, page_b, slot_b):
        a, b = self.pages[page_a].slots, self.pages[page_b].slots
        a[slot_a], b[slot_b] = b[slot_b], a[slot_a]

    def remove(self, page, slot):
        self.pages[page].slots[slot] = None

    def can_move_face(self, src_page, src_slot, dst_page, dst_slot, wide=()):
        """Whether the face in a slot can go to another slot: it needs a face of its own (not a slider, which is dragged, not lifted),
        and the target must not lie in a row that belongs to a slider (`wide` holds the ids of the sliders)."""
        face = self.pages[src_page].slots[src_slot]
        if face is None or face in wide or (src_page, src_slot) == (dst_page, dst_slot):
            return False
        return not _slider_row(self.pages[dst_page], dst_slot, wide)

    def move_face(self, src_page, src_slot, dst_page, dst_slot, wide=()):
        """Move a face to another slot; a face already there changes places with it. Returns whether anything moved."""
        if not self.can_move_face(src_page, src_slot, dst_page, dst_slot, wide):
            return False
        self.swap(src_page, src_slot, dst_page, dst_slot)
        return True

    def hide_face(self, page, slot, wide=()):
        """Take a face off its panel; it stays hidden until `show_hidden` (sliders cannot be hidden). Returns whether it was hidden."""
        face = self.pages[page].slots[slot]
        if face is None or face in wide:
            return False
        self.remove(page, slot)
        if face not in self.hidden:
            self.hidden.append(face)
        return True

    def show_hidden(self, default, wide=()):
        """Put every hidden face back into a free slot (the page it belongs to in `default` when that has room). Returns whether
        anything came back."""
        hidden, self.hidden = self.hidden, []
        self.add_missing(default, wide)
        self.hidden = [f for f in hidden if not any(f in p.slots for p in self.pages)]
        return len(self.hidden) < len(hidden)

    def to_json(self, **extra):
        """The layout as JSON; `extra` adds keys to the file (the values carousel marks its arrangement)."""
        return json.dumps({"version": VERSION, "hidden": self.hidden, **extra,
                           "pages": [{"name": p.name, "side": p.side, "row": p.row, "slots": p.slots, **({"hue": p.hue} if p.hue is not None else {}),
                                      **({"cols": p.cols, "rows": p.rows} if (p.cols, p.rows) != (COLS, ROWS) else {})}
                                     for p in self.pages]}, indent=1)

    @classmethod
    def from_json(cls, text, known_faces=None):
        """Parse a layout; ids that are not in `known_faces` (when given) become empty slots, so a layout saved with a
        newer or different set of faces still loads. Older files without sides, rows or hidden faces load with a side per page, one
        row and no hidden faces."""
        data = json.loads(text)
        pages = []
        for page in data["pages"]:
            slots = [current_face(s) if (isinstance(s, str) and (known_faces is None or current_face(s) in known_faces)) else None
                     for s in page.get("slots", [])]
            side, row = page.get("side"), page.get("row")
            hue, cols, rows = page.get("hue"), page.get("cols", COLS), page.get("rows", ROWS)
            pages.append(Page(RENAMED_PAGES.get(str(page["name"]), str(page["name"])), slots, side if isinstance(side, int) else None,
                              row if isinstance(row, int) else None,
                              min(max(float(hue), 0.0), 1.0) if isinstance(hue, (int, float)) and not isinstance(hue, bool) else None,
                              cols if isinstance(cols, int) and not isinstance(cols, bool) else COLS,
                              rows if isinstance(rows, int) and not isinstance(rows, bool) else ROWS))
        if not pages:
            raise ValueError("layout without pages")
        hidden = [current_face(f) for f in data.get("hidden", []) if isinstance(f, str) and (known_faces is None or current_face(f) in known_faces)]
        version = data.get("version")
        return cls(pages, hidden, version if isinstance(version, int) else 0)


def user_layout_path(name="layout"):
    """The file of a saved layout: `layout.json` for the palette carousel, `values_layout.json` for the values carousel."""
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "VReeCAD", name + ".json")


def load_layout(default, known_faces, path=None):
    """The user's saved layout, or `default` when there is none or it cannot be read."""
    path = path or user_layout_path()
    try:
        with open(path, encoding="utf-8") as f:
            return Layout.from_json(f.read(), known_faces)
    except (OSError, ValueError, KeyError, TypeError):
        return default


def save_layout(layout, path=None, **extra):
    path = path or user_layout_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(layout.to_json(**extra))
    return path


def wrap_label(label, max_chars=9):
    """Split a label into lines of at most `max_chars` characters at spaces (long words are kept whole)."""
    lines, current = [], ""
    for word in label.split():
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = word if not current else current + " " + word
    if current:
        lines.append(current)
    return lines or [""]
