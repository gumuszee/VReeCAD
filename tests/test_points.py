import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.cad import block as real_block
from freecad.BlocksCAD.cad import blockgeom as bg
from freecad.BlocksCAD.cad import picking
from freecad.BlocksCAD.core import grab
from freecad.BlocksCAD.tools import base
from freecad.BlocksCAD.tools.points import PointsTool


class FakeShape:
    def isNull(self):
        return False

    def hashCode(self):
        return 1


class FakeBlock:
    def __init__(self, name):
        self.Name, self.Label, self.Shape = name, name.upper(), FakeShape()
        self.vertices, self.faces = bg.box((0, 0, 0), (100, 100, 100))
        self.fixed = set()


class FakeDocument:
    def __init__(self, *blocks):
        self.objects = {b.Name: b for b in blocks}
        self.log = []

    def getObject(self, name):
        return self.objects.get(name)

    def openTransaction(self, text):
        self.log.append(("open", text))

    def commitTransaction(self):
        self.log.append(("commit",))

    def abortTransaction(self):
        self.log.append(("abort",))

    def recompute(self):
        self.log.append(("recompute",))


class FakeBlocks:
    """What `cad.block` offers the tool, on fake objects and in document coordinates."""
    parse_sub = staticmethod(real_block.parse_sub)

    def __init__(self, doc):
        self.doc = doc

    def blocks(self, doc):
        return list(doc.objects.values())

    def pick(self, doc, point, mm, kind):
        best = None
        for obj in doc.objects.values():
            if kind == "vertex":
                d, i = bg.nearest_vertex(obj.vertices, point)
                found = (d, f"Point{i}")
            else:
                d, pair, _, _ = bg.nearest_edge(obj.vertices, obj.faces, point)
                found = (d, f"Segment{pair[0]}-{pair[1]}")
            if grab.within_reach(kind, found[0], mm) and (best is None or found[0] < best.distance):
                best = picking.Pick(obj.Name, kind, found[1], found[0])
        return best

    def read(self, obj):
        return list(obj.vertices), list(obj.faces)

    def apply(self, doc, obj, vertices, faces=None):
        new_faces = faces if faces is not None else obj.faces
        error = bg.validate(vertices, new_faces)
        if error is None:
            obj.vertices, obj.faces = list(vertices), list(new_faces)
        return error

    def set_picked(self, obj, index):
        self.picked = (obj.Name, index)

    def is_point_fixed(self, obj, index):
        return index in obj.fixed

    def set_point_fixed(self, obj, index, value):
        obj.fixed = obj.fixed | {index} if value else obj.fixed - {index}

    def renumber_fixed(self, obj, removed):
        obj.fixed = {i - 1 if i > removed else i for i in obj.fixed if i != removed}

    def to_local(self, obj, point):
        return tuple(point)

    def to_world(self, obj, point):
        return tuple(point)

    def display(self, obj, sub):
        return picking.Display(markers=[obj.vertices[0]])

    def handles(self, doc):
        return picking.Display(markers=[v for o in doc.objects.values() for v in o.vertices])

    def signature(self, doc):
        return tuple((o.Name, tuple(o.vertices)) for o in doc.objects.values())


class FakeLayer:
    def __init__(self):
        self.shown = 0

    def show(self, displays, half):
        self.shown += 1

    def hide(self):
        pass


class FakeHighlights(FakeLayer):
    def __init__(self):
        self.hover, self.selected = FakeLayer(), FakeLayer()


class PointsToolTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.sim.set_head(position=(0.0, 1.6, 0.0), look_at_point=(0.0, 1.2, -1.0))
        self.sim.set_hand(1, position=(0.0, 1.2, -0.4), point_at=(0.0, 1.2, -2.0))
        self.block = FakeBlock("block")
        self.doc = FakeDocument(self.block)
        self.cursor = [100.0, 0.0, 0.0]
        self.placement = "snap"                                                      # the A button changes it while the trigger is held
        self.selection, self.toasts, self.readouts = [], [], []
        self.highlights = FakeHighlights()
        ctx = base.ToolContext(dominant=1)
        ctx.services.update({
            "cursor": lambda hand: tuple(self.cursor), "to_document": lambda p: p, "document": lambda: self.doc,
            "toast": self.toasts.append, "readout": self.readouts.append, "highlight": self.highlights,
            "blocks": FakeBlocks(self.doc), "mm_per_metre": lambda: 1000.0, "placement": lambda: self.placement,
            "get_selection": lambda doc: list(self.selection), "set_selection": lambda doc, items: self.selection.__init__(items),
            "clear_selection": lambda: self.selection.clear()})
        self.tool = PointsTool(ctx)

    def frames(self, count=3, **inputs):
        for _ in range(count):
            self.tool.update(self.sim.frame(0.1))

    def drag(self, to, release=True, **inputs):
        self.sim.set_hand(1, trigger=0.0, button1=False)
        self.frames()
        self.sim.set_hand(1, trigger=1.0, **inputs)
        self.tool.update(self.sim.frame(0.02))
        self.cursor = list(to)
        self.tool.update(self.sim.frame(0.02))
        if release:
            self.sim.set_hand(1, trigger=0.0, button1=False)
            self.tool.update(self.sim.frame(0.02))

    def test_dragging_a_point_snaps_it_to_the_grid_and_is_one_transaction(self):
        self.drag((123.0, -4.0, 17.0))
        self.assertEqual(self.block.vertices[1], (120.0, 0.0, 20.0))
        self.assertEqual(self.doc.log.count(("commit",)), 1)
        self.assertEqual(self.doc.log[0], ("open", "Move point of BLOCK"))
        self.assertEqual(self.toasts[-1], "Moved point 1 of BLOCK")
        self.assertEqual(self.selection, [("block", "")])
        self.assertEqual(self.tool.ctx.services["blocks"].picked, ("block", 1))     # the value panels show the point

    def test_the_free_placement_leaves_the_point_off_the_grid_and_the_grid_placement_has_no_guides(self):
        self.placement = "free"
        self.drag((123.0, -4.0, 17.0))
        self.assertEqual(self.block.vertices[1], (123.0, -4.0, 17.0))
        self.placement = "grid"
        self.drag((143.0, -4.0, 17.0))
        self.assertEqual(self.block.vertices[1], (140.0, 0.0, 20.0))

    def test_a_position_the_block_cannot_take_is_refused_and_the_point_stays_at_the_last_good_one(self):
        blocks = self.tool.ctx.services["blocks"]
        real_apply = blocks.apply
        blocks.apply = lambda doc, obj, vertices, faces=None: "FreeCAD cannot build that block" if min(v[2] for v in vertices) < -100 else real_apply(doc, obj, vertices, faces)
        self.drag((100.0, 0.0, 50.0), release=False)
        self.cursor = [100.0, 0.0, -200.0]
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.block.vertices[1], (100.0, 0.0, 50.0))
        self.assertEqual(self.readouts[-1], "FreeCAD cannot build that block")
        self.assertTrue(self.tool.busy)

    def test_the_tool_starts_in_the_move_mode_whatever_the_mode_was(self):
        self.tool.values["mode"] = "Split"
        self.tool.activate()
        self.assertEqual(self.tool.values["mode"], "Move")

    def test_a_press_on_nothing_says_how_to_make_a_block_only_when_the_document_has_none(self):
        self.cursor = [900.0, 900.0, 900.0]
        self.sim.set_hand(1, trigger=0.0)
        self.frames()
        self.sim.set_hand(1, trigger=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.toasts, [])                                    # the document has a block: an empty press is just that
        self.doc.objects.clear()
        self.sim.set_hand(1, trigger=0.0)
        self.frames()
        self.sim.set_hand(1, trigger=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(len(self.toasts), 1)
        self.assertIn("Nothing to edit", self.toasts[0])

    def test_a_tap_that_moves_nothing_changes_nothing_but_selects_the_block(self):
        self.drag((102.0, 1.0, 0.0))
        self.assertEqual(self.block.vertices[1], (100.0, 0.0, 0.0))
        self.assertIn(("abort",), self.doc.log)
        self.assertEqual(self.selection, [("block", "")])

    def test_a_grip_cancels(self):
        self.drag((150.0, 0.0, 0.0), release=False)
        self.sim.set_hand(1, grip=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertFalse(self.tool.busy)
        self.assertEqual(self.toasts[-1], "Cancelled")
        self.assertIn(("abort",), self.doc.log)

    def test_the_split_mode_adds_a_point_on_the_edge_and_drags_it(self):
        self.tool.values["mode"] = "Split"
        self.cursor = [50.0, 2.0, 1.0]
        self.drag((50.0, -30.0, 0.0))
        self.assertEqual(len(self.block.vertices), 9)
        self.assertEqual(self.block.vertices[8], (50.0, -30.0, 0.0))
        self.assertEqual(self.toasts[-1], "Split point 8 of BLOCK")
        self.assertEqual(self.doc.log.count(("commit",)), 1)
        self.assertIsNone(bg.validate(self.block.vertices, self.block.faces))

    def test_a_split_that_is_not_moved_is_still_kept(self):
        self.tool.values["mode"] = "Split"
        self.cursor = [50.0, 0.0, 0.0]
        self.drag((50.0, 0.0, 0.0))
        self.assertEqual(len(self.block.vertices), 9)
        self.assertEqual(self.block.vertices[8], (50.0, 0.0, 0.0))

    def test_flat_faces_hold_a_corner_where_its_faces_are_and_free_faces_let_it_go(self):
        self.tool.values["faces"] = "Flat"
        self.drag((130.0, -20.0, 40.0), release=False)
        self.assertEqual(self.block.vertices[1], (100.0, 0.0, 0.0))                 # three flat faces: the corner cannot move
        self.assertTrue(self.readouts[-1].endswith("(flat)"))
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.tool.values["faces"] = "Free"
        self.cursor = [100.0, 0.0, 0.0]
        self.drag((130.0, -20.0, 40.0))
        self.assertEqual(self.block.vertices[1], (130.0, -20.0, 40.0))

    def test_a_split_point_slides_along_its_edge_while_the_faces_are_flat(self):
        self.tool.values["mode"], self.tool.values["faces"] = "Split", "Flat"
        self.cursor = [50.0, 2.0, 1.0]
        self.drag((80.0, -30.0, 10.0))
        self.assertEqual(self.block.vertices[8], (80.0, 0.0, 0.0))
        self.assertIsNone(bg.validate(self.block.vertices, self.block.faces))

    def remove(self, at):
        self.tool.values["mode"] = "Remove"
        self.cursor = list(at)
        self.sim.set_hand(1, trigger=0.0, button1=False)
        self.frames()
        self.sim.set_hand(1, trigger=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))

    def test_the_remove_mode_cuts_a_corner_off_in_one_undo_step_and_selects_the_block(self):
        self.remove((100.0, 0.0, 0.0))
        self.assertEqual(len(self.block.vertices), 7)
        self.assertEqual(len(self.block.faces), 7)
        self.assertEqual([e for e in self.doc.log if e[0] in ("open", "commit", "abort")],
                         [("open", "Remove point of BLOCK"), ("commit",)])
        self.assertEqual(self.selection, [("block", "")])
        self.assertEqual(self.toasts[-1], "Removed point 1 of BLOCK")
        self.assertEqual(self.tool.values["mode"], "Remove")                           # the mode stays: several points can go in a row
        self.assertFalse(self.tool.busy)                                              # no drag follows

    def test_a_point_that_split_an_edge_goes_back_to_the_box(self):
        vertices, faces, index = bg.split_edge(self.block.vertices, self.block.faces, 0, 1, (50.0, 0.0, 0.0))
        self.block.vertices, self.block.faces = vertices, faces
        self.remove((50.0, 0.0, 0.0))
        self.assertEqual(self.block.vertices, bg.box((0, 0, 0), (100, 100, 100))[0])
        self.assertEqual(len(self.block.faces), 6)

    def test_a_removal_that_leaves_no_solid_is_refused_and_the_block_stays(self):
        self.block.vertices = [(0, 0, 0), (100, 0, 0), (0, 100, 0), (0, 0, 100)]
        self.block.faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
        self.remove((0.0, 0.0, 0.0))
        self.assertEqual(len(self.block.vertices), 4)
        self.assertEqual([e for e in self.doc.log if e[0] in ("open", "commit", "abort")], [("open", "Remove point of BLOCK"), ("abort",)])
        self.assertTrue(self.toasts[-1].startswith("Cannot remove that point"))

    def test_a_block_with_bound_points_keeps_them(self):
        self.tool._blocks().has_bound_points = lambda obj: True
        self.remove((100.0, 0.0, 0.0))
        self.assertEqual(len(self.block.vertices), 8)
        self.assertEqual(self.toasts[-1], "Unbind the points of the block first")
        self.assertEqual([e for e in self.doc.log if e[0] in ("open", "commit", "abort")], [])

    def test_a_point_off_the_grid_stays_where_it_is_until_the_hand_has_moved_away_from_the_press(self):
        self.block.vertices[1] = (103.0, 4.0, 0.0)
        self.cursor = [103.0, 4.0, 0.0]
        self.sim.set_hand(1, trigger=0.0, button1=False)
        self.frames()
        self.sim.set_hand(1, trigger=1.0)
        self.tool.update(self.sim.frame(0.02))
        self.cursor = [108.0, 7.0, 0.0]                                              # a tremor, within the reach of the press
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.block.vertices[1], (103.0, 4.0, 0.0))                  # not snapped to the grid
        self.assertEqual(self.readouts[-1], "Point 1")
        self.cursor = [140.0, 7.0, 0.0]                                              # the hand leaves: the point follows, on the grid
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.block.vertices[1], (140.0, 10.0, 0.0))
        self.cursor = [104.0, 4.0, 0.0]                                              # once moving, it goes on even near the first place
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.block.vertices[1], (100.0, 0.0, 0.0))

    def hold_point(self, at=(100.0, 0.0, 0.0)):
        self.cursor = list(at)
        self.sim.set_hand(1, trigger=0.0, button1=False)
        self.frames()
        self.sim.set_hand(1, trigger=1.0)
        self.tool.update(self.sim.frame(0.02))

    def test_b_while_a_point_is_held_fixes_it_and_it_stays_while_the_hand_moves(self):
        self.assertIsNone(self.tool.toggle_fixed())                                  # nothing is held
        self.hold_point()
        self.assertEqual(self.tool.toggle_fixed(), "Fixed point 1")
        self.assertEqual(self.block.fixed, {1})
        self.cursor = [160.0, 40.0, 0.0]
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.block.vertices[1], (100.0, 0.0, 0.0))
        self.assertEqual(self.readouts[-1], "Point 1 is fixed (B releases)")
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.doc.log[-1], ("commit",))
        self.assertEqual(self.toasts[-1], "Fixed point 1 of BLOCK")

    def test_a_fixed_point_does_not_move_and_b_releases_it_so_that_it_follows_after_the_hand_has_left(self):
        self.block.fixed = {1}
        self.hold_point()
        self.cursor = [160.0, 40.0, 0.0]
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.block.vertices[1], (100.0, 0.0, 0.0))
        self.assertEqual(self.tool.toggle_fixed(), "Released point 1")
        self.tool.update(self.sim.frame(0.02))                                       # the hand goes on from here
        self.assertEqual(self.block.vertices[1], (100.0, 0.0, 0.0))
        self.cursor = [220.0, 40.0, 0.0]
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.block.vertices[1], (220.0, 40.0, 0.0))
        self.sim.set_hand(1, trigger=0.0)
        self.tool.update(self.sim.frame(0.02))
        self.assertEqual(self.toasts[-1], "Moved point 1 of BLOCK")

    def test_a_fixed_point_is_not_removed_and_the_numbers_of_the_fixed_points_follow_a_removal(self):
        self.block.fixed = {1, 5}
        self.remove((100.0, 0.0, 0.0))
        self.assertEqual(len(self.block.vertices), 8)
        self.assertIn("is fixed", self.toasts[-1])
        self.remove((0.0, 0.0, 0.0))                                                 # point 0 goes: the points after it are one lower
        self.assertEqual(len(self.block.vertices), 7)
        self.assertEqual(self.block.fixed, {0, 4})

    def test_nothing_is_touched_far_from_the_points(self):
        self.cursor = [50.0, 50.0, 50.0]
        self.drag((60.0, 60.0, 60.0))
        self.assertEqual(self.block.vertices, bg.box((0, 0, 0), (100, 100, 100))[0])
        self.assertFalse(self.tool.busy)

    def test_the_points_of_the_blocks_are_marked_and_the_option_disc_has_the_modes_and_the_faces(self):
        self.frames()
        self.assertGreater(self.highlights.selected.shown, 0)
        labels = [slot.label for slot in self.tool.disc_slots()]
        self.assertEqual(labels, ["Move point", "Split edge", "Remove point", "", "Free faces", "Flat faces", "", ""])
        self.tool.values["faces"] = "Flat"
        self.assertEqual(self.tool.stick_click(), "Mode and faces reset")
        self.assertEqual(self.tool.values["faces"], "Free")
        self.assertEqual((self.tool.pick_kind, self.tool.grid), ("vertex", 10.0))
        self.tool.values["mode"] = "Split"
        self.assertEqual(self.tool.pick_kind, "edge")


if __name__ == "__main__":
    unittest.main()
