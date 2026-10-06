# Hot-reload the VR addon's Python modules in the running FreeCAD and restart the XR viewer.
# Saves a full FreeCAD restart when iterating on addon code:  fc_rpc.py exec -f tools/snippets/xr_restart.py
# Note: reloading only affects modules listed below; for class-identity-sensitive changes prefer restarting FreeCAD.
import importlib
import FreeCADGui
import freecad.BlocksCAD.commonXR as cxr
cxr.close_xr_viewer()
import freecad.BlocksCAD as _pkg
_mods = ["qtWidgetRender", "previewCoin", "menuCoin", "controllerXR", "movementXR", "documentInteraction", "commonXR"]
for _m in _mods:
    importlib.reload(importlib.import_module("freecad.BlocksCAD." + _m))
import freecad.BlocksCAD.commonXR as cxr
FreeCADGui.activateWorkbench("BlocksCADWorkbench")
cxr.open_xr_viewer()
print("XR viewer restarted with reloaded modules")
