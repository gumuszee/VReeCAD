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
"""Runtime-provided controller models (XR_EXT_interaction_render_model + XR_EXT_render_model), see docs/controller-models.md.

`RuntimeModels` enumerates the models the runtime holds for the controllers, downloads each glTF asset once (cached on disk by
UUID, never bundled), and per frame reports each model's pose in a base space plus the animatable node states.
pyopenxr 1.1.6302 wrappers for several of these calls do not work; the raw functions are called through their prototypes.
"""

import ctypes
import os
import uuid as uuid_mod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import xr
from xr.exception import check_result

REQUIRED_EXTENSIONS = ("XR_EXT_uuid", "XR_EXT_render_model", "XR_EXT_interaction_render_model")
HAND_PATHS = {"left": "/user/hand/left", "right": "/user/hand/right"}


def _int(handle):
    return int(getattr(handle, "value", handle))


def cache_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "VReeCAD", "cache", "rendermodels")


@dataclass
class NodeState:
    name: str
    visible: bool
    position: tuple
    orientation: tuple


@dataclass
class RuntimeModel:
    hand: str
    cache_id: str
    handle: object
    space: object
    glb: bytes
    node_names: List[str] = field(default_factory=list)


class RuntimeModels:
    def __init__(self, instance, session):
        self.instance = instance
        self.session = session
        self.models: Dict[str, RuntimeModel] = {}   # hand -> model
        # path handles may be ctypes objects (unhashable), so they are compared by their integer value
        self._hand_paths = {side: _int(xr.string_to_path(instance, path)) for side, path in HAND_PATHS.items()}
        self._glb_by_uuid: Dict[str, bytes] = {}

    # raw calls
    def _fn(self, name, proto):
        return ctypes.cast(xr.get_instance_proc_addr(self.instance, name), proto)

    @staticmethod
    def _ok(result):
        res = check_result(result)
        if res.is_exception():
            raise res

    def _properties(self, handle):
        props = xr.RenderModelPropertiesEXT(cache_id=xr.Uuid())  # pyopenxr's wrapper passes an int here and raises
        self._ok(self._fn("xrGetRenderModelPropertiesEXT", xr.PFN_xrGetRenderModelPropertiesEXT)(
            handle, None, ctypes.byref(props)))
        return props

    def _subaction_paths(self, handle):
        fn = self._fn("xrEnumerateRenderModelSubactionPathsEXT", xr.PFN_xrEnumerateRenderModelSubactionPathsEXT)
        count = ctypes.c_uint32(0)
        self._ok(fn(handle, None, 0, ctypes.byref(count), None))
        paths = (xr.Path * max(count.value, 1))()
        self._ok(fn(handle, None, count.value, ctypes.byref(count), paths))
        return [paths[i] for i in range(count.value)]

    def _download(self, props):
        """GLB bytes and animatable node names of the asset behind `props.cache_id` (disk cache first)."""
        uid = str(uuid_mod.UUID(bytes=bytes(props.cache_id.data)))
        asset = xr.create_render_model_asset_ext(self.session, xr.RenderModelAssetCreateInfoEXT(cache_id=props.cache_id))
        try:
            count = props.animatable_node_count
            nodes = (xr.RenderModelAssetNodePropertiesEXT * count)()
            asset_props = xr.RenderModelAssetPropertiesEXT(node_property_count=count, node_properties=nodes)
            self._ok(self._fn("xrGetRenderModelAssetPropertiesEXT", xr.PFN_xrGetRenderModelAssetPropertiesEXT)(
                asset, None, ctypes.byref(asset_props)))
            names = [bytes(n.unique_name).split(b"\x00")[0].decode("utf-8", "replace") for n in nodes]

            path = os.path.join(cache_dir(), uid + ".glb")
            glb = self._glb_by_uuid.get(uid)
            if glb is None and os.path.isfile(path):
                with open(path, "rb") as f:
                    glb = f.read()
            if glb is None:
                data_fn = self._fn("xrGetRenderModelAssetDataEXT", xr.PFN_xrGetRenderModelAssetDataEXT)
                data = xr.RenderModelAssetDataEXT()
                self._ok(data_fn(asset, None, ctypes.byref(data)))      # capacity query
                buf = (ctypes.c_uint8 * data.buffer_count_output)()
                data = xr.RenderModelAssetDataEXT(buffer_capacity_input=len(buf), buffer=buf)
                self._ok(data_fn(asset, None, ctypes.byref(data)))
                glb = bytes(buf)[: data.buffer_count_output]
                os.makedirs(cache_dir(), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(glb)
            self._glb_by_uuid[uid] = glb
            return uid, glb, names
        finally:
            xr.destroy_render_model_asset_ext(asset)

    # public
    def refresh(self):
        """(Re)enumerate the controller models; call after the first successful xrSyncActions and on
        XrEventDataInteractionRenderModelsChangedEXT. Returns the hands that have a model."""
        self.destroy()
        ids = list(xr.enumerate_interaction_render_model_ids_ext(
            self.session, xr.InteractionRenderModelIdsEnumerateInfoEXT()))
        by_path = {value: side for side, value in self._hand_paths.items()}
        for model_id in ids:
            handle = xr.create_render_model_ext(self.session, xr.RenderModelCreateInfoEXT(render_model_id=model_id))
            try:
                hand = next((by_path[_int(p)] for p in self._subaction_paths(handle) if _int(p) in by_path), None)
                if hand is None or hand in self.models:
                    xr.destroy_render_model_ext(handle)
                    continue
                props = self._properties(handle)
                uid, glb, names = self._download(props)
                space = xr.create_render_model_space_ext(
                    self.session, xr.RenderModelSpaceCreateInfoEXT(render_model=handle))
                self.models[hand] = RuntimeModel(hand, uid, handle, space, glb, names)
            except Exception:
                xr.destroy_render_model_ext(handle)
                raise
        return sorted(self.models)

    def available_count(self):
        """Number of controller models the runtime offers now; differs from `len(models)` when a controller appeared or went away."""
        return len(list(xr.enumerate_interaction_render_model_ids_ext(self.session, xr.InteractionRenderModelIdsEnumerateInfoEXT())))

    def locate(self, hand, base_space, time):
        """Pose of the model in `base_space` as (position, orientation), or None when it is not tracked
        (spaces are locatable only while the session is FOCUSED)."""
        model = self.models.get(hand)
        if model is None:
            return None
        loc = xr.locate_space(model.space, base_space, time)
        need = xr.SPACE_LOCATION_POSITION_VALID_BIT | xr.SPACE_LOCATION_ORIENTATION_VALID_BIT
        if (loc.location_flags & need) != need:
            return None
        p, q = loc.pose.position, loc.pose.orientation
        return (p.x, p.y, p.z), (q.x, q.y, q.z, q.w)

    def node_states(self, hand, time) -> Optional[List[NodeState]]:
        model = self.models.get(hand)
        if model is None or not model.node_names:
            return None
        n = len(model.node_names)
        states = (xr.RenderModelNodeStateEXT * n)()
        out = xr.RenderModelStateEXT(node_state_count=n, node_states=states)
        info = xr.RenderModelStateGetInfoEXT(display_time=time)
        self._ok(self._fn("xrGetRenderModelStateEXT", xr.PFN_xrGetRenderModelStateEXT)(
            model.handle, ctypes.byref(info), ctypes.byref(out)))
        result = []
        for name, st in zip(model.node_names, states):
            p, q = st.node_pose.position, st.node_pose.orientation
            result.append(NodeState(name, bool(st.is_visible), (p.x, p.y, p.z), (q.x, q.y, q.z, q.w)))
        return result

    def destroy(self):
        for model in self.models.values():
            for destroy, obj in ((xr.destroy_space, model.space), (xr.destroy_render_model_ext, model.handle)):
                try:
                    destroy(obj)
                except Exception:
                    pass
        self.models.clear()
