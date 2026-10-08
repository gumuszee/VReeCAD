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
        names = [p.name for p in self.s.ui.layout.pages]
        self.assertEqual(self.s.ui.slider_rows(), {names.index("Pointer"): {1: "pointer.angle", 2: "pointer.length"},
                                                   names.index("Settings"): {1: "settings.grid", 2: "settings.angle"}})
        self.assertEqual((labels["settings.grid"], labels["settings.angle"]), ("Grid 10 mm", "Angle step 15\u00b0"))
        self.assertEqual((self.s.ui.slider_states()["settings.grid"][0], self.s.ui.slider_states()["settings.angle"][0]), (0.5, 0.25))
        self.s.ui.settings.grid = 50.0
        self.assertEqual(self.s.ui.labels()["settings.grid"], "Grid 50 mm")
        self.s.select_tool("move")
        self.assertEqual(self.s.tool_manager.active.grid, 50.0)                            # every tool takes the grid from the settings
        self.s.ui.settings.grid = 10.0
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

    def card_plates(self):
        from pivy import coin
        return [[p for p in card.plates if p.root.whichChild.getValue() == coin.SO_SWITCH_ALL] for card in self.s.ui.feedback._cards]

    def test_the_controls_face_shows_a_card_over_each_controller_and_the_tool_decides_what_the_tool_hand_card_says(self):
        import types
        self.show_carousel()
        ui = self.s
        ui.select_tool("move")
        face = ui.ui.faces["settings.tutorial"]
        self.assertEqual(face.action, "help:toggle")
        self.assertEqual([len(c) for c in self.card_plates()], [0, 0])
        ui.ui._run(face.action, types.SimpleNamespace(haptics=[]))
        self.settle(3)
        tool_card, palette_card = self.card_plates()
        self.assertEqual(self.s.ui.toasts.items[-1].text, "Controls shown")
        self.assertEqual(tool_card[0].label, "Move: tool hand")                           # the active tool of the session
        self.assertEqual(tool_card[1].label, "Trigger: tap: select, hold: move and turn")
        self.assertEqual(palette_card[0].label, "Palette hand")
        self.assertEqual(len({p._width for p in tool_card}), 1)                           # one width for the whole card
        self.assertGreater(len(palette_card), 4)
        ui.ui._run(face.action, types.SimpleNamespace(haptics=[]))
        self.settle(3)
        self.assertEqual([len(c) for c in self.card_plates()], [0, 0])

    def test_the_cards_show_once_on_the_first_run_and_the_setting_is_saved_when_they_go(self):
        import os
        import tempfile
        from freecad.BlocksCAD.tools import registry
        from freecad.BlocksCAD.ui import help as controls_help
        from freecad.BlocksCAD.ui import settings as cfg
        from freecad.BlocksCAD.ui.controller import UiController
        with tempfile.TemporaryDirectory() as folder:
            paths = dict(layout_path=os.path.join(folder, "layout.json"), settings_path=os.path.join(folder, "settings.json"))
            first = UiController(registry.names(), registry.label_of, {}, **paths)
            try:
                first.show_first_help()
                self.assertTrue(first.help.visible)
                self.assertFalse(cfg.load_settings(paths["settings_path"]).onboarded)       # not before they have been seen
                if first.help.update(controls_help.SHOW_SECONDS):                           # the time is up, as in `update`
                    first._help_ended()
                self.assertTrue(cfg.load_settings(paths["settings_path"]).onboarded)
            finally:
                first.close()
            second = UiController(registry.names(), registry.label_of, {}, **paths)
            try:
                second.show_first_help()
                self.assertFalse(second.help.visible)                                       # seen once: it stays away
            finally:
                second.close()

    def test_swapping_the_hands_gives_the_palette_to_the_other_hand_and_everything_of_a_hand_follows(self):
        import types
        ui = self.s.ui
        self.assertEqual((ui.tool_hand, ui.palette_hand), (1, 0))
        face = ui.faces["pointer.hands"]
        self.assertEqual(face.action, "hands:swap")
        ui._run(face.action, types.SimpleNamespace(haptics=[]))
        self.assertEqual(ui.toasts.items[-1].text, "Tool hand: left")
        self.assertEqual((ui.tool_hand, ui.palette_hand), (0, 1))
        self.assertEqual((ui.ring.tool_hand, ui.ring.palette_hand, ui.navigator.modifier_hand), (0, 1, 0))
        self.assertEqual([part.hand for part in (ui.radial, ui.undo_button, ui.module, ui.options)], [0, 0, 0, 0])
        self.assertEqual(self.s.tool_manager.ctx.dominant, 0)                              # the tools work with the new tool hand
        self.s.input.set_hand(0, button2=True)                                              # B of the new tool hand undoes
        self.settle(3)
        self.s.input.set_hand(0, button2=False)
        self.s.frame(0.02)
        self.assertEqual(self.calls, ["undo"])
        self.s.input.set_hand(1, aux1=True)                                                 # the D-pad shortcut belongs to the palette hand
        self.s.frame(0.02)
        self.s.input.set_hand(1, aux1=False)
        self.s.frame(0.02)
        self.assertEqual(self.calls, ["undo", "undo"])
        ui._run(face.action, types.SimpleNamespace(haptics=[]))
        self.assertEqual((ui.toasts.items[-1].text, ui.tool_hand, self.s.tool_manager.ctx.dominant), ("Tool hand: right", 1, 1))

    def test_the_tool_hand_is_saved_and_the_next_start_has_the_hands_the_way_they_were(self):
        import os
        import tempfile
        from freecad.BlocksCAD.tools import registry
        from freecad.BlocksCAD.ui import settings as cfg
        from freecad.BlocksCAD.ui.controller import UiController
        with tempfile.TemporaryDirectory() as folder:
            paths = dict(layout_path=os.path.join(folder, "layout.json"), settings_path=os.path.join(folder, "settings.json"))
            first = UiController(registry.names(), registry.label_of, {}, **paths)
            told = []
            first.hands_changed = told.append
            try:
                first.swap_hands()
                self.assertEqual(cfg.load_settings(paths["settings_path"]).tool_hand, "left")
                self.assertEqual(told, [0])
            finally:
                first.close()
            second = UiController(registry.names(), registry.label_of, {}, **paths)
            try:
                self.assertEqual(second.tool_hand, 1)                                       # until the host applies the setting
                second.apply_handedness()
                self.assertEqual((second.tool_hand, second.palette_hand), (0, 1))
            finally:
                second.close()

    def test_the_small_lengths_face_changes_between_decimal_millimetres_and_micrometres_and_is_saved(self):
        import os
        import tempfile
        import types
        from freecad.BlocksCAD.core import units
        from freecad.BlocksCAD.tools import registry
        from freecad.BlocksCAD.ui import settings as cfg
        from freecad.BlocksCAD.ui.controller import UiController
        ui = self.s.ui
        face = ui.faces["pointer.submm"]
        self.assertEqual(face.action, "units:submm")
        self.assertIn(face.id, [f for page in ui.layout.pages for f in page.slots])         # on a panel of the default layout
        self.assertEqual(units.format_length(0.25, ui.system), "0.25 mm")
        self.assertEqual(ui.labels()["pointer.submm"], "Small: 0.1 mm")
        ui._run(face.action, types.SimpleNamespace(haptics=[]))
        self.assertEqual(units.format_length(0.25, ui.system), "250 µm")
        self.assertEqual(ui.labels()["pointer.submm"], "Small: 100 µm")
        ui.set_unit_system("Standard (mm, kg, s, degree)")                                  # a document with the same system keeps the choice
        self.assertEqual(units.format_length(0.25, ui.system), "250 µm")
        ui._run(face.action, types.SimpleNamespace(haptics=[]))
        self.assertEqual(units.format_length(0.25, ui.system), "0.25 mm")
        with tempfile.TemporaryDirectory() as folder:
            paths = dict(layout_path=os.path.join(folder, "layout.json"), settings_path=os.path.join(folder, "settings.json"))
            first = UiController(registry.names(), registry.label_of, {}, **paths)
            try:
                first.toggle_sub_mm()
                self.assertEqual(cfg.load_settings(paths["settings_path"]).sub_mm, "um")
            finally:
                first.close()
            second = UiController(registry.names(), registry.label_of, {}, **paths)
            try:
                self.assertEqual(units.format_length(0.25, second.system), "250 µm")
            finally:
                second.close()

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
        self.assertEqual(ui.feedback._tooltip.label.replace("\n", " "), ui.faces[ui.layout.face_at(tools, 0)].tip)
        self.assertNotEqual(ui.feedback._tooltip.label, "")
        self.s.input.set_hand(1, position=(0.3, 1.0, -0.2), point_at=(0.3, 1.0, -2.0))      # point away
        self.settle(3)
        self.assertEqual(ui.feedback._tooltip.root.whichChild.getValue(), coin.SO_SWITCH_NONE)

    def test_a_hovered_face_stands_half_a_centimetre_in_front_of_its_panel_and_goes_back(self):
        from freecad.BlocksCAD.ui import ring_view as rv
        self.show_carousel()
        ui = self.s.ui
        tools = [p.name for p in ui.layout.pages].index("Tools")
        panel = ui.view._panels[tools]
        cell = panel.cells[0][0]
        z = lambda: panel.plates.rects[cell.plate.index][4]
        self.assertAlmostEqual(z(), rv.DEPTH * 0.5)
        self.aim_at_slot(0, tools)
        self.settle(2)
        self.assertTrue(cell.raised)
        self.assertAlmostEqual(z(), rv.DEPTH * 0.5 + 0.005)
        self.s.input.set_hand(1, position=(0.3, 1.0, -0.2), point_at=(0.3, 1.0, -2.0))      # point away
        self.settle(3)
        self.assertFalse(cell.raised)
        self.assertAlmostEqual(z(), rv.DEPTH * 0.5)

    def test_the_keys_of_the_number_pad_have_no_tooltip(self):
        from freecad.BlocksCAD.ui import value_module as vm
        ui = self.s.ui
        for face_id in ("key.0", "key.9", "key.point", "key.plus", "key.open"):
            self.assertIn(face_id, vm.NO_TOOLTIP)
        for face_id in ("key.enter", "key.unit", "key.makevar", "key.delete"):
            self.assertNotIn(face_id, vm.NO_TOOLTIP)

    def test_a_label_plate_is_as_wide_as_its_text_and_a_long_tooltip_is_broken_into_lines(self):
        from freecad.BlocksCAD.ui import feedback_view as fv
        plate = fv.LabelPlate()
        plate.set_text("Undo")
        short = plate._plate_width.getValue()
        plate.set_text("iiiiiiiiiiiiiiii")
        narrow = plate._plate_width.getValue()
        plate.set_text("WWWWWWWWWWWWWWWW")
        wide = plate._plate_width.getValue()
        self.assertLess(narrow, wide)                                                      # the width follows the glyphs, not the count
        self.assertAlmostEqual(narrow, fv.text_width("iiiiiiiiiiiiiiii") + 2 * fv.PAD, places=6)
        self.assertLess(short, narrow)
        plate.set_text("one"+chr(10)+"two"+chr(10)+"three")
        self.assertEqual(plate.lines, 3)
        self.assertAlmostEqual(plate._plate_height.getValue(), fv.HEIGHT + 2 * fv.LINE_PITCH)
        plate.set_text("8")
        self.assertEqual(plate._string.getNum(), 1)                                        # no line of the longer text stays behind
        self.assertAlmostEqual(plate._plate_height.getValue(), fv.HEIGHT)
        first = fv.text_width("8")
        fv.text_width("WWWWWWWWWW" + chr(10) + "WWWWWWWWWW")
        self.assertAlmostEqual(fv.text_width("8"), first)                                  # the measure does not keep the lines of an earlier text
        self.assertLess(fv.text_width("x" * fv.TOOLTIP_CHARS) + 2 * fv.PAD, 0.3)           # and a line of a tooltip is narrow

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

    def test_the_panels_are_tinted_by_name_and_the_value_panels_stay_grey(self):
        from freecad.BlocksCAD.ui import style, value_module

        def contrast(a, b):
            high, low = sorted((style.luminance(a), style.luminance(b)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        names = [page.name for page in self.s.ui.layout.pages]
        palettes = [style.panel_palette(name) for name in names]
        self.assertEqual(len({p.face for p in palettes}), len(names))
        self.assertEqual(style.panel_palette("Something else"), style.panel_palette("Something else"))
        for name in value_module.PAGE_NAMES:
            self.assertEqual(style.panel_palette(name, plain=True), style.DEFAULT_PALETTE)
        for palette in palettes + [style.DEFAULT_PALETTE]:
            self.assertGreaterEqual(contrast(style.TEXT, palette.face), 7.0)
            self.assertGreaterEqual(contrast(style.TEXT, palette.plate), 7.0)
            self.assertGreaterEqual(contrast(style.TEXT_DIM, palette.title), 4.5)
            self.assertGreaterEqual(contrast(palette.face, palette.empty), 1.1)
            self.assertGreaterEqual(contrast(style.HOVER, palette.face), 2.0)
            self.assertGreaterEqual(contrast(style.ACTIVE, palette.face), 4.0)
        views = {view.palette for view in self.s.ui.view._panels} if self.s.ui.view._panels else set()
        self.assertTrue(views <= set(palettes) | {style.DEFAULT_PALETTE})

    def test_a_still_carousel_writes_nothing_to_the_contents_of_its_panels(self):
        from pivy import coin
        self.s.input.set_head(position=(0.0, 1.6, 0.0), look_at_point=(-0.25, 1.2, -0.35))
        for _ in range(30):
            self.s.frame(0.02)
        panel = self.s.ui.view._panels[0]
        self.assertGreater(self.s.ui.ring.fade, 0.99)
        changes = []
        sensor = coin.SoNodeSensor(lambda *args: changes.append(1), None)
        sensor.setPriority(0)                      # immediate: fires when the node or something below it is notified
        sensor.attach(panel.front)
        for _ in range(10):
            self.s.frame(0.02)
        self.assertEqual(changes, [])
        self.s.ui.settings.tip_angle = 0.0
        self.s.input.set_hand(1, position=(0.25, 1.5, -0.25), point_at=self.s.ui.ring.slot_centre(0, 1)[0])
        for _ in range(3):
            self.s.frame(0.02)                     # a hover lights a face: now something is written
        self.assertGreater(len(changes), 0)
        sensor.detach()

    def test_a_moving_controller_writes_only_the_transform_of_the_carousel(self):
        from pivy import coin
        self.s.input.set_head(position=(0.0, 1.6, 0.0), look_at_point=(-0.25, 1.2, -0.35))
        self.s.input.set_hand(0, position=(-0.25, 1.2, -0.35), point_at=(0.0, 1.2, -1.0))      # a panel that turns away from the head is hidden: start in place
        for _ in range(30):
            self.s.frame(0.02)
        changes = []
        sensor = coin.SoNodeSensor(lambda *args: changes.append(1), None)
        sensor.setPriority(0)
        sensor.attach(self.s.ui.view._panels_sep)
        for k in range(10):
            self.s.input.set_hand(0, position=(-0.25 + 0.002 * k, 1.2, -0.35), point_at=(0.0, 1.2, -1.0))
            self.s.frame(0.02)
        self.assertEqual(changes, [])               # the panels stand in the frame of the carousel: a moving hand does not touch them
        sensor.detach()

    def test_the_carousel_is_drawn_with_a_handful_of_shapes_and_no_cubes(self):
        from pivy import coin

        def count(kind):
            action = coin.SoSearchAction()
            action.setType(kind.getClassTypeId())
            action.setInterest(coin.SoSearchAction.ALL)
            action.setSearchingAll(True)
            action.apply(self.s.ui.view.root)
            return action.getPaths().getLength()

        self.show_carousel()
        panels = len(self.s.ui.view._panels)
        self.assertEqual(count(coin.SoFaceSet), 2 * panels + 1 + len(self.s.ui.view._ghosts) * 1)    # the plates of each panel and its back, the card
        self.assertLessEqual(count(coin.SoCube), 1)                                                   # only the marker of a drop
        self.assertLess(count(coin.SoSeparator), 40 * panels)

    def test_a_panel_that_has_not_changed_is_not_refreshed(self):
        self.show_carousel()
        for _ in range(5):
            self.s.frame(0.02)
        panel = self.s.ui.view._panels[0]
        self.assertTrue(panel.facing)
        key = panel.key
        self.assertIsNotNone(key)
        calls = []
        original = self.s.ui.view._refresh
        self.s.ui.view._refresh = lambda *args: calls.append(args[1]) or original(*args)
        for _ in range(5):
            self.s.frame(0.02)
        self.assertEqual(calls, [])
        self.s.ui.settings.tip_angle = 0.0
        self.s.input.set_hand(1, position=(0.25, 1.5, -0.25), point_at=self.s.ui.ring.slot_centre(0, 1)[0])
        for _ in range(3):
            self.s.frame(0.02)
        self.assertIn(0, calls)                     # a hover on the panel refreshes it
        self.s.ui.view._refresh = original

    def test_a_panel_seen_from_behind_draws_only_its_plate(self):
        from pivy import coin
        self.s.input.set_head(position=(0.0, 1.6, 0.0), look_at_point=(-0.25, 1.2, -0.35))
        for _ in range(30):
            self.s.frame(0.02)
        views = self.s.ui.view._panels
        ring = self.s.ui.ring
        head = self.s.input.head.position
        from freecad.BlocksCAD.core import mathutil as mu
        for index, view in enumerate(views):
            pose = ring.poses[index]
            facing = mu.dot(mu.sub(head, pose.centre), pose.n) > 0.0
            self.assertEqual(view.facing, facing)
            self.assertEqual(view.front.whichChild.getValue(), coin.SO_SWITCH_ALL if facing else coin.SO_SWITCH_NONE)
        self.assertTrue(any(v.facing for v in views) and not all(v.facing for v in views))


if __name__ == "__main__":
    unittest.main()


class PrimitiveLiveTest(unittest.TestCase):
    """The primitives against real FreeCAD features, and the tool driven through the Sim session."""
    LO, SIZE = (10.0, 20.0, 30.0), (40.0, 60.0, 80.0)

    def setUp(self):
        import FreeCAD as App
        self.App = App
        self.doc = App.newDocument("BlocksCADPrimitives")
        self.doc.UndoMode = 1                       # the desktop has it on; a document without a GUI has not

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
            s.ui.settings.grid = 1.0                                 # every step of the hand is a new box: the worst case
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

    def test_the_stick_chooses_from_the_option_disc_of_the_create_tool(self):
        import math
        from pivy import coin
        s = sim.SimSession(None)
        try:
            s.select_tool("primitive")
            tool = s.tool_manager.active
            push = lambda degrees: s.input.set_hand(1, stick=(math.sin(math.radians(degrees)), math.cos(math.radians(degrees))))
            push(0)                                                          # up: no section, nothing happens
            s.frame(0.02)
            self.assertEqual(tool.values["shape"], "Box")
            push(60)                                                         # upper right: the second shape
            s.frame(0.02)
            self.assertEqual(tool.values["shape"], "Cylinder")
            self.assertEqual(s.ui.options_view.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
            self.assertTrue(s.ui_update.owns_stick)
            s.input.set_hand(1, stick=(0.0, 0.0))
            for _ in range(int(2.0 / 0.02)):
                s.frame(0.02)
            self.assertEqual(s.ui.options_view.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
            s.input.set_hand(1, stick_click=True)                            # the click turns to the other shapes
            s.frame(0.02)
            self.assertEqual([t.text for t in s.ui.toasts.items][-1], "Shapes: Torus, Wedge, Prism, Block")
            s.input.set_hand(1, stick_click=False)
            s.frame(0.02)
            push(300)                                                        # upper left: the first shape of the page
            s.frame(0.02)
            self.assertEqual(tool.values["shape"], "Torus")
        finally:
            s.close()


class MoveLiveTest(unittest.TestCase):
    """Picking, the Move tool and the Select tool against real FreeCAD objects, driven through the Sim session."""

    def setUp(self):
        import FreeCAD as App
        from freecad.BlocksCAD.cad import primitives as prim
        self.App = App
        self.doc = App.newDocument("BlocksCADMove")
        self.doc.UndoMode = 1
        self.box = prim.create(self.doc, "Box", (0.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        self.s = None

    def tearDown(self):
        if self.s is not None:
            self.s.close()
        self.App.closeDocument(self.doc.Name)

    def session(self):
        from freecad.BlocksCAD.core import mathutil as mu, stage
        s = self.s = sim.SimSession(None)
        s.ui.settings.pointer_mode = "tip"
        s.ui.settings.tip_angle = 0.0
        s.select_tool("move")
        s.input.set_head(position=(0.0, 1.6, 0.4), look_at_point=stage.to_stage(s.navigator.world, (50.0, 50.0, 50.0)))
        self.mu, self.stage = mu, stage
        self.tip = s.ui.settings.tip_length
        return s

    def hand(self, index, point, doc_rotation=None, **inputs):
        """Put the cursor (the tip) of a hand at a document point, the hand turned by `doc_rotation` (document axes)."""
        mu, stage, s = self.mu, self.stage, self.s
        world = s.navigator.world
        base = stage.orientation_to_document(world, s.input.hands[index].aim.orientation) if doc_rotation is None else doc_rotation
        q_stage = mu.quat_multiply(world.rotation, mu.quat_multiply(stage.Z_UP, base))
        shift = mu.rotate(q_stage, (0.0, 0.0, -self.tip))
        position = tuple(c - d for c, d in zip(stage.to_stage(world, point), shift))
        s.input.set_hand(index, position=position, orientation=q_stage, **inputs)
        s.frame(0.02)

    def selection(self):
        import FreeCADGui as Gui
        return [(o.ObjectName, tuple(o.SubElementNames)) for o in Gui.Selection.getSelectionEx(self.doc.Name)]

    def test_picking_prefers_a_corner_over_an_edge_over_a_face_over_the_inside(self):
        from freecad.BlocksCAD.cad import picking
        probe = lambda p: picking.pick(self.doc, p, 1000.0)
        self.assertIsNone(probe((400.0, 400.0, 400.0)))
        self.assertEqual(probe((3.0, 3.0, 3.0)).kind, "vertex")
        edge = probe((50.0, 4.0, 4.0))
        self.assertEqual((edge.kind, edge.name), ("edge", self.box.Name))
        face = probe((50.0, 50.0, 96.0))
        top = 1 + [f.CenterOfMass.z for f in self.box.Shape.Faces].index(100.0)
        self.assertEqual((face.kind, face.sub), ("face", f"Face{top}"))
        inside = probe((50.0, 50.0, 50.0))
        self.assertEqual((inside.kind, inside.sub), ("object", ""))
        self.box.Visibility = False
        self.assertIsNone(probe((50.0, 50.0, 96.0)))                                          # hidden objects are not touched

    def test_the_reach_shrinks_when_the_world_is_enlarged(self):
        from freecad.BlocksCAD.cad import picking
        self.assertEqual(picking.pick(self.doc, (50.0, 50.0, 125.0), 1000.0).kind, "face")     # 25 mm above the top: within 30 mm
        self.assertIsNone(picking.pick(self.doc, (50.0, 50.0, 125.0), 500.0))                  # at twice the scale only 15 mm

    def test_the_display_of_each_kind_of_element(self):
        from freecad.BlocksCAD.cad import picking
        self.assertEqual(len(picking.display(self.box, "Vertex1").markers), 1)
        edge = picking.display(self.box, "Edge1")
        self.assertEqual((len(edge.polylines), len(edge.triangles[1])), (1, 0))
        face = picking.display(self.box, "Face1")
        self.assertEqual((len(face.triangles[1]), len(face.polylines)), (2, 4))
        self.assertEqual(len(picking.display(self.box, "").polylines), 12)
        self.assertEqual(picking.kind_of("Face3"), "face")

    def test_touching_an_object_highlights_it_and_leaving_removes_the_highlight(self):
        from pivy import coin
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        self.assertEqual(s.highlights.hover.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.assertEqual(s.tool_manager.active._hover.kind, "face")
        self.hand(1, (50.0, 50.0, 500.0))
        self.assertEqual(s.highlights.hover.root.whichChild.getValue(), coin.SO_SWITCH_ALL)      # a moment passes before it goes
        for _ in range(10):
            self.hand(1, (50.0, 50.0, 500.0))
        self.assertEqual(s.highlights.hover.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
        self.assertIsNone(s.tool_manager.active._hover)

    def test_a_trembling_hand_does_not_make_the_highlight_jump_between_elements(self):
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        tool = s.tool_manager.active
        self.assertEqual(tool._hover.kind, "face")
        for i in range(8):                                                       # it jumps between a face and an edge every frame
            self.hand(1, (50.0, 4.0 if i % 2 else 50.0, 96.0))
        self.assertEqual(tool._hover.kind, "face")
        for _ in range(8):                                                       # held at the edge for a moment: it moves to the edge
            self.hand(1, (50.0, 4.0, 96.0))
        self.assertEqual(tool._hover.kind, "edge")

    def test_the_highlight_of_a_solid_the_tip_is_inside_is_a_fill_and_the_hover_lies_in_front_of_the_selection(self):
        s = self.session()
        self.hand(1, (50.0, 50.0, 50.0))
        tool = s.tool_manager.active
        self.assertEqual(tool._hover.kind, "object")
        display = tool._display(self.doc, tool._hover.name, "")[0]
        self.assertGreater(len(display.triangles[1]), 0)                         # the whole object is filled, not just outlined
        from freecad.BlocksCAD.render import highlight
        self.assertLess(highlight.DEPTH_RANGE[1], highlight.DEPTH_RANGE[0])      # the hover is nearer to the viewer

    def test_a_drag_moves_the_object_freely_and_in_grid_steps_while_a_is_held_in_one_undo_step(self):
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (84.0, 50.0, 96.0), trigger=1.0)                       # free: 34 mm
        base = tuple(round(c, 6) for c in self.box.Placement.Base)
        self.assertEqual(base, (34.0, 0.0, 0.0))
        self.assertTrue(s.ui.gesture_text.startswith("Move: 34 mm, 0, 0"))
        self.hand(1, (84.0, 50.0, 96.0), trigger=1.0, button1=True)         # A held: locked to the grid, 34 mm becomes 30
        self.assertEqual(tuple(round(c, 6) for c in self.box.Placement.Base), (30.0, 0.0, 0.0))
        self.hand(1, (84.0, 73.0, 126.0), trigger=1.0, button1=True)
        self.hand(1, (84.0, 73.0, 126.0), trigger=0.0, button1=False)
        self.assertEqual(tuple(round(c, 6) for c in self.box.Placement.Base), (30.0, 20.0, 30.0))
        self.assertIsNone(s.ui.gesture_text)
        self.assertEqual([t.text for t in s.ui.toasts.items][-1], "Moved " + self.box.Label)
        self.assertEqual(self.selection(), [(self.box.Name, ())])           # the moved object is selected as a whole
        from freecad.BlocksCAD.cad import picking
        self.assertEqual(picking.get_selection(self.doc), [(self.box.Name, "")])
        self.doc.undo()
        self.assertEqual(tuple(self.box.Placement.Base), (0.0, 0.0, 0.0))

    def test_a_free_grab_lines_the_box_of_the_object_up_with_the_model_and_a_locked_grab_does_not(self):
        from freecad.BlocksCAD.cad import anchors, primitives as prim
        prim.create(self.doc, "Box", (300.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        s = self.session()
        s.tool_manager.active.ctx.services["guide_anchors"] = lambda exclude: (anchors.collect(self.doc, exclude), 8.0)
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (244.0, 53.0, 96.0), trigger=1.0)                     # 194 mm along X and 3 mm along Y by hand
        self.assertEqual(tuple(round(c, 6) for c in self.box.Placement.Base), (200.0, 0.0, 0.0))      # level with the other box: 6 and 3 mm taken up
        self.assertIsNotNone(s.tool_manager.active._guide_key)
        self.hand(1, (244.0, 53.0, 96.0), trigger=1.0, button1=True)       # A held: only the grid, 194 mm becomes 190
        self.assertEqual(tuple(round(c, 6) for c in self.box.Placement.Base), (190.0, 0.0, 0.0))
        self.assertIsNone(s.tool_manager.active._guide_key)
        self.hand(1, (244.0, 53.0, 96.0), trigger=0.0, button1=False)
        self.doc.undo()
        self.assertEqual(tuple(self.box.Placement.Base), (0.0, 0.0, 0.0))

    def test_a_turn_of_the_hand_turns_the_object_in_steps_of_15_degrees_unless_the_mode_is_move(self):
        import math
        s = self.session()
        mu = self.mu
        rotation = lambda degrees: mu.quat_from_axis_angle((0.0, 0.0, 1.0), math.radians(degrees))
        start = self.stage.orientation_to_document(s.navigator.world, s.input.hands[1].aim.orientation)
        turned = mu.quat_multiply(rotation(100.0), start)
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (50.0, 50.0, 96.0), doc_rotation=turned, trigger=1.0)          # free: exactly 100 degrees
        self.assertAlmostEqual(math.degrees(self.box.Placement.Rotation.Angle), 100.0, places=3)
        self.hand(1, (50.0, 50.0, 96.0), doc_rotation=turned, trigger=1.0, button1=True)   # A held: the angle step of 15 gives 105
        self.assertAlmostEqual(math.degrees(self.box.Placement.Rotation.Angle), 105.0, places=3)
        self.hand(1, (50.0, 50.0, 96.0), doc_rotation=turned, trigger=0.0, button1=False)
        self.assertEqual([t.text for t in s.ui.toasts.items][-1], "Moved and turned " + self.box.Label)
        self.doc.undo()
        self.assertAlmostEqual(self.box.Placement.Rotation.Angle, 0.0, places=6)
        s.tool_manager.active.values["mode"] = "Move"
        self.hand(1, (50.0, 50.0, 96.0), doc_rotation=start)
        self.hand(1, (50.0, 50.0, 96.0), doc_rotation=start, trigger=1.0)
        self.hand(1, (80.0, 50.0, 96.0), doc_rotation=mu.quat_multiply(rotation(90.0), start), trigger=1.0)
        self.assertAlmostEqual(self.box.Placement.Rotation.Angle, 0.0, places=6)
        self.assertEqual(tuple(round(c, 6) for c in self.box.Placement.Base), (30.0, 0.0, 0.0))
        self.hand(1, (80.0, 50.0, 96.0), doc_rotation=start, trigger=0.0)

    def test_a_tap_selects_the_touched_element_and_a_tap_on_nothing_clears_the_selection(self):
        from pivy import coin
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        face = s.tool_manager.active._hover.sub
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (50.0, 50.0, 96.0), trigger=0.0)
        self.assertEqual(self.selection(), [(self.box.Name, (face,))])
        self.assertEqual(tuple(self.box.Placement.Base), (0.0, 0.0, 0.0))                      # a tap moves nothing
        self.assertEqual(s.highlights.selected.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        for _ in range(10):
            self.hand(1, (400.0, 400.0, 400.0))                          # long enough for the hover to let go of the box
        self.hand(1, (400.0, 400.0, 400.0), trigger=1.0)
        self.hand(1, (400.0, 400.0, 400.0), trigger=0.0)
        self.assertEqual(self.selection(), [])
        self.assertEqual(s.highlights.selected.root.whichChild.getValue(), coin.SO_SWITCH_NONE)

    def test_the_trigger_of_the_other_hand_scales_the_size_properties_around_the_centre(self):
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(0, (150.0, 50.0, 96.0), trigger=1.0)                       # the hands are 100 mm apart
        self.hand(0, (250.0, 50.0, 96.0), trigger=1.0)                       # 200 mm apart: twice the size
        self.assertEqual((self.box.Length.Value, self.box.Width.Value, self.box.Height.Value), (200.0, 200.0, 200.0))
        centre = self.box.Shape.BoundBox.Center
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip((centre.x, centre.y, centre.z), (50.0, 50.0, 50.0))))
        self.assertEqual(s.ui.gesture_text, "Scale: 200 %")
        self.hand(0, (230.0, 50.0, 96.0), trigger=1.0, button1=False)        # 180 mm apart: free, 180 per cent
        self.assertAlmostEqual(self.box.Length.Value, 180.0, places=6)
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0, button1=True)          # A held: the sizes go to the grid
        self.hand(0, (221.0, 50.0, 96.0), trigger=1.0)
        self.assertEqual(self.box.Length.Value, 170.0)
        self.hand(0, (250.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (50.0, 50.0, 96.0), trigger=0.0)
        self.hand(0, (250.0, 50.0, 96.0), trigger=0.0)
        self.assertEqual([t.text for t in s.ui.toasts.items][-1], "Scaled " + self.box.Label)
        self.doc.undo()
        self.assertEqual((self.box.Length.Value, tuple(self.box.Placement.Base)), (100.0, (0.0, 0.0, 0.0)))

    def test_an_object_that_cannot_be_scaled_is_only_moved(self):
        plain = self.doc.addObject("Part::Feature", "Plain")
        plain.Shape = self.box.Shape.copy()
        plain.Placement = self.App.Placement(self.App.Vector(300.0, 0.0, 0.0), self.App.Rotation())
        self.doc.recompute()
        self.box.Visibility = False
        s = self.session()
        before = plain.Shape.BoundBox.XLength
        self.hand(1, (350.0, 50.0, 96.0))
        self.hand(1, (350.0, 50.0, 96.0), trigger=1.0)
        self.hand(0, (450.0, 50.0, 96.0), trigger=1.0)
        self.hand(0, (550.0, 50.0, 96.0), trigger=1.0)
        self.assertEqual(plain.Shape.BoundBox.XLength, before)
        self.hand(1, (350.0, 50.0, 96.0), trigger=0.0)

    def test_deleting_removes_whole_objects_in_one_undo_step_and_leaves_selected_elements_alone(self):
        from freecad.BlocksCAD.cad import edit
        name, label = self.box.Name, self.box.Label
        self.assertEqual(edit.delete_objects(self.doc, [(name, "Face1")]), "Select a whole object to delete")
        self.assertIsNotNone(self.doc.getObject(name))
        self.assertEqual(edit.delete_objects(self.doc, [(name, "")]), "Deleted " + label)
        self.assertIsNone(self.doc.getObject(name))
        self.doc.undo()
        self.assertIsNotNone(self.doc.getObject(name))                                        # one undo step brings it back

    def second_shape(self, shape="Cylinder", lo=(50.0, 50.0, 0.0), size=(100.0, 100.0, 100.0)):
        from freecad.BlocksCAD.cad import primitives as prim
        return prim.create(self.doc, shape, lo, size)

    def test_a_fuse_is_one_undo_step_keeps_its_sources_and_follows_them(self):
        from freecad.BlocksCAD.cad import combine
        other = self.second_shape()
        text, name = combine.combine(self.doc, "fuse", [(self.box.Name, ""), (other.Name, "")])
        self.assertEqual(text, "Fuse: 2 objects")
        fused = self.doc.getObject(name)
        self.assertEqual(fused.TypeId, "Part::MultiFuse")
        self.assertEqual(list(fused.Shapes), [self.box, other])
        self.assertGreater(fused.Shape.Volume, self.box.Shape.Volume)
        before = fused.Shape.Volume
        self.box.Length = 300.0                                                              # the result follows its source
        self.doc.recompute()
        self.assertGreater(fused.Shape.Volume, before)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(name))
        self.assertIsNotNone(self.doc.getObject(self.box.Name))

    def test_a_cut_takes_every_later_object_from_the_first(self):
        from freecad.BlocksCAD.cad import combine
        other = self.second_shape("Box", (50.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        third = self.second_shape("Box", (0.0, 50.0, 0.0), (50.0, 50.0, 100.0))
        text, name = combine.combine(self.doc, "cut", [(self.box.Name, ""), (other.Name, "")])
        cut = self.doc.getObject(name)
        self.assertEqual(cut.TypeId, "Part::Cut")
        self.assertAlmostEqual(cut.Shape.Volume, 50.0 * 100.0 * 100.0)
        text, name = combine.combine(self.doc, "cut", [(self.box.Name, ""), (other.Name, ""), (third.Name, "")])
        cut = self.doc.getObject(name)
        self.assertEqual(cut.Tool.TypeId, "Part::MultiFuse")                                 # many tools are fused first
        self.assertAlmostEqual(cut.Shape.Volume, 50.0 * 50.0 * 100.0)

    def test_a_common_keeps_what_the_objects_share_and_an_empty_one_is_refused(self):
        from freecad.BlocksCAD.cad import combine
        other = self.second_shape("Box", (50.0, 50.0, 0.0), (100.0, 100.0, 100.0))
        text, name = combine.combine(self.doc, "common", [(self.box.Name, ""), (other.Name, "")])
        self.assertAlmostEqual(self.doc.getObject(name).Shape.Volume, 50.0 * 50.0 * 100.0)
        far = self.second_shape("Box", (500.0, 500.0, 500.0), (10.0, 10.0, 10.0))
        count = len(self.doc.Objects)
        text, name = combine.combine(self.doc, "common", [(self.box.Name, ""), (far.Name, "")])
        self.assertIsNone(name)
        self.assertTrue(text.startswith("Common failed"), text)
        self.assertEqual(len(self.doc.Objects), count)                                      # nothing was left behind

    def test_a_copy_has_its_own_parameters_and_lies_beside_the_original(self):
        from freecad.BlocksCAD.cad import combine
        other = self.second_shape()
        text, names = combine.copy_objects(self.doc, [(self.box.Name, "")])
        self.assertEqual(len(names), 1)
        copy = self.doc.getObject(names[0])
        self.assertEqual(copy.TypeId, "Part::Box")
        self.assertEqual(copy.Length.Value, 100.0)
        self.assertAlmostEqual(copy.Placement.Base.x, self.box.Placement.Base.x + 110.0)
        self.box.Length = 50.0
        self.doc.recompute()
        self.assertEqual(copy.Length.Value, 100.0)                                           # independent of the original
        text, name = combine.combine(self.doc, "fuse", [(self.box.Name, ""), (other.Name, "")])
        text, names = combine.copy_objects(self.doc, [(name, "")])                           # a boolean copies with its sources
        copied = self.doc.getObject(names[0])
        self.assertEqual(copied.TypeId, "Part::MultiFuse")
        self.assertAlmostEqual(copied.Shape.BoundBox.XMin, self.doc.getObject(name).Shape.BoundBox.XMax + 10.0, places=3)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(names[0]))

    def test_variables_live_in_a_sheet_and_everything_bound_to_one_follows_it(self):
        from freecad.BlocksCAD.cad import values as object_values, variables
        from freecad.BlocksCAD.core import values as editing
        self.assertEqual(variables.list_variables(self.doc), [])
        target = object_values.ObjectValues(self.doc, self.box)
        editor = editing.ValueEditor(target, step=10.0)
        editor.select(0)                                                                     # Length
        editor.key("makevar")
        self.assertEqual(editor.message, "Variable length = 100 mm")
        self.assertEqual(variables.list_variables(self.doc), [("length", 100.0)])
        self.assertEqual(self.box.ExpressionEngine, [("Length", "Variables.length")])
        editor.select(1)                                                                     # Width = length * 2 + 10 mm
        editor.entry = "length * 2 + 10 mm"
        editor.key("enter")
        self.assertEqual(editor.message, "Width = (length * 2) + 10 mm")
        self.assertAlmostEqual(self.box.Width.Value, 210.0)
        editor.select(0)
        self.assertTrue(editor.nudge(1))                                                     # the stick edits the variable
        editor.commit()
        self.assertEqual(variables.list_variables(self.doc), [("length", 110.0)])
        self.assertAlmostEqual(self.box.Length.Value, 110.0)
        self.assertAlmostEqual(self.box.Width.Value, 230.0)                                  # the bound expression followed
        editor.select(1)
        self.assertFalse(editor.nudge(1))                                                    # a compound expression is not edited by number
        self.assertTrue(editor.message.startswith("Bound to"), editor.message)
        editor.key("unbind")
        self.assertEqual([e[0] for e in self.box.ExpressionEngine], ["Length"])
        self.assertAlmostEqual(self.box.Width.Value, 230.0)                                  # it keeps its number
        self.assertTrue(editor.nudge(1))
        self.assertAlmostEqual(self.box.Width.Value, 240.0)
        editor.commit()
        self.doc.undo()
        self.assertAlmostEqual(self.box.Width.Value, 230.0)
        for _ in range(4):                                                                   # unbind, the stick, the width, the variable
            self.doc.undo()
        self.assertEqual(variables.list_variables(self.doc), [])                             # the sheet went with its first binding
        self.assertEqual(self.box.ExpressionEngine, [])

    def test_a_position_can_be_bound_and_a_variable_the_shape_cannot_take_is_refused(self):
        from freecad.BlocksCAD.cad import values as object_values, variables
        from freecad.BlocksCAD.core import values as editing
        editor = editing.ValueEditor(object_values.ObjectValues(self.doc, self.box), step=10.0)
        editor.select(3)                                                                     # X
        editor.entry = "40"
        editor.key("makevar")
        self.assertEqual(variables.list_variables(self.doc), [("position_x", 40.0)])
        self.assertAlmostEqual(self.box.Placement.Base.x, 40.0)
        self.assertEqual(editor.field.expression, "Variables.position_x")
        editor.select(0)
        editor.entry = "0"
        editor.key("makevar")                                                                # a length of zero is not allowed
        self.assertEqual(editor.message, "Length cannot be that small")
        self.assertEqual([n for n, _ in variables.list_variables(self.doc)], ["position_x"])
        editor.entry = "length"
        editor.key("enter")                                                                  # no such variable
        self.assertEqual(editor.message, "Unknown variable 'length'")
        variables.set_value(self.doc, "position_x", 70.0)
        self.doc.recompute()
        self.assertAlmostEqual(self.box.Placement.Base.x, 70.0)

    def test_a_block_is_a_solid_of_points_in_one_undo_step_and_moving_a_point_rebuilds_it(self):
        from freecad.BlocksCAD.cad import block, blockgeom
        made = block.create(self.doc, (200.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        self.assertTrue(block.is_block(made))
        self.assertFalse(block.is_block(self.box))
        self.assertEqual(len(made.Shape.Faces), 6)
        self.assertAlmostEqual(made.Shape.Volume, 1.0e6)
        vertices, faces = block.read(made)
        self.assertIsNone(block.apply(self.doc, made, blockgeom.move_vertex(vertices, 6, (300.0, 100.0, 150.0))))
        self.assertAlmostEqual(made.Shape.BoundBox.ZMax, 150.0)
        self.assertGreater(made.Shape.Volume, 1.0e6)
        self.assertEqual(len(made.Shape.Faces), 7)                                           # the bent top is two triangles
        self.assertTrue(made.Shape.isValid())
        self.doc.undo()
        self.doc.undo()
        self.assertNotIn(made.Name, [o.Name for o in self.doc.Objects])

    def test_a_block_that_cannot_be_built_is_refused_and_stays_as_it_was(self):
        from freecad.BlocksCAD.cad import block, blockgeom
        made = block.create(self.doc, (0.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        vertices, faces = block.read(made)
        flat = [(x, y, 0.0) for x, y, _ in vertices]
        self.assertIn(block.apply(self.doc, made, flat), ("The block has no volume", "A face has no area"))
        self.assertEqual(block.read(made)[0], vertices)
        self.assertTrue(made.isValid())
        with self.assertRaises(ValueError):
            block.make_shape(vertices, faces[:4])

    def test_a_block_splits_an_edge_and_the_new_point_moves(self):
        from freecad.BlocksCAD.cad import block, blockgeom
        made = block.create(self.doc, (0.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        vertices, faces = block.read(made)
        vertices, faces, index = blockgeom.split_edge(vertices, faces, 0, 1, (50.0, 0.0, 0.0))
        self.assertIsNone(block.apply(self.doc, made, vertices, faces))
        self.assertEqual(len(made.Vertices), 9)
        self.assertAlmostEqual(made.Shape.Volume, 1.0e6)
        self.assertIsNone(block.apply(self.doc, made, blockgeom.move_vertex(vertices, index, (50.0, -20.0, 0.0))))
        self.assertAlmostEqual(made.Shape.BoundBox.YMin, -20.0)
        self.assertGreater(made.Shape.Volume, 1.0e6)
        self.assertTrue(made.Shape.isValid())

    def test_the_block_is_picked_by_its_points_and_edges(self):
        from freecad.BlocksCAD.cad import block
        made = block.create(self.doc, (400.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        found = block.pick(self.doc, (498.0, 1.0, 1.0), 1000.0, "vertex")
        self.assertEqual((found.name, found.sub), (made.Name, "Point1"))
        found = block.pick(self.doc, (450.0, 1.0, 1.0), 1000.0, "edge")
        self.assertEqual((found.name, found.sub), (made.Name, "Segment0-1"))
        self.assertIsNone(block.pick(self.doc, (450.0, 50.0, 50.0), 1000.0, "vertex"))
        self.assertEqual(block.display(made, "Point1").markers, [(500.0, 0.0, 0.0)])
        self.assertEqual(len(block.handles(self.doc).markers), 16)                          # the points of the block and of the box of the document
        found = block.pick(self.doc, (98.0, 1.0, 1.0), 1000.0, "vertex")
        self.assertEqual((found.name, found.sub), (self.box.Name, "Point1"))                # a box is picked like a block

    def test_a_block_comes_back_from_a_saved_document_and_recomputes(self):
        import os
        import tempfile
        from freecad.BlocksCAD.cad import block
        made = block.create(self.doc, (0.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        name = made.Name
        path = os.path.join(tempfile.mkdtemp(), "block.FCStd")
        self.doc.saveAs(path)
        self.App.closeDocument(self.doc.Name)
        self.doc = self.App.openDocument(path)
        again = self.doc.getObject(name)
        self.assertTrue(block.is_block(again))
        self.assertAlmostEqual(again.Shape.Volume, 1.0e6)
        again.Vertices = [self.App.Vector(v.x, v.y, v.z + (50.0 if v.z > 0 else 0.0)) for v in again.Vertices]
        self.doc.recompute()
        self.assertAlmostEqual(again.Shape.Volume, 1.5e6)

    def test_a_point_pulled_through_the_block_makes_no_solid_and_is_refused(self):
        from freecad.BlocksCAD.cad import block, blockgeom
        made = block.create(self.doc, (0.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        vertices, faces = block.read(made)
        error = block.apply(self.doc, made, blockgeom.move_vertex(vertices, 6, (-60.0, -60.0, -60.0)))
        self.assertIsNotNone(error)
        self.assertEqual(block.read(made)[0], vertices)
        self.assertTrue(made.isValid())
        self.assertAlmostEqual(made.Shape.Volume, 1.0e6)

    def test_the_create_tool_makes_a_block_from_a_drag_and_the_points_tool_moves_a_point_of_it(self):
        s = self.session()
        s.select_tool("primitive")
        s.tool_manager.active.values["shape"] = "Block"
        self.hand(1, (400.0, 0.0, 0.0))
        self.hand(1, (400.0, 0.0, 0.0), trigger=1.0)
        self.hand(1, (500.0, 100.0, 100.0), trigger=1.0)
        self.hand(1, (500.0, 100.0, 100.0), trigger=0.0)
        from freecad.BlocksCAD.cad import block
        made = [o for o in self.doc.Objects if block.is_block(o)]
        self.assertEqual(len(made), 1)
        made = made[0]
        self.assertAlmostEqual(made.Shape.Volume, 1.0e6)
        s.select_tool("points")
        self.hand(1, (500.0, 100.0, 100.0))
        self.hand(1, (500.0, 100.0, 100.0), trigger=1.0)
        self.hand(1, (520.0, 100.0, 140.0), trigger=1.0)
        self.assertTrue(s.ui.gesture_text.startswith("Point 6: "), s.ui.gesture_text)
        self.hand(1, (520.0, 100.0, 140.0), trigger=0.0)
        self.assertEqual(tuple(round(c, 6) for c in block.read(made)[0][6]), (520.0, 100.0, 140.0))
        self.assertGreater(made.Shape.Volume, 1.0e6)
        self.assertEqual(self.selection(), [(made.Name, ())])
        self.doc.undo()
        self.assertEqual(tuple(round(c, 6) for c in block.read(made)[0][6]), (500.0, 100.0, 100.0))
        self.assertAlmostEqual(made.Shape.Volume, 1.0e6)

    def test_the_points_tool_turns_a_box_into_a_block_as_the_press_starts_and_one_undo_step_takes_both_back(self):
        from freecad.BlocksCAD.cad import block
        import FreeCAD as App
        placement = App.Placement(App.Vector(300.0, 40.0, 50.0), App.Rotation(App.Vector(0, 0, 1), 30.0))
        self.box.Placement = placement
        self.box.Label = "My box"
        self.doc.recompute()
        volume = self.box.Shape.Volume
        self.assertEqual([o.Name for o in block.blocks(self.doc)], [self.box.Name])                # the box is marked like a block
        s = self.session()
        s.select_tool("points")
        corner = block.to_world(self.box, (100.0, 100.0, 100.0))
        self.hand(1, corner)
        self.hand(1, corner, trigger=1.0)
        moved = tuple(c + d for c, d in zip(corner, (0.0, 0.0, 40.0)))
        self.hand(1, moved, trigger=1.0)
        self.hand(1, moved, trigger=0.0)
        made = [o for o in self.doc.Objects if block.is_block(o)]
        self.assertEqual(len(made), 1)
        self.assertEqual([o.TypeId for o in self.doc.Objects if o.TypeId == "Part::Box"], [])
        self.assertEqual(made[0].Label, "My box")
        self.assertTrue(made[0].Placement.isSame(placement, 1e-9))
        self.assertGreater(made[0].Shape.Volume, volume)
        self.doc.undo()                                                                              # the move and the conversion are one step
        self.assertEqual([o.TypeId for o in self.doc.Objects], ["Part::Box"])
        self.assertAlmostEqual(self.doc.Objects[0].Shape.Volume, volume)

    def test_a_box_that_another_object_uses_or_that_has_expressions_is_not_editable(self):
        from freecad.BlocksCAD.cad import block, primitives as prim
        other = prim.create(self.doc, "Box", (500.0, 0.0, 0.0), (50.0, 50.0, 50.0))
        self.assertTrue(block.editable_box(self.box))
        self.box.setExpression("Length", "100 mm")
        self.assertFalse(block.editable_box(self.box))
        self.box.setExpression("Length", None)
        fused = self.doc.addObject("Part::MultiFuse", "Fuse")
        fused.Shapes = [self.box, other]
        self.doc.recompute()
        self.assertFalse(block.editable_box(self.box))
        self.assertFalse(block.editable_box(fused))

    def test_a_block_can_be_attached_to_a_face_and_follows_it(self):
        from freecad.BlocksCAD.cad import attach, block
        import FreeCAD as App
        small = block.create(self.doc, (500.0, 0.0, 0.0), (40.0, 40.0, 40.0))
        face = lambda o, z: next(f"Face{i + 1}" for i, f in enumerate(o.Shape.Faces)
                                 if abs(f.CenterOfMass.z - z) < 1e-6 and abs(f.normalAt(0, 0).z) > 0.9)
        text, name = attach.attach(self.doc, [(small.Name, face(small, 0.0)), (self.box.Name, face(self.box, 100.0))])
        self.assertEqual(name, small.Name, text)
        self.assertAlmostEqual(small.Shape.BoundBox.ZMin, 100.0)
        self.assertAlmostEqual(small.Shape.BoundBox.Center.x, 50.0)
        self.box.Placement = App.Placement(App.Vector(30.0, 0.0, 0.0), App.Rotation())
        self.doc.recompute()
        self.assertAlmostEqual(small.Shape.BoundBox.Center.x, 80.0)                           # the block follows its support
        attach.detach(self.doc, [(small.Name, "")])
        self.box.Placement = App.Placement()
        self.doc.recompute()
        self.assertAlmostEqual(small.Shape.BoundBox.Center.x, 80.0)                           # and stays where it was

    def test_the_points_tool_splits_an_edge_and_drags_the_new_point_in_one_undo_step(self):
        from freecad.BlocksCAD.cad import block
        made = block.create(self.doc, (400.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        s = self.session()
        s.select_tool("points")
        s.tool_manager.active.values["mode"] = "Split"
        self.hand(1, (450.0, 1.0, 1.0))
        self.hand(1, (450.0, 1.0, 1.0), trigger=1.0)
        self.hand(1, (450.0, -30.0, 0.0), trigger=1.0)
        self.hand(1, (450.0, -30.0, 0.0), trigger=0.0)
        vertices, faces = block.read(made)
        self.assertEqual(len(vertices), 9)
        self.assertEqual(tuple(round(c, 6) for c in vertices[8]), (450.0, -30.0, 0.0))
        self.assertTrue(made.Shape.isValid())
        self.doc.undo()
        self.assertEqual(len(made.Vertices), 8)
        self.assertEqual(len(made.Shape.Faces), 6)

    def test_with_flat_faces_a_dragged_corner_stays_in_its_planes_and_the_block_keeps_its_faces(self):
        from freecad.BlocksCAD.cad import block
        made = block.create(self.doc, (400.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        s = self.session()
        s.select_tool("points")
        s.tool_manager.active.values["faces"] = "Flat"
        s.tool_manager.active.values["mode"] = "Split"
        self.hand(1, (450.0, 1.0, 1.0))
        self.hand(1, (450.0, 1.0, 1.0), trigger=1.0)
        self.hand(1, (480.0, -30.0, 40.0), trigger=1.0)                                       # off the edge in every direction
        self.assertTrue(s.ui.gesture_text.endswith("(flat)"), s.ui.gesture_text)
        self.hand(1, (480.0, -30.0, 40.0), trigger=0.0)
        vertices, faces = block.read(made)
        self.assertEqual(tuple(round(c, 6) for c in vertices[8]), (480.0, 0.0, 0.0))          # it slid along the edge
        self.assertEqual(len(made.Shape.Faces), 6)                                           # no face was cut into triangles
        self.assertAlmostEqual(made.Shape.Volume, 1.0e6)

    def test_the_coordinates_of_a_picked_point_are_values_that_can_be_bound_to_a_variable(self):
        from freecad.BlocksCAD.cad import block, values as object_values, variables
        from freecad.BlocksCAD.core import values as editing
        made = block.create(self.doc, (0.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        key, factory = object_values.source(self.doc, lambda doc: [(made.Name, "")])
        self.assertEqual(key, (self.doc.Name, made.Name))                                      # no point picked: the position only
        block.set_picked(made, 6)
        key, factory = object_values.source(self.doc, lambda doc: [(made.Name, "")])
        self.assertEqual(key, (self.doc.Name, made.Name, 6))
        editor = editing.ValueEditor(factory(), step=10.0)
        self.assertEqual([f.label for f in editor.fields][:4], ["Point X", "Point Y", "Point Z", "X"])
        self.assertEqual(editor.target.title, made.Label + " point 6")
        editor.select(2)
        editor.entry = "130"
        editor.key("enter")                                                                    # a plain number moves the point
        self.assertAlmostEqual(made.Shape.BoundBox.ZMax, 130.0)
        self.assertEqual([f.value for f in editor.fields][:3], [100.0, 100.0, 130.0])
        editor.key("makevar")
        self.assertEqual(editor.message, "Variable point_z = 130 mm")
        self.assertIn("Point6", made.PropertiesList)
        self.assertEqual(variables.list_variables(self.doc), [("point_z", 130.0)])
        self.assertTrue(editor.nudge(1))                                                       # the stick edits the variable
        editor.commit()
        self.assertAlmostEqual(made.Shape.BoundBox.ZMax, 140.0)
        variables.set_value(self.doc, "point_z", 160.0)
        self.doc.recompute()
        self.assertAlmostEqual(made.Shape.BoundBox.ZMax, 160.0)
        self.assertEqual(block.read(made)[0][6], (100.0, 100.0, 160.0))
        vertices, _ = block.read(made)
        error = block.apply(self.doc, made, [(x, y, 170.0) if i == 6 else (x, y, z) for i, (x, y, z) in enumerate(vertices)])
        self.assertEqual(error, "Point 6 is bound to point_z: unbind it first")
        editor.select(0)
        editor.entry = "point_z / 2"
        editor.key("enter")                                                                    # another value follows the same variable
        self.assertAlmostEqual(block.read(made)[0][6][0], 80.0)
        editor.select(2)
        editor.key("unbind")
        vertices, _ = block.read(made)
        self.assertIsNone(block.apply(self.doc, made, [(x, y, 170.0) if i == 6 else (x, y, z) for i, (x, y, z) in enumerate(vertices)]))
        self.assertAlmostEqual(made.Shape.BoundBox.ZMax, 170.0)
        for _ in range(7):
            self.doc.undo()
        self.assertNotIn("Point6", made.PropertiesList)                                       # the property went with its first binding
        self.assertEqual(variables.list_variables(self.doc), [])

    def test_the_points_tool_shows_the_point_it_moved_on_the_value_panels(self):
        from freecad.BlocksCAD.cad import block
        made = block.create(self.doc, (400.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        s = self.session()
        s.select_tool("points")
        self.hand(1, (500.0, 100.0, 100.0))
        self.hand(1, (500.0, 100.0, 100.0), trigger=1.0)
        self.hand(1, (500.0, 100.0, 100.0), trigger=0.0)
        for _ in range(3):
            s.frame(0.02)
        self.assertTrue(s.ui.module.is_open)
        self.assertEqual(s.ui.module.editor.target.title, made.Label + " point 6")
        self.assertEqual(s.ui.module.readouts()["val.readout"], ("Point X", "500 mm", False))

    def sketch_on(self, plane="XY", point=(0.0, 0.0, 0.0)):
        from freecad.BlocksCAD.cad import sketching
        self.doc.openTransaction("sketch")
        sketch = sketching.create_on_plane(self.doc, plane, point, 10.0)
        self.doc.recompute()
        return sketch

    def test_a_sketch_lies_on_a_plane_at_the_height_of_the_cursor_and_maps_points_both_ways(self):
        from freecad.BlocksCAD.cad import sketching
        for plane, point, height_axis in (("XY", (5.0, 6.0, 33.0), 2), ("XZ", (5.0, 44.0, 7.0), 1), ("YZ", (52.0, 6.0, 7.0), 0)):
            sketch = self.sketch_on(plane, point)
            world = sketching.to_world(sketch, (10.0, 20.0, 0.0))
            normal = sketching.plane_normal(plane)
            self.assertAlmostEqual(abs(sum(w * n for w, n in zip(world, normal))), round(abs(point[height_axis]) / 10.0) * 10.0, places=6)
            back = sketching.to_local(sketch, world)
            self.assertAlmostEqual(back[0], 10.0)
            self.assertAlmostEqual(back[1], 20.0)
            self.assertAlmostEqual(back[2], 0.0)
        xz = self.sketch_on("XZ", (0.0, 0.0, 0.0))
        self.assertEqual(tuple(round(c, 6) for c in sketching.to_world(xz, (10.0, 20.0, 0.0))), (10.0, 0.0, 20.0))   # x to X, y to Z

    def test_frames_of_planes_and_sketches_agree_and_name_the_axes_of_the_document(self):
        from freecad.BlocksCAD.cad import sketching
        for plane, axes in (("XY", (0, 1)), ("XZ", (0, 2)), ("YZ", (1, 2))):
            frame = sketching.plane_frame(plane, (5.0, 44.0, 7.0), 10.0)
            sketch = self.sketch_on(plane, (5.0, 44.0, 7.0))
            self.assertEqual(sketching.world_axes(frame), axes)
            world = sketching.frame_to_world(frame, (10.0, 20.0, 0.0))
            self.assertEqual(tuple(round(c, 6) for c in sketching.to_world(sketch, (10.0, 20.0, 0.0))), tuple(round(c, 6) for c in world))
            self.assertEqual(tuple(round(c, 6) for c in sketching.frame_to_local(frame, world)), (10.0, 20.0, 0.0))
        tilted = (((0.0, 0.0, 0.0)), (0.0, 0.3826834, 0.0, 0.9238795))                      # 45 degrees about Y
        self.assertEqual(sketching.world_axes(tilted), (3, 1))

    def test_an_arc_passes_through_its_three_points_is_tied_at_its_ends_and_can_be_picked_and_dimensioned(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        sketching.add_rectangle(self.doc, sketch, (0.0, 0.0), (60.0, 40.0))
        geo, kept = sketching.add_arc(self.doc, sketch, (0.0, 40.0), (60.0, 40.0), (30.0, 70.0))      # over the top side
        self.doc.recompute()
        self.assertEqual(kept, 2)                                                                  # both ends coincide with corners
        self.assertEqual(sketch.Geometry[geo].TypeId, "Part::GeomArcOfCircle")
        arc = sketch.Geometry[geo]
        self.assertAlmostEqual(arc.Radius, 30.0, places=6)                                         # chord 60, rise 30: a half circle
        ends = sorted((round(p.x, 6), round(p.y, 6)) for p in (arc.StartPoint, arc.EndPoint))
        self.assertEqual(ends, [(0.0, 40.0), (60.0, 40.0)])
        top = arc.value(arc.FirstParameter + (arc.LastParameter - arc.FirstParameter) / 2.0)
        self.assertAlmostEqual(top.y, 70.0, places=6)                                              # the middle of the arc is the third point
        self.assertTrue(sketching.solved(sketch))
        found = sketching.pick(self.doc, sketching.to_world(sketch, (30.0, 70.0, 0.0)), 1000.0, "edge")
        self.assertEqual((found.name, found.sub), (sketch.Name, f"Curve{geo}"))
        shown = sketching.display(sketch, f"Curve{geo}")
        self.assertEqual(len(shown.polylines), 1)
        text, name = sketching.dimension(self.doc, sketch, geo)
        self.assertEqual(name, "radius")
        self.assertIn("radius =", text)
        with self.assertRaises(ValueError):
            sketching.add_arc(self.doc, sketch, (0.0, 0.0), (60.0, 0.0), (30.0, 0.0))

    def kinds(self, sketch):
        return [c.Type for c in sketch.Constraints]

    def test_a_line_and_an_arc_that_run_along_each_other_are_tangent_and_the_solver_keeps_them_so(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        geo, kept = sketching.add_arc(self.doc, sketch, (0.0, 30.0), (60.0, 30.0), (30.0, 60.0))     # a half circle over the top
        self.doc.recompute()
        down, kept = sketching.add_line(self.doc, sketch, (0.0, 30.0), (0.0, 10.0))                   # leaves its left end straight down
        self.doc.recompute()
        self.assertIn("Tangent", self.kinds(sketch))
        self.assertTrue(sketching.solved(sketch))
        self.assertIsNone(sketching.move_point(self.doc, sketch, down, 2, (0.0, 0.0)))
        self.assertTrue(sketching.solved(sketch))
        tail, kept = sketching.add_arc(self.doc, sketch, (0.0, 10.0), (-20.0, 10.0), (-10.0, 20.0))  # across the end of the line: only joined
        self.assertNotEqual(kept, 0)
        self.assertTrue(sketching.solved(sketch))

    def test_a_line_that_continues_an_arc_or_runs_beside_a_slanted_line_gets_the_relation_and_stays_solvable(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        sketching.add_line(self.doc, sketch, (0.0, 5.0), (40.0, 25.0))
        sketching.add_line(self.doc, sketch, (10.0, 50.0), (50.0, 70.0))                              # parallel
        sketching.add_line(self.doc, sketch, (10.0, 50.0), (30.0, 10.0))                              # across the slanted line
        self.doc.recompute()
        kinds = self.kinds(sketch)
        self.assertIn("Parallel", kinds)
        self.assertIn("Perpendicular", kinds)
        self.assertTrue(sketching.solved(sketch))

    def test_a_line_drawn_to_the_end_that_the_direction_guide_gives_is_parallel_by_constraint(self):
        from freecad.BlocksCAD.cad import sketching
        from freecad.BlocksCAD.core import guides
        sketch = self.sketch_on()
        sketching.add_line(self.doc, sketch, (0.0, 5.0), (40.0, 25.0))
        slanted = sketching.slanted_lines(sketch)
        self.assertEqual(slanted, [((0.0, 5.0), (40.0, 25.0))])
        end, relation = guides.align_direction((10.0, 50.0), (49.0, 71.0), slanted, 5.0)
        self.assertEqual(relation[0], "Parallel")
        sketching.add_line(self.doc, sketch, (10.0, 50.0), end)
        self.doc.recompute()
        self.assertIn("Parallel", self.kinds(sketch))
        self.assertTrue(sketching.solved(sketch))
        sketching.add_rectangle(self.doc, sketch, (100.0, 100.0), (150.0, 130.0))
        self.assertEqual(len(sketching.slanted_lines(sketch)), 2)                                  # the sides of a rectangle are not slanted

    def test_a_line_as_long_as_another_is_equal_to_it_by_constraint_and_follows_when_that_one_changes(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        sketching.add_rectangle(self.doc, sketch, (0.0, 0.0), (60.0, 40.0))                     # the bottom side is 60 mm
        geo, kept = sketching.add_line(self.doc, sketch, (100.0, 100.0), (160.0, 100.0))
        self.doc.recompute()
        self.assertIn("Equal", self.kinds(sketch))
        self.assertTrue(sketching.solved(sketch))
        text, name = sketching.dimension(self.doc, sketch, 0)                                    # the length of the bottom side
        self.assertEqual(name, "length")
        index = [i for i, c in enumerate(sketch.Constraints) if c.Name == "length"][0]
        self.assertIsNone(sketching.set_dimension(sketch, index, 80.0))
        self.doc.recompute()
        line = sketch.Geometry[geo]
        self.assertAlmostEqual((line.EndPoint - line.StartPoint).Length, 80.0, places=5)          # the equal line followed

    def test_the_own_points_of_a_sketch_leave_out_the_dragged_point_and_those_that_move_with_it(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        first, _ = sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (60.0, 40.0))
        points = sketching.own_points(sketch)
        self.assertEqual(len(points), 8)                                                     # a corner is the end of two lines
        apart = sketching.own_points(sketch, (first, 1))
        self.assertEqual(len(apart), 6)
        self.assertNotIn((10.0, 10.0, 0.0), [tuple(round(c, 6) for c in p) for p in apart])

    def test_a_rectangle_is_four_joined_horizontal_and_vertical_lines_with_free_size_and_position(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        first, kept = sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (60.0, 40.0))
        self.doc.recompute()
        self.assertEqual((first, kept), (0, 8))
        self.assertEqual(len(sketch.Geometry), 4)
        self.assertEqual(sketch.DoF, 4)                                                      # position and size are still free
        self.assertTrue(sketch.Shape.Wires[0].isClosed())
        box = sketch.Shape.BoundBox
        self.assertEqual((box.XMin, box.YMin, box.XMax, box.YMax), (10.0, 10.0, 60.0, 40.0))

    def test_shapes_are_tied_to_the_origin_the_axes_and_to_each_other(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        first, kept = sketching.add_rectangle(self.doc, sketch, (0.0, 0.0), (60.0, 40.0))
        self.assertEqual(kept, 9)                                                            # 8 and the corner on the origin
        self.assertEqual(sketch.DoF, 2)
        geo, kept = sketching.add_line(self.doc, sketch, (60.0, 40.0), (90.0, 70.0))         # starts at a corner of the rectangle
        self.assertEqual(kept, 1)
        self.assertEqual(sketch.DoF, 4)
        geo, kept = sketching.add_line(self.doc, sketch, (90.0, 70.0), (90.0, 20.0))         # vertical and joined to the last end
        self.assertEqual(kept, 2)
        geo, kept = sketching.add_circle(self.doc, sketch, (30.0, 20.0), 10.0)
        self.assertEqual(kept, 0)
        self.assertTrue(sketching.solved(sketch))
        self.doc.recompute()
        self.assertTrue(sketch.isValid())

    def test_a_constraint_the_solver_refuses_is_left_out_and_the_shape_stays(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        sketching.add_rectangle(self.doc, sketch, (0.0, 0.0), (60.0, 40.0))
        geo, kept = sketching.add_line(self.doc, sketch, (0.0, 0.0), (60.0, 0.0))            # on top of the lower side: redundant ties
        self.assertTrue(sketching.solved(sketch))
        self.assertEqual(len(sketch.Geometry), 5)

    def test_dragging_a_point_keeps_the_constraints_and_a_dimension_fixes_a_length(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        first, _ = sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (60.0, 40.0))
        self.assertIsNone(sketching.move_point(self.doc, sketch, first + 1, 2, (80.0, 55.0)))       # the far corner
        self.doc.recompute()
        box = sketch.Shape.BoundBox
        self.assertEqual((box.XMin, box.YMin, box.XMax, box.YMax), (10.0, 10.0, 80.0, 55.0))     # still a rectangle
        text, name = sketching.dimension(self.doc, sketch, first)                             # the lower side
        self.assertEqual((text, name), ("Dimension length = 70 mm", "length"))
        self.assertEqual(sketching.dimension(self.doc, sketch, first), ("That is dimensioned already", None))
        index = sketching.dimensions(sketch)[0][0]
        self.assertIsNone(sketching.set_dimension(sketch, index, 90.0))
        self.doc.recompute()
        self.assertAlmostEqual(sketch.Shape.BoundBox.XMax - sketch.Shape.BoundBox.XMin, 90.0)
        sketching.move_point(self.doc, sketch, first + 1, 2, (200.0, 55.0))                  # the dimension holds the width
        self.assertAlmostEqual(sketch.Shape.BoundBox.XMax - sketch.Shape.BoundBox.XMin, 90.0, places=4)

    def test_a_circle_gets_a_radius_and_a_value_the_solver_cannot_take_is_refused(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        geo, _ = sketching.add_circle(self.doc, sketch, (30.0, 30.0), 10.0)
        self.assertEqual(sketching.dimension(self.doc, sketch, geo), ("Dimension radius = 10 mm", "radius"))
        index = sketching.dimensions(sketch)[0][0]
        self.assertEqual(sketching.dimensions(sketch)[0][1:], ("radius", "Radius", 10.0))
        self.assertIsNone(sketching.set_dimension(sketch, index, 25.0))
        self.assertIsNotNone(sketching.set_dimension(sketch, index, -5.0))
        self.assertAlmostEqual(sketching.dimensions(sketch)[0][3], 25.0)

    def test_a_sketch_attached_to_a_face_follows_the_face(self):
        from freecad.BlocksCAD.cad import sketching
        self.doc.openTransaction("sketch")
        sketch = sketching.create_on_face(self.doc, self.box, "Face6")
        self.assertAlmostEqual(sketching.to_world(sketch, (5.0, 5.0, 0.0))[2], 100.0)
        sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (50.0, 30.0))
        self.doc.recompute()
        self.box.Height = 140.0
        self.doc.recompute()
        self.assertAlmostEqual(sketch.Shape.BoundBox.ZMax, 140.0)
        self.assertEqual(sketching.current_sketch(self.doc, [(self.box.Name, ""), (sketch.Name, "")]), sketch)
        self.assertIsNone(sketching.current_sketch(self.doc, [(self.box.Name, "")]))

    def test_a_sketch_is_extruded_into_a_solid_that_follows_it_and_an_open_sketch_is_refused(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on()
        sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (60.0, 40.0))
        self.doc.commitTransaction()
        text, names = sketching.extrude(self.doc, [(sketch.Name, "")], 20.0)
        self.assertEqual(text, "Extruded " + sketch.Label)
        solid = self.doc.getObject(names[0])
        self.assertAlmostEqual(solid.Shape.Volume, 50.0 * 30.0 * 20.0)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(names[0]))
        open_sketch = self.sketch_on("XZ", (0.0, 0.0, 0.0))
        sketching.add_line(self.doc, open_sketch, (0.0, 0.0), (50.0, 0.0))
        count = len(self.doc.Objects)
        text, names = sketching.extrude(self.doc, [(open_sketch.Name, "")], 20.0)
        self.assertTrue(text.startswith("Extrude failed"), text)
        self.assertEqual((names, len(self.doc.Objects)), ([], count))
        self.assertEqual(sketching.extrude(self.doc, [(self.box.Name, "")], 20.0), ("Select a sketch to extrude", []))

    def test_the_points_and_curves_of_a_sketch_are_picked_and_drawn(self):
        from freecad.BlocksCAD.cad import sketching
        sketch = self.sketch_on("XY", (0.0, 0.0, 0.0))
        sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (60.0, 40.0))
        sketching.add_circle(self.doc, sketch, (30.0, 25.0), 5.0)
        found = sketching.pick(self.doc, (11.0, 9.0, 1.0), 1000.0, "vertex")
        self.assertEqual((found.name, found.sub), (sketch.Name, "Point0.1"))
        self.assertIsNone(sketching.pick(self.doc, (45.0, 25.0, 0.0), 1000.0, "vertex"))
        found = sketching.pick(self.doc, (35.0, 12.0, 0.0), 1000.0, "edge")
        self.assertEqual(found.sub, "Curve0")
        found = sketching.pick(self.doc, (35.0, 25.0, 3.0), 1000.0, "edge")                    # the circle of radius 5 at 30, 25
        self.assertEqual(found.sub, "Curve4")
        self.assertEqual(len(sketching.handles(self.doc).markers), 9)
        self.assertEqual(sketching.display(sketch, "Point0.1").markers, [(10.0, 10.0, 0.0)])
        self.assertEqual(len(sketching.display(sketch, "Curve4").polylines[0]), sketching.CIRCLE_POINTS + 1)

    def test_the_dimensions_of_a_sketch_are_values_that_can_be_set_and_bound_to_a_variable(self):
        from freecad.BlocksCAD.cad import sketching, values as object_values, variables
        from freecad.BlocksCAD.core import values as editing
        sketch = self.sketch_on()
        first, _ = sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (60.0, 40.0))
        sketching.dimension(self.doc, sketch, first)
        sketching.dimension(self.doc, sketch, first + 1)
        key, factory = object_values.source(self.doc, lambda doc: [(sketch.Name, "")])
        self.assertEqual(key, (self.doc.Name, sketch.Name))
        editor = editing.ValueEditor(factory(), step=10.0)
        self.assertEqual([(f.label, f.value) for f in editor.fields][:3], [("length", 50.0), ("length2", 30.0), ("X", 0.0)])
        editor.select(0)
        self.assertTrue(editor.nudge(1))                                                      # the stick: 50 to 60
        editor.commit()
        self.assertAlmostEqual(sketch.Shape.BoundBox.XMax - sketch.Shape.BoundBox.XMin, 60.0)
        editor.key("makevar")
        self.assertEqual(editor.message, "Variable length = 60 mm")
        variables.set_value(self.doc, "length", 85.0)
        self.doc.recompute()
        self.assertAlmostEqual(sketch.Shape.BoundBox.XMax - sketch.Shape.BoundBox.XMin, 85.0)
        editor.select(1)
        editor.entry = "length / 2"
        editor.key("enter")
        self.assertAlmostEqual(sketch.Shape.BoundBox.YMax - sketch.Shape.BoundBox.YMin, 42.5)
        editor.select(0)
        editor.entry = "0"
        editor.key("enter")                                                                   # a length is at least 0.1 mm, the variable takes it
        self.assertEqual(variables.list_variables(self.doc), [("length", 0.1)])

    def test_an_attached_sketch_shows_only_its_dimensions_and_an_extrusion_has_a_length_to_edit(self):
        from freecad.BlocksCAD.cad import sketching, values as object_values
        from freecad.BlocksCAD.core import values as editing
        self.doc.openTransaction("sketch")
        sketch = sketching.create_on_face(self.doc, self.box, "Face6")
        first, _ = sketching.add_rectangle(self.doc, sketch, (10.0, 10.0), (60.0, 40.0))
        sketching.dimension(self.doc, sketch, first)
        self.doc.commitTransaction()
        key, factory = object_values.source(self.doc, lambda doc: [(sketch.Name, "")])
        self.assertEqual([f.label for f in editing.ValueEditor(factory()).fields], ["length"])
        text, names = sketching.extrude(self.doc, [(sketch.Name, "")], 20.0)
        solid = self.doc.getObject(names[0])
        key, factory = object_values.source(self.doc, lambda doc: [(solid.Name, "")])
        editor = editing.ValueEditor(factory(), step=10.0)
        self.assertEqual([(f.label, f.value) for f in editor.fields][:1], [("Length", 20.0)])
        self.assertTrue(editor.nudge(1))
        editor.commit()
        self.assertAlmostEqual(solid.LengthFwd.Value, 30.0)

    def test_the_sketch_tool_draws_edits_and_dimensions_a_rectangle_in_the_sim(self):
        from freecad.BlocksCAD.cad import sketching
        s = self.session()
        s.select_tool("sketch")
        s.tool_manager.active.values["mode"] = "Rectangle"
        self.hand(1, (300.0, 0.0, 0.0))
        self.hand(1, (300.0, 0.0, 0.0), trigger=1.0)
        self.hand(1, (360.0, 40.0, 0.0), trigger=1.0)
        self.assertEqual(s.ui.gesture_text, "Rectangle: 60 mm x 40 mm")
        self.hand(1, (360.0, 40.0, 0.0), trigger=0.0)
        (sketch,) = [o for o in self.doc.Objects if sketching.is_sketch(o)]
        self.assertEqual(len(sketch.Geometry), 4)
        box = sketch.Shape.BoundBox
        self.assertEqual((box.XMin, box.YMin, box.XMax, box.YMax), (300.0, 0.0, 360.0, 40.0))
        self.assertEqual(self.selection(), [(sketch.Name, ())])
        s.tool_manager.active.values["mode"] = "Edit"
        self.hand(1, (360.0, 40.0, 0.0))                                                      # drag the far corner out
        self.hand(1, (360.0, 40.0, 0.0), trigger=1.0)
        self.hand(1, (380.0, 60.0, 0.0), trigger=1.0)
        self.hand(1, (380.0, 60.0, 0.0), trigger=0.0)
        box = sketch.Shape.BoundBox
        self.assertEqual((box.XMin, box.YMin, box.XMax, box.YMax), (300.0, 0.0, 380.0, 60.0))
        self.hand(1, (340.0, 0.0, 0.0))                                                       # press on the lower side: it is dimensioned
        for _ in range(12):
            s.frame(0.02)
        self.hand(1, (340.0, 0.0, 0.0), trigger=1.0)
        self.hand(1, (340.0, 0.0, 0.0), trigger=0.0)
        self.assertEqual([d[1:] for d in sketching.dimensions(sketch)], [("length", "Distance", 80.0)])
        self.assertEqual([t.text for t in s.ui.toasts.items][-1], "Dimension length = 80 mm")
        self.doc.undo()                                                                       # the dimension is one step
        self.assertEqual(sketching.dimensions(sketch), [])
        self.doc.undo()                                                                       # the drag of the corner
        box = sketch.Shape.BoundBox
        self.assertEqual((box.XMax, box.YMax), (360.0, 40.0))
        self.doc.undo()                                                                       # the rectangle and its sketch
        self.assertEqual([o for o in self.doc.Objects if sketching.is_sketch(o)], [])

    def test_a_circle_and_a_line_join_the_sketch_and_a_press_on_a_face_attaches_a_new_one(self):
        from freecad.BlocksCAD.cad import sketching
        s = self.session()
        s.select_tool("sketch")
        s.tool_manager.active.values["mode"] = "Circle"
        self.hand(1, (50.0, 50.0, 96.0))                                                      # the tip is near the top face of the box
        for _ in range(12):
            s.frame(0.02)
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (70.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (70.0, 50.0, 96.0), trigger=0.0)
        (sketch,) = [o for o in self.doc.Objects if sketching.is_sketch(o)]
        self.assertEqual(list(sketch.AttachmentSupport[0][1]), ["Face6"])
        circle = sketch.Geometry[0]
        self.assertAlmostEqual(circle.Radius, 20.0)
        self.assertAlmostEqual(sketch.Shape.BoundBox.ZMax, 100.0)
        s.tool_manager.active.values["mode"] = "Line"
        self.hand(1, (20.0, 20.0, 100.0))
        self.hand(1, (20.0, 20.0, 100.0), trigger=1.0)
        self.hand(1, (20.0, 60.0, 100.0), trigger=1.0)
        self.hand(1, (20.0, 60.0, 100.0), trigger=0.0)
        self.assertEqual(len(sketch.Geometry), 2)
        self.assertTrue(sketching.solved(sketch))

    def test_a_mirror_is_a_parametric_image_one_gap_beyond_the_object(self):
        from freecad.BlocksCAD.cad import duplicate
        text, names = duplicate.mirror(self.doc, [(self.box.Name, "")], 0)
        image = self.doc.getObject(names[0])
        self.assertEqual(image.TypeId, "Part::Mirroring")
        self.assertAlmostEqual(image.Shape.BoundBox.XMin, 110.0)
        self.assertAlmostEqual(image.Shape.BoundBox.XMax, 210.0)
        self.box.Length = 150.0                                                              # the plane stays: the image follows the source
        self.doc.recompute()
        self.assertAlmostEqual(image.Shape.BoundBox.XMin, 60.0)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(names[0]))

    def test_a_pattern_repeats_an_object_three_times_and_its_numbers_stay_editable(self):
        from freecad.BlocksCAD.cad import duplicate
        text, names = duplicate.pattern(self.doc, [(self.box.Name, "")], 1)
        array = self.doc.getObject(names[0])
        self.assertEqual(array.NumberY, 3)
        self.assertAlmostEqual(array.Shape.BoundBox.YMax, 2 * 110.0 + 100.0)
        array.NumberY = 4
        self.doc.recompute()
        self.assertAlmostEqual(array.Shape.BoundBox.YMax, 3 * 110.0 + 100.0)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(names[0]))

    def test_a_fillet_and_a_chamfer_take_the_selected_edges_and_their_size_is_a_value(self):
        import math
        from freecad.BlocksCAD.cad import edges, values
        text, names = edges.make(self.doc, [(self.box.Name, "Edge1"), (self.box.Name, "Edge3")], "fillet", 5.0)
        rounded = self.doc.getObject(names[0])
        self.assertEqual(rounded.TypeId, "Part::Fillet")
        self.assertAlmostEqual(rounded.Shape.Volume, 1.0e6 - 2 * (1 - math.pi / 4) * 25.0 * 100.0, places=3)
        key, factory = values.source(self.doc, lambda doc: [(rounded.Name, "")])
        target = factory()
        self.assertEqual([(f.label, f.value) for f in target.fields()], [("Radius", 5.0)])
        target.set("edge.size", 10.0)
        target.commit()
        self.assertAlmostEqual(rounded.Shape.Volume, 1.0e6 - 2 * (1 - math.pi / 4) * 100.0 * 100.0, places=3)
        with self.assertRaises(ValueError):                                       # a radius larger than the box is taken back
            target.set("edge.size", 400.0)
        self.assertAlmostEqual(edges.size_of(rounded), 10.0)
        target.cancel()
        self.doc.undo()                                                                       # the size edit
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(names[0]))
        text, names = edges.make(self.doc, [(self.box.Name, "Edge1")], "chamfer", 10.0)
        self.assertEqual(self.doc.getObject(names[0]).TypeId, "Part::Chamfer")
        self.assertAlmostEqual(self.doc.getObject(names[0]).Shape.Volume, 1.0e6 - 50.0 * 100.0, places=3)
        text, names = edges.make(self.doc, [(self.box.Name, "Edge1")], "fillet", 400.0)
        self.assertEqual(names, [])
        self.assertIn("too large", text)

    def test_attaching_mates_two_faces_and_the_object_follows_its_support(self):
        import FreeCAD as App
        from freecad.BlocksCAD.cad import attach, edit
        other = self.doc.addObject("Part::Box", "Other")
        other.Length, other.Width, other.Height = 50.0, 40.0, 30.0
        other.Placement = App.Placement(App.Vector(300, 300, 300), App.Rotation(App.Vector(1, 1, 0), 33))
        self.doc.recompute()
        text, name = attach.attach(self.doc, [(other.Name, "Face5"), (self.box.Name, "Face6")])
        self.assertEqual(name, other.Name)
        self.assertEqual(other.MapMode, "FlatFace")
        face = other.Shape.getElement("Face5")                                               # the bottom lies on the top of the box
        self.assertAlmostEqual(face.CenterOfMass.z, 100.0, places=4)
        self.assertAlmostEqual(face.CenterOfMass.x, 50.0, places=4)
        self.assertAlmostEqual(face.CenterOfMass.y, 50.0, places=4)
        self.assertAlmostEqual(other.Shape.BoundBox.ZMin, 100.0, places=4)
        self.assertAlmostEqual(other.Shape.Volume, 50.0 * 40.0 * 30.0, places=3)
        self.box.Placement = App.Placement(App.Vector(500, 0, 0), App.Rotation())            # the support moves, the object follows
        self.doc.recompute()
        self.assertAlmostEqual(other.Shape.getElement("Face5").CenterOfMass.x, 550.0, places=4)
        base, rotation = edit.placement(other)                                               # the Move tool shifts it through the offset
        edit.set_placement(other, (base[0] + 10.0, base[1], base[2]), rotation)
        self.assertAlmostEqual(other.Shape.getElement("Face5").CenterOfMass.x, 560.0, places=4)
        self.assertEqual(other.MapMode, "FlatFace")
        text, names = attach.detach(self.doc, [(other.Name, "")])
        self.assertEqual(names, [other.Name])
        self.assertEqual(other.MapMode, "Deactivated")
        self.assertAlmostEqual(other.Shape.getElement("Face5").CenterOfMass.x, 560.0, places=4)
        self.doc.undo()                                                                      # the detach
        self.assertEqual(other.MapMode, "FlatFace")
        self.doc.undo()                                                                      # the attach
        self.assertEqual(other.MapMode, "Deactivated")

    def test_attaching_refuses_curved_faces_and_a_loop(self):
        import FreeCAD as App
        from freecad.BlocksCAD.cad import attach
        cylinder = self.doc.addObject("Part::Cylinder", "Tube")
        self.doc.recompute()
        text, name = attach.attach(self.doc, [(cylinder.Name, "Face1"), (self.box.Name, "Face6")])
        self.assertEqual((text, name), ("Attach needs flat faces", None))
        cut = self.doc.addObject("Part::Cut", "Cut")
        cut.Base, cut.Tool = self.box, cylinder
        self.doc.recompute()
        text, name = attach.attach(self.doc, [(self.box.Name, "Face6"), (cut.Name, "Face1")])
        self.assertIsNone(name)
        self.assertIn("built from", text)

    def _small_box(self):
        import FreeCAD as App
        other = self.doc.addObject("Part::Box", "Other")
        other.Length, other.Width, other.Height = 50.0, 40.0, 30.0
        other.Placement = App.Placement(App.Vector(300, 300, 300), App.Rotation(App.Vector(1, 1, 0), 33))
        self.doc.recompute()
        return other

    def test_a_fixed_joint_lays_the_faces_together_inside_an_assembly_with_the_target_grounded(self):
        from freecad.BlocksCAD.cad import joints
        other = self._small_box()
        text, name = joints.make(self.doc, [(other.Name, "Face5"), (self.box.Name, "Face6")], "Fixed")
        self.assertEqual(name, other.Name, text)
        assembly = joints.assembly_of(other)
        self.assertEqual(assembly.TypeId, "Assembly::AssemblyObject")
        self.assertIs(joints.assembly_of(self.box), assembly)
        self.assertTrue(assembly.isPartGrounded(self.box))
        face = other.Shape.getElement("Face5")
        self.assertAlmostEqual(face.CenterOfMass.z, 100.0, places=3)
        self.assertAlmostEqual(face.CenterOfMass.x, 50.0, places=3)
        self.assertAlmostEqual(face.CenterOfMass.y, 50.0, places=3)
        self.assertEqual(len(joints.joints_of(assembly, other)), 1)
        text, name = joints.make(self.doc, [(self.box.Name, "Face1"), (other.Name, "Face1")], "Ball")      # a second joint reuses the assembly
        self.assertEqual(len(self.doc.findObjects("Assembly::AssemblyObject")), 1)
        self.doc.undo()
        self.doc.undo()
        self.assertIsNone(joints.assembly_of(other))
        self.assertEqual(self.doc.findObjects("Assembly::AssemblyObject"), [])

    def test_a_slider_keeps_the_object_on_its_axis_and_a_hinge_keeps_it_on_the_pin(self):
        from freecad.BlocksCAD.cad import edit, joints
        other = self._small_box()
        joints.make(self.doc, [(other.Name, "Face5"), (self.box.Name, "Face6")], "Slider")
        base, rotation = edit.placement(other)
        edit.set_placement(other, (base[0] + 30.0, base[1] + 20.0, base[2] + 60.0), rotation)        # off the axis and up it
        centre = other.Shape.getElement("Face5").CenterOfMass
        self.assertAlmostEqual(centre.x, 50.0, places=2)                                             # the slide leaves only the axis
        self.assertAlmostEqual(centre.y, 50.0, places=2)
        self.assertGreater(centre.z, 120.0)
        text, count = joints.remove(self.doc, [(other.Name, "")])
        self.assertEqual(count, 1)
        self.assertEqual(joints.joints_of(joints.assembly_of(other), other), [])
        edit.set_placement(other, (base[0] + 30.0, base[1] + 20.0, base[2] + 60.0), rotation)        # free again
        self.assertNotAlmostEqual(other.Shape.getElement("Face5").CenterOfMass.x, 50.0, places=2)
        joints.make(self.doc, [(other.Name, "Face5"), (self.box.Name, "Face6")], "Revolute")
        centre = other.Shape.getElement("Face5").CenterOfMass
        self.assertAlmostEqual(centre.x, 50.0, places=2)
        self.assertAlmostEqual(centre.z, 100.0, places=2)

    def test_a_joint_of_an_attached_object_or_of_a_part_of_itself_is_refused(self):
        from freecad.BlocksCAD.cad import attach, joints
        other = self._small_box()
        attach.attach(self.doc, [(other.Name, "Face5"), (self.box.Name, "Face6")])
        text, name = joints.make(self.doc, [(other.Name, "Face1"), (self.box.Name, "Face2")], "Fixed")
        self.assertIsNone(name)
        self.assertIn("Detach", text)
        self.assertEqual(self.doc.findObjects("Assembly::AssemblyObject"), [])

    def test_the_anchors_are_the_corners_and_straight_edge_middles_of_the_visible_objects(self):
        from freecad.BlocksCAD.cad import anchors
        found = anchors.collect(self.doc)
        self.assertEqual(len(found), 8 + 12)                                                 # a box: corners and the middles of its edges
        self.assertIn((50.0, 0.0, 0.0), found)
        self.assertIn((100.0, 100.0, 100.0), found)
        self.assertEqual(anchors.collect(self.doc, exclude=(self.box.Name,)), [])
        self.box.Visibility = False
        self.assertEqual(anchors.collect(self.doc), [])
        self.box.Visibility = True
        cylinder = self.doc.addObject("Part::Cylinder", "Tube")
        self.doc.recompute()
        self.assertEqual(len(anchors.collect(self.doc)), 20 + 3)                              # a cylinder: the two seam vertices and the middle of the seam line, its circles are no anchors

    def test_the_ghost_draws_guides_of_every_kind_and_hides_them(self):
        from freecad.BlocksCAD.core import guides
        from freecad.BlocksCAD.render.ghost import Ghost
        from pivy import coin
        ghost = Ghost()
        found = [guides.Guide("axis", 0, (0.0, 0.0, 0.0), (0.0, 20.0, 0.0)), guides.Guide("point", -1, (5.0, 5.0, 5.0), (5.0, 5.0, 5.0))]
        ghost.show_guides(found, 4.0)
        self.assertEqual(ghost._guides.whichChild.getValue(), coin.SO_SWITCH_ALL)
        points, lines = ghost._guide_sets[0]
        self.assertEqual(points.point.getNum(), 2 + 6)                                        # the line and the cross of the X guide
        self.assertEqual(ghost._guide_sets[-1][0].point.getNum(), 6)                          # the cross of the point guide
        self.assertEqual(ghost._guide_sets[1][0].point.getNum(), 0)
        ghost.show_guides([], 4.0)
        self.assertEqual(ghost._guides.whichChild.getValue(), coin.SO_SWITCH_NONE)

    def test_a_push_fuses_an_extrusion_of_the_face_a_pull_cuts_it_and_the_length_stays_editable(self):
        from freecad.BlocksCAD.cad import pushpull
        self.box.setExpression("Height", "100 mm")                                           # a bound size is not changed directly
        self.doc.recompute()
        top = pushpull.face_info(self.box, "Face6")
        self.assertEqual((top[1], top[0][2]), ((0.0, 0.0, 1.0), 100.0))
        text, name = pushpull.apply(self.doc, self.box.Name, "Face6", 30.0)
        pushed = self.doc.getObject(name)
        self.assertEqual(pushed.TypeId, "Part::MultiFuse")
        self.assertAlmostEqual(pushed.Shape.BoundBox.ZMax, 130.0)
        extrusion = [o for o in self.doc.Objects if o.TypeId == "Part::Extrusion"][0]
        extrusion.LengthFwd = 50.0                                                           # the distance is a parameter
        self.doc.recompute()
        self.assertAlmostEqual(pushed.Shape.BoundBox.ZMax, 150.0)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(name))
        text, name = pushpull.apply(self.doc, self.box.Name, "Face6", -40.0)
        self.assertEqual(self.doc.getObject(name).TypeId, "Part::Cut")
        self.assertAlmostEqual(self.doc.getObject(name).Shape.Volume, 100.0 * 100.0 * 60.0)
        mesh = pushpull.preview_mesh(self.box, "Face6", 20.0)
        self.assertEqual(len(mesh.triangles), 12)
        self.assertEqual(sorted({round(p[2]) for p in mesh.points}), [100, 120])

    def test_a_face_that_a_size_moves_is_pushed_by_changing_the_size_and_adds_nothing(self):
        from freecad.BlocksCAD.cad import pushpull
        count = len(self.doc.Objects)
        text, name = pushpull.apply(self.doc, self.box.Name, "Face6", 30.0)                 # the top: Height
        self.assertEqual((name, text), (self.box.Name, "Pushed Box by 30 mm"))
        self.assertEqual((self.box.Height.Value, self.box.Placement.Base.z), (130.0, 0.0))
        text, name = pushpull.apply(self.doc, self.box.Name, "Face5", 20.0)                 # the bottom: Height and the base go with it
        self.assertEqual((self.box.Height.Value, self.box.Placement.Base.z), (150.0, -20.0))
        pushpull.apply(self.doc, self.box.Name, "Face2", -40.0)                              # an end of Length pulled in
        self.assertEqual((self.box.Length.Value, self.box.Placement.Base.x), (60.0, 0.0))
        pushpull.apply(self.doc, self.box.Name, "Face1", -10.0)
        self.assertEqual((self.box.Length.Value, self.box.Placement.Base.x), (50.0, 10.0))
        self.assertEqual(len(self.doc.Objects), count)
        self.assertAlmostEqual(self.box.Shape.Volume, 50.0 * 100.0 * 150.0)
        self.doc.undo()
        self.assertEqual((self.box.Length.Value, self.box.Placement.Base.x), (60.0, 0.0))     # one undo step each

    def test_a_turned_box_and_a_cylinder_end_are_pushed_along_their_own_axes(self):
        import FreeCAD as App
        from freecad.BlocksCAD.cad import pushpull, primitives as prim
        self.box.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90))   # Length now runs along Y
        self.doc.recompute()
        sub = next(f"Face{i + 1}" for i, f in enumerate(self.box.Shape.Faces) if abs(f.normalAt(0, 0).y - 1.0) < 1e-6)
        pushpull.apply(self.doc, self.box.Name, sub, 25.0)
        self.assertEqual(self.box.Length.Value, 125.0)
        cylinder = prim.create(self.doc, "Cylinder", (300.0, 0.0, 0.0), (50.0, 50.0, 80.0))
        top = next(f"Face{i + 1}" for i, f in enumerate(cylinder.Shape.Faces) if abs(f.CenterOfMass.z - 80.0) < 1e-6)
        pushpull.apply(self.doc, cylinder.Name, top, -30.0)
        self.assertEqual(cylinder.Height.Value, 50.0)

    def test_the_ends_of_the_extrusion_of_a_sketch_are_pushed_by_its_lengths(self):
        from freecad.BlocksCAD.cad import pushpull, sketching
        sketch = self.sketch_on()
        sketching.add_rectangle(self.doc, sketch, (0.0, 0.0), (60.0, 40.0))
        text, names = sketching.extrude(self.doc, [(sketch.Name, "")], 20.0)
        solid = self.doc.getObject(names[0])
        faces = {round(f.CenterOfMass.z): f"Face{i + 1}" for i, f in enumerate(solid.Shape.Faces) if abs(f.normalAt(0, 0).z) > 0.99}
        count = len(self.doc.Objects)
        pushpull.apply(self.doc, solid.Name, faces[20], 15.0)                                # the far end
        self.assertEqual((solid.LengthFwd, solid.LengthRev), (35.0, 0.0))
        pushpull.apply(self.doc, solid.Name, faces[0], 10.0)                                 # the end on the sketch
        self.assertEqual((solid.LengthFwd, solid.LengthRev), (35.0, 10.0))
        self.assertAlmostEqual(solid.Shape.BoundBox.ZMin, -10.0)
        self.assertAlmostEqual(solid.Shape.Volume, 60.0 * 40.0 * 45.0)
        self.assertEqual(len(self.doc.Objects), count)
        top = next(f"Face{i + 1}" for i, f in enumerate(solid.Shape.Faces) if abs(f.CenterOfMass.z - 35.0) < 1e-6)
        text, name = pushpull.apply(self.doc, solid.Name, top, -80.0)                        # more than the length: no size change, a cut that fails
        self.assertEqual((solid.LengthFwd, solid.LengthRev), (35.0, 10.0))
        self.assertTrue(text.startswith("Pull failed"), text)

    def test_a_curved_face_cannot_be_pushed_and_a_failed_pull_leaves_the_document_alone(self):
        from freecad.BlocksCAD.cad import pushpull, primitives as prim
        cylinder = prim.create(self.doc, "Cylinder", (300.0, 0.0, 0.0), (50.0, 50.0, 80.0))
        self.assertEqual(pushpull.apply(self.doc, cylinder.Name, "Face1", 10.0), ("Only flat faces can be pushed or pulled", None))
        count = len(self.doc.Objects)
        text, name = pushpull.apply(self.doc, self.box.Name, "Face6", -500.0)                # pulls through the whole box (no size is that small)
        self.assertIsNone(name)
        self.assertTrue(text.startswith("Pull failed"), text)
        self.assertEqual(len(self.doc.Objects), count)

    def test_the_push_pull_tool_pushes_a_face_by_a_drag_along_its_normal_in_one_undo_step(self):
        self.box.setExpression("Height", "100 mm")
        self.doc.recompute()
        s = self.session()
        s.select_tool("pushpull")
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (50.0, 50.0, 130.0), trigger=1.0)
        self.assertEqual(s.ui.gesture_text, "Push: 30 mm")
        self.hand(1, (50.0, 50.0, 130.0), trigger=0.0)
        pushed = [o for o in self.doc.Objects if o.TypeId == "Part::MultiFuse"][0]
        self.assertAlmostEqual(pushed.Shape.BoundBox.ZMax, 130.0)
        self.assertEqual(self.selection(), [(pushed.Name, ())])
        self.doc.undo()
        self.assertEqual([o.TypeId for o in self.doc.Objects], ["Part::Box"])

    def test_picking_and_the_anchors_follow_the_changes_of_the_document_through_the_change_log(self):
        import FreeCAD as App
        from freecad.BlocksCAD.cad import anchors, picking
        probe = lambda p: picking.pick(self.doc, p, 1000.0, "object")
        cache = anchors.Anchors()
        top = (50.0, 50.0, 96.0)
        self.assertEqual(probe(top).name, self.box.Name)
        self.assertEqual(len(cache.get(self.doc)), 8 + 12)                              # eight corners and twelve edge middles
        moved = self.box.Placement.copy()
        moved.Base = App.Vector(500.0, 0.0, 0.0)
        self.box.Placement = moved
        self.assertIsNone(probe(top))                                                    # no recompute needed: the placement is the change
        self.assertEqual(probe((550.0, 50.0, 96.0)).name, self.box.Name)
        self.assertIn((500.0, 0.0, 0.0), [tuple(round(c, 6) for c in a) for a in cache.get(self.doc)])
        self.box.Visibility = False
        self.assertIsNone(probe((550.0, 50.0, 96.0)))
        self.assertEqual(cache.get(self.doc), [])
        self.box.Visibility = True
        self.assertIsNotNone(probe((550.0, 50.0, 96.0)))
        self.assertEqual(cache.get(self.doc, (self.box.Name,)), [])                     # the excluded object has no anchors
        self.doc.openTransaction("delete")
        self.doc.removeObject(self.box.Name)
        self.doc.commitTransaction()
        self.assertIsNone(probe((550.0, 50.0, 96.0)))
        self.assertEqual(cache.get(self.doc), [])
        self.doc.undo()
        self.assertIsNotNone(probe((550.0, 50.0, 96.0)))                                 # the object is back, and so are its points
        self.assertEqual(len(cache.get(self.doc)), 20)
        other = App.newDocument("BlocksCADOther")                                       # a document of its own is read of its own
        try:
            self.assertIsNone(picking.pick(other, (550.0, 50.0, 96.0), 1000.0, "object"))
        finally:
            App.closeDocument(other.Name)

    def test_the_anchors_of_a_sphere_skip_its_degenerated_pole_edges(self):
        from freecad.BlocksCAD.cad import anchors, primitives as prim
        sphere = prim.create(self.doc, "Sphere", (300.0, 0.0, 0.0), (50.0, 50.0, 50.0))
        points = anchors.object_points(sphere)
        self.assertIsNotNone(points)
        self.assertTrue(all(len(p) == 3 for p in points))

    def test_warming_reads_every_box_at_once_and_a_pick_after_it_reads_nothing(self):
        from freecad.BlocksCAD.cad import picking, primitives as prim
        for i in range(5):
            prim.create(self.doc, "Box", (300.0 + 150.0 * i, 0.0, 0.0), (100.0, 100.0, 100.0))
        picking.warm(self.doc)
        values, touched = picking._BOXES.sync(self.doc)
        self.assertEqual(touched, set())                                                    # nothing was left to read
        self.assertEqual(len(values), 6)
        self.assertEqual(picking.pick(self.doc, (350.0, 50.0, 96.0), 1000.0, "object").kind, "object")
        self.assertEqual(picking._BOXES.sync(self.doc)[1], set())

    def test_picking_one_sort_of_element_ignores_closer_elements_of_another_sort(self):
        from freecad.BlocksCAD.cad import picking
        probe = lambda p, kind: picking.pick(self.doc, p, 1000.0, kind)
        corner = (3.0, 3.0, 3.0)                                                              # a corner is nearest, but a face may be asked for
        self.assertEqual([probe(corner, k).kind for k in ("vertex", "edge", "face", "object")], ["vertex", "edge", "face", "object"])
        self.assertEqual(probe(corner, "object").sub, "")
        self.assertIsNone(probe((50.0, 50.0, 96.0), "vertex"))                                # a vertex is 50 mm away: out of its reach of 12 mm
        self.assertIsNone(probe((50.0, 50.0, 96.0), "edge"))
        self.assertEqual(probe((50.0, 50.0, 96.0), "face").kind, "face")
        self.assertEqual(probe((50.0, 50.0, 96.0), "object").sub, "")                         # a touch of any element is a touch of the object
        for kind in ("vertex", "edge", "face", "object"):
            self.assertIsNone(probe((400.0, 400.0, 400.0), kind))

    def settle(self, point, frames=6):
        """Hold the cursor at a point until the hover has moved to what is there."""
        for _ in range(frames):
            self.hand(1, point)

    def tap(self, point):
        self.settle(point)
        self.hand(1, point, trigger=1.0)
        self.hand(1, point, trigger=0.0)

    def test_the_select_tool_selects_many_faces_edges_vertices_and_objects(self):
        from freecad.BlocksCAD.cad import picking, primitives as prim
        cylinder = prim.create(self.doc, "Cylinder", (300.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        s = self.session()
        s.select_tool("select")
        tool = s.tool_manager.active
        tool.values["operation"] = "Add"
        undo_steps = self.doc.UndoCount
        for target, points in (("Face", ((50.0, 50.0, 96.0), (50.0, 50.0, 4.0))), ("Edge", ((50.0, 4.0, 4.0), (50.0, 96.0, 96.0))),
                               ("Vertex", ((3.0, 3.0, 3.0), (97.0, 97.0, 97.0)))):
            picking.clear_selection()
            tool.values["target"] = target
            for point in points:
                self.tap(point)
            selected = picking.get_selection(self.doc)
            self.assertEqual(len(selected), 2, target)
            self.assertEqual({picking.kind_of(sub) for _, sub in selected}, {target.lower()}, target)
            self.assertEqual({name for name, _ in selected}, {self.box.Name})
        picking.clear_selection()
        tool.values["target"] = "Object"
        inside = cylinder.Shape.BoundBox.Center
        self.tap((50.0, 50.0, 50.0))
        self.tap((inside.x, inside.y, inside.z))
        self.assertEqual(picking.get_selection(self.doc), [(self.box.Name, ""), (cylinder.Name, "")])
        tool.values["operation"] = "Remove"
        self.tap((50.0, 50.0, 96.0))                                                          # touching a face removes the whole object
        self.assertEqual(picking.get_selection(self.doc), [(cylinder.Name, "")])
        tool.values["operation"] = "Replace"
        self.tap((50.0, 50.0, 50.0))
        self.assertEqual(picking.get_selection(self.doc), [(self.box.Name, "")])
        self.assertEqual(self.doc.UndoCount, undo_steps)                                      # selecting makes no undo step

    def test_the_select_tool_highlights_the_element_of_its_target_and_the_selection_opens_the_value_panels(self):
        from pivy import coin
        from freecad.BlocksCAD.cad import picking
        picking.clear_selection()
        s = self.session()
        s.select_tool("select")
        tool = s.tool_manager.active
        self.settle((50.0, 50.0, 96.0))
        self.assertEqual((tool._hover.kind, tool._hover.sub), ("object", ""))                 # what a press would select is what is lit
        self.assertEqual(s.highlights.hover.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        tool.values["target"] = "Face"
        self.hand(1, (50.0, 50.0, 96.0))
        self.assertEqual(tool._hover.kind, "face")                                            # at once, without the wait of a trembling hand
        self.assertFalse(s.ui.module.is_open)
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (50.0, 50.0, 96.0), trigger=0.0)
        for _ in range(3):
            self.hand(1, (50.0, 50.0, 96.0))
        self.assertTrue(s.ui.module.is_open)                                                  # the value editor opens as it does for the Move tool
        self.assertEqual(s.highlights.selected.root.whichChild.getValue(), coin.SO_SWITCH_ALL)

    def test_releasing_the_a_button_without_moving_the_hand_chooses_the_select_tool_and_the_hub_is_lit(self):
        from freecad.BlocksCAD.ui import style
        s = self.session()
        self.assertEqual(s.tool_manager.active_name, "move")
        self.hand(1, (60.0, 50.0, 96.0), button1=True)
        self.assertTrue(s.ui.radial.is_open)
        self.assertNotIn("tool.select", s.ui.radial._items)                  # never one of the segments
        self.assertEqual(s.ui.radial_view._hub_rgb, style.HOVER)
        self.assertEqual(s.ui.radial_view._hub_lines, ["Select"])
        self.hand(1, (60.0, 50.0, 96.0), button1=False)
        self.assertEqual(s.ui_update.activated, "tool:select")
        self.assertNotIn("tool.select", s.ui.settings.recent)

    def test_the_quick_radial_stays_closed_during_a_grab_and_a_padlock_shows_over_the_a_button(self):
        from pivy import coin
        s = self.session()
        lock = lambda: (s.ui.feedback._lock.root.whichChild.getValue(), s.ui.feedback._lock._states.whichChild.getValue())
        self.hand(1, (50.0, 50.0, 96.0))
        self.assertEqual(lock()[0], coin.SO_SWITCH_NONE)                     # no grab: no hint
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (60.0, 50.0, 96.0), trigger=1.0)
        self.assertEqual(lock(), (coin.SO_SWITCH_ALL, 0))                    # an open padlock: free
        self.hand(1, (60.0, 50.0, 96.0), trigger=1.0, button1=True)          # A pressed: locked, and no quick radial
        self.hand(1, (60.0, 50.0, 96.0), trigger=1.0, button1=True)          # the hint follows the tool by a frame
        self.assertEqual(lock(), (coin.SO_SWITCH_ALL, 1))
        self.assertFalse(s.ui.radial.is_open)
        self.assertEqual(s.ui.radial_view.root.whichChild.getValue(), coin.SO_SWITCH_NONE)
        self.hand(1, (60.0, 50.0, 96.0), trigger=0.0, button1=True)
        self.hand(1, (60.0, 50.0, 96.0), trigger=0.0, button1=False)
        self.hand(1, (60.0, 50.0, 96.0), trigger=0.0, button1=False)
        self.assertEqual(lock()[0], coin.SO_SWITCH_NONE)
        self.hand(1, (60.0, 50.0, 96.0), button1=True)                       # outside a grab A opens the quick radial again
        self.assertTrue(s.ui.radial.is_open)
        self.hand(1, (60.0, 50.0, 96.0), button1=False)

    def test_the_padlock_lies_flat_over_the_a_button_of_the_model(self):
        from pivy import coin
        from freecad.BlocksCAD.render.model_anchor import button_anchor
        from freecad.BlocksCAD.ui import controller
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        anchor = button_anchor(s.hand_models[1], lift=controller.LOCK_LIFT)
        aim = s.last_frame.hands[1].aim
        expected = self.mu.add(aim.position, self.mu.rotate(aim.orientation, anchor))
        icon = s.ui.feedback._lock
        self.assertEqual(icon.root.whichChild.getValue(), coin.SO_SWITCH_ALL)   # shown
        shown = icon._transform.translation.getValue().getValue()
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(shown, expected)))
        self.assertGreater(anchor[1], controller.LOCK_LIFT)                  # above the top of the button
        self.assertAlmostEqual(icon._transform.scaleFactor.getValue().getValue()[0], icon.SCALE)
        up = self.mu.rotate(aim.orientation, (0.0, 1.0, 0.0))                # the plate faces the way the thumb is on
        normal = self.mu.rotate(tuple(icon._transform.rotation.getValue().getValue()), (0.0, 0.0, 1.0))
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(normal, up)))

    def test_the_option_disc_is_centred_over_the_thumbstick_in_the_plane_of_the_controller_top(self):
        import math
        from freecad.BlocksCAD.render.model_anchor import STICK_PARTS, button_anchor
        from freecad.BlocksCAD.ui import controller
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        s.input.set_hand(1, stick=(0.0, 1.0))
        s.frame(0.02)
        aim = s.last_frame.hands[1].aim
        anchor = button_anchor(s.hand_models[1], STICK_PARTS, controller.OPTION_DISC_LIFT)
        expected = self.mu.add(aim.position, self.mu.rotate(aim.orientation, anchor))
        found = s.ui.part_frame(1, STICK_PARTS, controller.OPTION_DISC_LIFT)
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(found[0], expected)))
        up = self.mu.rotate(aim.orientation, (0.0, 1.0, 0.0))
        self.assertAlmostEqual(sum(a * b for a, b in zip(found[3], up)), 1.0, places=6)
        self.assertAlmostEqual(math.sqrt(sum(c * c for c in found[2])), 1.0, places=6)

    def test_the_option_disc_falls_back_to_a_point_above_a_controller_without_a_thumbstick(self):
        from freecad.BlocksCAD.render.model_anchor import STICK_PARTS
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        s.ui.part_frame = None
        placed = s.ui._controller_frame(s.last_frame, 1, STICK_PARTS, 0.04)
        aim = s.last_frame.hands[1].aim
        up = self.mu.rotate(aim.orientation, (0.0, 1.0, 0.0))
        offset = self.mu.sub(placed[0], aim.position)
        self.assertGreater(sum(a * b for a, b in zip(offset, up)), 0.04)

    def test_toasts_hang_behind_the_face_buttons_of_the_tool_hand_and_face_the_head(self):
        from pivy import coin
        from freecad.BlocksCAD.ui import controller, feedback_view
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        s.ui.toast("Hello")
        s.frame(0.1)
        plate = next(p for p in s.ui.feedback._toasts if p.root.whichChild.getValue() == coin.SO_SWITCH_ALL)
        shown = plate._transform.translation.getValue().getValue()
        anchor = s.ui._wrist_anchor(s.last_frame)
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(shown, anchor)))
        aim = s.last_frame.hands[1].aim
        self.assertLess(self.mu.length(self.mu.sub(anchor, aim.position)), 0.25)       # on the controller, not in front of the head
        head = s.last_frame.head.position
        normal = self.mu.rotate(tuple(plate._transform.rotation.getValue().getValue()), (0.0, 0.0, 1.0))
        towards = self.mu.normalize(self.mu.sub(head, anchor))
        self.assertAlmostEqual(sum(a * b for a, b in zip(normal, towards)), 1.0, places=5)
        self.assertAlmostEqual(plate._transform.scaleFactor.getValue().getValue()[0],
                               feedback_view.WRIST_SCALE * s.ui.toasts.items[0].scale, places=5)

    def test_toasts_return_in_front_of_the_head_when_the_tool_hand_is_not_tracked(self):
        from dataclasses import replace
        from pivy import coin
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        frame = s.last_frame
        lost = replace(frame.hands[1], aim=replace(frame.hands[1].aim, tracked=False))
        frame = replace(frame, hands=[frame.hands[0], lost])
        self.assertIsNone(s.ui._wrist_anchor(frame))
        s.ui.toast("Hello")
        s.ui.feedback.update(frame.head, s.ui.toasts.update(0.1))
        plate = next(p for p in s.ui.feedback._toasts if p.root.whichChild.getValue() == coin.SO_SWITCH_ALL)
        self.assertAlmostEqual(plate._transform.scaleFactor.getValue().getValue()[0], 1.5 * s.ui.toasts.items[0].scale, places=5)

    def test_a_grab_selects_the_whole_object_as_it_starts(self):
        from pivy import coin
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.assertEqual(self.selection(), [(self.box.Name, ())])
        self.assertEqual(s.highlights.selected.root.whichChild.getValue(), coin.SO_SWITCH_ALL)

    def test_the_stick_chooses_from_the_option_disc_of_the_move_tool(self):
        import math
        s = self.session()
        tool = s.tool_manager.active
        push = lambda degrees: s.input.set_hand(1, stick=(math.sin(math.radians(degrees)), math.cos(math.radians(degrees))))
        release = lambda: (s.input.set_hand(1, stick=(0.0, 0.0)), s.frame(0.02), s.frame(0.02))
        for degrees, option, expected in ((120, "mode", "Move"), (60, "mode", "Move and rotate")):
            push(degrees)
            s.frame(0.02)
            self.assertEqual(tool.values[option], expected, f"{degrees}")
            release()

    # the value panels
    def select(self, name=None, sub=""):
        """Select an object as a whole (the panels follow the selection) and let the carousel with the panels fade in."""
        from freecad.BlocksCAD.cad import picking
        s = self.s or self.session()
        picking.set_selection(self.doc, [(name or self.box.Name, sub)] if name != "" else [])
        s.input.set_head(position=(0.0, 1.5, 0.0), look_at_point=s.input.hands[0].aim.position)       # looking at the left controller
        self.hand(1, (400.0, 400.0, 400.0))
        for _ in range(12):
            s.frame(0.02)
        return s.ui.module

    def push(self, x, y, frames=1):
        s = self.s
        s.input.set_hand(1, stick=(x, y))
        for _ in range(frames):
            s.frame(0.02)
        s.input.set_hand(1, stick=(0.0, 0.0))
        s.frame(0.02)

    def face_point(self, face_id, along=None, dy=0.0, front=0.01):
        """The point `front` in front of a face of the carousel (a slider: at `along` of its track, `dy` above the middle of its row)."""
        from freecad.BlocksCAD.ui import ring as rg
        ui = self.s.ui
        pages = ui.shown_layout().pages
        candidates = [i for i, p in enumerate(pages) if face_id in p.slots]
        page = next((i for i in candidates if pages[i].side == ui.ring.front_side()), candidates[0])     # the Value panel stands on every side
        if pages[page].side != ui.ring.front_side():
            ui.ring.focus_side(pages[page].side)                          # turn the carousel to the face
            self.s.frame(0.02)
        centre, u, v = ui.ring.slot_centre(page, pages[page].slots.index(face_id))
        x = 0.0 if along is None else (-rg.GRID_W / 2 + rg.SLIDER_PAD) + along * (rg.GRID_W - 2 * rg.SLIDER_PAD)
        n = ui.ring.poses[page].n
        return self.mu.add(self.mu.add(self.mu.add(centre, self.mu.mul(u, x)), self.mu.mul(v, dy)), self.mu.mul(n, front))

    def tip_to(self, point, **inputs):
        s = self.s
        s.input.set_hand(1, position=(point[0], point[1], point[2] + self.tip), orientation=(0.0, 0.0, 0.0, 1.0), **inputs)
        s.frame(0.02)

    def press_face(self, face_id):
        """Touch a face of the carousel with the tip of the tool hand, press the trigger and let it go."""
        point = self.face_point(face_id)
        self.tip_to(point, trigger=0.0)
        self.tip_to(point)
        self.tip_to(point, trigger=1.0)
        self.tip_to(point, trigger=0.0)
        self.s.frame(0.02)

    BAR = -0.013      # the bar of a slider lies this far below the middle of its row

    def drag_slider(self, face_id, *alongs):
        """Press the trigger on the bar of a slider and drag the tip along the track through the positions `alongs`."""
        self.tip_to(self.face_point(face_id, alongs[0], self.BAR), trigger=0.0)
        self.tip_to(self.face_point(face_id, alongs[0], self.BAR))
        for along in alongs:
            self.tip_to(self.face_point(face_id, along, self.BAR), trigger=1.0)
        self.tip_to(self.face_point(face_id, alongs[-1], self.BAR), trigger=0.0)
        self.s.frame(0.02)

    def focus(self, face_id):
        """Bring the tip close to a slider without touching it."""
        self.tip_to(self.face_point(face_id, 0.5, 0.0, front=0.08), trigger=0.0)
        self.tip_to(self.face_point(face_id, 0.5, 0.0, front=0.08))

    def test_selecting_an_object_swaps_the_palette_carousel_for_the_values_carousel_and_clearing_it_swaps_back(self):
        from pivy import coin
        s = self.session()
        s.ui.ring.focus_side(2)
        tool_sides, front = len(s.ui.layout.sides()), s.ui.ring.front_side()
        module = self.select("")
        self.assertFalse(module.is_open)                                               # nothing is selected
        self.assertEqual(s.ui.carousel, "tools")
        module = self.select()
        self.assertTrue(module.is_open)                                                # no click is needed
        self.assertEqual(module.editor.target.title, self.box.Label)
        self.assertEqual([f.label for f in module.editor.fields], ["Length", "Width", "Height", "X", "Y", "Z"])
        self.assertEqual(s.ui.carousel, "values")
        names = [p.name for p in s.ui.shown_layout().pages]
        self.assertEqual(sorted(names), sorted(["Values", "Variables", "Keys", "Number pad", "Value", "Value"]))
        self.assertEqual(len(s.ui.ring.display_sides()), 2)                            # the palette carousel is gone
        self.assertEqual(s.ui.ring.front_side(), 0)                                    # the list of the values is in front
        self.assertEqual(s.ui.view.root.whichChild.getValue(), coin.SO_SWITCH_ALL)
        self.assertFalse(s.ui.ring.pinned)                                             # it is not forced open
        self.assertEqual(s.ui.ring.fixed_from, len(s.ui.values_layout.pages))
        module = self.select("")
        self.assertFalse(module.is_open)
        for _ in range(3):
            s.frame(0.02)
        self.assertEqual((s.ui.carousel, len(s.ui.ring.display_sides()), s.ui.ring.front_side(), s.ui.ring.fixed_from),
                         ("tools", tool_sides, front, None))

    def test_the_trigger_of_the_palette_hand_swaps_the_carousels_while_an_object_is_selected(self):
        s = self.session()
        self.select("")
        s.input.set_hand(0, trigger=1.0)
        s.frame(0.02)
        s.input.set_hand(0, trigger=0.0)
        s.frame(0.02)
        self.assertEqual(s.ui.carousel, "tools")                                       # nothing is selected: there is no other carousel
        self.select()
        s.ui.ring.focus_side(1)
        s.frame(0.02)

        def tap():
            s.input.set_hand(0, trigger=1.0)
            s.frame(0.02)
            s.input.set_hand(0, trigger=0.0)
            s.frame(0.02)
        tap()
        self.assertEqual(s.ui.carousel, "tools")
        self.assertEqual(len(s.ui.ring.display_sides()), len(s.ui.layout.sides()))
        self.assertEqual(s.ui.ring.front_side(), 0)
        s.ui.ring.focus_side(3)
        s.frame(0.02)
        tap()
        self.assertEqual(s.ui.carousel, "values")
        self.assertEqual(s.ui.ring.front_side(), 1)                                    # each carousel is at the side it was left at
        tap()
        self.assertEqual((s.ui.carousel, s.ui.ring.front_side()), ("tools", 3))
        self.assertTrue(s.ui.module.is_open)                                           # the object stays selected

    def test_the_trigger_of_the_palette_hand_scales_in_the_move_tool_and_does_not_swap(self):
        s = self.session()
        self.select()
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.assertTrue(s.tool_manager.active.busy)                                    # the box is grabbed
        s.input.set_hand(0, trigger=1.0)
        s.frame(0.02)
        self.assertEqual(s.ui.carousel, "values")                                      # the other trigger scales, it does not swap
        s.input.set_hand(0, trigger=0.0)
        self.hand(1, (50.0, 50.0, 96.0), trigger=0.0)
        self.assertFalse(s.tool_manager.active.busy)
        s.input.set_hand(0, trigger=1.0)
        s.frame(0.02)
        s.input.set_hand(0, trigger=0.0)
        s.frame(0.02)
        self.assertEqual(s.ui.carousel, "tools")                                       # after the grab it swaps again

    def test_the_panels_follow_the_selection_from_one_object_to_the_next_and_stay_where_they_are(self):
        from freecad.BlocksCAD.cad import primitives as prim
        cylinder = prim.create(self.doc, "Cylinder", (200.0, 0.0, 0.0), (80.0, 80.0, 60.0))
        s = self.session()
        module = self.select()
        self.assertEqual(module.key[1], self.box.Name)
        self.select(cylinder.Name)
        self.assertEqual(module.key[1], cylinder.Name)
        self.assertEqual([f.label for f in module.editor.fields], ["Radius", "Height", "X", "Y", "Z"])
        s.ui.ring.focus_side(1)
        s.frame(0.02)
        self.select(self.box.Name)
        self.assertEqual(s.ui.ring.front_side(), 1)                                    # they did not turn again
        self.select("")
        self.assertFalse(module.is_open)
        self.select(self.box.Name, "Face6")                                            # a selected face selects its object for the panels
        self.assertEqual(module.key[1], self.box.Name)

    def test_a_press_on_the_values_panel_picks_the_value_and_lights_its_face(self):
        s = self.session()
        module = self.select()
        self.press_face("val.item.2")
        self.assertEqual(module.editor.selected, 2)
        self.assertEqual(module.readouts()["val.readout"], ("Height", "100 mm", False))
        self.assertEqual(s.ui.module.picked_actions(), {"values:val.item.2"})
        self.assertEqual(s.ui.module.labels()["val.item.3"], "X 0 mm")

    def test_the_value_panels_are_rearranged_like_the_palette_panels_and_the_value_panel_stays_on_top(self):
        import os
        import tempfile
        from freecad.BlocksCAD.ui.controller import UiController
        from freecad.BlocksCAD.tools import registry
        s = self.session()
        self.select()
        ui = s.ui
        layout = ui.values_layout
        names = [p.name for p in layout.pages]
        self.assertEqual(names, ["Values", "Variables", "Keys", "Number pad"])
        self.assertTrue(all(ui.shown_layout().pages[i].name == "Value" for i in range(len(names), len(ui.shown_layout().pages))))
        ui.values_layout.move_page(3, 0, 0, 0, False)                                  # the Number pad next to the Values panel
        ui._save_layout()
        s.frame(0.02)
        self.assertEqual([(p.name, p.side) for p in ui.values_layout.pages][:2], [("Number pad", 0), ("Values", 0)])
        self.assertEqual(ui.ring.fixed_from, 4)
        self.assertEqual(ui.shown_layout().pages[-1].name, "Value")
        # the faces of the values carousel cannot be lifted or moved
        self.assertFalse(ui.ring.can_lift(0, 0))
        self.assertFalse(ui.ring.can_drop((0, 0), (1, 0)))
        with tempfile.TemporaryDirectory() as folder:
            paths = dict(layout_path=os.path.join(folder, "layout.json"), settings_path=os.path.join(folder, "settings.json"),
                         values_layout_path=os.path.join(folder, "values_layout.json"))
            first = UiController(registry.names(), registry.label_of, {}, **paths)
            first.values_layout.move_page(3, 0, 0, 0, False)
            first._save_layout()
            second = UiController(registry.names(), registry.label_of, {}, **paths)
            self.assertEqual([(p.name, p.side) for p in second.values_layout.pages][:2], [("Number pad", 0), ("Values", 0)])
            second.reset_layout()
            self.assertEqual([p.name for p in second.values_layout.pages], ["Values", "Variables", "Keys", "Number pad"])
            self.assertFalse(os.path.exists(paths["values_layout_path"]))
            first.close()
            second.close()

    def test_the_value_panels_are_ordinary_depth_tested_geometry(self):
        from pivy import coin
        s = self.session()
        self.select()
        action = coin.SoSearchAction()
        action.setType(coin.SoDepthBuffer.getClassTypeId())
        action.setInterest(coin.SoSearchAction.ALL)
        action.apply(s.ui.view.root)
        self.assertEqual(action.getPaths().getLength(), 0)                             # nothing of the carousel ignores the depth

    def test_the_stick_steps_the_picked_value_while_the_slider_is_focused_and_one_push_is_one_undo_step(self):
        s = self.session()
        module = self.select()
        steps = self.doc.UndoCount
        self.press_face("val.next")
        self.assertEqual(module.editor.selected, 1)                                    # Width is picked with the selector
        self.focus("val.slider")
        self.assertTrue(module.engaged)
        self.assertTrue(s.ui_update.owns_stick)
        self.push(0.0, 1.0)
        self.assertEqual(self.box.Width.Value, 110.0)
        self.assertEqual((self.box.Length.Value, self.box.Height.Value), (100.0, 100.0))
        self.focus("val.slider")
        self.push(0.0, 1.0)
        self.focus("val.slider")
        self.push(0.0, -1.0)
        self.assertEqual(self.box.Width.Value, 110.0)
        self.assertEqual(self.doc.UndoCount, steps + 3)                                # three pushes, three undo steps
        self.doc.undo()
        self.assertEqual(self.box.Width.Value, 120.0)

    def test_without_a_focused_slider_the_stick_belongs_to_the_tool(self):
        import math
        from pivy import coin
        s = self.session()
        tool = s.tool_manager.active
        module = self.select()
        self.tip_to(self.face_point("val.slider", 0.5, 0.0, front=0.4), trigger=0.0)   # far from the panels
        self.assertFalse(module.engaged)
        self.push(math.sin(math.radians(120)), math.cos(math.radians(120)))
        self.assertEqual(self.box.Width.Value, 100.0)
        self.assertEqual(tool.values["mode"], "Move")                                  # the option disc of the Move tool took the stick
        self.assertFalse(s.ui_update.owns_stick and module.engaged)

    def test_a_slider_changes_its_value_only_when_its_bar_is_pressed_and_dragged(self):
        s = self.session()
        module = self.select()
        steps = self.doc.UndoCount
        point = self.face_point("val.slider", 0.8, 0.015)                              # the label part of the row
        self.tip_to(point, trigger=0.0)
        self.tip_to(point, trigger=1.0)
        self.tip_to(point, trigger=0.0)
        self.assertEqual(self.box.Length.Value, 100.0)                                 # a press beside the bar does nothing
        self.assertEqual(module.editor.selected, 0)
        self.drag_slider("val.slider", 0.5, 0.62, 0.77)                                # Length: the track is 0 to 200 mm, the step 10 mm
        self.assertEqual(self.box.Length.Value, 150.0)
        self.assertEqual(self.box.Shape.BoundBox.XLength, 150.0)
        self.assertEqual(module.readouts()["val.readout"], ("Length", "150 mm", False))
        self.assertEqual(self.doc.UndoCount, steps + 1)                                # the whole drag is one undo step
        self.press_face("val.next")
        self.drag_slider("val.slider", 0.5, 0.1)
        self.assertEqual(self.box.Width.Value, 20.0)
        self.assertEqual(module.editor.selected, 1)
        self.assertEqual(self.doc.UndoCount, steps + 2)
        self.doc.undo()
        self.assertEqual((self.box.Length.Value, self.box.Width.Value), (150.0, 100.0))

    def test_the_selector_picks_the_value_the_readout_and_the_slider_show(self):
        module = self.select()
        self.assertEqual(module.labels()["val.which"], "Value 1 of 6")
        for _ in range(3):
            self.press_face("val.next")
        self.assertEqual(module.labels()["val.which"], "Value 4 of 6")
        self.assertEqual(module.readouts()["val.readout"], ("X", "0 mm", False))
        self.assertEqual(module.slider_states()["val.slider"][1], "-100 to 100 mm")
        self.press_face("val.next")
        self.drag_slider("val.slider", 0.75)                                           # Y: a track from -100 to 100 mm
        self.assertEqual(self.box.Placement.Base.y, 50.0)
        self.assertEqual(module.editor.selected, 4)
        self.press_face("val.prev")
        self.assertEqual(module.editor.selected, 3)

    def test_the_step_slider_goes_down_to_a_hundredth_of_a_millimetre(self):
        module = self.select()
        self.drag_slider("val.step", 0.0)
        self.assertEqual(module.editor.step, 0.01)
        self.assertEqual(module.slider_states()["val.step"][1], "Step 0.01 mm")
        self.focus("val.slider")
        self.push(0.0, 1.0)
        self.assertAlmostEqual(self.box.Length.Value, 100.01)

    def test_the_keys_of_the_carousel_type_an_expression_with_a_unit_and_enter_keeps_each_value(self):
        module = self.select()
        steps = self.doc.UndoCount
        for key in ("key.2", "key.times", "key.open", "key.3", "key.close", "key.unit", "key.unit", "key.enter"):    # 2 * (3) cm
            self.press_face(key)
        self.assertAlmostEqual(self.box.Length.Value, 60.0)
        self.assertIsNone(module.editor.entry)
        self.assertEqual(self.doc.UndoCount, steps + 1)
        for _ in range(3):
            self.press_face("val.next")                                                # X is picked
        for key in ("key.minus", "key.5", "key.enter"):
            self.press_face(key)
        self.assertEqual(self.box.Placement.Base.x, -5.0)
        self.assertEqual(self.doc.UndoCount, steps + 2)
        self.doc.undo()
        self.assertEqual((self.box.Length.Value, self.box.Placement.Base.x), (60.0, 0.0))

    def test_the_readout_shows_what_is_typed_and_the_step_slider_sets_the_step_of_the_stick(self):
        s = self.session()
        module = self.select()
        self.assertEqual(module.titles(), {"Value": self.box.Label})
        self.press_face("key.7")
        self.assertEqual(module.readouts()["val.readout"], ("Length, Enter applies", "7|", True))
        self.press_face("key.delete")
        self.assertEqual(module.readouts()["val.readout"], ("Length", "100 mm", False))
        self.drag_slider("val.step", 10 / 12)
        self.assertEqual(module.slider_states()["val.step"][1], "Step 20 mm")
        self.focus("val.slider")
        self.push(0.0, 1.0)
        self.assertEqual(self.box.Length.Value, 120.0)                                 # the stick uses the new step

    def test_an_object_can_be_grabbed_while_the_panels_are_up_and_they_follow_it(self):
        s = self.session()
        module = self.select()
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (80.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (80.0, 50.0, 96.0), trigger=0.0)
        self.assertEqual(tuple(self.box.Placement.Base), (30.0, 0.0, 0.0))
        self.assertTrue(module.is_open)
        self.assertEqual(module.editor.fields[3].value, 30.0)                          # X shows where the object is now

    def test_the_panels_cannot_be_lifted_or_rearranged(self):
        s = self.session()
        self.select()
        point = self.face_point("key.7")
        self.tip_to(point, trigger=0.0)
        self.tip_to(point, trigger=1.0)
        for _ in range(30):                                                            # held for longer than a face needs to be lifted
            self.tip_to(point, trigger=1.0)
        self.assertIsNone(s.ui.ring.lifted_face)
        self.tip_to(point, trigger=0.0)
        self.assertEqual(s.ui.layout.hidden, [])

    def test_a_torus_cannot_get_a_tube_wider_than_its_ring(self):
        from freecad.BlocksCAD.cad import primitives as prim
        torus = prim.create(self.doc, "Torus", (200.0, 0.0, 0.0), (100.0, 100.0, 100.0))
        s = self.session()
        module = self.select(torus.Name)
        self.assertEqual([f.label for f in module.editor.fields][:2], ["Radius 1", "Radius 2"])
        radius1, radius2 = torus.Radius1.Value, torus.Radius2.Value
        self.press_face("val.next")                                                    # pick Radius 2
        for key in ("key.9", "key.9", "key.enter"):
            self.press_face(key)
        self.assertEqual((torus.Radius1.Value, torus.Radius2.Value), (radius1, radius2))
        self.assertTrue(torus.isValid())
        self.assertEqual([t.text for t in s.ui.toasts.items][-1], "The shape cannot take that value")
        self.drag_slider("val.slider", 1.0)                                            # the slider is refused the same way
        self.assertTrue(torus.isValid())
        self.assertEqual(torus.Radius2.Value, radius2)

    def test_the_click_of_the_stick_changes_nothing_in_the_move_tool_and_the_grid_and_the_angle_are_the_settings(self):
        s = self.session()
        tool = s.tool_manager.active
        self.select("")
        s.ui.settings.grid, s.ui.settings.angle = 50.0, 45.0
        s.input.set_hand(1, stick_click=True)
        s.frame(0.02)
        self.assertEqual((tool.grid, tool.angle), (50.0, 45.0))
        self.assertEqual(tool.disc_hub(), ["Move and rotate", "Grid 50 mm, angle 45 deg"])

    def test_a_cone_may_end_in_a_point(self):
        from freecad.BlocksCAD.cad import values as object_values
        specs = {name: low for name, _, low in object_values.field_specs("Part::Cone")}
        self.assertEqual((specs["Radius1"], specs["Radius2"], specs["Height"]), (0.0, 0.0, 0.1))

    def test_the_source_finds_the_first_editable_object_of_the_selection(self):
        from freecad.BlocksCAD.cad import values as object_values
        self.assertIsNone(object_values.source(self.doc, lambda doc: []))
        self.assertIsNone(object_values.source(None))
        self.assertIsNone(object_values.source(self.doc, lambda doc: [("Nothing", "")]))
        key, factory = object_values.source(self.doc, lambda doc: [("Nothing", ""), (self.box.Name, "Face1")])
        self.assertEqual(key, (self.doc.Name, self.box.Name))
        self.assertEqual(factory().title, self.box.Label)

    def test_the_target_edits_properties_in_one_transaction_that_cancel_aborts(self):
        from freecad.BlocksCAD.cad import values as object_values
        target = object_values.ObjectValues(self.doc, self.box)
        self.assertEqual([(f.name, f.value) for f in target.fields()][:3], [("Length", 100.0), ("Width", 100.0), ("Height", 100.0)])
        target.set("Length", 130.0)
        target.set("pos.z", 7.0)
        self.assertEqual((self.box.Length.Value, self.box.Placement.Base.z), (130.0, 7.0))
        target.cancel()
        self.assertEqual((self.box.Length.Value, self.box.Placement.Base.z), (100.0, 0.0))
        target.cancel()                                                                # nothing open: nothing happens
        target.set("Height", 40.0)
        target.commit()
        self.doc.undo()
        self.assertEqual(self.box.Height.Value, 100.0)

    def test_the_grip_that_cancels_a_grab_does_not_move_the_world_until_it_is_released(self):
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (80.0, 50.0, 96.0), trigger=1.0)
        world = s.navigator.world
        s.input.set_hand(0, grip=1.0)
        s.frame(0.02)
        for x in (0.1, 0.2, 0.3):                                                             # the gripping hand moves on
            s.input.set_hand(0, position=(x, 1.2, -0.3))
            s.frame(0.02)
        self.assertEqual(s.navigator.world, world)
        s.input.set_hand(0, grip=0.0)
        s.frame(0.02)
        s.input.set_hand(0, grip=1.0)                                                         # a fresh grip holds the world again
        s.frame(0.02)
        s.input.set_hand(0, position=(0.5, 1.2, -0.3))
        s.frame(0.02)
        self.assertNotEqual(s.navigator.world, world)

    def test_a_free_grab_ticks_once_for_every_grid_step_it_travels(self):
        s = self.session()
        ticks = []
        s.tool_manager.ctx.haptic = lambda hand, amplitude, duration: ticks.append(amplitude)
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        del ticks[:]
        for x in (51.0, 52.0, 53.0, 54.0):                                                    # within one step of the grid (10 mm)
            self.hand(1, (x + 0.5, 50.0, 96.0), trigger=1.0)
        self.assertEqual(ticks, [])
        for x in range(60, 100, 10):                                                          # four steps further, a step per frame
            self.hand(1, (float(x), 50.0, 96.0), trigger=1.0)
        self.assertEqual(len(ticks), 4)

    def test_a_grip_cancels_the_grab(self):
        s = self.session()
        self.hand(1, (50.0, 50.0, 96.0))
        self.hand(1, (50.0, 50.0, 96.0), trigger=1.0)
        self.hand(1, (80.0, 50.0, 96.0), trigger=1.0)
        self.assertEqual(tuple(self.box.Placement.Base), (30.0, 0.0, 0.0))
        s.input.set_hand(0, grip=1.0)
        s.frame(0.02)
        self.assertEqual(tuple(self.box.Placement.Base), (0.0, 0.0, 0.0))                      # the transaction was aborted
        self.assertIsNone(s.ui.gesture_text)
        s.input.set_hand(0, grip=0.0)
        self.hand(1, (80.0, 50.0, 96.0), trigger=0.0)
        self.assertEqual(tuple(self.box.Placement.Base), (0.0, 0.0, 0.0))
