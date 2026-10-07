# Setup & environment facts

Machine: Windows 11, RTX 4080, SteamVR as active OpenXR runtime, Steam Frame headset + Steam Frame controllers. All of this is automated by `tools/bootstrap.ps1`;
this page records *what* it does and *why*, plus the facts you need when something breaks.

## Components and where they live

| Thing | Location | Notes |
|---|---|---|
| FreeCAD 1.1.4 (installed release) | `%LOCALAPPDATA%\Programs\FreeCAD 1.1` | bundled Python 3.11.14, PySide6 6.8.3, numpy 1.26. **We do not build from source**: both addons are Python. |
| FreeCAD user dir | `%APPDATA%\FreeCAD\v1-1` | `Mod\` holds our junctions; `user.cfg`; `freecad_mcp_settings.json` |
| `pyopenxr` 1.1.6302, `PyOpenGL` 3.1.10 (+glfw) | FreeCAD's `bin\Lib\site-packages` | `bin\python.exe -m pip install ...`. **Lost if FreeCAD is reinstalled/upgraded** - rerun bootstrap. |
| The addon (this repo) | repo root -> junction `Mod\BlocksCAD` | Namespace `freecad.BlocksCAD`, workbench `BlocksCADWorkbench`. It has its own namespace, distinct from upstream's `freecad.XR`; do not install both. Edit repo, restart FreeCAD (or `tools/snippets/xr_restart.py`). |
| OpenXR spec sources (sparse) | `refs\OpenXR-Docs\specification\sources\chapters\extensions\{ext,valve}` | Khronos spec text (AsciiDoc) for extension questions, e.g. `ext\ext_render_model.adoc` |
| Open Brush (sparse) | `refs\open-brush\Assets\Scripts` | Reference for the UX: `SketchControlsScript.cs` (grip world transform), `Util\MathUtils.cs` (two point transform), `GUI\PanelManager.cs` (palette ring), `GUI\PinCushion.cs` (quick radial). Apache-2.0, behaviour reference only |
| MCP RPC addon (DEV-ONLY) | `refs\freecad-mcp\addon\FreeCADMCP` -> junction `Mod\FreeCADMCP` | Runs XML-RPC on `127.0.0.1:9875`, auto-start enabled. If we start modifying it, copy it out of `refs/` into our own repo. |
| MCP server (external process) | `refs\freecad-mcp` run via `uv` (Python >= 3.12) | `uv` installed with `winget install astral-sh.uv`. Never pip-install it into FreeCAD's Python. |
| Claude Code registration (DEV-ONLY) | `.mcp.json` (project scope, git-ignored; bootstrap writes it) | The Claude app must be restarted after uv is first installed (PATH) and the project MCP server approved on first use. |

## Reference clones (shallow, `--depth 1`)

`refs/FreeCAD` tracks `main` (**27.1.0-dev**), which differs from the installed **1.1.4**. For API questions about the installed
version, fetch the matching tag: `git -C refs/FreeCAD fetch --depth 1 origin tag 1.1.4` (verify tag name) and `git checkout` it, or
read the installed `Mod\` Python sources under `%LOCALAPPDATA%\Programs\FreeCAD 1.1\Mod` (they are the ground truth for the runtime).
To unshallow any ref: `git -C refs/<x> fetch --unshallow`.

## Gotchas discovered (keep this list growing)

1. **Workbench commands exist only after the workbench has been activated in the session.** `Gui.runCommand('startXR')` fails with
   "No such command" until `Gui.activateWorkbench('XRWorkbench')` ran.
2. **pyopenxr's newest API (1.1.63) is rejected by SteamVR 2.17** (`ApiVersionUnsupportedError`). The addon already
   requests 1.0.x by default and falls back; leave the "Use highest OpenXR version" preference **off**.
3. **Session state `SYNCHRONIZED` (3) = running but headset not worn.** `VISIBLE`/`FOCUSED` need the proximity sensor
   triggered (SteamVR). Rendering to the HMD only happens in VISIBLE/FOCUSED. `tools/snippets/xr_state.py` prints it.
4. `print()` from addon code goes to FreeCAD's **Report view**, not to the RPC `exec` result. Use `tools/snippets/report_view.py`.
5. Starting the XR viewer needs an **active document** (`open_xr_viewer` returns "No active view!" otherwise).
6. Windows console is cp1252: `fc_rpc.py` forces UTF-8 output because FreeCAD returns non-ASCII text.
7. PowerShell 5.1 wraps native stderr in ErrorRecords - avoid `2>&1` on git/uv in scripts; use `ForEach-Object { "$_" }`.
8. `FreeCAD.exe --write-log <file>` writes a log, but with the MCP RPC the Report view snippet is usually more useful.
9. The RPC `execute_code` shares **one persistent namespace** across calls and runs on the GUI thread (blocking calls freeze the UI).

10. **A session's working directory is locked** and cannot be renamed or moved while the session runs. `Move-Item` of a large tree
    fails on locked files; `robocopy /E` copies reliably.
11. The Steam Frame profile
    `valve/frame_controller_valve` is enabled only if the runtime offers `XR_VALVE_frame_controller_interaction`. The full action set is specified in `design.md`.
12. PowerShell scripts are run as `powershell -NoProfile -ExecutionPolicy Bypass -File tools\<script>.ps1`; the default execution policy rejects unsigned scripts.
13. `XR_EXT_render_model` requires `XR_EXT_uuid` on an OpenXR 1.0 instance; without it `xrCreateInstance` fails with a validation error.
14. Runtime controller models exist only after the first successful `xrSyncActions`, and their spaces are locatable only while the session is `FOCUSED` (not `VISIBLE`). A controller that is asleep at the first enumeration gets its model from the periodic re-check. See `controller-models.md`.
15. The pyopenxr 1.1.6302 wrappers for render models do not work as called (UUID default, missing two-call idiom, missing preallocated arrays); `controller-models.md` lists the workarounds.
16. Text sent through the RPC `execute_code` is XML: a snippet file containing a NUL or another control character is rejected (`not well-formed (invalid token)`); runtime strings are printed with `ascii()`.
17. The repo `.gitignore` excludes `__pycache__`, `refs/`, `tools/logs/` and `.mcp.json`; check `git status` before committing.
18. **pivy field names can be shadowed by node methods.** `SoDepthBuffer.write` is the `SoNode.write` method, so the field is set with `node.getField("write").setValue(False)`. `SoMFVec3f.setValues` does not shorten a field: call `setNum(n)` first when a shape is refilled with fewer entries.
19. **Coin text fonts:** `SoFont.name = "Segoe UI:Bold"` selects a Windows system font for `SoText3`; the unset default is a serif face. Unicode text such as the micrometre sign renders.
20. A fresh FreeCAD start has no document (gotcha 5); `tools/snippets/demo_document.py` creates one.
21. **A pivy field lookup costs about 20 microseconds** (`node.field`, and so `node.field = value`, goes through `getField`). Scene code that runs every frame looks its fields up once (`self._at = transform.translation`) and writes only when the value changes (`style.Paint`, `style.Show`): a write also notifies the scene graph, which drops the render caches above the node. Cached fields and guarded writes keep the interface frame with the ten panels of the value module at 0.25 ms of Python; looking the fields up and writing them every frame costs about 1 ms more.
22. **Coin render caches:** a `SoSeparator` keeps a display list of its subgraph while nothing in it changes, but the automatic caching (`renderCaching` AUTO) does not engage in the XR render loop: the carousel with its 16000 glyph triangles then costs 17 ms of CPU per eye (measured in the headset with `xr_profile.py`; the GPU is not the limit), while the same scene costs 1.3 ms with `renderCaching` ON. `style.cached(separator)` switches it on, and every separator that holds text or the rectangles of a panel uses it. A cached separator costs the renderer about 2.5 microseconds per frame, a `SoText3` label about 40 triangles per character (`SoComplexity` changes that for a TrueType font, not for the default one), a `SoCube` 12 triangles and a draw call. The carousel therefore also draws the rectangles of a panel as one `SoFaceSet` with a colour per rectangle (`ring_view._Plates`) and hangs the whole carousel under one transform that follows the controller. A bench through `SoOffscreenRenderer` shows nothing of this: it caches by itself, so only the profiler in the headset measures the render loop.

## Reproducing from scratch

```powershell
winget install FreeCAD.FreeCAD   # or the installer from freecad.org; per-user path assumed by env.ps1 (override: $env:BLOCADVR_FREECAD)
tools\bootstrap.ps1
tools\start-freecad.ps1
uv run --directory refs/freecad-mcp python ../../tools/mcp_smoke_test.py   # whole MCP chain
& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\xr_probe.py # OpenXR runtime/HMD check
```
