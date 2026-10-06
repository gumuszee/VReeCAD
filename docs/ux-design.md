# UX design

The interface of BlocksCAD follows the control scheme of [Open Brush](https://github.com/icosa-foundation/open-brush) (Apache-2.0), adapted to parametric CAD,
with the direct, "hand is the cursor" feel of Open Blocks. Open Brush code and assets are used as a reference for behaviour only; nothing is copied.
The upstream interface (quick menu on the left trigger, stick locomotion) is not part of BlocksCAD.

## Principles

1. **One finger per job.** The thumb rests on the stick; a task never needs the thumb to hold a face button while the stick is used. Selection by hand movement or by the stick alone, confirmation by trigger or stick click.
2. **Hands, not menus.** Tools live on a palette carried by the off hand; the tool hand points at it. Navigation is grabbing the world with the grips.
3. **Everything is a modular panel.** A face is a button (label, action). Faces sit on panels, panels sit on the sides of a carousel around the palette controller, and the layout is data the user can rearrange.
4. **Readable at arm's length.** Fixed physical sizes (face edge 5 cm, label glyphs about 9 mm), high contrast, backing plates, one sans serif font (Segoe UI Bold) for every label; no overlapping text.
5. **Feedback on every state change.** Haptic tick on hover change and activation, highlight on hover, a short toast for results.
6. **Hardware independent.** Only the five abstract inputs per hand plus the optional `aux1` and `aux2` (`input-profiles.md`); poses decide the rest.
7. **CAD, not painting.** The model is worked on from every angle, so the view rotates freely; levelling is the modifier, not the default.

## Hand roles

| Role | Default | Carries |
|---|---|---|
| Tool hand | right | the active tool (tip, ray, trigger = primary action), the navigation modifiers |
| Palette hand | left | the palette carousel, undo and redo shortcuts |

Handedness is a preference; the roles swap as a whole.

## Navigation (grips)

Derived from Open Brush's world transform, with a free orbit:

- **One grip on empty space:** the world is held in the hand: it follows the position and the rotation of the hand and turns about the hand.
- **Both grips:** two-point transform. The pivot is the midpoint between the hands; the world scales by the ratio of the hand distance, rotates with the line between the hands and moves with the midpoint. Scale is clamped to 1:100 .. 100:1.
- **Free orbit (default):** with one grip the world takes the full rotation of the hand; with two grips it takes the shortest rotation that turns the old hand line into the new one. The model tips over in every direction.
- **Level (hold button1 of the tool hand, A on the Steam Frame):** the rotation is limited to the vertical axis (one grip: the yaw of the hand), so the bottom of the model stays down. Pressing or releasing the modifier mid gesture starts a new gesture from the current pose; nothing jumps. The mode is shown on the plate.
- **Hold 1:1 (hold button2 of the tool hand, B on the Steam Frame, while gripping):** the scale animates to 1 : 1 about the hands (the world point between the hands stays between them) and stays at 1 : 1 for as long as the button is held, however the hands move; the world still follows them. Releasing the button lets the hand distance scale the world again, starting from 1 : 1.
- **Reset (stick click of a gripping hand, or the Reset view face):** animates to the home pose: scale 1 : 1, the document origin 1 m in front of the head (horizontally), at 75 % of the head height above the floor (chest height when standing), turned so that the front view of the document (looking along the document Y axis) points away from the head.
- **Tip mode:** the world is held with the tips instead of the grips. One grip pivots the world about the tip (the point under the tip stays under it while the hand turns), two grips scale and rotate about the midpoint between the tips, and the ruler runs between the tips, so the tips measure: touch two points of the model and read the distance.
- **After a two-grip gesture** the grips rarely let go at the same moment. When one grip is released first, the other does nothing until both are released (the model does not drift while the hands let go one after the other); a new grip after both are released works as usual, and a second grip pressed while the first is still held resumes two-hand navigation.
- While a grip navigates, the carousel hides and the tool is inactive. A haptic tick marks every doubling or halving of the scale.
- A grip pressed on an object grabs that object instead (milestone M2).

### Scale ruler

While both grips hold the world, a line joins the hands and reads as a ruler in the measurement system of the document:

- **Ticks** stand at round lengths of the model as it is at the current scale (1, 2, 5 times a power of ten of the unit), about 7 cm apart on the stage, with a labelled tick at every step and unlabelled ticks between them. The ruler starts at 0 at the left hand.
- **Units** follow the `UnitSystem` property of the active document: metric systems label in micrometres, millimetres, centimetres (Building Euro), metres and kilometres; imperial systems in thou, inches, feet and miles.
- **Summary plate** below the line: the scale ratio (`4 : 1` when the model is enlarged, `1 : 4` when shrunk), the length between the hands in the document unit, and the modes (free orbit or level, and 1 : 1 locked).
- **One grip** has no span to measure: the scale ratio and the modes float above the gripping hand.
- The ruler is drawn on top of everything (no depth test) with a dark outline, so the model never hides it and it reads on light and dark backgrounds. It uses the interface font.

## Palette carousel (palette hand)

The carousel is a prism around the long axis of the palette controller. It is attached to the controller: it follows the position and the rotation of the hand (Open Brush's wand panels).

- **Geometry.** The axis runs along the controller from the grip point forward (the carousel centre is 9 cm in front of the grip point). The side at the front stands on the thumb side of the controller, facing up when the controller is held upright, with its top edge pointing the way the controller points. The other sides stand around the axis at equal angles, and **all sides are visible at all times**. Rolling the wrist rolls the carousel.
- **Panels** are pages of faces (4 columns by 3 rows, face edge 5 cm) with a title bar and nothing else, so no panel space is spent on indicators. A side carries rows of panels: panels next to each other in a row, rows above each other (the first row nearest the user, further rows further forward). The prism radius grows with the number of sides and the width of the panels so that sides do not overlap.
- **Stick left/right turns the carousel** one side per flick (snap with a haptic tick and a short ease). No button is held. Sides that face away from the user are drawn but cannot be pointed at.
- **Visibility:** the carousel fades in when the head looks at the controller (gaze cone of 35 degrees at 0.12 to 0.95 m) and fades out otherwise; it is hidden while gripping. Palette hand `button1` pins it visible or releases it.
- **Pointing:** the tool hand points with its laser or its tip (see Pointer below). The face under the pointer highlights and a haptic tick marks the change. A face is pressed with the trigger and activates when the trigger is released over the same face within 0.4 s; a pointer that leaves the face before the release cancels the press, and a longer hold lifts the face (see Moving and hiding faces).

### Panels (initial)

| Panel | Faces |
|---|---|
| Tools | Teleport, Line, Cube, Select, Drag, Working plane (the inherited tools, until replaced) |
| Edit | Undo, Redo, Delete |
| View | Reset view, Overlays (Model tree and Tasks), Work plane, Reload scene, Reset layout, Show hidden |
| Session | Pointer (laser or tip), Close VR, and the sliders Angle and Length (tip angle and tip length) |

Planned: Create (primitives, milestone M1), Modify (push/pull, boolean, mirror, pattern), Values (numeric keypad, variables, milestone M3), Settings (handedness, comfort, snapping).

### Sliders

A slider is a face that takes a whole row of its panel: the label with the current value on the left, a track and a handle. Point at it (laser) or touch it (tip), **hold the trigger** and move the pointer along the track: the handle follows the pointer projected onto the panel, also beyond the ends of the panel (the value stops at the ends), and the value changes in steps with a small haptic tick on every step. Releasing the trigger ends the drag and saves the setting. A slider goes in the first slot of a row; the other slots of that row stay empty. The Session panel carries the pointer sliders.

### Rearranging panels

Each panel has a title bar with a grip mark on its right. The layout is a JSON document (`%APPDATA%\BlocksCAD\layout.json`, version 4): the panels in order, the side and the row of each panel, the face ids in each slot and the ids of the hidden faces. Defaults come from code. The initial layout has one panel per side.

1. Point the tool hand at a title bar (it highlights) and **hold the trigger**: the panel lifts off the carousel and follows the laser as a small card. The panels close up and one extra empty side ("Drop here") is offered at the end of the carousel.
2. **Turn the carousel** with the palette stick while holding, to bring the target side to the front (only sides facing the user can be pointed at).
3. **Aim at a panel** to choose where the lifted panel goes; an orange bar shows the place and the panel under the laser lights up:
   - the left or right half of the panel: next to it in its row, in front of it (left) or after it (right);
   - the upper or lower quarter of the panel: a new row above or below it;
   - the empty slot of an empty side: that side, alone.
4. **Release the trigger** to drop the panel. Releasing over nothing cancels.
5. The layout is saved on every change. Stacking panels in rows and columns on one side puts every module in reach without turning the carousel. The **Reset layout** face restores the defaults and removes the saved file.

### Moving and hiding faces

A single face is lifted the same way as a panel, with the trigger held on it:

1. Point at a face and **hold the trigger for 0.4 s**: a haptic pulse marks the lift, the face lifts off its slot as a card that follows the pointer, and its slot dims. One extra empty side ("Hide face") is offered at the end of the carousel.
2. **Aim at a slot** of any panel on the sides facing the user (turn the carousel with the palette stick while holding, as for panels): the slot lights orange. A face already in the slot changes places with the lifted face; an empty slot takes it. Slots in a row that belongs to a slider are not offered, and the slot the face came from is not a target.
3. **Release the trigger** to drop the face. Releasing over nothing, over the source slot or over a refused slot cancels. Dropped on the empty side, the face is hidden: it leaves the panels and the quick radial.
4. The layout is saved on every change. The **Show hidden** face (View panel) puts every hidden face back into a free slot, on its home panel when that has room; **Reset layout** restores the defaults and unhides everything. Loading a saved layout never places hidden faces again.

Sliders are dragged with the trigger, so they cannot be lifted or hidden; they move with their panel.

## Pointer

Every controller has a pointer pose derived from its aim pose and three settings, which the Session panel changes and `%APPDATA%\BlocksCAD\settings.json` keeps:

- **Mode: laser or tip.** Both modes can be compared and switched at any time with the Pointer face.
- **Angle:** the pointer is tilted down from the controller axis by this angle (slider from -30 to 60 degrees in steps of 1, default 15). It follows the roll of the controller.
- **Length:** the distance of the tip from the controller (slider from 0 to 20 cm in steps of 5 mm, default 40 mm, shown in the document unit).

**Laser.** A thin beam from the tool hand along the tilted aim direction, drawn on top of the scene and ending in a dot at the point it hits (0.6 m long when it hits nothing). Panels are pointed at with the ray; models are picked with the ray.

**Tip.** Like the brush tip of Open Brush: a thin cone that narrows from the controller to the tip, ending in a small sphere (7 mm), in front of both controllers, at the tip length along the tilted direction, drawn on top of the scene. The tip of the palette hand is hidden while the carousel is shown; both tips stay visible while navigating. The parts of a tip that lie behind or inside a panel or the model are drawn in the inverted colours (the tip is drawn twice: always, in inverted colours, and again in the normal colours where nothing is in front of it), so the colour shows whether the tip is in front of or in contact with what it acts on. The controller models always hide the tips and the laser: they are drawn a second time over them with a depth test against the scene, so a controller hides the pointer exactly where the controller itself is visible (not where something else is in front of the controller). The base of the cone, which starts inside the controller, therefore never shows in the inverted colours. The tip is the selector:

- panels react to what the tip touches: a panel is touched when the tip is within 3 cm in front of its plate (or up to 1.5 cm behind it) and inside it; the sphere lights up while it touches; the trigger presses a face or lifts a panel by its title bar, as with the laser;
- tools pick with the tip: the pointer pose of each hand (the tip position and the tilted orientation) replaces the aim pose for everything the tools do, and a model is picked only within 3 cm in front of the tip, so objects are selected by touching them. The inherited ray is not drawn.

## Tool hand

| Input | Action |
|---|---|
| Trigger | primary action of the tool; press and release on a face when pointing (laser) or touching (tip) at the carousel to activate it; hold on a face to lift it, on a title bar to lift a panel |
| Grip | grab the world or an object |
| Stick up/down | first option of the tool (size, segments, grid step), stepped, with a live readout (see Tool options) |
| Stick left/right | second option of the tool (cycle shape or mode) |
| Stick click | reset the option changed last to its default |
| Button 1 | held while navigating (one or two grips): level rotation. Otherwise: hold for the quick radial (below) |
| Button 2 | held while navigating: scale locked at 1 : 1. Otherwise: undo (tap), redo (hold) |

### Create tool

The first tool of the palette makes parametric primitives (`tools/primitives.py`, `cad/primitives.py`). The tip of the tool hand is the cursor, in laser mode as well as in tip mode (the tip position is the controller position moved by the tip length along the tilted aim).

- **Snap:** the cursor snaps to a grid in document millimetres (options below). A small cross at the snapped point shows where a press would start; it is drawn over the model so it is never lost. A haptic tick marks every move to another grid point.
- **Drag:** the trigger pressed on a grid point starts an axis-aligned box in document axes; moving the hand drags out the opposite corner in 3D. A ghost of the chosen shape fitted into the box and the outline of the box follow the hand. The ghost is a lit translucent body (front faces only, so there is no internal geometry) with outline curves along its characteristic edges (circles, seams, edges): bright where they lie in front of the model, dim where the model hides them. The ghost is a polygonal mesh built from the same sizing rules as the feature (`cad/meshes.py`, a fixed triangulation at every size, a few milliseconds), the feature itself is made by FreeCAD. The outline of the box is orange; and the readout next to the pointer names the shape and the three sizes ("Cylinder: 120 mm x 120 mm x 80 mm") in the unit system of the document. Every axis is at least one grid step long.
- **Release** makes the shape as a real FreeCAD feature in one transaction, so one undo step removes it; a toast reports it. A **tap** (the hand stays within its grid cell) places the shape at a default size of four grid steps centred on the cursor.
- **Shapes** fit into the box: Box (the box itself), Cylinder, Cone and Prism (the hexagonal prism) stand on the bottom of the box with the radius of half the smaller horizontal side, Sphere (half the smallest side) and Torus (tube of a fifth of the smaller horizontal side) are centred in it, Wedge is a ramp that rises towards +Y. The features are `Part::Box`, `Part::Cylinder`, `Part::Cone`, `Part::Sphere`, `Part::Torus`, `Part::Wedge` and `Part::Prism` with their dimensions as properties, so the size can be edited afterwards.
- **Options:** the stick up and down changes the grid (1, 2, 5, 10, 20, 50 and 100 mm; default 10 mm), left and right the shape.
- A press that starts on the carousel or the radial does not start a shape; a grip pressed during a drag cancels it, as does choosing another tool. Without an open document a release makes nothing and a toast says so.
- The grid is in document millimetres, whatever the scale of the world; zooming in with the grips and choosing a finer grid give finer shapes.

### Grab tool

The second tool of the palette touches, selects, moves, turns and scales objects (`tools/grab.py`, `cad/picking.py`, `cad/edit.py`, `core/grab.py`, `render/highlight.py`). The cursor is the tip of the tool hand, as in the Create tool.

- **Touch:** the element the cursor touches is highlighted and a haptic tick marks every change: the nearest **vertex** (within 12 mm of the stage, a cross), else the nearest **edge** (20 mm, a curve), else the nearest **face** (30 mm, a translucent fill with its outline), else the **object** when the cursor is inside a solid (all its edges). The reach is measured on the stage, so it is a shorter length in the document when the world is enlarged. Hidden objects are not touched. The hover is blue, the selection orange; both are drawn over the model with bright lines where they are in front and dim lines where the model hides them.
- **Tap** (press and release without moving anything) selects the touched element as FreeCAD's own selection, so what is selected in VR is selected on the desktop. A tap on nothing clears the selection.
- **Grab:** the trigger pressed on an element grabs its object in one transaction. The object follows the hand as a rigid body: the cursor position is on the grid, so it moves in whole grid steps, and a turn of the hand turns the object about the cursor in steps of 15 degrees (the option Mode switches the turn off). The readout names the move ("Move: 30 mm, 0, 20 mm, turn 90 deg"). Releasing keeps the change and selects the object; one undo step takes it back. The change is made to the `Placement` of the feature.
- **Scale:** the trigger of the other hand pressed during a grab scales the object through the size properties of its feature (`cad/edit.py`): the factor is the distance between the two cursors divided by their distance when the second trigger went down, every size is rounded to the grid and is at least one grid step long, and the centre of the object stays in place. The readout shows the factor. Releasing the second trigger goes back to moving from the pose the object has. Only objects made by the Create tool can be scaled (box, cylinder, cone, sphere, torus, wedge and prism); other objects are only moved.
- **Cancel:** a grip pressed during a grab aborts it and the transaction restores the object; choosing another tool does the same.
- **Options:** the stick up and down changes the grid (the same steps as the Create tool), left and right the mode (Move and rotate, Move).
- A press that starts on the carousel or the radial does not grab.

### Tool options

A tool declares up to two options (`ToolOption` in `tools/base.py`): a number with a range and a step, a length in millimetres (shown in the unit system of the document) or a choice from a list. While such a tool is active the stick of the tool hand belongs to its options:

- **Stick up/down** changes the first option, **stick left/right** the second. A number steps once when the stick is pushed out and repeats (after 0.3 s, ten steps per second) while it is held; a choice steps once per push and wraps round. Every step gives a haptic tick.
- **Stick click** puts the option changed last (the first when none was changed) back to its default.
- **Readout:** a plate next to the pointer of the tool hand names the option and its value ("Grid: 10 mm") and stays for 1.5 s after the last change.
- The options are inactive while a grip holds the world, while the quick radial is open and while the carousel is being used. A tool without options leaves the stick to the inherited code. The inherited tools declare no options.

### Undo and redo

`button2` of the tool hand outside navigation: a **tap** undoes (when the button is released within 0.4 s), a **hold** of 0.4 s redoes once while the button is still down. While a grip holds the world `button2` is the 1 : 1 lock, and a grip pressed while it is down cancels the undo. Both show a toast ("Undo", "Redo", "Nothing to undo", "Nothing to redo").

### Toasts, tooltips and readouts

All three are dark plates that fit their text, drawn over the model in the interface font.

- **Toasts** stand 0.8 m in front of the head, 0.2 m below the line of sight, at 1.5 times the size of the labels. Up to three stand at once, the newest at the bottom; each stays for 2.2 s, grows in and shrinks away, and a message that is still there is renewed instead of repeated. Toasts report the result of an action: undo and redo, the tool chosen with its hint, the pointer mode, layout reset, hidden and shown faces, and the selection text of the inherited tools.
- **Tooltips:** hovering one face for 0.5 s shows its description above it in the plane of its panel. Tool faces use the hint of the tool. The tooltip disappears when the pointer leaves the face and is not shown while something is lifted or pressed.
- **Readout** of a tool option: see Tool options.

### Quick radial

A pin-cushion like Open Brush's: holding tool hand `button1` (outside navigation) opens a radial of the favourite faces around the controller.

- **Items:** the six faces activated last (from the carousel or the radial), newest first, padded from the defaults (Undo, Redo, Reset view, Delete, Overlays, Pointer) when fewer than six were used. Hidden faces, sliders, Reset layout and Close VR are never offered. The list is kept in `settings.json`.
- **Choosing:** the item is chosen by the **direction the hand moves** from the spot where the button went down, seen from the head and measured in the plane facing the head (no stick needed). The first item is straight up, the others follow clockwise. Nothing is chosen within 3 cm of the start (dead zone). A haptic tick marks every change of the choice; the chosen segment lights up and a dot follows the hand over the disc.
- **Release** of the button activates the chosen item; a release inside the dead zone cancels.
- **Drawing:** a disc of 12.7 cm radius cut into one pie segment per item (segments from 3 cm to 11.5 cm, thin gaps between them), with the label of the face on each segment and a hub of 3 cm radius in the middle, which is the dead zone. It stands 5 cm in front of the hand towards the head, drawn over the model, in the colours and font of the palette. The plane is fixed when the radial opens.
- **Blocked:** the radial does not open while a grip holds the world (there `button1` is the level modifier) or while a slider is dragged, a panel or a face is lifted, or a face is pressed. A grip pressed while it is open cancels it. While it is open the tool hand's pointer does not touch the carousel and its trigger belongs to the interface.

## Palette hand

| Input | Action |
|---|---|
| Stick left/right | turn the carousel |
| Stick up/down | page scroll for long panels |
| Trigger | secondary action of the tool (modifier) |
| Grip | grab the world (alone or with the other grip) |
| Button 1 | pin or release the carousel |
| `aux1` (Steam Frame: D-pad left) | undo |
| `aux2` (Steam Frame: D-pad right) | redo |

Controllers without `aux1` and `aux2` undo and redo through the Edit panel faces; the tool hand shortcuts on `button2` cover every profile.

## Visual style

Flat, high contrast panels: dark plate (RGB 0.10, 0.11, 0.14), face plate (0.20, 0.22, 0.28), hover (0.30, 0.45, 0.80), active tool and lifted panel (0.95, 0.65, 0.10), drop target (0.18, 0.36, 0.24), text white.
Text is drawn from glyph outlines (Coin `SoText3`) in Segoe UI Bold (the platform default where the family is missing) at fixed height and sits on a plate so scene geometry never overlaps it.
The colours, the font and the text size are defined once in `ui/style.py`. Controllers keep the runtime-provided models.

## Implementation plan (UX milestones, before M1)

U1, U2, U3 and U4 are implemented (verification state in `verification.md`).

| U | Deliverable |
|---|---|
| U1 | World navigation: one-grip drag, one-grip hold with rotation, two-grip move/rotate/scale, free orbit and the level modifier, held 1 : 1 lock, home reset, scale ruler with document units, haptics; `core/navigation.py` and `core/units.py` (pure math, unit tested); the stick locomotion and the quick menu are removed |
| U2 | Panel system: `ui/` faces, panels, the carousel on the controller with every side visible, rows and columns of panels and rearranging, gaze visibility, laser, ray hover and press, haptics, undo and redo on `aux1` and `aux2`; inherited tools as faces; the first radial palette is removed |
| U3 | Quick radial (`ui/radial.py`, `ui/radial_view.py`); moving single faces between slots and panels; hiding faces and showing them again; a face activates on release |
| U4 | Tool options on the stick with a readout (`ui/options.py`, `tools/base.py`), undo and redo on `button2` (`ui/undo_button.py`), toasts and tooltips (`ui/toast.py`, `ui/feedback_view.py`) |

Every U step is tested through the Sim backend (scripted hands, offscreen render) and then checked in the headset by the owner (`verification.md`).
