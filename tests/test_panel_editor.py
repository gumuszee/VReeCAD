import unittest

import support  # noqa: F401
from freecad.VReeCAD.ui import layout as lay
from freecad.VReeCAD.ui import panel_editor as pe


def press(editor, text):
    last = None
    for char in text:
        last = editor.activate(pe.SPACE if char == " " else pe.key_id(char))
    return last


class PagesTest(unittest.TestCase):
    def test_the_keyboard_is_one_wide_panel_in_qwerty_order_and_the_name_and_colour_stand_over_it(self):
        layout = pe.layout(0.5)
        self.assertEqual([(p.name, p.side, p.row, p.cols, p.rows) for p in layout.pages],
                         [("Keyboard", 0, 0, 10, 4), ("Name", 0, 1, 4, 3), ("Colour", 0, 1, 4, 3)])
        self.assertEqual(layout.sides(), [[[0], [1, 2]]])
        keys = layout.pages[0].slots
        rows = ["".join(f[-1] if f.startswith("ed.key.") else "." for f in keys[r * 10:(r + 1) * 10] if f) for r in range(4)]
        self.assertEqual(rows, ["1234567890", "qwertyuiop", "asdfghjkl.", "zxcvbnm..."])
        self.assertEqual((keys[29], keys[37], keys[38], keys[39]), (pe.BACK, pe.CASE, pe.SPACE, pe.CLEAR))
        self.assertEqual(keys[28 + 1 - 1], "ed.key.l")                                  # the delete key follows the nine letters of the home row
        self.assertTrue(all(p.hue == 0.5 for p in layout.pages))

    def test_every_button_is_known_once_and_the_readout_has_a_row_of_its_own(self):
        known = pe.buttons()
        layout = pe.layout(None)
        placed = [f for p in layout.pages for f in p.slots if f]
        self.assertEqual(sorted(placed), sorted(known))
        self.assertEqual(len(placed), len(set(placed)))
        self.assertEqual(known[pe.READOUT].kind, "readout")
        name = next(p for p in layout.pages if p.name == "Name")
        self.assertEqual(name.slots[:4], [pe.READOUT, None, None, None])
        self.assertEqual(name.slots[4:8], list(pe.SIZE_IDS))
        self.assertTrue(all(len(p.slots) == p.cols * p.rows for p in layout.pages))
        self.assertEqual(len(pe.HUES), lay.SLOTS)                                    # Auto and eleven hues fill the Colour panel

    def test_the_colour_buttons_wear_the_colour_they_give_and_auto_has_a_label_instead(self):
        known = pe.buttons()
        self.assertEqual([known[f].tint for f in pe.HUE_IDS], [h for _, h in pe.HUES])
        self.assertEqual([known[f].label for f in pe.HUE_IDS], ["Auto"] + [""] * 11)


