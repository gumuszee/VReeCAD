# Tests that need a running FreeCAD GUI (Coin3D and an OpenGL context for offscreen rendering).
# Run through the remote channel:  python tools/fc_rpc.py exec -f tools/snippets/run_live_tests.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import support  # noqa: F401,E402
import test_gltf  # noqa: E402  (synthetic GLB builder)

from freecad.BlocksCAD.render import controller_shape, gltf_coin, offscreen  # noqa: E402
from freecad.BlocksCAD.backends import sim  # noqa: E402


def non_background(image, background=(31, 31, 36), tol=6):
    """Number of pixels that differ from the background colour."""
    count = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            c = image.pixelColor(x, y)
            if max(abs(c.red() - background[0]), abs(c.green() - background[1]), abs(c.blue() - background[2])) > tol:
                count += 1
    return count


class GltfCoinTest(unittest.TestCase):
    def test_build_and_render_synthetic_glb(self):
        model = gltf_coin.load_glb(test_gltf.triangle_glb())
        self.assertEqual(sorted(model.parts), ["root", "tri"])
        image = offscreen.render(model.root, (0.67, 2.33, 5.0), target=(0.67, 2.33, 3.0), size=(160, 120), ambient=1.0)
        self.assertGreater(non_background(image), 30)
        # hiding the node removes the triangle from the image
        model.part("tri").set_visible(False)
        image = offscreen.render(model.root, (0.67, 2.33, 5.0), target=(0.67, 2.33, 3.0), size=(160, 120), ambient=1.0)
        self.assertEqual(non_background(image), 0)

    def test_cached_runtime_models_build_when_present(self):
        folder = os.path.join(os.environ.get("LOCALAPPDATA", ""), "BlocksCAD", "cache", "rendermodels")
        files = [f for f in os.listdir(folder) if f.endswith(".glb")] if os.path.isdir(folder) else []
        if not files:
            self.skipTest("no cached runtime controller models")
        for name in files:
            with open(os.path.join(folder, name), "rb") as f:
                model = gltf_coin.load_glb(f.read())
            self.assertIn("body", model.parts)
            self.assertIn("trigger", model.parts)


class FallbackShapeTest(unittest.TestCase):
    def test_parts_and_animation(self):
        for side, extra in (("left", "button_x"), ("right", "button_a")):
            model = controller_shape.build_fallback(side)
            for part in ("body", "trigger", "thumbstick", extra):
                self.assertIsNotNone(model.part(part), part)
        hand = sim.HandInput(trigger=1.0, stick=(1.0, 0.0))
        before = model.part("trigger").transform.translation.getValue().getValue()
        controller_shape.animate(model, hand)
        after = model.part("trigger").transform.translation.getValue().getValue()
        self.assertGreater(after[2], before[2])


class SimSessionTest(unittest.TestCase):
    def test_render_shows_the_controllers_and_follows_the_script(self):
        s = sim.SimSession()
        try:
            s.input.set_head(position=(0.0, 1.5, 1.0), look_at_point=(0.0, 1.2, 0.0))
            s.input.set_hand(1, position=(0.1, 1.2, 0.2), point_at=(0.1, 1.2, -1.0))
            s.frame()
            with_hands = non_background(s.render("head", (200, 150)))
            self.assertGreater(with_hands, 40)
            # looking away from the hands shows nothing
            s.input.set_head(look_at_point=(0.0, 1.5, 5.0))
            s.frame()
            self.assertEqual(non_background(s.render("head", (200, 150))), 0)
            stereo = s.render_stereo((100, 100))
            self.assertEqual((stereo.width(), stereo.height()), (200, 100))
        finally:
            s.close()


