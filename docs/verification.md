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
| Input actions (trigger, grip, stick, stick click, two buttons, menu, haptic, aim and grip poses): suggested bindings accepted by the runtime for the Frame, Touch, Index, Vive and WMR profiles | Verified | SteamVR 2.17.10 accepts all five profiles (`backends/openxr_input.py`, `profiles.py`) |
| Input values in the headset: grip, two buttons, stick click, menu, haptics | Unverified | owner check pending, see the in-headset checklist below |
| Meta Quest / Index / Vive / WMR / Pico controllers | Unverified | bindings exist for the profiles; no device tested |
| Performance with large scenes | Unverified | |
| Offscreen render of the document scene from an arbitrary camera pose to PNG | Verified | `tools/snippets/offscreen_render.py` |
| Sim backend: scripted head and controller poses and inputs, edge events, offscreen mono and stereo render of the document scene with controller shapes | Verified | `backends/sim.py`, `tools/snippets/sim_demo.py`, `tests/live/test_coin.py` |
| Unit tests without FreeCAD (input edges, profiles, glTF parser, Sim math, tool registry, palette logic) | Verified | `"%LOCALAPPDATA%\Programs\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests` |
| Unit tests with the live GUI (glTF to Coin loader, generated controller shape, Sim session render) | Verified | `tools/snippets/run_live_tests.py` |
| Runtime controller models: both interaction render models enumerated, GLB assets downloaded, node names read, model spaces located while `FOCUSED`, node animation reported | Verified | Steam Frame controllers, SteamVR 2.17.10; `controller-models.md` |
| Runtime controller models parsed and built into Coin3D; rendered offscreen | Verified | `render/gltf_coin.py`, `tools/snippets/render_controller_models.py`; the Frame controller texture atlas is near black, so the model appears black |
| Runtime controller models displayed at the controllers in the headset, animated with input | Unverified | owner check pending, see the in-headset checklist below |
| Tool registry with the six inherited modes, `select_tool` | Unverified in-headset | the viewer starts with the registry; manager lifecycle is unit tested |
| Palette ring (pages of faces around the left controller, stick flick turns it, gaze or button1 shows it, tool hand ray hovers and trigger activates a face): logic unit tested, rendered offscreen through the Sim session | Verified | `tests/test_ring.py`, `tools/snippets/render_ui.py` |
| Palette ring in the headset (readability, gaze visibility, ray hover, activation, haptics) | Unverified | owner check pending, checklist items 3 and 4 |
| Steam Frame controller input paths accepted by the runtime | Verified | `tools/xr_probe_paths.py`; `input-profiles.md` |
| Steam Frame left D-pad directions work as buttons | Verified | owner-confirmed |
| Dev remote control (`tools/fc_rpc.py`, MCP smoke test) | Verified | `tools/mcp_smoke_test.py` passes end to end |

| Grip navigation (`core/navigation.py`): one grip drags, two grips move/rotate/scale about the midpoint, stick click resets; unit tested and run through the Sim session | Verified | `tests/test_navigation.py`, `tests/live/test_coin.py` |
| Grip navigation in the headset (haptics, scale readout, teleport tool moving the world) | Unverified | owner check pending, checklist item 5 |

## In-headset checklist (owner)

Start the viewer (workbench BlocksCAD, "Open XR viewer"), wear the headset until the session is `FOCUSED`, then check:

1. Both controllers are drawn as the runtime models (Steam Frame shapes) at the hands, and the report view prints `Controller models from the runtime: ['left', 'right']`.
2. Pulling a trigger, squeezing a grip, moving a stick and pressing buttons moves the matching parts of the models.
3. Looking at the left controller fades in the palette ring above it (pages of labelled faces, page dots below); looking away fades it out; the left D-pad up (button1) pins and releases it.
4. Flicking the left stick left or right turns the ring one page with a haptic tick. Pointing the right controller at a face highlights it (blue) with a tick, the trigger activates it (the active tool is orange, the status label changes). Faces: Tools (Teleport, Line, Cube, Select, Drag, Working plane), Edit (Undo, Redo, Delete), View (Reset view, Panels, Work plane, Reload scene), Session (Close VR). The labels are readable and do not overlap.
5. Navigation: gripping with one hand drags the world with that hand; gripping with both hands moves, turns (about the vertical axis) and scales the world, a `N : 1` readout floats above the midpoint, haptic ticks occur when the scale passes a power of two; clicking the stick of a gripping hand animates the view back to the origin at scale 1 : 1; the teleport tool brings the picked surface under your feet. The thumbsticks do not move you.
