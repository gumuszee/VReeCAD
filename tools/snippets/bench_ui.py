# Time the carousel: the Python side of one UI frame and the Coin render of the scene, with the carousel shown and hidden, with and
# without the value panels. The scene is rendered through one persistent root and one `SoOffscreenRenderer`, so render caches that
# survive between frames count as they do in the headset. Numbers are milliseconds per frame (mean of FRAMES frames); they compare
# variants on one machine, they are not headset frame times. The triangle, line and text counts of the carousel are exact.
# Set the environment variable BENCH_PROFILE=1 to print the cProfile of the Python frame.
# Run:  & "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\run_headless_render.py tools\snippets\bench_ui.py
import os
import time

import FreeCAD as _App
import freecad.BlocksCAD.backends.sim as _sim
import freecad.BlocksCAD.cad.primitives as _pm
import freecad.BlocksCAD.cad.picking as _pk
from pivy import coin as _coin

FRAMES = 60
SIZE = (1200, 1200)


def _scene():
    root = _coin.SoSeparator()
    root.addChild(_coin.SoLightModel())
    cube = _coin.SoCube()
    cube.width = cube.height = cube.depth = 300
    root.addChild(cube)
    return root


def _mean_ms(fn, count=FRAMES):
    start = time.perf_counter()
    for _ in range(count):
        fn()
    return (time.perf_counter() - start) * 1000.0 / count


def _counts(node):
    """(triangles, lines, points) the node draws, and the number of nodes under it."""
    action = _coin.SoGetPrimitiveCountAction()
    action.apply(node)
    nodes = _coin.SoSearchAction()
    nodes.setInterest(_coin.SoSearchAction.ALL)
    nodes.setSearchingAll(True)
    nodes.setType(_coin.SoNode.getClassTypeId())
    nodes.apply(node)
    return action.getTriangleCount(), action.getLineCount(), action.getPointCount(), nodes.getPaths().getLength()


_s = _sim.SimSession(_scene())
_head, _ctrl = (0.0, 1.6, 0.0), (-0.12, 1.25, -0.44)
_s.input.set_head(position=_head, look_at_point=_ctrl)
_s.input.set_hand(0, position=_ctrl, point_at=(0.0, 1.3, -1.0))
_s.input.set_hand(1, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
for _ in range(30):
    _s.frame(0.014)

cam = _coin.SoPerspectiveCamera()
head = _s.input.head
cam.position.setValue(*head.position)
cam.orientation.setValue(*head.orientation)
cam.heightAngle, cam.nearDistance, cam.farDistance, cam.aspectRatio = 1.0, 0.02, 200.0, 1.0
root = _coin.SoSeparator()
root.ref()
root.addChild(cam)
root.addChild(_s.scene)
renderer = _coin.SoOffscreenRenderer(_coin.SbViewportRegion(*SIZE))


def _render():
    if not renderer.render(root):
        raise RuntimeError("render failed")
    renderer.getBuffer()     # reads the pixels back, which waits for the GPU to finish


def _ui():
    _s.frame(0.014)


def _ui_only():
    """The user interface alone: no tool update, no animation of the controller models."""
    frame = _s.input.frame(0.014)
    _s.last_frame = frame
    _s.ui.update(frame)


def _both():
    _s.frame(0.014)
    _render()


def _report(title):
    print(title, "| fade", round(_s.ui.ring.fade, 2), "panels", len(_s.ui.ring.poses))
    print("  carousel: %d triangles, %d lines, %d points, %d nodes" % _counts(_s.ui.view.root))
    print("  ui update only    %.2f ms" % _mean_ms(_ui_only))
    print("  python frame      %.2f ms" % _mean_ms(_ui))
    print("  render only       %.2f ms" % _mean_ms(_render))
    print("  frame + render    %.2f ms" % _mean_ms(_both))


def _profile():
    import cProfile
    import pstats
    prof = cProfile.Profile()
    prof.enable()
    for _ in range(FRAMES):
        _ui()
    prof.disable()
    pstats.Stats(prof).sort_stats("tottime").print_stats(18)


_render()
_report("default panels")
if os.environ.get("BENCH_PROFILE"):
    _profile()

_temp = _App.newDocument("BlocksCADBench")
_pm.create(_temp, "Box", (200.0, -60.0, 0.0), (120.0, 120.0, 80.0))
_s.tool_manager.ctx.services["document"] = _s._document
_pk.set_selection(_temp, [(_temp.Objects[0].Name, "")])
_s.input.set_hand(1, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
for _ in range(30):
    _s.frame(0.014)
_render()
_report("with the value panels (%s)" % ("open" if _s.ui.module.is_open else "NOT open"))
if os.environ.get("BENCH_PROFILE"):
    _profile()

_s.input.set_head(position=_head, look_at_point=(3.0, 1.6, 0.0))     # looking away: the carousel fades out
for _ in range(60):
    _s.frame(0.014)
_report("carousel hidden")
_App.closeDocument(_temp.Name)
root.unref()
_s.close()
