# Stand-in for FreeCAD's selection (FreeCADGui.Selection) in a headless FreeCAD process, where the GUI is not running. Dev tooling.
# Used by tools/run_headless_tests.py and tools/run_headless_render.py:  import headless_gui; headless_gui.install()
import FreeCADGui


class _Selected:
    def __init__(self, object_name, subs):
        self.ObjectName, self.SubElementNames = object_name, tuple(subs)


class _Selection:
    """Enough of FreeCADGui.Selection for the tools: whole objects and sub-elements per document."""

    def __init__(self):
        self.items = []

    def clearSelection(self, *args):
        self.items = []

    def addSelection(self, doc, name, sub=""):
        self.items.append((doc, name, sub))

    def getSelectionEx(self, doc=None):
        names = []
        for d, name, sub in self.items:
            if doc is not None and d != doc:
                continue
            if name not in [n for n, _ in names]:
                names.append((name, []))
            if sub:
                dict(names)[name].append(sub)
        return [_Selected(name, subs) for name, subs in names]


def install():
    """Put the stand-in on FreeCADGui when it has no selection of its own."""
    if not hasattr(FreeCADGui, "Selection"):
        FreeCADGui.Selection = _Selection()
