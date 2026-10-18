import math
import unittest

import support  # noqa: F401
from freecad.VReeCAD.cad import sketchinfer as si


class DirectionTest(unittest.TestCase):
    def test_a_line_along_an_axis_is_horizontal_or_vertical(self):
        self.assertEqual(si.direction((0, 5), (30, 5)), "horizontal")
        self.assertEqual(si.direction((4, 0), (4, -30)), "vertical")
        self.assertIsNone(si.direction((0, 0), (30, 10)))
        self.assertIsNone(si.direction((3, 3), (3, 3)))                      # a point is neither


class PointRelationTest(unittest.TestCase):
    def test_the_origin_a_point_a_line_a_circle_and_the_axes_in_that_order(self):
        existing = si.Existing(points=[(0, 2, (50.0, 20.0))], lines=[(1, (0.0, 40.0), (100.0, 40.0))], circles=[(2, (80.0, 80.0), 10.0)])
        self.assertEqual(si.point_relation(5, 1, (0.0, 0.0), existing), ("Coincident", 5, 1, -1, 1))
        self.assertEqual(si.point_relation(5, 2, (50.0, 20.0), existing), ("Coincident", 5, 2, 0, 2))
        self.assertEqual(si.point_relation(5, 1, (30.0, 40.0), existing), ("PointOnObject", 5, 1, 1))
        self.assertEqual(si.point_relation(5, 1, (90.0, 80.0), existing), ("PointOnObject", 5, 1, 2))
        self.assertEqual(si.point_relation(5, 1, (30.0, 0.0), existing), ("PointOnObject", 5, 1, -1))
        self.assertEqual(si.point_relation(5, 1, (0.0, 30.0), existing), ("PointOnObject", 5, 1, -2))
        self.assertIsNone(si.point_relation(5, 1, (33.0, 22.0), existing))

    def test_the_end_of_a_line_is_not_on_that_line_and_a_point_of_the_new_geometry_is_not_its_own_partner(self):
        existing = si.Existing(points=[(5, 1, (10.0, 10.0))], lines=[(5, (10.0, 10.0), (50.0, 10.0))])
        self.assertIsNone(si.point_relation(5, 2, (30.0, 10.0), existing, allow_axes=False))

    def test_a_point_on_the_end_of_a_line_is_coincident_not_on_object(self):
        existing = si.Existing(points=[(0, 2, (50.0, 10.0))], lines=[(0, (10.0, 10.0), (50.0, 10.0))])
        self.assertEqual(si.point_relation(1, 1, (50.0, 10.0), existing), ("Coincident", 1, 1, 0, 2))


class LineTest(unittest.TestCase):
    def test_a_free_line_has_no_constraints(self):
        self.assertEqual(si.infer_line(0, (10.0, 10.0), (50.0, 30.0), si.Existing()), [])

    def test_a_horizontal_line_is_horizontal_and_its_end_on_an_axis_is_not_tied_twice(self):
        self.assertEqual(si.infer_line(0, (10.0, 0.0), (60.0, 0.0), si.Existing()), [("Horizontal", 0), ("PointOnObject", 0, 1, -1)])
        self.assertEqual(si.infer_line(0, (0.0, 0.0), (0.0, 40.0), si.Existing()), [("Vertical", 0), ("Coincident", 0, 1, -1, 1)])

    def test_a_chained_line_starts_coincident_with_the_end_of_the_last(self):
        existing = si.Existing(points=[(0, 1, (10.0, 10.0)), (0, 2, (60.0, 10.0))], lines=[(0, (10.0, 10.0), (60.0, 10.0))])
        self.assertEqual(si.infer_line(1, (60.0, 10.0), (60.0, 50.0), existing), [("Vertical", 1), ("Coincident", 1, 1, 0, 2)])

    def test_a_closing_line_is_coincident_at_both_ends(self):
        existing = si.Existing(points=[(0, 1, (10.0, 10.0)), (0, 2, (60.0, 10.0)), (1, 2, (60.0, 50.0))])
        self.assertEqual(si.infer_line(2, (60.0, 50.0), (10.0, 10.0), existing), [("Coincident", 2, 1, 1, 2), ("Coincident", 2, 2, 0, 1)])

    def test_a_line_whose_ends_are_the_same_point_is_not_constrained_twice(self):
        self.assertEqual(si.infer_line(0, (0.0, 0.0), (0.0, 0.0), si.Existing()), [("Coincident", 0, 1, -1, 1)])


