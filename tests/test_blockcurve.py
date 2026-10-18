import unittest

import support  # noqa: F401
from freecad.VReeCAD.cad import blockcurve as bc
from freecad.VReeCAD.cad import blockgeom as bg
from freecad.VReeCAD.core import mathutil as mu


def cube():
    return bg.box((0, 0, 0), (100, 100, 100))


def close(test, a, b, places=6):
    for x, y in zip(a, b):
        test.assertAlmostEqual(x, y, places=places)


class HandlesTest(unittest.TestCase):
    def test_handles_are_written_as_text_and_read_back(self):
        handles = {(4, 5): ((20.0, -40.0, 40.0), (-20.0, -40.0, 40.0)), (1, 5): ((30.0, 0.0, 20.0), (30.0, 0.0, -20.0))}
        self.assertEqual(bc.from_text(bc.to_text(handles)), handles)
        self.assertEqual(bc.from_text(["junk", "0 1 2"]), {})

    def test_an_edge_without_handles_is_the_straight_line_from_either_end(self):
        vertices, _ = cube()
        forward = bc.poles(vertices, {}, 0, 1)
        self.assertEqual(forward[0], (0, 0, 0))
        self.assertEqual(forward[3], (100, 0, 0))
        close(self, forward[1], (100 / 3.0, 0, 0))
        self.assertEqual(bc.poles(vertices, {}, 1, 0), forward[::-1])

    def test_the_handles_of_a_curved_edge_are_read_from_the_end_the_curve_starts_at(self):
        vertices, _ = cube()
        handles = {(0, 1): ((0.0, 10.0, 0.0), (0.0, 30.0, 0.0))}
        up = bc.poles(vertices, handles, 0, 1)
        down = bc.poles(vertices, handles, 1, 0)
        self.assertEqual(up[1], (0.0, 10.0, 0.0))
        self.assertEqual(up[2], (100.0, 30.0, 0.0))
        self.assertEqual(down, up[::-1])

    def test_stored_handles_that_equal_the_straight_line_are_no_handles(self):
        vertices, _ = cube()
        curve = bc.poles(vertices, {}, 0, 1)
        self.assertEqual(bc.store_edge({}, vertices, 0, 1, curve), {})
        bent = [curve[0], mu.add(curve[1], (0, 5, 0)), curve[2], curve[3]]
        stored = bc.store_edge({}, vertices, 1, 0, bent[::-1])
        self.assertEqual(list(stored), [(0, 1)])
        self.assertEqual(bc.poles(vertices, stored, 0, 1), bent)
        self.assertEqual(bc.store_edge(stored, vertices, 0, 1, curve), {})

    def test_handles_of_edges_that_are_gone_are_left_out(self):
        vertices, faces = cube()
        handles = {(0, 1): ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0)), (0, 6): ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0)), (3, 9): ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0))}
        self.assertEqual(list(bc.usable(handles, faces, len(vertices))), [(0, 1)])      # 0-6 is a diagonal of the box, point 9 does not exist

    def test_a_removed_point_takes_its_edges_and_renumbers_the_others(self):
        handles = {(0, 1): "a", (1, 3): "b", (2, 4): "c"}
        self.assertEqual(bc.renumber_after_removal(handles, 1), {(1, 3): "c"})


class CurveTest(unittest.TestCase):
    CURVE = [(0, 0, 0), (0, 40, 30), (100, 40, 30), (100, 0, 0)]

    def test_the_curve_starts_and_ends_at_its_points_and_is_symmetric_here(self):
        close(self, bc.point_at(self.CURVE, 0.0), (0, 0, 0))
        close(self, bc.point_at(self.CURVE, 1.0), (100, 0, 0))
        close(self, bc.point_at(self.CURVE, 0.5), (50, 30, 22.5))

    def test_cutting_a_curve_gives_two_curves_that_meet_on_it_and_follow_it(self):
        first, second = bc.split_curve(self.CURVE, 0.3)
        close(self, first[3], bc.point_at(self.CURVE, 0.3))
        self.assertEqual(first[3], second[0])
        close(self, bc.point_at(first, 0.5), bc.point_at(self.CURVE, 0.15))
        close(self, bc.point_at(second, 0.5), bc.point_at(self.CURVE, 0.65))

    def test_splitting_an_edge_keeps_the_curve(self):
        vertices, _ = cube()
        handles = {(0, 1): ((0.0, 40.0, 30.0), (0.0, 40.0, 30.0))}
        middle = bc.point_at(bc.poles(vertices, handles, 0, 1), 0.4)
        vertices = vertices + [middle]
        after = bc.split_edge(vertices, handles, 0, 1, 8, 0.4)
        self.assertNotIn((0, 1), after)
        whole = bc.poles(vertices, handles, 0, 1)
        close(self, bc.point_at(bc.poles(vertices, after, 0, 8), 0.5), bc.point_at(whole, 0.2))
        close(self, bc.point_at(bc.poles(vertices, after, 8, 1), 0.5), bc.point_at(whole, 0.7))
        close(self, bc.point_at(bc.poles(vertices, after, 1, 8), 0.5), bc.point_at(whole, 0.7))      # from the other end

    def test_a_curve_is_measured_along_itself(self):
        d, t, nearest = bc.nearest_on_curve(self.CURVE, (50, 30, 22.5))
        self.assertLess(d, 0.5)
        self.assertAlmostEqual(t, 0.5, delta=0.02)
        straight_d = bg.nearest_on_segment((50, 30, 22.5), (0, 0, 0), (100, 0, 0))[2]
        self.assertGreater(straight_d, 30.0)

    def test_the_nearest_edge_follows_a_curved_edge(self):
        vertices, faces = cube()
        handles = {(0, 1): ((0.0, 40.0, 30.0), (0.0, 40.0, 30.0))}
        found = bc.nearest_edge(vertices, faces, handles, (50, 30, 22.5))
        self.assertEqual(found[1], (0, 1))
        self.assertAlmostEqual(found[2], 0.5, delta=0.02)
        straight = bc.nearest_edge(vertices, faces, {}, (50, 1, 1))
        self.assertEqual(straight[:2], bg.nearest_edge(vertices, faces, (50, 1, 1))[:2])


