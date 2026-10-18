# The VR integration layer (from freecad-xr-workbench)

Upstream: https://github.com/kwahoo2/freecad-xr-workbench (LGPL-3.0+, base version 1.0.3.1). The addon keeps the VR integration of that module and nothing else (`design.md`, D8): the OpenXR session and render loop, input, controller models, the desktop mirror, the spectator camera, and the lighting and anti-aliasing preferences. Its tools, in-world menus, Qt panel overlay and document code are not part of the addon.
Pure Python addon in the `freecad.VReeCAD` namespace package (`freecad/VReeCAD/`). Targets FreeCAD 1.1 / Python 3.11+.
Deps: `pyopenxr`, `PyOpenGL`. Needs a runtime with `XR_KHR_opengl_enable`.

## Compatibility

Runs on FreeCAD 1.1.4 with SteamVR OpenXR 2.17.10 (see `verification.md`).

## Architecture (file by file)

| File | Role |
|---|---|
| `init_gui.py` | `VReeCADWorkbench` (Gui::PythonWorkbench); toolbar and menu with 6 commands; preferences page |
| `startXR/stopXR/enableMirror/disableMirror/reloadScenegraph/toggleTPPCamera.py` | One-class command wrappers that call `commonXR` functions |
| `commonXR.py` | `DockWidget` (Qt dock hosting) + `XRwidget(QOpenGLWidget)`: OpenXR instance, session and swapchains, the Coin scene (`setup_scene`), the render loop (`update_render`, `paintGL`), the per-frame input (`update_xr_controls`), the tool manager and the services the tools use (`setup_tool_services`), the actions of the interface (`setup_ui`) |
| `controllerXR.py` | `xrController`: the Coin node of one controller (the generated shape or the runtime model, hidden while untracked) and where a part of it is (`part_frame`) |
| `input.py`, `profiles.py` | `InputFrame` / `HandInput` / `InputTracker` (hardware independent input with edge events) and the per-profile mapping of the abstract inputs to OpenXR paths |
| `backends/` | `openxr_input.py` (action set, bindings, polling, haptics), `openxr_models.py` (runtime controller models), `sim.py` (scripted head and controllers) |
| `render/` | `gltf_coin.py` (glTF to Coin3D), `controller_shape.py` (generated controller), `offscreen.py` (headless render to an image), `ghost.py`, `highlight.py`, `model_anchor.py` |
| `gltf.py` | GLB reader (node tree, triangle meshes, materials, embedded images) |
| `tools/`, `ui/`, `core/`, `cad/` | The tools, the interface, the pure logic and the FreeCAD wrappers (`design.md`, Architecture) |
| `preferences.py`, `XRWorkbench_rc.py`, `Resources/` | Preferences page (lighting, anti-aliasing, mirror, debug, OpenXR version, AR mode, spectator camera), compiled Qt resources, icons |

`XRWorkbench_rc.py` is generated from `Resources/Gui/Resources/XRWorkbench.qrc` with Qt's `rcc` (`-g python --compress-algo zlib`), the import line changed to `from PySide import QtCore`.

### Control flow per frame
`update_render` (timer) -> `poll_xr_events` -> `start_xr_frame` -> `update_xr_movement` (frame timing) -> `update_xr_views` (eye cameras, head pose) ->
`update_xr_controls` (sync actions, `InputFrame`, controller models, `update_ui`: grip navigation, palette carousel, pointer poses, controller poses) ->
`update_xr_interaction` (`tools.update(frame)`) -> Coin render per eye -> `end_xr_frame`; `update_gui` (title bar) runs on its own timer.

### Coordinates
The controller pose comes from the `InputFrame` in the stage frame (metres). The document is drawn through `doc_xr_transform` (millimetres to metres, Z up) and the navigation transform of the grips; `core/stage.py` converts between the stage and the document.

## Reusable API surface
`XRwidget.input_frame` (the current `InputFrame`), `XRwidget.xr_con[]` (the controller nodes), `XRwidget.tools` (the tool manager and its context with the services), `UiController` (`ui/controller.py`).
