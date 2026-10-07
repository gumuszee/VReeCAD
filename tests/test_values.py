import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import units
from freecad.BlocksCAD.core import values as v


class Target(v.ValueTarget):
    """A fake object: named lengths, a torus-like rule that Radius 2 stays below Radius 1."""
    title = "Thing"

    def __init__(self):
        self.values = {"a": 23.0, "b": 100.0, "c": -5.0}
        self.log = []

    def fields(self):
        return [v.Field("a", "A", self.values["a"], 1.0), v.Field("b", "B", self.values["b"], 0.0, 200.0), v.Field("c", "C", self.values["c"])]

    def set(self, name, value):
        if name == "b" and value == 123.0:
            raise ValueError("The shape cannot take that value")
        self.values[name] = value
        self.log.append(("set", name, value))

    def commit(self):
        self.log.append("commit")

    def cancel(self):
        self.log.append("cancel")


class EvaluateTest(unittest.TestCase):
    def test_plain_numbers_are_in_the_default_unit(self):
        self.assertEqual(v.evaluate("100"), 100.0)
        self.assertEqual(v.evaluate("1.5", 25.4), 1.5 * 25.4)
        self.assertEqual(v.evaluate(".5"), 0.5)

    def test_units(self):
        for text, mm in (("2 cm", 20.0), ("2cm", 20.0), ("1.5 m", 1500.0), ("1 in", 25.4), ("2 ft", 609.6), ("7 MM", 7.0)):
            self.assertAlmostEqual(v.evaluate(text), mm, msg=text)

    def test_the_four_operators_brackets_and_signs(self):
        self.assertEqual(v.evaluate("2*(3 cm+4)"), 68.0)
        self.assertEqual(v.evaluate("10/4"), 2.5)
        self.assertEqual(v.evaluate("-3 + 5"), 2.0)
        self.assertEqual(v.evaluate("2 - -3"), 5.0)
        self.assertEqual(v.evaluate("(2+3)*(4)"), 20.0)
        self.assertEqual(v.evaluate("3 cm / 2"), 15.0)

    def test_a_plain_number_added_to_a_length_is_in_the_default_unit(self):
        self.assertEqual(v.evaluate("5 + 3 cm"), 35.0)
        self.assertAlmostEqual(v.evaluate("1 + 1 in", 25.4), 50.8)

    def test_text_that_is_not_a_length_is_refused_with_a_short_message(self):
        for text in ("", "   ", "abc", "(3", "3)", "3 +", "1/0", "3 cm cm", "3 cm * 2 cm", "2 / 3 cm", "3 parsec", "1e500 * 1e500", "2 3"):
            with self.assertRaises(ValueError, msg=text) as raised:
                v.evaluate(text)
            self.assertLess(len(str(raised.exception)), 50, text)

    def test_the_default_unit_follows_the_measurement_system(self):
        self.assertEqual(v.default_unit_mm(units.METRIC_MM), 1.0)
        self.assertEqual(v.default_unit_mm(units.METRIC_CM), 10.0)
        self.assertEqual(v.default_unit_mm(units.IMPERIAL), 25.4)

    def test_the_unit_key_turns_the_unit_at_the_end(self):
        self.assertEqual(v.cycle_unit("12"), "12 mm")
        self.assertEqual(v.cycle_unit("12 mm"), "12 cm")
        self.assertEqual(v.cycle_unit("12 cm"), "12 m")
        self.assertEqual(v.cycle_unit("12 m"), "12 in")
        self.assertEqual(v.cycle_unit("12 in"), "12 mm")
        self.assertEqual(v.cycle_unit(""), "")
        self.assertEqual(v.cycle_unit("3+"), "3+")


class StepTest(unittest.TestCase):
    def test_a_step_goes_to_the_next_multiple(self):
        self.assertEqual(v.step_up(23.0, 10.0), 30.0)
        self.assertEqual(v.step_up(30.0, 10.0), 40.0)
        self.assertEqual(v.step_down(23.0, 10.0), 20.0)
        self.assertEqual(v.step_down(30.0, 10.0), 20.0)
        self.assertEqual(v.step_down(0.0, 10.0), -10.0)
        self.assertEqual(v.step_up(-5.0, 10.0), 0.0)
        self.assertAlmostEqual(v.step_up(0.3, 0.1), 0.4)


