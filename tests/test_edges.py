import unittest

import support  # noqa: F401
from freecad.VReeCAD.cad import edges


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


class Surface:
    def __init__(self, **attributes):
        self.__dict__.update(attributes)


def make_surface(kind, **attributes):
    return type(kind, (Surface,), {})(**attributes)


class SurfaceKeyTest(unittest.TestCase):
    def test_a_plane_has_the_same_key_whichever_way_its_axis_points(self):
        up = make_surface("Plane", Axis=(0.0, 0.0, 1.0), Position=(5.0, 5.0, 100.0))
        down = make_surface("Plane", Axis=(0.0, 0.0, -1.0), Position=(0.0, 0.0, 100.0))
        other = make_surface("Plane", Axis=(0.0, 0.0, 1.0), Position=(0.0, 0.0, 90.0))
        self.assertEqual(edges.surface_key(up), edges.surface_key(down))
        self.assertNotEqual(edges.surface_key(up), edges.surface_key(other))

    def test_a_cylinder_is_told_by_its_axis_line_and_radius(self):
        a = make_surface("Cylinder", Axis=(0.0, 0.0, 1.0), Center=(10.0, 0.0, 0.0), Radius=5.0)
        b = make_surface("Cylinder", Axis=(0.0, 0.0, -1.0), Center=(10.0, 0.0, 70.0), Radius=5.0)     # the same axis line, another point on it
        c = make_surface("Cylinder", Axis=(0.0, 0.0, 1.0), Center=(10.0, 0.0, 0.0), Radius=6.0)
        self.assertEqual(edges.surface_key(a), edges.surface_key(b))
        self.assertNotEqual(edges.surface_key(a), edges.surface_key(c))

    def test_a_surface_that_is_not_analytic_has_no_key(self):
        self.assertIsNone(edges.surface_key(make_surface("BSplineSurface")))
        self.assertIsNone(edges.surface_key(make_surface("Plane")))                     # unreadable: no key rather than an error


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
