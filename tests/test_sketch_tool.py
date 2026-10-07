import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.cad import picking, sketchinfer, sketching
from freecad.BlocksCAD.tools import base
from freecad.BlocksCAD.tools.sketch import SketchTool, plane_square


class FakeShape:
    def isNull(self):
        return False

    def hashCode(self):
        return 1


class FakeSketch:
    TypeId = sketching.TYPE

    def __init__(self, name, plane, face=None):
        self.Name, self.Label, self.Shape = name, name.upper(), FakeShape()
        self.plane, self.face = plane, face
        self.shapes = []                      # ("Line", p0, p1), ("Rectangle", c0, c2), ("Circle", centre, radius)
        self.points = {}                      # (geo, pos) -> (x, y)


class FakeDocument:
    def __init__(self):
        self.objects = {"solid": FakeSketch("solid", "XY")}
        self.objects["solid"].TypeId = "Part::Box"
        self.log = []

    def getObject(self, name):
        return self.objects.get(name)

    def openTransaction(self, text):
        self.log.append(("open", text))

    def commitTransaction(self):
        self.log.append(("commit",))

    def abortTransaction(self):
        self.log.append(("abort",))
        for name in [n for n, o in self.objects.items() if getattr(o, "fresh", False)]:
            del self.objects[name]

    def recompute(self):
        pass


class FakeSketching:
    """What `cad.sketching` offers the tool, for sketches that are planes at the origin (local = world on the XY plane)."""
    TYPE = sketching.TYPE
    PLANES = sketching.PLANES
    PLANE_ROTATION = sketching.PLANE_ROTATION
    current_sketch = staticmethod(sketching.current_sketch)
    parse_sub = staticmethod(sketching.parse_sub)
    outline = staticmethod(sketching.outline)

    def __init__(self, doc):
        self.doc = doc
        self.face_under_cursor = None

    def create_on_plane(self, doc, plane, point, grid):
        sketch = FakeSketch(f"sketch{len(doc.objects)}", plane)
        sketch.fresh = True
        doc.objects[sketch.Name] = sketch
        return sketch

    def create_on_face(self, doc, obj, sub):
        sketch = FakeSketch(f"sketch{len(doc.objects)}", "face", (obj.Name, sub))
        sketch.fresh = True
        doc.objects[sketch.Name] = sketch
        return sketch

    def pick_face(self, doc, point, mm):
        return self.face_under_cursor

    def to_local(self, sketch, point):
        return tuple(point)

    def to_world(self, sketch, point):
        return tuple(point)

    IDENTITY = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    placement = staticmethod(lambda sketch: FakeSketching.IDENTITY)
    plane_frame = staticmethod(lambda plane, point, grid: FakeSketching.IDENTITY)
    frame_to_local = staticmethod(lambda frame, point: tuple(point))
    frame_to_world = staticmethod(lambda frame, point: tuple(point))
    world_axes = staticmethod(lambda frame: (0, 1))

    def lines(self, sketch):
        return [(a, b) for kind, a, b, *_ in sketch.shapes if kind == "Line"]

    def slanted_lines(self, sketch):
        return [(a, b) for kind, a, b, *_ in sketch.shapes if kind == "Line" and sketchinfer.direction(a, b) is None]

    def own_points(self, sketch, apart_from=None):
        return [(at[0], at[1], 0.0) for key, at in sketch.points.items() if key != apart_from]

    def add_line(self, doc, sketch, p0, p1):
        sketch.shapes.append(("Line", p0, p1))
        sketch.points[(len(sketch.shapes) - 1, 1)], sketch.points[(len(sketch.shapes) - 1, 2)] = p0, p1
        return len(sketch.shapes) - 1, 1

    def add_rectangle(self, doc, sketch, c0, c2):
        sketch.shapes.append(("Rectangle", c0, c2))
        return len(sketch.shapes) - 1, 8

    def add_arc(self, doc, sketch, start, end, middle):
        if sketchinfer.arc_through(start, end, middle) is None:
            raise ValueError("the three points lie on a line")
        sketch.shapes.append(("Arc", start, end, middle))
        return len(sketch.shapes) - 1, 2

    def add_circle(self, doc, sketch, centre, radius):
        sketch.shapes.append(("Circle", centre, radius))
        return len(sketch.shapes) - 1, 0

    def pick(self, doc, point, mm, kind):
        best = None
        for sketch in doc.objects.values():
            for (geo, pos), at in getattr(sketch, "points", {}).items():
                d = ((point[0] - at[0]) ** 2 + (point[1] - at[1]) ** 2 + point[2] ** 2) ** 0.5
                if kind == "vertex" and d < 12 and (best is None or d < best.distance):
                    best = picking.Pick(sketch.Name, "vertex", f"Point{geo}.{pos}", d)
        return best

    def display(self, sketch, sub):
        return picking.Display()

    def handles(self, doc):
        return picking.Display(markers=[at for o in doc.objects.values() for at in getattr(o, "points", {}).values()])

    def signature(self, doc):
        return tuple((o.Name, tuple(getattr(o, "points", {}).items())) for o in doc.objects.values())

    def point_position(self, sketch, geo, pos):
        return sketch.points[(geo, pos)]

    def move_point(self, doc, sketch, geo, pos, target):
        if target[0] < -100:
            return "The sketch cannot take that move"
        sketch.points[(geo, pos)] = target
        return None

    def dimension(self, doc, sketch, geo):
        return "Dimension length = 10 mm", "length"


