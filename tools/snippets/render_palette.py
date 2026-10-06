# Render the radial palette view offscreen (open, with one item highlighted) to check size and legibility without a headset.
# Run:  python tools/fc_rpc.py exec -f tools/snippets/render_palette.py
# Output: <RENDER_DIR>/palette.png (default %TEMP%\blockscad_renders); PALETTE_DISTANCE (metres, default 0.45) sets the viewing distance.
import importlib
import os

import freecad.BlocksCAD.input as _input
import freecad.BlocksCAD.ui.palette as _pal
import freecad.BlocksCAD.ui.palette_view as _pv
import freecad.BlocksCAD.render.offscreen as _off
import freecad.BlocksCAD.tools as _tools
import freecad.BlocksCAD.tools.legacy  # noqa: F401  (registers the inherited tools)
for _m in (_input, _pal, _pv):
    importlib.reload(_m)

_out = globals().get("RENDER_DIR", os.path.join(os.environ.get("TEMP", "."), "blockscad_renders"))
os.makedirs(_out, exist_ok=True)
_dist = globals().get("PALETTE_DISTANCE", 0.45)
_p = _pal.RadialPalette([(n, _tools.label_of(n)) for n in _tools.names()])
_v = _pv.PaletteView(_p)
_p.is_open = True
_p.highlighted = 1
_v.update()
_img = _off.render(_v.root, (0.0, 0.0, _dist), target=(0.0, 0.0, 0.0), size=(900, 700), fov=1.2, ambient=1.0,
                   background=(0.35, 0.4, 0.5))
_off.save(_img, os.path.join(_out, "palette.png"))
print("palette rendered at", _dist, "m ->", os.path.join(_out, "palette.png"))
