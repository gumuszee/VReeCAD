# Dump the text of FreeCAD's Report view (console output: prints, warnings, errors) - run via
#   python tools/fc_rpc.py exec -f tools/snippets/report_view.py
# Optional: set N before to limit lines (default last 60). Report view is the only place addon print()s land.
import FreeCADGui
from PySide import QtWidgets
_n = globals().get("N", 60)
_mw = FreeCADGui.getMainWindow()
for _w in _mw.findChildren(QtWidgets.QTextEdit):
    if _w.objectName() in ("Report view", "ReportView") or "Report" in _w.objectName():
        _lines = _w.toPlainText().splitlines()
        print("\n".join(_lines[-_n:]))
        break
else:
    print("Report view not found (View > Panels > Report view must exist)")
