# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""Which objects of a document have changed, so that what is costly to read from many objects is read again only for those that did.

Picking and the guides look at every visible object of a document many times a second. Reading a shape of FreeCAD costs tens of
microseconds, so a document of a few hundred objects would cost more than a frame. `Changes` is a log of the objects that FreeCAD
reported as created, deleted, changed or recomputed (a document observer); `ObjectCache` keeps one value per object, made by a
function, and after each change of the log makes it again for the objects named there only. A frame in which nothing changed costs
one comparison of two numbers. `Changes` itself needs no FreeCAD when it is made with `register=False`; `shared()` is the one that
listens to FreeCAD."""

from bisect import bisect_right

LOG_LIMIT = 20000          # entries kept; a cache that is further behind than the log reaches makes all its values again


class Changes:
    """The log. `counter` grows with every entry; `since(n)` names the objects noted after `n`."""

    def __init__(self, register=True):
        self.counter = 0
        self._log = []                    # (counter, document name, object name or None for a whole document)
        self._lost = 0                    # counters up to this are no longer in the log
        if register:
            import FreeCAD as App
            App.addDocumentObserver(self)

    def note(self, document, name=None):
        """Record that the object `name` of the document `document` (all of it when `name` is None) changed."""
        self.counter += 1
        self._log.append((self.counter, document, name))
        if len(self._log) > 2 * LOG_LIMIT:
            dropped = self._log[:LOG_LIMIT]
            self._log = self._log[LOG_LIMIT:]
            self._lost = dropped[-1][0]

    def since(self, counter):
        """The set of (document name, object name) noted after `counter`, or None when the log no longer reaches back that far."""
        if counter < self._lost:
            return None
        start = bisect_right(self._log, (counter, chr(0x10FFFF), None)) if self._log else 0
        return {(document, name) for _, document, name in self._log[start:]}

    # the slots of a FreeCAD document observer
    def _object(self, obj):
        try:
            self.note(obj.Document.Name, obj.Name)
        except Exception:                 # an object that is being made or deleted may have no document yet
            pass

    def slotCreatedObject(self, obj):
        self._object(obj)

    def slotDeletedObject(self, obj):
        self._object(obj)

    def slotChangedObject(self, obj, prop):
        self._object(obj)

    def slotRecomputedObject(self, obj):
        self._object(obj)

    def slotCreatedDocument(self, doc):
        self.note(doc.Name)

    def slotDeletedDocument(self, doc):
        self.note(doc.Name)


class Everything:
    """A stand-in for `Changes` where FreeCAD cannot be listened to: every call says that everything changed."""

    def __init__(self):
        self._reads = 0

    @property
    def counter(self):
        self._reads += 1                  # never the same twice: a cache is never up to date
        return self._reads

    def since(self, counter):
        return None


_SHARED = None


def shared():
    """The log of the process, listening to FreeCAD (made on the first call); `Everything` when FreeCAD cannot be listened to."""
    global _SHARED
    if _SHARED is None:
        try:
            import FreeCAD as App
            _SHARED = getattr(App, "_vreecad_changes", None)     # a reload of the modules keeps the observer that is registered
            if _SHARED is None:
                _SHARED = App._vreecad_changes = Changes()
        except Exception as error:
            print(f"VReeCAD: cannot watch the documents, reading every object each time: {error}")
            _SHARED = Everything()
    return _SHARED


class ObjectCache:
    """One value per object of a document, `compute(obj)`, kept up to date through a `Changes` log. A value of None is not kept (the
    object has nothing to say). `sync(doc)` returns (values by object name, names made again in this call or None when all were)."""

    def __init__(self, changes, compute):
        self._changes, self._compute = changes, compute
        self._docs = {}                   # document name -> [counter at the last sync, {object name: value}]

    def _all(self, doc):
        values = {}
        for obj in doc.Objects:
            value = self._compute(obj)
            if value is not None:
                values[obj.Name] = value
        return values

    def sync(self, doc):
        entry = self._docs.get(doc.Name)
        now = self._changes.counter
        if entry is not None and entry[0] == now:
            return entry[1], set()
        changed = None if entry is None else self._changes.since(entry[0])
        if changed is None or (doc.Name, None) in changed:
            entry = self._docs[doc.Name] = [self._changes.counter, self._all(doc)]
            return entry[1], None
        touched = {name for document, name in changed if document == doc.Name}
        for name in touched:
            obj = doc.getObject(name)
            value = None if obj is None else self._compute(obj)
            if value is None:
                entry[1].pop(name, None)
            else:
                entry[1][name] = value
        entry[0] = self._changes.counter
        return entry[1], touched

    def get(self, doc):
        return self.sync(doc)[0]
