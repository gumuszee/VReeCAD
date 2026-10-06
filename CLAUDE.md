# BlocksCAD - instructions for AI sessions

Goal: parametric CAD modelling in VR on FreeCAD (installed 1.1.4) with Blocks-inspired intuitive controls. This repo
(github.com/gumuszee/BlocksCAD_VR, a fork of kwahoo2/freecad-xr-workbench) **is the addon**. Overview `README.md`;
direction `docs/design.md`; verification state `docs/verification.md`.

## Read first
- `docs/design.md` (decisions D1-D7, architecture, milestones) and `docs/ux-design.md` (the Open Brush derived UI; reference code in `refs/open-brush`) - the owner's answers there are binding.
- `docs/controller-models.md` and `docs/input-profiles.md` (runtime controller models, measured input components), `docs/setup.md` (environment + **gotchas**), `docs/toolbox.md` (existing tools - extend, don't reinvent), `docs/licensing.md`.
- `docs/analysis-xr-workbench.md` before touching `freecad/BlocksCAD/`.

## Hard rules
- **Never mention Claude/AI in commits or sign off as Claude.** Commits use the owner's git identity (global config: Vojtech Tuma). No `Co-Authored-By`, no "Generated with" lines. Don't push unless asked.
- **No AI/MCP in the addon** (`freecad/`, `Resources/`, `package.xml`). Dev tooling (`tools/`, the freecad-mcp RPC addon in `refs/`) is development-only; the addon must not import or depend on it.
- Strictly parametric CAD: gestures create/edit real FreeCAD features (Part/PartDesign/Sketcher), never baked geometry.
- Keep upstream LGPL headers; new files get the same LGPL-3.0-or-later header + our copyright. See `docs/licensing.md`. Don't use Google's "Blocks" name/logo.
- **Never use em-dashes, en-dashes or double hyphens as punctuation** in comments, docs, commit messages or replies (use commas, colons, parentheses). Literal command-line flags are exempt.
- `refs/` is read-only. Work on the **installed** FreeCAD, not a source build (`refs/FreeCAD` is newer, 27.1-dev).

## Working with the live FreeCAD
- Start `powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-freecad.ps1`; poke `python tools\fc_rpc.py exec "..."` / `exec -f file.py` / `shot`. If the `freecad` MCP server is available natively, its tools hit the same RPC.
- Addon `print()` is only visible in the Report view: `tools/snippets/report_view.py`. XR state: `xr_state.py`. Hot reload: `xr_restart.py`.
- Only the owner can wear the headset: ask for in-headset verification and record the result in `docs/verification.md`; mark unverified claims as such. Prefer the Sim backend / offscreen renders for self-testing (design.md, Test strategy).
- Windows quirks: avoid `2>&1` on native commands in PowerShell 5.1; Python console is cp1252 (force UTF-8); heredocs with apostrophes break the Bash tool - use the Write tool for docs. A session's working directory is locked and cannot be renamed while the session runs.

## Tests
- Pure unit tests (no FreeCAD): `& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests`. GUI-dependent tests: `& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\run_headless_tests.py --render` runs them in a separate headless process and never touches the running FreeCAD or the viewer (use it whenever the headset may be in use; `tools\run_headless_render.py` does the same for the render snippets). `python tools\fc_rpc.py exec -f tools\snippets\run_live_tests.py` runs them in the live GUI and reloads modules there: close the viewer first and only when nobody wears the headset. Run the unit tests, the live tests and `tools\lint_imports.py` before committing addon changes.
- Tools are classes in `freecad/BlocksCAD/tools/` (registered with `@register`); they see only the `InputFrame`. Drive them headless with `backends/sim.py` (`tools/snippets/sim_demo.py`).

## Conventions
- New script -> `tools/` (FreeCAD-side snippets in `tools/snippets/`), header comment with purpose/usage, row in `docs/toolbox.md`.
- **Documentation states the current truth in absolute terms.** No relative or temporal wording ("now", "no longer", "renamed", "fixed", "previously", "so far", "yet"), no changelogs or journals in the repo. History, rationale of past changes and session notes belong in Claude's memory; git history carries the code changes.
- Decisions and design -> `docs/design.md`; verification state -> `docs/verification.md`; environment facts and gotchas -> `docs/setup.md`; keep the README status table accurate.
- Small, focused commits with descriptive messages (imperative subject, body explains why). Never commit `refs/`, logs, `.mcp.json`, `__pycache__`.
