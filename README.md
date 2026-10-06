# BlocksCAD

**Intuitive parametric CAD modelling in VR for FreeCAD.** A FreeCAD workbench (OpenXR) that brings the simple, direct,
"hand is the cursor" feel of [Open Blocks](https://github.com/icosa-foundation/open-blocks) to real parametric CAD:
primitives, push/pull, booleans, moving points in space, sketches, constraints, alignment, and typed dimensions/variables.

> Early prototype (v0.1.0). Fork of [freecad-xr-workbench](https://github.com/kwahoo2/freecad-xr-workbench) by Adrian Przekwas (LGPL-3.0-or-later);
> upstream's original README is kept in [docs/upstream/](docs/upstream/README-freecad-xr-workbench.md).
> Inspired by Open Blocks / Blocks by Google (Apache-2.0); not affiliated with Google. No AI/MCP code lives in this addon.

## Status

| | |
|---|---|
| Version | 0.1.0 |
| Verified on | FreeCAD 1.1.4, Windows 11, SteamVR OpenXR 2.17, Steam Frame (details: [docs/verification.md](docs/verification.md)) |
| Capabilities | view documents in VR; Open Brush style interface: palette carousel on the left controller (panels of faces, arranged in rows and columns by the user, with sliders), grip navigation (free orbit, level mode, 1 : 1 lock, home reset, scale ruler in the document unit), laser or tip pointer on both controllers; runtime-provided controller models; tool registry with the inherited tools (teleport, line and cube builders, select, drag, working plane, Qt panel overlay); full action set per controller profile; headless Sim backend with offscreen rendering |
| Milestone | M0 platform and the interface foundation (U1, U2, pointer) implemented and owner-verified in the headset; open checks in [docs/verification.md](docs/verification.md); next U3 and U4, then M1 primitives, see [docs/design.md](docs/design.md) |

## Repository layout

```
package.xml, LICENSE, Resources/, freecad/BlocksCAD/   the addon (FreeCAD loads the repo root as the addon)
docs/       design, licensing, verification status, setup + gotchas, toolbox index, analyses of upstream/Open Blocks
tests/      unit tests (pure Python, `tests/live/` needs the FreeCAD GUI)
tools/      dev tooling (PowerShell/Python): bootstrap, launch FreeCAD, remote control, probes, test helpers
refs/       read-only reference clones of FreeCAD, freecad-xr-workbench, open-blocks, freecad-mcp, OpenXR-Docs, open-brush (git-ignored)
CLAUDE.md   guidance for AI coding sessions working on this repo
```

## Use (development setup on Windows)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1       # idempotent: refs, python deps, links the repo into FreeCAD's Mod dir
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-freecad.ps1   # launch FreeCAD (dev remote-control channel on :9875)
# in FreeCAD: open/create a document, switch to the "BlocksCAD" workbench, click "Open XR viewer" (SteamVR must see the headset)
```

Requires an OpenXR runtime with `XR_KHR_opengl_enable` (SteamVR, Monado, ...), plus `pyopenxr` and `PyOpenGL`
(installed into FreeCAD's Python by the bootstrap script).

## Docs
[design](docs/design.md) · [UX design](docs/ux-design.md) · [controller models](docs/controller-models.md) · [input profiles](docs/input-profiles.md) · [verification](docs/verification.md) · [licensing](docs/licensing.md) · [setup & gotchas](docs/setup.md) · [toolbox](docs/toolbox.md) ·
[analysis: upstream addon](docs/analysis-xr-workbench.md) · [analysis: Open Blocks](docs/analysis-open-blocks.md)