class TypingTest(unittest.TestCase):
    def test_the_name_is_the_text_with_a_capital_at_the_start_of_every_word(self):
        editor = pe.PanelEditor(0, "Tools", None)
        editor.activate(pe.CLEAR)
        press(editor, "my parts 2")
        self.assertEqual(editor.text, "My Parts 2")
        self.assertEqual(editor.readouts()[pe.READOUT], ("Name, panel of 4 x 3 buttons", "My Parts 2|", True))

    def test_a_name_that_is_edited_goes_on_in_small_letters_and_the_case_key_makes_capitals(self):
        editor = pe.PanelEditor(0, "Tools", None)
        press(editor, "x")
        self.assertEqual(editor.text, "Toolsx")
        self.assertEqual(editor.labels()[pe.key_id("a")], "a")
        editor.activate(pe.CASE)
        self.assertEqual((editor.labels()[pe.key_id("a")], editor.labels()[pe.CASE]), ("A", "ABC"))
        press(editor, "yz")
        self.assertEqual(editor.text, "ToolsxYZ")
        self.assertIn("editor:" + pe.CASE, editor.lit_actions())
        editor.activate(pe.CASE)
        self.assertNotIn("editor:" + pe.CASE, editor.lit_actions())

    def test_delete_clear_and_space_and_no_double_or_leading_space(self):
        editor = pe.PanelEditor(0, "", None)
        editor.activate(pe.SPACE)
        self.assertEqual(editor.text, "")
        press(editor, "ab")
        editor.activate(pe.SPACE)
        editor.activate(pe.SPACE)
        self.assertEqual(editor.text, "Ab ")
        editor.activate(pe.BACK)
        editor.activate(pe.BACK)
        self.assertEqual(editor.text, "A")
        editor.activate(pe.CLEAR)
        self.assertEqual(editor.text, "")
        editor.activate(pe.BACK)                                                     # nothing to delete
        self.assertEqual(editor.text, "")

    def test_a_name_has_a_limit(self):
        editor = pe.PanelEditor(0, "", None)
        press(editor, "a" * pe.NAME_LIMIT)
        self.assertEqual(len(editor.text), pe.NAME_LIMIT)
        step = editor.activate(pe.key_id("b"))
        self.assertEqual(len(editor.text), pe.NAME_LIMIT)
        self.assertIn("at most", step.message)


class ResultTest(unittest.TestCase):
    def test_ok_applies_the_name_and_the_hue_cancel_leaves_everything(self):
        editor = pe.PanelEditor(2, "Tools", None)
        editor.activate(pe.CLEAR)
        press(editor, "box")
        editor.activate(pe.HUE_IDS[3])
        self.assertEqual(editor.result(), ("Box", 0.11))
        step = editor.activate(pe.OK)
        self.assertEqual((step.done, step.applied), (True, True))
        other = pe.PanelEditor(2, "Tools", 0.38)
        other.activate(pe.CLEAR)
        step = other.activate(pe.CANCEL)
        self.assertEqual((step.done, step.applied), (True, False))

    def test_an_empty_name_is_refused_and_the_editor_stays(self):
        editor = pe.PanelEditor(0, "Tools", None)
        editor.activate(pe.CLEAR)
        editor.activate(pe.SPACE)
        step = editor.activate(pe.OK)
        self.assertEqual((step.done, step.message), (False, "A name needs a letter"))

    def test_the_editor_starts_with_the_name_and_the_colour_of_the_panel(self):
        editor = pe.PanelEditor(0, "Tools", 0.68)
        self.assertEqual((editor.text, editor.hue_index, editor.hue), ("Tools", 4, 0.68))
        self.assertEqual(editor.labels()[pe.HUE_IDS[4]], "*")                         # the chosen colour is marked, not lit: it keeps its colour
        self.assertNotIn(pe.HUE_IDS[3], editor.labels())
        auto = pe.PanelEditor(0, "Tools", None)
        self.assertEqual((auto.hue_index, auto.hue), (0, None))
        self.assertEqual(auto.preview_hue(), lay.default_hue("Tools"))              # the colour the name gives
        auto.activate(pe.CLEAR)
        press(auto, "zzz")
        self.assertEqual(auto.preview_hue(), lay.default_hue("Zzz"))
        odd = pe.PanelEditor(0, "Tools", 0.123)                                      # a hue that is no choice is the colour of the name
        self.assertEqual((odd.hue_index, odd.hue), (0, None))

    def test_choosing_auto_takes_the_hue_away(self):
        editor = pe.PanelEditor(0, "Tools", 0.68)
        editor.activate(pe.HUE_IDS[0])
        self.assertEqual(editor.result(), ("Tools", None))


