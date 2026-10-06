import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.ui import radial as rd
from freecad.BlocksCAD.ui import settings as cfg

HAND = (0.25, 1.2, -0.4)
ITEMS = ["a", "b", "c", "d"]


class SectorTest(unittest.TestCase):
    def test_the_first_item_is_straight_up_and_the_others_follow_clockwise(self):
        self.assertEqual([rd.sector(0, 1, 4), rd.sector(1, 0, 4), rd.sector(0, -1, 4), rd.sector(-1, 0, 4)], [0, 1, 2, 3])
        self.assertEqual([rd.sector(0.0, 1.0, 6), rd.sector(0.87, 0.5, 6), rd.sector(-0.87, 0.5, 6), rd.sector(0.0, -1.0, 6)], [0, 1, 5, 3])

    def test_the_sectors_are_centred_on_their_item(self):
        self.assertEqual(rd.sector(-0.1, 1.0, 6), 0)       # a little left of up is still the top item
        self.assertEqual(rd.sector(0.1, 1.0, 6), 0)
        self.assertEqual(rd.sector(0.0, 1.0, 1), 0)


class ItemsTest(unittest.TestCase):
    KNOWN = {"doc.undo", "doc.redo", "view.reset", "doc.delete", "view.overlay", "pointer.mode", "tool.line", "tool.cube", "app.close",
             "view.layout"}

    def test_recent_faces_come_first_then_the_defaults(self):
        items = rd.choose_items(["tool.cube", "tool.line"], self.KNOWN)
        self.assertEqual(items[:2], ["tool.cube", "tool.line"])
        self.assertEqual(items[2:], ["doc.undo", "doc.redo", "view.reset", "doc.delete"])
        self.assertEqual(len(items), rd.RECENT)

    def test_unknown_hidden_repeated_and_dangerous_faces_are_left_out(self):
        items = rd.choose_items(["gone", "tool.cube", "doc.undo", "tool.cube", "app.close", "view.layout", "view.reset"], self.KNOWN,
                                hidden=["view.reset"])
        self.assertEqual(items, ["tool.cube", "doc.undo", "doc.redo", "doc.delete", "view.overlay", "pointer.mode"])

    def test_remember_moves_a_face_to_the_front_and_keeps_the_newest(self):
        recent = []
        for face in ("a", "b", "c", "a", "d", "e", "f", "g"):
            recent = rd.remember(recent, face)
        self.assertEqual(recent, ["g", "f", "e", "d", "a", "c"])

    def test_recent_faces_are_saved_with_the_settings(self):
        settings = cfg.Settings(recent=["x", "y"])
        self.assertEqual(cfg.Settings.from_json(settings.to_json()).recent, ["x", "y"])
        self.assertEqual(cfg.Settings.from_json('{"recent": "oops"}').recent, [])
        self.assertEqual(cfg.Settings.from_json('{"recent": ["a", 3, null]}').recent, ["a"])
        self.assertEqual(cfg.Settings.from_json('{"tip_angle": 20}').recent, [])


class QuickRadialTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.radial = rd.QuickRadial(hand=1)
        self.sim.set_head(position=(0.0, 1.6, 0.0), look_at_point=(0.0, 1.2, -1.0))
        self.sim.set_hand(1, position=HAND, point_at=(0.0, 1.2, -2.0))

    def step(self, items=ITEMS, blocked=False, n=1):
        state = None
        for _ in range(n):
            state = self.radial.update(self.sim.frame(0.02), items, blocked)
        return state

    def move(self, dx, dy):
        self.sim.set_hand(1, position=(HAND[0] + dx, HAND[1] + dy, HAND[2]))

    def test_holding_button1_opens_it_and_the_hand_direction_chooses(self):
        self.assertFalse(self.step().open)
        self.sim.set_hand(1, button1=True)
        state = self.step()
        self.assertTrue(state.open)
        self.assertIsNone(state.selected)
        self.assertEqual(state.items, ITEMS)
        self.move(0.0, 0.06)
        self.assertEqual(self.step().selected, 0)
        self.move(0.06, 0.0)
        state = self.step()
        self.assertEqual(state.selected, 1)
        self.assertIn((1, 0.2, 0.02), state.haptics)                    # a tick on every change of the choice
        self.move(-0.05, -0.05)
        self.assertEqual(self.step().selected, 3)                        # down and left
        self.move(0.0, -0.06)
        self.assertEqual(self.step().selected, 2)
        self.sim.set_hand(1, button1=False)
        state = self.step()
        self.assertFalse(state.open)
        self.assertEqual(state.activated, 2)
        self.assertFalse(self.radial.is_open)
        self.assertIsNone(self.step().activated)

    def test_the_choice_follows_the_view_of_the_head(self):
        self.sim.set_head(position=(0.0, 1.6, 0.0), look_at_point=(1.0, 1.6, 0.0))        # looking along +X: its right is +Z
        self.sim.set_hand(1, button1=True)
        self.step()
        self.sim.set_hand(1, position=(HAND[0], HAND[1], HAND[2] + 0.06))
        self.assertEqual(self.step().selected, 1)

    def test_no_choice_inside_the_dead_zone_cancels_on_release(self):
        self.sim.set_hand(1, button1=True)
        self.step()
        self.move(0.01, 0.01)
        self.assertIsNone(self.step().selected)
        self.sim.set_hand(1, button1=False)
        state = self.step()
        self.assertIsNone(state.activated)
        self.assertFalse(self.radial.is_open)

    def test_the_view_axes_are_fixed_when_it_opens(self):
        self.sim.set_hand(1, button1=True)
        state = self.step()
        right = state.right
        self.sim.set_head(look_at_point=(1.0, 1.6, 0.0))
        self.assertEqual(self.step().right, right)

    def test_a_grip_cancels_it_and_releasing_does_nothing(self):
        self.sim.set_hand(1, button1=True)
        self.step()
        self.move(0.06, 0.0)
        self.step()
        self.sim.set_hand(0, grip=1.0)
        self.assertFalse(self.step().open)
        self.sim.set_hand(0, grip=0.0)
        self.sim.set_hand(1, button1=False)
        self.assertIsNone(self.step().activated)

    def test_it_does_not_open_while_navigating_or_blocked_and_cannot_open_late(self):
        self.sim.set_hand(0, grip=1.0)
        self.sim.set_hand(1, button1=True)
        self.assertFalse(self.step().open)                             # button1 is the level modifier while a grip holds the world
        self.sim.set_hand(0, grip=0.0)
        self.assertFalse(self.step().open)                             # the press is over: holding on does not open it
        self.sim.set_hand(1, button1=False)
        self.step()
        self.sim.set_hand(1, button1=True)
        self.assertFalse(self.step(blocked=True).open)
        self.sim.set_hand(1, button1=False)
        self.step()
        self.sim.set_hand(1, button1=True)
        self.assertTrue(self.step().open)
        self.assertFalse(self.step(blocked=True).open)                 # becoming blocked cancels it
        self.assertFalse(self.radial.is_open)

    def test_nothing_opens_without_items(self):
        self.sim.set_hand(1, button1=True)
        self.assertFalse(self.step(items=[]).open)

    def test_the_hand_of_the_palette_does_not_open_it(self):
        self.sim.set_hand(0, button1=True)
        self.assertFalse(self.step().open)


if __name__ == "__main__":
    unittest.main()
