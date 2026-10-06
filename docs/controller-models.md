# Controller models

BlocksCAD renders the controller models that the **OpenXR runtime** provides. No controller meshes or textures are bundled
with the addon, so every user sees the exact devices in use (Steam Frame, Quest Touch, Index, ...), with animated parts, and the
repository stays free of third-party assets.

## Mechanism

Extensions: `XR_EXT_interaction_render_model` (which models exist and who holds them) on top of `XR_EXT_render_model`
(asset download and animation). On an OpenXR 1.0 instance `XR_EXT_uuid` is also required. All three are requested when the
runtime offers them (`commonXR.prepare_xr_instance`, flag `render_model_support`).
`XR_MSFT_controller_model` is superseded by these extensions and is not used.

Call sequence per session (functions are available in pyopenxr as `xr.*_ext`):

1. `xrSyncActions` must have succeeded once (session `FOCUSED`): the runtime enumerates no models before that. The event
   `XrEventDataInteractionRenderModelsChangedEXT` signals that the list must be enumerated again.
2. `xrEnumerateInteractionRenderModelIdsEXT` -> model ids (no meaning in the order).
3. `xrCreateRenderModelEXT(id)` with an empty glTF extension list (the runtime must then deliver a plain glTF 2.0 asset).
4. `xrGetRenderModelPropertiesEXT` -> `cacheId` (UUID) and `animatableNodeCount`.
5. `xrEnumerateRenderModelSubactionPathsEXT` -> which hand (`/user/hand/left|right`) the model belongs to.
6. `xrCreateRenderModelAssetEXT(cacheId)`, `xrGetRenderModelAssetDataEXT` (two-call idiom) -> GLB bytes,
   `xrGetRenderModelAssetPropertiesEXT` -> names of the animatable nodes (array preallocated to `animatableNodeCount`).
7. `xrCreateRenderModelSpaceEXT`; each frame `xrLocateSpace` (render only if position and orientation are tracked; the space
   is locatable only while the session is `FOCUSED`) and `xrGetRenderModelStateEXT` (pose + visibility per animatable node).

The model space origin is the glTF origin and has no fixed relation to the grip or aim pose; the models are placed by their own
space and the tool tip comes from the aim pose.

## Measured on SteamVR 2.17.10 with Steam Frame controllers

| Property | Value |
|---|---|
| Models enumerated | 2: `frame_controller_left` (subaction path `/user/hand/left`) and `frame_controller_right` (`/user/hand/right`) |
| Asset size | about 2.0 MB each, GLB (glTF 2.0), generator `SteamVR@2.17.10` |
| glTF extensions | none used, none required; no samplers; one scene; node transforms are identity |
| Content | one mesh and one PNG base-colour texture per animatable node; attributes POSITION, NORMAL, TEXCOORD_0; uint16 triangle indices; PBR metallic factor 0, roughness 0.5; units are metres |
| Left animatable nodes (9) | `body bumper button_grip button_system button_view dpad status thumbstick trigger` |
| Right animatable nodes (12) | `body bumper button_a button_b button_grip button_menu button_system button_x button_y status thumbstick trigger` |
| Animation | node poses change with input (the left trigger node reported a rotation while the trigger was pulled); `status` is invisible by default |
| Location | both spaces are located (position and orientation valid and tracked) near the controllers while `FOCUSED`; unlocatable while `VISIBLE` |

Probes: `tools/snippets/xr_render_models.py` (download and summarise) and `tools/snippets/xr_render_model_live.py` (hands, location, node state).
The assets are cached as `%LOCALAPPDATA%\BlocksCAD\cache\rendermodels\<uuid>.glb`.

## Loading into Coin3D

Coin has no glTF loader. `gltf.py` parses the GLB (JSON chunk + binary chunk, `struct`/`json`/`numpy`) and `render/gltf_coin.py` builds, per glTF node,
`SoSwitch { SoSeparator { SoTransform (node pose) ; SoMaterial ; SoTexture2 ; SoShapeHints ; SoCoordinate3 ; SoNormal ; SoTextureCoordinate2 ; SoIndexedFaceSet ; child nodes } }`;
the switch hides a node and its subtree, the transform poses it. PNG decode goes through Qt `QImage`. The decoded atlas is one `SoTexture2` shared by all meshes that use it
(the Steam Frame models use one 2048 x 2048 atlas for all nodes). Texture coordinates are used as stored: glTF has its origin at the top-left of the image, and the decoded rows
are passed top row first, so no flip is applied. Building one Frame controller takes about 0.1 s. The cached GLB is read from disk when its UUID is known; the
node states reported by the runtime (`xrGetRenderModelStateEXT`) replace the local pose and the visibility of the named nodes every frame.

The Frame controller atlas is near black (mean RGB about 15 of 255), so the models look black unless the scene is brightly lit.

## Fallback

If the extensions are missing, the models cannot be loaded, or before the first sync, the rig shows a **generated** controller shape
(simple primitives created in code, no assets, `render/controller_shape.py`). It uses the frame and the part names of the runtime models (`trigger`, `thumbstick`,
`button_a`, ...), is placed at the aim pose, and is animated from the `InputFrame`. The fallback is also what the Sim backend renders.

## Rules from the specification

- Cache assets locally keyed by UUID; the cache is not distributed with an application. `xrGetRenderModelPropertiesEXT` is called every session before using a cached UUID.
- Do not select models by id or UUID and do not infer the hardware from them; use whatever the runtime returns.
- Handle a model that is not located (hidden) and node visibility inheritance (an invisible animatable node hides its descendants).

## pyopenxr 1.1.6302 workarounds

The high-level wrappers do not implement the two-call idiom or preallocated arrays, so the functions are called through their
prototypes (`ctypes.cast(xr.get_instance_proc_addr(...), xr.PFN_...)`):

| Wrapper | Problem | Workaround |
|---|---|---|
| `get_render_model_properties_ext` | raises `TypeError: expected Uuid instance, got int` | pass `xr.RenderModelPropertiesEXT(cache_id=xr.Uuid())` to the raw function |
| `get_render_model_asset_data_ext` | performs only the capacity query (returns the struct, no data) | call twice: capacity, then a `c_uint8` buffer of that size |
| `get_render_model_asset_properties_ext` | passes an empty node array, runtime returns validation failure | preallocate `RenderModelAssetNodePropertiesEXT * animatable_node_count` |
| `get_render_model_state_ext` | same preallocation requirement for the node state array | preallocate `RenderModelNodeStateEXT * animatable_node_count` |

## Other sources considered

- `...\SteamVR\resources\rendermodels\` and `...\drivers\frame_controller\resources\rendermodels\` hold the legacy OpenVR format (OBJ + PNG/TGA + a JSON of component pivots).
  They are proprietary assets of the SteamVR installation, SteamVR-only, and are not read by the addon.

The model list is enumerated after the first successful action sync and again on `XrEventDataInteractionRenderModelsChangedEXT`; because the runtime does not always send that event for a controller that was asleep at the start, the count of offered models is also compared with the loaded models once per second and the list is enumerated again when they differ.
