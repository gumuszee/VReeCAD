import contextlib
import io
import math
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.cad import meshes
from freecad.BlocksCAD.cad import primitives as prim
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.core import snapping, stage
from freecad.BlocksCAD.core.navigation import WorldPose
from freecad.BlocksCAD.tools import base
from freecad.BlocksCAD.tools.primitives import PrimitiveTool


def close(a, b, places=6):
    return all(abs(x - y) < 10 ** -places for x, y in zip(a, b))


class StageTest(unittest.TestCase):
    def test_a_document_point_lands_on_the_stage_with_z_up(self):
        world = WorldPose()
        self.assertTrue(close(stage.to_stage(world, (100.0, 200.0, 300.0)), (0.1, 0.3, -0.2)))
        self.assertTrue(close(stage.to_document(world, (0.1, 0.3, -0.2)), (100.0, 200.0, 300.0)))

    def test_the_mapping_follows_the_navigation(self):
        world = WorldPose((0.5, 1.0, -1.0), mu.quat_from_axis_angle((0.0, 1.0, 0.0), 0.7), 2.5)
        for point in ((0.0, 0.0, 0.0), (12.5, -40.0, 33.0), (-1000.0, 5.0, 250.0)):
            self.assertTrue(close(stage.to_document(world, stage.to_stage(world, point)), point, 5))
        # at scale 2.5 the document origin sits at the world position
        self.assertTrue(close(stage.to_stage(world, (0.0, 0.0, 0.0)), world.position))
        self.assertTrue(close(stage.to_document(world, world.position), (0.0, 0.0, 0.0)))

    def test_a_scaled_world_makes_the_same_hand_move_a_shorter_document_length(self):
        point = (0.0, 0.0, -0.1)
        one = stage.to_document(WorldPose(scale=1.0), point)
        ten = stage.to_document(WorldPose(scale=10.0), point)
        self.assertAlmostEqual(mu.length(one) / mu.length(ten), 10.0, places=6)


class SnappingTest(unittest.TestCase):
    def test_snap_rounds_to_the_nearest_multiple_and_halves_go_up(self):
        self.assertEqual(snapping.snap(12.4, 5.0), 10.0)
        self.assertEqual(snapping.snap(12.5, 5.0), 15.0)
        self.assertEqual(snapping.snap(-12.4, 5.0), -10.0)
        self.assertEqual(snapping.snap_point((1.2, 7.6, -3.4), 2.0), (2.0, 8.0, -4.0))

    def test_a_drag_spans_the_box_between_its_points_whatever_the_direction(self):
        self.assertEqual(snapping.drag_box((0, 0, 0), (30, 20, 10), 10.0), ((0, 0, 0), (30, 20, 10)))
        self.assertEqual(snapping.drag_box((30, 20, 10), (0, 0, 0), 10.0), ((0, 0, 0), (30, 20, 10)))
        self.assertEqual(snapping.drag_box((0, 0, 0), (-20, 10, 0), 10.0), ((-20, 0, 0), (20, 10, 10)))

    def test_no_axis_collapses_and_a_tap_makes_a_default_box_around_the_start(self):
        self.assertEqual(snapping.drag_box((0, 0, 0), (30, 0, 0), 10.0), ((0, 0, 0), (30, 10, 10)))
        lo, size = snapping.drag_box((50, 50, 50), (50, 50, 50), 10.0)
        self.assertEqual((size, lo), ((40.0, 40.0, 40.0), (30.0, 30.0, 30.0)))
        self.assertTrue(snapping.is_tap((5, 5, 5), (5, 5, 5), 10.0))
        self.assertFalse(snapping.is_tap((5, 5, 5), (15, 5, 5), 10.0))


