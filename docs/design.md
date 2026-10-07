# BlocksCAD design

Status: agreed direction. Milestone M0 (platform) is implemented except the `rig.py` extraction. The interface foundation is implemented: grip navigation (U1), the palette carousel with panels, sliders and arrangement (U2) and the laser and tip pointer are verified in the headset; the quick radial, the moving and hiding of single faces (U3), tool options, undo and redo on `button2`, toasts and tooltips (U4) the Create tool (M1), the Select and the Move tool (M2), the Sketch tool of M6, the Points tool and the blocks of M5, the Push/Pull tool and the Modify panel with booleans, copies, mirrors, patterns and colour (M4) and the value panels with variables (sliders, number pad, stick steps and variables for the values of the selected object, M3) are tested in the Sim and wait for the headset. Open checks are listed in `verification.md`.
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
| D7 | The UI is driven by the Open Brush control scheme (`ux-design.md`). The upstream interface is not part of the addon and no upstream compatibility is kept. |
| D8 | Only the VR integration of the upstream module remains: the OpenXR session and render loop, input, controller models, the desktop mirror, the spectator camera, and the lighting and anti-aliasing preferences. Its tools, in-world menus, overlays and document code are not part of the addon; every tool is written for this architecture (`tools/`) and sees only the `InputFrame` and its services. |

## Architecture

Python addon (`freecad.BlocksCAD`), no FreeCAD C++ changes. Layers, bottom-up (`*` marks planned modules):

```
backends/   openxr_input.py   action set, bindings per profile, polling into InputFrame, haptics
            openxr_models.py  runtime-provided controller models (XR_EXT_render_model)
            sim.py            scripted head + 2 controllers, offscreen mono/stereo render, no headset  <- test + desktop mode
input.py    InputFrame: head pose, per hand {aim/grip pose, trigger, grip, stick xy+click, button1, button2, menu, aux1, aux2}; edge events
profiles.py abstract input -> OpenXR path per interaction profile (data, see input-profiles.md)
gltf.py     GLB reader;  render/  gltf_coin.py (glTF -> Coin3D), controller_shape.py (generated), offscreen.py (image render)
commonXR.py XRwidget: OpenXR session, swapchains, Coin scene, render loop, the tool manager and the services of the tools (to be split: rig*);  controllerXR.py (the scene node of a controller)
core/       mathutil.py (vector/quaternion math), navigation.py (grip navigation, home pose), units.py (measurement systems, ruler ticks), stage.py (stage to document coordinates), snapping.py (grid, drag box), grab.py (rigid grab, rotation snap, what the cursor touches), selecting.py (combining a touched element with the selection), values.py (expressions of the keypad, the state of the value editor); transactions*
ui/         controller.py (navigation + carousel + ruler + actions), ring.py (carousel logic and geometry), ring_view.py, radial.py (quick radial logic and favourites), radial_view.py (the quick radial and the option discs of the tools), ruler.py, pointer.py (laser and tip), pointing.py (pointer pose), settings.py (user settings), style.py (colours, font), layout.py (faces, panels, sides, hidden faces, JSON), defaults.py; options.py (tool options on the stick), undo_button.py, toast.py (toasts, tooltip timing), feedback_view.py (toasts, tooltip, readout), value_module.py (the value panels of the carousel: faces, pages, sliders, keys, stick)
tools/      base.py (Tool, ToolOption, hint), registry.py, manager.py, touch.py (the base of the tools that touch), primitives.py (the Create tool), select.py (the Select tool), move.py (the Move tool), pushpull.py (the Push/Pull tool), points.py (the Points tool), sketch.py (the Sketch tool); new tools: one module each
core/*      picking/highlight, transactions (undo), parameter binding (further modules); render/ghost.py (the preview of a shape being made), render/highlight.py (hover and selection), render/model_anchor.py (where a button of a controller model is: the padlock hint)
cad/*       thin wrappers creating/editing FreeCAD features: primitives.py (Part primitives, implemented), block.py and blockgeom.py (the block of points and its geometry), sketching.py and sketchinfer.py (sketches and the constraints a shape implies), meshes.py (preview meshes of the primitives, pure Python), picking.py (what the hand touches, the selection), edit.py (placement, size properties and deleting objects), combine.py (booleans and copies), edges.py (fillets and chamfers of edges), attach.py (attaching an object to a face of another), joints.py (assemblies and joints), duplicate.py (mirrors and patterns), colour.py (the colour of an object), pushpull.py (pushing and pulling a face), values.py (the values of an object for the value panel), variables.py (the Variables spreadsheet); Sketcher, PartDesign, Attacher (planned)
```

