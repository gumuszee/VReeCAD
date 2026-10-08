import unittest

import support  # noqa: F401
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import panel_editor as pe


def press(editor, text):
    last = None
    for char in text:
        last = editor.activate(pe.SPACE if char == " " else pe.key_id(char))
    return last


class PagesTest(unittest.TestCase):
    def test_the_keyboard_is_three_panels_in_a_row_that_read_across_and_the_name_and_colour_stand_over_it(self):
        layout = pe.layout(0.5)
        self.assertEqual([(p.name, p.side, p.row) for p in layout.pages],
                         [("A to L", 0, 0), ("M to X", 0, 0), ("Y to 9", 0, 0), ("Name", 0, 1), ("Colour", 0, 1)])
        self.assertEqual(layout.sides(), [[[0, 1, 2], [3, 4]]])
        rows = ["".join(face[-1] for k in range(3) for face in layout.pages[k].slots[r * 4:(r + 1) * 4]) for r in range(3)]
        self.assertEqual(rows, [pe.KEY_ROWS[0].lower(), pe.KEY_ROWS[1].lower(), pe.KEY_ROWS[2].lower()])
        self.assertTrue(all(p.hue == 0.5 for p in layout.pages))

    def test_every_face_is_known_once_and_the_readout_has_a_row_of_its_own(self):
        known = pe.faces()
        layout = pe.layout(None)
        placed = [f for p in layout.pages for f in p.slots if f]
        self.assertEqual(sorted(placed), sorted(known))
        self.assertEqual(len(placed), len(set(placed)))
        self.assertEqual(known[pe.READOUT].kind, "readout")
        name = next(p for p in layout.pages if p.name == "Name")
        self.assertEqual(name.slots[:4], [pe.READOUT, None, None, None])
        self.assertTrue(all(len(p.slots) == lay.SLOTS for p in layout.pages))
        self.assertEqual(len(pe.HUES), lay.SLOTS)                                    # Auto and eleven hues fill the Colour panel


class TypingTest(unittest.TestCase):
    def test_the_name_is_the_text_with_a_capital_at_the_start_of_every_word(self):
        editor = pe.PanelEditor(0, "Tools", None)
        editor.activate(pe.CLEAR)
        press(editor, "my parts 2")
        self.assertEqual(editor.text, "My Parts 2")
        self.assertEqual(editor.readouts()[pe.READOUT], ("Name", "My Parts 2|", True))

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
        self.assertIn("editor:" + pe.HUE_IDS[4], editor.lit_actions())
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


if __name__ == "__main__":
    unittest.main()
