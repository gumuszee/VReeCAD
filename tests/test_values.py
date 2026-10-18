import unittest

import support  # noqa: F401
from freecad.VReeCAD.core import units
from freecad.VReeCAD.core import values as v


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


class VariableNameTest(unittest.TestCase):
    def test_a_label_becomes_a_lower_case_name_that_is_not_taken_and_not_a_unit(self):
        self.assertEqual(v.variable_name("Radius 1", set()), "radius_1")
        self.assertEqual(v.variable_name("Length", {"length"}), "length2")
        self.assertEqual(v.variable_name("Length", {"length", "length2"}), "length3")
        self.assertEqual(v.variable_name("m", set()), "m_value")
        self.assertEqual(v.variable_name("3d", set()), "v_3d")
        self.assertEqual(v.variable_name("  ", set()), "value")

    def test_pretty_and_single(self):
        self.assertEqual(v.pretty_expression("(Variables.width * (2 * 1 mm))"), "width * 2 mm")
        self.assertEqual(v.pretty_expression("Variables.width"), "width")
        self.assertEqual(v.pretty_expression("Variables.length * 2 + 10 * 1 mm"), "length * 2 + 10 mm")      # FreeCAD drops brackets
        self.assertEqual(v.pretty_expression("(a) + (b)"), "(a) + (b)")
        self.assertEqual(v.single_variable("Variables.width"), "width")
        self.assertEqual(v.single_variable("(Variables.width)"), "width")
        self.assertIsNone(v.single_variable("(Variables.width * 2)"))
        self.assertIsNone(v.single_variable("5 mm"))


class VariableExpressionTest(unittest.TestCase):
    WIDTH = {"width": 50.0, "depth": 30.0}

    def test_a_number_without_variables_has_no_expression(self):
        self.assertEqual(v.evaluate_bound("2*(3 cm+4)", 1.0, self.WIDTH), (68.0, None))

    def test_a_variable_is_a_length_and_the_expression_refers_to_the_sheet(self):
        value, expression = v.evaluate_bound("width", 1.0, self.WIDTH)
        self.assertEqual((value, expression), (50.0, "Variables.width"))
        value, expression = v.evaluate_bound("width * 2", 1.0, self.WIDTH)
        self.assertEqual(value, 100.0)
        self.assertEqual(expression, "(Variables.width * 2)")

    def test_a_plain_number_next_to_a_length_is_written_in_the_default_unit(self):
        value, expression = v.evaluate_bound("width + 4", 25.4, self.WIDTH)
        self.assertAlmostEqual(value, 50.0 + 4 * 25.4)
        self.assertEqual(expression, "(Variables.width + (4 * 25.4 mm))")

    def test_a_plain_result_is_a_length_in_the_default_unit(self):
        value, expression = v.evaluate_bound("depth / depth * 3", 10.0, self.WIDTH)
        self.assertEqual(value, 30.0)
        self.assertTrue(expression.endswith("* 10 mm)"), expression)

    def test_units_in_an_expression_are_written_as_units(self):
        value, expression = v.evaluate_bound("width + 2 cm", 1.0, self.WIDTH)
        self.assertEqual(value, 70.0)
        self.assertEqual(expression, "(Variables.width + (2 * 1 cm))")

    def test_unknown_names_are_refused_and_without_variables_nothing_changes(self):
        with self.assertRaises(ValueError) as raised:
            v.evaluate_bound("height * 2", 1.0, self.WIDTH)
        self.assertEqual(str(raised.exception), "Unknown variable 'height'")
        with self.assertRaises(ValueError):
            v.evaluate("width")
        with self.assertRaises(ValueError):
            v.evaluate_bound("width * width", 1.0, self.WIDTH)           # a length times a length is not a length

    def test_a_variable_is_not_a_unit_and_a_unit_cannot_follow_a_variable(self):
        with self.assertRaises(ValueError):
            v.evaluate_bound("width cm", 1.0, self.WIDTH)


