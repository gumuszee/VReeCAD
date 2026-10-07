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

    def test_only_the_listed_axes_line_up(self):
        anchors = [(100.0, 50.0, 49.0), (0.0, 0.0, 49.0)]
        point, found = guides.align((101.0, 1.0, 49.0), (100.0, 0.0, 70.0), anchors, 5.0, axes=(0, 1))
        self.assertEqual(point, (100.0, 0.0, 70.0))                         # z is not lined up although an anchor has it
        self.assertEqual(sorted(g.axis for g in found), [0, 1])
        self.assertEqual([g.kind for g in found], ["axis", "axis"])         # the z of the anchor does not make it a point guide on two axes of three...


class AlongTest(unittest.TestCase):
    def test_the_nearest_candidate_within_reach_wins(self):
        self.assertEqual(guides.align_along(34.0, 30.0, [(37.0, "a"), (35.5, "b"), (90.0, "c")], 5.0), (35.5, "b"))

    def test_without_a_candidate_in_reach_the_grid_value_stays(self):
        self.assertEqual(guides.align_along(34.0, 30.0, [(90.0, "c")], 5.0), (30.0, None))
        self.assertEqual(guides.align_along(34.0, 30.0, [], 5.0), (30.0, None))


class PlaneTest(unittest.TestCase):
    """A plane that is the XZ plane of the document: x of the plane is X, y of the plane is Z, its z is -Y."""
    @staticmethod
    def to_local(p):
        return (p[0], p[2], -p[1])

    @staticmethod
    def to_world(p):
        return (p[0], -p[2], p[1])

    def test_anchors_are_seen_on_the_plane_once_each(self):
        flat = guides.flatten([(10.0, 5.0, 20.0), (10.0, 99.0, 20.0), (3.0, 0.0, 4.0)], self.to_local)
        self.assertEqual(flat, [(10.0, 20.0, 0.0), (3.0, 4.0, 0.0)])

    def test_a_coordinate_on_the_plane_lines_up_and_the_guide_is_in_the_document(self):
        flat = guides.flatten([(100.0, 70.0, 40.0)], self.to_local)
        point, found = guides.align_plane((101.0, 10.0), (100.0, 10.0), flat, 5.0, self.to_world, (0, 2))
        self.assertEqual(point, (100.0, 10.0))
        (guide,) = found
        self.assertEqual((guide.kind, guide.axis), ("axis", 0))
        self.assertEqual(guide.anchor, (100.0, 0.0, 40.0))
        self.assertEqual(guide.point, (100.0, 0.0, 10.0))

    def test_the_second_axis_of_the_plane_is_named_by_the_axis_of_the_document(self):
        flat = [(0.0, 40.0, 0.0)]
        _, found = guides.align_plane((60.0, 41.0), (60.0, 40.0), flat, 5.0, self.to_world, (0, 2))
        self.assertEqual([g.axis for g in found], [2])

    def test_one_anchor_on_both_axes_is_a_point_guide_on_the_plane(self):
        flat = [(30.0, 40.0, 0.0)]
        point, found = guides.align_plane((31.0, 39.0), (30.0, 40.0), flat, 5.0, self.to_world, (0, 2))
        self.assertEqual(point, (30.0, 40.0))
        self.assertEqual([(g.kind, g.axis) for g in found], [("point", -1)])

    def test_a_direction_of_a_face_that_is_no_axis_has_its_own_colour_key(self):
        flat = [(0.0, 40.0, 0.0)]
        _, found = guides.align_plane((60.0, 41.0), (60.0, 40.0), flat, 5.0, self.to_world, (3, 3))
        self.assertEqual((found[0].axis, found[0].text), (guides.OFF_AXIS, "Aligned"))
