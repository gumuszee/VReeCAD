import unittest

import support  # noqa: F401
from freecad.VReeCAD.core import snapping
from freecad.VReeCAD.ui import defaults
from freecad.VReeCAD.ui import layout as lay

TOOLS = ["primitive", "select", "move", "pushpull", "points", "sketch"]


class DefaultLayoutTest(unittest.TestCase):
    def test_every_button_has_a_slot_in_the_default_layout(self):
        # a panel holds 12 slots and drops what does not fit, so a button that is missing here is a button nobody can reach
        buttons = defaults.build_buttons(TOOLS, lambda name: name)
        placed = [button for page in defaults.default_layout(TOOLS).pages for button in page.slots if button]
        self.assertEqual(sorted(placed), sorted(buttons))

    def test_no_button_is_placed_twice(self):
        placed = [button for page in defaults.default_layout(TOOLS).pages for button in page.slots if button]
        self.assertEqual(len(placed), len(set(placed)))


    def test_the_pointer_and_the_settings_have_a_panel_each_with_their_sliders_on_whole_rows(self):
        pages = {p.name: p for p in defaults.default_layout(TOOLS).pages}
        self.assertNotIn("Session", pages)
        self.assertEqual(pages["Pointer"].slots[0], "pointer.mode")
        self.assertEqual((pages["Pointer"].slots[4], pages["Pointer"].slots[8]), ("pointer.angle", "pointer.length"))
        self.assertEqual((pages["Settings"].slots[4], pages["Settings"].slots[8]), ("settings.grid", "settings.angle"))
        self.assertIn("settings.tutorial", pages["Settings"].slots)
        self.assertNotIn("view.controls", defaults.build_buttons(TOOLS, lambda name: name))


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
        """A layout as it was saved before the pointer got a panel: the panel called Session holds the pointer buttons."""
        layout = defaults.default_layout(TOOLS)
        layout.pages = [p for p in layout.pages if p.name not in ("Pointer", "Settings")]
        for page in layout.pages:
            page.slots = [None if f == "app.close" else f for f in page.slots]       # Close VR was on the Session panel
        layout.pages.append(lay.Page("Session", ["pointer.mode", "app.close", "pointer.hands", "pointer.submm", "pointer.angle", None, None, None,
                                                 "pointer.length"]))
        layout.normalize()
        return layout

    def test_the_session_panel_is_the_settings_panel_and_the_pointer_buttons_move_to_a_pointer_panel(self):
        loaded = lay.Layout.from_json(self.saved().to_json().replace('"version": 5', '"version": 4'))      # a file of the version before the Pointer panel
        self.assertIn("Settings", [p.name for p in loaded.pages])
        default = defaults.default_layout(TOOLS)
        self.assertTrue(defaults.migrate(loaded, default))
        pages = {p.name: p for p in loaded.pages}
        self.assertEqual([f for f in pages["Pointer"].slots if f], ["pointer.mode", "pointer.angle", "pointer.length"])
        self.assertEqual([f for f in pages["Settings"].slots if f], ["app.close", "pointer.hands", "pointer.submm"])
        self.assertTrue(loaded.add_missing(default, {"pointer.angle", "pointer.length", "settings.grid", "settings.angle"}))
        placed = [f for p in loaded.pages for f in p.slots if f]
        self.assertEqual(sorted(placed), sorted(defaults.build_buttons(TOOLS, lambda name: name)))
        self.assertEqual(len(placed), len(set(placed)))
        self.assertEqual((pages["Settings"].slots[4], pages["Settings"].slots[8]), ("settings.grid", "settings.angle"))

    def test_a_layout_of_the_current_version_is_never_migrated_so_a_panel_the_user_renamed_stays_renamed(self):
        layout = defaults.default_layout(TOOLS)
        next(p for p in layout.pages if p.name == "Pointer").name = "Laser"
        loaded = lay.Layout.from_json(layout.to_json())
        self.assertEqual(loaded.version, lay.VERSION)
        self.assertFalse(defaults.migrate(loaded, defaults.default_layout(TOOLS)))
        self.assertEqual(sum(p.name == "Pointer" for p in loaded.pages), 0)
        self.assertEqual(lay.Layout.from_json('{"pages": [{"name": "A"}]}').version, 0)         # a file without a version is an old one

    def test_the_hue_of_a_panel_is_kept_in_the_file_and_a_bad_one_is_dropped(self):
        layout = lay.Layout([lay.Page("A", ["x"], 0, 0, 0.25), lay.Page("B", ["y"], 1, 0)])
        loaded = lay.Layout.from_json(layout.to_json())
        self.assertEqual([p.hue for p in loaded.pages], [0.25, None])
        text = '{"version": 5, "pages": [{"name": "A", "hue": 7.5}, {"name": "B", "hue": "red"}, {"name": "C", "hue": true}]}'
        self.assertEqual([p.hue for p in lay.Layout.from_json(text).pages], [1.0, None, None])
        self.assertEqual(lay.default_hue("Tools"), 0.38)
        self.assertIn(lay.default_hue("Anything else"), lay.SPARE_HUES)

    def test_a_panel_has_a_grid_of_its_own_that_grows_and_shrinks_without_losing_a_button(self):
        page = lay.Page("A", ["a", "b", None, None, "c"], cols=2, rows=3)
        self.assertEqual((page.cols, page.rows, len(page.slots)), (2, 3, 6))
        self.assertEqual(page.slots, ["a", "b", None, None, "c", None])
        self.assertTrue(page.resize(4, 4))                                         # every button keeps its row and column
        self.assertEqual(page.slots[:9], ["a", "b", None, None, None, None, None, None, "c"])
        self.assertEqual(len(page.slots), 16)
        self.assertFalse(page.resize(1, 4))                                        # b would be cut off
        self.assertEqual((page.cols, page.rows), (4, 4))
        self.assertTrue(page.resize(3, 3))
        self.assertEqual(page.slots, ["a", "b", None, None, None, None, "c", None, None])
        self.assertFalse(page.resize(0, 3))
        self.assertFalse(page.resize(3, lay.MAX_ROWS + 1))
        self.assertFalse(page.resize(lay.MAX_COLS + 1, 3))

    def test_the_grid_of_a_panel_is_kept_in_the_file_and_the_default_grid_is_not_written(self):
        layout = lay.Layout([lay.Page("Wide", ["x"], 0, 0, None, 10, 4), lay.Page("Plain", ["y"], 1, 0)])
        text = layout.to_json()
        self.assertEqual(text.count('"cols"'), 1)
        loaded = lay.Layout.from_json(text)
        self.assertEqual([(p.cols, p.rows, len(p.slots)) for p in loaded.pages], [(10, 4, 40), (4, 3, 12)])
        odd = lay.Layout.from_json('{"version": 5, "pages": [{"name": "A", "cols": "x", "rows": 99, "slots": ["a"]}]}')
        self.assertEqual((odd.pages[0].cols, odd.pages[0].rows), (4, lay.MAX_ROWS))

    def test_missing_buttons_are_placed_by_the_grid_of_the_panel_and_a_slider_keeps_its_whole_row(self):
        page = lay.Page("W", ["s"] + [None] * 5 + ["b"] + [None] * 4, cols=6, rows=2)
        default = lay.Layout([lay.Page("W", ["s", None, None, None, None, None, "t", "b", None, None, None, None], cols=6, rows=2)])
        self.assertTrue(lay.Layout([page]).add_missing(default, {"s"}))
        self.assertEqual(page.slots[7], "t")                                        # the first free slot outside the row of the slider
        self.assertEqual(page.slots[:6], ["s"] + [None] * 5)

    def test_a_layout_that_has_the_pointer_panel_is_left_alone(self):
        layout = defaults.default_layout(TOOLS)
        self.assertFalse(defaults.migrate(layout, defaults.default_layout(TOOLS)))

    def test_the_old_id_of_the_controls_button_is_the_tutorial_button(self):
        self.assertEqual(lay.current_button("view.controls"), "settings.tutorial")
        text = '{"version": 4, "hidden": ["view.controls"], "pages": [{"name": "View", "slots": ["view.controls", "view.reset"]}]}'
        loaded = lay.Layout.from_json(text, {"settings.tutorial", "view.reset"})
        self.assertEqual((loaded.hidden, loaded.pages[0].slots[:2]), (["settings.tutorial"], ["settings.tutorial", "view.reset"]))
