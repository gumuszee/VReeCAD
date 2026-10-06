# BlocksCAD design

Status: agreed direction. Milestone M0 (platform) is implemented except the `rig.py` extraction; its in-headset checks are listed in `verification.md`.
Inspiration: Open Blocks' simple direct manipulation; substance: real parametric CAD in FreeCAD.

## Decisions (from the project owner, 2026-10-06)

| # | Decision |
|---|---|
| D1 | Hardware: Steam Frame + Steam Frame controllers (eye/finger tracking exist but are **not** used). Per hand we rely only on: **thumbstick (+click), 2 face buttons, trigger, grip** - this also fits Meta Quest Touch controllers. Keep wide controller compatibility. |
| D2 | Core flow like Blocks: **moving points in space**. Then primitives, push/pull, booleans. Eventually all CAD features: sketches, **constraints, alignment, entering values/dimensions/variables** are imperative. Free-hand-only geometry is useless for CAD. Creative freedom to add useful features. |
| D3 | **Strictly parametric**, pure CAD. No direct-edit escape hatch. |
| D4 | The addon is reworked freely; upstream is the starting point and is not merged from. (Licence check: `licensing.md`.) |
| D5 | **No MCP / AI inside the addon, ever.** Any AI integration is a separate addon so VR works without AI. Dev tooling that talks to FreeCAD (`tools/`, MCP RPC addon) is development-only and the addon must not import it. |
| D6 | Desktop mirror ("Enable mirror") is useful for testing/screenshots. Autonomous testing without a person moving in VR is a goal: see *Test strategy*. |
| D7 | The UI is driven by the Open Brush control scheme (`ux-design.md`). The inherited interface is replaced: no upstream compatibility is kept, and the inherited tools remain only as faces until new tools replace them. |

## Architecture

Python addon (`freecad.BlocksCAD`), no FreeCAD C++ changes. Layers, bottom-up (`*` marks planned modules):

```
backends/   openxr_input.py   action set, bindings per profile, polling into InputFrame, haptics
            openxr_models.py  runtime-provided controller models (XR_EXT_render_model)
            sim.py            scripted head + 2 controllers, offscreen mono/stereo render, no headset  <- test + desktop mode
input.py    InputFrame: head pose, per hand {aim/grip pose, trigger, grip, stick xy+click, button1, button2, menu}; edge events
profiles.py abstract input -> OpenXR path per interaction profile (data, see input-profiles.md)
gltf.py     GLB reader;  render/  gltf_coin.py (glTF -> Coin3D), controller_shape.py (generated), offscreen.py (image render)
commonXR.py XRwidget: OpenXR session, swapchains, Coin scene, render loop, inherited interact_* handlers (to be split: rig*)
ui/         palette.py + palette_view.py (radial palette); panels*, numeric keypad*, value field*, tool tips*, toasts*
tools/      base.py, registry.py, manager.py, legacy.py (the six inherited modes as tools); new tools: one module each
core/*      snapping, picking/highlight, preview ghosts, transactions (undo), units, parameter binding
cad/*       thin wrappers creating/editing FreeCAD features (Part primitives, Sketcher, PartDesign, booleans, Attacher)
```

Rules:
- Tools see only `InputFrame` + services (`snap`, `pick`, `preview`, `doc`, `ui`); they never touch OpenXR. That is what makes the sim backend and tests possible.
- Gesture = Coin preview only; **commit on release** in one `doc.openTransaction()` -> one undo step.
- Everything created is a normal FreeCAD feature with meaningful properties/expressions.
- Handedness is a preference (dominant = tool hand, other = palette hand).

## Interaction design

The interface is specified in [ux-design.md](ux-design.md): the Open Brush control scheme adapted to CAD (palette ring on the off hand, grip navigation with two-hand
move/rotate/scale, quick radial, modular faces and pages with a user layout). Hardware independence rests on the five abstract inputs per hand (`input-profiles.md`).

### The Blocks-like core: "move points"
A parametric solid made of **editable points**: `BlocksCAD::Block` (FeaturePython, a polyhedron: `Vertices` (VectorList) + `Faces` (index lists), solid built with OCCT).
Grab a vertex, drag, snap (grid / other vertices / edges / faces / work planes); vertex positions are the parameters, so they can carry
expressions, be driven from spreadsheet variables, be constrained (planar faces, fixed distance, symmetry, aligned-with) and can be typed in via the value panel.
Non-planar results are prevented (triangulate or constrain). Same "grab a point" gesture also edits: sketch points (solver keeps constraints),
primitive handles (box face -> Length/Width/Height), Pad/Pocket length, fillet radius, placement.

