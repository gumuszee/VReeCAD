# Print the VR addon's live OpenXR state (run via fc_rpc.py exec -f). Needs the XR viewer started.
import freecad.VReeCAD.commonXR as _c
_w = _c.xr_dock_w
if _w is None:
    print("XR viewer not started")
else:
    _x = getattr(_w, "xr_widget", None) or getattr(_w, "xr", None) or _w
    for _o in [_w] + [getattr(_w, a) for a in dir(_w) if not a.startswith("_") and hasattr(getattr(_w, a, None), "session_state")]:
        print(type(_o).__name__, "session_state =", __import__("xr").SessionState(getattr(_o, "session_state")).name if isinstance(getattr(_o, "session_state", None), int) or hasattr(getattr(_o, "session_state", None), "name") else "?",
              "| api =", getattr(_o, "api_version", "?"))
