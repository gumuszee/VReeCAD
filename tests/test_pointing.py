import json
import math
import os
import tempfile
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.input import Pose
from freecad.BlocksCAD.ui import pointing
from freecad.BlocksCAD.ui import settings as cfg


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
    def test_defaults_and_adjustments_are_clamped(self):
        s = cfg.Settings()
        self.assertEqual((s.pointer_mode, s.tip_angle, s.tip_length), ("laser", 0.0, 0.10))
        s.toggle_mode()
        self.assertEqual(s.pointer_mode, "tip")
        s.toggle_mode()
        self.assertEqual(s.pointer_mode, "laser")
        s.adjust_angle(3)
        self.assertEqual(s.tip_angle, 15.0)
        s.adjust_angle(-100)
        self.assertEqual(s.tip_angle, -90.0)
        s.adjust_length(-100)
        self.assertEqual(s.tip_length, 0.0)
        s.adjust_length(5)
        self.assertAlmostEqual(s.tip_length, 0.05)
        s.adjust_length(1000)
        self.assertEqual(s.tip_length, 0.4)

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