class PreviewTest(unittest.TestCase):
    def test_the_preview_is_the_panel_as_it_will_be_above_the_name_and_colour_panels(self):
        editor = pe.PanelEditor(0, "Tools", 0.68, 4, 3, ["a", None, None, "b"] + [None] * 8)
        page = editor.preview_page()
        self.assertEqual((page.name, page.side, page.row, page.cols, page.rows, page.hue), ("Preview", 0, 2, 4, 3, 0.68))
        self.assertEqual(page.slots[0], "a")
        editor.activate("ed.cols_inc")
        editor.activate("ed.rows_inc")
        grown = editor.preview_page()
        self.assertEqual((grown.cols, grown.rows, len(grown.slots), grown.slots[0], grown.slots[3]), (5, 4, 20, "a", "b"))
        self.assertEqual(grown.slots.index("b"), 3)                                      # "b" kept its row and column: row 0, column 3
        layout = pe.layout(0.68, grown)
        self.assertEqual([p.name for p in layout.pages], list(pe.PAGE_NAMES))
        self.assertEqual(layout.sides(), [[[0], [1, 2], [3]]])                          # the preview is the top row
        self.assertEqual(layout.pages[3].hue, 0.68)

    def test_the_preview_wears_the_typed_name_and_the_colour_of_the_name_on_auto(self):
        editor = pe.PanelEditor(0, "Tools", None, 4, 3, [])
        self.assertEqual(editor.titles(), {"Preview": "Tools"})
        editor.activate(pe.CLEAR)
        self.assertEqual(editor.titles(), {"Preview": "Tools"})                         # nothing typed: the name it had
        press(editor, "box")
        self.assertEqual(editor.titles(), {"Preview": "Box"})
        self.assertEqual(editor.preview_page().hue, lay.default_hue("Box"))

    def test_the_layout_of_the_editor_is_made_again_only_when_the_look_of_the_preview_changes(self):
        editor = pe.PanelEditor(0, "Tools", 0.38, 4, 3, [])
        first = editor.key()
        press(editor, "x")
        self.assertEqual(editor.key(), first)                                           # a letter changes only the title, which is drawn in place
        editor.activate(pe.HUE_IDS[2])
        self.assertNotEqual(editor.key(), first)
        second = editor.key()
        editor.activate("ed.cols_inc")
        self.assertNotEqual(editor.key(), second)


class SizeTest(unittest.TestCase):
    def test_the_size_grows_and_shrinks_by_one_column_or_row_within_the_limits(self):
        editor = pe.PanelEditor(0, "Tools", None, 4, 3, [None] * 12)
        self.assertEqual(editor.size, (4, 3))
        editor.activate("ed.cols_inc")
        editor.activate("ed.rows_inc")
        self.assertEqual(editor.size, (5, 4))
        self.assertEqual(editor.readouts()[pe.READOUT][0], "Name, panel of 5 x 4 buttons")
        editor.activate("ed.cols_dec")
        editor.activate("ed.rows_dec")
        self.assertEqual(editor.size, (4, 3))
        for _ in range(lay.MAX_COLS):
            step = editor.activate("ed.cols_inc")
        self.assertEqual(editor.size[0], lay.MAX_COLS)
        self.assertEqual(step.message, "The panel is as large as it can be")
        for _ in range(lay.MAX_COLS + 2):
            step = editor.activate("ed.cols_dec")
        self.assertEqual(editor.size[0], 1)

    def test_a_size_that_would_cut_off_a_button_is_refused(self):
        slots = ["a", None, None, None, None, None, None, "b", None, None, None, None]        # a in the corner, b at the end of the second row
        editor = pe.PanelEditor(0, "Tools", None, 4, 3, slots)
        step = editor.activate("ed.cols_dec")
        self.assertEqual((editor.size, step.message), ((4, 3), "Buttons stand there: move them away first"))
        editor.activate("ed.rows_dec")                                                       # the last row is empty
        self.assertEqual(editor.size, (4, 2))
        step = editor.activate("ed.rows_dec")
        self.assertEqual((editor.size, step.message), ((4, 2), "Buttons stand there: move them away first"))


if __name__ == "__main__":
    unittest.main()
