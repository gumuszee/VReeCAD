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

    def test_the_overlay_is_the_last_child_of_the_scene(self):
        self.assertEqual(self.s.scene.findChild(self.s.ui.overlay), self.s.scene.getNumChildren() - 1)


if __name__ == "__main__":
    unittest.main()
