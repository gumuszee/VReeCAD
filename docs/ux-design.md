# UX design

The interface of BlocksCAD follows the control scheme of [Open Brush](https://github.com/icosa-foundation/open-brush) (Apache-2.0), adapted to parametric CAD,
with the direct, "hand is the cursor" feel of Open Blocks. Open Brush code and assets are used as a reference for behaviour only; nothing is copied.
The inherited upstream interface (quick menu on the left trigger, stick locomotion, the first radial palette) is replaced, not extended.

## Principles

1. **One finger per job.** The thumb rests on the stick; a task never needs the thumb to hold a face button while the stick is used. Selection by hand movement or by the stick alone, confirmation by trigger or stick click.
2. **Hands, not menus.** Tools live on a palette carried by the off hand; the tool hand points at it. Navigation is grabbing the world with the grips.
3. **Everything is a modular face.** A face is a button (icon, label, action). Faces sit on pages, pages sit on a ring around the palette controller, and the layout is data the user can rearrange.
4. **Readable at arm's length.** Fixed physical sizes (face edge 4 cm, label height 1 cm at 0.5 m), high contrast, backing plates; no overlapping text.
5. **Feedback on every state change.** Haptic tick on hover change and activation, highlight on hover, a short toast for results.
6. **Hardware independent.** Only the five abstract inputs per hand (`input-profiles.md`); poses decide the rest.

## Hand roles

| Role | Default | Carries |
|---|---|---|
| Tool hand | right | the active tool (tip, ray, trigger = primary action) |
| Palette hand | left | the palette ring, readouts, undo/redo shortcuts |

Handedness is a preference; the roles swap as a whole.

## Navigation (grips)

Derived from Open Brush's world transform:

- **One grip on empty space:** the world follows the hand (translation 1:1).
- **Both grips:** two-point transform. The pivot is the midpoint between the hands; the world scales by the ratio of the hand distance, rotates with the line between the hands (and the twist of the hands about that line), and moves with the midpoint. Rotation is constrained to the vertical axis ("tilt protection"); scale is clamped to 1:100 .. 100:1.
- **Stick click of a gripping hand:** reset the view (animated back to scale 1:1 at the origin).
- While a grip navigates, the palette hides, the tool is inactive and a ground grid fades in; a scale readout (`1 : 4`) floats between the hands; haptic ticks mark round scales.
- A grip pressed on an object grabs that object instead (milestone M2).

## Palette ring (palette hand)

- Pages are flat panels arranged on a ring around the palette controller (three pages around 360 degrees). The page facing the user is fully visible, the neighbours are turned away.
- **Stick left/right turns the ring** one page per flick (snap with a haptic tick and a short ease). No button is held.
- **Visibility:** the ring fades in when the head looks at the palette controller (gaze cone of 35 degrees at 0.15 to 0.9 m) and fades out otherwise; it is hidden while gripping. Palette hand `button1` pins it visible or releases it.
- **Pointing:** the tool hand's ray hits a face; the face highlights (colour, slight lift) and a tooltip names it; trigger activates. Hover change and activation give a haptic tick on the tool hand.
- A page is a grid of faces (4 columns). A face has: id, label, icon (a short glyph or text), action id, optional toggle or value state.

### Pages (initial)

| Page | Faces |
|---|---|
| Tools | Select, Grab, Teleport, Line, Cube, Drag, Working plane (the inherited tools, until replaced) |
| Create | primitives (milestone M1) |
| Modify | push/pull, boolean, mirror, pattern (milestones M4 and later) |
| Values | numeric keypad, variables (milestone M3) |
| View | reset view, toggle Model tree and Tasks overlays, grid, units |
| Settings | handedness, comfort, snapping |

### Layout and customization

The layout is a JSON document (`%APPDATA%\BlocksCAD\layout.json`): pages, their order, and the face ids in each slot. Defaults come from code.
**Customize mode** (a face on the View page): grip a face with the tool hand and drop it on another slot to swap or move it, drop it on the trash slot to hide it,
turn the ring to move it to another page. The layout is saved on leaving the mode.

## Tool hand

| Input | Action |
|---|---|
| Trigger | primary action of the tool; press a face when pointing at the palette |
| Grip | grab the world or an object |
| Stick up/down | tool option (size, segments, grid step) with a live readout |
| Stick left/right | tool option 2 (cycle shape or mode) |
| Stick click | confirm the pending value / reset the option |
| Button 1 | hold: quick radial (below) |
| Button 2 | undo (tap), redo (hold) |

### Quick radial

A pin-cushion like Open Brush's: holding tool hand `button1` opens a radial of the favourite faces (default: the last six used) around the controller.
The item is chosen by the **direction the hand moves** from the spot where the button was pressed (no stick needed); releasing the button activates it.

## Palette hand

| Input | Action |
|---|---|
| Stick left/right | turn the ring |
| Stick up/down | page scroll for long pages |
| Trigger | secondary action of the tool (modifier) |
| Grip | grab the world (alone or with the other grip) |
| Button 1 | pin or release the ring |
| Button 2 | redo |

## Visual style

Flat, high contrast panels: dark plate (RGB 0.10, 0.11, 0.14), face plate (0.20, 0.22, 0.28), hover (0.30, 0.45, 0.80), active tool (0.95, 0.65, 0.10), text white.
Text is drawn from glyph outlines (Coin `SoText3`) at fixed height and sits on a plate so scene geometry never overlaps it.
Controllers keep the runtime-provided models.

## Implementation plan (UX milestones, before M1)

| U | Deliverable |
|---|---|
| U1 | World navigation: one-grip drag, two-grip move/rotate/scale, reset, scale readout, haptics; `core/navigation.py` (pure math, unit tested); the stick locomotion and the quick menu are removed |
| U2 | Panel system: `ui/` faces, pages, ring layout, gaze visibility, ray hover and press, tooltips, haptics; inherited tools as faces; the first radial palette is removed |
| U3 | Quick radial and layout customization (JSON layout, customize mode) |
| U4 | Tool hand options with readouts, undo/redo buttons, toasts |

Every U step is tested through the Sim backend (scripted hands, offscreen render) and then checked in the headset by the owner (`verification.md`).
