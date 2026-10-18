import json
import math
import os
import tempfile
import unittest

import support  # noqa: F401
from freecad.VReeCAD.core import mathutil as mu
from freecad.VReeCAD.input import Pose
from freecad.VReeCAD.ui import pointing
from freecad.VReeCAD.ui import settings as cfg


def close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class PointingTest(unittest.TestCase):
    AIM = Pose((1.0, 1.5, -0.5), (0.0, 0.0, 0.0, 1.0), True)    # pointing along -Z

    def test_laser_starts_at_the_controller_along_the_aim(self):
        p = pointing.pointer_pose(self.AIM)
        self.assertFalse(p.tip)
        self.assertTrue(close(p.position, self.AIM.position))
        self.assertTrue(close(p.direction, (0.0, 0.0, -1.0)))

    def test_tip_is_a_point_in_front_of_the_controller(self):
        p = pointing.pointer_pose(self.AIM, "tip", 0.0, 0.12)
        self.assertTrue(p.tip)
        self.assertTrue(close(p.position, (1.0, 1.5, -0.62)))

    def test_angle_tilts_the_pointer_down(self):
        p = pointing.pointer_pose(self.AIM, "tip", 30.0, 0.10)
        self.assertTrue(close(p.direction, (0.0, -math.sin(math.radians(30)), -math.cos(math.radians(30)))))
        self.assertTrue(close(p.position, mu.add(self.AIM.position, mu.mul(p.direction, 0.10))))
        laser = pointing.pointer_pose(self.AIM, "laser", 30.0, 0.10)       # the laser tilts too, and ignores the length
        self.assertTrue(close(laser.direction, p.direction))
        self.assertTrue(close(laser.position, self.AIM.position))

    def test_the_tilt_follows_the_controller_roll(self):
        rolled = Pose((0, 0, 0), mu.quat_from_axis_angle((0, 0, -1), math.pi / 2), True)   # rolled a quarter turn about its axis
        p = pointing.pointer_pose(rolled, "tip", 30.0, 0.1)
        self.assertGreater(abs(p.direction[0]), 0.4)        # "down" for the controller is sideways now
        self.assertAlmostEqual(p.direction[1], 0.0, places=9)

    def test_an_untracked_aim_gives_an_untracked_pointer(self):
        self.assertFalse(pointing.pointer_pose(Pose(), "tip", 0.0, 0.1).tracked)


class SettingsTest(unittest.TestCase):
    def test_defaults_toggle_and_clamping(self):
        s = cfg.Settings()
        self.assertEqual((s.pointer_mode, s.tip_angle, s.tip_length), ("laser", 15.0, 0.04))
        s.toggle_mode()
        self.assertEqual(s.pointer_mode, "tip")
        s.toggle_mode()
        self.assertEqual(s.pointer_mode, "laser")
        self.assertEqual(cfg.Settings("tip", -500.0, -1.0).tip_angle, -90.0)
        self.assertEqual(cfg.Settings("tip", 500.0, 9.0).tip_length, 0.4)

    def test_the_grid_and_the_angle_step_are_shared_settings_that_snap_to_the_steps(self):
        s = cfg.Settings()
        self.assertEqual((s.grid, s.angle), (10.0, 15.0))
        s = cfg.Settings(grid=12.0, angle=40.0)
        self.assertEqual((s.grid, s.angle), (10.0, 45.0))                         # the nearest step of each list
        self.assertEqual(cfg.Settings(grid="nonsense", angle=None).grid, 10.0)
        loaded = cfg.Settings.from_json(json.dumps({"grid": 50, "angle": 90}))
        self.assertEqual((loaded.grid, loaded.angle), (50.0, 90.0))
        self.assertEqual(cfg.Settings.from_json(loaded.to_json()), loaded)

    def test_the_placement_cycles_through_snap_grid_and_free_and_the_snapping_toggles(self):
        s = cfg.Settings()
        self.assertEqual((s.placement, s.snap_source), ("snap", "guides"))
        self.assertEqual([s.cycle_placement() for _ in range(4)], ["grid", "free", "snap", "grid"])
        s.toggle_snapping()
        self.assertEqual(s.snap_source, "inference")
        self.assertEqual(cfg.Settings.from_json(s.to_json()), s)
        bad = cfg.Settings.from_json(json.dumps({"placement": "x", "snap_source": 3}))
        self.assertEqual((bad.placement, bad.snap_source), ("snap", "guides"))

    def test_json_roundtrip_and_bad_files(self):
        s = cfg.Settings("tip", 20.0, 0.15)
        self.assertEqual(cfg.Settings.from_json(s.to_json()), s)
        self.assertEqual(cfg.Settings.from_json(json.dumps({"pointer_mode": "nonsense", "tip_angle": 500})).pointer_mode, "laser")
        self.assertEqual(cfg.Settings.from_json(json.dumps({"tip_angle": 500})).tip_angle, 90.0)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            self.assertEqual(cfg.load_settings(path), cfg.Settings())          # missing
            cfg.save_settings(s, path)
            self.assertEqual(cfg.load_settings(path), s)
            with open(path, "w") as f:
                f.write("not json")
            self.assertEqual(cfg.load_settings(path), cfg.Settings())          # broken


if __name__ == "__main__":
    unittest.main()
