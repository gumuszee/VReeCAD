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
"""Detects a FreeCAD that renders on another GPU than the one SteamVR composes on (hybrid graphics on Linux, docs/setup.md).

On a laptop with an AMD or Intel iGPU and an NVIDIA GPU, FreeCAD renders on the iGPU unless it is started on the NVIDIA GPU, while the
SteamVR compositor runs on the NVIDIA GPU. The runtime then has to share a texture across GPUs, which crashes FreeCAD in
`xrEndFrame`. The check is a heuristic: it warns when the renderer of FreeCAD is an AMD, an Intel or a software renderer and the
machine has an NVIDIA GPU. It never blocks the viewer; the user may open it anyway. Everything here is plain Python and takes its
inputs as arguments, so it runs without FreeCAD (tests/test_gpucheck.py)."""

import glob
import os
import platform
import re

NVIDIA = "nvidia"
AMD = "amd"
INTEL = "intel"
SOFTWARE = "software"
UNKNOWN = "unknown"

# set to any non-empty value to skip the check
SKIP_ENV = "VREECAD_SKIP_GPU_CHECK"

_PCI_VENDORS = {"0x10de": NVIDIA, "0x1002": AMD, "0x8086": INTEL}
_EGL_NVIDIA_JSON = ("/usr/share/glvnd/egl_vendor.d/*nvidia*.json", "/etc/glvnd/egl_vendor.d/*nvidia*.json")


def gpu_vendors(drm_root="/sys/class/drm"):
    """The set of GPU vendors (NVIDIA, AMD, INTEL) of the display devices `cardN` under `drm_root`."""
    found = set()
    for path in glob.glob(os.path.join(drm_root, "card*", "device", "vendor")):
        if not re.fullmatch(r"card\d+", os.path.basename(os.path.dirname(os.path.dirname(path)))):
            continue
        try:
            with open(path, encoding="ascii") as f:
                vendor = _PCI_VENDORS.get(f.read().strip().lower())
        except OSError:
            continue
        if vendor:
            found.add(vendor)
    return found


def renderer_vendor(renderer):
    """The vendor named by a GL_RENDERER string: NVIDIA, AMD, INTEL, SOFTWARE or UNKNOWN."""
    r = (renderer or "").lower()
    if "nvidia" in r:
        return NVIDIA
    if any(s in r for s in ("llvmpipe", "softpipe", "swrast")):
        return SOFTWARE
    if "amd" in r or "radeon" in r or "ati " in r:
        return AMD
    if "intel" in r:
        return INTEL
    return UNKNOWN


def nvidia_launch_command(egl_json_globs=_EGL_NVIDIA_JSON):
    """The shell command that starts FreeCAD on the NVIDIA GPU, for Wayland (EGL) and X11 (GLX) alike."""
    egl_json = "/usr/share/glvnd/egl_vendor.d/10_nvidia.json"
    for pattern in egl_json_globs:
        matches = sorted(glob.glob(pattern))
        if matches:
            egl_json = matches[0]
            break
    return (f"env __EGL_VENDOR_LIBRARY_FILENAMES={egl_json} __GLX_VENDOR_LIBRARY_NAME=nvidia "
            "__NV_PRIME_RENDER_OFFLOAD=1 FreeCAD")


def check(renderer, vendors=None, system=None, environ=None):
    """None when the viewer can start, otherwise the text of the warning.

    `renderer` is GL_RENDERER of the context FreeCAD renders with (None when it could not be read, which never warns)."""
    system = platform.system() if system is None else system
    environ = os.environ if environ is None else environ
    if system != "Linux" or environ.get(SKIP_ENV) or not renderer:
        return None
    vendors = gpu_vendors() if vendors is None else vendors
    if NVIDIA not in vendors or renderer_vendor(renderer) not in (AMD, INTEL, SOFTWARE):
        return None
    return (f"FreeCAD renders on \"{renderer}\", but this computer also has an NVIDIA GPU, and SteamVR composes on it. "
            "A viewer on another GPU can crash FreeCAD when the first frame is submitted.\n\n"
            "Close FreeCAD and start it on the NVIDIA GPU:\n\n"
            f"{nvidia_launch_command()}\n\n"
            "docs/setup.md (Linux) describes a launcher entry that does this. "
            f"Setting {SKIP_ENV}=1 turns this check off.")
