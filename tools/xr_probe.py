#!/usr/bin/env python3
"""Standalone OpenXR probe - is a runtime present, does it support what the VR addon needs, is an HMD attached?

Run with FreeCAD's bundled Python (has pyopenxr installed) or any Python with `pyopenxr`:

  & "$env:LOCALAPPDATA\\Programs\\FreeCAD 1.1\\bin\\python.exe" tools\\xr_probe.py

Stages (stops at first failure and says which one):
  1. runtime found + instance extensions (XR_KHR_opengl_enable is REQUIRED by freecad-xr-workbench)
  2. xrCreateInstance
  3. xrGetSystem(HEAD_MOUNTED_DISPLAY)  -> fails with FORM_FACTOR_UNAVAILABLE when no headset is connected/awake
  4. OpenGL graphics requirements (min/max GL version)
Note: creating an instance may auto-launch the runtime (e.g. SteamVR).
"""
import sys

import xr


def main() -> int:
    try:
        exts = xr.enumerate_instance_extension_properties()
    except Exception as e:
        print("1. FAIL no OpenXR runtime / cannot enumerate extensions:", repr(e))
        return 1
    names = sorted(e.extension_name.decode() if isinstance(e.extension_name, bytes) else e.extension_name for e in exts)
    print(f"1. OK   {len(names)} instance extensions")
    for want in ("XR_KHR_opengl_enable",):
        print(f"   {'OK  ' if want in names else 'MISSING'} {want}")
    if "XR_KHR_opengl_enable" not in names:
        return 1

    # The addon asks for API 1.0 by default (pyopenxr's newest, 1.1.x, is rejected by older runtimes
    # such as SteamVR with ApiVersionUnsupportedError). Mirror that: try 1.0 first, then newest.
    inst = None
    for label, ver in (("1.0", xr.Version(1, 0, xr.XR_VERSION_PATCH)), ("newest", xr.Version(xr.XR_CURRENT_API_VERSION))):
        try:
            inst = xr.create_instance(xr.InstanceCreateInfo(
                enabled_extension_names=["XR_KHR_opengl_enable"],
                application_info=xr.ApplicationInfo(application_name="blocadvr-probe", api_version=ver)))
            print(f"   instance created with API {label} ({ver})")
            break
        except Exception as e:
            print(f"   xrCreateInstance with API {label} ({ver}) failed: {e!r}")
    if inst is None:
        print("2. FAIL xrCreateInstance")
        return 2
    props = xr.get_instance_properties(inst)
    print("2. OK   runtime:", props.runtime_name.decode() if isinstance(props.runtime_name, bytes) else props.runtime_name,
          f"v{xr.Version(props.runtime_version) if hasattr(xr, 'Version') else props.runtime_version}")

    try:
        system = xr.get_system(inst, xr.SystemGetInfo(form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY))
    except Exception as e:
        print("3. FAIL no HMD system (headset not connected / SteamVR not ready?):", repr(e))
        xr.destroy_instance(inst)
        return 3
    sp = xr.get_system_properties(inst, system)
    name = sp.system_name.decode() if isinstance(sp.system_name, bytes) else sp.system_name
    print("3. OK   HMD:", name.rstrip("\x00"),
          f"max swapchain {sp.graphics_properties.max_swapchain_image_width}x{sp.graphics_properties.max_swapchain_image_height}")

    pfn = ctypes_fn = None
    try:
        import ctypes
        fn = ctypes.cast(xr.get_instance_proc_addr(inst, "xrGetOpenGLGraphicsRequirementsKHR"),
                         xr.PFN_xrGetOpenGLGraphicsRequirementsKHR)
        req = xr.GraphicsRequirementsOpenGLKHR()
        fn(inst, system, ctypes.byref(req))
        print(f"4. OK   OpenGL requirement: min {xr.Version(req.min_api_version_supported)} max {xr.Version(req.max_api_version_supported)}")
    except Exception as e:
        print("4. WARN could not query GL requirements:", repr(e))
    xr.destroy_instance(inst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
