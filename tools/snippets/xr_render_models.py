# Probe the runtime-provided controller models (XR_EXT_interaction_render_model + XR_EXT_render_model) of the RUNNING XR session.
# Prerequisites: XR viewer started; the session must have run at least one successful xrSyncActions (headset worn -> FOCUSED).
# Run:  python tools/fc_rpc.py exec -f tools/snippets/xr_render_models.py
# Output per model: cache id, animatable node names, GLB size, glTF summary (meshes, materials, textures, extensions).
# GLB assets are written to %LOCALAPPDATA%\VReeCAD\cache\rendermodels\<uuid>.glb (local cache; never committed or bundled).
import ctypes
import json
import os
import struct
import traceback
import uuid as _uuid

import xr
from xr.exception import check_result as _check
import freecad.VReeCAD.commonXR as _cxr

_w = _cxr.xr_dock_w.xr_widget if _cxr.xr_dock_w else None
if _w is None or not getattr(_w, "render_model_support", False):
    print("XR viewer not running or render model extensions not enabled")
else:
    _cache = os.path.join(os.environ.get("LOCALAPPDATA", "."), "VReeCAD", "cache", "rendermodels")
    os.makedirs(_cache, exist_ok=True)
    _ids = list(xr.enumerate_interaction_render_model_ids_ext(
        _w.session, xr.InteractionRenderModelIdsEnumerateInfoEXT()))
    print("interaction render model ids:", _ids)
    _hand_paths = {"left": xr.string_to_path(_w.instance, "/user/hand/left"),
                   "right": xr.string_to_path(_w.instance, "/user/hand/right")}
    for _id in _ids:
        _step = "create model"
        try:
            _rm = xr.create_render_model_ext(_w.session, xr.RenderModelCreateInfoEXT(render_model_id=_id))
            _step = "properties"
            # pyopenxr 1.1.6302: get_render_model_properties_ext() builds its struct with cache_id=0 and raises TypeError
            _props = xr.RenderModelPropertiesEXT(cache_id=xr.Uuid())
            _fn = ctypes.cast(xr.get_instance_proc_addr(_rm.instance, "xrGetRenderModelPropertiesEXT"),
                              xr.PFN_xrGetRenderModelPropertiesEXT)
            _res = _check(_fn(_rm, None, ctypes.byref(_props)))
            if _res.is_exception():
                raise _res
            _uid = _uuid.UUID(bytes=bytes(_props.cache_id.data))
            _step = "create asset"
            _asset = xr.create_render_model_asset_ext(
                _w.session, xr.RenderModelAssetCreateInfoEXT(cache_id=_props.cache_id))
            _step = "asset data"
            # two-call idiom done by hand: pyopenxr's wrapper only performs the capacity query
            _dfn = ctypes.cast(xr.get_instance_proc_addr(_rm.instance, "xrGetRenderModelAssetDataEXT"),
                               xr.PFN_xrGetRenderModelAssetDataEXT)
            _data = xr.RenderModelAssetDataEXT()
            _r = _check(_dfn(_asset, None, ctypes.byref(_data)))
            if _r.is_exception():
                raise _r
            _buf = (ctypes.c_uint8 * _data.buffer_count_output)()
            _data = xr.RenderModelAssetDataEXT(buffer_capacity_input=len(_buf), buffer=_buf)
            _r = _check(_dfn(_asset, None, ctypes.byref(_data)))
            if _r.is_exception():
                raise _r
            _glb = bytes(_buf)[: _data.buffer_count_output]
            _step = "asset node names"
            # The spec requires the app to preallocate nodeProperties[animatableNodeCount]; the pyopenxr wrapper passes an empty
            # array and gets VALIDATION_FAILURE, so call the function directly.
            _count = _props.animatable_node_count
            _arr = (xr.RenderModelAssetNodePropertiesEXT * _count)()
            _ap = xr.RenderModelAssetPropertiesEXT(node_property_count=_count, node_properties=_arr)
            _afn = ctypes.cast(xr.get_instance_proc_addr(_rm.instance, "xrGetRenderModelAssetPropertiesEXT"),
                               xr.PFN_xrGetRenderModelAssetPropertiesEXT)
            _res = _check(_afn(_asset, None, ctypes.byref(_ap)))
            if _res.is_exception():
                raise _res
            _names = [bytes(n.unique_name).split(b"\x00")[0].decode() for n in _arr]
            xr.destroy_render_model_asset_ext(_asset)
            _path = os.path.join(_cache, str(_uid) + ".glb")
            with open(_path, "wb") as _f:
                _f.write(_glb)
            _step = "owner hand"
            _owner = "?"
            try:
                _top = xr.get_render_model_pose_top_level_user_path_ext(
                    _rm, xr.InteractionRenderModelTopLevelUserPathGetInfoEXT(
                        top_level_user_paths=list(_hand_paths.values())))
                _owner = ([k for k, v in _hand_paths.items() if v == _top] or ["none"])[0]
            except Exception as _e:
                _owner = f"error {_e!r}"
            print(f"\nmodel id={_id} owner={_owner} uuid={_uid} animatable_nodes={_props.animatable_node_count} glb={len(_glb)} bytes")
            print("  cached:", _path)
            print("  node names:", ascii(_names))
            _magic, _ver, _len = struct.unpack_from("<4sII", _glb, 0)
            _jlen, _jtype = struct.unpack_from("<I4s", _glb, 12)
            _j = json.loads(_glb[20:20 + _jlen])
            print(f"  glb magic={_magic} v{_ver} gltf: meshes={len(_j.get('meshes', []))} nodes={len(_j.get('nodes', []))} "
                  f"materials={len(_j.get('materials', []))} textures={len(_j.get('textures', []))} images={len(_j.get('images', []))}")
            print("  extensionsUsed:", ascii(_j.get("extensionsUsed")), "required:", ascii(_j.get("extensionsRequired")))
            print("  asset:", ascii(_j.get("asset")))
            xr.destroy_render_model_ext(_rm)
        except Exception:
            print(f"model id={_id} FAILED at step '{_step}':\n" + traceback.format_exc()[-700:])
