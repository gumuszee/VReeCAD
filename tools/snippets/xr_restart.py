# Hot-reload the VR addon's Python modules in the running FreeCAD and restart the XR viewer.
# Saves a full FreeCAD restart when iterating on addon code:  fc_rpc.py exec -f tools/snippets/xr_restart.py
# Note: reloading only affects modules listed below (in dependency order); for class-identity-sensitive changes prefer restarting FreeCAD
# (cad/block.py is not listed: the proxies of existing blocks would keep the old class). A tool that is missing from the list drops out of the registry.
import importlib
import FreeCADGui
import freecad.VReeCAD.commonXR as cxr
cxr.close_xr_viewer()
_mods = ["profiling", "core.mathutil", "core.units", "core.navigation", "core.stage", "core.snapping", "core.grab", "core.selecting", "core.values", "cad", "cad.primitives", "cad.meshes", "cad.edit", "cad.attach", "cad.blockgeom", "cad.changes", "cad.anchors", "cad.colour", "cad.values", "cad.picking", "render.ghost", "render.highlight", "input", "profiles", "gltf", "render.gltf_coin", "render.controller_shape", "render.offscreen",
         "backends.openxr_models", "backends.openxr_input", "backends.sim",
         "ui.layout", "ui.style", "ui.ring", "ui.ring_view", "ui.radial", "ui.radial_view", "ui.ruler", "ui.settings", "ui.pointing", "ui.pointer", "ui.defaults", "ui.toast", "ui.undo_button", "ui.options", "ui.value_module", "ui.feedback_view", "ui.controller", "tools.base", "tools.registry", "tools.manager", "tools", "tools.primitives", "tools.touch", "tools.select", "tools.move", "tools.pushpull", "tools.points", "tools.sketch",
         "controllerXR", "commonXR"]
for _m in _mods:
    importlib.reload(importlib.import_module("freecad.VReeCAD." + _m))
import freecad.VReeCAD.commonXR as cxr
FreeCADGui.activateWorkbench("VReeCADWorkbench")
cxr.open_xr_viewer()
print("XR viewer restarted with reloaded modules")
