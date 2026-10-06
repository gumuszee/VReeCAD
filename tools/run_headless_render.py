# Run a FreeCAD-side snippet that renders images (tools/snippets/render_ui.py by default) in a separate headless process.
# Dev tooling: nothing in a running FreeCAD or in the XR viewer is touched or reloaded, so it is safe while the headset is in use.
# The snippet sees the same globals as under fc_rpc.py (RENDER_DIR, UI_DISTANCE, UNIT_SYSTEM); objects without a view provider are
# drawn from their tessellated shape. Usage:  & "$env:LOCALAPPDATA\Programs\FreeCAD 1.1\bin\python.exe" tools\run_headless_render.py [snippet.py] [out-dir]
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "FreeCAD 1.1", "bin")
for path in (BIN, ROOT, os.path.dirname(os.path.abspath(__file__))):
    if path not in sys.path:
        sys.path.insert(0, path)

import FreeCAD  # noqa: E402,F401
import headless_gui  # noqa: E402

headless_gui.install()

snippet = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "tools", "snippets", "render_ui.py")
names = {"__name__": "__main__"}
if len(sys.argv) > 2:
    names["RENDER_DIR"] = sys.argv[2]
with open(snippet, encoding="utf-8") as f:
    exec(compile(f.read(), snippet, "exec"), names)
