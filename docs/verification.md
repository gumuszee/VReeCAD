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

## Platform and tooling

| Area | Status | Notes |
|---|---|---|
| Addon loads in FreeCAD (workbench `BlocksCADWorkbench`, package `freecad.BlocksCAD`) | Verified | all modules import; no Report-view errors |
| OpenXR session starts, reaches `FOCUSED` when the headset is worn | Verified | `tools/xr_probe.py`, `tools/snippets/xr_state.py` |
| Document geometry visible in the headset | Verified | owner-confirmed |
| Frame rate with a small scene | Verified | owner-reported "excellent" |
| Tree view overlay panel is found | Verified | dock name `Model` is accepted |
| Input actions (trigger, grip, stick, stick click, two buttons, menu, haptic, aim and grip poses, `aux1`, `aux2`): suggested bindings accepted by the runtime for the Frame, Touch, Index, Vive and WMR profiles | Verified | SteamVR 2.17.10 accepts all five profiles (`backends/openxr_input.py`, `profiles.py`) |
| Steam Frame controller input paths accepted by the runtime | Verified | `tools/xr_probe_paths.py`; `input-profiles.md` |
| Steam Frame left D-pad up and down work as buttons | Verified | owner-confirmed |
| Runtime controller models: both interaction render models enumerated, GLB assets downloaded, node names read, model spaces located while `FOCUSED`, node animation reported | Verified | Steam Frame controllers, SteamVR 2.17.10; `controller-models.md` |
| Runtime controller models parsed and built into Coin3D; rendered offscreen | Verified | `render/gltf_coin.py`, `tools/snippets/render_controller_models.py`; the Frame controller texture atlas is near black, so the models appear black |
| Runtime controller models displayed at both controllers in the headset, animated with input | Verified | owner-confirmed, alignment identical to the controllers of the Steam overlay |
| Offscreen render of the document scene from an arbitrary camera pose to PNG | Verified | `tools/snippets/offscreen_render.py` |
| Sim backend: scripted head and controller poses and inputs, edge events, offscreen mono and stereo render of the document scene with controller shapes | Verified | `backends/sim.py`, `tools/snippets/sim_demo.py`, `tests/live/test_coin.py` |
| Unit tests without FreeCAD (input, profiles, glTF, Sim math, tool registry, navigation, units, pointing, carousel, layout, sliders, face moves, quick radial, toasts, undo button, tool options) | Verified | 210 tests: `"%LOCALAPPDATA%\Programs\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests` |
| Unit tests with the live GUI (glTF to Coin loader, generated controller shape, Sim session render, interface scene graph, radial, face moves, undo button, toasts, tooltips and option readout through the controller) | Verified | 46 tests: `tools/snippets/run_live_tests.py` |
| Import check of the sources | Verified | `tools/lint_imports.py` reports no problem |
| Dev remote control (`tools/fc_rpc.py`, MCP smoke test) | Verified | `tools/mcp_smoke_test.py` passes end to end |
| Meta Quest / Index / Vive / WMR / Pico controllers | Unverified | bindings exist for the profiles; no device tested |
| Performance with large scenes | Unverified | |

## Interface in the headset

