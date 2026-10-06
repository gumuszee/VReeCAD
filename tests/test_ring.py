import json
import math
import os
import tempfile
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import ring as rg

CONTROLLER = (-0.2, 1.15, -0.35)
HEAD = (0.0, 1.6, 0.0)


class RingTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.ring = rg.PaletteRing(3)
        self.sim.set_head(position=HEAD, look_at_point=CONTROLLER)
        self.sim.set_hand(0, position=CONTROLLER, point_at=(0, 1.2, -1))
        self.sim.set_hand(1, position=(0.2, 1.2, -0.3), point_at=(0.2, 1.2, -2))

    def run_frames(self, n=30, **kw):
        result = None
        for _ in range(n):
            result = self.ring.update(self.sim.frame(0.02), **kw)
        return result

    def front_slot_point(self, slot, page=0):
        centre, u, v, n = self.ring.page_frame(page, CONTROLLER, HEAD)
        col, row = slot % lay.COLS, slot // lay.COLS
        x = (col - (lay.COLS - 1) / 2) * (rg.CELL + rg.GAP)
        y = ((lay.ROWS - 1) / 2 - row) * (rg.CELL + rg.GAP)
        return mu.add(centre, mu.add(mu.mul(u, x), mu.mul(v, y))), n

    def test_locate_slot(self):
        self.assertEqual(rg.PaletteRing.locate_slot(0.0, 0.0), 6)   # the centre lies between columns 1 and 2
        self.assertEqual(rg.PaletteRing.locate_slot(-(rg.CELL + rg.GAP) / 2, 0.0), 5)
        self.assertEqual(rg.PaletteRing.locate_slot(-rg.GRID_W / 2 + 0.01, rg.GRID_H / 2 - 0.01), 0)
        self.assertEqual(rg.PaletteRing.locate_slot(rg.GRID_W / 2 - 0.01, -rg.GRID_H / 2 + 0.01), lay.SLOTS - 1)
        self.assertIsNone(rg.PaletteRing.locate_slot(rg.GRID_W, 0.0))
        self.assertIsNone(rg.PaletteRing.locate_slot(0.0, -rg.GRID_H))

    def test_gaze_controls_visibility(self):
        self.assertTrue(self.run_frames().visible)
        self.assertAlmostEqual(self.ring.fade, 1.0)
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))   # look away
        self.assertFalse(self.run_frames().visible)
        self.assertEqual(self.ring.fade, 0.0)

    def test_pin_shows_the_ring_without_gaze_and_navigation_hides_it(self):
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))
        self.sim.set_hand(0, button1=True)
        self.run_frames(1)
        self.sim.set_hand(0, button1=False)
        self.assertTrue(self.run_frames().visible)
        self.assertFalse(self.run_frames(navigating=True).visible)
        self.sim.set_hand(0, button1=True)       # second press releases the pin
        self.run_frames(1, navigating=False)
        self.sim.set_hand(0, button1=False)
        self.assertFalse(self.run_frames().visible)

    def test_stick_flick_turns_one_page_per_flick(self):
        self.run_frames()
        self.sim.set_hand(0, stick=(1.0, 0.0))
        r = self.run_frames(1)
        self.assertEqual(self.ring.index, 1)
        self.assertEqual(r.haptics[0][0], 0)
        self.run_frames(10)                      # holding does not repeat
        self.assertEqual(self.ring.index, 1)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(2)
        self.sim.set_hand(0, stick=(-1.0, 0.0))
        self.run_frames(1)
        self.assertEqual(self.ring.index, 0)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(2)
        self.sim.set_hand(0, stick=(1.0, 0.0))
        self.run_frames(1)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(60)
        self.assertAlmostEqual(self.ring.angle, self.ring.target_angle, places=3)
        self.assertEqual(self.ring.front_page(), 1)

    def test_ray_hover_and_activate(self):
        self.run_frames()
        point, n = self.front_slot_point(5)
        origin = mu.add(point, mu.mul(n, 0.3))
        self.sim.set_hand(1, position=origin, point_at=point)
        r = self.run_frames(1)
        self.assertEqual(r.hover, (0, 5))
        self.assertTrue(r.consume_trigger)
        self.assertLess(mu.length(mu.sub(r.ray_end, point)), 1e-6)
        self.assertIsNone(r.activated)
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_frames(1)
        self.assertEqual(r.activated, (0, 5))
        r = self.run_frames(1)                   # still held: no second activation
        self.assertIsNone(r.activated)

    def test_ray_beside_the_grid_does_not_hover(self):
        self.run_frames()
        point, n = self.front_slot_point(0)
        far_left = mu.sub(point, mu.mul(mu.cross(rg.UP, n), 0.3))
        self.sim.set_hand(1, position=mu.add(far_left, mu.mul(n, 0.3)), point_at=far_left)
        r = self.run_frames(1)
        self.assertIsNone(r.hover)
        self.assertFalse(r.consume_trigger)

    def test_turned_away_pages_are_not_interactive(self):
        self.run_frames()
        point, n = self.front_slot_point(0, page=1)    # page 1 is 120 degrees around
        self.sim.set_hand(1, position=mu.add(point, mu.mul(n, 0.3)), point_at=point)
        self.assertIsNone(self.run_frames(1).hover)

    def test_hidden_ring_has_no_hover(self):
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))
        self.run_frames()
        point, n = self.front_slot_point(5)
        self.sim.set_hand(1, position=mu.add(point, mu.mul(n, 0.3)), point_at=point)
        self.assertIsNone(self.run_frames(1).hover)


