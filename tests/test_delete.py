import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import edit


class FakeObject:
    def __init__(self, name):
        self.Name, self.Label = name, name.upper()


class FakeDocument:
    def __init__(self, *names):
        self.objects = {n: FakeObject(n) for n in names}
        self.log = []
        self.dependents = {}                  # removing a name takes these along

    def getObject(self, name):
        return self.objects.get(name)

    def openTransaction(self, text):
        self.log.append(("open", text))

    def removeObject(self, name):
        self.log.append(("remove", name))
        for gone in [name] + self.dependents.get(name, []):
            self.objects.pop(gone, None)

    def commitTransaction(self):
        self.log.append(("commit",))

    def recompute(self):
        self.log.append(("recompute",))


class DeleteObjectsTest(unittest.TestCase):
    def test_a_whole_object_goes_in_one_transaction(self):
        doc = FakeDocument("box", "cyl")
        self.assertEqual(edit.delete_objects(doc, [("box", "")]), "Deleted BOX")
        self.assertEqual(doc.log, [("open", "Delete BOX"), ("remove", "box"), ("commit",), ("recompute",)])
        self.assertIsNone(doc.getObject("box"))
        self.assertIsNotNone(doc.getObject("cyl"))

    def test_many_objects_are_one_undo_step_and_named_by_their_count(self):
        doc = FakeDocument("a", "b", "c")
        self.assertEqual(edit.delete_objects(doc, [("a", ""), ("b", ""), ("a", "")]), "Deleted 2 objects")
        self.assertEqual([entry[0] for entry in doc.log], ["open", "remove", "remove", "commit", "recompute"])
        self.assertEqual(doc.log[0], ("open", "Delete 2 objects"))

    def test_selected_faces_edges_and_vertices_are_not_objects_and_stay(self):
        doc = FakeDocument("box")
        self.assertEqual(edit.delete_objects(doc, [("box", "Face3"), ("box", "Edge1")]), "Select a whole object to delete")
        self.assertEqual(doc.log, [])
        self.assertIsNotNone(doc.getObject("box"))

    def test_an_object_selected_with_a_face_of_another_is_deleted_and_the_face_object_stays(self):
        doc = FakeDocument("box", "cyl")
        self.assertEqual(edit.delete_objects(doc, [("box", ""), ("cyl", "Face1")]), "Deleted BOX")
        self.assertIsNotNone(doc.getObject("cyl"))

    def test_an_empty_selection_says_so_and_changes_nothing(self):
        doc = FakeDocument("box")
        self.assertEqual(edit.delete_objects(doc, []), "Nothing selected")
        self.assertEqual(doc.log, [])

    def test_an_object_that_went_with_another_one_is_not_removed_twice(self):
        doc = FakeDocument("body", "pad")
        doc.dependents["body"] = ["pad"]
        edit.delete_objects(doc, [("body", ""), ("pad", "")])
        self.assertEqual([e for e in doc.log if e[0] == "remove"], [("remove", "body")])

    def test_a_name_the_document_does_not_know_is_ignored(self):
        doc = FakeDocument("box")
        self.assertEqual(edit.delete_objects(doc, [("ghost", "")]), "Select a whole object to delete")


if __name__ == "__main__":
    unittest.main()
