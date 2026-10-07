import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.core import values as v
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import value_module as vm
from test_values import Target, VarTarget


class Wide(Target):
    """Seven values, like a wedge: four sizes and three positions."""
    title = "Wedge"

    def __init__(self):
        self.values = {"s0": 100.0, "s1": 60.0, "s2": 40.0, "s3": 20.0, "pos.x": 5.0, "pos.y": -30.0, "pos.z": 0.0}
        self.log = []

    def fields(self):
        return [v.Field(n, n.upper(), x, 0.1 if not n.startswith("pos") else None) for n, x in self.values.items()]


class One(Target):
    """A single value, like a fillet."""
    title = "Fillet"

    def __init__(self):
        self.values = {"r": 5.0}
        self.log = []

    def fields(self):
        return [v.Field("r", "Radius", self.values["r"], 0.1)]


class PagesTest(unittest.TestCase):
    def test_the_four_panels_stand_on_one_side_the_value_on_top(self):
        pages = vm.pages(4)
        self.assertEqual([(p.name, p.side, p.row) for p in pages],
                         [("Value", 4, 3), ("Number pad", 4, 2), ("Keys", 4, 1), ("Variables", 4, 0)])
        self.assertEqual(lay.Layout(pages).sides()[-1], [[3], [2], [1], [0]])      # rows count from the bottom

    def test_every_face_of_the_panels_is_known_and_each_is_on_a_panel_once(self):
        known = vm.faces()
        placed = [f for page in vm.pages(0) for f in page.slots if f]
        self.assertEqual(sorted(placed), sorted(known))
        self.assertEqual(len(placed), len(set(placed)))
        for fid in vm.SLIDER_IDS:
            self.assertEqual(known[fid].kind, "slider")
        self.assertEqual(known[vm.READOUT].kind, "readout")
        self.assertEqual(known[vm.WHICH].kind, "display")

    def test_the_readout_and_the_sliders_are_alone_on_the_rows_of_the_value_panel(self):
        slots = vm.pages(0)[0].slots
        for row, fid in enumerate((vm.READOUT, vm.VALUE_SLIDER, vm.STEP_SLIDER)):
            self.assertEqual(slots[row * lay.COLS], fid)
            self.assertTrue(all(s is None for s in slots[row * lay.COLS + 1:(row + 1) * lay.COLS]))

    def test_the_selector_is_a_row_of_the_keys_panel_between_the_operators_and_clear(self):
        slots = vm.pages(0)[2].slots
        self.assertEqual(slots[:4], ["key.0", "key.point", "key.minus", "key.plus"])
        self.assertEqual(slots[8:], [vm.PREV, vm.WHICH, vm.NEXT, "key.clear"])

    def test_every_key_of_the_editor_can_be_pressed_from_a_face(self):
        keys = {vm.KEYS[f][1] for page in vm.pages(0)[1:] for f in page.slots if f in vm.KEYS}
        self.assertEqual(keys, set("0123456789.+-*/()") | {"back", "unit", "enter", "clear", "makevar", "unbind"})

    def test_the_variables_panel_has_eight_variables_a_group_key_and_the_keys_that_make_and_free(self):
        slots = vm.pages(0)[3].slots
        self.assertEqual(slots[:8], list(vm.VARIABLE_IDS))
        self.assertEqual(slots[8:], ["key.makevar", "key.unbind", vm.VARIABLE_GROUP, None])

    def test_nice_ceiling(self):
        for value, expected in ((1, 1), (1.1, 2), (2, 2), (3, 5), (5, 5), (5.1, 10), (100, 100), (101, 200), (0.04, 0.05), (999, 1000)):
            self.assertAlmostEqual(vm.nice_ceiling(value), expected, msg=str(value))


class ModuleTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.target = Target()
        self.module = vm.ValueModule(tool_hand=1)
        self.module.open(v.ValueEditor(self.target, step=10.0), key="box")
        self.step(2)

    def step(self, n=1, dt=0.02, **kw):
        result = None
        for _ in range(n):
            result = self.module.update(self.sim.frame(dt), **kw)
        return result

    def stick(self, y, frames=1, **kw):
        self.sim.set_hand(1, stick=(0.0, y))
        return self.step(frames, **kw)

    def pick(self, index):
        self.module.editor.select(index)
        self.step()

    def test_the_value_slider_maps_its_track_to_a_range_of_round_numbers_in_steps(self):
        state = self.module.slider_states()[vm.VALUE_SLIDER]
        self.assertEqual(state[1:], ("0 to 100 mm", True))                         # the track of the picked value A: 23 mm
        self.assertAlmostEqual(state[0], 0.23)
        self.assertTrue(self.module.drag(vm.VALUE_SLIDER, 0.7))
        self.assertEqual(self.target.values["a"], 70.0)                            # a multiple of the step
        self.assertFalse(self.module.drag(vm.VALUE_SLIDER, 0.7))
        self.module.activate(vm.NEXT)
        self.step()
        self.assertEqual(self.module.slider_states()[vm.VALUE_SLIDER][1], "0 to 200 mm")      # B is 100 mm
        self.assertAlmostEqual(self.module.slider_states()[vm.VALUE_SLIDER][0], 0.5)
        self.assertTrue(self.module.drag(vm.VALUE_SLIDER, 0.7))
        self.assertEqual(self.target.values["b"], 140.0)
        self.assertEqual(self.target.values["a"], 70.0)                            # only the picked value changes

    def test_the_step_slider_chooses_from_the_steps_and_names_the_step(self):
        states = self.module.slider_states()
        self.assertEqual(states[vm.STEP_SLIDER][1:], ("Step 10 mm", False))
        self.assertAlmostEqual(states[vm.STEP_SLIDER][0], 9 / 12)
        self.assertTrue(self.module.drag(vm.STEP_SLIDER, 0.0))
        self.assertEqual(self.module.editor.step, 0.01)
        self.assertEqual(self.module.slider_states()[vm.STEP_SLIDER][1], "Step 10 µm")
        self.assertFalse(self.module.drag(vm.STEP_SLIDER, -1.0))                   # beyond the end is the end
        self.assertTrue(self.module.drag(vm.STEP_SLIDER, 4 / 12))
        self.assertEqual(self.module.editor.step, 0.2)
        self.assertTrue(self.module.drag(vm.STEP_SLIDER, 9.0))
        self.assertEqual(self.module.editor.step, 100.0)
        self.assertEqual(self.target.log, [])                                      # the step slider never touches the object

    def test_the_value_slider_works_in_the_step_of_the_step_slider(self):
        self.module.drag(vm.STEP_SLIDER, 3 / 12)                                   # 0.1 mm
        self.module.drag(vm.VALUE_SLIDER, 0.2345)
        self.assertAlmostEqual(self.target.values["a"], 23.4)

    def test_the_range_follows_the_step_once_the_slider_is_let_go(self):
        self.module.drag(vm.STEP_SLIDER, 1.0)
        self.step(2, dragging=True)
        self.assertEqual(self.module._ranges[0], (0.0, 100.0))                     # not while a slider is dragged
        self.module.end_drag()
        self.step(2)
        self.assertEqual(self.module._ranges[0], (0.0, 1000.0))                    # ten steps of 100 mm

    def test_a_drag_is_one_undo_step_kept_when_the_slider_is_let_go(self):
        self.module.drag(vm.VALUE_SLIDER, 0.6)
        self.module.drag(vm.VALUE_SLIDER, 0.7)
        self.module.drag(vm.VALUE_SLIDER, 0.8)
        self.assertNotIn("commit", self.target.log)
        self.module.end_drag()
        self.assertEqual(self.target.log.count("commit"), 1)
        self.module.end_drag()
        self.assertEqual(self.target.log.count("commit"), 1)

    def test_the_ends_of_a_track_clamp_to_the_limits_of_the_value(self):
        self.module.drag(vm.VALUE_SLIDER, 0.0)
        self.assertEqual(self.target.values["a"], 1.0)                             # the lowest allowed
        self.module.drag(vm.VALUE_SLIDER, 5.0)
        self.assertEqual(self.target.values["a"], 100.0)                           # the range of 23 mm is 0 to 100 mm
        self.assertEqual(self.module.slider_states()[vm.VALUE_SLIDER][0], 1.0)

    def test_a_position_has_a_track_from_minus_to_plus(self):
        self.pick(2)
        self.assertEqual(self.module.slider_states()[vm.VALUE_SLIDER][1], "-100 to 100 mm")
        self.module.drag(vm.VALUE_SLIDER, 0.5)
        self.assertEqual(self.target.values["c"], 0.0)
        self.module.drag(vm.VALUE_SLIDER, 1.0)
        self.assertEqual(self.target.values["c"], 100.0)
        self.module.drag(vm.VALUE_SLIDER, 0.0)
        self.assertEqual(self.target.values["c"], -100.0)

    def test_the_range_does_not_change_while_a_slider_is_dragged_and_grows_afterwards(self):
        self.module.editor.select(0)
        for key in "500":
            self.module.editor.key(key)
        self.module.editor.key("enter")
        self.step(2, dragging=True)
        self.assertEqual(self.module._ranges[0], (0.0, 100.0))
        self.step(2)
        self.assertEqual(self.module._ranges[0], (0.0, 1000.0))                    # 500 mm needs the next round number up

    def test_the_selector_picks_the_next_and_the_previous_value_round_the_ends(self):
        module = vm.ValueModule(1)
        module.open(v.ValueEditor(Wide(), step=10.0))
        self.assertEqual(module.labels()[vm.WHICH], "Value 1 of 7")
        self.assertEqual((module.labels()[vm.PREV], module.labels()[vm.NEXT]), ("Previous value", "Next value"))
        self.assertTrue(module.activate(vm.NEXT))
        self.assertEqual((module.editor.selected, module.labels()[vm.WHICH]), (1, "Value 2 of 7"))
        self.assertTrue(module.activate(vm.PREV))
        self.assertTrue(module.activate(vm.PREV))
        self.assertEqual((module.editor.selected, module.labels()[vm.WHICH]), (6, "Value 7 of 7"))   # the last one
        self.assertTrue(module.activate(vm.NEXT))
        self.assertEqual(module.editor.selected, 0)

    def test_an_object_with_one_value_has_nothing_to_select(self):
        module = vm.ValueModule(1)
        module.open(v.ValueEditor(One(), step=1.0))
        labels = module.labels()
        self.assertEqual((labels[vm.PREV], labels[vm.NEXT], labels[vm.WHICH]), ("-", "-", "Value 1 of 1"))
        self.assertFalse(module.activate(vm.NEXT))
        self.assertFalse(module.activate(vm.PREV))
        self.assertEqual(module.editor.selected, 0)

    def test_the_readout_and_the_display_do_nothing_when_pressed(self):
        for fid in (vm.READOUT, vm.WHICH):
            self.assertFalse(self.module.activate(fid))

    def test_the_readout_shows_the_picked_value_and_what_is_typed(self):
        self.assertEqual(self.module.readouts()[vm.READOUT], ("A", "23 mm", False))
        self.module.activate("key.7")
        self.module.activate("key.point")
        self.assertEqual(self.module.readouts()[vm.READOUT], ("A, Enter applies", "7.|", True))
        for _ in range(60):
            self.module.activate("key.1")
        small, large, typing = self.module.readouts()[vm.READOUT]
        self.assertTrue(large.startswith("..."))
        self.assertLessEqual(len(large), vm.TYPED_CHARS + 1)
        self.assertTrue(typing)
        self.module.activate("key.clear")
        self.assertEqual(self.module.readouts()[vm.READOUT], ("A", "23 mm", False))
        self.module.activate(vm.NEXT)
        self.assertEqual(self.module.readouts()[vm.READOUT], ("B", "100 mm", False))

    def test_the_readout_of_a_zero_is_in_a_unit_that_suits_a_hundred_millimetres(self):
        self.pick(1)
        self.module.drag(vm.VALUE_SLIDER, 0.0)
        self.assertEqual(self.module.readouts()[vm.READOUT][1], "0 mm")

    def test_the_keys_type_apply_and_keep_it(self):
        for fid in ("key.1", "key.2", "key.times", "key.2", "key.enter"):
            self.assertTrue(self.module.activate(fid))
        self.assertEqual(self.target.values["a"], 24.0)
        self.assertEqual(self.target.log[-1], "commit")
        self.assertTrue(self.module.is_open)                                        # there is no mode to leave

    def test_delete_clear_and_unit(self):
        self.module.activate("key.4")
        self.module.activate("key.5")
        self.module.activate("key.delete")
        self.assertEqual(self.module.editor.entry, "4")
        self.module.activate("key.unit")
        self.assertEqual(self.module.editor.entry, "4 mm")
        self.module.activate("key.clear")
        self.assertIsNone(self.module.editor.entry)

    def test_an_unreadable_text_is_reported_once(self):
        self.module.activate("key.open")
        self.module.activate("key.enter")
        self.assertTrue(self.step().message)
        self.assertIsNone(self.step().message)

    def test_the_title_of_the_value_panel_names_the_object(self):
        self.assertEqual(self.module.titles(), {"Value": "Thing"})

    def test_the_value_slider_that_has_the_pointer_close_is_focused(self):
        self.assertFalse(self.module.engaged)
        self.module.set_focus(vm.STEP_SLIDER)
        self.assertFalse(self.module.engaged)                                       # the stick does not work the step
        self.module.set_focus(vm.VALUE_SLIDER)
        self.assertTrue(self.module.engaged)
        self.step(int(vm.FOCUS_HOLD / 0.02) - 2)
        self.assertTrue(self.module.engaged)                                        # it stays focused for a moment
        self.step(5)
        self.assertFalse(self.module.engaged)
        self.module.set_focus(vm.VALUE_SLIDER)
        self.step(3)
        self.module.set_focus(vm.VALUE_SLIDER)
        self.assertTrue(self.module.engaged)

    def test_the_stick_steps_the_picked_value_while_the_slider_is_focused_and_a_push_is_one_undo_step(self):
        self.pick(1)
        self.module.set_focus(vm.VALUE_SLIDER)
        self.stick(1.0)
        self.assertEqual(self.target.values["b"], 110.0)
        self.assertEqual(self.target.values["a"], 23.0)                             # only the picked value changes
        self.module.set_focus(vm.VALUE_SLIDER)
        self.stick(1.0, 25)
        self.assertGreater(self.target.values["b"], 110.0)
        self.assertNotIn("commit", self.target.log)
        self.stick(0.0)
        self.assertEqual(self.target.log.count("commit"), 1)                        # the whole push is one step

    def test_the_stick_uses_the_step_of_the_step_slider(self):
        self.module.drag(vm.STEP_SLIDER, 3 / 12)                                    # 0.1 mm
        self.module.set_focus(vm.VALUE_SLIDER)
        self.stick(1.0)
        self.assertAlmostEqual(self.target.values["a"], 23.1)

    def test_the_stick_does_nothing_without_a_focused_slider(self):
        self.stick(1.0, 3)
        self.assertEqual(self.target.values, {"a": 23.0, "b": 100.0, "c": -5.0})

    def test_the_stick_is_the_tools_again_when_the_focus_is_gone(self):
        self.module.set_focus(vm.VALUE_SLIDER)
        self.stick(1.0)
        self.assertEqual(self.target.values["a"], 30.0)
        self.step(int(vm.FOCUS_HOLD / 0.02) + 2)                                    # the stick is still out, the pointer has left
        self.assertFalse(self.module.engaged)
        value = self.target.values["a"]
        self.step(30)
        self.assertEqual(self.target.values["a"], value)
        self.assertEqual(self.target.log.count("commit"), 1)

    def test_a_grip_holds_the_world_and_the_stick_is_not_the_modules(self):
        self.sim.set_hand(0, grip=1.0)
        self.module.set_focus(vm.VALUE_SLIDER)
        self.stick(1.0, 3)
        self.assertEqual(self.target.values["a"], 23.0)

    def test_a_busy_tool_keeps_the_panels_from_changing_the_document(self):
        self.module.set_focus(vm.VALUE_SLIDER)
        self.stick(1.0)
        self.assertEqual(self.target.values["a"], 30.0)
        self.module.set_focus(vm.VALUE_SLIDER)
        self.stick(1.0, 40, blocked=True)
        self.assertEqual(self.target.values["a"], 30.0)
        self.assertEqual(self.target.log.count("commit"), 1)                        # what was open is kept first

    def test_the_values_follow_changes_made_elsewhere(self):
        self.target.values["a"] = 50.0
        self.step()
        self.assertEqual(self.module.readouts()[vm.READOUT][1], "50 mm")

    def test_an_object_that_is_gone_unbinds_the_panels(self):
        def gone():
            raise ReferenceError("deleted")
        self.target.fields = gone
        self.assertFalse(self.step().open)
        self.assertFalse(self.module.is_open)

    def test_closing_keeps_what_is_open_and_remembers_the_step(self):
        self.module.drag(vm.STEP_SLIDER, 10 / 12)
        self.module.drag(vm.VALUE_SLIDER, 0.5)
        self.module.close()
        self.assertFalse(self.module.is_open)
        self.assertEqual(self.target.log[-1], "commit")
        self.assertEqual(self.module.step, 20.0)
        self.assertEqual((self.module.labels(), self.module.titles()), ({}, {}))
        self.assertFalse(self.step().open)
        self.assertFalse(self.module.activate("key.1"))
        self.assertFalse(self.module.engaged)

    def test_binding_to_another_object_keeps_the_last_edit_of_the_first(self):
        other = Target()
        self.module.drag(vm.VALUE_SLIDER, 0.5)
        self.module.open(v.ValueEditor(other, step=self.module.step), key="other")
        self.assertEqual(self.target.log[-1], "commit")
        self.assertEqual(self.module.key, "other")
        self.assertEqual(self.module.editor.selected, 0)


