# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""Mapping of the abstract inputs to OpenXR input paths per interaction profile (docs/input-profiles.md).

Pure data, no OpenXR import. An abstract input maps to one component path below `/user/hand/<side>/input/`.
The abstract inputs: trigger, grip (analog), stick (x, y), stick_click, button1, button2, menu, aux1, aux2 (digital; the last two
only where the controller has more buttons).
"""

# component paths per hand; "{h}" is replaced by "left" / "right"
_COMMON = {
    "aim_pose": "/user/hand/{h}/input/aim/pose",
    "grip_pose": "/user/hand/{h}/input/grip/pose",
    "haptic": "/user/hand/{h}/output/haptic",
    "trigger": "/user/hand/{h}/input/trigger/value",
}


def _stick(component):
    return {
        "stick_x": f"/user/hand/{{h}}/input/{component}/x",
        "stick_y": f"/user/hand/{{h}}/input/{component}/y",
        "stick_click": f"/user/hand/{{h}}/input/{component}/click",
    }


_TOUCH_LIKE = {  # Quest Touch family and Pico 4: x/y on the left, a/b on the right
    "left": {"grip": "/user/hand/left/input/squeeze/value",
             "button1": "/user/hand/left/input/x/click", "button2": "/user/hand/left/input/y/click",
             "menu": "/user/hand/left/input/menu/click"},
    "right": {"grip": "/user/hand/right/input/squeeze/value",
              "button1": "/user/hand/right/input/a/click", "button2": "/user/hand/right/input/b/click"},
}

# profile path -> {side: {abstract: path}} ; "both" entries apply to both hands
PROFILES = {
    "/interaction_profiles/valve/frame_controller_valve": {
        "extension": "XR_VALVE_frame_controller_interaction",
        "both": {**_stick("thumbstick"), "grip": "/user/hand/{h}/input/squeeze/value"},
        "left": {"button1": "/user/hand/left/input/dpad_up/click",
                 "button2": "/user/hand/left/input/dpad_down/click",
                 "aux1": "/user/hand/left/input/dpad_left/click",
                 "aux2": "/user/hand/left/input/dpad_right/click",
                 "menu": "/user/hand/left/input/view/click"},
        "right": {"button1": "/user/hand/right/input/a/click",
                  "button2": "/user/hand/right/input/b/click",
                  "menu": "/user/hand/right/input/menu/click"},
    },
    "/interaction_profiles/oculus/touch_controller": {
        "both": {**_stick("thumbstick")}, **_TOUCH_LIKE,
    },
    "/interaction_profiles/meta/touch_plus_controller": {
        "min_api": (1, 1), "both": {**_stick("thumbstick")}, **_TOUCH_LIKE,
    },
    "/interaction_profiles/meta/touch_pro_controller": {
        "min_api": (1, 1), "both": {**_stick("thumbstick")}, **_TOUCH_LIKE,
    },
    "/interaction_profiles/bytedance/pico4_controller": {
        "min_api": (1, 1), "both": {**_stick("thumbstick")}, **_TOUCH_LIKE,
    },
    "/interaction_profiles/valve/index_controller": {
        "both": {**_stick("thumbstick"), "grip": "/user/hand/{h}/input/squeeze/value",
                 "button1": "/user/hand/{h}/input/a/click", "button2": "/user/hand/{h}/input/b/click"},
    },
    "/interaction_profiles/htc/vive_controller": {
        # the trackpad click serves as button2; the trackpad itself is the stick (no separate stick click)
        "both": {"stick_x": "/user/hand/{h}/input/trackpad/x", "stick_y": "/user/hand/{h}/input/trackpad/y",
                 "grip": "/user/hand/{h}/input/squeeze/click",
                 "button1": "/user/hand/{h}/input/menu/click",
                 "button2": "/user/hand/{h}/input/trackpad/click"},
    },
    "/interaction_profiles/microsoft/motion_controller": {
        "both": {**_stick("thumbstick"), "grip": "/user/hand/{h}/input/squeeze/click",
                 "button1": "/user/hand/{h}/input/menu/click",
                 "button2": "/user/hand/{h}/input/trackpad/click"},
    },
}

# Abstract inputs and their OpenXR action types
ACTIONS = {
    "aim_pose": "pose", "grip_pose": "pose", "haptic": "haptic",
    "trigger": "float", "grip": "float", "stick_x": "float", "stick_y": "float",
    "stick_click": "bool", "button1": "bool", "button2": "bool", "menu": "bool", "aux1": "bool", "aux2": "bool",
}


def bindings(profile, side):
    """Abstract input -> concrete path for one hand ("left" / "right") of an interaction profile."""
    spec = PROFILES[profile]
    merged = dict(_COMMON)
    merged.update(spec.get("both", {}))
    merged.update(spec.get(side, {}))
    return {name: path.replace("{h}", side) for name, path in merged.items()}


def available_profiles(api_version=(1, 0), extensions=()):
    """Profile paths usable with an instance of the given API version and enabled extensions."""
    result = []
    for path, spec in PROFILES.items():
        if tuple(spec.get("min_api", (1, 0))) > tuple(api_version):
            continue
        ext = spec.get("extension")
        if ext and ext not in extensions:
            continue
        result.append(path)
    return result