Rules:
- Tools see only `InputFrame` + services (`snap`, `pick`, `preview`, `doc`, `ui`); they never touch OpenXR. That is what makes the sim backend and tests possible.
- Gesture = Coin preview only; **commit on release** in one `doc.openTransaction()` -> one undo step.
- Everything created is a normal FreeCAD feature with meaningful properties/expressions.
- Handedness is a preference (dominant = tool hand, other = palette hand).

## Interaction design

The interface is specified in [ux-design.md](ux-design.md): the Open Brush control scheme adapted to CAD (palette carousel on the off hand controller, grip navigation with two-hand
free orbit/scale, quick radial, modular faces and panels with a user layout). Hardware independence rests on the five abstract inputs per hand (`input-profiles.md`).

### The Blocks-like core: "move points"
A parametric solid made of **editable points**: `BlocksCAD::Block` (FeaturePython, a polyhedron: `Vertices` (VectorList) + `Faces` (index lists), solid built with OCCT).
Grab a vertex, drag, snap (grid / other vertices / edges / faces / work planes); vertex positions are the parameters, so they can carry
expressions, be driven from spreadsheet variables, be constrained (planar faces, fixed distance, symmetry, aligned-with) and can be typed in via the value panel.
Non-planar results are prevented (triangulate or constrain). Same "grab a point" gesture also edits: sketch points (solver keeps constraints),
primitive handles (box face -> Length/Width/Height), Pad/Pocket length, fillet radius, placement.

### Values, dimensions, variables
- Every drag shows the live value next to the hand (units from FreeCAD preferences).
- The **value panels** follow the selection: four panels on a carousel side of their own on the palette hand appear while an editable object is selected, with no mode and no extra input (sliders focused by approach and dragged by their bar, number pad with expressions, keys; the stick up and down step the focused value, see `ux-design.md`); named variables such as `width * 2` bind values through a fourth panel (see `ux-design.md`, Variables).
- Editing a dimension is the same gesture everywhere: point at it -> keypad -> Enter. Variables are aliases in a Spreadsheet named `Variables` (created with the first one); the Variables panel lists them and a value is bound with `Variables.<name>` expressions.

### Alignment and constraints
- Snapping engine with visible guides (axis, parallel, perpendicular, equal length, midpoint, tangent) like Blocks' snap hints.
- 3D alignment is **parametric**: objects attach via FreeCAD's Attacher (`AttachmentSupport` + `MapMode` + `AttachmentOffset`), not baked placement.
- Sketching on any plane/face in 3D: lines/arcs/circles/rects with **auto-inferred Sketcher constraints** (coincident, horizontal, vertical, tangent...), dimensions via the value panel; the solver result is shown live.

