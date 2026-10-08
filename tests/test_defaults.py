import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import snapping
from freecad.BlocksCAD.ui import defaults
from freecad.BlocksCAD.ui import layout as lay

TOOLS = ["primitive", "select", "move", "pushpull", "points", "sketch"]


class DefaultLayoutTest(unittest.TestCase):
    def test_every_face_has_a_slot_in_the_default_layout(self):
        # a panel holds 12 slots and drops what does not fit, so a face that is missing here is a face nobody can reach
        faces = defaults.build_faces(TOOLS, lambda name: name)
        placed = [face for page in defaults.default_layout(TOOLS).pages for face in page.slots if face]
        self.assertEqual(sorted(placed), sorted(faces))

    def test_no_face_is_placed_twice(self):
        placed = [face for page in defaults.default_layout(TOOLS).pages for face in page.slots if face]
        self.assertEqual(len(placed), len(set(placed)))


    def test_the_pointer_and_the_settings_have_a_panel_each_with_their_sliders_on_whole_rows(self):
        pages = {p.name: p for p in defaults.default_layout(TOOLS).pages}
        self.assertNotIn("Session", pages)
        self.assertEqual(pages["Pointer"].slots[0], "pointer.mode")
        self.assertEqual((pages["Pointer"].slots[4], pages["Pointer"].slots[8]), ("pointer.angle", "pointer.length"))
        self.assertEqual((pages["Settings"].slots[4], pages["Settings"].slots[8]), ("settings.grid", "settings.angle"))
        self.assertIn("settings.tutorial", pages["Settings"].slots)
        self.assertNotIn("view.controls", defaults.build_faces(TOOLS, lambda name: name))


class SliderTest(unittest.TestCase):
    def test_a_slider_over_choices_spreads_them_evenly_and_picks_the_nearest(self):
        grid = defaults.SLIDERS["settings.grid"]
        self.assertEqual([grid.value(i / 6) for i in range(7)], list(snapping.GRID_STEPS))
        self.assertEqual((grid.value(-1.0), grid.value(9.0), grid.value(0.52)), (1.0, 100.0, 10.0))
        self.assertEqual([grid.fraction(v) for v in snapping.GRID_STEPS], [i / 6 for i in range(7)])
        angle = defaults.SLIDERS["settings.angle"]
        self.assertEqual([angle.value(i / 4) for i in range(5)], list(snapping.ANGLE_STEPS))
        self.assertEqual(angle.fraction(15.0), 0.25)

    def test_a_slider_over_a_range_rounds_to_its_step(self):
        length = defaults.SLIDERS["pointer.length"]
        self.assertEqual(length.value(0.5), 0.1)
        self.assertEqual(length.fraction(0.1), 0.5)


class MigrationTest(unittest.TestCase):
    def saved(self):
        """A layout as it was saved before the pointer got a panel: the panel called Session holds the pointer faces."""
        layout = defaults.default_layout(TOOLS)
        layout.pages = [p for p in layout.pages if p.name not in ("Pointer", "Settings")]
        for page in layout.pages:
            page.slots = [None if f == "app.close" else f for f in page.slots]       # Close VR was on the Session panel
        layout.pages.append(lay.Page("Session", ["pointer.mode", "app.close", "pointer.hands", "pointer.submm", "pointer.angle", None, None, None,
                                                 "pointer.length"]))
        layout.normalize()
        return layout

    def test_the_session_panel_is_the_settings_panel_and_the_pointer_faces_move_to_a_pointer_panel(self):
        loaded = lay.Layout.from_json(self.saved().to_json())
        self.assertIn("Settings", [p.name for p in loaded.pages])
        default = defaults.default_layout(TOOLS)
        self.assertTrue(defaults.migrate(loaded, default))
        pages = {p.name: p for p in loaded.pages}
        self.assertEqual([f for f in pages["Pointer"].slots if f], ["pointer.mode", "pointer.angle", "pointer.length"])
        self.assertEqual([f for f in pages["Settings"].slots if f], ["app.close", "pointer.hands", "pointer.submm"])
        self.assertTrue(loaded.add_missing(default, {"pointer.angle", "pointer.length", "settings.grid", "settings.angle"}))
        placed = [f for p in loaded.pages for f in p.slots if f]
        self.assertEqual(sorted(placed), sorted(defaults.build_faces(TOOLS, lambda name: name)))
        self.assertEqual(len(placed), len(set(placed)))
        self.assertEqual((pages["Settings"].slots[4], pages["Settings"].slots[8]), ("settings.grid", "settings.angle"))

    def test_a_layout_that_has_the_pointer_panel_is_left_alone(self):
        layout = defaults.default_layout(TOOLS)
        self.assertFalse(defaults.migrate(layout, defaults.default_layout(TOOLS)))

    def test_the_old_id_of_the_controls_face_is_the_tutorial_face(self):
        self.assertEqual(lay.current_face("view.controls"), "settings.tutorial")
        text = '{"version": 4, "hidden": ["view.controls"], "pages": [{"name": "View", "slots": ["view.controls", "view.reset"]}]}'
        loaded = lay.Layout.from_json(text, {"settings.tutorial", "view.reset"})
        self.assertEqual((loaded.hidden, loaded.pages[0].slots[:2]), (["settings.tutorial"], ["settings.tutorial", "view.reset"]))
