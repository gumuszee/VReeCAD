# Render the cached runtime controller models (GLB) offscreen from a few viewpoints, to check the glTF -> Coin loader without a headset.
# Prerequisite: GLBs in %LOCALAPPDATA%\VReeCAD\cache\rendermodels (written by tools/snippets/xr_render_models.py during a FOCUSED session).
# Run:  python tools/fc_rpc.py exec -f tools/snippets/render_controller_models.py
# Output: <RENDER_DIR>/controller_<uuid8>_<view>.png (default RENDER_DIR = %TEMP%\vreecad_renders). Set RENDER_DIR before exec to change it.
import glob
import importlib
import os
import time

import freecad.VReeCAD.gltf as _gltf
import freecad.VReeCAD.render.gltf_coin as _gc
import freecad.VReeCAD.render.offscreen as _off
for _m in (_gltf, _gc, _off):
    importlib.reload(_m)

_out = globals().get("RENDER_DIR", os.path.join(os.environ.get("TEMP", "."), "vreecad_renders"))
os.makedirs(_out, exist_ok=True)
_cache = os.path.join(os.environ.get("LOCALAPPDATA", "."), "VReeCAD", "cache", "rendermodels")
_views = {  # eye, target, up (metres, model space; the model extends along +Z)
    "side": ((0.35, 0.05, 0.08), (0.0, -0.01, 0.08), (0, 1, 0)),
    "top": ((0.0, 0.40, 0.08), (0.0, 0.0, 0.08), (0, 0, -1)),
    "back": ((0.05, 0.1, 0.45), (0.0, -0.01, 0.08), (0, 1, 0)),
}
for _path in sorted(glob.glob(os.path.join(_cache, "*.glb"))):
    _t = time.time()
    _model = _gc.load_glb(open(_path, "rb").read())
    _dt = time.time() - _t
    print(os.path.basename(_path), "built in %.2fs" % _dt, "parts:", ascii(sorted(_model.parts)))
    for _name, (_eye, _tgt, _up) in _views.items():
        _img = _off.render(_model.root, _eye, target=_tgt, up=_up, size=(640, 480), ambient=1.0, background=(0.55, 0.6, 0.75))
        _off.save(_img, os.path.join(_out, "controller_%s_%s.png" % (os.path.basename(_path)[:8], _name)))
print("renders in", _out)
