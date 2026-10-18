import unittest

import support  # noqa: F401
from freecad.VReeCAD.cad import anchors, changes


class FakeObject:
    def __init__(self, doc, name, value=None):
        self.Name, self.Document, self.value = name, doc, value


class FakeDoc:
    def __init__(self, name="d"):
        self.Name = name
        self.Objects = []

    def add(self, name, value=None):
        obj = FakeObject(self, name, value)
        self.Objects.append(obj)
        return obj

    def getObject(self, name):
        return next((o for o in self.Objects if o.Name == name), None)

    def remove(self, name):
        self.Objects = [o for o in self.Objects if o.Name != name]


class ChangesTest(unittest.TestCase):
    def test_the_log_names_what_changed_after_a_counter(self):
        log = changes.Changes(register=False)
        log.note("d", "a")
        mark = log.counter
        log.note("d", "b")
        log.note("e", "c")
        log.note("d", "b")
        self.assertEqual(log.since(mark), {("d", "b"), ("e", "c")})
        self.assertEqual(log.since(log.counter), set())
        self.assertEqual(log.since(0), {("d", "a"), ("d", "b"), ("e", "c")})

    def test_a_counter_older_than_the_log_gets_none(self):
        log = changes.Changes(register=False)
        for i in range(2 * changes.LOG_LIMIT + 1):
            log.note("d", f"o{i}")
        self.assertIsNone(log.since(0))
        self.assertIsNotNone(log.since(log.counter - 5))
        self.assertEqual(len(log.since(log.counter - 5)), 5)

    def test_the_slots_of_an_observer_note_objects_and_documents(self):
        log = changes.Changes(register=False)
        doc = FakeDoc()
        obj = doc.add("a")
        log.slotChangedObject(obj, "Placement")
        log.slotDeletedDocument(doc)
        log.slotChangedObject(object(), "Shape")                     # an object without a document is ignored
        self.assertEqual(log.since(0), {("d", "a"), ("d", None)})

    def test_everything_is_never_up_to_date(self):
        stand_in = changes.Everything()
        self.assertNotEqual(stand_in.counter, stand_in.counter)
        self.assertIsNone(stand_in.since(0))


class ObjectCacheTest(unittest.TestCase):
    def setUp(self):
        self.log = changes.Changes(register=False)
        self.doc = FakeDoc()
        self.computed = []

        def compute(obj):
            self.computed.append(obj.Name)
            return obj.value
        self.cache = changes.ObjectCache(self.log, compute)

    def test_every_object_is_read_once_and_a_change_reads_only_that_object(self):
        a, b = self.doc.add("a", 1), self.doc.add("b", 2)
        self.assertEqual(self.cache.get(self.doc), {"a": 1, "b": 2})
        self.assertEqual(self.cache.get(self.doc), {"a": 1, "b": 2})
        self.assertEqual(self.computed, ["a", "b"])
        a.value = 10
        self.log.note("d", "a")
        values, touched = self.cache.sync(self.doc)
        self.assertEqual((values, touched), ({"a": 10, "b": 2}, {"a"}))
        self.assertEqual(self.computed, ["a", "b", "a"])

    def test_a_value_of_none_is_not_kept_and_a_deleted_object_goes(self):
        a = self.doc.add("a", 1)
        self.doc.add("b", None)
        self.assertEqual(self.cache.get(self.doc), {"a": 1})
        a.value = None
        self.log.note("d", "a")
        self.assertEqual(self.cache.get(self.doc), {})
        self.doc.add("c", 3)
        self.log.note("d", "c")
        self.doc.remove("c")
        self.log.note("d", "c")
        self.assertEqual(self.cache.get(self.doc), {})

    def test_a_whole_document_note_or_a_lost_log_reads_everything_again(self):
        self.doc.add("a", 1)
        self.cache.get(self.doc)
        self.log.note("d")
        values, touched = self.cache.sync(self.doc)
        self.assertIsNone(touched)
        self.assertEqual(self.computed, ["a", "a"])
        for i in range(2 * changes.LOG_LIMIT + 1):
            self.log.note("other", f"o{i}")
        self.assertIsNone(self.cache.sync(self.doc)[1])

    def test_changes_in_another_document_read_nothing(self):
        self.doc.add("a", 1)
        self.cache.get(self.doc)
        self.log.note("other", "x")
        self.assertEqual(self.cache.sync(self.doc)[1], set())
        self.assertEqual(self.computed, ["a"])


class AnchorsCacheTest(unittest.TestCase):
    def setUp(self):
        self.log = changes.Changes(register=False)
        self.doc = FakeDoc()
        self.reads = []

        def per_object(obj):
            self.reads.append(obj.Name)
            return obj.value
        self.cache = anchors.Anchors(self.log, per_object)

    def test_the_list_is_the_same_until_an_object_that_counts_changes(self):
        self.doc.add("a", [(0.0, 0.0, 0.0)])
        dragged = self.doc.add("b", [(5.0, 0.0, 0.0)])
        first = self.cache.get(self.doc, ("b",))
        self.assertEqual(first, [(0.0, 0.0, 0.0)])
        self.assertIs(self.cache.get(self.doc, ("b",)), first)
        dragged.value = [(9.0, 0.0, 0.0)]
        self.log.note("d", "b")
        self.assertIs(self.cache.get(self.doc, ("b",)), first)         # the excluded object changed: the list does not
        self.doc.getObject("a").value = [(1.0, 0.0, 0.0)]
        self.log.note("d", "a")
        self.assertEqual(self.cache.get(self.doc, ("b",)), [(1.0, 0.0, 0.0)])

    def test_another_exclusion_or_document_combines_again_without_reading_again(self):
        self.doc.add("a", [(0.0, 0.0, 0.0)])
        self.doc.add("b", [(5.0, 0.0, 0.0)])
        self.assertEqual(self.cache.get(self.doc), [(0.0, 0.0, 0.0), (5.0, 0.0, 0.0)])
        self.assertEqual(self.cache.get(self.doc, ("a",)), [(5.0, 0.0, 0.0)])
        self.assertEqual(self.reads, ["a", "b"])

    def test_a_point_that_is_in_two_objects_is_one_anchor_and_the_list_has_a_limit(self):
        self.doc.add("a", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])
        self.doc.add("b", [(0.0, 0.0, 0.00001), (2.0, 0.0, 0.0)])
        self.assertEqual(self.cache.get(self.doc), [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)])
        self.assertEqual(anchors.combine([[(i, 0.0, 0.0) for i in range(10)]], limit=4), [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (3.0, 0.0, 0.0)])


if __name__ == "__main__":
    unittest.main()