class LayoutTest(unittest.TestCase):
    def make(self):
        return lay.Layout([lay.Page("Tools", ["a", "b", None]), lay.Page("View", ["c"])])

    def test_json_roundtrip_and_padding(self):
        layout = lay.Layout.from_json(self.make().to_json())
        self.assertEqual([p.name for p in layout.pages], ["Tools", "View"])
        self.assertEqual(len(layout.pages[0].slots), lay.SLOTS)
        self.assertEqual(layout.face_at(0, 1), "b")
        self.assertIsNone(layout.face_at(1, 5))

    def test_unknown_faces_become_empty(self):
        layout = lay.Layout.from_json(self.make().to_json(), known_faces={"a", "c"})
        self.assertEqual((layout.face_at(0, 0), layout.face_at(0, 1)), ("a", None))

    def test_swap_and_remove(self):
        layout = self.make()
        layout.swap(0, 0, 1, 0)
        self.assertEqual((layout.face_at(0, 0), layout.face_at(1, 0)), ("c", "a"))
        layout.remove(0, 0)
        self.assertIsNone(layout.face_at(0, 0))

    def test_load_falls_back_to_the_default(self):
        default = self.make()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "layout.json")
            self.assertIs(lay.load_layout(default, {"a"}, path), default)         # missing file
            with open(path, "w") as f:
                f.write("not json")
            self.assertIs(lay.load_layout(default, {"a"}, path), default)         # broken file
            lay.save_layout(default, path)
            self.assertEqual(lay.load_layout(None, {"a", "b", "c"}, path).face_at(0, 1), "b")
            with open(path, "w") as f:
                f.write(json.dumps({"pages": []}))
            self.assertIs(lay.load_layout(default, {"a"}, path), default)         # no pages

    def test_wrap_label(self):
        self.assertEqual(lay.wrap_label("Teleport"), ["Teleport"])
        self.assertEqual(lay.wrap_label("Working plane"), ["Working", "plane"])
        self.assertEqual(lay.wrap_label("Extraordinarily"), ["Extraordinarily"])
        self.assertEqual(lay.wrap_label("Reset view now"), ["Reset", "view now"])
        self.assertEqual(lay.wrap_label(""), [""])


if __name__ == "__main__":
    unittest.main()
