# BlocksCAD design

Status: agreed direction; milestone M0 is in progress.
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

## Architecture

Python addon (`freecad.BlocksCAD`), no FreeCAD C++ changes. Layers, bottom-up:

```
backends/   openxr.py  (session, swapchains, action sets, poses, haptics - from upstream commonXR, cleaned)
            sim.py     (scripted/desktop input: fake HMD + 2 controllers, no headset)       <- test + desktop mode
input.py    InputFrame: hmd pose, per hand {pose, trigger, grip, stick xy+click, btn_a, btn_b, menu}; edge events (pressed/released)
rig.py      Coin scene root: world transform, controller models, rays, tips, HUD anchors, comfort (vignette later)
render.py   per-eye render (openxr) | offscreen render to PNG (sim/test)
ui/         radial palette, panels, numeric keypad, value field, tool tips, toasts       (Coin-based; Qt overlay stays for FreeCAD panels)
tools/      Tool base class + registry; one module per tool
core/       snapping, picking/highlight, preview ghosts, transactions (undo), units, parameter binding
cad/        thin wrappers creating/editing FreeCAD features (Part primitives, Sketcher, PartDesign, booleans, Attacher)
```

Rules:
- Tools see only `InputFrame` + services (`snap`, `pick`, `preview`, `doc`, `ui`); they never touch OpenXR. That is what makes the sim backend and tests possible.
- Gesture = Coin preview only; **commit on release** in one `doc.openTransaction()` -> one undo step.
- Everything created is a normal FreeCAD feature with meaningful properties/expressions.
- Handedness is a preference (dominant = tool hand, other = palette hand).

## Interaction design (hardware-agnostic, 5 inputs per hand)

Dominant hand = **tool hand**: the controller tip is the cursor (touch/near geometry; ray for far targets).
Off hand = **palette hand**: carries the tool belt and info.

| Input | Dominant (tool) hand | Off (palette) hand |
|---|---|---|
| Trigger | primary action of active tool (place, drag, confirm) | secondary/modifier action of the tool (e.g. hold to disable snap, second point) ; UI "click" when pointing at a panel |
| Grip | grab object / grab world (move, rotate; with both grips: scale/rotate world) | grab world / second hand for scale |
| Face button 1 (A / X) | confirm / cycle sub-mode of the tool (e.g. pad<->pocket) | open radial tool palette (hold, stick selects, release picks) |
| Face button 2 (B / Y) | undo (tap) / redo (hold) | open value panel (keypad) for the active parameter |
| Thumbstick | tool option: grid size / segments / snap angle (up-down), cycle shape (left-right) | locomotion: move + snap/smooth turn (comfort option) |
| Stick click | reset view / re-centre | toggle snapping guides |

Mapping is data-driven (`input_map`), remappable in preferences. Vive/WMR (no face buttons) get a fallback layout.

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
| M0 | **Platform**: split `commonXR.py` into backends/input/rig/render; new action set (trigger, grip, stick+click, 2 face buttons, menu, haptics) bound for Frame/Touch/Index/Vive/WMR/Pico; `InputFrame`; **Sim backend + offscreen render + test harness**; Tool registry wrapping old tools (no regression); radial palette skeleton; own controller models |
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
- Frame-controller OpenXR profile (`XR_VALVE_frame_controller_interaction`) input paths must be confirmed against the spec/runtime (the upstream addon binds only stick, trigger and pose).
- Python per-frame cost: keep gesture math light; do OCCT work on release only.
- FeaturePython `Block` objects need the addon to be installed to recompute on reopen (shape is cached; document remains viewable without it).
- The inherited controller `.iv` models have no stated licence: they are replaced by own models in M0.
- Naming: see `licensing.md` (trademark and an existing product called "BlocksCAD").
