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
import freecad.BlocksCAD.ui.radial as _rd
import freecad.BlocksCAD.ui.radial_view as _rdv
import freecad.BlocksCAD.ui.toast as _ts
import freecad.BlocksCAD.ui.undo_button as _ub
import freecad.BlocksCAD.ui.options as _op
import freecad.BlocksCAD.ui.feedback_view as _fv
import freecad.BlocksCAD.core.stage as _sg
import freecad.BlocksCAD.core.snapping as _sn
import freecad.BlocksCAD.cad.primitives as _pm
import freecad.BlocksCAD.render.ghost as _gh
import freecad.BlocksCAD.tools.primitives as _tp
import freecad.BlocksCAD.core.grab as _gb
import freecad.BlocksCAD.cad.edit as _ed
import freecad.BlocksCAD.cad.picking as _pk
import freecad.BlocksCAD.cad.meshes as _ms
import freecad.BlocksCAD.render.highlight as _hl
import freecad.BlocksCAD.tools.grab as _tg
import freecad.BlocksCAD.render.model_anchor as _ma
import freecad.BlocksCAD.ui.ruler as _ru
import freecad.BlocksCAD.ui.settings as _cf
import freecad.BlocksCAD.ui.pointing as _pg
import freecad.BlocksCAD.ui.pointer as _pt
import freecad.BlocksCAD.ui.defaults as _df
import freecad.BlocksCAD.tools.base as _tb
import freecad.BlocksCAD.tools.registry as _tr
import freecad.BlocksCAD.tools as _tools
import freecad.BlocksCAD.tools.legacy as _tl
import freecad.BlocksCAD.ui.controller as _ctl
import freecad.BlocksCAD.backends.sim as _sim
import freecad.BlocksCAD.render.offscreen as _off
for _m in (_mu, _un, _nav, _st, _lay, _ring, _rv, _rd, _rdv, _ts, _ub, _op, _fv, _sg, _sn, _gb, _ed, _pk, _ms, _pm, _gh, _hl, _ma, _tb, _tr, _tools, _tp, _tg, _tl, _ru, _cf, _pg, _pt, _df, _ctl, _sim):
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
    _y = (1 - 0) * (_ring.CELL + _ring.GAP) + _ring.GRID_Y
    _target = _mu.add(_pose.centre, _mu.add(_mu.mul(_pose.u, _x), _mu.mul(_pose.v, _y)))
    _s.input.set_hand(1, position=_mu.add(_target, _mu.mul(_pose.n, 0.3)), point_at=_target)
    _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_hover.png"))
    print("hover:", _s.ui.ring.hover, "ray end", _s.ui_update.ray_end is not None)

    # quick radial: hold button1 of the tool hand, move the hand up and to the right
    _hand = (0.25, 1.3, -0.25)
    _s.input.set_head(position=_head, look_at_point=(0.05, 1.3, -0.35))
    _s.input.set_hand(1, position=_hand, point_at=(0.0, 1.3, -1.0))
    _s.frame(0.02)
    _s.input.set_hand(1, button1=True)
    _s.frame(0.02)
    _s.input.set_hand(1, position=(_hand[0] + 0.05, _hand[1] + 0.045, _hand[2]))
    _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_radial.png"))
    print("radial items:", _s.ui.radial_items(), "chosen:", _s.ui.radial._selected)
    _s.input.set_hand(1, button1=False)
    _s.frame(0.02)
    print("radial activated:", _s.ui_update.activated, "favourites now:", _s.ui.radial_items())
    _s.input.set_head(position=_head, look_at_point=_ctrl)

    # lifting a single face: hold the trigger on it, carry it to a free slot, then over the empty side that hides it
    _s.ui.settings.tip_angle = 0.0
    _tools_page = [page.name for page in _s.ui.layout.pages].index("Tools")

    def _aim_slot(slot, trigger):
        _pose = _s.ui.ring.poses[_tools_page]
        _x = (slot % _lay.COLS - (_lay.COLS - 1) / 2) * (_ring.CELL + _ring.GAP)
        _y = ((_lay.ROWS - 1) / 2 - slot // _lay.COLS) * (_ring.CELL + _ring.GAP) + _ring.GRID_Y
        _target = _mu.add(_pose.centre, _mu.add(_mu.mul(_pose.u, _x), _mu.mul(_pose.v, _y)))
        _s.input.set_hand(1, position=_mu.add(_target, _mu.mul(_pose.n, 0.3)), point_at=_target, trigger=trigger)
        _s.frame(0.02)

    for _ in range(20):
        _s.frame(0.02)
    _aim_slot(1, 1.0)
    for _ in range(30):
        _s.frame(0.02)
    _aim_slot(10, 1.0)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_face_lift.png"))
    print("lifted face:", _s.ui.ring.lifted_face, "target:", _s.ui.ring._face_target)
    _aim_slot(10, 0.0)
    print("moved to slot 10:", _s.ui.layout.pages[_tools_page].slots)
    _aim_slot(10, 1.0)
    for _ in range(30):
        _s.frame(0.02)
    _s.input.set_hand(0, stick=(-1.0, 0.0))     # turn the carousel to the empty side at the end
    _s.frame(0.02)
    _s.input.set_hand(0, stick=(0.0, 0.0))
    for _ in range(40):
        _s.frame(0.02)
    _ghost = _s.ui.ring.ghosts[max(_s.ui.ring.ghosts)]
    _s.input.set_hand(1, position=_mu.add(_ghost.centre, _mu.mul(_ghost.n, 0.3)), point_at=_ghost.centre, trigger=1.0)
    _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_face_hide.png"))
    _s.input.set_hand(1, trigger=0.0)
    _s.frame(0.02)
    print("hidden:", _s.ui.layout.hidden)
    _s.ui.show_hidden()
    print("shown again:", _s.ui.layout.hidden, _s.ui.layout.pages[_tools_page].slots)
    _s.ui.settings.tip_angle = 15.0
    _s.input.set_hand(1, trigger=0.0, button1=False, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
    for _ in range(40):
        _s.frame(0.02)

    # toasts in front of the head, the tooltip of a hovered face and the readout of a tool option
    _s.ui.settings.tip_angle = 0.0
    _s.ui.ring.focus_side(_s.ui.layout.pages[_tools_page].side)
    _s.ui.toast("Undo")
    _s.ui.toast("Cube: Click and drag to build a cube")
    _s.ui.toast("Hidden: Line")
    for _ in range(10):
        _s.frame(0.02)
    _aim_slot(2, 0.0)
    for _ in range(40):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_feedback.png"))
    print("tooltip:", _s.ui.feedback._tooltip.label, "| toasts:", [t.text for t in _s.ui.toasts.items])

    class _Sized(_tb.Tool):
        name, label = "sized", "Sized"
        options = (_tb.ToolOption("size", "Grid", "length", 1.0, 100.0, 1.0, 10.0),)

    _tr.register(_Sized)
    _s.select_tool("sized")
    _s.input.set_hand(1, stick=(0.0, 1.0))
    for _ in range(12):
        _s.frame(0.02)
    _s.input.set_hand(1, stick=(0.0, 0.0), position=(0.2, 1.25, -0.5), point_at=(0.0, 1.25, -1.5))
    for _ in range(3):
        _s.frame(0.02)
    _s.input.set_head(position=_head, look_at_point=(0.1, 1.25, -0.5))
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_readout.png"))
    print("readout:", _s.ui.feedback._readout.label)
    _s.tool_manager.active_name = None
    _tr.unregister("sized")
    _s.ui.settings.tip_angle = 15.0
    _s.input.set_head(position=_head, look_at_point=_ctrl)
    _s.input.set_hand(1, stick=(0.0, 0.0), position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
    for _ in range(40):
        _s.frame(0.02)

    # the primitive tool: a cross marks the grid point under the tip, a drag spans a box and a ghost shows the chosen shape
    _s.ui.settings.pointer_mode = "tip"
    _s.ui.settings.tip_angle = 0.0
    _s.select_tool("primitive")
    _tool = _s.tool_manager.active
    _tool.ctx.services["document"] = lambda: None        # the render must not make anything in the open document
    _tool.values["grid"] = "20 mm"
    _to_stage = lambda p: _sg.to_stage(_s.navigator.world, p)
    _centre = _to_stage((260.0, 0.0, 40.0))          # beside the 300 mm test cube
    _s.input.set_head(position=_mu.add(_centre, (0.1, 0.25, 0.4)), look_at_point=_centre)
    _s.input.set_hand(1, position=_to_stage((200.0, -60.0, 0.0)), point_at=_to_stage((200.0, -60.0, -1000.0)))
    _s.frame(0.02)
    _shift = tuple(c - p for c, p in zip(_s.ui.cursor(_s.last_frame.hands[1]), _s.last_frame.hands[1].aim.position))

    def _cursor(point, **inputs):
        _s.input.set_hand(1, position=tuple(t - c for t, c in zip(_to_stage(point), _shift)), **inputs)
        _s.frame(0.02)

    _cursor((220.0, -40.0, 0.0))
    for _ in range(3):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_primitive_marker.png"))
    _s.input.set_hand(1, position=_to_stage((200.0, -60.0, 0.0)), stick=(0.87, 0.5))     # the stick towards the upper right
    for _ in range(6):
        _s.frame(0.02)
    _s.input.set_head(position=_mu.add(_centre, (0.1, 0.25, 0.4)), look_at_point=_to_stage((230.0, 0.0, 120.0)))
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_options_create.png"))
    print("create disc:", _s.tool_manager.active.values["shape"], _s.tool_manager.active.values["grid"])
    _s.input.set_hand(1, stick=(0.0, 0.0))
    _s.input.set_head(position=_mu.add(_centre, (0.1, 0.25, 0.4)), look_at_point=_centre)
    for _ in range(3):
        _s.frame(0.02)
    for _shape in ("Cylinder", "Prism", "Torus", "Sphere", "Wedge"):
        _tool.values["shape"] = _shape
        _cursor((200.0, -60.0, 0.0), trigger=1.0)
        _cursor((320.0, 60.0, 80.0), trigger=1.0)
        for _ in range(3):
            _s.frame(0.02)
        _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_primitive_" + _shape.lower() + ".png"))
        print(_shape, "readout:", _s.ui.gesture_text)
        _cursor((320.0, 60.0, 80.0), trigger=0.0)
    _s.tool_manager.active_name = None
    _s.ui.settings.pointer_mode = "laser"
    _s.ui.settings.tip_angle = 15.0
    _s.input.set_head(position=_head, look_at_point=_ctrl)
    _s.input.set_hand(1, trigger=0.0, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
    for _ in range(40):
        _s.frame(0.02)

    # the Grab tool: what the tip touches is highlighted (face, edge, vertex), a tap selects it; shown on objects of a temporary document
    import FreeCAD as _App
    _previous = _App.ActiveDocument.Name if _App.ActiveDocument is not None else None
    _temp = _App.newDocument("BlocksCADRender")
    _nodes = []
    try:
        _pm.create(_temp, "Box", (200.0, -60.0, 0.0), (120.0, 120.0, 80.0))
        _pm.create(_temp, "Cylinder", (340.0, -60.0, 0.0), (120.0, 120.0, 80.0))
        _s.tool_manager.ctx.services["document"] = _s._document      # the primitive block above had cleared it
        _s.ui.settings.pointer_mode = "tip"
        _s.ui.settings.tip_angle = 0.0
        import FreeCADGui as _Gui

        def _node_of(obj):
            try:
                return _Gui.getDocument(_temp.Name).getObject(obj.Name).RootNode
            except Exception:                                  # no GUI document (a headless run): draw the tessellated solid
                points, triangles = obj.Shape.tessellate(0.5)
                node = _coin.SoSeparator()
                material = _coin.SoMaterial()
                material.diffuseColor.setValue(0.8, 0.8, 0.84)
                node.addChild(material)
                coords = _coin.SoCoordinate3()
                coords.point.setValues(0, len(points), [(p.x, p.y, p.z) for p in points])
                node.addChild(coords)
                faces = _coin.SoIndexedFaceSet()
                indices = [i for t in triangles for i in (t[0], t[1], t[2], -1)]
                faces.coordIndex.setValues(0, len(indices), indices)
                node.addChild(faces)
                return node

        _nodes = [_node_of(o) for o in _temp.Objects]
        for _node in _nodes:
            _s.doc_scene.insertChild(_node, 2)             # before the previews and highlights, as in the headset host
        _s.input.set_hand(1, position=_to_stage((260.0, 0.0, 72.0)), point_at=_to_stage((260.0, 0.0, -1000.0)))
        _s.frame(0.02)
        _shift = tuple(c - p for c, p in zip(_s.ui.cursor(_s.last_frame.hands[1]), _s.last_frame.hands[1].aim.position))
        _s.select_tool("grab")
        _s.input.set_head(position=_mu.add(_to_stage((330.0, 0.0, 40.0)), (0.1, 0.3, 0.5)), look_at_point=_to_stage((330.0, 0.0, 40.0)))
        _shot = lambda name: _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_grab_" + name + ".png"))
        for _name, _point in (("face", (260.0, 0.0, 72.0)), ("edge", (260.0, -57.0, 77.0)), ("vertex", (203.0, -57.0, 77.0))):
            _cursor(_point)
            for _ in range(8):                               # long enough for the hover to move to the new element
                _s.frame(0.02)
            _shot(_name)
            _got = _sg.to_document(_s.navigator.world, _s.ui.cursor(_s.last_frame.hands[1]))
            print("grab hover:", _name, "target", _point, "cursor", tuple(round(v, 1) for v in _got), "->", _s.tool_manager.active._hover)
        _cursor((260.0, 0.0, 72.0), trigger=1.0)
        _cursor((260.0, 0.0, 72.0), trigger=0.0)            # a tap selects the face
        _cursor((400.0, -60.0 + 3.0, 77.0))                    # the cylinder edge under the tip
        for _ in range(3):
            _s.frame(0.02)
        _shot("selected")
        _cursor((260.0, 0.0, 72.0))                          # the selected face is touched again: hover lies in front of the selection
        for _ in range(12):
            _s.frame(0.02)
        _shot("selected_hover")
        _cursor((400.0, 0.0, 40.0))                          # inside the cylinder: the whole object is filled
        for _ in range(12):
            _s.frame(0.02)
        _shot("object")
        print("grab object hover:", _s.tool_manager.active._hover)
        _s.input.set_hand(1, stick=(-0.5, 0.8))              # the stick towards the upper left: the option disc of the Grab tool
        for _ in range(4):
            _s.frame(0.02)
        _shot("disc")
        _s.input.set_hand(1, stick=(0.0, 0.0))
        _cursor((260.0, 0.0, 72.0))
        for _ in range(12):
            _s.frame(0.02)
        _cursor((260.0, 0.0, 72.0), trigger=1.0)
        _cursor((283.3, 17.7, 90.0), trigger=1.0)            # a free drag: not on the grid, the open padlock over the A button
        for _ in range(3):
            _s.frame(0.02)
        _shot("free")
        print("grab free readout:", _s.ui.gesture_text)
        _cursor((283.3, 17.7, 90.0), trigger=1.0, button1=True)      # A held: locked to the grid, the closed padlock
        for _ in range(3):
            _s.frame(0.02)
        _shot("locked")
        print("grab locked readout:", _s.ui.gesture_text)
        _cursor((283.3, 17.7, 90.0), trigger=0.0, button1=False)
        # the value panels: they follow the selection, so selecting the box adds a side with the panels Values, Number pad and Keys to the carousel
        from freecad.BlocksCAD.cad import picking as _pk
        _pk.set_selection(_temp, [(_temp.Objects[0].Name, "")])
        _cursor((600.0, 0.0, 400.0))
        for _ in range(3):
            _s.frame(0.02)
        _s.ui.module.editor.select(0)
        for _key in ("2", "*", "6", "unit"):
            _s.ui.module.editor.key(_key)
        _s.input.set_head(position=_head, look_at_point=_ctrl)
        for _ in range(20):
            _s.frame(0.02)
        _pages = _s.ui.shown_layout().pages
        _page = next(i for i, p in enumerate(_pages) if "key.5" in p.slots)
        _centre, _, _ = _s.ui.ring.slot_centre(_page, _pages[_page].slots.index("key.5"))
        _at = _mu.add(_centre, _mu.mul(_s.ui.ring.poses[_page].n, 0.01))
        _s.input.set_hand(1, position=(_at[0], _at[1], _at[2] + _s.ui.settings.tip_length), orientation=(0.0, 0.0, 0.0, 1.0))
        for _ in range(3):
            _s.frame(0.02)
        _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_values.png"))
        print("value panels:", _s.ui.module.editor.target.title, [(f.label, f.value) for f in _s.ui.module.editor.fields][:3], _s.ui.module.editor.entry,
              _s.ui.ring.hover)
        _pk.clear_selection()
        for _ in range(3):
            _s.frame(0.02)
    finally:
        for _node in _nodes:
            _s.doc_scene.removeChild(_node)
        _App.closeDocument(_temp.Name)
        if _previous is not None and _previous in _App.listDocuments():
            _App.setActiveDocument(_previous)
        _s.tool_manager.active_name = None
        _s.ui.settings.pointer_mode = "laser"
        _s.ui.settings.tip_angle = 15.0
        _s.input.set_head(position=_head, look_at_point=_ctrl)
        _s.input.set_hand(1, trigger=0.0, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
        for _ in range(40):
            _s.frame(0.02)

    # the carousel turns with the controller: roll the wrist a quarter turn
    _o = _s.input.hands[0].aim.orientation
    _s.input.set_hand(0, orientation=_mu.quat_multiply(_o, _mu.quat_from_axis_angle((0, 0, -1), 0.6)))
    for _ in range(5):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_rolled.png"))
    _s.input.set_hand(0, orientation=_o)

    # tip mode: the tip of the tool hand touches the third face, the Session panel shows the pointer faces
    _s.ui.settings.pointer_mode = "tip"
    for _ in range(8):
        _s.frame(0.02)
    _pose = _s.ui.ring.poses[0]
    _x = (2 - 1.5) * (_ring.CELL + _ring.GAP)
    _y = (1 - 0) * (_ring.CELL + _ring.GAP) + _ring.GRID_Y
    _target = _mu.add(_pose.centre, _mu.add(_mu.mul(_pose.u, _x), _mu.mul(_pose.v, _y)))
    _touch = _mu.add(_target, _mu.mul(_pose.n, 0.015))
    _s.input.set_hand(1, position=_mu.add(_touch, _mu.mul(_pose.n, _s.ui.settings.tip_length)), point_at=_touch)
    for _ in range(3):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_tip.png"))
    print("tip hover:", _s.ui.ring.hover)
    # the same tip pushed through the plate and held well behind it: the parts behind are drawn in the inverted colours
    for _name, _gap in (("through", -0.012), ("behind", -0.06)):
        _touch = _mu.add(_target, _mu.mul(_pose.n, _gap))
        _s.input.set_hand(1, position=_mu.add(_touch, _mu.mul(_pose.n, _s.ui.settings.tip_length)), point_at=_touch)
        for _ in range(3):
            _s.frame(0.02)
        _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_tip_" + _name + ".png"))
    for _ in range(3):
        _s.input.set_hand(0, stick=(1.0, 0.0))
        _s.frame(0.02)
        _s.input.set_hand(0, stick=(0.0, 0.0))
        for _ in range(40):
            _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_session.png"))
    for _ in range(3):
        _s.input.set_hand(0, stick=(-1.0, 0.0))
        _s.frame(0.02)
        _s.input.set_hand(0, stick=(0.0, 0.0))
        for _ in range(40):
            _s.frame(0.02)
    _s.ui.settings.pointer_mode = "laser"

    # Edit next to Tools, View as a row above them
    _names = lambda: [page.name for page in _s.ui.layout.pages]
    _s.ui.layout.move_page(_names().index("Edit"), 0)
    _s.ui.layout.move_page(_names().index("View"), 0, 1, None, True)
    _s.input.set_hand(1, position=(0.25, 1.3, -0.25), point_at=(0.0, 1.3, -1.0))
    for _ in range(30):
        _s.frame(0.02)
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_stacked.png"))
    print("sides:", _s.ui.layout.sides(), _names())

    # lift the Session panel by its title bar and hold it above the Tools panel (a new row)
    _page = _names().index("Session")
    _s.input.set_hand(0, stick=(1.0, 0.0))
    _s.frame(0.02)
    _s.input.set_hand(0, stick=(0.0, 0.0))
    for _ in range(40):
        _s.frame(0.02)
    _pose = _s.ui.ring.poses[_page]
    _title = _mu.add(_pose.centre, _mu.mul(_pose.v, (_ring.TITLE_Y[0] + _ring.TITLE_Y[1]) / 2))
    _s.input.set_hand(1, position=_mu.add(_title, _mu.mul(_pose.n, 0.3)), point_at=_title, trigger=1.0)
    for _ in range(3):
        _s.frame(0.02)
    _s.input.set_hand(0, stick=(-1.0, 0.0))     # turn the carousel back to the Tools side while holding the panel
    _s.frame(0.02)
    _s.input.set_hand(0, stick=(0.0, 0.0))
    for _ in range(40):
        _s.frame(0.02)
    _tools = _s.ui.ring.poses[_names().index("Tools")]
    _above = _mu.add(_tools.centre, _mu.mul(_tools.v, 0.8 * _ring.PANEL_H / 2))
    _s.input.set_hand(1, position=_mu.add(_above, _mu.mul(_tools.n, 0.3)), point_at=_above, trigger=1.0)
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
    # one grip: the scale and the modes float above the gripping hand, the world turns with the hand
    _s.input.set_hand(0, grip=0.0)
    _s.input.set_hand(1, position=(0.1, 1.0, -0.9), button2=True)
    for _ in range(20):
        _s.frame(0.02)
    _s.input.set_hand(1, position=(0.1, 1.0, -0.9), orientation=_mu.quat_from_axis_angle((0, 0, 1), 0.5))
    for _ in range(3):
        _s.frame(0.02)
    _s.input.set_head(position=(0.0, 1.3, -0.4), look_at_point=(0.1, 1.1, -0.9))
    _off.save(_s.render("head", (1100, 800), fov=1.0), os.path.join(_out, "ui_single.png"))
finally:
    _s.close()
print("renders in", _out, _log)
