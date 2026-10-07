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


class PagesTest(unittest.TestCase):
    def test_the_four_panels_stand_on_one_side_in_rows_from_the_bottom(self):
        pages = vm.pages(4)
        self.assertEqual([(p.name, p.side, p.row) for p in pages],
                         [("Values", 4, 0), ("Number pad", 4, 1), ("Keys", 4, 2), ("Variables", 4, 3)])
        self.assertEqual(lay.Layout(pages).sides()[-1], [[0], [1], [2], [3]])

    def test_every_face_of_the_panels_is_known_and_each_is_on_a_panel_once(self):
        known = vm.faces()
        placed = [f for page in vm.pages(0) for f in page.slots if f]
        self.assertEqual(sorted(placed), sorted(known))
        self.assertEqual(len(placed), len(set(placed)))
        for fid in vm.SLIDER_IDS:
            self.assertEqual(known[fid].kind, "slider")

    def test_the_sliders_are_alone_on_their_rows(self):
        slots = vm.pages(0)[0].slots
        for row in range(lay.ROWS):
            self.assertEqual(slots[row * lay.COLS], vm.SLIDER_IDS[row])
            self.assertTrue(all(s is None for s in slots[row * lay.COLS + 1:(row + 1) * lay.COLS]))

    def test_every_key_of_the_editor_can_be_pressed_from_a_face(self):
        keys = {vm.KEYS[f][1] for page in vm.pages(0)[1:] for f in page.slots if f in vm.KEYS}
        self.assertEqual(keys, set("0123456789.+-*/()") | {"back", "unit", "enter", "clear", "step", "makevar", "unbind"})

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

    def test_a_slider_maps_its_track_to_a_range_of_round_numbers_in_steps(self):
        state = self.module.slider_states()
        self.assertEqual(state["val.0"][1:], ("A 23 mm", True))                    # the first value is picked
        self.assertEqual(state["val.1"][1:], ("B 100 mm", False))
        self.assertAlmostEqual(state["val.1"][0], 0.5)                             # 100 on a track of 0 to 200
        self.assertTrue(self.module.drag(1, 0.7))
        self.assertEqual(self.target.values["b"], 140.0)                           # 140 mm, a multiple of the step
        self.assertEqual(self.module.editor.selected, 1)                           # dragging a slider picks it
        self.assertFalse(self.module.drag(1, 0.7))

    def test_a_drag_is_one_undo_step_kept_when_the_slider_is_let_go(self):
        self.module.drag(1, 0.6)
        self.module.drag(1, 0.7)
        self.module.drag(1, 0.8)
        self.assertNotIn("commit", self.target.log)
        self.module.end_drag()
        self.assertEqual(self.target.log.count("commit"), 1)
        self.module.end_drag()
        self.assertEqual(self.target.log.count("commit"), 1)

    def test_the_ends_of_a_track_clamp_to_the_limits_of_the_value(self):
        self.module.drag(0, 0.0)
        self.assertEqual(self.target.values["a"], 1.0)                             # the lowest allowed
        self.module.drag(0, 5.0)
        self.assertEqual(self.target.values["a"], 100.0)                           # the range of 23 mm is 0 to 100 mm
        self.assertEqual(self.module.slider_states()["val.0"][0], 1.0)

    def test_a_position_has_a_track_from_minus_to_plus(self):
        self.module.drag(2, 0.5)
        self.assertEqual(self.target.values["c"], 0.0)
        self.module.drag(2, 1.0)
        self.assertEqual(self.target.values["c"], 100.0)
        self.module.drag(2, 0.0)
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

    def test_the_sliders_show_three_values_at_a_time(self):
        module = vm.ValueModule(1)
        module.open(v.ValueEditor(Wide(), step=10.0))
        self.assertEqual([module.slider_field(i) for i in range(3)], [0, 1, 2])
        self.assertEqual(module.groups, 3)
        module.activate(vm.GROUP)
        self.assertEqual([module.slider_field(i) for i in range(3)], [3, 4, 5])
        self.assertEqual(module.editor.selected, 3)                                # the first of the group is picked
        module.activate(vm.GROUP)
        self.assertEqual([module.slider_field(i) for i in range(3)], [6, None, None])
        self.assertEqual(module.slider_states()["val.1"], (0.0, "-", False))
        self.assertFalse(module.drag(1, 0.5))                                      # a slider without a value does nothing
        module.set_focus(1)
        self.assertFalse(module.engaged)
        module.activate(vm.GROUP)
        self.assertEqual(module.group, 0)

    def test_a_short_object_has_one_group_and_the_button_stays_on_it(self):
        self.assertEqual(self.module.groups, 1)
        self.module.activate(vm.GROUP)
        self.assertEqual((self.module.group, self.module.editor.selected), (0, 0))

    def test_the_keys_type_apply_and_keep_it(self):
        for fid in ("key.1", "key.2", "key.times", "key.2", "key.enter"):
            self.assertTrue(self.module.activate(fid))
        self.assertEqual(self.target.values["a"], 24.0)
        self.assertEqual(self.target.log[-1], "commit")
        self.assertTrue(self.module.is_open)                                        # there is no mode to leave

    def test_delete_clear_unit_and_the_step_key(self):
        self.module.activate("key.4")
        self.module.activate("key.5")
        self.module.activate("key.delete")
        self.assertEqual(self.module.editor.entry, "4")
        self.module.activate("key.unit")
        self.assertEqual(self.module.editor.entry, "4 mm")
        self.module.activate("key.clear")
        self.assertIsNone(self.module.editor.entry)
        self.assertEqual(self.module.labels()["key.step"], "Step 10 mm")
        self.module.activate("key.step")
        self.assertEqual(self.module.labels()["key.step"], "Step 20 mm")
        for _ in range(6):
            self.module.activate("key.step")
        self.assertEqual(self.module.labels()["key.step"], "Step 10 mm")          # round the seven steps

    def test_an_unreadable_text_is_reported_once(self):
        self.module.activate("key.open")
        self.module.activate("key.enter")
        self.assertTrue(self.step().message)
        self.assertIsNone(self.step().message)

    def test_the_titles_name_the_object_and_the_picked_value(self):
        self.assertEqual(self.module.titles(), {"Values": "Thing", "Number pad": "A: 23 mm"})
        self.module.activate("key.7")
        self.module.activate("key.point")
        self.assertEqual(self.module.titles()["Number pad"], "A: 7.|")
        for _ in range(60):
            self.module.activate("key.1")
        title = self.module.titles()["Number pad"]
        self.assertTrue(title.startswith("A: ..."))
        self.assertLess(len(title), 45)

    def test_a_slider_that_has_the_pointer_close_is_focused_and_its_value_picked(self):
        self.assertFalse(self.module.engaged)
        self.module.set_focus(1)
        self.assertTrue(self.module.engaged)
        self.assertEqual(self.module.editor.selected, 1)
        self.step(int(vm.FOCUS_HOLD / 0.02) - 2)
        self.assertTrue(self.module.engaged)                                        # it stays focused for a moment
        self.step(5)
        self.assertFalse(self.module.engaged)
        self.assertEqual(self.module.editor.selected, 1)                            # and the value stays picked
        self.module.set_focus(2)
        self.step(3)
        self.module.set_focus(2)
        self.assertTrue(self.module.engaged)

    def test_the_stick_steps_the_focused_value_and_a_push_is_one_undo_step(self):
        self.module.set_focus(1)
        self.stick(1.0)
        self.assertEqual(self.target.values["b"], 110.0)
        self.assertEqual(self.target.values["a"], 23.0)                             # only the focused value changes
        self.module.set_focus(1)
        self.stick(1.0, 25)
        self.assertGreater(self.target.values["b"], 110.0)
        self.assertNotIn("commit", self.target.log)
        self.stick(0.0)
        self.assertEqual(self.target.log.count("commit"), 1)                        # the whole push is one step

    def test_the_stick_does_nothing_without_a_focused_slider(self):
        self.stick(1.0, 3)
        self.assertEqual(self.target.values, {"a": 23.0, "b": 100.0, "c": -5.0})

    def test_the_stick_is_the_tools_again_when_the_focus_is_gone(self):
        self.module.set_focus(0)
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
        self.module.set_focus(1)
        self.stick(1.0, 3)
        self.assertEqual(self.target.values["b"], 100.0)

    def test_a_busy_tool_keeps_the_panels_from_changing_the_document(self):
        self.module.set_focus(1)
        self.stick(1.0)
        self.assertEqual(self.target.values["b"], 110.0)
        self.module.set_focus(1)
        self.stick(1.0, 40, blocked=True)
        self.assertEqual(self.target.values["b"], 110.0)
        self.assertEqual(self.target.log.count("commit"), 1)                        # what was open is kept first

    def test_the_values_follow_changes_made_elsewhere(self):
        self.target.values["a"] = 50.0
        self.step()
        self.assertEqual(self.module.slider_states()["val.0"][1], "A 50 mm")

    def test_an_object_that_is_gone_unbinds_the_panels(self):
        def gone():
            raise ReferenceError("deleted")
        self.target.fields = gone
        self.assertFalse(self.step().open)
        self.assertFalse(self.module.is_open)

    def test_closing_keeps_what_is_open_and_remembers_the_step(self):
        self.module.activate("key.step")
        self.module.drag(0, 0.5)
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
        self.module.drag(0, 0.5)
        self.module.open(v.ValueEditor(other, step=self.module.step), key="other")
        self.assertEqual(self.target.log[-1], "commit")
        self.assertEqual(self.module.key, "other")
        self.assertEqual(self.module.group, 0)


if __name__ == "__main__":
    unittest.main()


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
        self.assertEqual(self.module.slider_states()["val.0"][1], "A 23 mm = position_a")
        self.module.activate("key.unbind")
        self.assertEqual(self.module.slider_states()["val.0"][1], "A 23 mm")

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
