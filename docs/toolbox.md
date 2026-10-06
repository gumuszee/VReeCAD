# Toolbox

Every script we built, so nobody reinvents it. All paths relative to the repo root. Keep this table in sync when adding tools.

| Tool | What it does | Usage |
|---|---|---|
| `tools/env.ps1` | Shared path variables (FreeCAD install, Mod dir, addon dirs). Dot-source it. Override FreeCAD path with `$env:BLOCADVR_FREECAD`. | `. tools\env.ps1` |
| `tools/bootstrap.ps1` | Idempotent full environment setup (reference clones, pip deps, uv, junctions, dev-only MCP RPC auto-start + `.mcp.json`). | `tools\bootstrap.ps1` |
| `tools/install-addons.ps1` | Junction our addons into `%APPDATA%\FreeCAD\v1-1\Mod` (no copying; `-Remove` unlinks). | `tools\install-addons.ps1` |
| `tools/start-freecad.ps1` | Launch FreeCAD GUI detached with a log, wait until RPC `:9875` answers. | `tools\start-freecad.ps1 [-Wait 90] [-XrRuntime path.json]` |
| `tools/fc_rpc.py` | Stdlib-only XML-RPC client for the running FreeCAD: `status`, `docs`, `objects <doc>`, `exec "<code>"`/`exec -f file`, `shot out.png [View]`. Importable (`exec_code`). Exit code reflects success. | `python tools\fc_rpc.py exec "print(App.ActiveDocument.Name)"` |
| `tools/mcp_smoke_test.py` | Full-chain MCP test (MCP client -> server -> RPC -> GUI): builds a plate with a hole, checks volume, saves screenshot to `tools/logs/`. | `uv run --directory refs/freecad-mcp python ../../tools/mcp_smoke_test.py` |
| `tools/xr_probe.py` | Standalone OpenXR check: runtime, `XR_KHR_opengl_enable`, instance (API 1.0 then newest), HMD system, GL requirements. Run with FreeCAD's Python. | `& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\xr_probe.py` |
| `tools/xr_probe_paths.py` | Instance-only probe: which input/output paths a runtime accepts for an interaction profile (default Steam Frame). Prints accepted components per hand; `-v` lists every path. | `& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\xr_probe_paths.py [profile] [ext1,ext2] [-v]` |
| `tools/snippets/xr_render_models.py` | FreeCAD-side: enumerate the runtime's controller models, download the glTF assets to the local cache, print node names and a glTF summary (needs a `FOCUSED` session). | `... exec -f tools\snippets\xr_render_models.py` |
| `tools/snippets/xr_render_model_live.py` | FreeCAD-side: per model the hand, location versus the controllers and the animatable node state (pull a trigger while running). | `... exec -f tools\snippets\xr_render_model_live.py` |
| `tools/snippets/report_view.py` | FreeCAD-side snippet: dump the Report view (where addon `print`s go). | `python tools\fc_rpc.py exec -f tools\snippets\report_view.py` |
| `tools/snippets/xr_state.py` | FreeCAD-side: print live OpenXR session state (`SYNCHRONIZED`=headset off, `FOCUSED`=in use). | `... exec -f tools\snippets\xr_state.py` |
| `tools/snippets/offscreen_render.py` | FreeCAD-side: render the active document's scene offscreen from any eye pose/target to a PNG (virtual head, no headset). Parameters are set through globals `RENDER_EYE`, `RENDER_TARGET`, `RENDER_OUT`, `RENDER_SIZE`. | `... exec -f tools\snippets\offscreen_render.py` |
| `tools/lint_imports.py` | Static check of the sources with the standard library only: syntax errors and imported names that are never used. Exit code 1 on a finding. | `& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\lint_imports.py` |
| `tests/` (unit tests) | Pure unit tests without FreeCAD: input edges, profile mapping, glTF parser, Sim pose math, tool registry, navigation, units, carousel logic, layout, the quick radial, toasts, the undo button, tool options, stage mapping, snapping, primitive parameters, the Create tool with fake services, the rigid grab, rotation snap, picking priority and size scaling. | `& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests` |
| `tools/snippets/run_live_tests.py` | FreeCAD-side: runs `tests/live/test_coin.py` (glTF to Coin loader, generated controller shape, Sim session render, interface scene graph, real FreeCAD primitives, picking and the Create and Grab tools in the Sim) inside the GUI. Prints `LIVE TESTS: OK`. Stop the XR viewer first: the run reloads addon modules. | `... exec -f tools\snippets\run_live_tests.py` |
| `tools/snippets/sim_demo.py` | FreeCAD-side: scripted head and controllers (Sim backend) over the active document, with trigger and button edge events, rendered to mono and stereo PNGs. Output folder from global `SIM_DIR`. | `... exec -f tools\snippets\sim_demo.py` |
| `tools/snippets/render_controller_models.py` | FreeCAD-side: build the cached runtime controller models (GLB) and render them from three viewpoints. Output folder from global `RENDER_DIR`. | `... exec -f tools\snippets\render_controller_models.py` |
| `tools/snippets/render_ui.py` | FreeCAD-side: render the interface through the Sim session (carousel on the controller, hover, the quick radial, lifting a face and hiding it, the tip pushed through and held behind a panel, the Create tool (cross, drag ghosts), the Grab tool (hover, selection, move), toasts, a tooltip and an option readout, wrist roll, stacked panels, lifting a panel, scale ruler over a test cube in free and level mode). Output folder from global `RENDER_DIR`, unit system from `UNIT_SYSTEM`. | `... exec -f tools\snippets\render_ui.py` |
| `tools/snippets/demo_document.py` | FreeCAD-side: create a small demo document (plate with a hole and a block) and show it, so the viewer and the Sim have content after a fresh FreeCAD start. | `... exec -f tools\snippets\demo_document.py` |
| `tools/snippets/xr_restart.py` | FreeCAD-side: hot-reload addon modules and restart the XR viewer (fast edit loop; restart FreeCAD for class-identity changes). | `... exec -f tools\snippets\xr_restart.py` |

> Everything under `tools/` is **development tooling**, not shipped with the addon. `fc_rpc.py`, `mcp_smoke_test.py` and the MCP bits only exist to let a developer/agent remote-control a running FreeCAD; the addon never depends on them.

PowerShell scripts run as `powershell -NoProfile -ExecutionPolicy Bypass -File tools\<script>.ps1` (the default policy blocks unsigned scripts).

## Edit loop for addon development

1. Edit files in `freecad/BlocksCAD/`.
2. `python tools\fc_rpc.py exec -f tools\snippets\xr_restart.py` (headset on), watch `report_view.py` for errors.
3. If module-level state/classes changed in a way reload can't handle: close FreeCAD, `tools\start-freecad.ps1`.

## Conventions

- Every reusable script lives in `tools/` with a header comment (purpose, usage) and a row in the table above.
- FreeCAD-side snippets (run inside the GUI) -> `tools/snippets/`; they use underscore-prefixed names to avoid polluting the shared RPC namespace.
- Throw-away experiments go to the session scratchpad, not the repo. Logs/screenshots -> `tools/logs/` (git-ignored).
- Design decisions live in `docs/design.md`, verification state in `docs/verification.md`, environment facts and gotchas in `docs/setup.md`.
