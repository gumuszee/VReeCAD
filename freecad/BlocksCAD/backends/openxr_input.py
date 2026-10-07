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
"""OpenXR action set for the abstract inputs (docs/input-profiles.md) and its polling into `InputFrame`s.

Creates one action set with the actions of `profiles.ACTIONS`, suggests bindings for every interaction profile in
`profiles.PROFILES` that the instance can use, and attaches the set to the session.
`poll` syncs the actions and returns the raw per-hand values; edges are derived by `input.InputTracker`.
"""

import logging

import xr

from freecad.BlocksCAD import profiles
from freecad.BlocksCAD.input import HandInput, InputFrame, Pose

SIDES = ("left", "right")
_TYPES = {"pose": xr.ActionType.POSE_INPUT, "float": xr.ActionType.FLOAT_INPUT,
          "bool": xr.ActionType.BOOLEAN_INPUT, "haptic": xr.ActionType.VIBRATION_OUTPUT}

log = logging.getLogger(__name__)


def _pose(location):
    flags = location.location_flags
    valid = bool(flags & xr.SPACE_LOCATION_POSITION_VALID_BIT) and bool(flags & xr.SPACE_LOCATION_ORIENTATION_VALID_BIT)
    p, q = location.pose.position, location.pose.orientation
    return Pose((p.x, p.y, p.z), (q.x, q.y, q.z, q.w), valid)


class OpenXRInput:
    def __init__(self, instance, session, api_version, extensions, extra_action_sets=()):
        self.instance = instance
        self.session = session
        self.api_version = (api_version.major, api_version.minor)
        self.hand_paths = [xr.string_to_path(instance, f"/user/hand/{side}") for side in SIDES]
        self.action_set = xr.create_action_set(
            instance, xr.ActionSetCreateInfo(action_set_name="blockscad", localized_action_set_name="BlocksCAD", priority=0))
        self.actions = {}
        for name, kind in profiles.ACTIONS.items():
            self.actions[name] = xr.create_action(
                self.action_set,
                xr.ActionCreateInfo(action_type=_TYPES[kind], action_name=name.replace("_", ""),
                                    localized_action_name=name.replace("_", " "),
                                    count_subaction_paths=len(self.hand_paths), subaction_paths=self.hand_paths))
        self.suggested = []
        for profile in profiles.available_profiles(self.api_version, extensions):
            if self._suggest(profile):
                self.suggested.append(profile)
        self.aim_space = []
        self.grip_space = []
        for hand_path in self.hand_paths:
            self.aim_space.append(xr.create_action_space(
                session, xr.ActionSpaceCreateInfo(action=self.actions["aim_pose"], subaction_path=hand_path)))
            self.grip_space.append(xr.create_action_space(
                session, xr.ActionSpaceCreateInfo(action=self.actions["grip_pose"], subaction_path=hand_path)))
        self.action_sets = [self.action_set] + list(extra_action_sets)
        arr = (xr.ActionSet * len(self.action_sets))(*self.action_sets)
        xr.attach_session_action_sets(session, xr.SessionActionSetsAttachInfo(
            count_action_sets=len(self.action_sets), action_sets=arr))
        self.synced = False   # True after the first successful xrSyncActions

    # bindings
    def _binding(self, action, path):
        return xr.ActionSuggestedBinding(self.actions[action], xr.string_to_path(self.instance, path))

    def _suggest(self, profile):
        entries = []
        for side in SIDES:
            for action, path in profiles.bindings(profile, side).items():
                entries.append((action, path))
        profile_path = xr.string_to_path(self.instance, profile)

        def submit(items):
            xr.suggest_interaction_profile_bindings(
                self.instance,
                xr.InteractionProfileSuggestedBinding(
                    interaction_profile=profile_path, count_suggested_bindings=len(items),
                    suggested_bindings=(xr.ActionSuggestedBinding * len(items))(*items)))

        try:
            submit([self._binding(a, p) for a, p in entries])
            return True
        except Exception as error:
            log.warning("Binding suggestion for %s rejected as a whole (%s); retrying per binding", profile, error)
        accepted = []
        for action, path in entries:
            try:
                submit([self._binding(action, path)])
                accepted.append(self._binding(action, path))
            except Exception:
                log.debug("%s: %s rejected", profile, path)
        if not accepted:
            return False
        try:
            submit(accepted)
            return True
        except Exception as error:
            log.warning("Binding suggestion for %s failed: %s", profile, error)
            return False

    # polling
    def _float(self, action, hand):
        state = xr.get_action_state_float(self.session, xr.ActionStateGetInfo(
            action=self.actions[action], subaction_path=self.hand_paths[hand]))
        return state.current_state if state.is_active else 0.0

    def _bool(self, action, hand):
        state = xr.get_action_state_boolean(self.session, xr.ActionStateGetInfo(
            action=self.actions[action], subaction_path=self.hand_paths[hand]))
        return bool(state.current_state) if state.is_active else False

    def active_profile(self):
        try:
            state = xr.get_current_interaction_profile(self.session, self.hand_paths[1])
            if state.interaction_profile:
                return xr.path_to_string(self.instance, state.interaction_profile)
        except Exception:
            pass
        return None

    def poll(self, base_space, time, extra_active=()):
        """Sync the actions and read every hand. Returns an `InputFrame` without head pose and edges,
        or None while the session cannot deliver input (not focused)."""
        active = [xr.ActiveActionSet(s, xr.NULL_PATH) for s in [self.action_set] + list(extra_active)]
        arr = (xr.ActiveActionSet * len(active))(*active)
        try:
            xr.sync_actions(self.session, xr.ActionsSyncInfo(count_active_action_sets=len(active), active_action_sets=arr))
        except xr.exception.SessionNotFocused:
            return None
        self.synced = True
        frame = InputFrame(profile=self.active_profile())
        hands = []
        for hand in range(2):
            h = HandInput()
            h.aim = _pose(xr.locate_space(self.aim_space[hand], base_space, time))
            h.grip_pose = _pose(xr.locate_space(self.grip_space[hand], base_space, time))
            h.trigger = self._float("trigger", hand)
            h.grip = self._float("grip", hand)
            h.stick = (self._float("stick_x", hand), self._float("stick_y", hand))
            h.stick_click = self._bool("stick_click", hand)
            h.button1 = self._bool("button1", hand)
            h.button2 = self._bool("button2", hand)
            h.menu = self._bool("menu", hand)
            h.aux1 = self._bool("aux1", hand)
            h.aux2 = self._bool("aux2", hand)
            hands.append(h)
        frame.hands = tuple(hands)
        return frame

    def haptic(self, hand, amplitude=0.5, duration_s=0.05, frequency=0.0):
        """Vibrate a controller (frequency 0 lets the runtime choose)."""
        vib = xr.HapticVibration(duration=int(duration_s * 1e9), frequency=frequency, amplitude=amplitude)
        xr.apply_haptic_feedback(
            self.session,
            xr.HapticActionInfo(action=self.actions["haptic"], subaction_path=self.hand_paths[hand]), vib)   # pyopenxr casts the struct itself

    def destroy(self):
        for space in self.aim_space + self.grip_space:
            try:
                xr.destroy_space(space)
            except Exception:
                pass
