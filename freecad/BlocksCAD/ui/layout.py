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
from dataclasses import dataclass, field
from typing import List, Optional

COLS, ROWS = 4, 3
SLOTS = COLS * ROWS
RENAMED_FACES = {"tool.grab": "tool.move"}    # ids that saved layouts and settings may hold, and the faces they stand for


def current_face(face_id):
    """The id of the face that a saved id stands for."""
    return RENAMED_FACES.get(face_id, face_id)


@dataclass(frozen=True)
class Face:
    id: str
    label: str
    action: str
    kind: str = "button"   # "button" or "slider" (a slider takes a whole row of its panel)
    tip: str = ""          # one line shown as a tooltip while the face is hovered


@dataclass
class Page:
    name: str
    slots: List[Optional[str]] = field(default_factory=lambda: [None] * SLOTS)
    side: Optional[int] = None   # carousel side; None puts the page on a side of its own
    row: Optional[int] = None    # row on the side; None puts the page in the bottom row

    def __post_init__(self):
        self.slots = (list(self.slots) + [None] * SLOTS)[:SLOTS]


def _slider_row(page, slot, wide):
    """Whether a slot lies in a row of its page that belongs to a slider (`wide` holds the ids of the sliders)."""
    first = page.slots[slot // COLS * COLS]
    return first is not None and first in wide


def without_page(sides, page):
    """The structure `sides` (side -> rows -> page indexes) as it is drawn while `page` is lifted off it: the page is gone, rows that
    become empty are gone, a side that becomes empty stays (as a place to drop the page back)."""
    return [[row for row in ([i for i in r if i != page] for r in side) if row] for side in sides]


@dataclass
class Layout:
    pages: List[Page] = field(default_factory=list)
    hidden: List[str] = field(default_factory=list)   # faces taken off the panels by the user; they stay out of `add_missing`

    def __post_init__(self):
        self.normalize()

    def normalize(self):
        """Number the sides 0, 1, 2 ... in carousel order and the rows of each side 0, 1, 2 ...; a page without a side gets one of
        its own, a page without a row goes to the bottom row."""
        free = max([p.side for p in self.pages if p.side is not None], default=-1) + 1
        for page in self.pages:
            if page.side is None:
                page.side, free = free, free + 1
            if page.row is None:
                page.row = 0
        side_rank = {side: i for i, side in enumerate(sorted({p.side for p in self.pages}))}
        row_rank = {}
        for side in side_rank:
            for i, row in enumerate(sorted({p.row for p in self.pages if p.side == side})):
                row_rank[(side, row)] = i
        for page in self.pages:
            page.row = row_rank[(page.side, page.row)]
            page.side = side_rank[page.side]

    def sides(self):
        """The pages (as indexes) on each carousel side: side -> rows from the bottom up -> pages from left to right."""
        result = [[] for _ in range(1 + max([p.side for p in self.pages], default=-1))]
        for index, page in enumerate(self.pages):
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
        for default_page in default.pages:
            for face in default_page.slots:
                if not face or face in present:
                    continue
                home = [p for p in self.pages if p.name == default_page.name]
                for page in home + self.pages:
                    if face in wide:
                        rows = [r for r in range(ROWS) if all(s is None for s in page.slots[r * COLS:(r + 1) * COLS])]
                        slot = rows[0] * COLS if rows else None
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

    def to_json(self):
        return json.dumps({"version": 4, "hidden": self.hidden,
                           "pages": [{"name": p.name, "side": p.side, "row": p.row, "slots": p.slots} for p in self.pages]}, indent=1)

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
            pages.append(Page(str(page["name"]), slots, side if isinstance(side, int) else None,
                              row if isinstance(row, int) else None))
        if not pages:
            raise ValueError("layout without pages")
        hidden = [current_face(f) for f in data.get("hidden", []) if isinstance(f, str) and (known_faces is None or current_face(f) in known_faces)]
        return cls(pages, hidden)


def user_layout_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "BlocksCAD", "layout.json")


def load_layout(default, known_faces, path=None):
    """The user's saved layout, or `default` when there is none or it cannot be read."""
    path = path or user_layout_path()
    try:
        with open(path, encoding="utf-8") as f:
            return Layout.from_json(f.read(), known_faces)
    except (OSError, ValueError, KeyError, TypeError):
        return default


def save_layout(layout, path=None):
    path = path or user_layout_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(layout.to_json())
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
