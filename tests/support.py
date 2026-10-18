# Test support: makes `freecad.VReeCAD.*` importable without FreeCAD (plain Python, e.g. FreeCAD's bundled python.exe).
# Inside FreeCAD the real package is used. Only modules without FreeCAD/Coin/OpenXR imports can be imported this way.
import os
import sys
import types

ADDON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "freecad", "VReeCAD")


def install():
    try:
        import freecad.VReeCAD  # noqa: F401  (real package inside FreeCAD)
        return
    except ImportError:
        pass
    for dotted, path in (("freecad", os.path.dirname(ADDON_DIR)), ("freecad.VReeCAD", ADDON_DIR)):
        module = types.ModuleType(dotted)
        module.__path__ = [path]
        sys.modules[dotted] = module


install()
