# Verification status

State of what has been checked, per configuration. "Verified" means observed working on the listed setup; everything else is unverified.
Only the owner can verify in-headset behaviour. Update the table cells in place when a check changes.

## Reference configuration

| Item | Value |
|---|---|
| OS / GPU | Windows 11, NVIDIA RTX 4080 |
| FreeCAD | 1.1.4 (installed release, Python 3.11, PySide6 6.8.3) |
| OpenXR runtime | SteamVR 2.17.10, OpenXR API 1.0 instance (API 1.1.x is rejected by this runtime) |
| Headset / controllers | Steam Frame / Steam Frame controllers |

## Checks

| Area | Status | Notes |
|---|---|---|
| Addon loads in FreeCAD (workbench `BlocksCADWorkbench`, package `freecad.BlocksCAD`) | Verified | all modules import; no Report-view errors |
| OpenXR session starts, reaches `FOCUSED` when the headset is worn | Verified | `tools/xr_probe.py`, `tools/snippets/xr_state.py` |
| Document geometry visible in the headset | Verified | owner-confirmed |
| Frame rate with a small scene | Verified | owner-reported "excellent" |
| Tree view overlay panel is found | Verified | dock name `Model` is accepted |
| Locomotion, teleport, line builder, cube builder, select / pad / pocket, drag, Qt overlay interaction | Unverified in-headset | upstream controls are rated unintuitive by the owner and are replaced by the design in `design.md` |
| Steam Frame controller grip, face buttons, stick click | Unverified | the input layer binds them as part of milestone M0 |
| Meta Quest / Index / Vive / WMR / Pico controllers | Unverified | bindings exist for the profiles; no device tested |
| Performance with large scenes | Unverified | |
| Offscreen render of the document scene from an arbitrary camera pose to PNG | Verified | `tools/snippets/offscreen_render.py`; document geometry only, rendering the XR rig overlays (controllers, panels) is part of milestone M0 |
| Runtime controller models: both interaction render models enumerated, GLB assets downloaded, node names read, model spaces located while `FOCUSED`, node animation reported | Verified | Steam Frame controllers, SteamVR 2.17.10; `controller-models.md` |
| Controller models rendered in the headset | Unverified | the glTF loader and rig nodes are part of milestone M0 |
| Steam Frame controller input paths accepted by the runtime | Verified | `tools/xr_probe_paths.py`; `input-profiles.md` |
| Steam Frame left D-pad directions work as buttons | Verified | owner-confirmed |
| Dev remote control (`tools/fc_rpc.py`, MCP smoke test) | Verified | `tools/mcp_smoke_test.py` passes end to end |
