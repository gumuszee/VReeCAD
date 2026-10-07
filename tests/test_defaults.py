import unittest

import support  # noqa: F401
from freecad.BlocksCAD.ui import defaults

TOOLS = ["primitive", "select", "move", "pushpull", "points", "sketch"]


class DefaultLayoutTest(unittest.TestCase):
    def test_every_face_has_a_slot_in_the_default_layout(self):
        # a panel holds 12 slots and drops what does not fit, so a face that is missing here is a face nobody can reach
        faces = defaults.build_faces(TOOLS, lambda name: name)
        placed = [face for page in defaults.default_layout(TOOLS).pages for face in page.slots if face]
        self.assertEqual(sorted(placed), sorted(faces))

    def test_no_face_is_placed_twice(self):
        placed = [face for page in defaults.default_layout(TOOLS).pages for face in page.slots if face]
        self.assertEqual(len(placed), len(set(placed)))
