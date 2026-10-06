# Run the unit tests that need the live FreeCAD GUI (Coin3D, offscreen OpenGL): tests/live/test_coin.py.
# The pure unit tests run outside FreeCAD:  "%LOCALAPPDATA%\Programs\FreeCAD 1.1\bin\python.exe" -m unittest discover -s tests
# Run:  python tools/fc_rpc.py exec -f tools/snippets/run_live_tests.py
# Set LIVE_TESTS_DIR before exec to point at another checkout; the default is the addon repo of the installed addon.
import importlib
import os
import sys
import unittest

import freecad.BlocksCAD as _pkg

_repo = globals().get("LIVE_TESTS_DIR") or os.path.abspath(os.path.join(os.path.dirname(_pkg.__file__), "..", ".."))
_tests = os.path.join(_repo, "tests")
for _p in (os.path.join(_tests, "live"), _tests):
    if _p not in sys.path:
        sys.path.insert(0, _p)
for _name in ("support", "test_gltf", "test_coin"):
    sys.modules.pop(_name, None)
for _name in ("freecad.BlocksCAD.core.mathutil", "freecad.BlocksCAD.core.units", "freecad.BlocksCAD.core.navigation", "freecad.BlocksCAD.input", "freecad.BlocksCAD.gltf", "freecad.BlocksCAD.render.gltf_coin",
              "freecad.BlocksCAD.render.controller_shape", "freecad.BlocksCAD.render.offscreen",
              "freecad.BlocksCAD.ui.layout", "freecad.BlocksCAD.ui.style", "freecad.BlocksCAD.ui.ring", "freecad.BlocksCAD.ui.ring_view",
              "freecad.BlocksCAD.ui.ruler", "freecad.BlocksCAD.ui.defaults", "freecad.BlocksCAD.ui.controller",
              "freecad.BlocksCAD.backends.sim"):
    if _name in sys.modules:
        importlib.reload(sys.modules[_name])
_suite = unittest.defaultTestLoader.loadTestsFromName("test_coin")
_result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(_suite)
print("LIVE TESTS:", "OK" if _result.wasSuccessful() else "FAILED", f"({_result.testsRun} run, "
      f"{len(_result.failures)} failures, {len(_result.errors)} errors, {len(_result.skipped)} skipped)")