## Tool roadmap (milestones)
| M | Deliverable |
|---|---|
| U1, U2, pointer | **UX foundation, implemented**: world navigation, palette carousel with faces, panels and sliders, laser and tip pointer. See `ux-design.md` |
| U3 | **UX foundation, implemented**: quick radial on `button1` of the tool hand, moving single faces between slots and panels, hiding faces and showing them again, faces activate on trigger release. See `ux-design.md` |
| U4 | **UX foundation, implemented**: tool options on the stick with a readout, undo and redo on `button2`, toasts, tooltips. See `ux-design.md` |
| M0 | **Platform** (implemented, except the `rig.py` split of `commonXR.py`): backends/input/render split; complete action set (trigger, grip, stick+click, two buttons, menu, haptics) bound for Frame/Touch/Index/Vive/WMR/Pico per `input-profiles.md`; `InputFrame`; runtime-provided controller models with a generated fallback (`controller-models.md`); **Sim backend + offscreen render + test harness**; tool registry and manager |
| M1 | **Implemented**: primitives (box, cylinder, cone, sphere, torus, wedge, prism) with snap grid, ghost preview, live dimension, undo/redo: the Create tool (`tools/primitives.py`, `cad/primitives.py`). See `ux-design.md`, Create tool |
| M2 | **Implemented**: hover highlight and selection (vertex/edge/face/object), the Select tool (objects, faces, edges and vertices, many at once) and the Move tool (move and rotate on a grid, two-hand scale through the size parameters of the primitives; `tools/select.py`, `tools/move.py`, `tools/touch.py`, `cad/picking.py`, `cad/edit.py`, `core/grab.py`, `core/selecting.py`, `render/highlight.py`), world navigation (U1). See `ux-design.md`, Select tool and Move tool |
| M3 | **Implemented**: value panels (sliders, number pad, expressions and stick steps for the size and position of the selected object; `ui/value_module.py`, `core/values.py`, `cad/values.py`) and variables (a `Variables` spreadsheet, values bound to expressions of it, the Variables panel; `cad/variables.py`) |
| M4 | **Implemented**: booleans (fuse, cut and common as `Part::MultiFuse`, `Part::Cut` and `Part::MultiCommon`), copy, mirror, pattern (Draft array), colour and delete (Modify and Edit panels; `cad/combine.py`, `cad/duplicate.py`, `cad/colour.py`, `cad/edit.py`), and the Push/Pull tool (a face extruded and fused or cut; `tools/pushpull.py`, `cad/pushpull.py`). Push/pull of curved faces and of faces of a sketch based solid (Pad/Pocket) are not built |
| M5 | **Block**: a point-based solid (`cad/block.py`, `cad/blockgeom.py`), made with the Create tool and edited with the Points tool (`tools/points.py`): point move on a grid, edge split and points bound to variables are implemented; constraints (planar faces, distances) are not built |
| M6 | **Implemented**: sketching in space with the Sketch tool (lines, rectangles, circles on a plane or an attached face, auto-inferred constraints, point drag through the solver, named dimensions edited on the value panels) and the Extrude action; `tools/sketch.py`, `cad/sketching.py`, `cad/sketchinfer.py`. Arcs, tangent and parallel inference, symmetry and further sketch tools (trim, offset) are not built |
| M7 | Fillet and chamfer of selected edges (`Part::Fillet` and `Part::Chamfer` from the Shape panel, the size is a value; `cad/edges.py`) and Attacher-based placement (Attach and Detach on the Shape panel: a face of one object mated with a face of another through `AttachmentSupport`, `MapMode` and `AttachmentOffset`; `cad/attach.py`) are **implemented**. and joints between two faces through the Assembly workbench (Fixed, Hinge, Slider, Ball; `cad/joints.py`) are **implemented**. Not built: guides |
| M8 | Polish: haptics, tool tips, onboarding, preferences/remap, performance, docs, packaging for Addon Manager |

## Test strategy (no human in the loop where possible)
1. **Unit-ish**: tools driven by synthetic `InputFrame` sequences against a real FreeCAD document (headless `freecadcmd` or live via `fc_rpc`); assert feature types/properties/undo.
2. **Visual**: the Sim backend sets HMD and controller poses from a script and renders the scene offscreen (`SoOffscreenRenderer`, raw RGB buffer saved through Qt; FreeCAD's Coin has no image-writer plugin) to PNG, optionally side-by-side stereo like the mirror window. This provides "movement in VR space" for testing without a headset; `tools/snippets/offscreen_render.py` renders the document scene from any eye pose.
3. **In-headset checklist** per milestone, run by the owner; results are recorded in `verification.md`.
4. Real-device facts that sims cannot prove (comfort, tracking, button feel) stay explicitly marked *unverified* until the owner confirms.

## Risks / open items
- The addon binds the physical controls listed in `input-profiles.md`.
- Python per-frame cost: keep gesture math light; do OCCT work on release only.
- FeaturePython `Block` objects need the addon to be installed to recompute on reopen (shape is cached; document remains viewable without it).
- Controller models come from the runtime and are not bundled (`controller-models.md`); the repository contains no controller meshes.
- Naming: see `licensing.md` (trademark and an existing product called "BlocksCAD").

## Known limitations
- `commonXR.py` hosts the OpenXR session, the render loop and the services of the tools in one module; the extraction into `rig.py` is open.
- The model tree and the task panel of FreeCAD are not shown in the headset; the desktop window shows them.
- Handedness is fixed: the left controller carries the carousel, the right controller is the tool hand.
- Only the Steam Frame controllers are tested; the other profiles are bound but unverified (`verification.md`).
