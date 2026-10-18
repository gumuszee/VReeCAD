import math
import unittest

import support  # noqa: F401
from freecad.VReeCAD.backends.sim import SimInput
from freecad.VReeCAD.core import units
from freecad.VReeCAD.tools import base
from freecad.VReeCAD.ui import options as opt
from freecad.VReeCAD.ui import toast as ts
from freecad.VReeCAD.ui import undo_button as ub


class ToastTest(unittest.TestCase):
    def test_a_toast_stays_for_its_duration_and_grows_in_and_out(self):
        toasts = ts.Toasts()
        toasts.show("Undo")
        self.assertEqual(toasts.items[0].scale, 0.0)
        toasts.update(ts.POP_IN)
        self.assertEqual(toasts.items[0].scale, 1.0)
        toasts.update(1.0)
        self.assertEqual([t.text for t in toasts.update(0.0)], ["Undo"])
        toasts.update(ts.DURATION - 1.0 - ts.POP_IN - ts.POP_OUT / 2)
        self.assertAlmostEqual(toasts.items[0].scale, 0.5, places=6)
        self.assertEqual(toasts.update(1.0), [])

    def test_the_same_text_renews_instead_of_stacking(self):
        toasts = ts.Toasts()
        toasts.show("Undo")
        toasts.update(1.5)
        toasts.show("Redo")
        toasts.show("Undo")
        self.assertEqual([t.text for t in toasts.items], ["Redo", "Undo"])       # renewed Undo is the newest
        self.assertLessEqual(toasts.items[1].age, ts.POP_IN)

    def test_at_most_three_stand_at_once_and_empty_text_is_ignored(self):
        toasts = ts.Toasts()
        for text in ("a", "b", "c", "d", ""):
            toasts.show(text)
        self.assertEqual([t.text for t in toasts.items], ["b", "c", "d"])


class DwellTest(unittest.TestCase):
    def test_the_tooltip_shows_after_the_delay_and_restarts_on_a_new_target(self):
        dwell = ts.Dwell(0.5)
        self.assertIsNone(dwell.update((0, 1), 0.02))
        self.assertIsNone(dwell.update((0, 1), 0.4))
        self.assertEqual(dwell.update((0, 1), 0.2), (0, 1))
        self.assertEqual(dwell.update((0, 1), 0.02), (0, 1))
        self.assertIsNone(dwell.update((0, 2), 0.02))
        self.assertIsNone(dwell.update(None, 1.0))
        self.assertIsNone(dwell.update(None, 1.0))


class UndoButtonTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.button = ub.UndoButton(hand=1)

    def step(self, n=1, dt=0.02, blocked=False):
        actions = []
        for _ in range(n):
            state = self.button.update(self.sim.frame(dt), blocked)
            if state.action:
                actions.append(state.action)
        return actions

    def test_a_tap_undoes_when_the_button_is_released(self):
        self.sim.set_hand(1, button2=True)
        self.assertEqual(self.step(5), [])
        self.sim.set_hand(1, button2=False)
        self.assertEqual(self.step(1), ["undo"])

    def test_holding_redoes_once_and_releasing_does_nothing_more(self):
        self.sim.set_hand(1, button2=True)
        self.assertEqual(self.step(int(ub.HOLD / 0.02) + 3), ["redo"])
        self.assertEqual(self.step(20), [])
        self.sim.set_hand(1, button2=False)
        self.assertEqual(self.step(1), [])

    def test_a_grip_blocks_it_and_the_button_of_the_palette_hand_is_not_used(self):
        self.sim.set_hand(0, grip=1.0)
        self.sim.set_hand(1, button2=True)
        self.step(3)
        self.sim.set_hand(1, button2=False)
        self.assertEqual(self.step(2), [])                                          # the 1 : 1 lock, not an undo
        self.sim.set_hand(0, grip=0.0)
        self.sim.set_hand(1, button2=True)
        self.step(2)
        self.sim.set_hand(0, grip=1.0)                                              # a grip while the button is down cancels
        self.step(2)
        self.sim.set_hand(0, grip=0.0)
        self.sim.set_hand(1, button2=False)
        self.assertEqual(self.step(2), [])
        self.sim.set_hand(0, button2=True)
        self.sim.set_hand(0, button2=False)
        self.assertEqual(self.step(2), [])

    def test_a_button_held_from_before_does_not_start_anything(self):
        self.sim.set_hand(1, button2=True)
        self.assertEqual(self.step(2, blocked=True), [])
        self.sim.set_hand(1, button2=False)
        self.assertEqual(self.step(2), [])


