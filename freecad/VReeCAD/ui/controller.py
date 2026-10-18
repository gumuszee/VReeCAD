# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""The user interface as one unit: grip navigation with its ruler, the palette carousel with its panels, the quick radial, action
dispatch, undo and redo on the tool hand, tool options, toasts, tooltips.
While an editable object is selected a values carousel (the panels of `ui/value_module.py`) can replace the palette carousel; the trigger of
the palette hand swaps the two. A tap on the menu mark of a panel title opens the panel editor (`ui/panel_editor.py`), a carousel of its
own that renames the panel and gives it a colour.
Hosts (the XR widget and the Sim session) feed it one `InputFrame` per frame and apply what it returns: the world pose goes to a
scene transform, `haptics` to the controllers, `ray_end` to the tool hand's ray, `consume_trigger` suppresses the tool hand's trigger.
The scene graph has two roots: `root` (the carousel, depth tested) and `overlay` (the ruler, drawn last on top of everything)."""

import os
from dataclasses import dataclass, field
from dataclasses import replace
from typing import Callable, Dict, List, Optional

from pivy import coin

from freecad.VReeCAD.core import mathutil as mu
from freecad.VReeCAD.core import snapping, units
from freecad.VReeCAD.core import values as value_editing
from freecad.VReeCAD.core.navigation import Navigator
from freecad.VReeCAD.profiling import PROFILER as prof
from freecad.VReeCAD.ui import defaults
from freecad.VReeCAD.ui import layout as lay
from freecad.VReeCAD.ui import pointing, settings as cfg
from freecad.VReeCAD.ui import options as tool_options
from freecad.VReeCAD.ui import help as controls_help
from freecad.VReeCAD.ui import radial, toast
from freecad.VReeCAD.ui.feedback_view import FeedbackView
from freecad.VReeCAD.render.model_anchor import BUTTON_PARTS, STICK_PARTS
from freecad.VReeCAD.ui.pointer import Pointer, TipMarker
from freecad.VReeCAD.ui.radial_view import RadialView
from freecad.VReeCAD.ui.ring import PaletteRing
from freecad.VReeCAD.ui.ring_view import RingView
from freecad.VReeCAD.ui.ruler import Ruler
from freecad.VReeCAD.ui.undo_button import UndoButton
from freecad.VReeCAD.ui import panel_editor, value_module
from freecad.VReeCAD.ui.value_module import ValueModule


@dataclass
class UiUpdate:
    haptics: List[tuple] = field(default_factory=list)   # (hand, amplitude, duration_s)
    ray_end: Optional[tuple] = None
    consume_trigger: bool = False
    owns_stick: bool = False                             # the active tool has options: the stick of the tool hand belongs to them
    activated: Optional[str] = None                      # action id executed this frame


OPTION_DISC_OUTER = 0.07       # metres: radius of the option disc of a tool
OPTION_DISC_INNER = 0.022
OPTION_DISC_LIFT = 0.04        # metres above the top of the thumbstick: the disc lies in the plane of the top of the controller
LOCK_LIFT = 0.012              # metres above the top of the A button
WRIST_BACK = 0.07              # metres behind the face buttons, towards the wrist
WRIST_LIFT = 0.03              # metres above the plane of the buttons
HELP_LIFT = 0.15               # metres above a controller: where the title of its controls card hangs


class UiController:
    def __init__(self, tool_names, tool_label, actions: Dict[str, Callable], palette_hand=0, tool_hand=1,
                 layout_path=None, use_user_layout=True, mm_to_stage=0.001, settings_path=None, tool_hint=None, values_layout_path=None, start_home=True):
        self.actions = actions
        self.buttons = defaults.build_buttons(tool_names, tool_label, tool_hint)
        self._tool_names = list(tool_names)
        default = defaults.default_layout(self._tool_names)
        self.use_user_layout, self.layout_path = use_user_layout, layout_path
        self.layout = lay.load_layout(default, set(self.buttons), layout_path) if use_user_layout else default
        self.settings = cfg.load_settings(settings_path) if use_user_layout else cfg.Settings()
        self.settings_path = settings_path
        self.values_layout_path = values_layout_path
        self.wide = {fid for fid, button in self.buttons.items() if button.kind == "slider"}
        if use_user_layout and self.layout is not default:
            migrated = defaults.migrate(self.layout, default)
            if self.layout.add_missing(default, self.wide) or migrated:
                self._save_layout()
        self.palette_hand, self.tool_hand = palette_hand, tool_hand
        self.navigator = Navigator(modifier_hand=tool_hand, start_home=start_home)
        self._grip_claimed = [False, False]     # a grip pressed while the tool is in a gesture: it cancels it and does not hold the world
        self.ring = PaletteRing(self.layout.sides(), palette_hand, tool_hand)
        self.ring.can_lift = lambda page, slot: self.carousel == "tools" and self.layout.button_at(page, slot) is not None
        self.ring.can_drop = lambda src, dst: self.carousel == "tools" and self.layout.can_move_button(*src, *dst, self.wide)
        self.radial = radial.QuickRadial(tool_hand)
        self.radial_view = RadialView()
        self.options_view = RadialView(OPTION_DISC_OUTER, OPTION_DISC_INNER, 0.8)        # the disc of the options of the active tool
        self.part_frame = None             # callable(hand, part names, lift) -> (position, right, forward, up) on the controller, set by the host
        self.undo_button = UndoButton(tool_hand)
        self.module = ValueModule(tool_hand)       # the panels for the values of the selected object, on a carousel side of their own
        self.panel_editor = None           # the `panel_editor.PanelEditor` while a panel is renamed or coloured
        self._editor_buttons = panel_editor.buttons()
        self._editor_layout = None         # (what it depends on, layout) of the editor carousel
        self._return_to = "tools"          # the carousel that comes back when the editor closes
        self.view_buttons = {**self.buttons, **self.module.buttons, **self._editor_buttons}      # every button that can be drawn: the user's, the module's and the editor's
        self.values_layout = (value_module.load_layout(set(self.module.buttons), values_layout_path) if use_user_layout
                              else value_module.default_layout())     # the panels of the values carousel that the user can rearrange
        self.carousel = "tools"            # which carousel the palette hand shows: "tools" (the user layout), "values" (while the module is open) or "editor"
        self._front = {"tools": 0, "values": 0, "editor": 0}     # the side at the front of each carousel while the other one is shown
        self.values_source = None          # callable() -> (key, factory of a `core.values.ValueTarget`) of the selected object, or None; set by the host
        self._shown = None                 # (key, layout of the values carousel) while it is shown
        self.options = tool_options.OptionControl(tool_hand)
        self._disc_shown = False           # the option disc of the tool is drawn: the pointer of the tool hand stays out of its way
        self.active_tool = None            # the active `tools.base.Tool`, set by the host before `update`
        self.hands_changed = None          # callable(tool hand index), set by the host: the hands have swapped roles
        self.gesture_text = None           # readout of a running gesture (the size of a shape being dragged), set by the tool
        self.toasts = toast.Toasts()
        self.help = controls_help.HelpState()
        self._first_help = False           # the controls card shows for the first time (`show_first_help`)
        self.dwell = toast.Dwell()
        self.feedback = FeedbackView()
        self.view = RingView()
        self.ruler = Ruler()
        self.pointer = Pointer()
        self.tips = [TipMarker(), TipMarker()]
        self.pointer_poses = [None, None]     # `pointing.PointerPose` of each hand, set by `update`
        self._unit_system_name = ""
        self.system = units.METRIC_MM
        self._apply_system()
        self.mm_to_stage = mm_to_stage     # stage length of one document millimetre at world scale 1
        self.root = coin.SoSeparator()
        self.root.ref()
        self.root.addChild(self.view.root)
        self.overlay = coin.SoSeparator()
        self.overlay.ref()
        self.overlay.addChild(self.pointer.root)
        for tip in self.tips:
            self.overlay.addChild(tip.root)
        # the controller models are drawn again over the laser and the tips, so the controllers always hide them (`add_occluder`)
        self.occluders = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE
        self.occluders.addChild(pick)
        depth = coin.SoDepthBuffer()
        depth.test.setValue(True)
        depth.function.setValue(coin.SoDepthBuffer.LEQUAL)
        depth.getField("write").setValue(False)
        self.occluders.addChild(depth)
        self.overlay.addChild(self.occluders)
        self.overlay.addChild(self.ruler.root)
        self.overlay.addChild(self.feedback.root)
        self.overlay.addChild(self.options_view.root)
        self.overlay.addChild(self.radial_view.root)
        self.active_actions = set()

    def set_unit_system(self, name):
        """Use the measurement system of a FreeCAD document unit system name (the document's `UnitSystem` property)."""
        self._unit_system_name = name
        self._apply_system()

    def _apply_system(self):
        """The measure system of the document, with lengths under a millimetre as the setting `sub_mm` says."""
        system = units.system_for(self._unit_system_name)
        self.system = units.without_micrometres(system) if self.settings.sub_mm == "mm" else system

    def action_at(self, page, slot):
        button_id = self.shown_layout().button_at(page, slot)
        button = self.view_buttons.get(button_id) if button_id else None
        return button.action if button else None

    def add_occluder(self, node):
        """Draw a scene node (the model of a controller) a second time over the laser and the tips, wherever it is visible in the
        scene: the depth test against the depth the scene already wrote passes only where nothing is in front of it. The node is
        shared, not copied, so it follows its original."""
        self.occluders.addChild(node)

    def cursor(self, hand):
        """The cursor of a hand (an `input.HandInput`) for the tools: the tip of the pointer, whatever the pointer mode is."""
        s = self.settings
        return pointing.pointer_pose(hand.aim, "tip", s.tip_angle, s.tip_length).position

    def set_readout(self, text):
        """The text of a running gesture, shown on the wrist of the tool hand like a toast; None removes it."""
        self.gesture_text = text

    def toast(self, text):
        """Show a short message in front of the head."""
        self.toasts.show(text)

    def _sync_values(self, out):
        """Bind the value panels to the object that is selected: they appear with it, follow the selection from one object to the
        next and go with it. They appear on a carousel side of their own, and the carousel turns to that side when they first appear."""
        source = None
        if self.values_source is not None:
            try:
                source = self.values_source()
            except Exception as error:      # a selection that cannot be read must not stop the session
                print(f"VReeCAD: cannot read the selection: {error}")
        module = self.module
        if source is None:
            if module.is_open:
                module.close()
                self._show_carousel("tools")
            return
        key, factory = source
        if module.is_open and module.key == key:
            return
        was_open = module.is_open
        try:
            editor = value_editing.ValueEditor(factory(), self.system, getattr(self.active_tool, "grid", module.step) if not was_open else module.step)
        except Exception as error:
            print(f"VReeCAD: cannot edit the values: {error}")
            return
        if not editor.fields:
            return
        module.open(editor, key)
        if not was_open:
            self._front["values"] = 0
            self._show_carousel("values")
            out.haptics.append((self.palette_hand, 0.2, 0.02))

    def shown_layout(self):
        """The layout the carousel shows: the palette layout of the user, or, while the module is open and the values carousel is shown,
        the panels of the values carousel with a Value panel at the top of every side."""
        if self.carousel == "editor" and self.panel_editor is not None:
            key = self.panel_editor.key()
            if self._editor_layout is None or self._editor_layout[0] != key:
                self._editor_layout = (key, panel_editor.layout(self.panel_editor.preview_hue(), self.panel_editor.preview_page()))
            return self._editor_layout[1]
        if not self.module.is_open or self.carousel != "values":
            return self.layout
        key = (id(self.values_layout), tuple((p.name, tuple(p.slots), p.side, p.row) for p in self.values_layout.pages))
        if self._shown is None or self._shown[0] != key:
            self._shown = (key, value_module.shown_layout(self.values_layout))
        return self._shown[1]

    def _show_carousel(self, mode):
        """Show the palette carousel ("tools") or the values carousel ("values") on the palette hand, each at the side it was left at."""
        if self.panel_editor is not None and self.carousel == "editor" and mode != "editor":
            self._return_to = mode                   # the editor has the carousel: the other one comes back when it closes
            return
        if mode == self.carousel:
            return
        self._front[self.carousel] = self.ring.front_side()
        self.carousel = mode
        sides = self.shown_layout().sides()
        self.ring.set_sides(sides)
        self.ring.focus_side(min(self._front[mode], len(sides) - 1), len(sides))

    def swap_carousels(self):
        """The trigger of the palette hand: the other carousel, when there is one (an object is selected). Returns whether it swapped."""
        if not self.module.is_open or self.panel_editor is not None:
            return False
        self._show_carousel("values" if self.carousel == "tools" else "tools")
        self.toast("Values carousel" if self.carousel == "values" else "Tools carousel")
        return True

    def open_panel_editor(self, page):
        """Show the panel editor for the panel `page` of the palette layout (a tap on the menu mark of its title)."""
        if self.carousel != "tools" or self.panel_editor is not None or not 0 <= page < len(self.layout.pages):
            return False
        chosen = self.layout.pages[page]
        self.panel_editor = panel_editor.PanelEditor(page, chosen.name, chosen.hue, chosen.cols, chosen.rows, chosen.slots)
        self._return_to = "tools"
        self._front["editor"] = 0
        self._show_carousel("editor")
        return True

    def close_panel_editor(self, applied):
        """Leave the panel editor: with `applied` the panel gets the name and the colour, then the carousel that was shown comes back."""
        editor, self.panel_editor = self.panel_editor, None
        if editor is None:
            return
        if applied and editor.page < len(self.layout.pages):
            name, hue = editor.result()
            chosen = self.layout.pages[editor.page]
            chosen.name, chosen.hue = name, hue
            chosen.resize(*editor.size)
            self._save_layout()
            self.toast(f"Panel: {name}")
        target = self._return_to if self._return_to == "tools" or self.module.is_open else "tools"
        self._show_carousel(target)

    def _preview_page(self, carousel):
        """The index of the page of the editor that only shows the panel being edited, or None."""
        if self.panel_editor is None or self.carousel != "editor":
            return None
        return next((i for i, p in enumerate(carousel.pages) if p.name == panel_editor.PAGE_PREVIEW), None)

    def _editing_layout(self):
        """The layout the user rearranges on the carousel that is shown."""
        return self.values_layout if self.carousel == "values" and self.module.is_open else self.layout

    def radial_items(self):
        """Button ids offered by the quick radial: the buttons used last, then the defaults."""
        return radial.choose_items(self.settings.recent, self.buttons, self.layout.hidden)

    def radial_hub(self):
        """The button id of the item in the middle of the quick radial, or None."""
        return radial.CENTRE if radial.CENTRE in self.buttons else None

    def _activate(self, button_id, out):
        """Run the action of a button and remember the button for the quick radial (the button of its hub is not a favourite)."""
        button = self.buttons.get(button_id) if button_id else None
        if button is None:
            return
        self._run(button.action, out)
        if button.kind == "button" and button_id != radial.CENTRE and (not self.settings.recent or self.settings.recent[0] != button_id):
            self.settings.recent = radial.remember(self.settings.recent, button_id)
            self._save_settings()

    def show_hidden(self):
        """Put the hidden buttons back on the panels."""
        shown = len(self.layout.hidden)
        if self.layout.show_hidden(defaults.default_layout(self._tool_names), self.wide):
            self._save_layout()
        left = len(self.layout.hidden)
        if not shown:
            self.toast("No hidden buttons")
        elif not left:
            self.toast("Buttons shown")
        elif left < shown:
            self.toast(f"{shown - left} buttons shown, no room for {left}")
        else:
            self.toast("No room for the hidden buttons")

    def reset_layout(self):
        """Back to the default layout (no hidden buttons); a saved layout file is removed."""
        self.layout = defaults.default_layout(self._tool_names)
        self.values_layout = value_module.default_layout()
        self._front = {"tools": 0, "values": 0}
        self.ring.set_sides(self.shown_layout().sides())
        self.ring.focus_side(0)
        self._save_layout(remove=True)
        self.toast("Layout reset")

    def _save_layout(self, remove=False):
        """Save the layout of the palette carousel and the one of the values carousel (or remove both files)."""
        if not self.use_user_layout:
            return
        for layout, path, extra in ((self.layout, self.layout_path or lay.user_layout_path(), {}),
                                    (self.values_layout, self.values_layout_path or value_module.user_layout_path(),
                                     {"arrangement": value_module.ARRANGEMENT})):
            try:
                if remove:
                    os.remove(path)
                else:
                    lay.save_layout(layout, path, **extra)
            except OSError:
                pass   # the layout is a convenience; a failed write must not stop the session

    def labels(self):
        """Labels of the buttons whose text shows a value, by button id."""
        s = self.settings
        return {
            "pointer.mode": "Pointer: " + ("Tip" if s.pointer_mode == "tip" else "Laser"),
            "pointer.angle": f"Angle {s.tip_angle:.0f}\u00b0",
            "pointer.length": "Length " + units.format_length(s.tip_length * 1000.0, self.system),
            "pointer.submm": "Small: " + ("0.1 mm" if s.sub_mm == "mm" else "100 µm"),
            "settings.snapping": "Snapping: " + ("Inference" if s.snap_source == "inference" else "Guides"),
            "settings.grid": "Grid " + units.format_length(s.grid, self.system),
            "settings.angle": f"Angle step {s.angle:.0f}°",
        }

    def slider_states(self):
        """Position along the track and label of each slider, by button id."""
        labels = self.labels()
        return {fid: (spec.fraction(getattr(self.settings, spec.attr)), labels[fid]) for fid, spec in defaults.SLIDERS.items()}

    def slider_rows(self, kind="slider"):
        """Pages and grid rows that hold a button of `kind` that takes the whole row, a "slider" or a "readout": page -> row -> button id."""
        rows = {}
        for p, page in enumerate(self.shown_layout().pages):
            for r in range(page.rows):
                button_id = page.slots[r * page.cols]
                button = self.view_buttons.get(button_id) if button_id else None
                if button is not None and button.kind == kind:
                    rows.setdefault(p, {})[r] = button_id
        return rows

    def _save_settings(self):
        if self.use_user_layout:
            try:
                cfg.save_settings(self.settings, self.settings_path)
            except OSError:
                pass   # settings are a convenience; a failed write must not stop the session

    def _change_pointer(self, action):
        if action == "pointer:mode":
            self.settings.toggle_mode()
            self._save_settings()
            self.toast("Pointer: " + ("Tip" if self.settings.pointer_mode == "tip" else "Laser"))

    def set_tool_hand(self, hand):
        """Hold the tools in the hand `hand` (0 left, 1 right) and the palette in the other: every part of the interface that belongs to
        a hand follows. The host is told through `hands_changed`."""
        palette = 1 - hand
        self.tool_hand, self.palette_hand = hand, palette
        self.navigator.modifier_hand = hand
        self.ring.palette_hand, self.ring.tool_hand = palette, hand
        for part in (self.radial, self.undo_button, self.module, self.options):
            part.hand = hand
        if self.hands_changed is not None:
            self.hands_changed(hand)

    def apply_handedness(self):
        """Give the hands the roles that the setting `tool_hand` names (the host calls it once the interface is built)."""
        self.set_tool_hand(0 if self.settings.tool_hand == "left" else 1)

    def swap_hands(self):
        """The tool hand and the palette hand change places; the choice is saved. Returns the text for a toast."""
        self.settings.tool_hand = "left" if self.tool_hand == 1 else "right"
        self._save_settings()
        self.apply_handedness()
        return f"Tool hand: {self.settings.tool_hand}"

    def cycle_placement(self, out):
        """The A button while the trigger holds a gesture: the next placement (snap, grid, free); the choice is saved."""
        placement = self.settings.cycle_placement()
        self._save_settings()
        self.toast("Placement: " + snapping.PLACEMENT_LABELS[placement])
        out.haptics.append((self.tool_hand, 0.3, 0.02))

    def toggle_sub_mm(self):
        """Lengths under a millimetre change between decimals of a millimetre and micrometres; the choice is saved. Returns the text for a toast."""
        self.settings.sub_mm = "um" if self.settings.sub_mm == "mm" else "mm"
        self._save_settings()
        self._apply_system()
        return "Lengths under 1 mm: " + ("decimals of mm" if self.settings.sub_mm == "mm" else "micrometres")

    def show_first_help(self):
        """Show the controls cards once when the addon has not been used yet (the setting `onboarded`); they stay until the Controls button
        or the time takes them away, and then the setting is saved."""
        if not self.settings.onboarded:
            self._first_help = True
            self.help.show()
            self.toast("Controls help: the Tutorial button on the Settings panel shows it again")

    def _help_ended(self):
        if self._first_help:
            self._first_help = False
            self.settings.onboarded = True
            self._save_settings()

    def _run(self, action, out):
        if action == "hands:swap":
            self.toast(self.swap_hands())
        elif action == "units:submm":
            self.toast(self.toggle_sub_mm())
        elif action == "settings:snapping":
            self.settings.toggle_snapping()
            self._save_settings()
            self.toast("Snapping: " + ("inference of the points near the hand" if self.settings.snap_source == "inference" else "guides to every point"))
        elif action == "help:toggle":
            shown = self.help.toggle()
            self.toast("Controls shown" if shown else "Controls hidden")
            if not shown:
                self._help_ended()
        elif action == "layout:reset":
            self.reset_layout()
        elif action == "layout:show_hidden":
            self.show_hidden()
        elif action.startswith("pointer:"):
            self._change_pointer(action)
        else:
            handler = self.actions.get(action)
            if handler is not None:
                try:
                    message = handler()
                except Exception as error:          # an action that fails says so and the viewer goes on
                    import traceback
                    traceback.print_exc()
                    message = f"{action.split(':')[-1].replace('_', ' ').capitalize()} failed: {error}"
                if isinstance(message, str):
                    self.toast(message)
        out.activated = action

    def _claim_grips(self, frame):
        """The hands whose grip belongs to the tool: a grip that goes down while the tool is in a gesture cancels the gesture, and the
        world stays where it is until that grip is released."""
        busy = bool(getattr(self.active_tool, "busy", False))
        for i, hand in enumerate(frame.hands):
            if not hand.down("grip"):
                self._grip_claimed[i] = False
            elif busy and not self.navigator.navigating:
                self._grip_claimed[i] = True
        return tuple(self._grip_claimed)

    def update(self, frame) -> UiUpdate:
        out = UiUpdate()
        s = self.settings
        self._sync_values(out)
        # the trigger of the palette hand swaps the carousels, except while the tool is in a gesture (the Move tool scales with it)
        if ("trigger" in frame.hands[self.palette_hand].pressed and not getattr(self.active_tool, "busy", False)
                and not self.navigator.navigating and self.swap_carousels()):
            out.haptics.append((self.palette_hand, 0.3, 0.025))
        if getattr(self.active_tool, "busy", False) and "button1" in frame.hands[self.tool_hand].pressed:
            self.cycle_placement(out)            # a gesture runs, so the quick radial is closed and A is free for the placement
        if getattr(self.active_tool, "busy", False) and "button2" in frame.hands[self.tool_hand].pressed and not self.navigator.navigating:
            text = self.active_tool.toggle_fixed()       # and B fixes what the gesture holds (undo is for outside a gesture)
            if text:
                self.toast(text)
                out.haptics.append((self.tool_hand, 0.4, 0.03))
        prof.lap("ui_values")
        self.pointer_poses = [pointing.pointer_pose(h.aim, s.pointer_mode, s.tip_angle, s.tip_length) for h in frame.hands]
        # in tip mode the world is held with the tips: it pivots about them and the ruler measures between them
        points = [p.position for p in self.pointer_poses] if s.pointer_mode == "tip" else None
        events = self.navigator.update(frame, blocked=self._claim_grips(frame), points=points)
        prof.lap("ui_nav")
        for event in events:
            if event[0] == "grab":
                out.haptics += [(0, 0.25, 0.03), (1, 0.25, 0.03)]
            elif event[0] == "tick":
                out.haptics += [(hand, 0.6, 0.04) for hand in event[1]]
            elif event[0] == "reset":
                out.haptics += [(0, 0.7, 0.12), (1, 0.7, 0.12)]
            elif event[0] == "snap":
                out.haptics += [(0, 0.5, 0.06), (1, 0.5, 0.06)]
            elif event[0] == "level":
                out.haptics.append((self.tool_hand, 0.3, 0.03))

        # the quick radial takes the tool hand while it is open: the carousel does not see its pointer
        busy = (self.navigator.navigating or self.ring.lifted is not None or self.ring.lifted_button is not None
                or self.ring.slider_drag is not None or self.ring.press is not None or getattr(self.active_tool, "busy", False))
        hub = self.radial_hub()
        quick = self.radial.update(frame, self.radial_items(), blocked=busy, hub=hub)
        out.owns_stick, readout = self._tool_hand_buttons(frame, self.navigator.navigating or self.radial.is_open or self.module.engaged, out)
        carousel = self.shown_layout()
        if self.panel_editor is not None and self.carousel == "editor":
            self.ring.fixed_from = 0                     # nothing of the editor is lifted or dropped on
        else:
            self.ring.fixed_from = len(self.values_layout.pages) if carousel is not self.layout else None
        self.ring.set_sides(carousel.sides())
        self.ring.pinned_pages = [i for i, p in enumerate(carousel.pages) if p.pinned]
        self.ring.set_dims({i: (p.cols, p.rows) for i, p in enumerate(carousel.pages) if (p.cols, p.rows) != (lay.COLS, lay.ROWS)})
        self.ring.slider_rows = self.slider_rows()
        self.ring.readout_rows = self.slider_rows("readout")
        self.ring.hold_visible = self.module.engaged       # the stick works the value slider: the carousel stays whatever the head sees
        pointers = list(self.pointer_poses)
        if self.radial.is_open:
            pointers[self.tool_hand] = replace(pointers[self.tool_hand], tracked=False)
        prof.lap("ui_misc")
        result = self.ring.update(frame, navigating=self.navigator.navigating, pointers=pointers)
        prof.lap("ui_ring")
        out.haptics += result.haptics + quick.haptics
        if result.menu is not None:
            self.open_panel_editor(result.menu)
        out.ray_end = result.ray_end
        out.consume_trigger = result.consume_trigger or self.radial.is_open or quick.activated is not None or quick.activated_hub
        if result.focus is not None:
            focused = carousel.button_at(*result.focus)
            if focused in value_module.SLIDER_IDS:
                self.module.set_focus(focused)
        if self.module.engaged:
            out.owns_stick = True                            # a value slider is focused: the stick of the tool hand steps its value
        preview = self._preview_page(carousel)               # the buttons of the preview are for show: nothing on it is pressed or dragged
        if result.slider is not None and result.slider[0] != preview:
            page, slot, along = result.slider
            button_id = carousel.button_at(page, slot)
            if button_id in value_module.SLIDER_IDS:
                if self.module.drag(button_id, along):
                    out.haptics.append((self.tool_hand, 0.15, 0.01))
            spec = defaults.SLIDERS.get(button_id)
            if spec is not None:
                value = spec.value(along)
                if value != getattr(self.settings, spec.attr):
                    setattr(self.settings, spec.attr, value)
                    out.haptics.append((self.tool_hand, 0.15, 0.01))
        if result.slider_done is not None and result.slider_done[0] != preview:
            if carousel.button_at(*result.slider_done) in value_module.SLIDER_IDS:
                self.module.end_drag()
            self._save_settings()
        if result.dropped is not None:
            page, side, row, before, new_row = result.dropped
            moved = self._editing_layout()
            index = moved.move_page(page, side, row, before, new_row)
            self.ring.set_sides(self.shown_layout().sides())
            self.ring.focus_side(moved.pages[index].side)
            self._save_layout()
        if result.button_dropped is not None:
            page, slot, target_page, target_slot = result.button_dropped
            if target_page is None:
                moved = self.layout.hide_button(page, slot, self.wide)
            else:
                moved = self.layout.move_button(page, slot, target_page, target_slot, self.wide)
            if moved:
                self._save_layout()
                if target_page is None:
                    button = self.buttons.get(self.layout.hidden[-1]) if self.layout.hidden else None
                    self.toast(f"Hidden: {button.label}" if button else "Button hidden")
        prof.lap("ui_misc")
        edit = self.module.update(frame, dragging=self.ring.slider_drag is not None, blocked=bool(getattr(self.active_tool, "busy", False)))
        out.haptics += edit.haptics
        if edit.message:
            self.toast(edit.message)
        prof.lap("ui_module")
        editing = self.panel_editor if self.carousel == "editor" else None
        labels = {**self.labels(), **self.module.labels(), **(editing.labels() if editing is not None else {})}
        sliders = {**self.slider_states(), **self.module.slider_states()} if self.module.is_open else self.slider_states()
        readouts = {**(self.module.readouts() if self.module.is_open else {}), **(editing.readouts() if editing is not None else {})}
        lit = self.active_actions | self.module.picked_actions() | (editing.lit_actions() if editing is not None else frozenset())
        titles = {**self.module.titles(), **(editing.titles() if editing is not None else {})}
        self.view.update(self.ring, result, carousel, self.view_buttons, frame.head.position, lit, labels, sliders,
                         titles, readouts or None)
        prof.lap("ui_view")
        self.radial_view.update(quick, [labels.get(f, self.buttons[f].label) for f in quick.items],
                                centre=labels.get(quick.hub, self.buttons[quick.hub].label) if quick.hub else None)
        tooltip = self._tooltip(result, frame.dt, labels)
        text = readout or self.gesture_text
        if self.help.update(frame.dt):
            self._help_ended()
        self.feedback.update(frame.head, self.toasts.update(frame.dt), tooltip, text or None, self._lock_hint(frame),
                             self._wrist_anchor(frame), self._help_cards(frame) if self.help.visible else None)
        prof.lap("ui_feedback")

        if result.activated is not None and result.activated[0] != preview:
            button_id = carousel.button_at(*result.activated)
            if button_id in self._editor_buttons and self.panel_editor is not None:
                step = self.panel_editor.activate(button_id)
                if step.message:
                    self.toast(step.message)
                if step.done:
                    self.close_panel_editor(step.applied)
                out.activated = self._editor_buttons[button_id].action
            elif button_id in self.module.buttons:
                self.module.activate(button_id)
                out.activated = self.module.buttons[button_id].action
                if button_id in value_module.COLOUR_IDS:          # a swatch colours the selected objects
                    self._run(out.activated, out)
            else:
                self._activate(button_id, out)
        if quick.activated is not None:
            self._activate(quick.items[quick.activated], out)
        elif quick.activated_hub:
            self._activate(hub, out)

        if any("menu" in hand.pressed for hand in frame.hands):       # the controls card can be called at any time, with the menu button of either controller
            self._run("help:toggle", out)
        palette = frame.hands[self.palette_hand]
        for name, action in (("aux1", "doc:undo"), ("aux2", "doc:redo")):
            if name in palette.pressed:
                self._run(action, out)
                out.haptics.append((self.palette_hand, 0.4, 0.03))

        nav = self.navigator
        if nav.state == "two":
            self.ruler.update(nav.point(frame.hands, 0), nav.point(frame.hands, 1), frame.head,
                              nav.world.scale, self.mm_to_stage, self.system, nav.level, nav.scale_locked)
        elif nav.state == "one":
            self.ruler.show_single(nav.point(frame.hands, 0 if nav.gripping[0] else 1), frame.head, nav.world.scale, nav.level,
                                   nav.scale_locked)
        else:
            self.ruler.hide()

        tool_pointer = self.pointer_poses[self.tool_hand]
        if (s.pointer_mode == "laser" and self.ring.fade > 0.3 and tool_pointer.tracked and not nav.navigating and not self.radial.is_open
                and not self._disc_shown):
            self.pointer.show(tool_pointer.position, tool_pointer.direction, out.ray_end)
        else:
            self.pointer.hide()
        for hand, marker in enumerate(self.tips):
            ptr = self.pointer_poses[hand]
            # the tips stay visible while navigating; the tip of the palette hand is hidden while the carousel is shown
            palette_shown = hand == self.palette_hand and self.ring.fade > 0.3 and not nav.navigating
            if s.pointer_mode == "tip" and ptr.tracked and not palette_shown and not (hand == self.tool_hand and self._disc_shown):
                touching = hand == self.tool_hand and out.ray_end is not None
                marker.show(frame.hands[hand].aim.position, ptr.position, touching)
            else:
                marker.hide()
        return out

    def _tool_hand_buttons(self, frame, blocked, out):
        """Undo and redo on button2 of the tool hand and the options of the active tool on its stick.
        Returns (whether the tool owns the stick, the text of the readout or None)."""
        undo = self.undo_button.update(frame, blocked or bool(getattr(self.active_tool, "busy", False)))
        if undo.action is not None:
            self._run("doc:" + undo.action, out)
        out.haptics += undo.haptics
        chosen = self.options.update(frame, self.active_tool, blocked, self.system)
        out.haptics += chosen.haptics
        if chosen.message:
            self.toast(chosen.message)
        self._show_option_disc(frame, None if self.module.engaged else chosen.disc)
        return chosen.owns_stick, chosen.readout

    def _controller_frame(self, frame, hand, names, lift):
        """(position, right, forward, up) of a part of the controller of `hand`, or, when the model has no such part, of a point above
        the controller; None when the hand is not tracked."""
        aim = frame.hands[hand].aim
        if not aim.tracked:
            return None
        found = self.part_frame(hand, names, lift) if self.part_frame is not None else None
        if found is not None:
            return found
        q = aim.orientation
        up = mu.rotate(q, (0.0, 1.0, 0.0))
        return (mu.add(aim.position, mu.add(mu.mul(up, 0.04 + lift), mu.rotate(q, (0.0, 0.0, -0.03)))), mu.rotate(q, (1.0, 0.0, 0.0)),
                mu.rotate(q, (0.0, 0.0, -1.0)), up)

    def _show_option_disc(self, frame, disc):
        """Draw the option disc of the active tool on the controller of the tool hand: centred over the thumbstick, in the plane of the
        top of the controller, turning with it like the carousel. The stick pushed forward points at the top section."""
        placed = None if disc is None else self._controller_frame(frame, self.tool_hand, STICK_PARTS, OPTION_DISC_LIFT)
        self._disc_shown = placed is not None
        if placed is None:
            self.options_view.update(radial.RadialState(), [])
            return
        centre, right, forward, _ = placed
        state = radial.RadialState(open=True, items=disc.labels, selected=disc.selected, centre=centre, right=right, up=forward,
                                   cursor=tuple(c * OPTION_DISC_OUTER * 0.8 for c in disc.stick))
        self.options_view.update(state, disc.labels, disc.active, disc.hub)

    def _lock_hint(self, frame):
        """(position, right, forward, locked) of the padlock lying over the A button while the active tool shows one, else None."""
        locked = getattr(self.active_tool, "lock_state", None)
        if locked is None:
            return None
        placed = self._controller_frame(frame, self.tool_hand, BUTTON_PARTS, LOCK_LIFT)
        return None if placed is None else (placed[0], placed[1], placed[2], bool(locked))

    def _wrist_anchor(self, frame):
        """The point where the toasts hang: on the controller of the tool hand, behind the face buttons towards the wrist, turning with the
        controller; None when the tool hand is not tracked (the toasts then show in front of the head)."""
        placed = self._controller_frame(frame, self.tool_hand, BUTTON_PARTS, 0.0)
        if placed is None:
            return None
        position, _, forward, up = placed
        return mu.add(position, mu.add(mu.mul(forward, -WRIST_BACK), mu.mul(up, WRIST_LIFT)))

    def _help_cards(self, frame):
        """The controls cards: (centre of the title, title, lines) over the controller of the tool hand and over the one of the palette
        hand; a hand that is not tracked has none."""
        tool = self.active_tool
        up = mu.rotate(frame.head.orientation, (0.0, 1.0, 0.0))
        cards = []
        for hand, (title, lines) in ((self.tool_hand, controls_help.tool_card(getattr(tool, "label", "Tool") or "Tool", getattr(tool, "controls", ()))),
                                     (self.palette_hand, controls_help.palette_card())):
            placed = self._controller_frame(frame, hand, BUTTON_PARTS, 0.0)
            if placed is not None:
                cards.append((mu.add(placed[0], mu.mul(up, HELP_LIFT)), title, lines))
        return cards

    def _tooltip(self, result, dt, labels):
        """(text, centre, u, v) of the tooltip of the hovered button once it has been hovered for a moment, else None."""
        idle = (self.ring.lifted is None and self.ring.lifted_button is None and self.ring.press is None and self.ring.slider_drag is None
                and not self.radial.is_open)
        target = self.dwell.update(result.hover if idle and self.ring.fade > 0.8 else None, dt)
        if target is None:
            return None
        button = self.view_buttons.get(self.shown_layout().button_at(*target) or "")
        place = self.ring.slot_centre(*target)
        if button is None or place is None or button.id in value_module.NO_TOOLTIP or button.id.startswith("ed.key."):
            return None
        return (button.tip or labels.get(button.id, button.label), *place)

    def close(self):
        self.root.unref()
        self.overlay.unref()
