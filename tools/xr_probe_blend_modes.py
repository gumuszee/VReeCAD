#!/usr/bin/env python3
"""List the environment blend modes and passthrough related extensions of the active OpenXR runtime (instance and system only; no session).

OPAQUE is plain VR. ALPHA_BLEND or ADDITIVE is what the addon's AR mode needs for passthrough (commonXR.check_xr_blend_modes).
Passthrough extensions (XR_FB_passthrough, XR_HTC_passthrough, ...) are an alternative route that the addon does not use.
The headset must be connected to SteamVR (it does not have to be worn).

Run with FreeCAD's bundled Python (has pyopenxr):
  & "$env:LOCALAPPDATA\\Programs\\FreeCAD 1.1\\bin\\python.exe" tools\\xr_probe_blend_modes.py [-v]
-v lists every extension the runtime offers.
"""
import sys

import xr

VERBOSE = "-v" in sys.argv
KEYWORDS = ("passthrough", "blend", "composition", "alpha", "camera", "environment")


def main() -> int:
    exts = sorted(e.extension_name.decode() for e in xr.enumerate_instance_extension_properties())
    inst = xr.create_instance(xr.InstanceCreateInfo(
        application_info=xr.ApplicationInfo(application_name="blocadvr-blend-probe", api_version=xr.Version(1, 0, xr.XR_VERSION_PATCH))))
    try:
        props = xr.get_instance_properties(inst)
        print(f"runtime {props.runtime_name.decode()} {props.runtime_version}")
        system_id = xr.get_system(inst, xr.SystemGetInfo(form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY))
        sp = xr.get_system_properties(inst, system_id)
        print(f"system {sp.system_name.decode()}")
        modes = xr.enumerate_environment_blend_modes(inst, system_id, xr.ViewConfigurationType.PRIMARY_STEREO)
        print("blend modes:", ", ".join(xr.EnvironmentBlendMode(m).name for m in modes))
        ar_ok = any(m in modes for m in (xr.EnvironmentBlendMode.ALPHA_BLEND, xr.EnvironmentBlendMode.ADDITIVE))
        print("addon AR mode possible:", "yes" if ar_ok else "no (OPAQUE only)")
    finally:
        xr.destroy_instance(inst)
    related = [e for e in exts if any(k in e.lower() for k in KEYWORDS)]
    print("related extensions:", ", ".join(related) or "none")
    if VERBOSE:
        print("all extensions:", ", ".join(exts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
