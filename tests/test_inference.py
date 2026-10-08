import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import inference

MM = 1000.0          # one metre of hand space is a thousand millimetres of the document
FAR, NEAR_ANCHOR = (900.0, 0.0, 0.0), (30.0, 0.0, 0.0)


class SelectTest(unittest.TestCase):
    def setUp(self):
        self.inference = inference.Inference()

    def test_only_the_anchors_near_the_probe_are_offered(self):
        offered, fresh = self.inference.select([NEAR_ANCHOR, FAR, (0.0, 200.0, 0.0)], [(0.0, 0.0, 0.0)], MM, 0.0)
        self.assertEqual((offered, fresh), ([NEAR_ANCHOR], False))                    # 60 mm of hand space reach

    def test_the_reach_is_measured_in_hand_space_so_it_grows_with_the_scale_of_the_model(self):
        offered, _ = self.inference.select([(500.0, 0.0, 0.0)], [(0.0, 0.0, 0.0)], 20000.0, 0.0)
        self.assertEqual(offered, [(500.0, 0.0, 0.0)])                                # 0.06 m of hand is 1200 mm of the model
        offered, _ = self.inference.select([(500.0, 0.0, 0.0)], [(0.0, 0.0, 0.0)], 1000.0, 0.0)
        self.assertEqual(offered, [])

    def test_any_probe_may_be_near(self):
        offered, _ = self.inference.select([FAR], [(0.0, 0.0, 0.0), (890.0, 0.0, 0.0)], MM, 0.0)
        self.assertEqual(offered, [FAR])

    def test_no_probe_offers_only_what_is_acquired(self):
        self.assertEqual(self.inference.select([NEAR_ANCHOR], [], MM, 0.0), ([], False))

    def dwell(self, anchor, start, steps=30, step=0.02):
        fresh_at = None
        for k in range(steps):
            _, fresh = self.inference.select([anchor, FAR], [(anchor[0] + 3.0, 0.0, 0.0)], MM, start + k * step)
            if fresh:
                fresh_at = start + k * step
        return fresh_at

    def test_a_probe_that_stays_on_an_anchor_acquires_it_after_the_dwell_and_it_stays_offered_far_away(self):
        fresh_at = self.dwell(FAR, 0.0)
        self.assertIsNotNone(fresh_at)
        self.assertGreaterEqual(fresh_at, inference.DWELL)
        self.assertEqual(self.inference.acquired, [FAR])
        offered, fresh = self.inference.select([FAR, NEAR_ANCHOR], [(0.0, 0.0, 0.0)], MM, 1.0)
        self.assertEqual((sorted(offered), fresh), (sorted([FAR, NEAR_ANCHOR]), False))      # the far one comes along, the near one is near

    def test_a_probe_that_passes_by_acquires_nothing(self):
        for k in range(30):
            self.inference.select([FAR], [(FAR[0] - 3.0 + 40.0 * (k % 2), 0.0, 0.0)], MM, k * 0.02)
        self.assertEqual(self.inference.acquired, [])

    def test_at_most_three_are_kept_the_oldest_goes_first(self):
        anchors = [(float(x), 0.0, 0.0) for x in (0, 300, 600, 900)]
        time = 0.0
        for anchor in anchors:
            for _ in range(30):
                self.inference.select(anchors, [anchor], MM, time)
                time += 0.02
        self.assertEqual(self.inference.acquired, anchors[1:])

    def test_the_acquired_anchors_are_forgotten_after_a_pause(self):
        self.dwell(FAR, 0.0)
        self.assertTrue(self.inference.acquired)
        offered, _ = self.inference.select([FAR], [(0.0, 0.0, 0.0)], MM, 5.0)
        self.assertEqual((offered, self.inference.acquired), ([], []))

    def test_an_anchor_that_is_acquired_is_not_acquired_again(self):
        self.dwell(FAR, 0.0)
        self.assertIsNone(self.dwell(FAR, 1.0))
        self.assertEqual(self.inference.acquired, [FAR])


if __name__ == "__main__":
    unittest.main()
