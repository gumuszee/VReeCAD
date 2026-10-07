import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import sketchinfer as si


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


class NameTest(unittest.TestCase):
    def test_a_dimension_name_gets_a_number_when_it_is_taken(self):
        self.assertEqual(si.length_name(set()), "length")
        self.assertEqual(si.length_name({"length"}), "length2")
        self.assertEqual(si.length_name({"length", "length2"}, "radius"), "radius")


if __name__ == "__main__":
    unittest.main()