class FakeLayer:
    def show(self, displays, half):
        pass

    def hide(self):
        pass


class FakeHighlights(FakeLayer):
    def __init__(self):
        self.hover, self.selected = FakeLayer(), FakeLayer()


class FakeGhost:
    def __init__(self):
        self.shapes, self.markers, self.guide_calls = [], [], []

    def show_shape(self, mesh):
        self.shapes.append(mesh)

    def hide_shape(self):
        pass

    def show_marker(self, point, half):
        self.markers.append(point)

    def hide_marker(self):
        pass

    def show_guides(self, guides, half):
        self.guide_calls.append(list(guides))

    def hide_guides(self):
        self.guide_calls.append([])


class SketchToolTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.sim.set_head(position=(0.0, 1.6, 0.0), look_at_point=(0.0, 1.2, -1.0))
        self.sim.set_hand(1, position=(0.0, 1.2, -0.4), point_at=(0.0, 1.2, -2.0))
        self.doc = FakeDocument()
        self.sk = FakeSketching(self.doc)
        self.cursor = [0.0, 0.0, 0.0]
        self.selection, self.toasts, self.readouts = [], [], []
        self.ghost = FakeGhost()
        ctx = base.ToolContext(dominant=1)
        ctx.services.update({
            "cursor": lambda hand: tuple(self.cursor), "to_document": lambda p: p, "document": lambda: self.doc, "ghost": self.ghost,
            "toast": self.toasts.append, "readout": self.readouts.append, "highlight": FakeHighlights(), "sketching": self.sk,
            "mm_per_metre": lambda: 1000.0, "get_selection": lambda doc: list(self.selection),
            "set_selection": lambda doc, items: self.selection.__init__(items), "clear_selection": lambda: self.selection.clear()})
        self.tool = SketchTool(ctx)

    def frames(self, count=3):
        for _ in range(count):
            self.tool.update(self.sim.frame(0.1))

    def drag(self, start, end, release=True, **inputs):
        self.cursor = list(start)
        self.sim.set_hand(1, trigger=0.0, button1=False)
        self.frames()
        self.sim.set_hand(1, trigger=1.0, **inputs)
        self.tool.update(self.sim.frame(0.02))
        self.cursor = list(end)
        self.tool.update(self.sim.frame(0.02))
        if release:
            self.sim.set_hand(1, trigger=0.0, button1=False)
            self.tool.update(self.sim.frame(0.02))

    def sketches(self):
        return [o for o in self.doc.objects.values() if o.TypeId == sketching.TYPE]

    def test_a_rectangle_drag_makes_a_sketch_on_the_plane_and_draws_in_one_transaction(self):
        self.drag((12.0, 8.0, 0.0), (63.0, 41.0, 3.0))
        (sketch,) = self.sketches()
        self.assertEqual(sketch.plane, "XY")
        self.assertEqual(sketch.shapes, [("Rectangle", (10.0, 10.0), (60.0, 40.0))])
        self.assertEqual(self.doc.log, [("open", "Sketch"), ("commit",)])
        self.assertEqual(self.toasts[-1], "Rectangle drawn, 8 constraints")
        self.assertEqual(self.selection, [(sketch.Name, "")])

    def test_drawing_goes_on_in_the_selected_sketch_and_a_line_or_a_circle_is_drawn_the_same_way(self):
        self.drag((0.0, 0.0, 0.0), (60.0, 40.0, 0.0))
        self.tool.values["mode"] = "Line"
        self.drag((60.0, 40.0, 0.0), (90.0, 40.0, 0.0))
        self.tool.values["mode"] = "Circle"
        self.drag((30.0, 20.0, 0.0), (30.0, 30.0, 0.0))
        (sketch,) = self.sketches()
        self.assertEqual([s[0] for s in sketch.shapes], ["Rectangle", "Line", "Circle"])
        self.assertEqual(sketch.shapes[2], ("Circle", (30.0, 20.0), 10.0))
        self.assertEqual(self.doc.log[2], ("open", "Draw Line"))
        self.assertEqual(self.toasts[-1], "Circle drawn, 0 constraints")

    def test_a_press_on_a_flat_face_makes_a_sketch_attached_to_it(self):
        self.sk.face_under_cursor = picking.Pick("solid", "face", "Face6", 0.0)
        self.drag((10.0, 10.0, 100.0), (50.0, 40.0, 100.0))
        (sketch,) = self.sketches()
        self.assertEqual((sketch.plane, sketch.face), ("face", ("solid", "Face6")))

    def test_a_tap_draws_nothing_and_leaves_no_empty_sketch(self):
        self.drag((12.0, 8.0, 0.0), (13.0, 9.0, 0.0))
        self.assertEqual(self.sketches(), [])
        self.assertIn(("abort",), self.doc.log)
        self.assertEqual(self.selection, [])

    def test_a_rectangle_needs_both_sides_and_a_line_needs_a_length(self):
        self.drag((0.0, 0.0, 0.0), (60.0, 2.0, 0.0))
        self.assertEqual(self.sketches(), [])
        self.tool.values["mode"] = "Line"
        self.drag((0.0, 0.0, 0.0), (2.0, 1.0, 0.0))
        self.assertEqual(self.sketches(), [])

    def test_the_a_button_leaves_the_end_off_the_grid_and_a_grip_cancels(self):
        self.tool.values["mode"] = "Line"
        self.drag((0.0, 0.0, 0.0), (43.0, 7.0, 0.0), button1=True)
        self.assertEqual(self.sketches()[0].shapes, [("Line", (0.0, 0.0), (43.0, 7.0))])
        self.drag((10.0, 10.0, 0.0), (50.0, 50.0, 0.0), release=False)
        self.sim.set_hand(1, grip=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertFalse(self.tool.busy)
        self.assertEqual(self.toasts[-1], "Cancelled")

    def test_the_preview_follows_the_drag_and_the_readout_names_the_size(self):
        self.drag((0.0, 0.0, 0.0), (50.0, 30.0, 0.0), release=False)
        self.assertEqual(self.readouts[-1], "Rectangle: 50 mm x 30 mm")
        self.assertEqual(len(self.ghost.shapes[-1].outline[0]), 5)
        self.tool.values["mode"] = "Circle"
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.drag((0.0, 0.0, 0.0), (0.0, 20.0, 0.0), release=False)
        self.assertEqual(self.readouts[-1], "Circle: radius 20 mm")

    def test_choosing_another_plane_ends_the_sketch_and_the_next_one_lies_on_that_plane(self):
        self.drag((0.0, 0.0, 0.0), (50.0, 30.0, 0.0))
        self.assertNotEqual(self.selection, [])
        self.frames()
        self.assertNotEqual(self.selection, [])                                   # the sketch stays current while the plane is the same
        self.tool.values["plane"] = "XZ"
        self.frames()
        self.assertEqual(self.selection, [])
        self.drag((0.0, 0.0, 0.0), (50.0, 30.0, 0.0))
        self.assertEqual([s.plane for s in self.sketches()], ["XY", "XZ"])

    def arc_drag(self, start, end, third, finish=True):
        """The two ends dragged, then the third point and a press."""
        self.tool.values["mode"] = "Arc"
        self.drag(start, end)
        self.assertTrue(self.tool.busy)                                           # the release of the chord does not finish the arc
        self.cursor = list(third)
        self.tool.update(self.sim.frame(0.02))
        if finish:
            self.sim.set_hand(1, trigger=1.0)
            self.tool.update(self.sim.frame(0.02))
            self.sim.set_hand(1, trigger=0.0)
            self.tool.update(self.sim.frame(0.02))

    def test_an_arc_takes_its_ends_from_the_drag_and_its_third_point_from_the_next_press_in_one_transaction(self):
        self.arc_drag((0.0, 0.0, 0.0), (60.0, 0.0, 0.0), (31.0, 29.0, 0.0))
        (sketch,) = self.sketches()
        self.assertEqual(sketch.shapes, [("Arc", (0.0, 0.0), (60.0, 0.0), (30.0, 30.0))])
        self.assertEqual(self.doc.log, [("open", "Sketch"), ("commit",)])
        self.assertEqual(self.toasts[-1], "Arc drawn, 2 constraints")
        self.assertFalse(self.tool.busy)

    def test_the_arc_preview_and_the_readout_follow_the_hand_in_both_steps(self):
        self.tool.values["mode"] = "Arc"
        self.drag((0.0, 0.0, 0.0), (60.0, 0.0, 0.0), release=False)
        self.assertEqual(self.readouts[-1], "Arc: chord 60 mm")
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.readouts[-1], "Arc: press on the third point")           # the third point is still the end
        self.cursor = [30.0, 30.0, 0.0]
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.readouts[-1], "Arc: radius 30 mm")
        self.assertGreater(len(self.ghost.shapes[-1].outline[0]), 10)                  # a curve, not a chord

    def test_three_points_on_a_line_are_refused_and_a_grip_cancels_the_arc(self):
        self.arc_drag((0.0, 0.0, 0.0), (60.0, 0.0, 0.0), (30.0, 0.0, 0.0), finish=False)
        self.sim.set_hand(1, trigger=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.toasts[-1], "The three points lie on a line")
        self.assertTrue(self.tool.busy)
        self.sim.set_hand(1, grip=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertFalse(self.tool.busy)
        self.assertEqual(self.sketches(), [])
        self.assertEqual(self.toasts[-1], "Cancelled")

    def test_a_tap_in_the_arc_mode_draws_nothing(self):
        self.tool.values["mode"] = "Arc"
        self.drag((12.0, 8.0, 0.0), (13.0, 9.0, 0.0))
        self.assertFalse(self.tool.busy)
        self.assertEqual(self.sketches(), [])

    def test_edit_drags_a_point_of_a_sketch_and_one_transaction_keeps_it(self):
        self.tool.values["mode"] = "Line"
        self.drag((0.0, 0.0, 0.0), (50.0, 0.0, 0.0))
        self.tool.values["mode"] = "Edit"
        self.doc.log.clear()
        self.drag((50.0, 0.0, 0.0), (73.0, 18.0, 0.0))
        sketch = self.sketches()[0]
        self.assertEqual(sketch.points[(0, 2)], (70.0, 20.0))
        self.assertEqual(self.doc.log, [("open", f"Move point of {sketch.Label}"), ("commit",)])
        self.assertEqual(self.toasts[-1], f"Moved a point of {sketch.Label}")

    def test_a_move_the_sketch_cannot_take_is_refused_and_a_release_that_moved_nothing_keeps_nothing(self):
        self.tool.values["mode"] = "Line"
        self.drag((0.0, 0.0, 0.0), (50.0, 0.0, 0.0))
        self.tool.values["mode"] = "Edit"
        self.doc.log.clear()
        self.drag((50.0, 0.0, 0.0), (-200.0, 0.0, 0.0), release=False)
        self.assertEqual(self.readouts[-1], "The sketch cannot take that move")
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.doc.log[-1], ("abort",))

    def test_edit_on_a_curve_gives_it_a_dimension(self):
        self.tool.values["mode"] = "Edit"
        self.doc.objects["solid"].TypeId = sketching.TYPE
        self.doc.objects["solid"].points = {}
        picked = picking.Pick("solid", "edge", "Curve0", 0.0)
        self.tool._press_edit(self.doc, picked, (0.0, 0.0, 0.0))
        self.assertEqual(self.toasts[-1], "Dimension length = 10 mm")
        self.assertEqual(self.doc.log, [("open", "Dimension"), ("commit",)])

    def with_anchors(self, anchors, reach=5.0):
        self.tool.ctx.services["guide_anchors"] = lambda exclude: (anchors, reach)

    def test_a_line_that_is_nearly_parallel_to_a_slanted_line_is_made_exactly_so_with_a_guide(self):
        self.with_anchors([], 5.0)
        self.tool.values["mode"], self.tool.values["grid"] = "Line", "1 mm"
        self.drag((0.0, 0.0, 0.0), (40.0, 20.0, 0.0))                              # a slanted line to be parallel to
        self.drag((10.0, 50.0, 0.0), (49.0, 71.0, 0.0), release=False)
        start = self.tool._gesture["start"]
        end = self.tool._gesture["now"]
        direction = (end[0] - start[0], end[1] - start[1])
        self.assertAlmostEqual(direction[0] * 20.0 - direction[1] * 40.0, 0.0)       # along (40, 20) exactly
        guide, same = [g for g in self.ghost.guide_calls[-1] if g.label]            # the new line is nearly as long as the reference, too
        self.assertEqual((guide.text, guide.axis, same.text), ("Parallel", 3, "Equal length"))
        self.assertEqual(guide.anchor, (20.0, 10.0, 0.0))                           # from the middle of the reference line
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(len(self.sketches()[0].shapes), 2)

    def test_a_line_that_is_nearly_as_long_as_another_gets_its_length_and_a_guide(self):
        self.with_anchors([], 5.0)
        self.tool.values["mode"], self.tool.values["grid"] = "Line", "1 mm"
        self.drag((0.0, 0.0, 0.0), (40.0, 0.0, 0.0))
        self.drag((0.0, 20.0, 0.0), (0.0, 62.0, 0.0), release=False)                 # 42 mm against 40 mm
        self.assertEqual(self.tool._gesture["now"], (0.0, 60.0))
        self.assertEqual([g.text for g in self.ghost.guide_calls[-1] if g.label], ["Equal length"])
        self.assertEqual(self.ghost.guide_calls[-1][-1].anchor, (20.0, 0.0, 0.0))     # from the middle of the line it equals

    def test_a_line_across_a_slanted_line_is_perpendicular_and_the_a_button_leaves_it_alone(self):
        self.with_anchors([], 5.0)
        self.tool.values["mode"], self.tool.values["grid"] = "Line", "1 mm"
        self.drag((0.0, 0.0, 0.0), (40.0, 20.0, 0.0))
        self.drag((10.0, 50.0, 0.0), (29.0, 11.0, 0.0), release=False)               # across (40, 20): along (-20, 40)
        start, end = self.tool._gesture["start"], self.tool._gesture["now"]
        self.assertAlmostEqual((end[0] - start[0]) * 40.0 + (end[1] - start[1]) * 20.0, 0.0)
        self.assertEqual([g.text for g in self.ghost.guide_calls[-1] if g.label], ["Perpendicular", "Equal length"])
        self.sim.set_hand(1, trigger=0.0, button1=False)
        self.tool.update(self.sim.frame(0.02))
        self.drag((10.0, 50.0, 0.0), (49.0, 71.0, 0.0), release=False, button1=True)   # A held: exactly where the hand is
        self.assertEqual(self.tool._gesture["now"], (49.0, 71.0))

    def test_the_start_and_the_end_of_a_rectangle_line_up_with_the_model_and_the_guides_are_drawn(self):
        self.with_anchors([(7.0, 0.0, 0.0), (0.0, 33.0, 0.0)])
        self.drag((6.0, 32.0, 0.0), (61.0, 41.0, 0.0), release=False)
        self.assertEqual(self.tool._gesture["start"], (7.0, 33.0))                  # the grid point (0, 0) is not what the cursor lines up with
        self.assertTrue(self.ghost.guide_calls[-1] == [])                           # the end has nothing near
        self.cursor = [8.0, 41.0, 0.0]
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.tool._gesture["now"], (7.0, 40.0))
        (guide,) = self.ghost.guide_calls[-1]
        self.assertEqual((guide.kind, guide.axis, guide.anchor), ("axis", 0, (7.0, 0.0, 0.0)))

    def test_the_cursor_of_a_new_sketch_shows_the_guides_and_the_a_button_leaves_them(self):
        self.with_anchors([(7.0, 0.0, 0.0)])
        self.cursor = [8.0, 41.0, 0.0]
        self.sim.set_hand(1, trigger=0.0, button1=False)
        self.frames()
        self.assertEqual(self.ghost.markers[-1], (7.0, 40.0, 0.0))
        self.assertEqual(len(self.ghost.guide_calls[-1]), 1)
        self.drag((8.0, 41.0, 0.0), (61.0, 73.0, 0.0), button1=True)
        self.assertEqual(self.sketches()[0].shapes, [("Rectangle", (7.0, 40.0), (61.0, 73.0))])      # the start is on the guides, the end is free
        self.assertEqual(self.ghost.guide_calls[-1], [])

    def test_a_point_of_the_sketch_lines_up_with_the_points_of_the_sketch_but_not_with_itself(self):
        self.with_anchors([])
        self.tool.values["mode"] = "Line"
        self.drag((0.0, 0.0, 0.0), (50.0, 0.0, 0.0))
        self.tool.values["mode"] = "Edit"
        self.drag((50.0, 0.0, 0.0), (3.0, 52.0, 0.0), release=False)
        self.assertEqual(self.tool._gesture["now"], (0.0, 50.0))                    # x lines up with the other end of the line
        (guide,) = self.ghost.guide_calls[-1]
        self.assertEqual((guide.kind, guide.axis, guide.anchor), ("axis", 0, (0.0, 0.0, 0.0)))
        self.cursor = [47.0, 2.0, 0.0]
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.tool._gesture["now"], (50.0, 0.0))                    # its own old place is no anchor: only the grid and the other end

    def test_the_disc_has_the_grid_and_the_four_modes_and_the_square_shows_the_plane(self):
        labels = [slot.label for slot in self.tool.disc_slots()]
        self.assertEqual(labels, ["Grid +", "Rectangle", "Circle", "Grid -", "Edit", "Line"])
        self.assertEqual(self.tool.stick_click(), "Arc and planes")
        self.assertEqual([slot.label for slot in self.tool.disc_slots()], ["Grid +", "Arc", "XY plane", "Grid -", "XZ plane", "YZ plane"])
        self.assertEqual(self.tool.stick_click(), "Line, Rectangle, Circle and Edit")
        square = plane_square("XZ", (0.0, 0.0, 0.0), 10.0)
        self.assertEqual(len(square), 5)
        self.assertTrue(all(abs(p[1]) < 1e-9 for p in square))                  # the XZ plane has no Y extent


if __name__ == "__main__":
    unittest.main()