class ParametersTest(unittest.TestCase):
    LO, SIZE = (10.0, 20.0, 30.0), (40.0, 60.0, 80.0)

    def test_a_box_takes_the_box_itself(self):
        spec = prim.parameters("Box", self.LO, self.SIZE)
        self.assertEqual((spec.type, spec.props, spec.position), ("Part::Box", {"Length": 40.0, "Width": 60.0, "Height": 80.0}, self.LO))

    def test_round_shapes_are_centred_on_the_box_and_fit_the_smaller_side(self):
        cylinder = prim.parameters("Cylinder", self.LO, self.SIZE)
        self.assertEqual((cylinder.props, cylinder.position), ({"Radius": 20.0, "Height": 80.0}, (30.0, 50.0, 30.0)))
        cone = prim.parameters("Cone", self.LO, self.SIZE)
        self.assertEqual(cone.props, {"Radius1": 20.0, "Radius2": 0.0, "Height": 80.0})
        sphere = prim.parameters("Sphere", self.LO, self.SIZE)
        self.assertEqual((sphere.props, sphere.position), ({"Radius": 20.0}, (30.0, 50.0, 70.0)))
        prism = prim.parameters("Prism", self.LO, self.SIZE)
        self.assertEqual((prism.props["Circumradius"], prism.props["Height"], prism.props["Polygon"]), (20.0, 80.0, 6))

    def test_a_torus_stays_inside_its_box(self):
        for size in ((40.0, 60.0, 80.0), (100.0, 100.0, 10.0), (20.0, 20.0, 20.0)):
            spec = prim.parameters("Torus", (0.0, 0.0, 0.0), size)
            r1, r2 = spec.props["Radius1"], spec.props["Radius2"]
            self.assertGreater(r1, r2)
            self.assertLessEqual(r1 + r2, min(size[0], size[1]) / 2 + 1e-9)
            self.assertLessEqual(r2, size[2] / 2 + 1e-9)

    def test_a_wedge_stands_on_its_side_and_is_turned_about_x(self):
        spec = prim.parameters("Wedge", self.LO, self.SIZE)
        self.assertEqual(spec.rotation, ((1.0, 0.0, 0.0), 90.0))
        self.assertEqual((spec.props["Xmax"], spec.props["Ymax"], spec.props["Zmax"]), (40.0, 80.0, 60.0))
        self.assertEqual(spec.position, (10.0, 80.0, 30.0))

    def test_unknown_shapes_are_refused_and_every_listed_shape_has_a_spec(self):
        with self.assertRaises(ValueError):
            prim.parameters("Teapot", self.LO, self.SIZE)
        for name in prim.SHAPES:
            self.assertTrue(prim.parameters(name, self.LO, self.SIZE).type.startswith("Part::"))

    def test_describe(self):
        self.assertEqual(prim.describe("Box", (10, 20, 30), lambda v: f"{v:g} mm"), "Box: 10 mm x 20 mm x 30 mm")


