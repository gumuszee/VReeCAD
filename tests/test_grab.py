import math
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import edit
from freecad.BlocksCAD.cad import primitives as prim
from freecad.BlocksCAD.core import grab, stage
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core.navigation import WorldPose


def close(a, b, places=6):
    return all(abs(x - y) < 10 ** -places for x, y in zip(a, b))


def qdot(a, b):
    return sum(x * y for x, y in zip(a, b))


def about_z(degrees):
    return mu.quat_from_axis_angle((0.0, 0.0, 1.0), math.radians(degrees))


class SnapRotationTest(unittest.TestCase):
    def test_the_angle_is_rounded_to_the_step_and_the_axis_is_kept(self):
        axis = mu.normalize((1.0, 2.0, 2.0))
        for degrees, expected in ((0.0, 0.0), (6.0, 0.0), (8.0, 15.0), (22.0, 15.0), (23.0, 30.0), (100.0, 105.0), (179.0, 180.0)):
            snapped = grab.snap_rotation(mu.quat_from_axis_angle(axis, math.radians(degrees)))
            reference = mu.quat_from_axis_angle(axis, math.radians(expected))
            self.assertAlmostEqual(abs(qdot(snapped, reference)), 1.0, places=6, msg=f"{degrees}")

    def test_a_turn_the_long_way_round_is_the_short_way(self):
        snapped = grab.snap_rotation(mu.quat_from_axis_angle((0.0, 0.0, 1.0), math.radians(350.0)))
        self.assertAlmostEqual(abs(qdot(snapped, about_z(-15.0))), 1.0, places=6)

    def test_no_turn_stays_no_turn(self):
        self.assertEqual(grab.snap_rotation(mu.IDENTITY_QUAT), mu.IDENTITY_QUAT)
        self.assertEqual(grab.snap_rotation(about_z(3.0)), mu.IDENTITY_QUAT)
        self.assertEqual(grab.snap_rotation((0.0, 0.0, 0.0, -1.0)), mu.IDENTITY_QUAT)       # the same rotation with the other sign


class GrabTest(unittest.TestCase):
    START = grab.Grab((100.0, 0.0, 0.0), mu.IDENTITY_QUAT, (110.0, 0.0, 0.0), mu.IDENTITY_QUAT)

    def test_the_object_follows_a_move_of_the_hand(self):
        base, rotation = self.START.at((130.0, 20.0, -10.0), mu.IDENTITY_QUAT)
        self.assertTrue(close(base, (140.0, 20.0, -10.0)))
        self.assertTrue(close(rotation, mu.IDENTITY_QUAT))

    def test_a_turn_of_the_hand_turns_the_object_about_the_hand(self):
        base, rotation = self.START.at((100.0, 0.0, 0.0), about_z(90.0))
        self.assertTrue(close(base, (100.0, 10.0, 0.0)))                 # 10 mm from the hand: swung a quarter turn about it
        self.assertAlmostEqual(abs(qdot(rotation, about_z(90.0))), 1.0, places=6)

    def test_the_turn_is_taken_from_the_pose_the_hand_had_at_the_start(self):
        grabbed = grab.Grab((0.0, 0.0, 0.0), about_z(40.0), (10.0, 0.0, 0.0), mu.IDENTITY_QUAT)
        base, rotation = grabbed.at((0.0, 0.0, 0.0), about_z(40.0))      # the hand has not turned since
        self.assertTrue(close(base, (10.0, 0.0, 0.0)))
        base, rotation = grabbed.at((0.0, 0.0, 0.0), about_z(70.0))      # 30 degrees since
        self.assertAlmostEqual(abs(qdot(rotation, about_z(30.0))), 1.0, places=6)

    def test_small_turns_snap_away_and_large_ones_snap_to_steps(self):
        self.assertTrue(close(self.START.at((100.0, 0.0, 0.0), about_z(5.0))[0], (110.0, 0.0, 0.0)))
        rotation = self.START.at((100.0, 0.0, 0.0), about_z(33.0))[1]
        self.assertAlmostEqual(abs(qdot(rotation, about_z(30.0))), 1.0, places=6)

    def test_the_move_only_mode_ignores_the_turn(self):
        base, rotation = self.START.at((120.0, 0.0, 0.0), about_z(90.0), rotate=False)
        self.assertTrue(close(base, (130.0, 0.0, 0.0)))
        self.assertTrue(close(rotation, mu.IDENTITY_QUAT))

    def test_the_object_keeps_its_own_orientation_under_the_turn(self):
        grabbed = grab.Grab((0.0, 0.0, 0.0), mu.IDENTITY_QUAT, (0.0, 0.0, 0.0), about_z(30.0))
        rotation = grabbed.at((0.0, 0.0, 0.0), about_z(45.0))[1]
        self.assertAlmostEqual(abs(qdot(rotation, about_z(75.0))), 1.0, places=6)


