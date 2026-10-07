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
| Capabilities | view documents in VR; Open Brush style interface: palette carousel on the left controller (panels of faces, arranged in rows and columns by the user, single faces moved or hidden, with sliders), quick radial of favourite faces on `button1` of the tool hand, grip navigation (free orbit, level mode, 1 : 1 lock, home reset, scale ruler in the document unit), laser or tip pointer on both controllers; the Create tool (box, cylinder, cone, sphere, torus, wedge and prism as FreeCAD features, dragged out on a snap grid with a ghost preview), the Select tool (touch and select objects, faces, edges or vertices, many at once, with add and remove) and the Move tool (touch, select, move, turn and scale objects, free or locked to the grid and angles with the A button), both with hover and selection highlights; a release of the A button without moving the hand chooses the Select tool; option discs on the thumbstick for the three tools; runtime-provided controller models; tool registry and manager; full action set per controller profile; headless Sim backend with offscreen rendering |
| Milestone | M0 platform and the interface foundation: U1, U2 and the pointer are owner-verified in the headset, U3 (quick radial, moving and hiding faces) and U4 (tool options, undo and redo on `button2`, toasts, tooltips) are implemented and tested in the Sim, as is M1 (the Create tool: parametric primitives dragged out in space on a snap grid); open checks in [docs/verification.md](docs/verification.md); M2 (hover highlight, the Select tool and the Move tool: select, move, turn and scale objects) is implemented and tested in the Sim; the value panels of M3 (sliders, a number pad and keys for the size and position of the selected object appear on the left-hand carousel with the selection, with no mode to enter; the stick steps the focused value) is implemented and tested in the Sim, as is the first part of M5 (blocks made of points, moved and split with the Points tool), variables (named lengths in a `Variables` spreadsheet that values are bound to by expressions, with their own panel) complete M3 and are implemented and tested in the Sim; M4 (the Push/Pull tool; the Modify panel with the booleans fuse, cut and common, copy, mirror, pattern and colour) is implemented and tested in the Sim, see [docs/design.md](docs/design.md) |

## Repository layout

```
package.xml, LICENSE, Resources/, freecad/BlocksCAD/   the addon (FreeCAD loads the repo root as the addon)
docs/       design, licensing, verification status, setup + gotchas, toolbox index, the VR integration layer, analysis of Open Blocks
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
[VR integration layer](docs/analysis-xr-workbench.md) · [analysis: Open Blocks](docs/analysis-open-blocks.md)
