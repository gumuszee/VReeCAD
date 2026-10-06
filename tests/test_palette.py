import math
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.input import HandInput, InputTracker, InputFrame
from freecad.BlocksCAD.ui.palette import RadialPalette

ITEMS = [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]


def step(tracker, t, **values):
    frame = InputFrame(time=t)
    frame.hands = (HandInput(**values), HandInput())
    tracker.update(frame)
    return frame.left


class PaletteTest(unittest.TestCase):
    def test_item_selection_by_direction(self):
        p = RadialPalette(ITEMS)
        self.assertEqual(p.item_at((0, 1)), 0)      # up
        self.assertEqual(p.item_at((1, 0)), 1)      # right (clockwise)
        self.assertEqual(p.item_at((0, -1)), 2)     # down
        self.assertEqual(p.item_at((-1, 0)), 3)     # left
        self.assertIsNone(p.item_at((0.1, 0.1)))    # dead zone
        self.assertEqual(p.item_at((0.2, 1.0)), 0)  # slightly off axis
        self.assertEqual(p.item_at((-0.2, 1.0)), 0)  # wraps around the top

    def test_hold_point_release_picks(self):
        p, tr = RadialPalette(ITEMS), InputTracker()
        self.assertIsNone(p.update(step(tr, 0.0)))
        self.assertFalse(p.is_open)
        self.assertIsNone(p.update(step(tr, 0.1, button1=True)))
        self.assertTrue(p.is_open)
        self.assertIsNone(p.update(step(tr, 0.2, button1=True, stick=(1.0, 0.0))))
        self.assertEqual(p.highlighted, 1)
        self.assertEqual(p.update(step(tr, 0.3, button1=False, stick=(1.0, 0.0))), "b")
        self.assertFalse(p.is_open)

    def test_release_in_dead_zone_picks_nothing(self):
        p, tr = RadialPalette(ITEMS), InputTracker()
        p.update(step(tr, 0.0, button1=True))
        self.assertIsNone(p.update(step(tr, 0.1, button1=False)))
        self.assertFalse(p.is_open)

    def test_empty_palette_never_opens(self):
        p, tr = RadialPalette(), InputTracker()
        p.update(step(tr, 0.0, button1=True))
        self.assertFalse(p.is_open)

    def test_sector_angles(self):
        p = RadialPalette(ITEMS)
        self.assertAlmostEqual(p.sector_angle(1), math.pi / 2)


if __name__ == "__main__":
    unittest.main()