class EditorTest(unittest.TestCase):
    def setUp(self):
        self.target = Target()
        self.editor = v.ValueEditor(self.target, step=10.0)

    def type(self, text):
        for character in text:
            self.editor.key(character)

    def test_the_stick_changes_the_picked_value_by_whole_steps_and_the_object_follows(self):
        self.assertTrue(self.editor.nudge(1))
        self.assertEqual(self.target.values["a"], 30.0)
        self.editor.nudge(1)
        self.assertEqual(self.target.values["a"], 40.0)
        self.editor.nudge(-1)
        self.editor.nudge(-1)
        self.editor.nudge(-1)
        self.assertEqual(self.target.values["a"], 10.0)
        self.assertEqual(self.editor.field.value, 10.0)                     # the editor reads the object back

    def test_a_value_stops_at_its_limits(self):
        for _ in range(3):
            self.editor.nudge(-1)
        self.assertEqual(self.target.values["a"], 1.0)                     # 23, 20, 10, and not below the lowest
        self.assertFalse(self.editor.nudge(-1))
        self.editor.select(1)
        for _ in range(12):
            self.editor.nudge(1)
        self.assertEqual(self.target.values["b"], 200.0)

    def test_the_step_keys_choose_from_the_grid_steps(self):
        self.assertEqual(self.editor.step, 10.0)
        self.editor.key("step+")
        self.assertEqual(self.editor.step, 20.0)
        self.editor.nudge(1)
        self.assertEqual(self.target.values["a"], 40.0)
        for _ in range(10):
            self.editor.key("step+")
        self.assertEqual(self.editor.step, 100.0)
        for _ in range(10):
            self.editor.key("step-")
        self.assertEqual(self.editor.step, 1.0)
        self.assertEqual(v.ValueEditor(self.target, step=7.0).step, 5.0)   # the nearest grid step

    def test_typing_builds_a_text_that_enter_applies(self):
        self.type("2*3")
        self.assertEqual(self.editor.entry, "2*3")
        self.assertEqual(self.target.values["a"], 23.0)                     # nothing is applied before Enter
        self.editor.key("enter")
        self.assertEqual((self.target.values["a"], self.editor.entry), (6.0, None))

    def test_units_and_expressions_are_applied_in_millimetres(self):
        self.type("12")
        self.editor.key("unit")
        self.editor.key("unit")
        self.assertEqual(self.editor.entry, "12 cm")
        self.editor.key("enter")
        self.assertEqual(self.target.values["a"], 120.0)

    def test_delete_and_clear(self):
        self.type("123")
        self.editor.key("back")
        self.assertEqual(self.editor.entry, "12")
        self.editor.key("clear")
        self.assertIsNone(self.editor.entry)
        self.assertFalse(self.editor.key("back"))
        self.type("1")
        self.editor.key("back")
        self.assertIsNone(self.editor.entry)

    def test_text_that_cannot_be_read_stays_and_says_why(self):
        self.type("2*")
        self.editor.key("enter")
        self.assertEqual(self.editor.entry, "2*")
        self.assertTrue(self.editor.message)
        self.editor.key("clear")
        self.assertIsNone(self.editor.message)
        self.assertEqual(self.target.values["a"], 23.0)

    def test_a_value_the_object_refuses_is_reported_and_kept_as_it_was(self):
        self.editor.select(1)
        self.type("123")
        self.editor.key("enter")
        self.assertEqual(self.target.values["b"], 100.0)
        self.assertEqual(self.editor.message, "The shape cannot take that value")
        self.assertFalse(self.editor.dirty)

    def test_a_value_is_limited_to_what_the_field_allows(self):
        self.type("0")
        self.editor.key("enter")
        self.assertEqual(self.target.values["a"], 1.0)
        self.editor.select(1)
        self.type("999")
        self.editor.key("enter")
        self.assertEqual(self.target.values["b"], 200.0)

    def test_picking_another_value_drops_the_typed_text(self):
        self.type("5")
        self.assertTrue(self.editor.select(2))
        self.assertIsNone(self.editor.entry)
        self.assertFalse(self.editor.select(2))
        self.assertFalse(self.editor.select(9))                             # clamped to the last
        self.assertEqual(self.editor.selected, 2)
        self.editor.select(-3)
        self.assertEqual(self.editor.selected, 0)

    def test_enter_applies_what_is_typed_and_keeps_it_as_one_step(self):
        self.type("5")
        self.editor.key("enter")
        self.assertEqual(self.target.values["a"], 5.0)
        self.assertEqual(self.target.log[-1], "commit")
        self.assertFalse(self.editor.dirty)

    def test_enter_with_text_that_cannot_be_read_keeps_nothing(self):
        self.type("(")
        self.editor.key("enter")
        self.assertTrue(self.editor.message)
        self.assertEqual(self.target.log, [])

    def test_the_steps_of_one_gesture_are_kept_together_and_a_commit_without_a_change_does_nothing(self):
        self.editor.commit()
        self.assertEqual(self.target.log, [])
        self.editor.nudge(1)
        self.editor.nudge(1)
        self.assertTrue(self.editor.dirty)
        self.assertNotIn("commit", self.target.log)                                 # nothing is kept before the gesture ends
        self.editor.commit()
        self.assertEqual(self.target.log.count("commit"), 1)
        self.editor.commit()
        self.assertEqual(self.target.log.count("commit"), 1)

    def test_refresh_reads_the_object_again_and_keeps_the_picked_value(self):
        self.editor.select(2)
        self.target.values["c"] = 77.0
        self.editor.refresh()
        self.assertEqual((self.editor.field.value, self.editor.selected), (77.0, 2))

    def test_the_text_of_a_value_uses_the_measurement_system(self):
        self.assertEqual(self.editor.text_of(self.editor.fields[1]), "100 mm")
        imperial = v.ValueEditor(self.target, units.IMPERIAL)
        self.assertEqual(imperial.text_of(imperial.fields[1]), "3.94 in")
        imperial.select(1)
        for character in "2":
            imperial.key(character)
        imperial.key("enter")
        self.assertAlmostEqual(self.target.values["b"], 50.8)               # a plain 2 is two inches

    def test_an_unknown_key_is_an_error(self):
        with self.assertRaises(ValueError):
            self.editor.key("x")

    def test_the_text_has_a_limit(self):
        for _ in range(60):
            self.editor.key("1")
        self.assertEqual(len(self.editor.entry), v.MAX_ENTRY)


if __name__ == "__main__":
    unittest.main()
