# BlocksCAD - instructions for AI sessions

Goal: parametric CAD modelling in VR on FreeCAD (installed 1.1.4) with Blocks-inspired intuitive controls. This repo
(github.com/gumuszee/BlocksCAD_VR, a fork of kwahoo2/freecad-xr-workbench) **is the addon**. Overview `README.md`;
direction `docs/design.md`; verification state `docs/verification.md`.

## Read first
- `docs/design.md` (decisions D1-D6, architecture, controls, milestones) - the owner's answers there are binding.
- `docs/controller-models.md` and `docs/input-profiles.md` (runtime controller models, measured input components), `docs/setup.md` (environment + **gotchas**), `docs/toolbox.md` (existing tools - extend, don't reinvent), `docs/licensing.md`.
- `docs/analysis-xr-workbench.md` before touching `freecad/BlocksCAD/`.

## Hard rules
- **Never mention Claude/AI in commits or sign off as Claude.** Commits use the owner's git identity (global config: Vojtech Tuma). No `Co-Authored-By`, no "Generated with" lines. Don't push unless asked.
- **No AI/MCP in the addon** (`freecad/`, `Resources/`, `package.xml`). Dev tooling (`tools/`, the freecad-mcp RPC addon in `refs/`) is development-only; the addon must not import or depend on it.
- Strictly parametric CAD: gestures create/edit real FreeCAD features (Part/PartDesign/Sketcher), never baked geometry.
- Keep upstream LGPL headers; new files get the same LGPL-3.0-or-later header + our copyright. See `docs/licensing.md`. Don't use Google's "Blocks" name/logo.
- `refs/` is read-only. Work on the **installed** FreeCAD, not a source build (`refs/FreeCAD` is newer, 27.1-dev).

## Working with the live FreeCAD
- Start `powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-freecad.ps1`; poke `python tools\fc_rpc.py exec "..."` / `exec -f file.py` / `shot`. If the `freecad` MCP server is available natively, its tools hit the same RPC.
- Addon `print()` is only visible in the Report view: `tools/snippets/report_view.py`. XR state: `xr_state.py`. Hot reload: `xr_restart.py`.
- Only the owner can wear the headset: ask for in-headset verification and record the result in `docs/verification.md`; mark unverified claims as such. Prefer the Sim backend / offscreen renders for self-testing (design.md, Test strategy).
- Windows quirks: avoid `2>&1` on native commands in PowerShell 5.1; Python console is cp1252 (force UTF-8); heredocs with apostrophes break the Bash tool - use the Write tool for docs. A session's working directory is locked and cannot be renamed while the session runs.

## Conventions
- New script -> `tools/` (FreeCAD-side snippets in `tools/snippets/`), header comment with purpose/usage, row in `docs/toolbox.md`.
- **Documentation states the current truth in absolute terms.** No relative or temporal wording ("now", "no longer", "renamed", "fixed", "previously", "so far", "yet"), no changelogs or journals in the repo. History, rationale of past changes and session notes belong in Claude's memory; git history carries the code changes.
- Decisions and design -> `docs/design.md`; verification state -> `docs/verification.md`; environment facts and gotchas -> `docs/setup.md`; keep the README status table accurate.
- Small, focused commits with descriptive messages (imperative subject, body explains why). Never commit `refs/`, logs, `.mcp.json`, `__pycache__`.
