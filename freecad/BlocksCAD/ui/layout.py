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

A `Face` is a button: id, label and an action id such as "tool:teleport" or "view:reset". A `Page` is a grid of slots (COLS x ROWS),
each holding a face id or None. The `Layout` is an ordered list of pages; it is the part the user can rearrange."""

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

    def __post_init__(self):
        self.slots = (list(self.slots) + [None] * SLOTS)[:SLOTS]


@dataclass
class Layout:
    pages: List[Page] = field(default_factory=list)

    def face_at(self, page, slot):
        return self.pages[page].slots[slot]

    def swap(self, page_a, slot_a, page_b, slot_b):
        a, b = self.pages[page_a].slots, self.pages[page_b].slots
        a[slot_a], b[slot_b] = b[slot_b], a[slot_a]

    def remove(self, page, slot):
        self.pages[page].slots[slot] = None

    def to_json(self):
        return json.dumps({"version": 1, "pages": [{"name": p.name, "slots": p.slots} for p in self.pages]}, indent=1)

    @classmethod
    def from_json(cls, text, known_faces=None):
        """Parse a layout; ids that are not in `known_faces` (when given) become empty slots, so a layout saved with a
        newer or different set of faces still loads."""
        data = json.loads(text)
        pages = []
        for page in data["pages"]:
            slots = [s if (isinstance(s, str) and (known_faces is None or s in known_faces)) else None
                     for s in page.get("slots", [])]
            pages.append(Page(str(page["name"]), slots))
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
