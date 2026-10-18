# Time what the tools ask of a document that has many objects: `cad.picking.pick` (every frame while a tool hovers) and the anchors of
# the guides (`cad.anchors.Anchors`, asked for every frame while a shape is dragged), both kept per object through the change log
# `cad.changes`. "cold" is the first call (every object is read), "warm" a call after which nothing changed, "one changed" a call
# after one object was moved (the case of a grab: one object is read again). `collect` reads every object each time (what the tools
# did before the caches). Numbers are milliseconds per call for documents of COUNTS boxes laid out on a grid; they compare variants on
# one machine, they are not headset frame times.
# Run:  & "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\run_headless_render.py tools\snippets\bench_pick.py
import time

import FreeCAD as _App
import freecad.VReeCAD.cad.anchors as _anchors
import freecad.VReeCAD.cad.picking as _pk
import freecad.VReeCAD.cad.primitives as _pm

COUNTS = (50, 200, 800)
CALLS = 30


def _ms(fn, count=1):
    start = time.perf_counter()
    for _ in range(count):
        fn()
    return (time.perf_counter() - start) * 1000.0 / count


for _count in COUNTS:
    _doc = _App.newDocument(f"BenchPick{_count}")
    side = int(_count ** 0.5) + 1
    _boxes = [_pm.create(_doc, "Box", ((_i % side) * 150.0, (_i // side) * 150.0, 0.0), (100.0, 100.0, 100.0)) for _i in range(_count)]
    _doc.recompute()
    far = (-500.0, -500.0, -500.0)                                  # touches nothing: the common case while the hand moves
    near = (50.0, 50.0, 96.0)                                       # the top face of the first box
    cold = _ms(lambda: _pk.pick(_doc, far, 1000.0))
    warm = _ms(lambda: _pk.pick(_doc, far, 1000.0), CALLS)
    touching = _ms(lambda: _pk.pick(_doc, near, 1000.0), CALLS)

    def _moved_pick():
        base = _boxes[-1].Placement.copy()
        base.Base.x += 1.0
        _boxes[-1].Placement = base
        _pk.pick(_doc, far, 1000.0)
    one_changed = _ms(_moved_pick, CALLS)
    _cache = _anchors.Anchors()
    a_cold = _ms(lambda: _cache.get(_doc, ()))
    a_warm = _ms(lambda: _cache.get(_doc, ()), CALLS)

    def _moved_anchors():
        base = _boxes[-1].Placement.copy()
        base.Base.x += 1.0
        _boxes[-1].Placement = base
        _cache.get(_doc, (_boxes[-1].Name,))
    a_dragged = _ms(_moved_anchors, CALLS)                          # the dragged object is excluded: nothing is combined again

    def _other_anchors():
        base = _boxes[0].Placement.copy()
        base.Base.x += 1.0
        _boxes[0].Placement = base
        _cache.get(_doc, (_boxes[-1].Name,))
    a_other = _ms(_other_anchors, CALLS)                            # another object changed: its points are read and the list is combined again
    collect = _ms(lambda: _anchors.collect(_doc), 3)
    print(f"{_count} boxes: pick cold {cold:.1f}, warm {warm:.2f}, touching {touching:.2f}, one changed {one_changed:.2f} ms;",
          f"anchors cold {a_cold:.1f}, warm {a_warm:.3f}, dragged excluded {a_dragged:.2f}, another changed {a_other:.2f}, uncached collect {collect:.1f} ms")
    _App.closeDocument(_doc.Name)
