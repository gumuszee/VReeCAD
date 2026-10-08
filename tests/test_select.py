import math
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.cad import picking
from freecad.BlocksCAD.core import selecting
from freecad.BlocksCAD.tools import base
from freecad.BlocksCAD.tools.select import SelectTool
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import options as opt
from freecad.BlocksCAD.ui import radial as rd
from freecad.BlocksCAD.ui import settings as cfg


class CombineTest(unittest.TestCase):
    A, B, F = ("Box", ""), ("Cyl", ""), ("Box", "Face3")

    def test_replace_makes_the_element_the_only_one(self):
        self.assertEqual(selecting.combine([self.A, self.B], self.F, selecting.REPLACE), [self.F])

    def test_add_appends_in_order_and_never_twice(self):
        self.assertEqual(selecting.combine([self.A], self.B, selecting.ADD), [self.A, self.B])
        self.assertEqual(selecting.combine([self.A, self.B], self.A, selecting.ADD), [self.A, self.B])
        self.assertEqual(selecting.combine([self.A], self.F, selecting.ADD), [self.A, self.F])      # objects and faces side by side

    def test_remove_takes_an_element_out_and_a_whole_object_takes_all_its_elements(self):
        self.assertEqual(selecting.combine([self.A, self.B], self.A, selecting.REMOVE), [self.B])
        self.assertEqual(selecting.combine([self.A, self.F, self.B], self.F, selecting.REMOVE), [self.A, self.B])
        self.assertEqual(selecting.combine([self.F, ("Box", "Edge1"), self.B], self.A, selecting.REMOVE), [self.B])
        self.assertEqual(selecting.combine([self.B], self.A, selecting.REMOVE), [self.B])

    def test_the_selection_that_was_given_is_not_changed(self):
        current = [self.A]
        selecting.combine(current, self.B, selecting.ADD)
        selecting.combine(current, self.A, selecting.REMOVE)
        self.assertEqual(current, [self.A])


class FakeShape:
    def isNull(self):
        return False

    def hashCode(self):
        return 1


class FakeObject:
    def __init__(self, name):
        self.Name, self.Label, self.Shape = name, name.upper(), FakeShape()


class FakeLayer:
    def show(self, displays, half):
        pass

    def hide(self):
        pass


class FakeHighlights(FakeLayer):
    def __init__(self):
        self.hover, self.selected = FakeLayer(), FakeLayer()


class FakeDocument:
    def __init__(self, *names):
        self.objects = {n: FakeObject(n) for n in names}

    def getObject(self, name):
        return self.objects.get(name)


class SelectToolTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.sim.set_head(position=(0.0, 1.6, 0.0), look_at_point=(0.0, 1.2, -1.0))
        self.sim.set_hand(1, position=(0.0, 1.2, -0.4), point_at=(0.0, 1.2, -2.0))
        self.doc = FakeDocument("box", "cyl")
        self.selection = []
        self.touched = None          # what the pick service returns
        self.kinds = []              # the kinds the pick service was asked for
        self.toasts = []
        self.free = True
        ctx = base.ToolContext(dominant=1)
        ctx.services.update({
            "cursor": lambda hand: (0.0, 0.0, 0.0), "to_document": lambda p: p, "document": lambda: self.doc,
            "trigger_free": lambda: self.free, "toast": self.toasts.append, "pick": self.pick, "highlight": FakeHighlights(),
            "display": lambda obj, sub: picking.Display(), "get_selection": lambda doc: list(self.selection),
            "set_selection": lambda doc, items: self.selection.__init__(items),
            "clear_selection": lambda: self.selection.clear()})
        self.tool = SelectTool(ctx)

    def pick(self, doc, point, mm, kind=None):
        self.kinds.append(kind)
        if self.touched is None:
            return None
        name, sub = self.touched
        return picking.Pick(name, picking.kind_of(sub), sub, 0.0)

    def press(self, touching, **inputs):
        """Touch an element (name, sub) or nothing until the hover has moved to it, press the trigger for one frame, then let go."""
        self.touched = touching
        self.sim.set_hand(1, trigger=0.0)
        for _ in range(3):                                   # the hover moves to what is touched after a moment
            self.tool.update(self.sim.frame(0.1))
        self.sim.set_hand(1, trigger=1.0, **inputs)
        self.tool.update(self.sim.frame(0.02))
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.5))

    def test_the_default_replaces_the_selection_with_the_whole_object(self):
        self.press(("box", ""))
        self.assertEqual(self.selection, [("box", "")])
        self.press(("cyl", ""))
        self.assertEqual(self.selection, [("cyl", "")])
        self.assertEqual(self.toasts[-1], "Selected CYL")

    def test_a_press_on_nothing_clears_the_selection_only_when_replacing(self):
        self.selection[:] = [("box", ""), ("cyl", "")]
        self.tool.values["operation"] = selecting.ADD
        self.press(None)
        self.assertEqual(len(self.selection), 2)
        self.tool.values["operation"] = selecting.REPLACE
        self.press(None)
        self.assertEqual(self.selection, [])
        self.assertEqual(self.toasts[-1], "Selection cleared")

    def test_add_and_remove_change_the_selection_one_element_at_a_time(self):
        self.press(("box", ""))
        self.tool.values["operation"] = selecting.ADD
        self.press(("cyl", ""))
        self.assertEqual(self.selection, [("box", ""), ("cyl", "")])
        self.assertEqual(self.toasts[-1], "Added CYL, 2 selected")
        self.press(("cyl", ""))
        self.assertEqual(self.toasts[-1], "CYL is already selected")
        self.tool.values["operation"] = selecting.REMOVE
        self.press(("box", ""))
        self.assertEqual(self.selection, [("cyl", "")])
        self.assertEqual(self.toasts[-1], "Removed BOX, 1 selected")
        self.press(("box", ""))
        self.assertEqual(self.toasts[-1], "BOX is not selected")

    def test_every_target_selects_many_elements(self):
        self.tool.values["operation"] = selecting.ADD
        for target, subs in (("Face", ("Face1", "Face4")), ("Edge", ("Edge2", "Edge7")), ("Vertex", ("Vertex1", "Vertex5"))):
            self.selection.clear()
            self.tool.values["target"] = target
            for sub in subs:
                self.press(("box", sub))
            self.assertEqual(self.selection, [("box", s) for s in subs], target)
        self.selection.clear()
        self.tool.values["target"] = "Object"
        self.press(("box", ""))
        self.press(("cyl", ""))
        self.assertEqual(self.selection, [("box", ""), ("cyl", "")])

    def test_the_target_decides_what_is_asked_for_and_the_hover_starts_again(self):
        self.touched = ("box", "")
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.kinds[-1], "object")
        self.assertIsNotNone(self.tool._hover)
        self.tool.values["target"] = "Edge"
        self.touched = ("box", "Edge3")
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.kinds[-1], "edge")
        self.assertEqual((self.tool._hover.name, self.tool._hover.sub), ("box", "Edge3"))      # no 0.08 s wait for the new sort

    def test_a_press_the_interface_took_does_nothing(self):
        self.free = False
        self.press(("box", ""))
        self.assertEqual(self.selection, [])

    def test_the_tool_changes_nothing_in_the_document(self):
        self.doc.openTransaction = lambda *a: self.fail("a transaction was opened")
        self.press(("box", ""))
        self.assertEqual(self.selection, [("box", "")])


class SelectDiscTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.control = opt.OptionControl(hand=1)
        self.tool = SelectTool(base.ToolContext())

    def push(self, degrees):
        a = math.radians(degrees)
        self.sim.set_hand(1, stick=(math.sin(a), math.cos(a)))
        state = self.control.update(self.sim.frame(0.02), self.tool)
        self.sim.set_hand(1, stick=(0.0, 0.0))
        self.control.update(self.sim.frame(0.02), self.tool)
        return state

    def test_the_sections_choose_the_target_and_the_operation(self):
        labels = [s.label for s in self.tool.disc_slots()]
        self.assertEqual(labels, ["Object", "Face", "Edge", "Vertex", "Remove", "Add", "", ""])
        for degrees, target in ((45, "Face"), (90, "Edge"), (135, "Vertex"), (0, "Object")):
            self.push(degrees)
            self.assertEqual(self.tool.values["target"], target)
        self.assertEqual(self.tool.values["operation"], selecting.REPLACE)

    def test_add_and_remove_go_back_to_replace_when_pushed_again(self):
        self.push(225)
        self.assertEqual(self.tool.values["operation"], selecting.ADD)
        self.push(225)
        self.assertEqual(self.tool.values["operation"], selecting.REPLACE)
        self.push(180)
        self.assertEqual(self.tool.values["operation"], selecting.REMOVE)
        self.push(225)
        self.assertEqual(self.tool.values["operation"], selecting.ADD)

    def test_the_disc_lights_the_target_and_the_operation_that_are_set(self):
        self.push(225)
        state = self.push(90)
        self.assertEqual(state.disc.active, [False, False, True, False, False, True, False, False])
        self.assertEqual(state.disc.hub, ["Edge", "Add"])

    def test_the_click_of_the_stick_puts_both_back(self):
        self.push(90)
        self.push(180)
        self.tool.stick_click()
        self.assertEqual((self.tool.values["target"], self.tool.values["operation"]), ("Object", selecting.REPLACE))


class RadialHubTest(unittest.TestCase):
    HAND = (0.25, 1.2, -0.4)

    def setUp(self):
        self.sim = SimInput()
        self.radial = rd.QuickRadial(hand=1)
        self.sim.set_head(position=(0.0, 1.6, 0.0), look_at_point=(0.0, 1.2, -1.0))
        self.sim.set_hand(1, position=self.HAND, point_at=(0.0, 1.2, -2.0))

    def step(self, hub=rd.CENTRE):
        return self.radial.update(self.sim.frame(0.02), ["a", "b", "c", "d"], hub=hub)

    def test_releasing_without_moving_the_hand_chooses_the_hub_item(self):
        self.sim.set_hand(1, button1=True)
        self.assertEqual(self.step().hub, rd.CENTRE)
        self.sim.set_hand(1, position=(self.HAND[0] + 0.01, self.HAND[1], self.HAND[2]))      # a tremble inside the dead zone
        self.step()
        self.sim.set_hand(1, button1=False)
        state = self.step()
        self.assertTrue(state.activated_hub)
        self.assertIsNone(state.activated)
        self.assertIn((1, 0.5, 0.04), state.haptics)

    def test_moving_out_chooses_a_segment_and_not_the_hub(self):
        self.sim.set_hand(1, button1=True)
        self.step()
        self.sim.set_hand(1, position=(self.HAND[0], self.HAND[1] + 0.06, self.HAND[2]))
        self.step()
        self.sim.set_hand(1, button1=False)
        state = self.step()
        self.assertEqual((state.activated, state.activated_hub), (0, False))

    def test_without_a_hub_item_releasing_in_the_dead_zone_still_cancels(self):
        self.sim.set_hand(1, button1=True)
        self.step(hub=None)
        self.sim.set_hand(1, button1=False)
        state = self.step(hub=None)
        self.assertEqual((state.activated, state.activated_hub), (None, False))

    def test_the_hub_item_is_never_a_segment(self):
        known = {"tool.select", "tool.move", "doc.undo", "doc.redo", "view.reset", "doc.delete", "pointer.mode"}
        items = rd.choose_items(["tool.select", "tool.move"], known)
        self.assertNotIn("tool.select", items)
        self.assertEqual(items[0], "tool.move")


class RenamedFaceTest(unittest.TestCase):
    def test_a_saved_layout_keeps_the_place_of_a_renamed_face(self):
        text = '{"pages": [{"name": "Tools", "slots": ["tool.primitive", "tool.grab", null]}], "hidden": ["tool.grab"]}'
        layout = lay.Layout.from_json(text, {"tool.primitive", "tool.move"})
        self.assertEqual(layout.pages[0].slots[:3], ["tool.primitive", "tool.move", None])
        self.assertEqual(layout.hidden, ["tool.move"])

    def test_saved_settings_keep_a_renamed_face_in_the_recent_faces(self):
        self.assertEqual(cfg.Settings.from_json('{"recent": ["tool.grab", "doc.undo"]}').recent, ["tool.move", "doc.undo"])


if __name__ == "__main__":
    unittest.main()
