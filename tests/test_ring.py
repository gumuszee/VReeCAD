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
SIDES = [[0], [1], [2]]


class RingTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.ring = rg.PaletteRing(SIDES)
        self.sim.set_head(position=HEAD, look_at_point=CONTROLLER)
        self.sim.set_hand(0, position=CONTROLLER, point_at=(0, 1.2, -1))
        self.sim.set_hand(1, position=(0.2, 1.2, -0.3), point_at=(0.2, 1.2, -2))

    def run_frames(self, n=30, **kw):
        result = None
        for _ in range(n):
            result = self.ring.update(self.sim.frame(0.02), **kw)
        return result

    def slot_point(self, slot, page=0):
        pose = self.ring.poses[page]
        col, row = slot % lay.COLS, slot // lay.COLS
        x = (col - (lay.COLS - 1) / 2) * (rg.CELL + rg.GAP)
        y = ((lay.ROWS - 1) / 2 - row) * (rg.CELL + rg.GAP)
        return mu.add(pose.centre, mu.add(mu.mul(pose.u, x), mu.mul(pose.v, y))), pose.n

    def aim_at(self, point, normal, distance=0.3):
        self.sim.set_hand(1, position=mu.add(point, mu.mul(normal, distance)), point_at=point)

    def title_point(self, page=0):
        pose = self.ring.poses[page]
        y = (rg.TITLE_Y[0] + rg.TITLE_Y[1]) / 2
        return mu.add(pose.centre, mu.mul(pose.v, y)), pose.n

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

    def test_stick_flick_turns_one_side_per_flick(self):
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
        self.assertEqual(self.ring.front_side(), 1)

    def test_front_side_stands_on_the_controller_and_turns_with_it(self):
        self.run_frames()
        pose = self.ring.poses[0]
        controller = self.sim.hands[0]
        up = mu.rotate(controller.aim.orientation, (0.0, 1.0, 0.0))
        forward = mu.rotate(controller.aim.orientation, (0.0, 0.0, -1.0))
        self.assertLess(mu.length(mu.sub(pose.n, up)), 1e-6)         # faces the thumb side of the controller
        self.assertLess(mu.length(mu.sub(pose.v, forward)), 1e-6)    # its top points the way the controller points
        offset = mu.sub(pose.centre, controller.aim.position)
        self.assertAlmostEqual(mu.dot(offset, forward), rg.FORWARD, places=6)
        self.assertAlmostEqual(mu.dot(offset, up), self.ring.radius, places=6)
        # roll the controller a quarter turn about its own axis: the side follows
        roll = mu.quat_multiply(controller.aim.orientation, mu.quat_from_axis_angle((0.0, 0.0, -1.0), math.pi / 2))
        self.sim.set_hand(0, orientation=roll)
        self.run_frames(5)
        pose = self.ring.poses[0]
        self.assertLess(mu.length(mu.sub(pose.n, mu.rotate(roll, (0.0, 1.0, 0.0)))), 1e-6)

    def test_ray_hover_and_activate(self):
        self.run_frames()
        point, n = self.slot_point(5)
        self.aim_at(point, n)
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

    def test_ray_beside_the_panel_does_not_hover(self):
        self.run_frames()
        point, n = self.slot_point(0)
        far_left = mu.sub(point, mu.mul(self.ring.poses[0].u, 0.3))
        self.aim_at(far_left, n)
        r = self.run_frames(1)
        self.assertIsNone(r.hover)
        self.assertFalse(r.consume_trigger)

    def test_turned_away_sides_are_not_interactive(self):
        self.run_frames()
        pose = self.ring.poses.get(1)            # side 1 is 120 degrees around: not drawn and never interactive
        self.assertIsNone(pose)
        self.sim.set_hand(0, stick=(1.0, 0.0))
        self.run_frames(2)                       # mid turn: both sides are drawn but only the one near the front hovers
        self.assertEqual(self.ring.index, 1)

    def test_hidden_ring_has_no_hover(self):
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))
        self.run_frames()
        self.assertEqual(self.ring.poses, {})
        self.assertIsNone(self.run_frames(1).hover)

    def test_panels_stacked_on_one_side_stand_next_to_each_other(self):
        self.ring = rg.PaletteRing([[0, 1], [2]])
        self.run_frames()
        a, b = self.ring.poses[0], self.ring.poses[1]
        self.assertLess(mu.length(mu.sub(a.n, b.n)), 1e-9)
        gap = mu.sub(b.centre, a.centre)
        self.assertAlmostEqual(mu.dot(gap, a.u), rg.PANEL_W + rg.PANEL_GAP, places=6)
        self.assertAlmostEqual(mu.dot(gap, a.v), 0.0, places=6)
        # both are interactive: a face of the second panel hovers
        point, n = self.slot_point(3, page=1)
        self.aim_at(point, n)
        self.assertEqual(self.run_frames(1).hover, (1, 3))

    def test_four_panels_on_one_side_make_two_rows(self):
        self.ring = rg.PaletteRing([[0, 1, 2, 3]])
        self.run_frames()
        poses = [self.ring.poses[i] for i in range(4)]
        rows = {round(mu.dot(p.centre, poses[0].v), 4) for p in poses}
        self.assertEqual(len(rows), 2)

    def lift(self, page=0):
        point, n = self.title_point(page)
        self.aim_at(point, n)
        self.run_frames(1)
        self.assertEqual(self.ring.hover_title, page)
        self.sim.set_hand(1, trigger=1.0)
        return self.run_frames(1)

    def test_lift_a_panel_and_drop_it_in_front_of_another(self):
        self.run_frames()
        r = self.lift(0)
        self.assertEqual(self.ring.lifted, 0)
        self.assertTrue(r.consume_trigger)
        self.assertNotIn(0, self.ring.poses)     # the lifted panel leaves its side
        self.sim.set_hand(0, stick=(1.0, 0.0))   # turn the carousel to side 1
        self.run_frames(1)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(60)
        self.assertEqual(self.ring.front_side(), 1)
        point, n = self.slot_point(2, page=1)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual(r.drop_target, (1, 1))
        self.assertIsNone(r.dropped)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertEqual(r.dropped, (0, 1, 1))
        self.assertIsNone(self.ring.lifted)

    def test_drop_on_the_empty_slot_appends_and_on_nothing_cancels(self):
        self.ring = rg.PaletteRing([[0, 1], [2]])
        self.run_frames()
        self.lift(1)
        ghost = self.ring.ghost
        self.assertIsNotNone(ghost)
        self.aim_at(ghost.centre, ghost.n)
        r = self.run_frames(1)
        self.assertEqual(r.drop_target, (0, None))
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_frames(1).dropped, (1, 0, None))
        # cancel: lift, point at nothing, release
        self.lift(0)
        self.sim.set_hand(1, position=(0.3, 1.5, -0.3), point_at=(0.3, 1.5, -2.0))
        self.run_frames(1)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertIsNone(r.dropped)
        self.assertIsNone(self.ring.lifted)

    def test_lifting_offers_a_new_side(self):
        self.ring = rg.PaletteRing([[0, 1], [2]])
        self.run_frames()
        self.lift(0)
        self.run_frames(2)
        self.assertEqual(len(self.ring.display_sides()), 3)    # the extra, empty side at the end
        self.assertEqual(self.ring.display_sides()[2], [])


