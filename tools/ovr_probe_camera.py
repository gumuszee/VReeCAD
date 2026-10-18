#!/usr/bin/env python3
"""Ask SteamVR (OpenVR API) whether the connected headset offers a tracked camera, i.e. whether passthrough can reach an app.

Connects as a background application (does not start SteamVR or take over the display). Prints the HMD model, the camera
properties, the camera frame size and whether a frame can be acquired. The Rectus OpenXR passthrough layer needs a working
camera here. Development tool only; the addon does not use OpenVR.

The pyopenvr package is not part of FreeCAD. Install it into a separate folder and pass that folder as the first argument:
  & "$env:LOCALAPPDATA\\Programs\\FreeCAD 1.1\\bin\\python.exe" -m pip install --target <dir> --no-deps openvr
Run:
  & "$env:LOCALAPPDATA\\Programs\\FreeCAD 1.1\\bin\\python.exe" -I tools\\ovr_probe_camera.py <dir>
"""
import sys

if len(sys.argv) < 2:
    sys.exit(__doc__)
sys.path.insert(0, sys.argv[1])

import openvr  # noqa: E402


def main() -> int:
    try:
        openvr.init(openvr.VRApplication_Background)
    except openvr.OpenVRError as e:
        print("cannot connect to SteamVR (is it running with the headset connected?):", e)
        return 1
    try:
        sysv = openvr.VRSystem()
        cam = openvr.VRTrackedCamera()
        hmd = openvr.k_unTrackedDeviceIndex_Hmd

        def prop(getter, p):
            try:
                return getter(hmd, p)
            except Exception as e:
                return f"error: {e}"

        print("HMD model:", prop(sysv.getStringTrackedDeviceProperty, openvr.Prop_ModelNumber_String))
        print("driver:", prop(sysv.getStringTrackedDeviceProperty, openvr.Prop_TrackingSystemName_String))
        print("Prop_HasCamera_Bool:", prop(sysv.getBoolTrackedDeviceProperty, openvr.Prop_HasCamera_Bool))
        print("Prop_HasCameraComponent_Bool:", prop(sysv.getBoolTrackedDeviceProperty, openvr.Prop_HasCameraComponent_Bool))
        print("Prop_NumCameras_Int32:", prop(sysv.getInt32TrackedDeviceProperty, openvr.Prop_NumCameras_Int32))
        try:
            print("IVRTrackedCamera.hasCamera:", cam.hasCamera(hmd))
        except Exception as e:
            print("IVRTrackedCamera.hasCamera: error", e)
        try:
            print("frame size (w, h, bufferSize):", cam.getCameraFrameSize(hmd, openvr.VRTrackedCameraFrameType_Undistorted))
        except Exception as e:
            print("frame size: error", e)
        try:
            handle = cam.acquireVideoStreamingService(hmd)
            print("video streaming service: acquired")
            cam.releaseVideoStreamingService(handle)
        except Exception as e:
            print("video streaming service: error", e)
        try:
            print("enableCamera setting:", openvr.VRSettings().getBool("camera", "enableCamera"))
        except Exception as e:
            print("enableCamera setting: error", e)
    finally:
        openvr.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
