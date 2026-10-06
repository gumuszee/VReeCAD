# Analysis: Open Blocks (inspiration only)

https://github.com/icosa-foundation/open-blocks - community fork of *Blocks by Google* (Apache-2.0, Unity/C#; the main tools are ~9.7k lines).
Trademark: "Blocks" belongs to Google; never use the name or logo (`BRAND_GUIDELINES.md`). We take **interaction ideas**, not code (Unity C# isn't portable here anyway).

Caveat: the interaction description below is from the tool/class structure plus general knowledge of Blocks; before building each
tool, read the matching `.cs` file for exact behaviour (snapping rules, button mapping, options).

## What makes Blocks feel simple
- A **tiny tool set**, each a controller mode (`ControllerMode`): insert volume, insert stroke, reshape, extrude, subdivide, paint, move/grab, delete, plus fuser (union) and flipper.
- **Direct manipulation with the hand as cursor**: the controller tip is the cursor; hover highlights vertex/edge/face to show what a click affects.
- **Snapping + grid** make casual input produce clean geometry; guides appear while dragging.
- **Fearless**: every operation is a `Command` (`model/core/*Command.cs`: AddMesh, MoveMesh, DeleteMesh, CopyMesh, ChangeFaceProperties, Composite...) on a command stack, giving universal undo/redo.
- Palette on the *other* hand (`PaletteController`, `ShapesMenu`, `ToolOptionsPanel`): choose tool/shape/colour; touchpad/stick adjusts options.
- Two-hand grab to move/scale/rotate the world or an object.

## Source map (under `Assets/Scripts/`)
| Path | Content |
|---|---|
| `tools/VolumeInserter.cs` (1.1k lines) | Place + size a primitive by dragging, with snapping & preview. `Primitives.Shape { CONE, SPHERE, CUBE, CYLINDER, TORUS, ICOSAHEDRON }` |
| `tools/Freeform.cs` (1.5k) | Freehand stroke -> swept volume |
| `tools/Extruder.cs`, `ExtrusionOperation.cs` | Pull a face out of a mesh |
| `tools/Reshaper.cs` (1k) | Move vertices/edges/faces (hover-select, grab) |
| `tools/Subdivider.cs` (1.5k) | Split faces/edges to add geometry |
| `tools/Mover.cs`, `Scaler.cs`, `MoveableObject.cs` | Grab, move, rotate, scale objects and the world |
| `tools/Painter.cs`, `Deleter.cs`, `Fuser.cs`, `Flipper.cs`, `Selector.cs` | Material, delete, union, flip normals, selection |
| `model/core/` | `MMesh`, `Face`, `Vertex`, `Model` (scene), `*Command` undo stack, `SnapDetector`, `SpatialIndex`, `MeshValidator` |
| `model/csg/` | Mesh CSG (union/subtract) |
| `model/controller/` | Controller abstraction (`ControllerDeviceOpenXR`), palette, menus, haptics, toolhead animations, sliders |

## The key mismatch with FreeCAD
Blocks = **polygon meshes**, free-form, no design intent. FreeCAD = **BRep + parametric feature tree**.
"Move a vertex" cannot be ported 1:1. Mapping idea (details in `design.md`): *each Blocks gesture becomes the creation or
edit of a parametric FreeCAD feature*, so the result stays editable, dimensioned and AI-addressable.

| Blocks tool | FreeCAD analogue |
|---|---|
| Insert volume | `Part::Box/Cylinder/Sphere/Cone/Torus` (+Wedge/Prism) with dragged size -> real parameters |
| Freeform stroke | polyline/spline on a plane/surface + `Part::Sweep` or Pad of the profile |
| Extrude | PartDesign Pad/Pocket (prototyped upstream) or `Part::Extrusion` |
| Reshape | drag *parameter handles* (box face -> Length/Width/Height, sketch vertex -> sketch point, fillet radius), not raw vertices |
| Subdivide | Fillet / Chamfer on picked edges (nearest CAD analogue); true subdivision has no BRep meaning |
| Move/Scale | `Placement` edit; scale = change size parameters, not a transform |
| Fuse | `Part::MultiFuse / Cut / Common` (parametric booleans) |
| Paint | `ShapeColor` / Material |
| Delete / undo | `doc.removeObject` inside `doc.openTransaction()`; FreeCAD's own undo stack |
