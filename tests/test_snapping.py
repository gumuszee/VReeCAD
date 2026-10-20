import unittest

import support  # noqa: F401
from freecad.VReeCAD.core import snapping


class GridAnchorsTest(unittest.TestCase):
    def test_the_anchors_are_absolute_multiples_of_the_step(self):
        for position, _ in snapping.grid_anchors((13.0, -27.0, 4.0), 10.0):
            self.assertTrue(all(abs(c / 10.0 - round(c / 10.0)) < 1e-9 for c in position), position)

    def test_the_nearest_anchor_is_the_snapped_point_and_the_biggest(self):
        anchors = snapping.grid_anchors((13.0, -27.0, 4.0), 10.0)
        self.assertEqual(anchors[0][0], snapping.snap_point((13.0, -27.0, 4.0), 10.0))
        radii = [r for _, r in anchors]
        self.assertEqual(radii, sorted(radii, reverse=True))
        self.assertGreater(radii[0], radii[-1])

    def test_several_anchors_surround_the_pointer(self):
        anchors = snapping.grid_anchors((15.0, 15.0, 15.0), 10.0)       # in the middle of a cell: its eight corners are equally near
        self.assertGreaterEqual(len(anchors), 8)
        self.assertLessEqual(len(anchors), 64)
        positions = {p for p, _ in anchors}
        for corner in ((10.0, 10.0, 10.0), (20.0, 20.0, 20.0), (10.0, 20.0, 10.0)):
            self.assertIn(corner, positions)

    def test_the_spheres_scale_with_the_step(self):
        self.assertAlmostEqual(snapping.grid_anchors((0.0, 0.0, 0.0), 10.0)[0][1], 10.0 * snapping.ANCHOR_RADIUS[1])
        self.assertAlmostEqual(snapping.grid_anchors((0.0, 0.0, 0.0), 2.0)[0][1], 2.0 * snapping.ANCHOR_RADIUS[1])

    def test_a_plane_has_anchors_on_two_axes_only(self):
        anchors = snapping.grid_anchors((13.0, 27.0, 0.0), 10.0, dims=2)
        self.assertTrue(anchors)
        self.assertTrue(all(len(p) == 3 and p[2] == 0.0 for p, _ in anchors))
        self.assertEqual(anchors[0][0], (10.0, 30.0, 0.0))


if __name__ == "__main__":
    unittest.main()
