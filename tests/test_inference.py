import unittest

import support  # noqa: F401
from freecad.VReeCAD.core import inference

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


EDGE_X = ((0.0, 0.0, 0.0), (100.0, 0.0, 0.0))
EDGE_Y = ((0.0, 0.0, 0.0), (0.0, 100.0, 0.0))


def features(*edges):
    anchors = []
    for a, b in edges:
        for p in (a, b, tuple((x + y) / 2 for x, y in zip(a, b))):
            if p not in anchors:
                anchors.append(p)
    return inference.Features(anchors, list(edges))


class SnapTest(unittest.TestCase):
    def setUp(self):
        self.snapper = inference.Snapper()
        self.model = features(EDGE_X, EDGE_Y)

    def test_a_vertex_and_a_middle_are_snapped_to_with_the_kind_that_says_what_drives_it(self):
        snap = self.snapper.snap_to((4.0, 6.0, 0.0), self.model, MM)
        self.assertEqual((snap.point, snap.kind, snap.edge), ((0.0, 0.0, 0.0), "vertex", None))
        self.snapper.reset()
        snap = self.snapper.snap_to((52.0, 5.0, 0.0), self.model, MM)
        self.assertEqual((snap.point, snap.kind, snap.edge), ((50.0, 0.0, 0.0), "middle", EDGE_X))

    def test_an_edge_is_snapped_to_at_its_nearest_point_within_its_own_reach(self):
        snap = self.snapper.snap_to((30.0, 9.0, 4.0), self.model, MM)
        self.assertEqual((snap.kind, snap.edge), ("edge", EDGE_X))
        self.assertEqual(snap.point, (30.0, 0.0, 0.0))
        self.snapper.reset()
        self.assertIsNone(self.snapper.snap_to((30.0, 12.0, 0.0), self.model, MM))        # the reach of an edge is smaller than that of a vertex
        self.assertIsNone(self.snapper.snap_to((300.0, 300.0, 0.0), self.model, MM))

    def test_a_vertex_wins_over_an_edge_that_is_nearer(self):
        snap = self.snapper.snap_to((3.0, 0.5, 0.0), self.model, MM)                  # on both an edge and near the corner
        self.assertEqual((snap.kind, snap.point), ("vertex", (0.0, 0.0, 0.0)))
        self.snapper.reset()
        self.snapper.snap_to((30.0, 2.0, 0.0), self.model, MM)                         # held on the edge
        snap = self.snapper.snap_to((2.0, 2.0, 0.0), self.model, MM)
        self.assertEqual(snap.kind, "vertex")                                          # the vertex takes over from the held edge

    def test_a_feature_is_held_until_the_cursor_is_much_further_away(self):
        self.snapper.snap_to((30.0, 8.0, 0.0), self.model, MM)
        snap = self.snapper.snap_to((30.0, 15.0, 0.0), self.model, MM)                 # 15 mm: beyond the reach of 11 mm, within the hold of 17.6 mm
        self.assertEqual((snap.kind, snap.point), ("edge", (30.0, 0.0, 0.0)))
        self.assertIsNone(self.snapper.snap_to((30.0, 25.0, 0.0), self.model, MM))
        self.assertIsNone(self.snapper.held)
        self.assertIsNone(self.snapper.snap_to((30.0, 15.0, 0.0), self.model, MM))     # and it has to be caught again

    def test_a_held_vertex_is_kept_beyond_its_reach_and_the_nearer_of_two_takes_over(self):
        lone = inference.Features([(0.0, 0.0, 0.0)], [])
        self.assertEqual(self.snapper.snap_to((10.0, 0.0, 0.0), lone, MM).point, (0.0, 0.0, 0.0))
        self.assertEqual(self.snapper.snap_to((20.0, 0.0, 0.0), lone, MM).point, (0.0, 0.0, 0.0))      # held: 20 mm is within 1.6 times 14 mm
        self.assertIsNone(self.snapper.snap_to((30.0, 0.0, 0.0), lone, MM))
        self.snapper.reset()
        model = features(((0.0, 0.0, 0.0), (20.0, 0.0, 0.0)))
        self.assertEqual(self.snapper.snap_to((4.0, 2.0, 0.0), model, MM).point, (0.0, 0.0, 0.0))
        self.assertEqual(self.snapper.snap_to((9.0, 2.0, 0.0), model, MM).point, (10.0, 0.0, 0.0))       # the middle is nearer now

    def test_the_reaches_are_measured_in_hand_space(self):
        self.assertIsNone(self.snapper.snap_to((30.0, 9.0, 0.0), self.model, 500.0))      # 9 mm of the document are 18 mm of hand space
        self.assertIsNotNone(self.snapper.snap_to((30.0, 9.0, 0.0), self.model, 2000.0))

    def test_describe_tells_a_middle_from_a_vertex_by_its_place(self):
        model = features(EDGE_X)
        self.assertEqual(model.describe((50.0, 0.0, 0.0)).kind, "middle")
        self.assertEqual(model.describe((100.0, 0.0, 0.0)).kind, "vertex")
        self.assertEqual(model.describe((50.0000004, 0.0, 0.0)).edge, EDGE_X)


class SegmentTest(unittest.TestCase):
    def test_the_nearest_point_of_a_segment_is_clamped_to_its_ends(self):
        self.assertEqual(inference.nearest_on_segment((50, 10, 0), *EDGE_X), ((50.0, 0.0, 0.0), 10.0))
        self.assertEqual(inference.nearest_on_segment((-30, 40, 0), *EDGE_X), ((0.0, 0.0, 0.0), 50.0))
        self.assertEqual(inference.nearest_on_segment((7, 0, 0), (5, 5, 5), (5, 5, 5))[0], (5, 5, 5))


if __name__ == "__main__":
    unittest.main()
