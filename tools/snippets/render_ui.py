# Render the user interface (palette ring with faces, navigation readout) from a simulated head, without a headset.
# The Sim session runs the same UiController as the headset path: a scripted head looks at the left controller, the right
# controller points at a face, the trigger activates it.
# Run:  python tools/fc_rpc.py exec -f tools/snippets/render_ui.py
# Output: <RENDER_DIR>/ui_*.png (default %TEMP%\blockscad_renders). Globals: UI_DISTANCE (metres from the head to the controller).
import importlib
import os

import freecad.BlocksCAD.core.mathutil as _mu
import freecad.BlocksCAD.ui.layout as _lay
import freecad.BlocksCAD.ui.ring as _ring
import freecad.BlocksCAD.ui.ring_view as _rv
import freecad.BlocksCAD.ui.defaults as _df
import freecad.BlocksCAD.ui.readout as _ro
import freecad.BlocksCAD.ui.controller as _ctl
import freecad.BlocksCAD.backends.sim as _sim
import freecad.BlocksCAD.render.offscreen as _off
for _m in (_mu, _lay, _ring, _rv, _df, _ro, _ctl, _sim):
    importlib.reload(_m)

_out = globals().get("RENDER_DIR", os.path.join(os.environ.get("TEMP", "."), "blockscad_renders"))
os.makedirs(_out, exist_ok=True)
_dist = globals().get("UI_DISTANCE", 0.55)
_log = []
_s = _sim.SimSession(None, actions={"tool:cube_builder": lambda: _log.append("cube")})
try:
    _head = (0.0, 1.6, 0.0)
    _ctrl = (-0.12, 1.25, -_dist * 0.8)
    _s.input.set_head(position=_head, look_at_point=_ctrl)
    _s.input.set_hand(0, position=_ctrl, point_at=(0.0, 1.3, -1.0))
    _s.input.set_hand(1, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
    for _ in range(20):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_ring.png"))
    # hover the third face of the front page, then flick the ring
    _centre, _u, _v, _n = _s.ui.ring.page_frame(0, _ctrl, _head)
    _target = _mu.add(_centre, _mu.mul(_u, 0.0))
    _col, _row = 2, 0
    _x = (_col - 1.5) * (_ring.CELL + _ring.GAP)
    _y = (1 - _row) * (_ring.CELL + _ring.GAP)
    _target = _mu.add(_centre, _mu.add(_mu.mul(_u, _x), _mu.mul(_v, _y)))
    _s.input.set_hand(1, position=_mu.add(_target, _mu.mul(_n, 0.3)), point_at=_target)
    _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_hover.png"))
    print("hover:", _s.ui.ring.hover, "ray end", _s.ui_update.ray_end is not None)
    # navigation readout: both grips, spread the hands
    _s.input.set_hand(0, position=(-0.2, 1.0, -0.5), grip=1.0)
    _s.input.set_hand(1, position=(0.2, 1.0, -0.5), grip=1.0)
    _s.frame(0.02)
    _s.input.set_hand(0, position=(-0.35, 1.0, -0.5))
    _s.input.set_hand(1, position=(0.35, 1.0, -0.5))
    _s.frame(0.02)
    _s.input.set_head(position=_head, look_at_point=(0.0, 1.0, -0.5))
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_navigate.png"))
    print("scale:", _s.navigator.world.scale)
finally:
    _s.close()
print("renders in", _out)
