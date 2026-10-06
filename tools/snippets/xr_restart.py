# Hot-reload the VR addon's Python modules in the running FreeCAD and restart the XR viewer.
# Saves a full FreeCAD restart when iterating on addon code:  fc_rpc.py exec -f tools/snippets/xr_restart.py
# Note: reloading only affects modules listed below (in dependency order); for class-identity-sensitive changes prefer restarting FreeCAD.
import importlib
import FreeCADGui
import freecad.BlocksCAD.commonXR as cxr
cxr.close_xr_viewer()
import freecad.BlocksCAD as _pkg
_mods = ["core.mathutil", "core.units", "core.navigation", "input", "profiles", "gltf", "render.gltf_coin", "render.controller_shape", "render.offscreen",
         "backends.openxr_models", "backends.openxr_input", "backends.sim",
         "ui.layout", "ui.style", "ui.ring", "ui.ring_view", "ui.ruler", "ui.defaults", "ui.controller", "tools.base", "tools.registry", "tools.manager", "tools", "tools.legacy",
         "qtWidgetRender", "previewCoin", "menuCoin", "controllerXR", "documentInteraction", "commonXR"]
for _m in _mods:
    importlib.reload(importlib.import_module("freecad.BlocksCAD." + _m))
import freecad.BlocksCAD.commonXR as cxr
FreeCADGui.activateWorkbench("BlocksCADWorkbench")
cxr.open_xr_viewer()
print("XR viewer restarted with reloaded modules")
