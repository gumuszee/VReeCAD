# VReeCAD

**Parametric CAD modelling in VR, on FreeCAD.** VReeCAD is a FreeCAD workbench (OpenXR) with the simple, direct,
"the hand is the cursor" feel of [Open Blocks](https://github.com/icosa-foundation/open-blocks) and the controller scheme of
[Open Brush](https://github.com/icosa-foundation/open-brush). Every gesture creates or edits a real FreeCAD feature
(Part, PartDesign, Sketcher, Draft, Assembly), so the model stays parametric and opens on the desktop like any other document.

> Prototype (version 0.1.0). Fork of [freecad-xr-workbench](https://github.com/kwahoo2/freecad-xr-workbench) by Adrian Przekwas (LGPL-3.0-or-later);
> the original README is kept in [docs/upstream/](docs/upstream/README-freecad-xr-workbench.md).
> Inspired by Open Blocks and Open Brush (Apache-2.0); not affiliated with Google.

## What it does

- **Create** parametric primitives (box, cylinder, cone, sphere, torus, wedge, prism) by dragging them out on a snap grid with a ghost preview.
- **Select** objects, faces, edges and vertices (FreeCAD's own selection, shared with the desktop), **move, turn and scale** objects, free or locked to the grid and angle step.
- **Push/Pull** flat faces along their normal; the sizes of boxes, cylinders, cones and sketch extrusions change in place, other faces get fuse or cut features.
- **Points**: blocks (solids made of points) whose points are dragged, split and removed, optionally keeping faces flat.
- **Sketch** lines, rectangles, circles and arcs on a plane or on a face, with the constraints the drawing implies; edit points through the solver, dimension lines and radii, extrude to solids.
- **Modify** with booleans (fuse, cut, common), copy, mirror, linear patterns, colours, fillet and chamfer, attach to a face, and assembly joints (fixed, hinge, slider, ball).
- **Values**: selecting an object brings up sliders, a number pad and keys for its sizes and position. Values bind to named **variables** (a `Variables` spreadsheet) and to expressions such as `width * 2 + 10 mm`.
- **Snapping** by guides or by inference (vertices, middles and edges of nearby geometry), with a ruler in the document's unit system while navigating.
- **Interface**: a palette carousel of panels on one controller that the user rearranges, a quick radial of favourite faces, option discs on the thumbstick, toasts, tooltips and a controls card. Runtime-provided controller models, laser or tip pointer.

## Install

**No release is needed.** VReeCAD is Python and uses the repository as it is: the repository root is the addon (`package.xml`, `freecad/VReeCAD/`, `Resources/`). Nothing is compiled or packaged.

Requirements: FreeCAD 1.1 or newer (developed on 1.1.4, Windows 11), an OpenXR runtime with `XR_KHR_opengl_enable` (SteamVR, Monado, ...), and the Python packages `pyopenxr` and `PyOpenGL` in FreeCAD's Python.

1. **Addon Manager (custom repository):** in FreeCAD open Edit, Preferences, Addon Manager, Custom repositories, add `https://github.com/gumuszee/VReeCAD` with the branch `main`, then install VReeCAD from the list and accept the two Python packages. This route is unverified; see [docs/verification.md](docs/verification.md).
2. **By hand:** clone the repository into the `Mod` folder of the FreeCAD user data directory (on Windows `%APPDATA%\FreeCAD\v1-1\Mod\VReeCAD`) and install the packages into FreeCAD's Python:

   ```powershell
   & "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" -m pip install pyopenxr PyOpenGL
   ```

3. **Development setup (Windows):** `tools\bootstrap.ps1` clones the reference repositories, installs the packages and links the working copy into `Mod`, so edits are live after a restart of FreeCAD (see [docs/setup.md](docs/setup.md)):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File tools\start-freecad.ps1
   ```

Start it: open or create a FreeCAD document, switch to the **VReeCAD** workbench, put the headset on and click **Open XR viewer**. Without a document the viewer does not start. The first run shows a controls card over each controller (the **Tutorial** face of the Settings panel shows it again, and the menu button of either controller toggles it).

## Controls

The controls use five abstract inputs per hand, mapped to the physical controls of each controller family by `freecad/VReeCAD/profiles.py`. Two optional inputs, `aux1` and `aux2`, exist only on the Steam Frame left controller.

| Input | Steam Frame | Quest Touch | Index | Vive / WMR |
|---|---|---|---|---|
| Trigger | trigger | trigger | trigger | trigger |
| Grip | squeeze | squeeze | squeeze | squeeze |
| Stick | thumbstick | thumbstick | thumbstick | trackpad (WMR: thumbstick) |
| Stick click | thumbstick click | thumbstick click | thumbstick click | trackpad click on WMR |
| Button 1 (**A**) | right A, left D-pad up | right A, left X | A | menu |
| Button 2 (**B**) | right B, left D-pad down | right B, left Y | B | trackpad click |
| `aux1` / `aux2` | left D-pad left / right | none | none | none |
| Menu | right menu, left view | left menu | none | none |

The text below says **A** and **B** for Button 1 and Button 2. Only the Steam Frame is tested; the other profiles are bound but unverified ([docs/input-profiles.md](docs/input-profiles.md)).

### Hands

| Hand | Default | Carries |
|---|---|---|
| Tool hand | right | the active tool (trigger is the primary action), the navigation modifiers, the pointer |
| Palette hand | left | the palette carousel (or the values carousel), undo and redo shortcuts |

The **Tool hand** face of the Settings panel swaps the roles; everything that belongs to a hand follows and the choice is saved. The D-pad shortcuts belong to the palette hand, so with the tool hand on the left they are not available (B on the tool hand undoes on every controller).

### Tool hand

| Input | Action |
|---|---|
| Trigger | the primary action of the tool; on the carousel: press and release on a face to activate it, hold on a face (0.4 s) to lift it, hold on a title bar to lift the panel |
| Grip | grab the world (see Navigation) |
| Stick | the options of the tool (see Tool options) |
| Stick click | the tool decides: Select goes back to Object and Replace, Points back to Move and Free faces; the other tools ignore it. While gripping: reset the view |
| A | outside a gesture: hold for the quick radial. During a gesture: cycle the placement Snap, Grid, Free. While gripping: level mode |
| B | outside a gesture: tap undoes, hold (0.4 s) redoes. During a gesture: fix or release what is held. While gripping: hold the scale at 1 : 1 |

### Palette hand

| Input | Action |
|---|---|
| Stick left / right | turn the carousel one side per flick |
| Trigger | with an object selected: swap the palette carousel and the values carousel (the Move tool keeps this trigger for scaling during a grab) |
| Grip | grab the world, alone or together with the other grip |
| A | pin the carousel visible, or release it |
| Stick click | with a grip held: reset the view |
| `aux1`, `aux2` | undo, redo (Steam Frame D-pad left and right) |
| Menu | show or hide the controls cards |

Controllers without `aux1` and `aux2` undo and redo through B on the tool hand and the Edit panel.

### Navigation (grips)

| Gesture | Action |
|---|---|
| One grip | hold the world in the hand: it follows the position and rotation of the hand (free orbit, the model can tip in every direction) |
| Both grips | two-point transform: the world moves with the midpoint, rotates with the line between the hands and scales with their distance (1 : 100 to 100 : 1). A ruler between the hands reads the length in the document unit |
| A held (tool hand) | level mode: rotation about the vertical axis only, the bottom of the model stays down |
| B held (tool hand) | the scale animates to 1 : 1 and stays there while the button is held |
| Stick click while gripping | animate to the home pose: 1 : 1, the document origin 30 cm in front of the head at chest height, front view facing away from the head |
| Tip mode | with the **tip** pointer the world is held at the tips instead of the grips, so the tips measure: touch two points and read the distance |

After a two-grip gesture the grip that stays down does nothing until both are released. The carousel hides while gripping. A haptic tick marks each doubling or halving of the scale.

### Pointing

The tool hand points at the carousel and at the model with either a **laser** (a beam along the tilted aim direction) or a **tip** (a cone ending in a small sphere in front of the controller; panels and the model react to what the tip touches). Both are switched with the **Pointer** face; the **Angle** (tilt, default 15 degrees) and **Length** (tip distance, default 40 mm) sliders sit on the Pointer panel. The tip is the cursor of every tool.

### Palette carousel

The carousel is a prism around the long axis of the palette controller, with every side visible and a stack of panels on each side. It fades in when the head looks at the controller or at a panel.

| Panel | Faces |
|---|---|
| Tools | Create, Select, Move, Push/Pull, Points, Sketch |
| Edit | Undo, Redo, Delete |
| Modify | Fuse, Cut, Common, Copy, Mirror X, Y, Z, Colour, Pattern X, Y, Z |
| Shape | Extrude, Fillet, Chamfer, Attach, Detach, Fixed joint, Hinge, Slider, Ball joint, Unjoint, Sources |
| View | Reset view, Reload scene, Reset layout, Show hidden, Close VR |
| Pointer | Pointer (laser or tip), sliders Angle and Length |
| Settings | Tool hand, Small lengths, Tutorial, Snapping (guides or inference), sliders Grid (1 to 100 mm) and Angle step (5 to 90 degrees) |

- **Activate a face:** press the trigger on it and release over the same face within 0.4 s.
- **Sliders** are dragged by their bar: hold the trigger on the bar and move along the track.
- **Rearrange panels:** hold the trigger on a title bar and drop the panel next to, above or below another panel, or on the empty side; turn the carousel with the palette stick while holding.
- **Move or hide a face:** hold the trigger on it for 0.4 s, drop it on a slot (an occupied slot swaps) or on the hide slot in a title bar. **Show hidden** brings them back, **Reset layout** restores the defaults.
- **Panel editor:** tap the menu mark at the right end of a title bar to rename a panel, give it a hue and set its size (up to 12 by 8 faces) with an on-screen keyboard.
- The layout is saved in `%APPDATA%\VReeCAD\layout.json` and the settings in `settings.json`.

### Quick radial

Hold **A** on the tool hand (outside gestures and navigation) to open a radial of the eight faces used last. Move the hand in the direction of an item (a tick marks each change) and release A to activate it. Releasing A without moving the hand chooses the **Select** tool, which sits in the middle.

### Tool options

While a tool is active, the stick of the tool hand belongs to its options. Tools with an **option disc** (Create, Select, Move, Points, Sketch) show eight sections like a clock, the first straight up and then clockwise: push the stick toward a section to apply it. The middle shows the current values. A tool without a disc steps its first option with the stick up and down and its second with left and right. The disc hides the pointer while it is shown. The grid and the angle step are not options of a tool: they are the sliders of the Settings panel and apply to every tool.

### Tools

| Tool | Trigger | Disc sections (clockwise from the top) |
|---|---|---|
| **Create** | drag out a shape on the grid (ghost and size readout), release makes it; a tap places a default shape of four grid steps | Box, Cylinder, Cone, Sphere, Torus, Wedge, Prism, Block |
| **Select** | select what the tip touches (Replace, Add or Remove) | Object, Face, Edge, Vertex, Remove, Add (two sections have no function) |
| **Move** | tap selects; hold on an object grabs it and it follows the hand (free, any angle). A at the same time, or the Grid placement, locks the move to grid steps and the turn to angle steps (an orange padlock shows it). The trigger of the other hand during a grab scales a primitive | Move and rotate, Move only |
| **Push/Pull** | press a flat face, move along its normal: out of the solid pushes, into it pulls, in grid steps; release applies | none; the grid is the Settings slider |
| **Points** | on a point: drag it; on an edge (Split): add a point and drag it; on a point (Remove): take it out | Move point, Split edge, Remove point, (gap), Free faces, Flat faces |
| **Sketch** | drag a line, rectangle or circle on a plane or a face; an arc takes two ends then a third point (press again); Edit drags a point through the solver, dimensions a line, drags the radius of a circle or an arc | Rectangle, Circle, Line, Arc, Edit, XY plane, XZ plane, YZ plane |

All tools line a point up with the model (guides or inference, chosen on the Settings panel). The **A** button changes the placement during a gesture: **Snap** (grid and guides), **Grid** (grid only) or **Free** (exactly where the hand is), and a toast names it. A **grip** cancels the gesture, and every gesture is one undo step. The **B** button during a gesture **fixes** what is held (a body, a point of a block, a point of a sketch) or releases it.

### Values and variables

Selecting an editable object brings the **values carousel** onto the palette hand (the trigger of that hand swaps the two carousels). It holds:

| Panel | Use |
|---|---|
| Value | the readout of the picked value, a value slider and a step slider (0.01 to 100 mm) |
| Values | every value of the object, press one to pick it |
| Number pad | digits, Enter, Del and Unit; expressions such as `2*(3 cm+4)` are evaluated |
| Keys | operators, brackets, Previous and Next value, Clear |
| Variables | variables of the document, Make variable, Unbind |
| Colour | twelve swatches that colour the selection |

While the value slider is focused (the tip near it, or the laser over its row) the **stick of the tool hand** steps the picked value up and down. The values are the sizes of a primitive, the dimensions of a sketch, the coordinates of a picked point of a block and the position of any object. **Make variable** turns a value into a named length of the `Variables` spreadsheet; a typed text that uses a variable binds the value to the expression.

### Modify, Shape and Edit faces

All act on the current selection and make one undo step.

| Face | Action |
|---|---|
| Fuse, Common, Cut | `Part::MultiFuse`, `Part::MultiCommon`, `Part::Cut` (everything after the first object is cut away) |
| Copy | a parametric copy laid beside the original |
| Mirror X, Y, Z | a `Part::Mirroring` image 10 mm from the object |
| Pattern X, Y, Z | a Draft array of three |
| Colour | the next colour of eight |
| Extrude | extrudes selected sketches by 20 mm; an outline open at two ends is closed first |
| Fillet, Chamfer | on selected edges (5 mm to begin with, a value on the panels) |
| Attach, Detach | lay one selected face against another through the Attacher, or release |
| Fixed joint, Hinge, Slider, Ball joint, Unjoint | Assembly joints between two selected faces |
| Sources | select the objects a feature is made from, hidden ones included |
| Delete | remove the selected objects |
| Undo, Redo | as B and the D-pad |

Details of every behaviour are in [docs/ux-design.md](docs/ux-design.md).

## Status

| | |
|---|---|
| Version | 0.1.0 |
| Verified on | FreeCAD 1.1.4, Windows 11, SteamVR OpenXR 2.17, Steam Frame |
| Verification | [docs/verification.md](docs/verification.md) lists per feature what was observed in the headset and what is only tested in the headless Sim backend |
| Milestones | M0 platform and interface, M1 Create, M2 Select and Move, M3 value panels and variables, M4 Push/Pull and Modify, M5 Points and blocks, M6 Sketch and Extrude, M7 fillet, chamfer, attach and joints; the plan and decisions are in [docs/design.md](docs/design.md) |
| Other headsets | bindings exist for Quest, Index, Vive, WMR and Pico; untested |

## Repository layout

```
package.xml, LICENSE, Resources/, freecad/VReeCAD/   the addon (FreeCAD loads the repo root as the addon)
docs/       design, UX, licensing, verification status, setup and gotchas, toolbox index, the VR integration layer, analysis of Open Blocks
tests/      unit tests (pure Python; tests/live/ needs the FreeCAD GUI)
tools/      development tooling (PowerShell and Python): bootstrap, launch FreeCAD, remote control, probes, test helpers
refs/       read-only reference clones (git-ignored)
CLAUDE.md   guidance for AI coding sessions working on this repository
```

Unit tests without FreeCAD's GUI:

```powershell
& "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests
```

## Docs

[design](docs/design.md) · [UX design](docs/ux-design.md) · [controller models](docs/controller-models.md) · [input profiles](docs/input-profiles.md) · [verification](docs/verification.md) · [licensing](docs/licensing.md) · [setup and gotchas](docs/setup.md) · [toolbox](docs/toolbox.md) ·
[VR integration layer](docs/analysis-xr-workbench.md) · [analysis: Open Blocks](docs/analysis-open-blocks.md)

## License

LGPL-3.0-or-later, see [LICENSE](LICENSE) and [docs/licensing.md](docs/licensing.md).