class BendTest(unittest.TestCase):
    def test_a_bent_curve_passes_through_the_target_and_keeps_its_ends(self):
        straight = [(0, 0, 0), (100 / 3.0, 0, 0), (200 / 3.0, 0, 0), (100, 0, 0)]
        for t in (0.2, 0.5, 0.7):
            bent = bc.bend_through(straight, t, (50, 20, 10))
            self.assertEqual((bent[0], bent[3]), (straight[0], straight[3]))
            close(self, bc.point_at(bent, bc.clamp_t(t)), (50, 20, 10))

    def test_the_middle_of_a_curve_bends_both_handles_the_same(self):
        straight = [(0, 0, 0), (100 / 3.0, 0, 0), (200 / 3.0, 0, 0), (100, 0, 0)]
        bent = bc.bend_through(straight, 0.5, (50, 0, 30))
        close(self, mu.sub(bent[1], straight[1]), mu.sub(bent[2], straight[2]))

    def test_grabbing_near_an_end_is_treated_as_grabbing_further_in(self):
        straight = [(0, 0, 0), (100 / 3.0, 0, 0), (200 / 3.0, 0, 0), (100, 0, 0)]
        bent = bc.bend_through(straight, 0.0, (10, 5, 0))
        self.assertLess(mu.length(mu.sub(bent[1], straight[1])), 200.0)
        self.assertEqual(bent[0], straight[0])


class PatchTest(unittest.TestCase):
    def test_a_face_with_straight_edges_is_the_bilinear_patch_of_its_corners(self):
        vertices, faces = cube()
        grid = bc.face_poles(vertices, {}, faces[1])
        a, b, c, d = (vertices[i] for i in faces[1])
        close(self, grid[0][0], a)
        close(self, grid[3][0], b)
        close(self, grid[3][3], c)
        close(self, grid[0][3], d)
        close(self, grid[1][1], mu.add(mu.add(mu.mul(a, 4 / 9.0), mu.mul(b, 2 / 9.0)), mu.add(mu.mul(c, 1 / 9.0), mu.mul(d, 2 / 9.0))))

    def test_the_border_of_a_patch_is_the_curves_of_its_edges(self):
        vertices, faces = cube()
        handles = {(4, 5): ((20.0, -40.0, 40.0), (-20.0, -40.0, 40.0)), (5, 6): ((0.0, 10.0, 30.0), (0.0, -10.0, 30.0))}
        face = faces[1]                                     # (4, 5, 6, 7)
        grid = bc.face_poles(vertices, handles, face)
        def same(border, expected):
            for p, q in zip(border, expected):
                close(self, p, q)
        same([grid[i][0] for i in range(4)], bc.poles(vertices, handles, 4, 5))
        same([grid[3][j] for j in range(4)], bc.poles(vertices, handles, 5, 6))
        same([grid[i][3] for i in range(4)], bc.poles(vertices, handles, 7, 6))
        same([grid[0][j] for j in range(4)], bc.poles(vertices, handles, 4, 7))

    def test_a_triangle_is_a_patch_with_one_side_shrunk_to_a_point(self):
        vertices = [(0, 0, 0), (100, 0, 0), (50, 80, 0), (50, 30, 90)]
        grid = bc.face_poles(vertices, {}, (0, 1, 2))
        self.assertEqual([grid[i][3] for i in range(4)], [(50, 80, 0)] * 4)
        close(self, grid[0][0], (0, 0, 0))
        close(self, grid[3][0], (100, 0, 0))

    def test_only_faces_of_three_or_four_points_can_have_a_curved_edge(self):
        faces = [(0, 1, 2, 3, 4), (0, 1, 5), (0, 3, 6, 7)]
        self.assertIsNone(bc.unsupported({}, faces))
        self.assertIsNone(bc.unsupported({(1, 5): ((0, 0, 1), (0, 0, 1))}, faces))
        self.assertIsNotNone(bc.unsupported({(0, 1): ((0, 0, 1), (0, 0, 1))}, faces))
        self.assertIsNone(bc.face_poles([(0, 0, 0)] * 5, {}, (0, 1, 2, 3, 4)))


if __name__ == "__main__":
    unittest.main()
