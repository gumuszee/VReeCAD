import json
import unittest

import support  # noqa: F401
from freecad.VReeCAD.tools import registry
from freecad.VReeCAD.ui import help as controls_help
from freecad.VReeCAD.ui import settings as cfg


class CardTest(unittest.TestCase):
    def test_the_tool_card_lists_what_the_tool_declares_then_what_every_tool_has(self):
        title, lines = controls_help.tool_card("Move", (("Trigger", "hold: move"), ("A", "hold: lock")))
        self.assertEqual(title, "Move: tool hand")
        self.assertEqual(lines[:2], ["Trigger: hold: move", "A: hold: lock"])
        self.assertEqual([line.split(":")[0] for line in lines[2:]], ["Stick", "B", "Grip"])

    def test_a_tool_that_says_nothing_about_the_a_button_gets_the_quick_menu(self):
        _, lines = controls_help.tool_card("Create", (("Trigger", "drag"),))
        self.assertEqual(lines[:2], ["Trigger: drag", "A: hold: quick menu"])
        _, bare = controls_help.tool_card("Tool", ())
        self.assertEqual(bare[0], "A: hold: quick menu")

    def test_the_palette_card_names_the_stick_the_trigger_the_grips_the_pad_and_the_menu(self):
        title, lines = controls_help.palette_card()
        self.assertEqual(title, "Palette hand")
        self.assertEqual([line.split(":")[0] for line in lines], ["Stick", "Trigger", "Grip", "A", "D-pad", "Menu"])

    def test_every_tool_declares_what_its_trigger_does_and_the_card_fits(self):
        import freecad.VReeCAD.tools  # noqa: F401  (registers the tools)
        for name in registry.names():
            controls = registry.controls_of(name)
            self.assertTrue(controls, name)
            self.assertEqual(controls[0][0], "Trigger", name)
            _, lines = controls_help.tool_card(registry.label_of(name), controls)
            self.assertLessEqual(len(lines), 8, name)
            self.assertTrue(all(len(line) <= 48 for line in lines), name)


class StateTest(unittest.TestCase):
    def test_toggling_shows_and_hides(self):
        state = controls_help.HelpState()
        self.assertFalse(state.visible)
        self.assertTrue(state.toggle())
        self.assertFalse(state.toggle())

    def test_the_cards_go_by_themselves_and_say_so_once(self):
        state = controls_help.HelpState()
        self.assertFalse(state.update(100.0))                      # nothing is shown: nothing ends
        state.show()
        self.assertFalse(state.update(controls_help.SHOW_SECONDS - 1.0))
        self.assertTrue(state.visible)
        self.assertTrue(state.update(2.0))
        self.assertFalse(state.visible)
        self.assertFalse(state.update(2.0))

    def test_showing_again_starts_the_time_again(self):
        state = controls_help.HelpState()
        state.show()
        state.update(controls_help.SHOW_SECONDS - 1.0)
        state.show()
        self.assertFalse(state.update(controls_help.SHOW_SECONDS - 1.0))


class OnboardedTest(unittest.TestCase):
    def test_the_setting_is_kept_and_a_bad_value_is_a_flag(self):
        self.assertFalse(cfg.Settings().onboarded)
        self.assertTrue(cfg.Settings.from_json(cfg.Settings(onboarded=True).to_json()).onboarded)
        self.assertFalse(cfg.Settings.from_json(json.dumps({"tip_angle": 20})).onboarded)
        self.assertFalse(cfg.Settings.from_json(json.dumps({"onboarded": 0})).onboarded)


class HandednessSettingTest(unittest.TestCase):
    def test_the_tool_hand_is_right_unless_the_setting_says_left_and_a_bad_value_is_right(self):
        self.assertEqual(cfg.Settings().tool_hand, "right")
        self.assertEqual(cfg.Settings.from_json(cfg.Settings(tool_hand="left").to_json()).tool_hand, "left")
        self.assertEqual(cfg.Settings.from_json(json.dumps({"tool_hand": "both"})).tool_hand, "right")
        self.assertEqual(cfg.Settings.from_json(json.dumps({"tip_angle": 20})).tool_hand, "right")

    def test_small_lengths_are_decimals_of_a_millimetre_unless_the_setting_says_micrometres(self):
        self.assertEqual(cfg.Settings().sub_mm, "mm")
        self.assertEqual(cfg.Settings.from_json(cfg.Settings(sub_mm="um").to_json()).sub_mm, "um")
        self.assertEqual(cfg.Settings.from_json(json.dumps({"sub_mm": "nm"})).sub_mm, "mm")
        self.assertEqual(cfg.Settings.from_json(json.dumps({"tip_angle": 20})).sub_mm, "mm")


if __name__ == "__main__":
    unittest.main()
