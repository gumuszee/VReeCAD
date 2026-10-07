import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import guides

ANCHORS = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 100.0, 50.0)]


class AlignTest(unittest.TestCase):
    def test_no_anchor_near_keeps_the_grid_point(self):
        self.assertEqual(guides.align((33.0, 47.0, 71.0), (30.0, 50.0, 70.0), ANCHORS, 5.0), ((30.0, 50.0, 70.0), []))

    def test_a_coordinate_near_an_anchor_takes_its_value_and_makes_a_guide(self):
        point, found = guides.align((101.5, 47.0, 71.0), (100.0, 50.0, 70.0), ANCHORS, 5.0)
        self.assertEqual(point, (100.0, 50.0, 70.0))
        self.assertEqual([(g.kind, g.axis) for g in found], [("axis", 0)])
        self.assertEqual(found[0].anchor[0], 100.0)

    def test_a_value_off_the_grid_is_taken_from_the_anchor(self):
        point, _ = guides.align((11.0, 3.0, 49.0), (10.0, 0.0, 50.0), [(7.0, 3.5, 49.5)], 5.0)
        self.assertEqual(point, (7.0, 3.5, 49.5))          # all three axes line up with one anchor: the point is the anchor

    def test_the_nearest_of_several_anchors_wins_on_an_axis(self):
        point, found = guides.align((101.0, 10.0, 30.0), (100.0, 10.0, 30.0), [(100.0, 0.0, 0.0), (101.5, 90.0, 90.0)], 5.0)
        self.assertEqual(point[0], 100.0)
        self.assertEqual(found[0].anchor, (100.0, 0.0, 0.0))

    def test_a_cursor_near_one_anchor_on_every_axis_is_a_point_guide(self):
        point, found = guides.align((99.0, 1.0, -2.0), (100.0, 0.0, 0.0), ANCHORS, 5.0)
        self.assertEqual(point, (100.0, 0.0, 0.0))
        self.assertEqual([(g.kind, g.axis, g.anchor) for g in found], [("point", -1, (100.0, 0.0, 0.0))])
        self.assertEqual(found[0].text, "On the point")

    def test_two_axes_from_two_anchors_make_two_guides(self):
        point, found = guides.align((101.0, 99.0, 25.0), (100.0, 100.0, 30.0), ANCHORS, 5.0)
        self.assertEqual(point, (100.0, 100.0, 30.0))
        self.assertEqual(sorted(g.axis for g in found), [0, 1])
        self.assertEqual(found[0].text, "Aligned X")

    def test_nothing_to_align_with(self):
        self.assertEqual(guides.align((1.0, 2.0, 3.0), (0.0, 0.0, 0.0), [], 5.0), ((0.0, 0.0, 0.0), []))
