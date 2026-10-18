import unittest

import support  # noqa: F401
from freecad.VReeCAD.cad import joints


class FakeObject:
    def __init__(self, parents=()):
        self.Parents = list(parents)


class FakeDocument:
    def __init__(self):
        self.log = []

    def getObject(self, name):
        return None

    def openTransaction(self, text):
        self.log.append(text)


class JointsTest(unittest.TestCase):
    def test_the_kinds_are_the_assembly_joint_types(self):
        self.assertEqual(joints.KINDS, ("Fixed", "Revolute", "Slider", "Ball"))

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            joints.make(FakeDocument(), [("a", "Face1"), ("b", "Face1")], "Gears")

    def test_a_joint_needs_two_faces_of_two_objects(self):
        doc = FakeDocument()
        self.assertIn("then the face", joints.make(doc, [("a", "Face1")], "Fixed")[0])
        self.assertEqual(joints.make(doc, [("a", "Face1"), ("a", "Face2")], "Fixed"),
                         ("Select faces of two different objects", None))
        self.assertEqual(doc.log, [])

    def test_nothing_to_unjoin_changes_nothing(self):
        doc = FakeDocument()
        self.assertEqual(joints.remove(doc, []), ("Nothing selected", 0))
        self.assertEqual(joints.remove(doc, [("a", "")]), ("Nothing selected is jointed", 0))
        self.assertEqual(doc.log, [])

    def test_an_object_outside_an_assembly_has_none(self):
        self.assertIsNone(joints.assembly_of(FakeObject()))
        self.assertTrue(joints.solve(FakeObject()))
