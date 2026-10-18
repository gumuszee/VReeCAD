import unittest

import support  # noqa: F401
from freecad.VReeCAD.input import HandInput, InputFrame, InputTracker, PRESS_THRESHOLD, RELEASE_THRESHOLD


def frame(t, **right):
    f = InputFrame(time=t)
    f.hands = (HandInput(), HandInput(**right))
    return f


class InputTrackerTest(unittest.TestCase):
    def test_analog_press_and_release_with_hysteresis(self):
        tr = InputTracker()
        self.assertEqual(tr.update(frame(0.0, trigger=0.0)).right.pressed, frozenset())
        self.assertEqual(tr.update(frame(0.1, trigger=PRESS_THRESHOLD)).right.pressed, {"trigger"})
        # between the thresholds nothing changes
        mid = (PRESS_THRESHOLD + RELEASE_THRESHOLD) / 2
        f = tr.update(frame(0.2, trigger=mid))
        self.assertEqual((f.right.pressed, f.right.released), (frozenset(), frozenset()))
        self.assertTrue(f.right.down("trigger"))
        self.assertEqual(tr.update(frame(0.3, trigger=RELEASE_THRESHOLD - 0.01)).right.released, {"trigger"})

    def test_digital_edges(self):
        tr = InputTracker()
        self.assertEqual(tr.update(frame(0.0, button1=True)).right.pressed, {"button1"})
        self.assertEqual(tr.update(frame(0.1, button1=True)).right.pressed, frozenset())
        self.assertEqual(tr.update(frame(0.2, button1=False)).right.released, {"button1"})

    def test_hands_are_independent(self):
        tr = InputTracker()
        f = InputFrame(time=0.0)
        f.hands = (HandInput(grip=1.0), HandInput())
        tr.update(f)
        self.assertEqual(f.left.pressed, {"grip"})
        self.assertEqual(f.right.pressed, frozenset())

    def test_dt(self):
        tr = InputTracker()
        self.assertEqual(tr.update(frame(1.0)).dt, 0.0)
        self.assertAlmostEqual(tr.update(frame(1.25)).dt, 0.25)


if __name__ == "__main__":
    unittest.main()
