#!/usr/bin/env python3
"""Discover which input/output paths a runtime accepts for an OpenXR interaction profile (instance only; no headset, no session).

The runtime validates suggested bindings per interaction profile, so each candidate path is suggested on its own and the
accept/reject result is recorded. Use it where the profile's path list is not published (e.g. Valve Steam Frame controller).

Run with FreeCAD's bundled Python (has pyopenxr):
  & "$env:LOCALAPPDATA\\Programs\\FreeCAD 1.1\\bin\\python.exe" tools\\xr_probe_paths.py [profile] [ext1,ext2] [-v]
Default profile: /interaction_profiles/valve/frame_controller_valve  with extension XR_VALVE_frame_controller_interaction.
Examples:
  ... tools\\xr_probe_paths.py /interaction_profiles/oculus/touch_controller
  ... tools\\xr_probe_paths.py /interaction_profiles/meta/touch_plus_controller XR_META_touch_controller_plus
"""
import ctypes
import sys

import xr

VERBOSE = "-v" in sys.argv
sys.argv = [a for a in sys.argv if a != "-v"]
PROFILE = sys.argv[1] if len(sys.argv) > 1 else "/interaction_profiles/valve/frame_controller_valve"
EXTS = ([e for e in sys.argv[2].split(",") if e] if len(sys.argv) > 2 else
        (["XR_VALVE_frame_controller_interaction"] if "frame_controller" in PROFILE else []))

COMPONENTS = ["a", "b", "x", "y", "menu", "view", "system", "bumper", "trigger", "squeeze", "grip", "thumbstick",
              "thumbrest", "trackpad", "dpad_up", "dpad_down", "dpad_left", "dpad_right", "dpad", "shoulder", "select", "start"]
IDENTIFIERS = ["click", "touch", "value", "force", "x", "y"]


def main() -> int:
    inst = xr.create_instance(xr.InstanceCreateInfo(
        enabled_extension_names=EXTS,
        application_info=xr.ApplicationInfo(application_name="blocadvr-path-probe", api_version=xr.Version(1, 0, xr.XR_VERSION_PATCH))))
    aset = xr.create_action_set(inst, xr.ActionSetCreateInfo(action_set_name="probe", localized_action_set_name="probe", priority=0))
    profile = xr.string_to_path(inst, PROFILE)
    hands = ["left", "right"]
    sub = (xr.Path * 2)(*[xr.string_to_path(inst, f"/user/hand/{h}") for h in hands])

    def make(name, kind):
        return xr.create_action(aset, xr.ActionCreateInfo(
            action_type=kind, action_name=name, localized_action_name=name,
            count_subaction_paths=2, subaction_paths=sub))

    bool_a = make("b", xr.ActionType.BOOLEAN_INPUT)
    float_a = make("f", xr.ActionType.FLOAT_INPUT)
    pose_a = make("p", xr.ActionType.POSE_INPUT)
    haptic_a = make("h", xr.ActionType.VIBRATION_OUTPUT)

    def accepted(action, path_str):
        try:
            p = xr.string_to_path(inst, path_str)
            b = [xr.ActionSuggestedBinding(action, p)]
            xr.suggest_interaction_profile_bindings(inst, xr.InteractionProfileSuggestedBinding(
                interaction_profile=profile, count_suggested_bindings=1,
                suggested_bindings=(xr.ActionSuggestedBinding * 1)(*b)))
            return True
        except Exception:
            return False

    print(f"profile {PROFILE}  extensions {EXTS}")
    for hand in hands:
        found = []
        for comp in COMPONENTS:
            for ident in IDENTIFIERS:
                path = f"/user/hand/{hand}/input/{comp}/{ident}"
                for kind, action in (("bool", bool_a), ("float", float_a)):
                    if accepted(action, path):
                        found.append(f"{comp}/{ident}:{kind}")
            path = f"/user/hand/{hand}/input/{comp}"
            for kind, action in (("bool", bool_a), ("float", float_a)):
                if accepted(action, path):
                    found.append(f"{comp}:{kind}")
        for pose in ("grip/pose", "aim/pose", "palm_ext/pose"):
            if accepted(pose_a, f"/user/hand/{hand}/input/{pose}"):
                found.append(f"{pose}:pose")
        if accepted(haptic_a, f"/user/hand/{hand}/output/haptic"):
            found.append("haptic:out")
        extras = [f for f in found if f.startswith(("grip/pose", "aim/pose", "palm", "haptic"))]
        comps = sorted({f.split("/")[0].split(":")[0] for f in found if f not in extras})
        print(f"\n{hand}: accepted components: {', '.join(comps)}")
        print("  poses/outputs:", ", ".join(extras) or "none")
        if VERBOSE:
            print("  all accepted paths:", ", ".join(found))
    xr.destroy_instance(inst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