class ClassifyTest(unittest.TestCase):
    def test_a_corner_wins_over_its_edge_and_an_edge_over_its_face(self):
        self.assertEqual(grab.classify(5.0, 5.0, 5.0, True, 1000.0), "vertex")
        self.assertEqual(grab.classify(30.0, 10.0, 10.0, True, 1000.0), "edge")
        self.assertEqual(grab.classify(80.0, 80.0, 20.0, True, 1000.0), "face")

    def test_inside_a_solid_far_from_everything_is_the_object_and_far_outside_is_nothing(self):
        self.assertEqual(grab.classify(80.0, 80.0, 80.0, True, 1000.0), "object")
        self.assertIsNone(grab.classify(80.0, 80.0, 80.0, False, 1000.0))
        self.assertIsNone(grab.classify(None, None, None, False, 1000.0))

    def test_the_reach_follows_the_scale_of_the_world(self):
        self.assertIsNone(grab.classify(None, None, 20.0, False, 500.0))       # world twice as big: 15 mm reach
        self.assertEqual(grab.classify(None, None, 20.0, False, 1000.0), "face")


class ScaleTest(unittest.TestCase):
    def test_sizes_are_scaled_and_rounded_to_the_grid(self):
        values = {"Length": 30.0, "Width": 20.0, "Height": 10.0}
        self.assertEqual(edit.scaled_values("Part::Box", values, 2.0, 10.0), {"Length": 60.0, "Width": 40.0, "Height": 20.0})
        self.assertEqual(edit.scaled_values("Part::Box", values, 1.37, 10.0), {"Length": 40.0, "Width": 30.0, "Height": 10.0})
        self.assertEqual(edit.scaled_values("Part::Box", values, 1.37, 1.0), {"Length": 41.0, "Width": 27.0, "Height": 14.0})

    def test_no_size_collapses_and_a_zero_stays_zero(self):
        self.assertEqual(edit.scaled_values("Part::Box", {"Length": 30.0, "Width": 20.0, "Height": 10.0}, 0.01, 5.0),
                         {"Length": 5.0, "Width": 5.0, "Height": 5.0})
        cone = edit.scaled_values("Part::Cone", {"Radius1": 20.0, "Radius2": 0.0, "Height": 80.0}, 0.5, 10.0)
        self.assertEqual(cone, {"Radius1": 10.0, "Radius2": 0.0, "Height": 40.0})

    def test_the_tube_of_a_torus_stays_thinner_than_its_ring(self):
        torus = edit.scaled_values("Part::Torus", {"Radius1": 12.0, "Radius2": 8.0}, 0.2, 10.0)
        self.assertLess(torus["Radius2"], torus["Radius1"])

    def test_every_shape_the_create_tool_makes_can_be_scaled_by_its_own_properties(self):
        for name in prim.SHAPES:
            spec = prim.parameters(name, (0.0, 0.0, 0.0), (40.0, 60.0, 80.0))
            self.assertTrue(edit.scalable(spec.type), name)
            self.assertTrue(set(edit.SIZE_PROPERTIES[spec.type]) <= set(spec.props), name)
        self.assertFalse(edit.scalable("Part::Feature"))


class OrientationTest(unittest.TestCase):
    def test_a_hand_pointing_forward_on_the_stage_points_along_minus_y_of_the_document(self):
        # stage -Z is forward; the document is turned so that its Z is up (stage Y) and its Y points along stage -Z
        q = stage.orientation_to_document(WorldPose(), mu.IDENTITY_QUAT)
        self.assertTrue(close(mu.rotate(q, (0.0, 0.0, -1.0)), (0.0, 1.0, 0.0)))

    def test_a_turn_of_the_hand_keeps_its_angle_and_its_axis_is_mapped_into_the_document(self):
        world = WorldPose((0.3, 1.0, -0.5), mu.quat_from_axis_angle((0.0, 1.0, 0.0), 0.8), 2.0)
        axis = mu.normalize((1.0, 0.5, -0.2))
        turn = mu.quat_from_axis_angle(axis, 0.4)
        before = stage.orientation_to_document(world, mu.quat_from_axis_angle((0.0, 0.0, 1.0), 0.3))
        after = stage.orientation_to_document(world, mu.quat_multiply(turn, mu.quat_from_axis_angle((0.0, 0.0, 1.0), 0.3)))
        relative = mu.quat_multiply(after, mu.quat_conjugate(before))
        self.assertAlmostEqual(2 * math.acos(abs(relative[3])), 0.4, places=6)
        # the stage axis, seen from the document: undo the world turn, then the quarter turn that makes Z up
        expected = mu.rotate(mu.quat_conjugate(stage.Z_UP), mu.rotate(mu.quat_conjugate(world.rotation), axis))
        direction = relative[:3] if relative[3] > 0 else tuple(-c for c in relative[:3])
        self.assertTrue(close(mu.normalize(direction), expected))


if __name__ == "__main__":
    unittest.main()