class RectangleTest(unittest.TestCase):
    def test_the_corners_run_counter_clockwise_from_the_lower_left_whatever_the_drag(self):
        self.assertEqual(si.rectangle((60.0, 40.0), (10.0, 10.0)), [(10.0, 10.0), (60.0, 10.0), (60.0, 40.0), (10.0, 40.0)])

    def test_a_rectangle_is_four_joined_lines_two_horizontal_and_two_vertical(self):
        corners, constraints = si.infer_rectangle(3, (10.0, 10.0), (60.0, 40.0), si.Existing())
        self.assertEqual(len(corners), 4)
        self.assertEqual([c for c in constraints if c[0] == "Coincident"], [("Coincident", 3 + i, 2, 3 + (i + 1) % 4, 1) for i in range(4)])
        self.assertEqual([c for c in constraints if c[0] == "Horizontal"], [("Horizontal", 3), ("Horizontal", 5)])
        self.assertEqual([c for c in constraints if c[0] == "Vertical"], [("Vertical", 4), ("Vertical", 6)])
        self.assertEqual(len(constraints), 8)

    def test_a_corner_on_the_origin_or_on_an_axis_is_tied_to_it(self):
        _, constraints = si.infer_rectangle(0, (0.0, 0.0), (60.0, 40.0), si.Existing())
        self.assertIn(("Coincident", 0, 1, -1, 1), constraints)
        _, constraints = si.infer_rectangle(0, (20.0, 0.0), (60.0, 40.0), si.Existing())
        self.assertIn(("PointOnObject", 0, 1, -1), constraints)
        self.assertEqual(len(constraints), 9)

    def test_the_far_corner_is_tied_to_a_point_it_lands_on(self):
        existing = si.Existing(points=[(0, 2, (60.0, 40.0))])
        _, constraints = si.infer_rectangle(1, (10.0, 10.0), (60.0, 40.0), existing)
        self.assertIn(("Coincident", 2, 2, 0, 2), constraints)


class CircleTest(unittest.TestCase):
    def test_the_centre_is_tied_to_what_it_touches(self):
        self.assertEqual(si.infer_circle(0, (20.0, 20.0), 5.0, si.Existing()), [])
        self.assertEqual(si.infer_circle(0, (0.0, 0.0), 5.0, si.Existing()), [("Coincident", 0, 3, -1, 1)])
        self.assertEqual(si.infer_circle(1, (20.0, 20.0), 5.0, si.Existing(points=[(0, 2, (20.0, 20.0))])), [("Coincident", 1, 3, 0, 2)])


class ArcTest(unittest.TestCase):
    def test_the_arc_through_three_points_has_their_circle(self):
        centre, radius, first, last, p_first, p_last = si.arc_through((0.0, 0.0), (60.0, 0.0), (30.0, 30.0))
        self.assertAlmostEqual(centre[0], 30.0)
        self.assertAlmostEqual(centre[1], 0.0)
        self.assertAlmostEqual(radius, 30.0)
        self.assertEqual((p_first, p_last), ((60.0, 0.0), (0.0, 0.0)))        # over the top it runs counter-clockwise from the right end
        self.assertAlmostEqual(first, 0.0)
        self.assertAlmostEqual(last, 3.141592653589793)

    def test_the_other_side_swaps_the_ends_and_the_arc_keeps_its_middle(self):
        centre, radius, first, last, p_first, p_last = si.arc_through((0.0, 0.0), (60.0, 0.0), (30.0, -30.0))
        self.assertEqual((p_first, p_last), ((0.0, 0.0), (60.0, 0.0)))
        self.assertGreater(last, first)
        mid = (first + last) / 2.0
        self.assertAlmostEqual(centre[0] + radius * 0.0 + radius * math.cos(mid), 30.0)
        self.assertAlmostEqual(centre[1] + radius * math.sin(mid), -30.0)

    def test_points_on_a_line_make_no_arc(self):
        self.assertIsNone(si.arc_through((0.0, 0.0), (60.0, 0.0), (30.0, 0.0)))
        self.assertIsNone(si.arc_through((0.0, 0.0), (0.0, 0.0), (30.0, 5.0)))

    def test_the_points_of_an_arc_run_from_the_first_angle_to_the_last(self):
        points = si.arc_points((0.0, 0.0), 10.0, 0.0, 3.141592653589793, 4)
        self.assertEqual(len(points), 5)
        self.assertAlmostEqual(points[0][0], 10.0)
        self.assertAlmostEqual(points[2][1], 10.0)
        self.assertAlmostEqual(points[4][0], -10.0)

    def test_the_ends_of_an_arc_are_tied_to_what_they_touch(self):
        existing = si.Existing(points=[(0, 2, (60.0, 0.0))])
        self.assertEqual(si.infer_arc(1, (30.0, 0.0), (0.0, 0.0), (60.0, 0.0), existing),
                         [("Coincident", 1, 1, -1, 1), ("Coincident", 1, 2, 0, 2)])
        self.assertEqual(si.infer_arc(1, (30.0, 0.0), (10.0, 10.0), (50.0, 10.0), existing), [])


