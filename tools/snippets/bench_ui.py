# Time the carousel: the Python side of one UI frame and the Coin render of the scene, with the carousel shown and hidden.
# The scene is rendered through one persistent root and one `SoOffscreenRenderer`, so render caches that survive between frames
# count as they do in the headset. Numbers are milliseconds per frame (mean of FRAMES frames); they compare variants on one
# machine, they are not headset frame times.
# Run:  & "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\run_headless_render.py tools\snippets\bench_ui.py
import time

import freecad.BlocksCAD.backends.sim as _sim
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


def _both():
    _s.frame(0.014)
    _render()


_render()
print("pinned", _s.ui.ring.pinned, "carousel visible: fade", round(_s.ui.ring.fade, 2), "panels", len(_s.ui.ring.poses))
print("python frame      %.2f ms" % _mean_ms(_ui))
print("render only       %.2f ms" % _mean_ms(_render))
print("frame + render    %.2f ms" % _mean_ms(_both))
if globals().get("PROFILE"):
    import cProfile
    import pstats
    prof = cProfile.Profile()
    prof.enable()
    for _ in range(FRAMES):
        _ui()
    prof.disable()
    pstats.Stats(prof).sort_stats("cumulative").print_stats(22)

_s.input.set_head(position=_head, look_at_point=(3.0, 1.6, 0.0))     # looking away: the carousel fades out
for _ in range(60):
    _s.frame(0.014)
print("carousel hidden: fade", round(_s.ui.ring.fade, 2))
print("python frame      %.2f ms" % _mean_ms(_ui))
print("render only       %.2f ms" % _mean_ms(_render))
print("frame + render    %.2f ms" % _mean_ms(_both))
root.unref()
_s.close()
