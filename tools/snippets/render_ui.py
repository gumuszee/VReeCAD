# Render the user interface (palette carousel on the controller, panel rearranging, scale ruler) from a simulated head, without a headset.
# The Sim session runs the same UiController as the headset path: a scripted head looks at the left controller, the right
# controller points at a face, the trigger activates it; with both grips the ruler is drawn over a test cube.
# Run:  python tools/fc_rpc.py exec -f tools/snippets/render_ui.py
# Output: <RENDER_DIR>/ui_*.png (default %TEMP%\blockscad_renders). Globals: UI_DISTANCE (metres from the head to the controller),
# UNIT_SYSTEM (name of a FreeCAD document unit system for the ruler, default "Standard (mm, kg, s, degree)").
import importlib
import os

import freecad.BlocksCAD.core.mathutil as _mu
import freecad.BlocksCAD.core.units as _un
import freecad.BlocksCAD.core.navigation as _nav
import freecad.BlocksCAD.ui.style as _st
import freecad.BlocksCAD.ui.layout as _lay
import freecad.BlocksCAD.ui.ring as _ring
import freecad.BlocksCAD.ui.ring_view as _rv
import freecad.BlocksCAD.ui.ruler as _ru
import freecad.BlocksCAD.ui.defaults as _df
import freecad.BlocksCAD.ui.controller as _ctl
import freecad.BlocksCAD.backends.sim as _sim
import freecad.BlocksCAD.render.offscreen as _off
for _m in (_mu, _un, _nav, _st, _lay, _ring, _rv, _ru, _df, _ctl, _sim):
    importlib.reload(_m)
from pivy import coin as _coin

_out = globals().get("RENDER_DIR", os.path.join(os.environ.get("TEMP", "."), "blockscad_renders"))
os.makedirs(_out, exist_ok=True)
_dist = globals().get("UI_DISTANCE", 0.55)
_system = globals().get("UNIT_SYSTEM", "Standard (mm, kg, s, degree)")


def _test_scene():
    """A 300 mm cube and a 100 mm cube on top of it (millimetres, Z up)."""
    root = _coin.SoSeparator()
    light = _coin.SoLightModel()
    root.addChild(light)
    colour = _coin.SoBaseColor()
    colour.rgb = _coin.SbColor(0.85, 0.85, 0.9)
    root.addChild(colour)
    big = _coin.SoCube()
    big.width, big.height, big.depth = 300, 300, 300
    root.addChild(big)
    return root


_log = []
_s = _sim.SimSession(_test_scene(), actions={"tool:cube_builder": lambda: _log.append("cube"), "doc:undo": lambda: _log.append("undo"),
                                              "doc:redo": lambda: _log.append("redo")})
_s.ui.set_unit_system(_system)
try:
    _head = (0.0, 1.6, 0.0)
    _ctrl = (-0.12, 1.25, -_dist * 0.8)
    _s.input.set_head(position=_head, look_at_point=_ctrl)
    _s.input.set_hand(0, position=_ctrl, point_at=(0.0, 1.3, -1.0))
    _s.input.set_hand(1, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
    for _ in range(20):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_ring.png"))

    # hover the third face of the front panel
    _pose = _s.ui.ring.poses[0]
    _x = (2 - 1.5) * (_ring.CELL + _ring.GAP)
    _y = (1 - 0) * (_ring.CELL + _ring.GAP)
    _target = _mu.add(_pose.centre, _mu.add(_mu.mul(_pose.u, _x), _mu.mul(_pose.v, _y)))
    _s.input.set_hand(1, position=_mu.add(_target, _mu.mul(_pose.n, 0.3)), point_at=_target)
    _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_hover.png"))
    print("hover:", _s.ui.ring.hover, "ray end", _s.ui_update.ray_end is not None)

    # the carousel turns with the controller: roll the wrist a quarter turn
    _o = _s.input.hands[0].aim.orientation
    _s.input.set_hand(0, orientation=_mu.quat_multiply(_o, _mu.quat_from_axis_angle((0, 0, -1), 0.6)))
    for _ in range(5):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_rolled.png"))
    _s.input.set_hand(0, orientation=_o)

    # stack all panels on one side
    for _name in ("Edit", "View", "Session"):
        _s.ui.layout.move_page([page.name for page in _s.ui.layout.pages].index(_name), 0)
    _s.input.set_hand(1, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
    for _ in range(30):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_stacked.png"))
    print("sides:", _s.ui.layout.sides())

    # lift the Edit panel by its title bar and hold it over the empty slot
    _pose = _s.ui.ring.poses[1]
    _title = _mu.add(_pose.centre, _mu.mul(_pose.v, (_ring.TITLE_Y[0] + _ring.TITLE_Y[1]) / 2))
    _s.input.set_hand(1, position=_mu.add(_title, _mu.mul(_pose.n, 0.3)), point_at=_title, trigger=1.0)
    for _ in range(3):
        _s.frame(0.02)
    _ghost = _s.ui.ring.ghost
    _s.input.set_hand(1, position=_mu.add(_ghost.centre, _mu.mul(_ghost.n, 0.3)), point_at=_ghost.centre, trigger=1.0)
    _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_lift.png"))
    _s.input.set_hand(1, trigger=0.0)
    _s.frame(0.02)
    print("sides after drop:", _s.ui.layout.sides(), [p.name for p in _s.ui.layout.pages])

    # navigation ruler: both grips, hands spread behind the cube (the cube must not hide the ruler)
    _s.input.set_hand(0, position=(-0.2, 1.0, -1.4), grip=0.0)
    _s.input.set_hand(1, position=(0.2, 1.0, -1.4), grip=0.0, trigger=0.0)
    _s.navigator.request_reset()
    for _ in range(40):
        _s.frame(0.02)
    _s.input.set_hand(0, grip=1.0)
    _s.input.set_hand(1, grip=1.0)
    _s.frame(0.02)
    _s.input.set_hand(0, position=(-0.3, 1.0, -1.5))
    _s.input.set_hand(1, position=(0.3, 1.1, -1.5))
    for _ in range(3):
        _s.frame(0.02)
    _s.input.set_head(position=(0.0, 1.3, -0.4), look_at_point=(0.0, 1.1, -1.3))
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_ruler.png"))
    print("scale:", _s.navigator.world.scale, "level:", _s.navigator.level)
    _s.input.set_hand(0, position=(-0.45, 1.0, -1.5))
    _s.input.set_hand(1, position=(0.45, 1.1, -1.5), button1=True)
    for _ in range(3):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_ruler_level.png"))
    print("scale:", _s.navigator.world.scale, "level:", _s.navigator.level)
    # the line passes behind the cube: it is still drawn
    _s.input.set_hand(0, position=(-0.5, 1.0, -1.5))
    _s.input.set_hand(1, position=(0.2, 1.05, -1.5), button1=False)
    for _ in range(3):
        _s.frame(0.02)
    _s.input.set_head(position=(0.0, 1.3, -0.4), look_at_point=(-0.1, 1.1, -1.3))
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_ruler_behind.png"))
finally:
    _s.close()
print("renders in", _out, _log)
