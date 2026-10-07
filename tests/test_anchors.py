import unittest

import support  # noqa: F401
from freecad.BlocksCAD.cad import anchors


class FakeDoc:
    def __init__(self, name="d"):
        self.Name = name


class AnchorsCacheTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.calls = []

        def collector(doc, exclude):
            self.calls.append((doc.Name, exclude))
            return [(len(self.calls), 0.0, 0.0)]
        self.cache = anchors.Anchors(clock=lambda: self.now, collector=collector)

    def test_the_list_is_kept_for_a_short_while(self):
        doc = FakeDoc()
        first = self.cache.get(doc)
        self.now = anchors.REFRESH / 2
        self.assertIs(self.cache.get(doc), first)
        self.assertEqual(len(self.calls), 1)
        self.now = anchors.REFRESH * 2
        self.assertIsNot(self.cache.get(doc), first)
        self.assertEqual(len(self.calls), 2)

    def test_another_document_or_exclusion_collects_again(self):
        self.cache.get(FakeDoc("a"))
        self.cache.get(FakeDoc("b"))
        self.cache.get(FakeDoc("b"), ("block",))
        self.assertEqual(self.calls, [("a", ()), ("b", ()), ("b", ("block",))])