class VariablePanelTest(unittest.TestCase):
    def setUp(self):
        self.target = VarTarget()
        self.module = vm.ValueModule(tool_hand=1)
        self.module.open(v.ValueEditor(self.target, step=10.0), key="box")

    def test_the_faces_show_the_variables_and_a_dash_where_there_is_none(self):
        labels = self.module.labels()
        self.assertEqual(labels["var.0"], "width 80 mm")
        self.assertEqual(labels["var.1"], "-")
        self.assertEqual(labels["var.7"], "-")

    def test_pressing_a_variable_types_its_name_and_an_empty_face_does_nothing(self):
        self.assertTrue(self.module.activate("var.0"))
        self.assertEqual(self.module.editor.entry, "width")
        self.assertFalse(self.module.activate("var.1"))
        self.assertEqual(self.module.editor.entry, "width")

    def test_make_variable_and_unbind_are_faces_of_the_panel(self):
        self.module.activate("key.makevar")
        self.assertEqual(self.target.bound["a"], "Variables.position_a")      # the fake labels are one letter, like X, Y and Z
        self.assertIn("Variable position_a", self.module._pending_message)
        self.assertEqual(self.module.readouts()[vm.READOUT], ("A = position_a", "23 mm", False))
        self.module.activate("key.unbind")
        self.assertEqual(self.module.readouts()[vm.READOUT], ("A", "23 mm", False))

    def test_more_variables_shows_the_next_eight(self):
        for i in range(10):
            self.target.vars[f"v{i}"] = float(i)
        self.module.editor.refresh_variables()
        self.assertEqual(len(self.module.editor.variables), 11)
        self.assertEqual(self.module.variable_at(0)[0], "width")
        self.module.activate(vm.VARIABLE_GROUP)
        self.assertEqual(self.module.variable_at(0)[0], "v7")
        self.assertEqual(self.module.labels()["var.3"], "-")
        self.module.activate(vm.VARIABLE_GROUP)
        self.assertEqual(self.module.variable_at(0)[0], "width")           # back to the first group

    def test_the_variables_are_read_again_every_half_second(self):
        sim = SimInput()
        self.target.vars["depth"] = 5.0
        for _ in range(30):
            self.module.update(sim.frame(0.02))
        self.assertEqual([n for n, _ in self.module.editor.variables], ["width", "depth"])


if __name__ == "__main__":
    unittest.main()
