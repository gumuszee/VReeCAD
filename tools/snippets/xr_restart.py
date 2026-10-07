# Hot-reload the VR addon's Python modules in the running FreeCAD and restart the XR viewer.
# Saves a full FreeCAD restart when iterating on addon code:  fc_rpc.py exec -f tools/snippets/xr_restart.py
# Note: reloading only affects modules listed below (in dependency order); for class-identity-sensitive changes prefer restarting FreeCAD.
import importlib
import FreeCADGui
import freecad.BlocksCAD.commonXR as cxr
cxr.close_xr_viewer()
_mods = ["profiling", "core.mathutil", "core.units", "core.navigation", "core.stage", "core.snapping", "core.grab", "core.selecting", "core.values", "cad", "cad.primitives", "cad.meshes", "cad.edit", "cad.values", "cad.picking", "render.ghost", "render.highlight", "input", "profiles", "gltf", "render.gltf_coin", "render.controller_shape", "render.offscreen",
         "backends.openxr_models", "backends.openxr_input", "backends.sim",
         "ui.layout", "ui.style", "ui.ring", "ui.ring_view", "ui.radial", "ui.radial_view", "ui.ruler", "ui.settings", "ui.pointing", "ui.pointer", "ui.defaults", "ui.toast", "ui.undo_button", "ui.options", "ui.value_module", "ui.feedback_view", "ui.controller", "tools.base", "tools.registry", "tools.manager", "tools", "tools.primitives", "tools.touch", "tools.select", "tools.move",
         "controllerXR", "commonXR"]
for _m in _mods:
    importlib.reload(importlib.import_module("freecad.BlocksCAD." + _m))
import freecad.BlocksCAD.commonXR as cxr
FreeCADGui.activateWorkbench("BlocksCADWorkbench")
cxr.open_xr_viewer()
print("XR viewer restarted with reloaded modules")
