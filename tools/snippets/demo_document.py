# Create a small demo document (a plate with a hole and a block) in the running FreeCAD and show it in a 3D view,
# so the XR viewer and the Sim render have something to display.
# Run:  python tools/fc_rpc.py exec -f tools/snippets/demo_document.py
import FreeCAD as App
import FreeCADGui as Gui

doc = App.ActiveDocument or App.newDocument("Demo")
if not doc.getObjectsByLabel("Plate"):
    plate = doc.addObject("Part::Box", "Plate")
    plate.Length, plate.Width, plate.Height = 200, 120, 10
    hole = doc.addObject("Part::Cylinder", "Hole")
    hole.Radius, hole.Height = 20, 30
    hole.Placement.Base = App.Vector(100, 60, -10)
    cut = doc.addObject("Part::Cut", "PlateWithHole")
    cut.Base, cut.Tool = plate, hole
    block = doc.addObject("Part::Box", "Block")
    block.Length, block.Width, block.Height = 40, 40, 60
    block.Placement.Base = App.Vector(20, 20, 10)
    doc.recompute()
Gui.activateWorkbench("VReeCADWorkbench")
Gui.ActiveDocument = Gui.getDocument(doc.Name)
Gui.ActiveDocument.ActiveView.viewIsometric()
Gui.SendMsgToActiveView("ViewFit")
print("document", doc.Name, [o.Name for o in doc.Objects])