| Area | Status | Notes |
|---|---|---|
| Palette carousel on the left controller: follows the position and rotation of the hand, every side visible, gaze fade, stick flick turns it, faces activate tools | Verified | owner-confirmed; `tests/test_ring.py`, `tools/snippets/render_ui.py` |
| Panel arrangement: lifting a panel by its title bar, dropping it next to, above or below another panel, stacking on one side, saved layout | Verified | owner-confirmed |
| Sliders in panels (trigger held on the row, drag along the track) | Verified | owner-confirmed with the Session panel sliders |
| Grip navigation: free orbit with one and two grips, level rotation while A is held, scale locked at 1 : 1 while B is held, reset to the home pose 1 m in front of the head | Verified | owner-confirmed; `core/navigation.py`, `tests/test_navigation.py` |
| Scale ruler (document units, drawn over the model, interface font) and the scale plate with one grip | Verified | owner-confirmed; `core/units.py`, `ui/ruler.py` |
| Pointer: laser, and tip on both controllers with a cone and a small sphere; angle 15 degrees and length 40 mm | Verified | owner-confirmed; the tip of the left controller hides while the carousel is shown |
| Navigation in tip mode: the world is held at the tips, the ruler runs between the tips, both tips stay visible | Verified | owner-confirmed |
| Faces activate when the trigger is released over them (tip and laser); a press that leaves the face does nothing | Unverified | `tests/test_ring.py`, `tests/live/test_coin.py` |
| Quick radial: `button1` of the tool hand held opens it, the hand direction chooses, release activates; favourites follow use | Unverified | `tests/test_radial.py`, `tests/live/test_coin.py`, `tools/snippets/render_ui.py` (`ui_radial.png`); disc size and dead zone (3 cm hub) are guesses |
| Lifting a face (0.4 s hold), dropping it on a slot (move or swap), hiding it on the extra side, Show hidden | Unverified | `tests/test_ring.py`, `tests/live/test_coin.py`, `tools/snippets/render_ui.py` (`ui_face_lift.png`, `ui_face_hide.png`) |
| Tip drawn in inverted colours where it is behind or inside a panel or the model | Unverified | `tools/snippets/render_ui.py` (`ui_tip_through.png`, `ui_tip_behind.png`); legibility of the dark inverted colours is a guess |
| Controller models hide the tip and the laser (second draw of the models with the depth test), no flicker where the model is drawn twice | Unverified | `tests/live/test_coin.py` counts the inverted cone pixels (0 with, more than 10 without); the runtime glTF models have not been checked for depth fighting |
| Grab tool: hover highlight of vertex, edge, face and object (the whole object is filled), the hover steady against a trembling hand and in front of the selection, tap selects, drag moves and turns freely, A held locks to the grid and the angle step with a padlock over the A button, the other trigger scales a primitive, grip cancels, no quick radial during a grab, one undo step | Unverified | `tests/test_grab.py`, `tests/live/test_coin.py` (`GrabLiveTest`, real FreeCAD objects and the Sim), `tools/snippets/render_ui.py` (`ui_grab_*.png`); the reach (12, 20 and 30 mm), the rotation step and the feel of the grab are guesses; picking measures every object whose box contains the cursor, so large documents are untested |
| Option disc of six sections on the stick for the Create tool (grid top and bottom, four shapes, click for more shapes) and the Grab tool (grid top and bottom, two move modes, angle step), shown above the tool hand while the stick is out | Unverified | `tests/test_feedback.py` (`DiscTest`), `tests/test_primitives.py`, `tests/live/test_coin.py`, `tools/snippets/render_ui.py` (`ui_options_create.png`, `ui_grab_disc.png`); the size and the height of the disc are guesses |
| Create tool: cross at the snapped cursor, drag to a ghost and sizes, release makes the feature, tap places a default shape, undo removes it | Unverified | `tests/test_primitives.py`, `tests/live/test_coin.py` (`PrimitiveLiveTest`, real FreeCAD features and the Sim), `tools/snippets/render_ui.py` (`ui_primitive_*.png`); feel of the snap, cursor offset and ghost are guesses; the preview mesh volume matches the feature within 3.5 % and updates in under 12 ms on average even for a torus |
| Undo on `button2` of the tool hand (tap), redo (hold 0.4 s), toasts for undo and redo | Unverified | `tests/test_feedback.py`, `tests/live/test_coin.py`; `button2` stays the 1 : 1 lock while a grip holds the world |
| Toasts in front of the head (position, size, duration) and tooltips of faces after 0.5 s | Unverified | `tools/snippets/render_ui.py` (`ui_feedback.png`); distance 0.8 m, drop 0.2 m, scale 1.5 are guesses |
| Tool options on the stick with the readout next to the pointer | Unverified | `tests/test_feedback.py`, `tools/snippets/render_ui.py` (`ui_readout.png`); no inherited tool declares options, so the first use is a new tool |
| Undo on the left D-pad left, redo on D-pad right | Unverified | `tests/live/test_coin.py` covers the dispatch; the runtime binding of `dpad_left` and `dpad_right` has not been observed |
| After a two-grip gesture the remaining grip does nothing until both are released | Unverified | `tests/test_navigation.py` covers it |
| Haptic feedback (hover, activation, steps, grips, reset) | Unverified | calls are issued; the feel has not been judged |
| Teleport tool moves the world | Unverified | |
| Tools (Select, Drag, Teleport, Line, Cube, Working plane) acting on what the tip touches (3 cm reach) | Unverified | the inherited tools pick along a short ray from the tip |
| Inherited tools in the headset, routed through the tool registry | Unverified | the manager lifecycle is unit tested |

## Remaining in-headset checks (owner)

Start the viewer (workbench BlocksCAD, "Open XR viewer"), wear the headset until the session is `FOCUSED`, then check:

1. Grab tool (free and locked): choose Grab, touch a box made with Create at a corner, an edge, a face and inside it (each highlights), tap to select, drag it (grid steps, turn with the wrist), scale it with the trigger of the other hand, hold A during the grab (padlock closes, grid and angle lock), cancel with a grip, undo. Check that the highlight is steady and that the quick radial stays closed during a grab. Check that the reach and the highlights are easy to judge, that the highlight does not flicker (also with the selected element under the hand) and that selecting also shows on the desktop. Push the stick for the option discs of Create and Grab.
2. Create tool: choose Create on the palette, move the tip (a cross shows the grid point), drag with the trigger and release; try every shape on the stick left and right, the grid on the stick up and down, a tap, a grip during a drag and undo. Check that the snapped point and the box feel right at different world scales.
3. Quick radial: hold `button1` of the right controller (A on the Steam Frame), move the hand towards an item, release; check that it is not triggered while a grip holds the world and that the dead zone and the ring size feel right.
4. Faces: tap a face (it runs on release), hold a face for 0.4 s and drop it on another slot, on a filled slot (swap) and on the "Hide face" side; use Show hidden and Reset layout.
5. `button2` of the right controller (B on the Steam Frame): a tap undoes, a hold of 0.4 s redoes, with toasts; while a grip holds the world it is still the 1 : 1 lock. Toast size and place, tooltips after 0.5 s on a face.
6. Pressing the left D-pad left undoes and D-pad right redoes the last document change, with a haptic tick (the Edit faces do the same).
7. After a two-grip gesture, releasing one grip first and moving the other hand does not move the model; after releasing both, a one-grip drag works again.
8. The haptic ticks are noticeable and not annoying: hover over a face, activation, slider steps, grip start, scale doubling, reset.
9. The Teleport tool brings the picked surface under the feet, with the laser and with the tip.
10. In tip mode Select, Drag and the builders act on what the tip touches.
