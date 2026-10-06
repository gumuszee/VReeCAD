import math
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import navigation as nav
from freecad.BlocksCAD.backends.sim import SimInput


def close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class TwoPointTest(unittest.TestCase):
    def test_translation_with_the_midpoint(self):
        w = nav.two_point(nav.IDENTITY, (-0.2, 1, 0), (0.2, 1, 0), (-0.2, 1, -0.5), (0.2, 1, -0.5))
        self.assertTrue(close(w.position, (0, 0, -0.5)))
        self.assertAlmostEqual(w.scale, 1.0)

    def test_scale_follows_the_hand_distance_about_the_midpoint(self):
        w = nav.two_point(nav.IDENTITY, (-0.2, 1, 0), (0.2, 1, 0), (-0.4, 1, 0), (0.4, 1, 0))
        self.assertAlmostEqual(w.scale, 2.0)
        # a world point at the pivot stays at the pivot
        self.assertTrue(close(w.to_stage((0, 1, 0)), (0, 1, 0)))
        # a point 0.1 from the pivot is now 0.2 from it
        self.assertTrue(close(w.to_stage((0.1, 1, 0)), (0.2, 1, 0)))

    def test_yaw_rotation_about_the_vertical_axis(self):
        # hands turn a quarter turn about the vertical through the midpoint
        w = nav.two_point(nav.IDENTITY, (-0.2, 1, 0), (0.2, 1, 0), (0, 1, 0.2), (0, 1, -0.2))
        p = w.to_stage((0.2, 1, 0))
        self.assertTrue(close(p, (0, 1, -0.2), 1e-6) or close(p, (0, 1, 0.2), 1e-6))
        # the grabbed points follow the hands: the world point under the right hand is now under the right hand
        self.assertTrue(close(w.to_stage((0.2, 1, 0)), (0, 1, -0.2)))
        self.assertTrue(close(w.to_stage((-0.2, 1, 0)), (0, 1, 0.2)))

    def test_hands_tilting_do_not_tilt_the_world_when_constrained(self):
        w = nav.two_point(nav.IDENTITY, (-0.2, 1, 0), (0.2, 1, 0), (-0.2, 0.8, 0), (0.2, 1.2, 0))
        self.assertTrue(close(mu.rotate(w.rotation, (0, 1, 0)), (0, 1, 0)))
        free = nav.two_point(nav.IDENTITY, (-0.2, 1, 0), (0.2, 1, 0), (-0.2, 0.8, 0), (0.2, 1.2, 0), constrain_up=False)
        self.assertGreater(abs(mu.rotate(free.rotation, (0, 1, 0))[0]), 0.1)

    def test_scale_is_clamped(self):
        w = nav.two_point(nav.IDENTITY, (-0.01, 1, 0), (0.01, 1, 0), (-1, 1, 0), (1, 1, 0), max_scale=10.0)
        self.assertAlmostEqual(w.scale, 10.0)
        w = nav.two_point(nav.IDENTITY, (-1, 1, 0), (1, 1, 0), (-0.001, 1, 0), (0.001, 1, 0), min_scale=0.1)
        self.assertAlmostEqual(w.scale, 0.1)

    def test_pose_roundtrip(self):
        w = nav.WorldPose((1, 2, 3), mu.quat_from_axis_angle((0, 1, 0), 0.7), 2.5)
        p = (0.3, -1.0, 2.0)
        self.assertTrue(close(w.to_world(w.to_stage(p)), p))


class NavigatorTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.nav = nav.Navigator()

    def step(self, **kw):
        return self.nav.update(self.sim.frame(0.02), **kw)

    def test_one_grip_drags_the_world(self):
        self.sim.set_hand(1, position=(0.3, 1.2, 0.0))
        self.step()
        self.sim.set_hand(1, grip=1.0)
        self.assertEqual(self.step(), [("grab", 1)])
        self.sim.set_hand(1, position=(0.3, 1.2, -0.4))
        self.step()
        self.assertTrue(close(self.nav.world.position, (0, 0, -0.4)))
        self.sim.set_hand(1, grip=0.0)
        self.assertEqual(self.step(), [("release",)])
        self.sim.set_hand(1, position=(0.3, 1.2, 5.0))
        self.step()
        self.assertTrue(close(self.nav.world.position, (0, 0, -0.4)))   # no longer following

    def test_two_grips_scale_and_tick_once_per_octave(self):
        self.sim.set_hand(0, position=(-0.2, 1.2, 0))
        self.sim.set_hand(1, position=(0.2, 1.2, 0))
        self.step()
        self.sim.set_hand(0, grip=1.0)
        self.sim.set_hand(1, grip=1.0)
        events = self.step()
        self.assertEqual(events, [("grab", 2)])
        ticks = 0
        for width in (0.5, 0.7, 0.9, 1.1, 1.3):  # half widths: scale goes 1.25 .. 3.25
            self.sim.set_hand(0, position=(-width / 2, 1.2, 0))
            self.sim.set_hand(1, position=(width / 2, 1.2, 0))
            ticks += sum(1 for e in self.step() if e[0] == "tick")
        self.assertAlmostEqual(self.nav.world.scale, 1.3 / 0.4)
        self.assertEqual(ticks, 1)   # crossing 2.0 only

    def test_switching_from_one_to_two_grips_does_not_jump(self):
        self.sim.set_hand(0, position=(-0.2, 1.2, 0))
        self.sim.set_hand(1, position=(0.2, 1.2, 0), grip=1.0)
        self.step()
        self.sim.set_hand(1, position=(0.2, 1.2, -0.3))
        self.step()
        before = self.nav.world
        self.sim.set_hand(0, grip=1.0)
        self.step()
        self.assertEqual(self.nav.state, "two")
        self.assertTrue(close(self.nav.world.position, before.position))
        self.assertAlmostEqual(self.nav.world.scale, before.scale)

    def test_blocked_hand_does_not_grab(self):
        self.sim.set_hand(1, grip=1.0)
        self.assertEqual(self.step(blocked=(False, True)), [])
        self.assertEqual(self.nav.state, "idle")

    def test_stick_click_resets_with_an_animation(self):
        self.sim.set_hand(1, position=(0.3, 1.2, 0.0), grip=1.0)
        self.step()
        self.sim.set_hand(1, position=(0.3, 1.2, -1.0))
        self.step()
        self.assertFalse(close(self.nav.world.position, (0, 0, 0)))
        self.sim.set_hand(1, stick_click=True)
        self.assertEqual(self.step(), [("reset",)])
        self.assertTrue(self.nav.resetting)
        for _ in range(30):
            self.step()
        self.assertFalse(self.nav.resetting)
        self.assertEqual(self.nav.world, nav.IDENTITY)
        # the grip still held does not drag until it is released
        self.sim.set_hand(1, stick_click=False, position=(0.3, 1.2, -2.0))
        self.step()
        self.assertEqual(self.nav.world, nav.IDENTITY)
        self.sim.set_hand(1, grip=0.0)
        self.step()
        self.sim.set_hand(1, grip=1.0)
        self.assertEqual(self.step(), [("grab", 1)])

    def test_format_scale(self):
        self.assertEqual(nav.format_scale(1.0), "1 : 1")
        self.assertEqual(nav.format_scale(4.0), "4 : 1")
        self.assertEqual(nav.format_scale(0.25), "1 : 4")
        self.assertEqual(nav.format_scale(2.5), "2.5 : 1")
        self.assertEqual(nav.format_scale(0.01), "1 : 100")


if __name__ == "__main__":
    unittest.main()