class RelationTest(unittest.TestCase):
    ARC = si.Existing(points=[(0, 1, (60.0, 30.0)), (0, 2, (0.0, 30.0)), (0, 3, (30.0, 30.0))], arcs=[(0, (30.0, 30.0), 30.0, 0.0, math.pi)])

    def test_a_line_that_leaves_the_end_of_an_arc_along_it_is_tangent_to_it(self):
        self.assertEqual(si.infer_line(1, (0.0, 30.0), (0.0, 10.0), self.ARC), [("Vertical", 1), ("Tangent", 1, 1, 0, 2)])

    def test_a_line_that_leaves_across_the_arc_is_only_joined_to_it(self):
        self.assertEqual(si.infer_line(1, (0.0, 30.0), (20.0, 10.0), self.ARC), [("Coincident", 1, 1, 0, 2)])

    def test_an_arc_that_starts_along_a_line_is_tangent_to_it(self):
        line = si.Existing(points=[(0, 1, (0.0, 0.0)), (0, 2, (0.0, 30.0))], lines=[(0, (0.0, 0.0), (0.0, 30.0))])
        self.assertEqual(si.infer_arc(1, (30.0, 30.0), (60.0, 30.0), (0.0, 30.0), line), [("Tangent", 1, 2, 0, 2)])

    def test_two_lines_end_to_end_are_not_made_tangent(self):
        line = si.Existing(points=[(0, 1, (10.0, 10.0)), (0, 2, (30.0, 30.0))], lines=[(0, (10.0, 10.0), (30.0, 30.0))])
        self.assertEqual(si.infer_line(1, (30.0, 30.0), (50.0, 50.0), line), [("Coincident", 1, 1, 0, 2), ("Parallel", 1, 0), ("Equal", 1, 0)])

    def test_a_line_along_or_across_a_slanted_line_is_parallel_or_perpendicular_to_it(self):
        slanted = si.Existing(points=[(0, 1, (0.0, 5.0)), (0, 2, (40.0, 25.0))], lines=[(0, (0.0, 5.0), (40.0, 25.0))])
        self.assertEqual(si.infer_line(1, (10.0, 50.0), (50.0, 70.0), slanted), [("Parallel", 1, 0), ("Equal", 1, 0)])    # as long as it, too
        self.assertEqual(si.infer_line(1, (10.0, 50.0), (30.0, 10.0), slanted), [("Perpendicular", 1, 0), ("Equal", 1, 0)])
        self.assertEqual(si.infer_line(1, (10.0, 50.0), (70.0, 80.0), slanted), [("Parallel", 1, 0)])                  # parallel and longer
        self.assertEqual(si.infer_line(1, (10.0, 50.0), (30.0, 25.0), slanted), [])

    def test_a_line_that_is_tied_at_both_ends_gets_no_further_relation(self):
        slanted = si.Existing(points=[(0, 1, (0.0, 5.0)), (0, 2, (40.0, 25.0)), (1, 1, (10.0, 50.0)), (1, 2, (50.0, 70.0))],
                              lines=[(0, (0.0, 5.0), (40.0, 25.0))])
        self.assertEqual(si.infer_line(2, (10.0, 50.0), (50.0, 70.0), slanted), [("Coincident", 2, 1, 1, 1), ("Coincident", 2, 2, 1, 2)])

    def test_a_line_along_an_axis_is_related_to_a_slanted_line_by_nothing(self):
        slanted = si.Existing(lines=[(0, (0.0, 5.0), (40.0, 25.0))])
        self.assertEqual(si.infer_line(1, (10.0, 50.0), (50.0, 50.0), slanted), [("Horizontal", 1)])


class EqualTest(unittest.TestCase):
    LINES = si.Existing(lines=[(0, (0.0, 0.0), (30.0, 0.0)), (1, (0.0, 10.0), (0.0, 50.0))])

    def test_a_line_as_long_as_another_is_equal_to_the_first_such_line(self):
        self.assertEqual(si.infer_line(2, (10.0, 20.0), (40.0, 20.0), self.LINES), [("Horizontal", 2), ("Equal", 2, 0)])
        self.assertEqual(si.infer_line(2, (10.0, 20.0), (10.0, 60.0), si.Existing(lines=self.LINES.lines)), [("Vertical", 2), ("Equal", 2, 1)])

    def test_a_line_of_another_length_gets_none(self):
        self.assertEqual(si.infer_line(2, (10.0, 20.0), (45.0, 20.0), self.LINES), [("Horizontal", 2)])

    def test_nothing_is_added_that_would_leave_the_line_over_constrained(self):
        tied = si.Existing(points=[(0, 2, (30.0, 0.0)), (2, 1, (10.0, 20.0))], lines=self.LINES.lines)
        full = si.infer_line(3, (30.0, 0.0), (60.0, 0.0), tied)                         # horizontal, joined at its start: three of four degrees
        self.assertEqual(full, [("Horizontal", 3), ("Coincident", 3, 1, 0, 2), ("Equal", 3, 0)])
        both = si.Existing(points=[(0, 2, (30.0, 0.0)), (4, 1, (60.0, 0.0))], lines=self.LINES.lines)
        self.assertEqual(si.infer_line(3, (30.0, 0.0), (60.0, 0.0), both),
                         [("Horizontal", 3), ("Coincident", 3, 1, 0, 2), ("Coincident", 3, 2, 4, 1)])    # both ends are joined: Equal would be redundant


class NameTest(unittest.TestCase):
    def test_a_dimension_name_gets_a_number_when_it_is_taken(self):
        self.assertEqual(si.length_name(set()), "length")
        self.assertEqual(si.length_name({"length"}), "length2")
        self.assertEqual(si.length_name({"length", "length2"}, "radius"), "radius")


if __name__ == "__main__":
    unittest.main()
