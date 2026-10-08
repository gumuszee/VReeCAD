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


def page(name, layout=None):
    return next(p for p in (layout or vm.default_layout()).pages if p.name == name)


class PagesTest(unittest.TestCase):
    def test_the_default_layout_puts_one_panel_on_every_side_like_the_palette(self):
        layout = vm.default_layout()
        self.assertEqual([(p.name, p.side, p.row) for p in layout.pages],
                         [("Values", 0, 0), ("Number pad", 1, 0), ("Keys", 2, 0), ("Variables", 3, 0)])
        self.assertEqual(layout.sides(), [[[0]], [[1]], [[2]], [[3]]])

    def test_the_value_panel_is_pinned_it_stands_on_no_side_and_is_the_page_after_the_others(self):
        layout = vm.default_layout()
        shown = vm.shown_layout(layout)
        self.assertEqual([(p.name, p.pinned) for p in shown.pages[len(layout.pages):]], [("Value", True)])
        self.assertEqual(shown.sides(), layout.sides())                               # it is on none of the sides
        self.assertTrue(all(p.name != "Value" and not p.pinned for p in layout.pages))   # it is no part of what the user rearranges
        self.assertEqual(sum(p.pinned for p in shown.pages), 1)

    def test_rearranging_the_panels_leaves_the_pinned_panel_alone(self):
        layout = vm.default_layout()
        layout.move_page(3, 0, 0, 0, False)                                           # the Variables next to the Values panel
        self.assertEqual(len(layout.sides()), 3)                                       # the Variables joined the Values panel on one side
        shown = vm.shown_layout(layout)
        self.assertEqual(shown.pages[-1].name, "Value")
        self.assertEqual(len(shown.sides()), len(layout.sides()))

    def test_every_face_of_the_panels_is_known_and_each_is_on_a_panel_once(self):
        known = vm.faces()
        shown = vm.shown_layout(vm.default_layout())
        placed = [f for page in shown.pages for f in page.slots if f]
        self.assertEqual(sorted(placed), sorted(known))
        self.assertEqual(len(placed), len(set(placed)))
        for fid in vm.SLIDER_IDS:
            self.assertEqual(known[fid].kind, "slider")
        self.assertEqual(known[vm.READOUT].kind, "readout")
        self.assertEqual(known[vm.WHICH].kind, "display")

    def test_the_readout_and_the_sliders_are_alone_on_the_rows_of_the_value_panel(self):
        slots = vm.shown_layout(vm.default_layout()).pages[-1].slots
        for row, fid in enumerate((vm.READOUT, vm.VALUE_SLIDER, vm.STEP_SLIDER)):
            self.assertEqual(slots[row * lay.COLS], fid)
            self.assertTrue(all(s is None for s in slots[row * lay.COLS + 1:(row + 1) * lay.COLS]))

    def test_the_selector_is_a_row_of_the_keys_panel_between_the_operators_and_clear(self):
        slots = page("Keys").slots
        self.assertEqual(slots[:4], ["key.0", "key.point", "key.minus", "key.plus"])
        self.assertEqual(slots[8:], [vm.PREV, vm.WHICH, vm.NEXT, "key.clear"])

    def test_every_key_of_the_editor_can_be_pressed_from_a_face(self):
        keys = {vm.KEYS[f][1] for p in vm.default_layout().pages for f in p.slots if f in vm.KEYS}
        self.assertEqual(keys, set("0123456789.+-*/()") | {"back", "unit", "enter", "clear", "makevar", "unbind"})

    def test_the_variables_panel_has_eight_variables_a_group_key_and_the_keys_that_make_and_free(self):
        slots = page("Variables").slots
        self.assertEqual(slots[:8], list(vm.VARIABLE_IDS))
        self.assertEqual(slots[8:], ["key.makevar", "key.unbind", vm.VARIABLE_GROUP, None])

    def test_the_values_panel_has_twelve_faces_for_the_values(self):
        self.assertEqual(page("Values").slots, list(vm.ITEM_IDS))

    def test_a_saved_layout_loses_the_value_panel_and_gets_back_a_panel_that_is_missing(self):
        saved = vm.default_layout()
        saved.pages = [p for p in saved.pages if p.name != "Keys"] + [lay.Page("Value", list(vm.VALUE_SLOTS), 0, 1)]
        fixed = vm.complete(lay.Layout(saved.pages))
        self.assertEqual(sorted(p.name for p in fixed.pages), sorted(vm.MOVABLE_NAMES))
        self.assertEqual(len({p.side for p in fixed.pages}), 4)                      # the missing panel has a side of its own

    def test_the_layout_is_saved_and_loaded_without_the_value_panel_and_only_of_the_current_arrangement(self):
        import os
        import tempfile
        layout = vm.default_layout()
        layout.move_page(3, 0, 0, 0, True)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "values.json")
            lay.save_layout(layout, path, arrangement=vm.ARRANGEMENT)
            loaded = vm.load_layout(set(vm.faces()), path)
            self.assertEqual([(p.name, p.side, p.row) for p in loaded.pages], [(p.name, p.side, p.row) for p in layout.pages])
            default = [(p.name, p.side, p.row) for p in vm.default_layout().pages]
            self.assertEqual([(p.name, p.side, p.row) for p in vm.load_layout(set(vm.faces()), os.path.join(folder, "none.json")).pages], default)
            lay.save_layout(layout, path)                                              # a file of an older arrangement is not read
            self.assertEqual([(p.name, p.side, p.row) for p in vm.load_layout(set(vm.faces()), path).pages], default)
            with open(path, "w") as f:
                f.write("not json")
            self.assertEqual([(p.name, p.side, p.row) for p in vm.load_layout(set(vm.faces()), path).pages], default)

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


class ValuesPanelTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.module = vm.ValueModule(tool_hand=1)
        self.module.open(v.ValueEditor(Wide(), step=10.0))
        self.module.update(self.sim.frame(0.02))

    def test_the_faces_list_the_values_with_their_numbers_and_a_dash_where_there_is_none(self):
        labels = self.module.labels()
        self.assertEqual(labels["val.item.0"], "S0 100 mm")
        self.assertEqual(labels["val.item.6"], "POS.Z 0 mm")
        self.assertEqual(labels["val.item.7"], "-")

    def test_a_press_picks_the_value_and_the_picked_face_is_lit(self):
        self.assertEqual(self.module.picked_actions(), {"values:val.item.0"})
        self.assertTrue(self.module.activate("val.item.4"))
        self.assertEqual(self.module.editor.selected, 4)
        self.assertEqual(self.module.picked_actions(), {"values:val.item.4"})
        self.assertFalse(self.module.activate("val.item.4"))                         # it is picked already
        self.assertFalse(self.module.activate("val.item.9"))                         # a face with no value

    def test_the_list_follows_the_selector_and_the_numbers_follow_the_object(self):
        self.module.activate(vm.NEXT)
        self.assertEqual(self.module.picked_actions(), {"values:val.item.1"})
        self.module.editor.target.values["s0"] = 50.0
        self.module.update(self.sim.frame(0.02))
        self.assertEqual(self.module.labels()["val.item.0"], "S0 50 mm")

    def test_nothing_is_lit_and_no_value_is_listed_while_nothing_is_bound(self):
        self.module.close()
        self.assertEqual((self.module.picked_actions(), self.module.labels()), (frozenset(), {}))
        self.assertFalse(self.module.activate("val.item.0"))

    def test_more_values_than_faces_make_the_last_face_the_next_page(self):
        class Many(Target):
            title = "Sketch"

            def __init__(self):
                self.values = {f"d{i}": float(i + 1) for i in range(15)}
                self.log = []

            def fields(self):
                return [v.Field(n, n.upper(), x, 0.1) for n, x in self.values.items()]
        module = vm.ValueModule(tool_hand=1)
        module.open(v.ValueEditor(Many(), step=1.0))
        module.update(self.sim.frame(0.02))
        labels = module.labels()
        self.assertEqual((labels["val.item.0"], labels["val.item.10"], labels["val.item.11"]), ("D0 1 mm", "D10 11 mm", "More values"))
        self.assertTrue(module.activate("val.item.11"))
        labels = module.labels()
        self.assertEqual((labels["val.item.0"], labels["val.item.3"], labels["val.item.4"]), ("D11 12 mm", "D14 15 mm", "-"))
        self.assertEqual(module.picked_actions(), frozenset())                       # the picked value is on the first page
        self.assertTrue(module.activate("val.item.2"))
        self.assertEqual(module.editor.selected, 13)
        self.assertEqual(module.picked_actions(), {"values:val.item.2"})
        self.assertTrue(module.activate("val.item.11"))                               # round to the first page again
        self.assertEqual(module.labels()["val.item.0"], "D0 1 mm")
        module.activate(vm.PREV)                                                     # the selector brings the list to the picked value
        module.update(self.sim.frame(0.02))
        self.assertEqual(module.editor.selected, 12)
        self.assertEqual(module.picked_actions(), {"values:val.item.1"})


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
