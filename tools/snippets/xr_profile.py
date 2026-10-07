# Switch the frame profiler of the running XR viewer on or off (docs/toolbox.md). FreeCAD-side snippet: run it once to start, once to stop.
# While it is on, the Report view gets a summary every few seconds, one line for the frames with the carousel shown and one for the
# frames with it hidden: frames per second, the period of a frame and the milliseconds each part of the frame takes (wait for the
# runtime, input, ui_*, tools, render_left and render_right with the GPU waited for, resolve, mirror). Wear the headset, look at the
# palette and away from it, then run the snippet again; the rows of every frame are in tools/logs/xr_profile.csv.
# Run:  python tools\fc_rpc.py exec -f tools\snippets\xr_profile.py        (the Report view: tools\snippets\report_view.py)
import os

from freecad.BlocksCAD import profiling

_root = os.path.abspath(os.path.join(os.path.dirname(profiling.__file__), "..", ".."))
_path = os.path.join(_root, "tools", "logs", "xr_profile.csv")
os.makedirs(os.path.dirname(_path), exist_ok=True)
if profiling.PROFILER.on:
    profiling.PROFILER.stop()
else:
    import freecad.BlocksCAD.commonXR as _c
    from pivy import coin as _coin
    _w = _c.xr_dock_w
    _x = getattr(_w, "xr_widget", None) or getattr(_w, "xr", None) or _w
    if _w is not None:
        for _o in [_w, _x] + [getattr(_w, a, None) for a in dir(_w) if not a.startswith("_")]:
            if hasattr(_o, "render_target_size") and hasattr(_o, "ui"):
                _x = _o
                break
        _action = _coin.SoGetPrimitiveCountAction()
        _action.apply(_x.ui.root)
        print("profiler: render target", getattr(_x, "render_target_size", "?"), "MSAA", getattr(_x, "sample_count", "?"),
              "| carousel now", _action.getTriangleCount(), "triangles")
    profiling.PROFILER.start(interval=3.0, path=_path)
