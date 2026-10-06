# Render the active document's 3D scene offscreen from an arbitrary eye pose to a PNG (no headset, no window).
# Proves the "virtual head" test path: any HMD/controller pose can be photographed without wearing a headset.
# Run:  python tools/fc_rpc.py exec -f tools/snippets/offscreen_render.py
# Configure by assigning before exec (shared RPC namespace), e.g. RENDER_EYE=(0,-300,150); RENDER_TARGET=(0,0,30); RENDER_OUT="C:/tmp/a.png"
import FreeCADGui
from pivy import coin

_eye = globals().get("RENDER_EYE", (150.0, -250.0, 180.0))        # mm, document coordinates
_target = globals().get("RENDER_TARGET", (0.0, 0.0, 0.0))
_out = globals().get("RENDER_OUT", "offscreen.png")
_size = globals().get("RENDER_SIZE", (1024, 768))

_view = FreeCADGui.ActiveDocument.ActiveView
_root = _view.getSceneGraph()

_cam = coin.SoPerspectiveCamera()
_cam.position.setValue(*_eye)
_cam.pointAt(coin.SbVec3f(*_target), coin.SbVec3f(0, 0, 1))
_cam.heightAngle = 0.9          # ~52 deg vertical field of view
_cam.nearDistance = 1.0
_cam.farDistance = 20000.0
_light = coin.SoDirectionalLight()
_light.direction.setValue(-0.4, 0.5, -1.0)

_scene = coin.SoSeparator()
_scene.ref()
_scene.addChild(_cam)
_scene.addChild(_light)
_scene.addChild(_root)

_vp = coin.SbViewportRegion(_size[0], _size[1])
_r = coin.SoOffscreenRenderer(_vp)
_r.setBackgroundColor(coin.SbColor(0.12, 0.12, 0.14))
_ok = _r.render(_scene)
if _ok:
    # Coin in FreeCAD has no image-writer plugin (writeToFile writes nothing): save the raw RGB buffer via Qt.
    from PySide import QtGui
    _w, _h = _size
    _img = QtGui.QImage(_r.getBuffer(), _w, _h, _w * 3, QtGui.QImage.Format_RGB888).mirrored(False, True)  # GL rows are bottom-up
    _ok = _img.save(_out)
print("rendered:", bool(_ok), "->", _out)
_scene.unref()
