import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import blockgeom as bg


def pyramid():
    vertices = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (5, 5, 8)]
    faces = [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    return vertices, faces


class BoxTest(unittest.TestCase):
    def test_a_box_is_a_closed_solid_with_the_volume_of_its_box(self):
        vertices, faces = bg.box((1, 2, 3), (10, 20, 30))
        self.assertIsNone(bg.validate(vertices, faces))
        self.assertAlmostEqual(bg.signed_volume(vertices, faces), 6000.0)
        self.assertEqual(len(bg.edges(faces)), 12)
        self.assertEqual(bg.bounds(vertices), ((1, 2, 3), (11, 22, 33)))

    def test_a_pyramid_is_valid_too(self):
        vertices, faces = pyramid()
        self.assertIsNone(bg.validate(vertices, faces))
        self.assertAlmostEqual(bg.signed_volume(vertices, faces), 10 * 10 * 8 / 3.0)


class FlatnessTest(unittest.TestCase):
    def test_flat_and_bent_polygons(self):
        flat = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
        self.assertEqual(bg.flatness(flat), 0.0)
        self.assertTrue(bg.is_flat(flat))
        bent = [(0, 0, 0), (10, 0, 0), (10, 10, 4), (0, 10, 0)]
        self.assertAlmostEqual(bg.flatness(bent), 0.9622504, places=5)    # the distance from the mean plane
        self.assertFalse(bg.is_flat(bent))
        self.assertEqual(bg.flatness(flat[:3]), 0.0)


class TriangulateTest(unittest.TestCase):
    def area(self, points, triangles):
        total = 0.0
        for a, b, c in triangles:
            n = bg.mu.cross(bg.mu.sub(points[b], points[a]), bg.mu.sub(points[c], points[a]))
            total += bg.mu.length(n) / 2
        return total

    def test_a_triangle_is_itself_and_a_quad_is_two_triangles_that_keep_the_winding(self):
        self.assertEqual(bg.triangulate([(0, 0, 0), (1, 0, 0), (0, 1, 0)]), [(0, 1, 2)])
        quad = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)]
        triangles = bg.triangulate(quad)
        self.assertEqual(len(triangles), 2)
        self.assertAlmostEqual(self.area(quad, triangles), 100.0)
        for a, b, c in triangles:                                   # counter-clockwise seen from +Z
            self.assertGreater(bg.mu.cross(bg.mu.sub(quad[b], quad[a]), bg.mu.sub(quad[c], quad[a]))[2], 0)

    def test_a_polygon_with_a_dent_keeps_its_area(self):
        dent = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (5, 3, 0), (0, 10, 0)]
        triangles = bg.triangulate(dent)
        self.assertEqual(len(triangles), 3)
        self.assertAlmostEqual(self.area(dent, triangles), 100.0 - 0.5 * 10 * 7)

    def test_a_bent_quad_and_a_face_seen_from_below_still_triangulate(self):
        bent = [(0, 0, 0), (10, 0, 0), (10, 10, 4), (0, 10, 0)]
        self.assertEqual(len(bg.triangulate(bent)), 2)
        below = [(0, 0, 0), (0, 10, 0), (10, 10, 0), (10, 0, 0)]
        self.assertEqual(len(bg.triangulate(below)), 2)

    def test_a_polygon_without_area_gives_nothing(self):
        self.assertEqual(bg.triangulate([(0, 0, 0), (5, 0, 0), (10, 0, 0), (7, 0, 0)]), [])
        self.assertEqual(bg.triangulate([(0, 0, 0), (1, 0, 0)]), [])