class Fake(base.Tool):
    name = "fake_options"
    label = "Fake"
    options = (base.ToolOption("size", "Size", "length", 1.0, 100.0, 1.0, 10.0),
               base.ToolOption("shape", "Shape", "choice", default="Box", choices=("Box", "Cylinder", "Sphere")))


class NumberTool(base.Tool):
    name = "fake_number"
    label = "Number"
    options = (base.ToolOption("count", "Count", "number", 0, 3, 1, 2, "x"),)


class OptionTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.control = opt.OptionControl(hand=1)
        self.tool = Fake(base.ToolContext())

    def step(self, tool=None, n=1, dt=0.02, **kw):
        state = None
        for _ in range(n):
            state = self.control.update(self.sim.frame(dt), tool or self.tool, **kw)
        return state

    def test_a_tool_declares_its_options_with_defaults_and_limits(self):
        self.assertEqual(self.tool.values, {"size": 10.0, "shape": "Box"})
        self.assertEqual(self.tool.set_option("size", 250.0), 100.0)
        self.assertEqual(self.tool.set_option("size", 3.4), 3.0)
        self.assertEqual(self.tool.set_option("shape", "Torus"), "Box")
        self.assertEqual(base.ToolOption("a", "A", "number", 0, 1, 0.1).clamp(0.34), 0.3)

    def test_option_text(self):
        size, shape = Fake.options
        self.assertEqual(size.format(10.0), "10 mm")
        self.assertEqual(size.format(10.0, units.IMPERIAL), "0.394 in")
        self.assertEqual(shape.format("Box"), "Box")
        self.assertEqual(NumberTool.options[0].format(2), "2 x")
        self.assertEqual(base.ToolOption("a", "A", "number", 0, 9, 0.5, 1, "deg").format(1.5), "1.5 deg")

    def test_a_tool_without_options_leaves_the_stick_alone(self):
        self.sim.set_hand(1, stick=(0.0, 1.0))
        state = self.step(base.Tool(base.ToolContext()))
        self.assertFalse(state.owns_stick)
        self.assertIsNone(state.readout)
        self.assertFalse(self.control.update(self.sim.frame(0.02), None).owns_stick)

    def test_stick_up_steps_the_first_option_at_once_then_repeats_while_held(self):
        self.sim.set_hand(1, stick=(0.0, 1.0))
        state = self.step()
        self.assertTrue(state.owns_stick)
        self.assertEqual((self.tool.values["size"], state.changed, state.readout), (11.0, "size", "Size: 11 mm"))
        self.assertEqual(len(state.haptics), 1)
        self.step(n=int(opt.FIRST_REPEAT / 0.02) - 2)
        self.assertEqual(self.tool.values["size"], 11.0)                              # still in the delay
        self.step(n=3)
        self.assertEqual(self.tool.values["size"], 12.0)
        self.step(n=int(0.5 / 0.02))
        high = self.tool.values["size"]
        self.assertGreaterEqual(high, 16.0)
        self.sim.set_hand(1, stick=(0.0, -1.0))
        self.step()
        self.assertEqual(self.tool.values["size"], high - 1.0)                        # the reversed push steps at once

    def test_values_stop_at_the_ends(self):
        self.tool.values["size"] = 100.0
        self.sim.set_hand(1, stick=(0.0, 1.0))
        state = self.step(n=10)
        self.assertEqual(self.tool.values["size"], 100.0)
        self.assertIsNone(state.changed)
        self.assertEqual(state.readout, "Size: 100 mm")                               # the readout still tells the value

    def test_stick_right_cycles_the_choice_once_per_flick(self):
        self.sim.set_hand(1, stick=(1.0, 0.0))
        self.step(n=30)
        self.assertEqual(self.tool.values["shape"], "Cylinder")                       # holding does not repeat a choice
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.step(n=2)
        self.sim.set_hand(1, stick=(-1.0, 0.0))
        self.step()
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.step(n=2)
        self.sim.set_hand(1, stick=(-1.0, 0.0))
        state = self.step()
        self.assertEqual((self.tool.values["shape"], state.readout), ("Sphere", "Shape: Sphere"))   # wraps round

    def test_the_stick_click_resets_the_option_changed_last(self):
        self.sim.set_hand(1, stick=(0.0, 1.0))
        self.step(n=20)
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.step(n=2)
        self.sim.set_hand(1, stick=(1.0, 0.0))
        self.step()
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.step(n=2)
        self.sim.set_hand(1, stick_click=True)
        state = self.step()
        self.assertEqual((self.tool.values["shape"], state.readout), ("Box", "Shape: Box"))
        self.assertGreater(self.tool.values["size"], 10.0)                            # the other option is left alone
        self.sim.set_hand(1, stick_click=False)
        self.step(n=2)
        self.sim.set_hand(1, stick_click=True)
        self.assertEqual(self.step(NumberTool(base.ToolContext())).readout, "Count: 2 x")

    def test_the_readout_fades_and_a_grip_blocks_the_options(self):
        self.sim.set_hand(1, stick=(0.0, 1.0))
        self.step()
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.assertIsNotNone(self.step(n=10).readout)
        self.assertIsNone(self.step(n=int(opt.READOUT_TIME / 0.02)).readout)
        self.sim.set_hand(0, grip=1.0)
        self.sim.set_hand(1, stick=(0.0, 1.0))
        before = self.tool.values["size"]
        self.step(n=20)
        self.assertEqual(self.tool.values["size"], before)

    def test_a_second_option_axis_needs_a_second_option(self):
        tool = NumberTool(base.ToolContext())
        self.sim.set_hand(1, stick=(1.0, 0.0))
        self.step(tool, n=5)
        self.assertEqual(tool.values["count"], 2)
        self.sim.set_hand(1, stick=(0.0, 1.0))
        self.step(tool)
        self.assertEqual(tool.values["count"], 3)



