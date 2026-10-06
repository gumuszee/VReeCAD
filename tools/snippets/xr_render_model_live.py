# Live check of the interaction render models in the RUNNING, FOCUSED XR session: owner hand (subaction paths), model-space
# location versus the controllers' aim poses, and the per-frame animatable node state (trigger/stick/button animation).
# Hold a trigger / squeeze a grip / tilt a stick while running it to see the node states change.
# Run:  python tools/fc_rpc.py exec -f tools/snippets/xr_render_model_live.py
import ctypes
import traceback

import xr
from xr.exception import check_result as _check
import freecad.BlocksCAD.commonXR as _cxr

_w = _cxr.xr_dock_w.xr_widget if _cxr.xr_dock_w else None


def _call(name, proto, *args):
    fn = ctypes.cast(xr.get_instance_proc_addr(_w.instance, name), proto)
    res = _check(fn(*args))
    if res.is_exception():
        raise res


def _path_str(p):
    try:
        return xr.path_to_string(_w.instance, p)
    except Exception:
        return str(p)


if _w is None or not getattr(_w, "render_model_support", False):
    print("XR viewer not running or render model extensions not enabled")
else:
    _ids = list(xr.enumerate_interaction_render_model_ids_ext(
        _w.session, xr.InteractionRenderModelIdsEnumerateInfoEXT()))
    for _id in _ids:
        try:
            _rm = xr.create_render_model_ext(_w.session, xr.RenderModelCreateInfoEXT(render_model_id=_id))
            _props = xr.RenderModelPropertiesEXT(cache_id=xr.Uuid())
            _call("xrGetRenderModelPropertiesEXT", xr.PFN_xrGetRenderModelPropertiesEXT, _rm, None, ctypes.byref(_props))
            _n = _props.animatable_node_count
            # subaction paths bound to this model (two-call idiom)
            _cnt = ctypes.c_uint32(0)
            _call("xrEnumerateRenderModelSubactionPathsEXT", xr.PFN_xrEnumerateRenderModelSubactionPathsEXT,
                  _rm, None, 0, ctypes.byref(_cnt), None)
            _paths = (xr.Path * max(_cnt.value, 1))()
            _call("xrEnumerateRenderModelSubactionPathsEXT", xr.PFN_xrEnumerateRenderModelSubactionPathsEXT,
                  _rm, None, _cnt.value, ctypes.byref(_cnt), _paths)
            _sub = [_path_str(_paths[i]) for i in range(_cnt.value)]
            # locate the model space against the same space the controllers are located in
            _space = xr.create_render_model_space_ext(_w.session, xr.RenderModelSpaceCreateInfoEXT(render_model=_rm))
            _loc = xr.locate_space(_space, _w.projection_layer.space, _w.frame_state.predicted_display_time)
            _pos = _loc.pose.position
            _ok = bool(_loc.location_flags & xr.SPACE_LOCATION_POSITION_VALID_BIT)
            # animatable node state
            _states = (xr.RenderModelNodeStateEXT * _n)()
            _st = xr.RenderModelStateEXT(node_state_count=_n, node_states=_states)
            _info = xr.RenderModelStateGetInfoEXT(display_time=_w.frame_state.predicted_display_time)
            _call("xrGetRenderModelStateEXT", xr.PFN_xrGetRenderModelStateEXT, _rm, ctypes.byref(_info), ctypes.byref(_st))
            print("session state:", _w.session_state.name, "flags:", int(_loc.location_flags))
            print(f"model {_id}: subaction paths={_sub} located={_ok} pos=({_pos.x:.3f},{_pos.y:.3f},{_pos.z:.3f})")
            for _h in (0, 1):
                _c = _w.xr_con[_h].get_global_transf().translation.getValue()
                print(f"   controller {_h} (0=left,1=right) at ({_c[0]:.3f},{_c[1]:.3f},{_c[2]:.3f})")
            for _i in range(_n):
                _p = _states[_i].node_pose
                print(f"   node {_i}: visible={bool(_states[_i].is_visible)} "
                      f"pos=({_p.position.x:.4f},{_p.position.y:.4f},{_p.position.z:.4f}) "
                      f"rot=({_p.orientation.x:.3f},{_p.orientation.y:.3f},{_p.orientation.z:.3f},{_p.orientation.w:.3f})")
            xr.destroy_space(_space)
            xr.destroy_render_model_ext(_rm)
        except Exception:
            print(ascii(f"model {_id} failed:\n" + traceback.format_exc()[-700:]))
