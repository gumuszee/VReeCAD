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
(COLS x ROWS), each holding a face id or None. The panels stand on the sides of the carousel around the palette controller; the pages
with the same `side` share one side and are laid out next to each other there. The `Layout` is the ordered list of pages; panels
and faces are the parts the user can rearrange."""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

COLS, ROWS = 4, 3
SLOTS = COLS * ROWS


@dataclass(frozen=True)
class Face:
    id: str
    label: str
    action: str


@dataclass
class Page:
    name: str
    slots: List[Optional[str]] = field(default_factory=lambda: [None] * SLOTS)
    side: Optional[int] = None   # carousel side; None puts the page on a side of its own

    def __post_init__(self):
        self.slots = (list(self.slots) + [None] * SLOTS)[:SLOTS]


@dataclass
class Layout:
    pages: List[Page] = field(default_factory=list)

    def __post_init__(self):
        self.normalize()

    def normalize(self):
        """Number the sides 0, 1, 2 ... in carousel order; a page without a side gets one of its own."""
        free = max([p.side for p in self.pages if p.side is not None], default=-1) + 1
        for page in self.pages:
            if page.side is None:
                page.side, free = free, free + 1
        rank = {side: i for i, side in enumerate(sorted({p.side for p in self.pages}))}
        for page in self.pages:
            page.side = rank[page.side]

    def sides(self):
        """The pages (as indexes) on each carousel side, in carousel order and, within a side, in layout order."""
        result = [[] for _ in range(1 + max([p.side for p in self.pages], default=-1))]
        for index, page in enumerate(self.pages):
            result[page.side].append(index)
        return result

    def move_page(self, page, side, before=None):
        """Move a page onto a carousel side (`side` equal to the number of sides makes a new side at the end), in front of the
        page `before` on that side or after the last page of the side. Returns the new index of the page."""
        moved = self.pages[page]
        sides = self.sides()
        target = [self.pages[i] for i in sides[side]] if side < len(sides) else []
        anchor = self.pages[before] if before is not None else None
        rest = [p for p in self.pages if p is not moved]
        moved.side = target[0].side if target else len(sides)
        if anchor is not None and anchor is not moved and any(anchor is p for p in target):
            index = next(i for i, p in enumerate(rest) if p is anchor)
        else:
            last = [p for p in rest if p.side == moved.side]
            if last:
                index = next(i for i, p in enumerate(rest) if p is last[-1]) + 1
            elif side < len(sides):
                index = next(i for i, p in enumerate(self.pages) if p is moved)   # alone on its side: stays in place
            else:
                index = len(rest)
        rest.insert(index, moved)
        self.pages = rest
        self.normalize()
        return index

    def face_at(self, page, slot):
        return self.pages[page].slots[slot]

    def swap(self, page_a, slot_a, page_b, slot_b):
        a, b = self.pages[page_a].slots, self.pages[page_b].slots
        a[slot_a], b[slot_b] = b[slot_b], a[slot_a]

    def remove(self, page, slot):
        self.pages[page].slots[slot] = None

    def to_json(self):
        return json.dumps({"version": 2, "pages": [{"name": p.name, "side": p.side, "slots": p.slots} for p in self.pages]}, indent=1)

    @classmethod
    def from_json(cls, text, known_faces=None):
        """Parse a layout; ids that are not in `known_faces` (when given) become empty slots, so a layout saved with a
        newer or different set of faces still loads."""
        data = json.loads(text)
        pages = []
        for page in data["pages"]:
            slots = [s if (isinstance(s, str) and (known_faces is None or s in known_faces)) else None
                     for s in page.get("slots", [])]
            side = page.get("side")
            pages.append(Page(str(page["name"]), slots, side if isinstance(side, int) else None))
        if not pages:
            raise ValueError("layout without pages")
        return cls(pages)


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
