import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import edges


class EdgeSelectionTest(unittest.TestCase):
    def test_edges_are_grouped_by_object_in_selection_order_each_once(self):
        items = [("b", "Edge2"), ("a", "Edge1"), ("b", "Edge5"), ("b", "Edge2")]
        self.assertEqual(edges.edge_selection(items), [("b", [2, 5]), ("a", [1])])

    def test_whole_objects_faces_and_vertices_do_not_count(self):
        items = [("a", ""), ("a", "Face3"), ("a", "Vertex1"), ("a", "Edgex")]
        self.assertEqual(edges.edge_selection(items), [])

    def test_the_edge_number_is_one_based_as_freecad_counts(self):
        self.assertEqual(edges.edge_index("Edge12"), 12)
        self.assertIsNone(edges.edge_index("Face1"))


class EdgeRowsTest(unittest.TestCase):
    def test_every_edge_gets_the_size_at_both_ends(self):
        self.assertEqual(edges.edge_rows([3, 7], 2.5), [(3, 2.5, 2.5), (7, 2.5, 2.5)])


class FakeDocument:
    def __init__(self):
        self.log = []

    def getObject(self, name):
        return None

    def openTransaction(self, text):
        self.log.append(text)


class GuardsTest(unittest.TestCase):
    def test_nothing_selected_or_no_edges_changes_nothing(self):
        doc = FakeDocument()
        self.assertEqual(edges.make(doc, [], "fillet"), ("Nothing selected", []))
        self.assertEqual(edges.make(doc, [("a", "")], "chamfer"), ("Select edges first", []))
        self.assertEqual(doc.log, [])

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            edges.make(FakeDocument(), [("a", "Edge1")], "bevel")