class MeshTest(unittest.TestCase):
    LO, SIZE = (10.0, 20.0, 30.0), (40.0, 60.0, 80.0)
    EXPECTED = {   # volume of the shape in a 40 x 60 x 80 box, polygonal meshes are a little under the exact solids
        "Box": 40 * 60 * 80, "Cylinder": math.pi * 20 ** 2 * 80, "Cone": math.pi * 20 ** 2 * 80 / 3,
        "Sphere": 4 / 3 * math.pi * 20 ** 3, "Torus": 2 * math.pi ** 2 * 12 * 8 ** 2, "Wedge": 40 * 60 * 80 / 2,
        "Prism": 3 * math.sqrt(3) / 2 * 20 ** 2 * 80}

    def test_every_mesh_encloses_the_shape_with_outward_faces(self):
        for name in prim.SHAPES:
            mesh = meshes.build(name, self.LO, self.SIZE)
            self.assertAlmostEqual(meshes.volume(mesh) / self.EXPECTED[name], 1.0, delta=0.035, msg=name)   # positive: outward winding

    def test_triangles_agree_with_their_normals_and_the_normals_are_unit_vectors(self):
        for name in prim.SHAPES:
            mesh = meshes.build(name, self.LO, self.SIZE)
            self.assertEqual(len(mesh.points), len(mesh.normals), name)
            for n in mesh.normals:
                self.assertAlmostEqual(mu.length(n), 1.0, places=6, msg=name)
            for a, b, c in mesh.triangles:
                self.assertTrue(all(0 <= i < len(mesh.points) for i in (a, b, c)), name)
                face = mu.cross(mu.sub(mesh.points[b], mesh.points[a]), mu.sub(mesh.points[c], mesh.points[a]))
                self.assertGreater(mu.dot(face, mu.add(mesh.normals[a], mu.add(mesh.normals[b], mesh.normals[c]))), 0.0, name)

    def test_the_mesh_stays_inside_the_box_and_the_outline_lies_on_it(self):
        for name in prim.SHAPES:
            mesh = meshes.build(name, self.LO, self.SIZE)
            self.assertTrue(mesh.outline, name)
            for point in mesh.points + [p for curve in mesh.outline for p in curve]:
                for axis in range(3):
                    self.assertGreaterEqual(point[axis], self.LO[axis] - 1e-6, name)
                    self.assertLessEqual(point[axis], self.LO[axis] + self.SIZE[axis] + 1e-6, name)

    def test_the_structure_does_not_change_with_the_size_so_nothing_flickers(self):
        for name in prim.SHAPES:
            reference = meshes.build(name, self.LO, self.SIZE)
            for size in ((10.0, 10.0, 10.0), (200.0, 30.0, 500.0), (10.0, 10.0, 400.0)):
                other = meshes.build(name, self.LO, size)
                self.assertEqual(other.triangles, reference.triangles, f"{name} {size}")
                self.assertEqual([len(c) for c in other.outline], [len(c) for c in reference.outline], f"{name} {size}")

    def test_a_flat_torus_and_a_thin_box_still_build(self):
        for name in prim.SHAPES:
            mesh = meshes.build(name, (0.0, 0.0, 0.0), (100.0, 100.0, 2.0))
            self.assertGreater(meshes.volume(mesh), 0.0, name)

    def test_building_is_fast_enough_for_every_frame(self):
        import time
        start = time.perf_counter()
        for name in prim.SHAPES:
            meshes.build(name, self.LO, self.SIZE)
        self.assertLess(time.perf_counter() - start, 0.25)       # all seven together, well under a frame budget each


class FakeGhost:
    def __init__(self):
        self.calls = []

    def show_marker(self, point, half):
        self.calls.append(("marker", point, half))

    def hide_marker(self):
        self.calls.append(("hide_marker",))

    def show_shape(self, mesh):
        self.calls.append(("shape", len(mesh.points), len(mesh.triangles)))

    def show_box(self, lo, size):
        self.calls.append(("box", lo, size))

    def hide_shape(self):
        self.calls.append(("hide_shape",))

    def hide(self):
        self.calls.append(("hide",))

    def kinds(self):
        return [c[0] for c in self.calls]


class ToolTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.ghost = FakeGhost()
        self.created, self.toasts, self.readouts, self.haptics = [], [], [], []
        self.free = True
        self.document = object()
        world = WorldPose()
        context = base.ToolContext(dominant=1, haptic=lambda *a: self.haptics.append(a))
        context.services.update({
            "cursor": lambda hand: self.sim.hands[hand].aim.position,
            "to_document": lambda p: stage.to_document(world, p),
            "document": lambda: self.document,
            "trigger_free": lambda: self.free,
            "ghost": self.ghost,
            "toast": self.toasts.append,
            "readout": self.readouts.append,
            "create": lambda doc, shape, lo, size: self.created.append((doc, shape, lo, size)),
            "mesh": lambda shape, lo, size: meshes.Mesh([(0, 0, 0)] * 8, [(0, 0, 1)] * 8, [(0, 1, 2)] * 12),
        })
        self.tool = PrimitiveTool(context)

    def doc_to_stage(self, point):
        return stage.to_stage(WorldPose(), point)

    def hand_at(self, point_mm, **kw):
        self.sim.set_hand(1, position=self.doc_to_stage(point_mm), **kw)

    def step(self, n=1):
        for _ in range(n):
            self.tool.update(self.sim.frame(0.02))

    def test_it_declares_a_grid_and_a_shape_option(self):
        self.assertEqual([o.name for o in self.tool.options], ["grid", "shape"])
        self.assertEqual((self.tool.grid, self.tool.values["shape"]), (10.0, "Box"))
        self.tool.values["grid"] = "2 mm"
        self.assertEqual(self.tool.grid, 2.0)
        self.assertEqual(self.tool.options[0].choices[-1], "100 mm")

    def test_a_cross_marks_the_grid_point_under_the_cursor(self):
        self.hand_at((13.0, 28.0, 2.0))
        self.step()
        self.assertEqual(self.ghost.calls[-1][:2], ("marker", (10.0, 30.0, 0.0)))
        self.free = False                                           # the carousel has the trigger: no cross
        self.step()
        self.assertEqual(self.ghost.calls[-1], ("hide_marker",))

    def test_dragging_shows_the_ghost_and_the_sizes_and_releasing_makes_the_shape(self):
        self.hand_at((0.0, 0.0, 0.0))
        self.step()
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.hand_at((30.0, 20.0, 10.0), trigger=1.0)
        self.step()
        self.assertIn("shape", self.ghost.kinds())
        self.assertEqual(self.ghost.calls[-1], ("box", (0.0, 0.0, 0.0), (30.0, 20.0, 10.0)))
        self.assertEqual(self.readouts[-1], "Box: 30 mm x 20 mm x 10 mm")
        self.hand_at((30.0, 20.0, 10.0), trigger=0.0)
        self.step()
        self.assertEqual(self.created, [(self.document, "Box", (0.0, 0.0, 0.0), (30.0, 20.0, 10.0))])
        self.assertEqual(self.toasts, ["Box made: 30 mm x 20 mm x 10 mm"])
        self.assertIsNone(self.readouts[-1])
        self.assertEqual(self.ghost.calls[-1], ("hide_shape",))
        self.assertIn((1, 0.5, 0.04), self.haptics)

    def test_the_ghost_is_rebuilt_only_when_the_box_changes(self):
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step(2)
        self.hand_at((20.0, 20.0, 20.0), trigger=1.0)
        self.step(5)
        self.assertEqual(self.ghost.kinds().count("shape"), 2)       # the tap-sized box, then the dragged one

    def test_a_tap_places_a_default_shape_around_the_cursor_and_the_shape_option_is_used(self):
        self.tool.values["shape"] = "Sphere"
        self.hand_at((50.0, 50.0, 50.0), trigger=1.0)
        self.step()
        self.hand_at((50.0, 50.0, 50.0), trigger=0.0)
        self.step()
        self.assertEqual(self.created, [(self.document, "Sphere", (30.0, 30.0, 30.0), (40.0, 40.0, 40.0))])

    def test_the_disc_has_the_grid_on_top_and_bottom_and_four_shapes_that_the_click_pages(self):
        slots = self.tool.disc_slots()
        self.assertEqual(len(slots), 6)
        self.assertEqual([(s.label, s.option, s.value, s.kind) for s in (slots[0], slots[3])],
                         [("Grid +", "grid", 1, "step"), ("Grid -", "grid", -1, "step")])
        self.assertEqual([slots[i].label for i in (5, 1, 2, 4)], ["Box", "Cylinder", "Cone", "Sphere"])      # clockwise from the upper left
        self.assertTrue(all(slots[i].option == "shape" for i in (5, 1, 2, 4)))
        self.assertEqual(self.tool.disc_hub(), ["10 mm"])
        self.assertEqual(self.tool.stick_click(), "Shapes: Torus, Wedge, Prism")
        slots = self.tool.disc_slots()
        self.assertEqual([slots[i].label for i in (5, 1, 2, 4)], ["Torus", "Wedge", "Prism", ""])
        self.assertEqual(slots[4].option, "")                                  # the fourth place of the second page is empty
        self.assertEqual(self.tool.stick_click(), "Shapes: Box, Cylinder, Cone, Sphere")
        shown = set()
        for _ in range(2):                                                      # look at both pages
            shown |= {slot.value for slot in self.tool.disc_slots() if slot.option == "shape"}
            self.tool.stick_click()
        self.assertEqual(shown, set(prim.SHAPES))                               # every shape is on a page

    def test_the_grid_stops_at_its_ends_and_the_radial_stays_closed_during_a_drag(self):
        self.assertFalse(self.tool.options[0].wrap)
        self.assertFalse(self.tool.busy)
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.assertTrue(self.tool.busy)
        self.hand_at((0.0, 0.0, 0.0), trigger=0.0)
        self.step()
        self.assertFalse(self.tool.busy)

    def test_the_grid_option_changes_the_snap(self):
        self.tool.values["grid"] = "5 mm"
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.hand_at((12.0, 3.0, 0.0), trigger=1.0)
        self.step()
        self.hand_at((12.0, 3.0, 0.0), trigger=0.0)
        self.step()
        self.assertEqual(self.created[0][2:], ((0.0, 0.0, 0.0), (10.0, 5.0, 5.0)))

    def test_a_drag_in_the_negative_direction_makes_the_same_box(self):
        self.hand_at((40.0, 40.0, 40.0), trigger=1.0)
        self.step()
        self.hand_at((10.0, 20.0, 40.0), trigger=1.0)
        self.step()
        self.hand_at((10.0, 20.0, 40.0), trigger=0.0)
        self.step()
        self.assertEqual(self.created[0][2:], ((10.0, 20.0, 40.0), (30.0, 20.0, 10.0)))

    def test_a_grip_cancels_the_drag(self):
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.hand_at((30.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.sim.set_hand(0, grip=1.0)
        self.step()
        self.sim.set_hand(0, grip=0.0)
        self.hand_at((30.0, 0.0, 0.0), trigger=0.0)
        self.step(2)
        self.assertEqual(self.created, [])
        self.assertIsNone(self.readouts[-1])

    def test_a_press_the_interface_owns_does_not_start_a_shape(self):
        self.free = False
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.hand_at((0.0, 0.0, 0.0), trigger=0.0)
        self.step()
        self.assertEqual(self.created, [])
        self.free = True                                             # a trigger held on from the carousel is no new press
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.assertIsNotNone(self.tool._start)

    def test_without_a_document_nothing_is_made(self):
        self.document = None
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.hand_at((0.0, 0.0, 0.0), trigger=0.0)
        self.step()
        self.assertEqual((self.created, self.toasts), ([], ["No document open"]))

    def test_a_shape_freecad_cannot_make_is_reported_and_the_tool_goes_on(self):
        def fail(*args):
            raise RuntimeError("no solid")
        self.tool.ctx.services["create"] = fail
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step()
        self.hand_at((0.0, 0.0, 0.0), trigger=0.0)
        with contextlib.redirect_stdout(io.StringIO()) as printed:       # the tool names the error on the console
            self.step()
        self.assertIn("no solid", printed.getvalue())
        self.assertEqual(self.toasts, ["Could not make the box"])
        self.assertIsNone(self.tool._start)

    def test_deactivating_removes_the_preview(self):
        self.hand_at((0.0, 0.0, 0.0), trigger=1.0)
        self.step(2)
        self.tool.deactivate()
        self.assertEqual(self.ghost.calls[-1], ("hide",))
        self.assertIsNone(self.tool._start)

    def test_the_tool_is_registered_first_with_a_hint(self):
        from freecad.BlocksCAD.tools import registry
        self.assertIn("primitive", registry.names())
        self.assertEqual(registry.label_of("primitive"), "Create")
        self.assertTrue(registry.hint_of("primitive"))


if __name__ == "__main__":
    unittest.main()
