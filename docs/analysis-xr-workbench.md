# Analysis: freecad-xr-workbench (the base of this repo)

Upstream: https://github.com/kwahoo2/freecad-xr-workbench (LGPL-3.0+, base version 1.0.3.1).
Pure Python addon in the `freecad.BlocksCAD` namespace package (`freecad/BlocksCAD/`). Targets FreeCAD 1.1 / Python 3.11+.
Deps: `pyopenxr`, `PyOpenGL`. Needs a runtime with `XR_KHR_opengl_enable`.

## Compatibility

Runs on FreeCAD 1.1.4 with SteamVR OpenXR 2.17.10 (see `verification.md`). The one FreeCAD 1.1 difference, the tree view dock name, is handled (setup.md gotcha 3).
The controller tools (teleport, line, cube, select, drag, working plane), Qt overlay interaction and Pad/Pocket editing are unverified in-headset.

## Architecture (file by file)

| File | Role |
|---|---|
| `init_gui.py` | `XRWorkbench` (Gui::PythonWorkbench); toolbar/menu with 6 commands; preferences page |
| `startXR/stopXR/enableMirror/...py` | One-class command wrappers that call `commonXR` functions |
| `commonXR.py` (about 1.9k lines) | `DockWidget` (Qt dock hosting) + `XRwidget(QOpenGLWidget)`: OpenXR instance/session/swapchains, Coin scene (`setup_scene`), render loop (`update_render`, `paintGL`), per-frame input handling (`update_xr_controls`), the inherited `interact_*` tool handlers (called through registered tools), palette and tool selection (`select_tool`) |
| `input.py`, `profiles.py` | `InputFrame` / `HandInput` / `InputTracker` (hardware independent input with edge events) and the per-profile mapping of the abstract inputs to OpenXR paths |
| `backends/` | `openxr_input.py` (action set, bindings, polling, haptics), `openxr_models.py` (runtime controller models), `sim.py` (scripted head and controllers) |
| `render/` | `gltf_coin.py` (glTF to Coin3D), `controller_shape.py` (generated controller), `offscreen.py` (headless render to an image) |
| `tools/`, `ui/` | Tool base class, registry, manager and the inherited modes as tools; palette ring logic, layout and view, the UI controller |
| `gltf.py` | GLB reader (node tree, triangle meshes, materials, embedded images) |
| `controllerXR.py` | `xrController`: Coin node for the controller (generated shape or runtime model) + picking ray; button state machine `AnInpEv` (JUST_PRESSED/PRESSED/JUST_RELEASED/RELEASED); `find_picked_coin_object` (ray pick on any Coin graph) |
| `menuCoin.py` | Minimal in-world Coin widgets: `buttonWidget`, `sliderWidget`, `labelWidget`, `coinMenu`, `editCoinMenu` (shown near the right hand after selecting an object) |
| `previewCoin.py` | Coin overlays: polyline preview, working plane, length/coordinate labels |
| `qtWidgetRender.py` | Renders Qt dock widgets (Model tree, Tasks) to textures on quads in the scene; ray emulates mouse |
| `documentInteraction.py` | **Bridge to the FreeCAD document**, module-global state: polyline -> face, add/resize `Part::Box`, select (view picking), drag (Placement), PartDesign Pad/Pocket by dragging, body management |
| `preferences.py`, `XRWorkbench_rc.py`, `Resources/` | Preferences UI, compiled Qt resources, icons |

### Control flow per frame
`update_render` (timer) -> `poll_xr_events` -> `start_xr_frame` -> `update_xr_movement` (frame timing) -> `update_xr_views` (eye cameras, head pose) ->
`update_xr_controls` (sync actions, `InputFrame`, controller models, `update_ui`: grip navigation and palette ring, controller poses) ->
`update_xr_interaction` (Qt widgets, `tools.update(frame)`) -> Coin render per eye -> `end_xr_frame`; `update_gui` (title bar) runs on its own timer.

### Interaction model
- `InteractMode` enum: TELEPORT, LINE_BUILDER, CUBE_BUILDER, SELECT_MODE, DRAG_MODE, WORKING_PLANE; each names a registered tool, and `XRwidget.interact_mode` reads and writes the active tool of the `ToolManager`.
- Left controller trigger = main menu (point + release to choose tool); the **secondary (right) controller is the tool hand**.
- `interact_*` methods are state machines over the right controller's trigger (`grab_ev`) event.
- Coordinates: controller pose is in XR space; `get_doc_transf()` / `get_xr_sbvec()` convert between XR (Coin) and document coordinates (m vs mm scaling, `world_transform`).
- Edit tools (Pad/Pocket): `set_start_edit` -> `update_edit_transf` (distance along face normal from controller movement) -> `set_finish_edit`.
- The document is mutated **during** the gesture (cube resize rewrites `Length/Width/Height` each frame; recompute on release).

## Strengths to keep
Working end-to-end OpenXR in pure Python; bindings for many controller profiles; in-world menu widgets; ray picking against both the document scene and menus; Qt overlay; teleport/arch/free locomotion.

## Weak points for the BlocksCAD goal (the rework in `design.md` addresses them)
1. The inherited tools are state machines inside the widget and keep their state in module globals of `documentInteraction.py`; new tools are classes in `tools/` that see only the `InputFrame`.
2. Menus are a fixed set of buttons/sliders/labels; no icons, no palette, no tool-options panel.
3. No undo/redo integration (no `doc.openTransaction` around gestures); Blocks-style fearless editing needs it.
4. No snapping/grid; no two-handed manipulation (scale/rotate); selection limited to whole objects/faces via view picking.
5. Gestures mutate the document continuously (heavy for non-trivial recompute); want Coin-only preview, then commit.
6. Handedness fixed by preferences (primary/secondary).

## Reusable API surface we will build on
`XRwidget.input_frame` (the current `InputFrame`), `xrController.get_buttons_states()`, `.get_local_transf()`, `.find_picked_coin_object(...)`, `.show_ray_ext()`;
`coinMenu` and its widgets; `coinPreview`; `docInter.coin_to_doc_*` conversions; `XRwidget.hmd_transform / world_transform / xr_con[]`.
