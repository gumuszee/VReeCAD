import math
import unittest

import support  # noqa: F401

# backends.sim imports Coin only inside SimSession methods, so the pose math is testable without FreeCAD
from freecad.VReeCAD.backends import sim
from freecad.VReeCAD.input import PRESS_THRESHOLD


def close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class SimMathTest(unittest.TestCase):
    def test_look_at_points_minus_z_at_the_target(self):
        for target in ((0, 0, -1), (1, 0, 0), (0, 1, 0), (0, -2, -2), (3, 1, 4)):
            q = sim.look_at((0, 0, 0), target)
            forward = sim.rotate(q, (0, 0, -1))
            n = math.sqrt(sum(c * c for c in target))
            self.assertTrue(close(forward, tuple(c / n for c in target)), (target, forward))

    def test_look_at_keeps_up_when_possible(self):
        q = sim.look_at((0, 0, 0), (0, 0, -5))
        self.assertTrue(close(sim.rotate(q, (0, 1, 0)), (0, 1, 0)))

    def test_axis_angle_and_multiply(self):
        quarter = sim.quat_from_axis_angle((0, 1, 0), math.pi / 2)
        self.assertTrue(close(sim.rotate(quarter, (0, 0, -1)), (-1, 0, 0)))
        half = sim.quat_multiply(quarter, quarter)
        self.assertTrue(close(sim.rotate(half, (0, 0, -1)), (0, 0, 1)))


class SimInputTest(unittest.TestCase):
    def test_scripted_frames_produce_edges(self):
        s = sim.SimInput()
        s.set_hand(1, trigger=1.0, button2=True)
        f = s.frame(0.5)
        self.assertEqual(f.right.pressed, {"trigger", "button2"})
        self.assertAlmostEqual(f.time, 0.5)
        f = s.frame(0.5)
        self.assertEqual(f.right.pressed, frozenset())
        self.assertTrue(f.right.down("trigger"))
        s.set_hand(1, trigger=0.0)
        self.assertEqual(s.frame().right.released, {"trigger"})

    def test_set_hand_aims_the_controller(self):
        s = sim.SimInput()
        s.set_hand(1, position=(0, 1, 0), point_at=(0, 1, -3))
        self.assertTrue(close(sim.rotate(s.hands[1].aim.orientation, (0, 0, -1)), (0, 0, -1)))

    def test_unknown_input_is_rejected(self):
        with self.assertRaises(ValueError):
            sim.SimInput().set_hand(0, thumbwheel=1)

    def test_frames_are_snapshots(self):
        s = sim.SimInput()
        s.set_hand(0, trigger=PRESS_THRESHOLD)
        first = s.frame()
        s.set_hand(0, trigger=0.0)
        s.frame()
        self.assertEqual(first.left.trigger, PRESS_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
