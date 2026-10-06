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
- **Panels** are pages of faces (4 columns by 3 rows, face edge 5 cm) with a title bar and side dots. A side carries rows of panels: panels next to each other in a row, rows above each other (the first row nearest the user, further rows further forward). The prism radius grows with the number of sides and the width of the panels so that sides do not overlap.
- **Stick left/right turns the carousel** one side per flick (snap with a haptic tick and a short ease). No button is held. Sides that face away from the user are drawn but cannot be pointed at.
- **Visibility:** the carousel fades in when the head looks at the controller (gaze cone of 35 degrees at 0.12 to 0.95 m) and fades out otherwise; it is hidden while gripping. Palette hand `button1` pins it visible or releases it.
- **Pointing:** while the carousel is shown the tool hand carries a laser: a thin beam on top of the scene that ends in a dot at the point it hits (a fixed 0.6 m beam when it hits nothing). The face under the dot highlights and a haptic tick marks the change; the trigger activates it.

### Panels (initial)

| Panel | Faces |
|---|---|
| Tools | Teleport, Line, Cube, Select, Drag, Working plane (the inherited tools, until replaced) |
| Edit | Undo, Redo, Delete |
| View | Reset view, Overlays (Model tree and Tasks), Work plane, Reload scene, Reset layout |
| Session | Close VR |

Planned: Create (primitives, milestone M1), Modify (push/pull, boolean, mirror, pattern), Values (numeric keypad, variables, milestone M3), Settings (handedness, comfort, snapping).

### Rearranging panels

Each panel has a title bar with a grip mark on its right. The layout is a JSON document (`%APPDATA%\BlocksCAD\layout.json`, version 3): the panels in order, the side and the row of each panel and the face ids in each slot. Defaults come from code. The initial layout has one panel per side.

1. Point the tool hand at a title bar (it highlights) and **hold the trigger**: the panel lifts off the carousel and follows the laser as a small card. The panels close up and one extra empty side ("Drop here") is offered at the end of the carousel.
2. **Turn the carousel** with the palette stick while holding, to bring the target side to the front (only sides facing the user can be pointed at).
3. **Aim at a panel** to choose where the lifted panel goes; an orange bar shows the place and the panel under the laser lights up:
   - the left or right half of the panel: next to it in its row, in front of it (left) or after it (right);
   - the upper or lower quarter of the panel: a new row above or below it;
   - the empty slot of an empty side: that side, alone.
4. **Release the trigger** to drop the panel. Releasing over nothing cancels.
5. The layout is saved on every change. Stacking panels in rows and columns on one side puts every module in reach without turning the carousel. The **Reset layout** face restores the defaults and removes the saved file.

Moving single faces between slots and panels, and hiding faces, is part of U3.

## Tool hand

| Input | Action |
|---|---|
| Trigger | primary action of the tool; press a face when pointing at the carousel; hold on a title bar to lift a panel |
| Grip | grab the world or an object |
| Stick up/down | tool option (size, segments, grid step) with a live readout |
| Stick left/right | tool option 2 (cycle shape or mode) |
| Stick click | confirm the pending value / reset the option |
| Button 1 | held while navigating (one or two grips): level rotation. Otherwise: hold for the quick radial (below) |
| Button 2 | held while navigating: scale locked at 1 : 1. Otherwise: undo (tap), redo (hold) |

### Quick radial

A pin-cushion like Open Brush's: holding tool hand `button1` (outside navigation) opens a radial of the favourite faces (default: the last six used) around the controller.
The item is chosen by the **direction the hand moves** from the spot where the button was pressed (no stick needed); releasing the button activates it.

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

Controllers without `aux1` and `aux2` undo and redo through the Edit panel faces; the tool hand shortcuts on `button2` (U4) cover every profile.

## Visual style

Flat, high contrast panels: dark plate (RGB 0.10, 0.11, 0.14), face plate (0.20, 0.22, 0.28), hover (0.30, 0.45, 0.80), active tool and lifted panel (0.95, 0.65, 0.10), drop target (0.18, 0.36, 0.24), text white.
Text is drawn from glyph outlines (Coin `SoText3`) in Segoe UI Bold (the platform default where the family is missing) at fixed height and sits on a plate so scene geometry never overlaps it.
The colours, the font and the text size are defined once in `ui/style.py`. Controllers keep the runtime-provided models.

## Implementation plan (UX milestones, before M1)

U1 and U2 are implemented (verification state in `verification.md`); U3 and U4 are planned.

| U | Deliverable |
|---|---|
| U1 | World navigation: one-grip drag, one-grip hold with rotation, two-grip move/rotate/scale, free orbit and the level modifier, held 1 : 1 lock, home reset, scale ruler with document units, haptics; `core/navigation.py` and `core/units.py` (pure math, unit tested); the stick locomotion and the quick menu are removed |
| U2 | Panel system: `ui/` faces, panels, the carousel on the controller with every side visible, rows and columns of panels and rearranging, gaze visibility, laser, ray hover and press, haptics, undo and redo on `aux1` and `aux2`; inherited tools as faces; the first radial palette is removed |
| U3 | Quick radial; moving single faces between slots and panels; hiding faces |
| U4 | Tool hand options with readouts, undo/redo on `button2`, toasts, tooltips |

Every U step is tested through the Sim backend (scripted hands, offscreen render) and then checked in the headset by the owner (`verification.md`).
