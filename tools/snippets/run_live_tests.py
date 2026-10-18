# Run the unit tests that need the live FreeCAD GUI (Coin3D, offscreen OpenGL): tests/live/test_coin.py.
# The pure unit tests run outside FreeCAD:  "%LOCALAPPDATA%\Programs\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests
# Run:  python tools/fc_rpc.py exec -f tools/snippets/run_live_tests.py
# Set LIVE_TESTS_DIR before exec to point at another checkout; the default is the addon repo of the installed addon.
# The run reloads addon modules: stop the XR viewer first, otherwise a running viewer reports transient errors in the Report view until it is restarted (xr_restart.py).
import importlib
import os
import sys
import unittest

import freecad.VReeCAD as _pkg

_repo = globals().get("LIVE_TESTS_DIR") or os.path.abspath(os.path.join(os.path.dirname(_pkg.__file__), "..", ".."))
_tests = os.path.join(_repo, "tests")
for _p in (os.path.join(_tests, "live"), _tests):
    if _p not in sys.path:
        sys.path.insert(0, _p)
for _name in ("support", "test_gltf", "test_coin"):
    sys.modules.pop(_name, None)
for _name in ("freecad.VReeCAD.core.mathutil", "freecad.VReeCAD.core.units", "freecad.VReeCAD.core.navigation", "freecad.VReeCAD.input", "freecad.VReeCAD.gltf", "freecad.VReeCAD.render.gltf_coin",
              "freecad.VReeCAD.render.controller_shape", "freecad.VReeCAD.render.offscreen",
              "freecad.VReeCAD.ui.layout", "freecad.VReeCAD.ui.style", "freecad.VReeCAD.ui.ring", "freecad.VReeCAD.ui.ring_view", "freecad.VReeCAD.ui.radial", "freecad.VReeCAD.ui.radial_view",
              "freecad.VReeCAD.ui.ruler", "freecad.VReeCAD.ui.settings", "freecad.VReeCAD.ui.pointing", "freecad.VReeCAD.ui.pointer", "freecad.VReeCAD.ui.defaults", "freecad.VReeCAD.ui.toast", "freecad.VReeCAD.ui.undo_button", "freecad.VReeCAD.ui.options",
              "freecad.VReeCAD.ui.feedback_view", "freecad.VReeCAD.tools.base", "freecad.VReeCAD.tools.registry", "freecad.VReeCAD.tools",
              "freecad.VReeCAD.core.stage", "freecad.VReeCAD.core.snapping", "freecad.VReeCAD.cad", "freecad.VReeCAD.cad.primitives",
              "freecad.VReeCAD.core.grab", "freecad.VReeCAD.core.selecting", "freecad.VReeCAD.cad.edit", "freecad.VReeCAD.cad.picking", "freecad.VReeCAD.cad.meshes",
              "freecad.VReeCAD.render.ghost", "freecad.VReeCAD.render.highlight", "freecad.VReeCAD.tools.primitives", "freecad.VReeCAD.tools.touch", "freecad.VReeCAD.tools.select", "freecad.VReeCAD.tools.move", "freecad.VReeCAD.ui.controller",
              "freecad.VReeCAD.backends.sim"):
    if _name in sys.modules:
        importlib.reload(sys.modules[_name])
_suite = unittest.defaultTestLoader.loadTestsFromName("test_coin")
_result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(_suite)
print("LIVE TESTS:", "OK" if _result.wasSuccessful() else "FAILED", f"({_result.testsRun} run, "
      f"{len(_result.failures)} failures, {len(_result.errors)} errors, {len(_result.skipped)} skipped)")