class LayoutTest(unittest.TestCase):
    def make(self):
        return lay.Layout([lay.Page("Tools", ["a", "b", None]), lay.Page("View", ["c"])])

    def three(self):
        return lay.Layout([lay.Page("A"), lay.Page("B"), lay.Page("C")])

    def test_json_roundtrip_and_padding(self):
        layout = lay.Layout.from_json(self.make().to_json())
        self.assertEqual([p.name for p in layout.pages], ["Tools", "View"])
        self.assertEqual(len(layout.pages[0].slots), lay.SLOTS)
        self.assertEqual(layout.face_at(0, 1), "b")
        self.assertIsNone(layout.face_at(1, 5))

    def test_sides_survive_the_roundtrip_and_old_files_get_a_side_per_page(self):
        layout = self.three()
        layout.move_page(2, 0)
        again = lay.Layout.from_json(layout.to_json())
        self.assertEqual(again.sides(), layout.sides())
        old = json.dumps({"version": 1, "pages": [{"name": "A", "slots": []}, {"name": "B", "slots": []}]})
        self.assertEqual(lay.Layout.from_json(old).sides(), [[0], [1]])

    def test_unknown_faces_become_empty(self):
        layout = lay.Layout.from_json(self.make().to_json(), known_faces={"a", "c"})
        self.assertEqual((layout.face_at(0, 0), layout.face_at(0, 1)), ("a", None))

    def test_swap_and_remove(self):
        layout = self.make()
        layout.swap(0, 0, 1, 0)
        self.assertEqual((layout.face_at(0, 0), layout.face_at(1, 0)), ("c", "a"))
        layout.remove(0, 0)
        self.assertIsNone(layout.face_at(0, 0))

    def test_every_page_starts_on_its_own_side(self):
        self.assertEqual(self.three().sides(), [[0], [1], [2]])

    def test_move_page_onto_another_side(self):
        layout = self.three()
        layout.move_page(2, 0)                       # C joins the side of A, after it
        self.assertEqual([p.name for p in layout.pages], ["A", "C", "B"])
        self.assertEqual(layout.sides(), [[0, 1], [2]])
        layout.move_page(2, 0, before=0)             # B in front of A
        self.assertEqual([p.name for p in layout.pages], ["B", "A", "C"])
        self.assertEqual(layout.sides(), [[0, 1, 2]])

    def test_move_page_to_a_new_side_and_empty_sides_vanish(self):
        layout = self.three()
        layout.move_page(0, 3)                       # a new side at the end
        self.assertEqual([p.name for p in layout.pages], ["B", "C", "A"])
        self.assertEqual(layout.sides(), [[0], [1], [2]])
        layout = self.three()
        layout.move_page(1, 0)
        self.assertEqual(layout.sides(), [[0, 1], [2]])
        layout.move_page(0, 2)                       # A leaves for a new side, B stays alone on the first
        self.assertEqual([p.name for p in layout.pages], ["B", "C", "A"])
        self.assertEqual(layout.sides(), [[0], [1], [2]])

    def test_move_page_before_itself_changes_nothing(self):
        layout = self.three()
        layout.move_page(1, 1, before=1)
        self.assertEqual([p.name for p in layout.pages], ["A", "B", "C"])
        self.assertEqual(layout.sides(), [[0], [1], [2]])

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
