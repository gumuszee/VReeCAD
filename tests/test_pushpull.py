import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.cad import picking, pushpull
from freecad.BlocksCAD.tools import base
from freecad.BlocksCAD.tools.pushpull import PushPullTool


class SnappedTest(unittest.TestCase):
    def test_distances_round_to_the_grid_and_less_than_a_step_is_none(self):
        self.assertEqual(pushpull.snapped(23.0, 10.0), 20.0)
        self.assertEqual(pushpull.snapped(-27.0, 10.0), -30.0)
        self.assertEqual(pushpull.snapped(4.0, 10.0), 0.0)
        self.assertEqual(pushpull.snapped(-4.9, 10.0), 0.0)
        self.assertEqual(pushpull.snapped(5.0, 10.0), 10.0)

    def test_describe_names_push_and_pull(self):
        fmt = lambda v: f"{v:g} mm"
        self.assertEqual(pushpull.describe(30.0, fmt), "Push: 30 mm")
        self.assertEqual(pushpull.describe(-20.0, fmt), "Pull: 20 mm")
        self.assertEqual(pushpull.describe(0.0, fmt), "Push or pull: 0")


class FakeShape:
    def isNull(self):
        return False

    def hashCode(self):
        return 1


class FakeObject:
    def __init__(self, name):
        self.Name, self.Label, self.Shape = name, name.upper(), FakeShape()


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
        self.shown, self.hidden, self.guide_calls = [], 0, []

    def show_guides(self, guides, half):
        self.guide_calls.append(list(guides))

    def hide_guides(self):
        self.guide_calls.append([])

    def show_shape(self, mesh):
        self.shown.append(mesh)

    def hide_shape(self):
        self.hidden += 1


class FakeDocument:
    def __init__(self, *names):
        self.objects = {n: FakeObject(n) for n in names}

    def getObject(self, name):
        return self.objects.get(name)


class PushPullToolTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.sim.set_head(position=(0.0, 1.6, 0.0), look_at_point=(0.0, 1.2, -1.0))
        self.sim.set_hand(1, position=(0.0, 1.2, -0.4), point_at=(0.0, 1.2, -2.0))
        self.doc = FakeDocument("box")
        self.cursor = [0.0, 0.0, 0.0]
        self.selection, self.toasts, self.readouts, self.applied = [], [], [], []
        self.normal = (0.0, 0.0, 1.0)
        self.ghost = FakeGhost()
        ctx = base.ToolContext(dominant=1)
        ctx.services.update({
            "cursor": lambda hand: tuple(self.cursor), "to_document": lambda p: p, "document": lambda: self.doc,
            "toast": self.toasts.append, "readout": self.readouts.append, "highlight": FakeHighlights(), "ghost": self.ghost,
            "pick": lambda doc, point, mm, kind=None: picking.Pick("box", "face", "Face6", 0.0),
            "display": lambda obj, sub: picking.Display(), "get_selection": lambda doc: list(self.selection),
            "set_selection": lambda doc, items: self.selection.__init__(items), "clear_selection": lambda: self.selection.clear(),
            "pushpull_face": lambda obj, sub: ((0.0, 0.0, 0.0), self.normal) if self.normal else None,
            "pushpull_mesh": lambda obj, sub, distance: object(),
            "pushpull": lambda doc, name, sub, distance: (self.applied.append((name, sub, distance)) or "Pushed", "result")})
        self.tool = PushPullTool(ctx)

    def frames(self, count=3, **hand):
        for _ in range(count):
            self.tool.update(self.sim.frame(0.1))

    def gesture(self, move, release=True):
        self.sim.set_hand(1, trigger=0.0)
        self.frames()
        self.sim.set_hand(1, trigger=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.cursor = list(move)
        self.tool.update(self.sim.frame(0.02))
        if release:
            self.sim.set_hand(1, trigger=0.0)
            self.tool.update(self.sim.frame(0.02))

    def test_a_drag_along_the_normal_pushes_by_whole_grid_steps_in_one_call(self):
        self.gesture((0.0, 0.0, 33.0))
        self.assertEqual(self.applied, [("box", "Face6", 30.0)])
        self.assertEqual(self.selection, [("result", "")])
        self.assertEqual(self.toasts[-1], "Pushed")

    def test_a_drag_against_the_normal_pulls_and_sideways_movement_counts_for_nothing(self):
        self.gesture((500.0, 70.0, -48.0))
        self.assertEqual(self.applied, [("box", "Face6", -50.0)])

    def test_a_tap_selects_the_face_and_changes_nothing(self):
        self.gesture((0.0, 0.0, 3.0))
        self.assertEqual(self.applied, [])
        self.assertEqual(self.selection, [("box", "Face6")])

    def test_the_ghost_and_the_readout_follow_the_distance_and_vanish_afterwards(self):
        self.gesture((0.0, 0.0, 20.0), release=False)
        self.assertTrue(self.tool.busy)
        self.assertEqual(len(self.ghost.shown), 1)
        self.assertEqual(self.readouts[-1], "Push: 20 mm")
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertFalse(self.tool.busy)
        self.assertIsNone(self.readouts[-1])

    def test_a_grip_cancels(self):
        self.gesture((0.0, 0.0, 40.0), release=False)
        self.sim.set_hand(1, grip=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertFalse(self.tool.busy)
        self.assertEqual(self.applied, [])
        self.assertEqual(self.toasts[-1], "Cancelled")

    def test_a_curved_face_is_refused_but_selected(self):
        self.normal = None
        self.gesture((0.0, 0.0, 40.0))
        self.assertFalse(self.applied)
        self.assertEqual(self.toasts[-1], "Only flat faces can be pushed or pulled")
        self.assertEqual(self.selection, [("box", "Face6")])

    def with_anchors(self, anchors, reach=5.0):
        self.asked = []
        self.tool.ctx.services["guide_anchors"] = lambda exclude: (self.asked.append(exclude) or anchors, reach)

    def test_a_face_lines_up_level_with_a_point_of_the_model_and_the_guide_is_drawn(self):
        self.with_anchors([(80.0, 5.0, 37.0), (0.0, 0.0, 90.0)])
        self.gesture((0.0, 0.0, 34.0), release=False)
        self.assertEqual(self.readouts[-1], "Push: 37 mm")                       # the grid would say 30 mm
        (guide,) = self.ghost.guide_calls[-1]
        self.assertEqual((guide.kind, guide.axis, guide.anchor), ("axis", 2, (80.0, 5.0, 37.0)))
        self.assertEqual(guide.point, (0.0, 0.0, 37.0))                         # the hand's place in the plane of the face
        self.assertEqual(self.asked[-1], ("box",))                              # the object being pushed is no anchor
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.applied, [("box", "Face6", 37.0)])
        self.assertEqual(self.ghost.guide_calls[-1], [])

    def test_a_point_in_the_plane_of_the_face_and_points_out_of_reach_are_no_anchors(self):
        self.with_anchors([(80.0, 5.0, 0.0), (0.0, 0.0, 90.0)])
        self.gesture((0.0, 0.0, 22.0), release=False)
        self.assertEqual(self.readouts[-1], "Push: 20 mm")
        self.assertEqual(self.ghost.guide_calls[-1], [])

    def test_a_pull_lines_up_too_and_the_normal_of_a_tilted_face_has_no_axis_colour(self):
        self.with_anchors([(0.0, 0.0, -48.5)])
        self.gesture((0.0, 0.0, -50.0), release=False)
        self.assertEqual(self.readouts[-1], "Pull: 48.5 mm")
        self.normal = (0.6, 0.0, 0.8)
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.cursor = [0.0, 0.0, 0.0]
        self.with_anchors([(0.0, 0.0, 50.0)])                                   # 40 mm along the normal, the hand is at 39.2 mm
        self.gesture((0.0, 0.0, 49.0), release=False)
        self.assertEqual(self.ghost.guide_calls[-1][0].axis, 3)

    def test_the_tool_touches_faces_only(self):
        self.assertEqual(self.tool.pick_kind, "face")


if __name__ == "__main__":
    unittest.main()