### Values, dimensions, variables
- Every drag shows the live value next to the hand (units from FreeCAD preferences).
- Face button 2 / pointing at a value opens the **numeric panel** (keypad + expression line: `Spreadsheet.width * 2`, named variables).
- Editing a dimension is the same gesture everywhere: point at it -> keypad -> Enter. Variables/aliases live in a Spreadsheet (created on demand); the HUD lists them.

### Alignment and constraints
- Snapping engine with visible guides (axis, parallel, perpendicular, equal length, midpoint, tangent) like Blocks' snap hints.
- 3D alignment is **parametric**: objects attach via FreeCAD's Attacher (`AttachmentSupport` + `MapMode` + `AttachmentOffset`), not baked placement.
- Sketching on any plane/face in 3D: lines/arcs/circles/rects with **auto-inferred Sketcher constraints** (coincident, horizontal, vertical, tangent...), dimensions via the value panel; the solver result is shown live.

## Tool roadmap (milestones)
| M | Deliverable |
|---|---|
| U1 to U4 | **UX foundation** (before M1): world navigation, palette ring with faces and pages, quick radial, layout customization, tool options. See `ux-design.md` |
| M0 | **Platform** (implemented, except the `rig.py` split of `commonXR.py`): backends/input/render split; complete action set (trigger, grip, stick+click, two buttons, menu, haptics) bound for Frame/Touch/Index/Vive/WMR/Pico per `input-profiles.md`; `InputFrame`; runtime-provided controller models with a generated fallback (`controller-models.md`); **Sim backend + offscreen render + test harness**; tool registry wrapping the inherited tools; radial palette skeleton |
| M1 | Primitives (box, cylinder, cone, sphere, torus, wedge, prism) with snap grid, ghost preview, live dimension, undo/redo |
| M2 | Selection/hover highlight (vertex/edge/face/object), Grab tool (move/rotate, two-hand scale -> parameters), world navigation |
| M3 | Value panel: keypad + expressions + variables spreadsheet; property editing from VR |
| M4 | Push/pull (Pad/Pocket/offset face), booleans (fuse/cut/common), copy/mirror/pattern, delete, colour |
| M5 | **Block**: point-based parametric solid, vertex move/add/split, planarity & distance constraints |
| M6 | Sketching with auto-constraints and dimensions; sketch-point drag |
| M7 | Alignment: guides, Attacher-based placement, assembly joints (FreeCAD Assembly), fillet/chamfer |
| M8 | Polish: haptics, tool tips, onboarding, preferences/remap, performance, docs, packaging for Addon Manager |

## Test strategy (no human in the loop where possible)
1. **Unit-ish**: tools driven by synthetic `InputFrame` sequences against a real FreeCAD document (headless `freecadcmd` or live via `fc_rpc`); assert feature types/properties/undo.
2. **Visual**: the Sim backend sets HMD and controller poses from a script and renders the scene offscreen (`SoOffscreenRenderer`, raw RGB buffer saved through Qt; FreeCAD's Coin has no image-writer plugin) to PNG, optionally side-by-side stereo like the mirror window. This provides "movement in VR space" for testing without a headset; `tools/snippets/offscreen_render.py` renders the document scene from any eye pose.
3. **In-headset checklist** per milestone, run by the owner; results are recorded in `verification.md`.
4. Real-device facts that sims cannot prove (comfort, tracking, button feel) stay explicitly marked *unverified* until the owner confirms.

## Risks / open items
- The addon binds the physical controls listed in `input-profiles.md`; the inherited code binds only stick, trigger and pose.
- Python per-frame cost: keep gesture math light; do OCCT work on release only.
- FeaturePython `Block` objects need the addon to be installed to recompute on reopen (shape is cached; document remains viewable without it).
- Controller models come from the runtime and are not bundled (`controller-models.md`); the repository contains no controller meshes.
- Naming: see `licensing.md` (trademark and an existing product called "BlocksCAD").