class SimNavigationTest(unittest.TestCase):
    def test_two_grip_spread_enlarges_the_world_on_screen(self):
        from pivy import coin
        scene = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor.setValue(0.2, 0.7, 0.3)
        scene.addChild(material)
        cube = coin.SoCube()
        cube.width = cube.height = cube.depth = 100.0   # millimetres, shown as 0.1 m
        scene.addChild(cube)
        s = sim.SimSession(scene)
        try:
            s.input.set_head(position=(0.0, 0.1, 1.2), look_at_point=(0.0, 0.0, 0.0))
            s.input.set_hand(0, position=(-0.2, 0.0, 0.0))
            s.input.set_hand(1, position=(0.2, 0.0, 0.0))
            s.frame()
            before = non_background(s.render("head", (200, 150)))
            s.input.set_hand(0, grip=1.0)
            s.input.set_hand(1, grip=1.0)
            s.frame()
            s.input.set_hand(0, position=(-0.4, 0.0, 0.0))
            s.input.set_hand(1, position=(0.4, 0.0, 0.0))
            s.frame()
            self.assertAlmostEqual(s.navigator.world.scale, 2.0)
            after = non_background(s.render("head", (200, 150)))
            self.assertGreater(after, before * 1.5)
        finally:
            s.close()


def sim_sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


class SimUiTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.s = sim.SimSession(None, actions={"doc:undo": lambda: self.calls.append("undo"),
                                               "doc:redo": lambda: self.calls.append("redo")})

    def tearDown(self):
        self.s.close()

    def test_dpad_left_and_right_of_the_palette_hand_undo_and_redo(self):
        self.s.frame()
        self.s.input.set_hand(0, aux1=True)
        self.s.frame()
        self.s.input.set_hand(0, aux1=False)
        self.s.frame()
        self.s.input.set_hand(0, aux2=True)
        self.s.frame()
        self.assertEqual(self.calls, ["undo", "redo"])
        self.s.input.set_hand(1, aux1=True)       # the tool hand has no such shortcut
        self.s.frame()
        self.assertEqual(self.calls, ["undo", "redo"])

    def test_the_ruler_follows_the_two_grips_and_uses_the_document_units(self):
        from pivy import coin
        self.s.input.set_hand(0, position=(-0.2, 1.2, -0.5))
        self.s.input.set_hand(1, position=(0.2, 1.2, -0.5))
        self.s.frame()
        self.assertEqual(self.s.ui.ruler.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
        self.s.input.set_hand(0, grip=1.0)
        self.s.input.set_hand(1, grip=1.0)
        self.s.frame()
        self.s.frame()
        self.assertEqual(self.s.ui.ruler.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        shown = [label.text.string.getValues(0) for label in self.s.ui.ruler._labels if label.switch.whichChild.getValue() == coin.SO_SWITCH_ALL]
        self.assertEqual(shown[0], ["0"])
        self.assertTrue(shown[1][0].endswith(" mm"))
        self.s.ui.set_unit_system("Imperial decimal (in, lb)")
        self.s.frame()
        shown = [label.text.string.getValues(0) for label in self.s.ui.ruler._labels if label.switch.whichChild.getValue() == coin.SO_SWITCH_ALL]
        self.assertTrue(shown[1][0].endswith(" in"))
        self.s.input.set_hand(0, grip=0.0)
        self.s.input.set_hand(1, grip=0.0)
        self.s.frame()
        self.assertEqual(self.s.ui.ruler.root.whichChild.getValue(), coin.SO_SWITCH_NONE)

    def test_one_grip_shows_the_scale_and_the_mode_above_the_hand(self):
        from pivy import coin
        self.s.input.set_hand(1, position=(0.2, 1.2, -0.5))
        self.s.frame()
        self.s.input.set_hand(1, grip=1.0)
        self.s.frame()
        self.s.frame()
        self.assertEqual(self.s.ui.ruler.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.assertEqual(list(self.s.ui.ruler._ratio.text.string.getValues(0)), ["1 : 1"])
        self.assertEqual(list(self.s.ui.ruler._info.text.string.getValues(0)), ["free orbit"])
        self.s.input.set_hand(1, button1=True, button2=True)
        self.s.frame()
        self.assertEqual(list(self.s.ui.ruler._info.text.string.getValues(0)), ["level, 1 : 1 locked"])

    def test_the_laser_shows_while_the_carousel_is_visible(self):
        from pivy import coin
        self.s.input.set_head(position=(0.0, 1.6, 0.0), look_at_point=(-0.25, 1.2, -0.35))
        for _ in range(30):
            self.s.frame(0.02)
        self.assertEqual(self.s.ui.pointer.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.s.input.set_head(look_at_point=(0.0, 1.6, 2.0))
        for _ in range(30):
            self.s.frame(0.02)
        self.assertEqual(self.s.ui.pointer.root.whichChild.getValue(), coin.SO_SWITCH_NONE)

    def test_tip_mode_shows_a_tip_on_both_controllers_instead_of_the_laser(self):
        from pivy import coin
        self.s.input.set_head(position=(0.0, 1.6, 0.0), look_at_point=(-0.25, 1.2, -0.35))
        for _ in range(30):
            self.s.frame(0.02)
        self.assertEqual(self.s.ui.pointer.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.assertEqual([t.root.whichChild.getValue() for t in self.s.ui.tips], [coin.SO_SWITCH_NONE] * 2)
        self.s.ui._change_pointer("pointer:mode")
        self.s.frame(0.02)
        self.assertEqual(self.s.ui.settings.pointer_mode, "tip")
        self.assertEqual(self.s.ui.pointer.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
        # the palette hand's tip hides while the carousel is shown
        self.assertEqual([t.root.whichChild.getValue() for t in self.s.ui.tips], [coin.SO_SWITCH_NONE, coin.SO_SWITCH_ALL])
        for hand in range(2):                      # the tip sits in front of the controller
            aim = self.s.last_frame.hands[hand].aim
            pointer = self.s.ui.pointer_poses[hand]
            self.assertAlmostEqual(sum(c * c for c in sim_sub(pointer.position, aim.position)) ** 0.5, self.s.ui.settings.tip_length, places=6)

    def test_the_pointer_faces_show_their_values_and_the_sliders_set_them(self):
        labels = self.s.ui.labels()
        self.assertEqual(labels["pointer.mode"], "Pointer: Laser")
        self.assertEqual(labels["pointer.angle"], "Angle 15°")
        self.assertEqual(labels["pointer.length"], "Length 40 mm")
        self.assertEqual(self.s.ui.slider_states()["pointer.angle"][0], 0.5)
        self.assertEqual(self.s.ui.slider_rows(), {3: {1: "pointer.angle", 2: "pointer.length"}})
        self.s.ui.settings.tip_angle = 30.0
        self.assertEqual(self.s.ui.labels()["pointer.angle"], "Angle 30°")
        self.s.ui.set_unit_system("Imperial decimal (in, lb)")
        self.assertEqual(self.s.ui.labels()["pointer.length"], "Length 1.57 in")

    def test_the_tips_stay_while_navigating_but_the_palette_hand_tip_hides_behind_the_carousel(self):
        from pivy import coin
        self.s.ui.settings.pointer_mode = "tip"
        self.s.input.set_head(position=(0.0, 1.6, 0.0), look_at_point=(-0.25, 1.2, -0.35))
        for _ in range(30):
            self.s.frame(0.02)
        shown = [t.root.whichChild.getValue() for t in self.s.ui.tips]
        self.assertEqual(shown[self.s.ui.palette_hand], coin.SO_SWITCH_NONE)       # the carousel is visible
        self.assertEqual(shown[self.s.ui.tool_hand], coin.SO_SWITCH_ALL)
        self.s.input.set_hand(0, grip=1.0)
        self.s.input.set_hand(1, grip=1.0)
        for _ in range(30):
            self.s.frame(0.02)
        self.assertEqual([t.root.whichChild.getValue() for t in self.s.ui.tips], [coin.SO_SWITCH_ALL] * 2)   # navigating: both tips
        self.assertEqual(self.s.ui.ruler.root.whichChild.getValue(), coin.SO_SWITCH_ALL)

    def settle(self, n=30):
        for _ in range(n):
            self.s.frame(0.02)

    def show_carousel(self):
        """The head looks at the left controller: the carousel is visible; the tool hand rests away from it. The pointer points
        straight along the controller, so aiming at a point hits it."""
        self.s.ui.settings.tip_angle = 0.0
        self.s.input.set_head(position=(0.0, 1.6, 0.0), look_at_point=(-0.25, 1.2, -0.35))
        self.s.input.set_hand(1, position=(0.3, 1.0, -0.2), point_at=(0.3, 1.0, -2.0))
        self.settle()

    def aim_at_slot(self, slot, page=0):
        from freecad.BlocksCAD.ui import layout as lay, ring as rg
        pose = self.s.ui.ring.poses[page]
        x = (slot % lay.COLS - (lay.COLS - 1) / 2) * (rg.CELL + rg.GAP)
        y = ((lay.ROWS - 1) / 2 - slot // lay.COLS) * (rg.CELL + rg.GAP) + rg.GRID_Y
        point = tuple(c + u * x + v * y for c, u, v in zip(pose.centre, pose.u, pose.v))
        self.s.input.set_hand(1, position=tuple(c + n * 0.3 for c, n in zip(point, pose.n)), point_at=point)
        self.s.frame(0.02)

    def test_a_face_runs_when_the_trigger_is_released_over_it_and_the_quick_radial_remembers_it(self):
        self.show_carousel()
        ui = self.s.ui
        self.assertEqual(ui.radial_items()[:2], ["doc.undo", "doc.redo"])
        page = [p.name for p in ui.layout.pages].index("Edit")
        ui.layout.move_page(page, 0)                                             # next to Tools, on the side at the front
        self.settle(5)
        page = [p.name for p in ui.layout.pages].index("Edit")
        redo = ui.layout.pages[page].slots.index("doc.redo")
        self.aim_at_slot(redo, page)
        self.s.input.set_hand(1, trigger=1.0)
        self.s.frame(0.02)
        self.assertEqual(self.calls, [])
        self.assertTrue(self.s.ui_update.consume_trigger)
        self.s.input.set_hand(1, trigger=0.0)
        self.s.frame(0.02)
        self.assertEqual((self.calls, self.s.ui_update.activated), (["redo"], "doc:redo"))
        self.assertEqual(ui.radial_items()[:2], ["doc.redo", "doc.undo"])        # the face used last comes first

    def test_holding_button1_of_the_tool_hand_opens_the_radial_and_moving_chooses_a_face(self):
        from pivy import coin
        self.show_carousel()
        ui = self.s.ui
        first = ui.radial_items()[0]
        self.assertEqual(first, "doc.undo")
        self.s.input.set_hand(1, button1=True)
        self.s.frame(0.02)
        self.assertEqual(ui.radial_view.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.assertTrue(self.s.ui_update.consume_trigger)
        position = self.s.input.hands[1].aim.position
        self.s.input.set_hand(1, position=(position[0], position[1] + 0.06, position[2]))     # up: the first item
        self.s.frame(0.02)
        self.assertTrue(ui.radial.is_open)
        self.s.input.set_hand(1, button1=False)
        self.s.frame(0.02)
        self.assertEqual(ui.radial_view.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
        self.assertEqual(self.calls, ["undo"])

    def test_the_radial_does_not_open_while_the_world_is_held(self):
        from pivy import coin
        self.show_carousel()
        self.s.input.set_hand(0, grip=1.0)
        self.s.input.set_hand(1, button1=True)
        self.s.frame(0.02)
        self.assertEqual(self.s.ui.radial_view.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
        self.assertTrue(self.s.ui.navigator.level)                                # button1 is the level modifier then

    def test_a_face_held_on_is_lifted_and_dropped_on_a_slot_or_on_the_empty_side_to_hide_it(self):
        self.show_carousel()
        ui = self.s.ui
        tools = [p.name for p in ui.layout.pages].index("Tools")
        face = ui.layout.face_at(tools, 0)
        self.assertIsNotNone(face)
        free = ui.layout.pages[tools].slots.index(None)
        self.aim_at_slot(0, tools)
        self.s.input.set_hand(1, trigger=1.0)
        self.settle(30)                                                          # longer than the hold time
        self.assertEqual(ui.ring.lifted_face, (tools, 0))
        self.assertEqual(self.calls, [])
        self.aim_at_slot(free, tools)
        self.s.input.set_hand(1, trigger=0.0)
        self.s.frame(0.02)
        self.assertEqual((ui.layout.face_at(tools, free), ui.layout.face_at(tools, 0)), (face, None))
        # lift it again and drop it on the empty side that hides it
        self.aim_at_slot(free, tools)
        self.s.input.set_hand(1, trigger=1.0)
        self.settle(30)
        self.assertEqual(ui.ring.lifted_face, (tools, free))
        self.s.input.set_hand(0, stick=(-1.0, 0.0))
        self.s.frame(0.02)
        self.s.input.set_hand(0, stick=(0.0, 0.0))
        self.settle(40)
        ghost = ui.ring.ghosts[max(ui.ring.ghosts)]
        self.s.input.set_hand(1, position=tuple(c + n * 0.3 for c, n in zip(ghost.centre, ghost.n)), point_at=ghost.centre)
        self.s.frame(0.02)
        self.s.input.set_hand(1, trigger=0.0)
        self.s.frame(0.02)
        self.assertEqual((ui.layout.face_at(tools, free), ui.layout.hidden), (None, [face]))
        self.assertNotIn(face, ui.radial_items())
        ui.show_hidden()
        self.assertEqual((ui.layout.hidden, ui.layout.face_at(tools, 0)), ([], face))

    def test_button2_of_the_tool_hand_taps_to_undo_and_holds_to_redo_with_a_toast(self):
        self.s.actions["doc:undo"] = lambda: self.calls.append("undo") or "Undo"
        self.show_carousel()
        self.s.input.set_hand(1, button2=True)
        self.settle(3)
        self.s.input.set_hand(1, button2=False)
        self.s.frame(0.02)
        self.assertEqual(self.calls, ["undo"])
        self.assertEqual([t.text for t in self.s.ui.toasts.items], ["Undo"])
        self.s.input.set_hand(1, button2=True)
        self.settle(25)
        self.assertEqual(self.calls, ["undo", "redo"])
        self.s.input.set_hand(1, button2=False)
        self.settle(2)
        self.assertEqual(self.calls, ["undo", "redo"])

    def test_button2_stays_the_scale_lock_while_a_grip_holds_the_world(self):
        self.show_carousel()
        self.s.input.set_hand(0, grip=1.0)
        self.settle(2)
        self.s.input.set_hand(1, button2=True)
        self.settle(3)
        self.s.input.set_hand(1, button2=False)
        self.settle(2)
        self.assertEqual(self.calls, [])

    def test_toasts_are_drawn_in_front_of_the_head_and_expire(self):
        from pivy import coin
        self.show_carousel()
        self.s.ui.toast("Hello")
        self.settle(10)
        shown = [p for p in self.s.ui.feedback._toasts if p.root.whichChild.getValue() == coin.SO_SWITCH_ALL]
        self.assertEqual([p.label for p in shown], ["Hello"])
        self.settle(int(3.0 / 0.02))
        self.assertTrue(all(p.root.whichChild.getValue() == coin.SO_SWITCH_NONE for p in self.s.ui.feedback._toasts))

    def test_layout_actions_toast(self):
        self.show_carousel()
        self.s.ui._run("layout:reset", self.s.ui_update)
        self.s.ui._run("layout:show_hidden", self.s.ui_update)
        self.assertEqual([t.text for t in self.s.ui.toasts.items], ["Layout reset", "No hidden faces"])

    def test_hovering_a_face_shows_its_tooltip_after_a_moment(self):
        from pivy import coin
        self.show_carousel()
        ui = self.s.ui
        tools = [p.name for p in ui.layout.pages].index("Tools")
        self.aim_at_slot(0, tools)
        self.settle(5)
        self.assertEqual(ui.feedback._tooltip.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
        self.settle(int(0.6 / 0.02))
        self.assertEqual(ui.feedback._tooltip.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.assertEqual(ui.feedback._tooltip.label, ui.faces[ui.layout.face_at(tools, 0)].tip)
        self.assertNotEqual(ui.feedback._tooltip.label, "")
        self.s.input.set_hand(1, position=(0.3, 1.0, -0.2), point_at=(0.3, 1.0, -2.0))      # point away
        self.settle(3)
        self.assertEqual(ui.feedback._tooltip.root.whichChild.getValue(), coin.SO_SWITCH_NONE)

    def test_the_stick_of_the_tool_hand_adjusts_the_options_of_the_active_tool(self):
        from pivy import coin
        from freecad.BlocksCAD.tools import base, registry

        class Sized(base.Tool):
            name, label = "sized", "Sized"
            options = (base.ToolOption("size", "Size", "length", 1.0, 100.0, 1.0, 10.0),)

        registry.register(Sized)
        self.addCleanup(registry.unregister, "sized")
        self.show_carousel()
        ui = self.s.ui
        self.settle(2)
        self.assertFalse(self.s.ui_update.owns_stick)
        self.s.select_tool("sized")
        self.s.input.set_hand(1, stick=(0.0, 1.0))
        self.settle(2)
        self.assertTrue(self.s.ui_update.owns_stick)
        self.assertEqual(ui.active_tool.values["size"], 11.0)
        self.assertEqual(ui.feedback._readout.label, "Size: 11 mm")
        self.assertEqual(ui.feedback._readout.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.s.input.set_hand(1, stick=(0.0, 0.0))
        self.settle(int(2.0 / 0.02))
        self.assertEqual(ui.feedback._readout.root.whichChild.getValue(), coin.SO_SWITCH_NONE)

    def test_the_controller_hides_the_base_of_the_tip(self):
        """The cone of the tip starts inside the controller model: that part must not show in the inverted colours."""
        from freecad.BlocksCAD.ui import style
        target = tuple(round(c * 255) for c in style.invert((0.4, 0.5, 0.65)))     # the inverted colour of the cone

        def inverted_cone_pixels():
            image = self.s.render("head", (400, 300))
            return sum(1 for y in range(image.height()) for x in range(image.width())
                       if all(abs(v - t) < 18 for v, t in zip((image.pixelColor(x, y).red(), image.pixelColor(x, y).green(),
                                                              image.pixelColor(x, y).blue()), target)))

        self.s.ui.settings.pointer_mode = "tip"
        self.s.input.set_head(position=(0.55, 1.3, -0.25), look_at_point=(0.2, 1.2, -0.5))
        self.s.input.set_hand(1, position=(0.2, 1.2, -0.5), point_at=(0.2, 1.2, -2.0))
        self.settle(20)
        hidden = inverted_cone_pixels()
        self.s.ui.occluders.removeAllChildren()                                       # control: without the second pass
        self.s.frame(0.02)
        shown = inverted_cone_pixels()
        self.assertLessEqual(hidden, 2)
        self.assertGreater(shown, 10)

    def test_the_overlay_is_the_last_child_of_the_scene(self):
        self.assertEqual(self.s.scene.findChild(self.s.ui.overlay), self.s.scene.getNumChildren() - 1)


if __name__ == "__main__":
    unittest.main()


class PrimitiveLiveTest(unittest.TestCase):
    """The primitives against real FreeCAD features, and the tool driven through the Sim session."""
    LO, SIZE = (10.0, 20.0, 30.0), (40.0, 60.0, 80.0)

    def setUp(self):
        import FreeCAD as App
        self.App = App
        self.doc = App.newDocument("BlocksCADPrimitives")

    def tearDown(self):
        self.App.closeDocument(self.doc.Name)

    def bounds(self, shape):
        b = shape.optimalBoundingBox(False, False)     # the analytic tight box (the default one of a curved solid is loose)
        return tuple(round(v, 2) for v in (b.XMin, b.YMin, b.ZMin)), tuple(round(v, 2) for v in (b.XLength, b.YLength, b.ZLength))

    def test_every_shape_is_made_inside_its_box_and_the_preview_mesh_matches_the_feature(self):
        from freecad.BlocksCAD.cad import meshes, primitives as prim
        for name in prim.SHAPES:
            obj = prim.create(self.doc, name, self.LO, self.SIZE)
            lo, size = self.bounds(obj.Shape)
            mesh = meshes.build(name, self.LO, self.SIZE)
            self.assertTrue(obj.Shape.isValid(), name)
            self.assertAlmostEqual(meshes.volume(mesh) / obj.Shape.Volume, 1.0, delta=0.035, msg=name)
            for axis in range(3):                                           # the polygonal preview fills the same box
                low = min(p[axis] for p in mesh.points)
                high = max(p[axis] for p in mesh.points)
                self.assertAlmostEqual(low, lo[axis], delta=0.02 * self.SIZE[axis], msg=name)
                self.assertAlmostEqual(high - low, size[axis], delta=0.02 * self.SIZE[axis], msg=name)
            for axis in range(3):                                           # inside the box, and touching it where the shape fills it
                self.assertGreaterEqual(lo[axis], self.LO[axis] - 1e-6, name)
                self.assertLessEqual(lo[axis] + size[axis], self.LO[axis] + self.SIZE[axis] + 1e-6, name)
            if name in ("Box", "Wedge"):
                self.assertEqual((lo, size), (self.LO, self.SIZE), name)
            if name in ("Cylinder", "Cone", "Prism"):
                self.assertAlmostEqual(lo[2], self.LO[2], places=2)
                self.assertAlmostEqual(size[2], self.SIZE[2], places=2)
            if name in ("Sphere", "Torus"):
                centre = (self.LO[0] + self.SIZE[0] / 2, self.LO[1] + self.SIZE[1] / 2, self.LO[2] + self.SIZE[2] / 2)
                for axis in range(2):
                    self.assertAlmostEqual(lo[axis] + size[axis] / 2, centre[axis], places=2)
        self.assertEqual(len(self.doc.Objects), len(prim.SHAPES))

    def test_the_wedge_is_a_ramp_that_rises_towards_plus_y(self):
        from freecad.BlocksCAD.cad import primitives as prim
        wedge = prim.create(self.doc, "Wedge", (0.0, 0.0, 0.0), (40.0, 60.0, 80.0))
        self.assertAlmostEqual(wedge.Shape.Volume, 40.0 * 60.0 * 80.0 / 2, places=3)
        self.assertGreater(wedge.Shape.CenterOfMass.y, 30.0)                        # heavier on the +Y side where the ramp is tall

    def test_a_shape_is_one_undo_step_and_a_parametric_feature(self):
        from freecad.BlocksCAD.cad import primitives as prim
        obj = prim.create(self.doc, "Cylinder", self.LO, self.SIZE)
        self.assertEqual((obj.TypeId, obj.Radius.Value, obj.Height.Value), ("Part::Cylinder", 20.0, 80.0))
        obj.Radius = 10.0                                                          # editable afterwards
        self.doc.recompute()
        self.assertAlmostEqual(obj.Shape.optimalBoundingBox(False, False).XLength, 20.0, places=2)
        self.doc.undo()                                                            # undoes the radius edit
        self.doc.undo()                                                            # and the creation
        self.assertEqual(len(self.doc.Objects), 0)
        self.doc.redo()
        self.assertEqual(len(self.doc.Objects), 1)

    def test_a_failed_shape_leaves_the_document_unchanged(self):
        from freecad.BlocksCAD.cad import primitives as prim
        with self.assertRaises(Exception):
            prim.create(self.doc, "Box", self.LO, (0.0, 0.0, 0.0))
        self.assertEqual(len(self.doc.Objects), 0)

    def test_the_tool_makes_a_box_from_a_drag_in_the_sim_and_undo_removes_it(self):
        from pivy import coin
        from freecad.BlocksCAD.core import stage
        s = sim.SimSession(None)
        try:
            s.ui.settings.pointer_mode = "tip"
            s.select_tool("primitive")
            to_stage = lambda p: stage.to_stage(s.navigator.world, p)
            s.input.set_head(position=(0.0, 1.6, 0.4), look_at_point=to_stage((20.0, 20.0, 0.0)))
            tip = s.ui.settings.tip_length

            def put(point_mm, **inputs):
                aim_point = to_stage(point_mm)
                # the cursor is `tip_length` ahead of the controller along its tilted aim; point the controller straight down -Y
                s.input.set_hand(1, position=aim_point, point_at=(aim_point[0], aim_point[1], aim_point[2] - 1.0), **inputs)
                s.frame(0.02)

            s.ui.settings.tip_angle = 0.0
            put((0.0, 0.0, 0.0))
            offset = s.ui.cursor(s.last_frame.hands[1])
            cursor_shift = tuple(o - p for o, p in zip(offset, s.last_frame.hands[1].aim.position))
            self.assertAlmostEqual(sum(c * c for c in cursor_shift) ** 0.5, tip, places=6)

            def put_cursor(point_mm, **inputs):
                target = to_stage(point_mm)
                position = tuple(t - c for t, c in zip(target, cursor_shift))
                s.input.set_hand(1, position=position, **inputs)
                s.frame(0.02)

            put_cursor((0.0, 0.0, 0.0))
            self.assertEqual(s.ghost._marker.whichChild.getValue(), coin.SO_SWITCH_ALL)
            put_cursor((0.0, 0.0, 0.0), trigger=1.0)
            put_cursor((30.0, 20.0, 10.0), trigger=1.0)
            self.assertEqual(s.ghost._body.whichChild.getValue(), coin.SO_SWITCH_ALL)
            self.assertEqual(s.ui.gesture_text, "Box: 30 mm x 20 mm x 10 mm")
            put_cursor((30.0, 20.0, 10.0), trigger=0.0)
            self.assertEqual(len(self.doc.Objects), 1)
            box = self.doc.Objects[0]
            self.assertEqual((box.TypeId, box.Length.Value, box.Width.Value, box.Height.Value), ("Part::Box", 30.0, 20.0, 10.0))
            self.assertEqual(tuple(box.Placement.Base), (0.0, 0.0, 0.0))
            self.assertEqual(s.ghost._body.whichChild.getValue(), coin.SO_SWITCH_NONE)
            self.assertIsNone(s.ui.gesture_text)
            self.assertTrue(any(t.text.startswith("Box made") for t in s.ui.toasts.items))
            s.actions["doc:undo"] = lambda: self.doc.undo()
            s.ui._run("doc:undo", s.ui_update)
            self.assertEqual(len(self.doc.Objects), 0)
        finally:
            s.close()

    def test_dragging_a_torus_updates_the_preview_quickly(self):
        import time
        from freecad.BlocksCAD.core import stage
        s = sim.SimSession(None)
        try:
            s.ui.settings.pointer_mode = "tip"
            s.ui.settings.tip_angle = 0.0
            s.select_tool("primitive")
            s.tool_manager.active.values["shape"] = "Torus"
            s.tool_manager.active.values["grid"] = "1 mm"           # every step of the hand is a new box: the worst case
            s.input.set_hand(1, position=stage.to_stage(s.navigator.world, (0.0, 0.0, 0.0)), trigger=1.0)
            s.frame(0.02)
            durations = []
            for i in range(1, 41):
                s.input.set_hand(1, position=stage.to_stage(s.navigator.world, (i * 2.0, i * 1.5, i)), trigger=1.0)
                start = time.perf_counter()
                s.frame(0.02)
                durations.append(time.perf_counter() - start)
            self.assertLess(sum(durations) / len(durations), 0.012)
            self.assertLess(max(durations), 0.05)
        finally:
            s.close()

    def test_the_stick_changes_the_grid_and_the_shape_with_a_readout(self):
        s = sim.SimSession(None)
        try:
            s.select_tool("primitive")
            s.input.set_hand(1, stick=(0.0, 1.0))
            s.frame(0.02)
            s.input.set_hand(1, stick=(0.0, 0.0))
            s.frame(0.02)
            self.assertEqual(s.tool_manager.active.values["grid"], "20 mm")
            self.assertEqual(s.ui.feedback._readout.label, "Grid: 20 mm")
            s.input.set_hand(1, stick=(1.0, 0.0))
            s.frame(0.02)
            self.assertEqual(s.tool_manager.active.values["shape"], "Cylinder")
            self.assertTrue(s.ui_update.owns_stick)
        finally:
            s.close()