class ValidateTest(unittest.TestCase):
    def test_inside_out_open_and_broken_blocks_say_what_is_wrong(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        self.assertEqual(bg.validate(vertices, [tuple(reversed(f)) for f in faces]), "The block is inside out")
        self.assertEqual(bg.validate(vertices, faces[:5]), "The faces do not close into a solid")
        self.assertEqual(bg.validate(vertices, faces[:3]), "A block needs at least four faces")
        self.assertEqual(bg.validate(vertices[:3], faces), "A block needs at least four points")
        self.assertEqual(bg.validate(vertices, faces[:5] + [(0, 0, 1)]), "A face needs three different points")
        self.assertEqual(bg.validate(vertices, faces[:5] + [(0, 9, 1)]), "A face uses a point that does not exist")

    def test_a_flat_block_has_no_volume(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        flat = [(x, y, 0.0) for x, y, _ in vertices]
        self.assertIn(bg.validate(flat, faces), ("The block has no volume", "A face has no area"))

    def test_a_vertex_pulled_through_the_block_still_validates_only_if_it_has_volume(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        vertices = bg.move_vertex(vertices, 6, (10, 10, 14))            # a bent top: built from triangles, still a solid
        self.assertIsNone(bg.validate(vertices, faces))
        self.assertGreater(bg.signed_volume(vertices, faces), 1000.0)


class SplitTest(unittest.TestCase):
    def test_splitting_an_edge_adds_a_vertex_to_both_faces_that_share_it(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        new_vertices, new_faces, index = bg.split_edge(vertices, faces, 0, 1, (5, 0, 0))
        self.assertEqual(index, 8)
        self.assertEqual(new_vertices[8], (5, 0, 0))
        with_new = [f for f in new_faces if 8 in f]
        self.assertEqual(len(with_new), 2)
        self.assertTrue(all(len(f) == 5 for f in with_new))
        self.assertIsNone(bg.validate(new_vertices, new_faces))
        self.assertAlmostEqual(bg.signed_volume(new_vertices, new_faces), 1000.0)
        self.assertEqual(len(vertices), 8)                                   # the arguments are not changed
        self.assertEqual(faces, bg.box((0, 0, 0), (10, 10, 10))[1])

    def test_the_new_vertex_keeps_the_direction_of_the_edge_in_both_faces(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        _, new_faces, index = bg.split_edge(vertices, faces, 1, 0, (5, 0, 0))
        directed = {(f[k], f[(k + 1) % len(f)]) for f in new_faces for k in range(len(f))}
        self.assertIn((0, index), directed | {(index, 0)})
        self.assertTrue(((1, index) in directed and (index, 0) in directed) or ((0, index) in directed and (index, 1) in directed))

    def test_two_points_that_are_no_edge_are_refused(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        with self.assertRaises(ValueError):
            bg.split_edge(vertices, faces, 0, 6, (5, 5, 5))

    def test_a_split_edge_can_be_split_again_and_its_vertex_moved(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        vertices, faces, first = bg.split_edge(vertices, faces, 0, 1, (5, 0, 0))
        vertices, faces, second = bg.split_edge(vertices, faces, 0, first, (2.5, 0, 0))
        vertices = bg.move_vertex(vertices, second, (2.5, -3, 0))
        self.assertIsNone(bg.validate(vertices, faces))
        self.assertEqual(second, 9)


class NearestTest(unittest.TestCase):
    def test_nearest_vertex_edge_and_segment_point(self):
        vertices, faces = bg.box((0, 0, 0), (10, 10, 10))
        distance, index = bg.nearest_vertex(vertices, (9, 1, 0.5))
        self.assertEqual(index, 1)
        self.assertAlmostEqual(distance, (1 + 1 + 0.25) ** 0.5)
        d, pair, t, point = bg.nearest_edge(vertices, faces, (4, -1, 0))
        self.assertEqual(pair, (0, 1))
        self.assertAlmostEqual(d, 1.0)
        self.assertAlmostEqual(t, 0.4)
        self.assertEqual(point, (4.0, 0.0, 0.0))
        t, point, d = bg.nearest_on_segment((20, 0, 0), (0, 0, 0), (10, 0, 0))
        self.assertEqual((t, point, d), (1.0, (10.0, 0.0, 0.0), 10.0))
        self.assertEqual(bg.nearest_on_segment((1, 1, 1), (2, 2, 2), (2, 2, 2))[0], 0.0)


class TextTest(unittest.TestCase):
    def test_faces_survive_a_round_trip_through_text(self):
        _, faces = bg.box((0, 0, 0), (1, 1, 1))
        self.assertEqual(bg.faces_from_text(bg.faces_to_text(faces)), faces)
        self.assertEqual(bg.faces_to_text([(0, 3, 2, 1)]), ["0 3 2 1"])



class FlatFacesTest(unittest.TestCase):
    def test_a_corner_of_a_box_is_held_by_the_planes_of_its_three_faces(self):
        vertices, faces = bg.box((0, 0, 0), (100, 100, 100))
        planes = bg.face_planes(vertices, faces, 1)
        self.assertEqual(len(planes), 3)
        point = bg.constrain_to_planes((130.0, -20.0, 40.0), planes)
        self.assertEqual(tuple(round(c, 9) for c in point), (100.0, 0.0, 0.0))

    def test_a_point_on_an_edge_moves_along_the_edge_and_in_a_face_in_the_plane_of_the_face(self):
        vertices, faces = bg.box((0, 0, 0), (100, 100, 100))
        vertices, faces, index = bg.split_edge(vertices, faces, 0, 1, (50.0, 0.0, 0.0))
        planes = bg.face_planes(vertices, faces, index)
        self.assertEqual(len(planes), 2)
        point = bg.constrain_to_planes((80.0, -30.0, 10.0), planes)
        self.assertEqual(tuple(round(c, 9) for c in point), (80.0, 0.0, 0.0))
        self.assertEqual(tuple(round(c, 9) for c in bg.constrain_to_planes((80.0, -30.0, 10.0), planes[:1])[:1]), (80.0,))
        one = bg.constrain_to_planes((80.0, -30.0, 10.0), [((0.0, 0.0, 1.0), (0.0, 0.0, 5.0))])
        self.assertEqual(one, (80.0, -30.0, 5.0))

    def test_triangles_and_corners_on_a_line_set_no_plane(self):
        vertices = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (0.0, 0.0, 10.0)]
        faces = [(0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)]                    # a tetrahedron: only triangles
        self.assertEqual(bg.face_planes(vertices, faces, 0), [])
        self.assertEqual(bg.constrain_to_planes((3.0, 4.0, 5.0), []), (3.0, 4.0, 5.0))
        line = bg.face_planes([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (5.0, 5.0, 5.0)], [(0, 1, 2, 3)], 3)
        self.assertEqual(line, [])

    def test_planes_that_run_along_each_other_count_once(self):
        planes = [((0.0, 0.0, 1.0), (0.0, 0.0, 5.0)), ((0.0, 0.0, -1.0), (1.0, 1.0, 5.0)), ((1.0, 0.0, 0.0), (7.0, 0.0, 0.0))]
        self.assertEqual(bg.constrain_to_planes((1.0, 2.0, 9.0), planes), (7.0, 2.0, 5.0))


if __name__ == "__main__":
    unittest.main()
