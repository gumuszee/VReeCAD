# Run the live tests (tests/live/test_coin.py) in a separate headless FreeCAD process. Dev tooling.
# It never touches a running FreeCAD or the XR viewer: unlike tools/snippets/run_live_tests.py it reloads nothing in the GUI,
# so it is safe to run while the headset is in use. Tests that render an image offscreen are skipped unless --render is given
# (SoOffscreenRenderer makes its own OpenGL context, so they usually run too, but they are slower);
# FreeCAD's selection (FreeCADGui.Selection) is replaced by a small in-memory stand-in (tools/headless_gui.py) because the GUI is not running.
# Usage:  & "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\run_headless_tests.py [--render] [name-filter]
import inspect
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "FreeCAD 1.1", "bin")
for path in (BIN, ROOT, os.path.dirname(os.path.abspath(__file__)), os.path.join(ROOT, "tests"), os.path.join(ROOT, "tests", "live")):
    if path not in sys.path:
        sys.path.insert(0, path)

import FreeCAD  # noqa: E402,F401
import headless_gui  # noqa: E402

headless_gui.install()


def _renders(test):
    method = getattr(test, test._testMethodName)
    try:
        source = inspect.getsource(method)
    except (OSError, TypeError):
        return False
    return ".render(" in source or "render_stereo(" in source or "offscreen.render" in source or "inverted_cone_pixels" in source


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--render"]
    with_render = "--render" in sys.argv[1:]
    pattern = args[0] if args else ""
    loaded = unittest.defaultTestLoader.loadTestsFromName("test_coin")
    suite, skipped = unittest.TestSuite(), 0
    for test in _flatten(loaded):
        if (pattern and pattern not in test.id()) or (_renders(test) and not with_render):
            skipped += 1
            continue
        suite.addTest(test)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    print(f"HEADLESS TESTS: {'OK' if result.wasSuccessful() else 'FAILED'} ({result.testsRun} run, {len(result.failures)} failures, "
          f"{len(result.errors)} errors, {skipped} not run: they render (use --render) or do not match the filter)")
    sys.exit(0 if result.wasSuccessful() else 1)
