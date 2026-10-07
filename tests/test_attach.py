import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import attach


class PlanTest(unittest.TestCase):
    def test_the_first_face_moves_and_the_second_is_the_target(self):
        items = [("b", "Face2"), ("a", "Face6")]
        self.assertEqual(attach.plan(items), (("b", "Face2"), ("a", "Face6")))

    def test_edges_objects_and_repeats_do_not_count(self):
        items = [("b", ""), ("b", "Edge1"), ("b", "Face2"), ("b", "Face2"), ("a", "Face6"), ("c", "Face1")]
        self.assertEqual(attach.plan(items), (("b", "Face2"), ("a", "Face6")))

    def test_fewer_than_two_faces_say_what_is_missing(self):
        self.assertIn("then the face", attach.plan([("b", "Face2")]))
        self.assertIn("then the face", attach.plan([("b", ""), ("a", "")]))

    def test_two_faces_of_one_object_are_refused(self):
        self.assertEqual(attach.plan([("b", "Face1"), ("b", "Face2")]), "Select faces of two different objects")

    def test_face_numbers(self):
        self.assertEqual(attach.face_number("Face12"), 12)
        self.assertIsNone(attach.face_number("Edge1"))
        self.assertIsNone(attach.face_number("Facet"))


class FakeDocument:
    def __init__(self):
        self.log = []

    def getObject(self, name):
        return None

    def openTransaction(self, text):
        self.log.append(text)


class GuardsTest(unittest.TestCase):
    def test_nothing_to_attach_changes_nothing(self):
        doc = FakeDocument()
        text, name = attach.attach(doc, [("a", "Face1")])
        self.assertIsNone(name)
        self.assertEqual(attach.detach(doc, []), ("Nothing selected", []))
        self.assertEqual(attach.detach(doc, [("a", "")]), ("Nothing selected is attached", []))
        self.assertEqual(doc.log, [])
