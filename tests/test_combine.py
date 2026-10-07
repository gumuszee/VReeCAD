import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import combine


class SelectedNamesTest(unittest.TestCase):
    def test_whole_objects_in_selection_order_each_once(self):
        items = [("b", ""), ("a", "Face1"), ("a", ""), ("b", ""), ("c", "")]
        self.assertEqual(combine.selected_names(items), ["b", "a", "c"])

    def test_elements_alone_are_not_objects(self):
        self.assertEqual(combine.selected_names([("a", "Face1"), ("a", "Edge2")]), [])


class PlanTest(unittest.TestCase):
    def test_the_first_object_is_the_base_and_the_others_the_tools(self):
        self.assertEqual(combine.plan("cut", ["a", "b", "c"]), ("a", ["b", "c"]))
        self.assertEqual(combine.plan("fuse", ["a", "b"]), ("a", ["b"]))

    def test_fewer_than_two_objects_say_what_is_missing(self):
        self.assertEqual(combine.plan("fuse", ["a"]), "Select two objects to fuse")
        self.assertEqual(combine.plan("common", []), "Select two objects to common")
        self.assertIn("base first", combine.plan("cut", ["a"]))

    def test_an_unknown_boolean_is_refused(self):
        with self.assertRaises(ValueError):
            combine.plan("xor", ["a", "b"])


class FakeObject:
    def __init__(self, name, type_id):
        self.Name, self.TypeId = name, type_id


class FakeDocument:
    def __init__(self, *names):
        self.objects = {n: FakeObject(n, "Part::Box") for n in names}
        self.log = []

    def getObject(self, name):
        return self.objects.get(name)


class CombineGuardsTest(unittest.TestCase):
    def test_a_boolean_of_one_object_changes_nothing(self):
        doc = FakeDocument("a", "b")
        text, name = combine.combine(doc, "fuse", [("a", "")])
        self.assertEqual((text, name), ("Select two objects to fuse", None))
        self.assertEqual(doc.log, [])

    def test_faces_and_unknown_names_do_not_count(self):
        doc = FakeDocument("a", "b")
        text, name = combine.combine(doc, "cut", [("a", ""), ("b", "Face1"), ("ghost", "")])
        self.assertIsNone(name)
        self.assertIn("base first", text)


if __name__ == "__main__":
    unittest.main()
