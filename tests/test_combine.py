import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import colour, combine, duplicate


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

    @property
    def Objects(self):
        return list(self.objects.values())

    def openTransaction(self, text):
        self.log.append(("open", text))

    def commitTransaction(self):
        self.log.append(("commit",))

    def abortTransaction(self):
        self.log.append(("abort",))


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


class DuplicateTest(unittest.TestCase):
    def test_the_mirror_plane_stands_half_a_gap_beyond_the_box_along_the_axis(self):
        base, normal = duplicate.mirror_plane((0, 0, 0), (10, 20, 30), 0)
        self.assertEqual((base, normal), ((15.0, 10.0, 15.0), (1.0, 0.0, 0.0)))
        base, normal = duplicate.mirror_plane((0, 0, 0), (10, 20, 30), 2, gap=4.0)
        self.assertEqual((base[2], normal), (32.0, (0.0, 0.0, 1.0)))

    def test_the_pattern_interval_is_a_box_length_plus_a_gap(self):
        self.assertEqual(duplicate.array_spacing((5, 0, 0), (25, 1, 1), 0), 30.0)
        self.assertEqual(duplicate.array_spacing((0, 0, 0), (1, 7, 1), 1, gap=3.0), 10.0)


class FakeView:
    def __init__(self, rgb):
        self.ShapeColor = rgb


class FakeColourObject:
    def __init__(self, name, rgb):
        self.Name, self.Label, self.ViewObject = name, name.upper(), FakeView(rgb)
        self.PropertiesList = []

    def addProperty(self, kind, name, group, text):
        self.PropertiesList.append(name)


class ColourTest(unittest.TestCase):
    def test_the_colour_after_the_current_one_and_the_first_for_a_stranger(self):
        self.assertEqual(colour.next_colour(colour.PALETTE[1][1])[0], "Orange")
        self.assertEqual(colour.next_colour(colour.PALETTE[-1][1])[0], "Grey")
        self.assertEqual(colour.next_colour((0.1, 0.2, 0.3))[0], "Grey")

    def test_each_selected_object_goes_on_from_its_own_colour(self):
        doc = FakeDocument()
        doc.objects = {"a": FakeColourObject("a", colour.PALETTE[1][1]), "b": FakeColourObject("b", (0.1, 0.2, 0.3))}
        text = colour.cycle(doc, [("a", ""), ("b", "Face1"), ("a", "Face2")])
        self.assertEqual(doc.objects["a"].ViewObject.ShapeColor, colour.PALETTE[2][1])
        self.assertEqual(doc.objects["b"].ViewObject.ShapeColor, colour.PALETTE[0][1])
        self.assertEqual(text, "2 objects: colours")
        self.assertEqual(doc.log, [("open", "Colour"), ("commit",)])                      # one undo step for all of them

    def test_the_colour_is_a_property_that_undo_can_restore_and_sync_brings_the_view_to_it(self):
        doc = FakeDocument()
        obj = FakeColourObject("a", colour.PALETTE[1][1])
        doc.objects = {"a": obj}
        colour.cycle(doc, [("a", "")])
        self.assertEqual(getattr(obj, colour.PROPERTY), colour.PALETTE[2][1])
        setattr(obj, colour.PROPERTY, colour.PALETTE[1][1])                              # what an undo does to the property
        self.assertEqual(obj.ViewObject.ShapeColor, colour.PALETTE[2][1])
        colour.sync(doc)
        self.assertEqual(obj.ViewObject.ShapeColor, colour.PALETTE[1][1])
        other = FakeColourObject("b", (0.1, 0.2, 0.3))                                   # an object that was never coloured is left alone
        doc.objects["b"] = other
        colour.sync(doc)
        self.assertEqual(other.ViewObject.ShapeColor, (0.1, 0.2, 0.3))

    def test_nothing_selected_says_so(self):
        self.assertEqual(colour.cycle(FakeDocument(), []), "Nothing selected")


if __name__ == "__main__":
    unittest.main()
