# Headset-free test of the Sim backend: scripted head and controllers over the active document, rendered offscreen.
# Prerequisite: a document with some geometry is active in the running FreeCAD (the script creates a box if there is none).
# Run:  python tools/fc_rpc.py exec -f tools/snippets/sim_demo.py
# Output: <SIM_DIR>/sim_*.png (default %TEMP%\vreecad_renders) and the edge events of the scripted frames.
import importlib
import os

import FreeCAD
import FreeCADGui
import freecad.VReeCAD.input as _input
import freecad.VReeCAD.render.gltf_coin as _gc
import freecad.VReeCAD.render.controller_shape as _cs
import freecad.VReeCAD.render.offscreen as _off
import freecad.VReeCAD.backends.sim as _sim
for _m in (_input, _gc, _cs, _off, _sim):
    importlib.reload(_m)

_out = globals().get("SIM_DIR", os.path.join(os.environ.get("TEMP", "."), "vreecad_renders"))
os.makedirs(_out, exist_ok=True)
if FreeCAD.ActiveDocument is None:
    FreeCAD.newDocument("SimDemo")
if not FreeCAD.ActiveDocument.Objects:
    _box = FreeCAD.ActiveDocument.addObject("Part::Box", "Box")
    _box.Length, _box.Width, _box.Height = 200, 200, 200
    FreeCAD.ActiveDocument.recompute()
_scene = FreeCADGui.ActiveDocument.ActiveView.getSceneGraph()

_s = _sim.SimSession(_scene)
try:
    _s.input.set_head(position=(0.0, 1.5, 1.2), look_at_point=(0.0, 0.1, 0.0))
    _s.input.set_hand(1, position=(0.2, 1.1, 0.5), point_at=(0.1, 0.1, 0.0))
    _s.input.set_hand(0, position=(-0.2, 1.1, 0.5), point_at=(-0.1, 0.1, 0.0))
    _f = _s.frame()
    _off.save(_s.render("head", (800, 600), ambient=0.7), os.path.join(_out, "sim_idle.png"))
    # script: pull the right trigger and press button1 on the left hand
    _s.input.set_hand(1, trigger=1.0)
    _s.input.set_hand(0, button1=True)
    _f = _s.frame()
    print("pressed:", sorted(_f.right.pressed), sorted(_f.left.pressed))
    _off.save(_s.render("head", (800, 600)), os.path.join(_out, "sim_pressed.png"))
    _s.input.set_hand(1, trigger=0.0)
    _f = _s.frame()
    print("released:", sorted(_f.right.released))
    _off.save(_s.render_stereo((480, 480)), os.path.join(_out, "sim_stereo.png"))
finally:
    _s.close()
print("renders in", _out)