class VarTarget(Target):
    """A fake object whose fields can be bound to variables of a fake document."""

    def __init__(self):
        super().__init__()
        self.vars = {"width": 80.0}
        self.bound = {}                       # field -> expression
        self.fail_bind = False

    def fields(self):
        base = super().fields()
        for field in base:
            field.expression = self.bound.get(field.name)
        return base

    def variables(self):
        return list(self.vars.items())

    def set(self, name, value):
        expression = self.bound.get(name)
        if expression is not None:
            variable = v.single_variable(expression)
            if variable is None:
                raise ValueError("Bound to " + v.pretty_expression(expression) + ": unbind it first")
            self.vars[variable] = value
            self.values[name] = value
            self.log.append(("variable", variable, value))
            return
        super().set(name, value)

    def bind(self, name, expression, value):
        if self.fail_bind:
            raise ValueError("The shape cannot take that value")
        self.bound[name] = expression
        self.values[name] = value
        self.log.append(("bind", name, expression))

    def unbind(self, name):
        self.bound.pop(name, None)
        self.log.append(("unbind", name))

    def make_variable(self, name, value):
        self.vars[name] = value
        self.log.append(("make", name, value))


class VariableEditorTest(unittest.TestCase):
    def setUp(self):
        self.target = VarTarget()
        self.editor = v.ValueEditor(self.target, step=10.0)

    def type(self, text):
        for key in text:
            self.editor.key(key)

    def test_the_editor_knows_the_variables(self):
        self.assertEqual(self.editor.variables, [("width", 80.0)])

    def test_a_variable_key_types_its_name_and_enter_binds_the_expression(self):
        self.editor.key("var:width")
        self.type("*2")
        self.assertEqual(self.editor.entry, "width*2")
        self.editor.key("enter")
        self.assertEqual(self.target.bound["a"], "(Variables.width * 2)")
        self.assertEqual(self.target.values["a"], 160.0)
        self.assertEqual(self.editor.message, "A = width * 2")
        self.assertEqual(self.target.log[-1], "commit")
        self.assertIsNotNone(self.editor.field.expression)

    def test_a_variable_after_a_digit_gets_a_space_and_an_unknown_key_does_nothing(self):
        self.type("2")
        self.editor.key("var:width")
        self.assertEqual(self.editor.entry, "2 width")
        self.assertFalse(self.editor.key("var:nothing"))
        self.assertEqual(self.editor.entry, "2 width")

    def test_a_name_that_is_not_known_is_refused_when_typed(self):
        self.editor.entry = "height"
        self.editor.key("enter")
        self.assertEqual(self.editor.message, "Unknown variable 'height'")
        self.assertEqual(self.editor.entry, "height")
        self.assertNotIn("a", self.target.bound)

    def test_a_value_the_object_refuses_stays_unbound(self):
        self.target.fail_bind = True
        self.editor.key("var:width")
        self.editor.key("enter")
        self.assertEqual(self.editor.message, "The shape cannot take that value")
        self.assertEqual(self.target.bound, {})

    def test_the_stick_and_numbers_edit_the_variable_when_the_value_is_bound_to_it_alone(self):
        self.editor.key("var:width")
        self.editor.key("enter")
        self.assertEqual(self.target.bound["a"], "Variables.width")
        self.assertTrue(self.editor.nudge(1))
        self.assertEqual(self.target.vars["width"], 90.0)
        self.type("120")
        self.editor.key("enter")
        self.assertEqual(self.target.vars["width"], 120.0)
        self.assertEqual(self.target.bound["a"], "Variables.width")

    def test_a_value_bound_to_an_expression_refuses_numbers(self):
        self.editor.key("var:width")
        self.type("*2")
        self.editor.key("enter")
        self.assertFalse(self.editor.nudge(1))
        self.assertEqual(self.editor.message, "Bound to width * 2: unbind it first")
        self.assertEqual(self.target.vars["width"], 80.0)

    def test_make_variable_names_it_after_the_value_binds_and_keeps_one_step(self):
        self.editor.select(1)
        self.editor.key("makevar")
        self.assertEqual(self.target.vars["position_b"], 100.0)          # a one letter label (X, Y, Z) is a position
        self.assertEqual(self.target.bound["b"], "Variables.position_b")
        self.assertEqual(self.editor.message, "Variable position_b = 100 mm")
        self.assertEqual(self.target.log[-3:], [("make", "position_b", 100.0), ("bind", "b", "Variables.position_b"), "commit"])
        self.assertIn(("position_b", 100.0), self.editor.variables)

    def test_make_variable_takes_a_typed_value_and_never_a_taken_name(self):
        self.editor.select(1)
        self.editor.key("makevar")
        self.editor.select(1)
        self.editor.key("unbind")
        self.type("40")
        self.editor.key("makevar")
        self.assertEqual(self.target.vars["position_b2"], 40.0)
        self.assertEqual(self.target.values["b"], 40.0)
        self.assertIsNone(self.editor.entry)

    def test_make_variable_refuses_an_expression_and_a_value_that_is_bound_to_a_variable_already(self):
        self.editor.key("var:width")
        self.type("*2")
        self.editor.key("makevar")
        self.assertEqual(self.editor.message, "Type a plain value to make a variable")
        self.editor.entry = None
        self.editor.key("var:width")
        self.editor.key("enter")
        self.editor.key("makevar")
        self.assertEqual(self.editor.message, "A is bound to width already")

    def test_a_failed_binding_after_making_the_variable_takes_everything_back(self):
        self.target.fail_bind = True
        self.editor.key("makevar")
        self.assertIn("cancel", self.target.log)
        self.assertFalse(self.editor.dirty)

    def test_unbind_frees_the_value_and_says_so_when_it_was_not_bound(self):
        self.editor.key("unbind")
        self.assertEqual(self.editor.message, "A is not bound")
        self.editor.key("var:width")
        self.editor.key("enter")
        self.editor.key("unbind")
        self.assertEqual(self.editor.message, "A is a number again")
        self.assertNotIn("a", self.target.bound)

    def test_the_variables_are_read_again_on_request(self):
        self.target.vars["depth"] = 30.0
        self.editor.refresh_variables()
        self.assertEqual(self.editor.variables, [("width", 80.0), ("depth", 30.0)])


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

    def test_the_step_is_one_of_the_value_steps_from_a_hundredth_of_a_millimetre(self):
        self.assertEqual(v.VALUE_STEPS[0], 0.01)
        self.assertEqual(v.VALUE_STEPS[-1], 100.0)
        self.assertEqual(self.editor.step, 10.0)
        self.assertTrue(self.editor.set_step(self.editor.step_index + 1))
        self.assertEqual(self.editor.step, 20.0)
        self.editor.nudge(1)
        self.assertEqual(self.target.values["a"], 40.0)
        self.assertTrue(self.editor.set_step(99))                            # clamped to the largest
        self.assertEqual(self.editor.step, 100.0)
        self.assertFalse(self.editor.set_step(99))
        self.assertTrue(self.editor.set_step(-3))
        self.assertEqual(self.editor.step, 0.01)
        self.assertEqual(v.ValueEditor(self.target, step=7.0).step, 5.0)   # the nearest step
        self.assertEqual(v.ValueEditor(self.target, step=0.001).step, 0.01)

    def test_a_small_step_moves_the_value_by_hundredths_of_a_millimetre(self):
        self.editor.set_step(0)
        self.editor.nudge(-1)
        self.assertAlmostEqual(self.target.values["a"], 22.99)
        self.editor.set_step(3)                                                # 0.1 mm
        self.editor.nudge(1)
        self.assertAlmostEqual(self.target.values["a"], 23.0)
        self.editor.nudge(1)
        self.assertAlmostEqual(self.target.values["a"], 23.1)

    def test_the_readout_shows_the_digits_of_the_step(self):
        value = v.Field("a", "A", 123.4)
        self.editor.set_step(3)                                                # 0.1 mm
        self.assertEqual(self.editor.text_of(value), "123.4 mm")
        self.editor.set_step(7)                                                # a step of a millimetre or more shows whole numbers
        self.assertEqual(self.editor.text_of(value), "123 mm")

    def test_the_picked_value_goes_round_the_values(self):
        self.assertEqual(self.editor.selected, 0)
        self.assertTrue(self.editor.select_next(-1))
        self.assertEqual(self.editor.selected, len(self.editor.fields) - 1)
        self.type("5")
        self.assertTrue(self.editor.select_next(1))
        self.assertEqual((self.editor.selected, self.editor.entry), (0, None))     # typing starts again

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
