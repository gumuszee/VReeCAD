import math
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import navigation as nav
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.input import Pose


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
        w = nav.two_point(nav.IDENTITY, (-0.2, 1, 0), (0.2, 1, 0), (-0.2, 0.8, 0), (0.2, 1.2, 0), constrain_up=True)
        self.assertTrue(close(mu.rotate(w.rotation, (0, 1, 0)), (0, 1, 0)))
        free = nav.two_point(nav.IDENTITY, (-0.2, 1, 0), (0.2, 1, 0), (-0.2, 0.8, 0), (0.2, 1.2, 0))
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

    def test_stick_click_resets_to_the_home_pose_in_front_of_the_head(self):
        self.sim.set_hand(1, position=(0.3, 1.2, 0.0), grip=1.0)
        self.step()
        self.sim.set_hand(1, position=(0.3, 1.2, -1.0))
        self.step()
        self.assertFalse(close(self.nav.world.position, (0, 1.2, -1.0)))
        self.sim.set_hand(1, stick_click=True)
        self.assertEqual(self.step(), [("reset",)])
        self.assertTrue(self.nav.resetting)
        for _ in range(30):
            self.step()
        self.assertFalse(self.nav.resetting)
        home = nav.home_pose(self.sim.head)
        self.assertEqual(self.nav.world, home)
        self.assertTrue(close(home.position, (0.0, 1.6 * nav.HOME_HEIGHT, -nav.HOME_DISTANCE)))
        # the grip still held does not drag until it is released
        self.sim.set_hand(1, stick_click=False, position=(0.3, 1.2, -2.0))
        self.step()
        self.assertEqual(self.nav.world, home)
        self.sim.set_hand(1, grip=0.0)
        self.step()
        self.sim.set_hand(1, grip=1.0)
        self.assertEqual(self.step(), [("grab", 1)])

    def test_home_pose_follows_the_head_position_and_heading(self):
        self.sim.set_head(position=(1.0, 1.7, 2.0), look_at_point=(6.0, 1.7, 2.0))   # looking along +X
        home = nav.home_pose(self.sim.head)
        self.assertTrue(close(home.position, (2.0, 1.7 * nav.HOME_HEIGHT, 2.0), 1e-6))
        # the document front view (document +Y is stage -Z) points along the line of sight
        self.assertTrue(close(mu.rotate(home.rotation, (0, 0, -1)), (1, 0, 0), 1e-6))
        # looking down does not turn the home pose: the top of the head points forward
        self.sim.set_head(position=(0.0, 1.7, 0.0), look_at_point=(0.0, 0.0, -0.01))
        home = nav.home_pose(self.sim.head)
        self.assertTrue(close(home.position, (0.0, 1.7 * nav.HOME_HEIGHT, -nav.HOME_DISTANCE), 1e-3))
        self.assertEqual(nav.home_pose(Pose()), nav.IDENTITY)   # an untracked head

    def test_reset_can_be_requested_without_a_gesture(self):
        self.step()
        self.nav.world = nav.WorldPose((3, 0, 0), mu.quat_from_axis_angle((1, 0, 0), 0.5), 3.0)
        self.nav.request_reset()
        self.assertEqual(self.step(), [("reset",)])
        for _ in range(30):
            self.step()
        self.assertEqual(self.nav.world, nav.home_pose(self.sim.head))
        self.nav.request_reset()                                   # already home: nothing to animate
        self.assertEqual(self.step(), [])
        self.assertFalse(self.nav.resetting)

    def two_grips(self, left=(-0.2, 1.2, 0), right=(0.2, 1.2, 0), **right_inputs):
        self.sim.set_hand(0, position=left, grip=1.0)
        self.sim.set_hand(1, position=right, grip=1.0, **right_inputs)
        self.step()

    def test_free_orbit_tilts_the_world_and_the_modifier_keeps_it_level(self):
        self.two_grips()
        self.sim.set_hand(0, position=(-0.2, 0.9, 0))
        self.sim.set_hand(1, position=(0.2, 1.5, 0))
        self.step()
        self.assertGreater(abs(mu.rotate(self.nav.world.rotation, (0, 1, 0))[0]), 0.1)   # free by default
        self.assertFalse(self.nav.level)
        # holding button1 of the tool hand: the next movement only turns about the vertical axis
        self.sim.set_hand(1, button1=True)
        events = self.step()
        self.assertIn(("level", True), events)
        tilted = mu.rotate(self.nav.world.rotation, (0, 1, 0))
        self.sim.set_hand(0, position=(-0.2, 1.5, 0))
        self.sim.set_hand(1, position=(0.2, 0.9, 0))
        self.step()
        self.assertTrue(close(mu.rotate(self.nav.world.rotation, (0, 1, 0)), tilted, 1e-6))   # no further tilt

    def test_switching_the_rotation_mode_does_not_jump(self):
        self.two_grips()
        self.sim.set_hand(0, position=(-0.2, 0.9, 0))
        self.sim.set_hand(1, position=(0.2, 1.5, 0))
        self.step()
        before = self.nav.world
        self.sim.set_hand(1, button1=True)
        self.step()
        self.assertTrue(close(self.nav.world.position, before.position, 1e-9))
        self.assertTrue(close(self.nav.world.rotation, before.rotation, 1e-9))
        self.sim.set_hand(1, button1=False)
        self.step()
        self.assertTrue(close(self.nav.world.position, before.position, 1e-9))

    def test_button2_snaps_the_scale_to_one_about_the_hands(self):
        self.two_grips()
        self.sim.set_hand(0, position=(-0.4, 1.2, 0))
        self.sim.set_hand(1, position=(0.4, 1.2, 0))
        self.step()
        self.assertAlmostEqual(self.nav.world.scale, 2.0)
        under = self.nav.world.to_world((0.0, 1.2, 0.0))          # the world point at the midpoint of the hands
        self.sim.set_hand(1, button2=True)
        events = self.step()
        self.assertIn(("snap",), events)
        self.sim.set_hand(1, button2=False)
        for _ in range(20):
            self.step()
        self.assertEqual(self.nav.world.scale, 1.0)
        self.assertTrue(close(self.nav.world.to_world((0.0, 1.2, 0.0)), under, 1e-9))
        # the gesture continues from 1 : 1
        self.sim.set_hand(0, position=(-0.2, 1.2, 0))
        self.sim.set_hand(1, position=(0.2, 1.2, 0))
        self.step()
        self.assertAlmostEqual(self.nav.world.scale, 0.5, places=6)   # the hands halved their distance

    def test_button2_without_a_grip_does_nothing(self):
        self.sim.set_hand(1, button2=True)
        self.assertEqual(self.step(), [])

    def test_format_scale(self):
        self.assertEqual(nav.format_scale(1.0), "1 : 1")
        self.assertEqual(nav.format_scale(4.0), "4 : 1")
        self.assertEqual(nav.format_scale(0.25), "1 : 4")
        self.assertEqual(nav.format_scale(2.5), "2.5 : 1")
        self.assertEqual(nav.format_scale(0.01), "1 : 100")


if __name__ == "__main__":
    unittest.main()