class DiscTool(base.Tool):
    name = "fake_disc"
    label = "Disc"
    options = (base.ToolOption("grid", "Grid", "choice", default="10 mm", choices=("1 mm", "10 mm", "100 mm"), wrap=False),
               base.ToolOption("shape", "Shape", "choice", default="Box", choices=("Box", "Cylinder", "Cone")))

    def __init__(self, ctx):
        super().__init__(ctx)
        self.clicks = 0

    def disc_slots(self):
        D = base.DiscSlot
        return (D("Grid +", "grid", 1, "step"), D("Cylinder", "shape", "Cylinder"), D("Cone", "shape", "Cone"),
                D("Grid -", "grid", -1, "step"), D("", ), D("Box", "shape", "Box"))

    def disc_hub(self):
        return [self.values["grid"]]

    def stick_click(self):
        self.clicks += 1
        return "clicked"


class DiscTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.control = opt.OptionControl(hand=1)
        self.tool = DiscTool(base.ToolContext())

    def step(self, n=1, dt=0.02, **kw):
        state = None
        for _ in range(n):
            state = self.control.update(self.sim.frame(dt), self.tool, **kw)
        return state

    def push(self, degrees, size=1.0):
        """The stick pushed out in a direction: 0 is straight up, clockwise."""
        a = math.radians(degrees)
        self.sim.set_hand(1, stick=(size * math.sin(a), size * math.cos(a)))

    def test_the_stick_points_at_a_section_like_the_hours_of_a_clock(self):
        for degrees, index in ((0, 0), (60, 1), (120, 2), (180, 3), (240, 4), (300, 5), (20, 0), (350, 0), (100, 2)):
            self.push(degrees, 0.5)
            state = self.step()
            self.assertEqual(state.disc.selected, index, degrees)
            self.sim.set_hand(1, stick=(0.0, 0.0))
            self.step(2)

    def test_up_and_down_step_the_grid_and_stop_at_its_ends(self):
        self.push(0)
        state = self.step()
        self.assertEqual(self.tool.values["grid"], "100 mm")
        self.assertEqual((state.changed, state.disc.hub, state.owns_stick), ("grid", ["100 mm"], True))
        self.step(30)
        self.assertEqual(self.tool.values["grid"], "100 mm")                       # no wrap round
        self.push(180)
        self.step()
        self.assertEqual(self.tool.values["grid"], "10 mm")
        self.step(int(opt.FIRST_REPEAT / 0.02) + 3)
        self.assertEqual(self.tool.values["grid"], "1 mm")
        self.step(30)
        self.assertEqual(self.tool.values["grid"], "1 mm")

    def test_a_set_section_sets_once_and_a_neighbouring_section_applies_when_the_stick_rolls_round(self):
        self.push(60)
        self.assertEqual((self.step().changed, self.tool.values["shape"]), ("shape", "Cylinder"))
        self.assertIsNone(self.step(20).changed)
        self.push(120)
        self.step()
        self.assertEqual(self.tool.values["shape"], "Cone")
        self.push(300)
        self.step()
        self.assertEqual(self.tool.values["shape"], "Box")

    def test_the_active_sections_are_those_that_hold_the_value(self):
        self.push(60)
        state = self.step()
        self.assertEqual(state.disc.active, [False, True, False, False, False, False])
        self.assertEqual(state.disc.labels, ["Grid +", "Cylinder", "Cone", "Grid -", "", "Box"])

    def test_an_empty_section_does_nothing(self):
        self.push(240)
        state = self.step()
        self.assertIsNone(state.changed)
        self.assertEqual(self.tool.values, {"grid": "10 mm", "shape": "Box"})

    def test_the_disc_is_shown_while_the_stick_is_out_and_for_a_while_after_a_change(self):
        self.assertIsNone(self.step().disc)
        self.push(60, 0.5)                                   # out, but not far enough to apply a section
        self.assertIsNotNone(self.step().disc)
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.assertIsNone(self.step(n=2).disc)
        self.push(60)
        self.step()
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.assertIsNotNone(self.step(n=10).disc)
        self.assertIsNone(self.step(n=int(opt.READOUT_TIME / 0.02)).disc)

    def test_a_grip_blocks_the_disc(self):
        self.sim.set_hand(0, grip=1.0)
        self.push(0)
        state = self.step(n=5)
        self.assertEqual((self.tool.values["grid"], state.disc), ("10 mm", None))

    def test_the_click_goes_to_the_tool_and_its_message_is_passed_on(self):
        self.sim.set_hand(1, stick_click=True)
        state = self.step()
        self.assertEqual((self.tool.clicks, state.message), (1, "clicked"))
        self.assertIsNotNone(state.disc)                                  # the disc shows what the click changed
        self.sim.set_hand(1, stick_click=False)
        self.step(2)
        self.assertEqual(self.step().message, None)

    def test_a_tool_without_a_disc_keeps_the_two_axes(self):
        tool = Fake(base.ToolContext())
        self.sim.set_hand(1, stick=(0.0, 1.0))
        state = self.control.update(self.sim.frame(0.02), tool)
        self.assertIsNone(state.disc)
        self.assertEqual(tool.values["size"], 11.0)


if __name__ == "__main__":
    unittest.main()
