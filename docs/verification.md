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
| Palette carousel on the controller (all sides of a prism around the left controller visible, follows its rotation, stick flick turns it, gaze or button1 shows it, laser from the tool hand, hover and trigger activate a face, panels arranged in rows and columns by lifting the title bar): logic unit tested, rendered offscreen through the Sim session | Verified | `tests/test_ring.py`, `tools/snippets/render_ui.py` |
| Pointer modes in the headset (laser and tip on both controllers, tip angle and length from the Session panel, menu by touch, models by touch) | Unverified | owner check pending, checklist item 7 |
| Palette carousel in the headset (all sides visible, laser, follows the wrist, gaze visibility, ray hover, activation, panel rearranging into rows and columns, haptics) | Unverified | owner check pending, checklist items 3 and 4 |
| Steam Frame controller input paths accepted by the runtime | Verified | `tools/xr_probe_paths.py`; `input-profiles.md` |
| Steam Frame left D-pad directions work as buttons | Verified | owner-confirmed |
| Dev remote control (`tools/fc_rpc.py`, MCP smoke test) | Verified | `tools/mcp_smoke_test.py` passes end to end |

| Grip navigation (`core/navigation.py`): one grip holds the world in the hand (position and rotation), two grips move/rotate/scale about the midpoint, free orbit, level modifier, held 1 : 1 lock, reset to the home pose in front of the head; unit tested and run through the Sim session | Verified | `tests/test_navigation.py`, `tests/live/test_coin.py` |
| Grip navigation in the headset (free orbit with one and two grips, level modifier on A, 1 : 1 lock while B is held, scale plate with one grip, home reset, haptics, teleport tool moving the world) | Unverified | owner check pending, checklist item 5 |
| Scale ruler between the hands (document units, drawn over the model, interface font): unit tested (`tests/test_units.py`), rendered offscreen | Verified | `core/units.py`, `ui/ruler.py`, `tools/snippets/render_ui.py` |
| Scale ruler and undo/redo on the D-pad in the headset | Unverified | owner check pending, checklist items 5 and 6 |

## In-headset checklist (owner)

Start the viewer (workbench BlocksCAD, "Open XR viewer"), wear the headset until the session is `FOCUSED`, then check:

1. Both controllers are drawn as the runtime models (Steam Frame shapes) at the hands, and the report view prints `Controller models from the runtime: ['left', 'right']`; a controller that was asleep when the viewer started gets its model within a second of waking.
2. Pulling a trigger, squeezing a grip, moving a stick and pressing buttons moves the matching parts of the models.
3. Looking at the left controller fades in the palette carousel on it: every side of the prism around the controller is visible at once, the front panel stands on the thumb side and follows the position and rotation of the hand (rolling the wrist rolls the carousel), looking away fades it out; the left D-pad up (button1) pins and releases it. Labels are readable, in a sans serif font. While it is shown the right controller carries a visible laser that ends in a dot on the panel.
4. Flicking the left stick left or right turns the carousel one side with a haptic tick. Pointing the right controller at a face highlights it (blue) with a tick, the trigger activates it (the active tool is orange, the status label changes). Panels: Tools (Teleport, Line, Cube, Select, Drag, Working plane), Edit (Undo, Redo, Delete), View (Reset view, Overlays, Work plane, Reload scene, Reset layout), Session (Close VR). Rearranging: holding the trigger on a title bar lifts the panel (a card follows the laser, one extra empty side "Drop here" appears); aiming at the left or right half of another panel and releasing puts the panel next to it, aiming at its upper or lower quarter makes a new row above or below it (an orange bar shows the place); turning the carousel while holding brings other sides to the front; the layout survives a viewer restart; the Reset layout face restores the defaults.
5. Navigation: gripping with one hand holds the world in that hand (it follows the hand and turns with its rotation, tipping freely); gripping with both hands moves, scales and rotates the world as a free orbit; holding A (right controller) keeps the bottom down (vertical axis only) with one or two grips, releasing A returns to free orbit without a jump; holding B while gripping animates the scale to 1 : 1 and keeps it there however the hands move, releasing B lets the hand distance scale again. With two grips a line joins the hands as a ruler with ticks labelled in the document unit (millimetres for a Standard document), the scale ratio `N : 1` and the length between the hands below it; with one grip the ratio and the modes float above the hand; all in the interface font and drawn over the model even when the model is in front. Haptic ticks occur when the scale passes a power of two. Clicking the stick of a gripping hand (or the Reset view face) animates the view to scale 1 : 1 with the origin 1 m in front of you at chest height. The teleport tool brings the picked surface under your feet. The thumbsticks do not move you.
6. Pressing the left D-pad left undoes and D-pad right redoes the last document change, with a haptic tick (the Edit faces do the same).
7. Session panel: the Pointer face switches between the laser and the tip (both controllers show a sphere on a stem in tip mode); Angle + and Angle - tilt the pointer down in 5 degree steps and Length + and Length - move the tip away from the controller in 1 cm steps, the faces show the current values, and the settings are kept after a viewer restart. In tip mode a face lights up and the trigger presses it when the sphere touches it (within about 3 cm), a panel is lifted by touching its title bar, and the Select, Drag and Teleport tools act on what the tip touches.
8. After a two-grip gesture, releasing one grip first and moving the other hand does not move the model; after releasing both, a one-grip drag works again.
