import unittest

import support  # noqa: F401
from freecad.BlocksCAD import profiles

FRAME = "/interaction_profiles/valve/frame_controller_valve"
QUEST = "/interaction_profiles/oculus/touch_controller"


class ProfilesTest(unittest.TestCase):
    def test_frame_left_uses_dpad_as_buttons(self):
        left = profiles.bindings(FRAME, "left")
        self.assertEqual(left["button1"], "/user/hand/left/input/dpad_up/click")
        self.assertEqual(left["button2"], "/user/hand/left/input/dpad_down/click")
        self.assertEqual(left["aux1"], "/user/hand/left/input/dpad_left/click")
        self.assertEqual(left["aux2"], "/user/hand/left/input/dpad_right/click")
        self.assertEqual(left["grip"], "/user/hand/left/input/squeeze/value")

    def test_frame_right_uses_face_buttons(self):
        right = profiles.bindings(FRAME, "right")
        self.assertEqual(right["button1"], "/user/hand/right/input/a/click")
        self.assertEqual(right["button2"], "/user/hand/right/input/b/click")

    def test_quest_left_uses_x_y(self):
        left = profiles.bindings(QUEST, "left")
        self.assertEqual((left["button1"], left["button2"]),
                         ("/user/hand/left/input/x/click", "/user/hand/left/input/y/click"))

    def test_every_profile_binds_the_core_inputs_for_both_hands(self):
        core = {"aim_pose", "grip_pose", "haptic", "trigger", "grip", "stick_x", "stick_y", "button1", "button2"}
        for profile in profiles.PROFILES:
            for side in ("left", "right"):
                bound = profiles.bindings(profile, side)
                self.assertTrue(core <= set(bound), f"{profile} {side} lacks {core - set(bound)}")
                for action, path in bound.items():
                    self.assertTrue(path.startswith(f"/user/hand/{side}/"), path)
                    self.assertIn(action, profiles.ACTIONS)

    def test_availability_depends_on_api_and_extension(self):
        base = profiles.available_profiles((1, 0), ())
        self.assertNotIn(FRAME, base)
        self.assertNotIn("/interaction_profiles/meta/touch_pro_controller", base)
        self.assertIn(FRAME, profiles.available_profiles((1, 0), ("XR_VALVE_frame_controller_interaction",)))
        self.assertIn("/interaction_profiles/meta/touch_pro_controller", profiles.available_profiles((1, 1), ()))


if __name__ == "__main__":
    unittest.main()
