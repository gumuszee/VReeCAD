import json
import math
import os
import tempfile
import unittest

import support  # noqa: F401
from freecad.BlocksCAD.backends.sim import SimInput
from freecad.BlocksCAD.core import mathutil as mu
from freecad.BlocksCAD.ui import defaults
from freecad.BlocksCAD.ui import layout as lay
from freecad.BlocksCAD.ui import pointing
from freecad.BlocksCAD.ui import ring as rg

CONTROLLER = (-0.2, 1.15, -0.35)
HEAD = (0.0, 1.6, 0.0)
SIDES = [[[0]], [[1]], [[2]]]        # side -> rows -> pages


class RingTest(unittest.TestCase):
    def setUp(self):
        self.sim = SimInput()
        self.ring = rg.PaletteRing(SIDES)
        self.sim.set_head(position=HEAD, look_at_point=CONTROLLER)
        self.sim.set_hand(0, position=CONTROLLER, point_at=(0, 1.2, -1))
        self.sim.set_hand(1, position=(0.2, 1.2, -0.3), point_at=(0.2, 1.2, -2))

    def run_frames(self, n=30, **kw):
        result = None
        for _ in range(n):
            result = self.ring.update(self.sim.frame(0.02), **kw)
        return result

    def slot_point(self, slot, page=0):
        pose = self.ring.poses[page]
        col, row = slot % lay.COLS, slot // lay.COLS
        x = (col - (lay.COLS - 1) / 2) * (rg.CELL + rg.GAP)
        y = ((lay.ROWS - 1) / 2 - row) * (rg.CELL + rg.GAP) + rg.GRID_Y
        return mu.add(pose.centre, mu.add(mu.mul(pose.u, x), mu.mul(pose.v, y))), pose.n

    def panel_point(self, page, fx, fy):
        """A point on a panel: fx and fy are fractions of its half width and half height."""
        pose = self.ring.poses[page]
        return mu.add(pose.centre, mu.add(mu.mul(pose.u, fx * rg.PANEL_W / 2), mu.mul(pose.v, fy * rg.PANEL_H / 2))), pose.n

    def aim_at(self, point, normal, distance=0.3):
        self.sim.set_hand(1, position=mu.add(point, mu.mul(normal, distance)), point_at=point)

    def title_point(self, page=0):
        pose = self.ring.poses[page]
        y = (rg.TITLE_Y[0] + rg.TITLE_Y[1]) / 2
        return mu.add(pose.centre, mu.mul(pose.v, y)), pose.n

    def flick(self, x):
        self.sim.set_hand(0, stick=(x, 0.0))
        self.run_frames(1)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(60)

    def test_locate_slot(self):
        self.assertEqual(rg.PaletteRing.locate_slot(0.0, 0.0), 6)   # the centre lies between columns 1 and 2
        self.assertEqual(rg.PaletteRing.locate_slot(-(rg.CELL + rg.GAP) / 2, 0.0), 5)
        self.assertEqual(rg.PaletteRing.locate_slot(-rg.GRID_W / 2 + 0.01, rg.GRID_H / 2 - 0.01), 0)
        self.assertEqual(rg.PaletteRing.locate_slot(rg.GRID_W / 2 - 0.01, -rg.GRID_H / 2 + 0.01), lay.SLOTS - 1)
        self.assertIsNone(rg.PaletteRing.locate_slot(rg.GRID_W, 0.0))
        self.assertIsNone(rg.PaletteRing.locate_slot(0.0, -rg.GRID_H))

    def test_gaze_controls_visibility(self):
        self.assertTrue(self.run_frames().visible)
        self.assertAlmostEqual(self.ring.fade, 1.0)
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))   # look away
        self.assertFalse(self.run_frames().visible)
        self.assertEqual(self.ring.fade, 0.0)

    def look_off(self, degrees):
        """Turn the head about the vertical so that its gaze is `degrees` (within a degree) away from the nearest part of the carousel;
        returns the angle reached."""
        origin = self.ring.origin
        base = mu.normalize(mu.sub(origin, HEAD))
        best = None
        for yaw in range(-120, 121):
            direction = mu.rotate(mu.quat_from_axis_angle((0.0, 1.0, 0.0), math.radians(yaw)), base)
            self.sim.set_head(look_at_point=mu.add(HEAD, direction))
            angle = math.degrees(self.ring.gaze_angle(origin, HEAD, self.sim.head.orientation))
            if best is None or abs(angle - degrees) < abs(best[0] - degrees):
                best = (angle, yaw)
        self.sim.set_head(look_at_point=mu.add(HEAD, mu.rotate(mu.quat_from_axis_angle((0.0, 1.0, 0.0), math.radians(best[1])), base)))
        return best[0]

    def test_the_carousel_appears_inside_a_narrow_gaze_cone_and_stays_inside_a_wider_one(self):
        self.run_frames()
        self.look_off(42.0)                                  # between the two cones
        self.assertTrue(self.run_frames(10).visible)         # shown, so it stays
        self.look_off(90.0)
        self.assertFalse(self.run_frames(30).visible)
        self.look_off(42.0)
        self.assertFalse(self.run_frames(30).visible)        # hidden, so it does not appear yet
        self.look_off(30.0)
        self.assertTrue(self.run_frames(30).visible)

    def test_the_far_end_of_a_long_column_of_panels_keeps_the_carousel_shown(self):
        self.ring = rg.PaletteRing([[[0]], [[1]], [[2]], [[3], [4], [5], [6]]])
        self.run_frames(30)
        far = max(self.ring.poses.values(), key=lambda p: mu.length(mu.sub(p.centre, self.ring.origin))).centre
        head = (0.05, 1.3, -0.65)                           # beside the far end of the column, as when the values are worked
        self.sim.set_head(position=head, look_at_point=far)
        r = self.run_frames(30)
        self.assertTrue(r.visible)
        origin_cone = mu.dot(mu.normalize(mu.sub(self.ring.origin, head)), mu.normalize(mu.sub(far, head)))
        self.assertLess(origin_cone, math.cos(math.radians(35.0)))   # the controller alone is outside the cone: the panel keeps it shown

    def test_working_the_carousel_keeps_it_shown_in_a_wide_cone(self):
        self.run_frames()
        self.look_off(60.0)
        self.assertFalse(self.run_frames(30).visible)
        self.look_off(30.0)
        self.run_frames(30)
        self.look_off(60.0)
        self.ring.hold_visible = True
        self.assertTrue(self.run_frames(30).visible)
        self.ring.hold_visible = False
        self.assertFalse(self.run_frames(30).visible)

    def test_pin_shows_the_ring_without_gaze_and_navigation_hides_it(self):
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))
        self.sim.set_hand(0, button1=True)
        self.run_frames(1)
        self.sim.set_hand(0, button1=False)
        self.assertTrue(self.run_frames().visible)
        self.assertFalse(self.run_frames(navigating=True).visible)
        self.sim.set_hand(0, button1=True)       # second press releases the pin
        self.run_frames(1, navigating=False)
        self.sim.set_hand(0, button1=False)
        self.assertFalse(self.run_frames().visible)

    def test_stick_flick_turns_one_side_per_flick(self):
        self.run_frames()
        self.sim.set_hand(0, stick=(1.0, 0.0))
        r = self.run_frames(1)
        self.assertEqual(self.ring.index, 1)
        self.assertEqual(r.haptics[0][0], 0)
        self.run_frames(10)                      # holding does not repeat
        self.assertEqual(self.ring.index, 1)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(2)
        self.sim.set_hand(0, stick=(-1.0, 0.0))
        self.run_frames(1)
        self.assertEqual(self.ring.index, 0)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(2)
        self.sim.set_hand(0, stick=(1.0, 0.0))
        self.run_frames(1)
        self.sim.set_hand(0, stick=(0.0, 0.0))
        self.run_frames(60)
        self.assertAlmostEqual(self.ring.angle, self.ring.target_angle, places=3)
        self.assertEqual(self.ring.front_side(), 1)

    def test_front_side_stands_on_the_controller_and_turns_with_it(self):
        self.run_frames()
        pose = self.ring.poses[0]
        controller = self.sim.hands[0]
        up = mu.rotate(controller.aim.orientation, (0.0, 1.0, 0.0))
        forward = mu.rotate(controller.aim.orientation, (0.0, 0.0, -1.0))
        self.assertLess(mu.length(mu.sub(pose.n, up)), 1e-6)         # faces the thumb side of the controller
        self.assertLess(mu.length(mu.sub(pose.v, forward)), 1e-6)    # its top points the way the controller points
        offset = mu.sub(pose.centre, controller.aim.position)
        self.assertAlmostEqual(mu.dot(offset, forward), rg.FORWARD, places=6)
        self.assertAlmostEqual(mu.dot(offset, up), self.ring.radius, places=6)
        # roll the controller a quarter turn about its own axis: the side follows
        roll = mu.quat_multiply(controller.aim.orientation, mu.quat_from_axis_angle((0.0, 0.0, -1.0), math.pi / 2))
        self.sim.set_hand(0, orientation=roll)
        self.run_frames(5)
        pose = self.ring.poses[0]
        self.assertLess(mu.length(mu.sub(pose.n, mu.rotate(roll, (0.0, 1.0, 0.0)))), 1e-6)

    def test_every_side_is_drawn_at_the_same_time(self):
        self.run_frames()
        self.assertEqual(sorted(self.ring.poses), [0, 1, 2])
        normals = [self.ring.poses[i].n for i in range(3)]
        for a in range(3):
            for b in range(a + 1, 3):
                self.assertAlmostEqual(mu.dot(normals[a], normals[b]), math.cos(2 * math.pi / 3), places=6)

    def test_ray_hover_and_activate(self):
        self.run_frames()
        point, n = self.slot_point(5)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual(r.hover, (0, 5))
        self.assertTrue(r.consume_trigger)
        self.assertLess(mu.length(mu.sub(r.ray_end, point)), 1e-6)
        self.assertIsNone(r.activated)
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_frames(1)
        self.assertIsNone(r.activated)           # a press only arms the face
        self.assertTrue(r.consume_trigger)
        r = self.run_frames(1)
        self.assertIsNone(r.activated)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)                   # released over the same face: activated once
        self.assertEqual(r.activated, (0, 5))
        self.assertIsNone(self.run_frames(1).activated)

    def test_ray_beside_the_panel_does_not_hover(self):
        self.run_frames()
        point, n = self.slot_point(0)
        far_left = mu.sub(point, mu.mul(self.ring.poses[0].u, 0.3))
        self.aim_at(far_left, n)
        r = self.run_frames(1)
        self.assertIsNone(r.hover)
        self.assertFalse(r.consume_trigger)

    def test_sides_turned_away_are_drawn_but_cannot_be_pointed_at(self):
        self.run_frames()
        pose = self.ring.poses[1]                # 120 degrees round: its back faces the user
        self.aim_at(pose.centre, pose.n)
        self.assertIsNone(self.run_frames(1).hover)
        self.flick(1.0)                          # turned to the front, the same panel can be pointed at
        point, n = self.slot_point(5, page=1)
        self.aim_at(point, n)
        self.assertEqual(self.run_frames(1).hover, (1, 5))

    def test_hidden_ring_has_no_hover(self):
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))
        self.run_frames()
        self.assertEqual(self.ring.poses, {})
        self.assertIsNone(self.run_frames(1).hover)

    def test_panels_in_one_row_stand_next_to_each_other(self):
        self.ring = rg.PaletteRing([[[0, 1]], [[2]]])
        self.run_frames()
        a, b = self.ring.poses[0], self.ring.poses[1]
        self.assertLess(mu.length(mu.sub(a.n, b.n)), 1e-9)
        gap = mu.sub(b.centre, a.centre)
        self.assertAlmostEqual(mu.dot(gap, a.u), rg.PANEL_W + rg.PANEL_GAP, places=6)
        self.assertAlmostEqual(mu.dot(gap, a.v), 0.0, places=6)
        point, n = self.slot_point(3, page=1)    # a face of the second panel hovers
        self.aim_at(point, n)
        self.assertEqual(self.run_frames(1).hover, (1, 3))

    def test_rows_are_stacked_forward_from_the_bottom(self):
        self.ring = rg.PaletteRing([[[0, 1], [2]]])
        self.run_frames()
        p = [self.ring.poses[i] for i in range(3)]
        self.assertAlmostEqual(mu.dot(mu.sub(p[2].centre, p[0].centre), p[0].v), rg.PANEL_H + rg.PANEL_GAP, places=6)
        self.assertAlmostEqual(mu.dot(mu.sub(p[2].centre, p[0].centre), p[0].u), (rg.PANEL_W + rg.PANEL_GAP) / 2, places=6)
        self.assertEqual((p[0].row, p[1].row, p[2].row), (0, 0, 1))

    def lift(self, page=0):
        point, n = self.title_point(page)
        self.aim_at(point, n)
        self.run_frames(1)
        self.assertEqual(self.ring.hover_title, page)
        self.sim.set_hand(1, trigger=1.0)
        return self.run_frames(1)

    def test_lift_a_panel_and_drop_it_next_to_another(self):
        self.run_frames()
        r = self.lift(0)
        self.assertEqual(self.ring.lifted, 0)
        self.assertTrue(r.consume_trigger)
        self.assertNotIn(0, self.ring.poses)     # the lifted panel leaves its side
        self.flick(1.0)                          # turn the carousel to side 1
        self.assertEqual(self.ring.front_side(), 1)
        point, n = self.panel_point(1, -0.5, 0.0)     # left half of the panel
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual(r.drop_target, (1, 0, 1, False))
        self.assertEqual(r.drop_marker, (1, "left", 1))
        self.assertIsNone(r.dropped)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertEqual(r.dropped, (0, 1, 0, 1, False))
        self.assertIsNone(self.ring.lifted)

    def test_right_half_puts_the_panel_after_and_above_or_below_makes_a_row(self):
        self.ring = rg.PaletteRing([[[0, 1]], [[2]]])
        self.run_frames()
        self.lift(1)
        point, n = self.panel_point(0, 0.5, 0.0)
        self.aim_at(point, n)
        self.assertEqual(self.run_frames(1).drop_target, (0, 0, None, False))    # after panel 0: the end of the row
        point, n = self.panel_point(0, 0.0, 0.8)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual(r.drop_target, (0, 1, None, True))                      # a new row above
        self.assertEqual(r.drop_marker, (0, "above", 0))
        point, n = self.panel_point(0, 0.0, -0.8)
        self.aim_at(point, n)
        self.assertEqual(self.run_frames(1).drop_target, (0, 0, None, True))     # a new row below
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_frames(1).dropped, (1, 0, 0, None, True))

    def test_drop_on_an_empty_side_and_on_nothing_cancels(self):
        self.ring = rg.PaletteRing([[[0, 1]], [[2]]])
        self.run_frames()
        self.lift(1)
        self.assertEqual(sorted(self.ring.ghosts), [2])          # the extra empty side at the end
        self.flick(-1.0)                                         # turn it to the front
        self.assertEqual(self.ring.front_side(), 2)
        ghost = self.ring.ghosts[2]
        self.aim_at(ghost.centre, ghost.n)
        r = self.run_frames(1)
        self.assertEqual(r.drop_target, (2, 0, None, False))
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_frames(1).dropped, (1, 2, 0, None, False))
        # cancel: lift, point at nothing, release
        self.flick(1.0)
        self.run_frames()
        self.lift(0)
        self.sim.set_hand(1, position=(0.3, 1.5, -0.3), point_at=(0.3, 1.5, -2.0))
        self.run_frames(1)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertIsNone(r.dropped)
        self.assertIsNone(self.ring.lifted)

    def test_lifting_offers_a_new_side(self):
        self.ring = rg.PaletteRing([[[0, 1]], [[2]]])
        self.run_frames()
        self.lift(0)
        self.run_frames(2)
        self.assertEqual(len(self.ring.display_sides()), 3)    # the extra, empty side at the end
        self.assertEqual(self.ring.display_sides()[2], [])


    def tip_at(self, point, normal, gap):
        """Put the tool hand so that its tip (tip mode, length 0.1) is `gap` in front of `point`."""
        tip = mu.add(point, mu.mul(normal, gap))
        self.sim.set_hand(1, position=mu.add(tip, mu.mul(normal, 0.1)), point_at=tip)

    def run_tip(self, n=1):
        result = None
        for _ in range(n):
            frame = self.sim.frame(0.02)
            pointers = [pointing.pointer_pose(h.aim, "tip", 0.0, 0.1) for h in frame.hands]
            result = self.ring.update(frame, pointers=pointers)
        return result

    def test_tip_touching_a_face_hovers_and_activates(self):
        self.run_tip(30)
        point, n = self.slot_point(5)
        self.tip_at(point, n, 0.02)
        r = self.run_tip()
        self.assertEqual(r.hover, (0, 5))
        self.assertTrue(r.consume_trigger)
        self.assertLess(mu.length(mu.sub(r.ray_end, point)), 1e-6)       # the tip projected onto the plate
        self.sim.set_hand(1, trigger=1.0)
        self.assertIsNone(self.run_tip().activated)
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_tip().activated, (0, 5))

    def test_tip_far_from_the_panel_does_nothing_and_pushing_through_still_touches(self):
        self.run_tip(30)
        point, n = self.slot_point(5)
        self.tip_at(point, n, 0.08)
        r = self.run_tip()
        self.assertIsNone(r.hover)
        self.assertFalse(r.consume_trigger)
        self.tip_at(point, n, -0.01)
        self.assertEqual(self.run_tip().hover, (0, 5))
        self.tip_at(point, n, -0.04)
        self.assertIsNone(self.run_tip().hover)

    def test_a_tip_beside_the_panel_does_not_touch_it(self):
        self.run_tip(30)
        point, n = self.slot_point(0)
        self.tip_at(mu.sub(point, mu.mul(self.ring.poses[0].u, 0.3)), n, 0.02)
        self.assertIsNone(self.run_tip().hover)

    def test_lifting_and_dropping_with_the_tip(self):
        self.ring = rg.PaletteRing([[[0, 1]], [[2]]])
        self.run_tip(30)
        title, n = self.title_point(0)
        self.tip_at(title, n, 0.02)
        self.run_tip()
        self.sim.set_hand(1, trigger=1.0)
        self.run_tip()
        self.assertEqual(self.ring.lifted, 0)
        point, n = self.panel_point(1, 0.5, 0.0)
        self.tip_at(point, n, 0.02)
        r = self.run_tip()
        self.assertEqual(r.drop_target, (0, 0, None, False))
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_tip().dropped, (0, 0, 0, None, False))


    def slider_setup(self):
        """One panel with a slider in its middle row (face ids are irrelevant to the ring)."""
        self.ring = rg.PaletteRing([[[0]], [[1]], [[2]]])
        self.ring.slider_rows = {0: {1: "pointer.angle"}}
        self.run_frames(30)

    def slider_point(self, along):
        pose = self.ring.poses[0]
        x = -rg.GRID_W / 2 + rg.SLIDER_PAD + along * (rg.GRID_W - 2 * rg.SLIDER_PAD)
        return mu.add(pose.centre, mu.add(mu.mul(pose.u, x), mu.mul(pose.v, rg.GRID_Y))), pose.n     # the middle row is at grid y 0

    def test_a_slider_row_hovers_as_one_and_dragging_follows_the_ray(self):
        self.slider_setup()
        point, n = self.slider_point(0.25)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual(r.hover, (0, 4))                       # the first slot of the row, wherever on the row it is hit
        self.assertTrue(r.consume_trigger)
        self.assertIsNone(r.slider)
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_frames(1)
        self.assertAlmostEqual(r.slider[2], 0.25, places=4)
        self.assertEqual(r.slider[:2], (0, 4))
        point, n = self.slider_point(0.8)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertAlmostEqual(r.slider[2], 0.8, places=4)
        self.assertTrue(r.consume_trigger)
        far = mu.add(point, mu.mul(self.ring.poses[0].u, 0.5))   # beyond the end of the panel: clamped, the drag continues
        self.aim_at(far, n)
        self.assertEqual(self.run_frames(1).slider[2], 1.0)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertEqual(r.slider_done, (0, 4))
        self.assertIsNone(r.slider)
        self.assertIsNone(self.ring.slider_drag)

    def test_a_slider_is_dragged_with_the_tip_too(self):
        self.slider_setup()
        point, n = self.slider_point(0.5)
        self.tip_at(point, n, 0.02)
        self.run_tip()
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_tip()
        self.assertAlmostEqual(r.slider[2], 0.5, places=4)
        point, n = self.slider_point(0.1)
        self.tip_at(point, n, 0.1)          # the tip may leave the plate while dragging: it is projected onto it
        self.assertAlmostEqual(self.run_tip().slider[2], 0.1, places=4)
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_tip().slider_done, (0, 4))

    def test_a_readout_row_is_one_face_over_the_whole_row_and_is_never_dragged(self):
        self.ring = rg.PaletteRing([[[0]], [[1]], [[2]]])
        self.ring.readout_rows = {0: {0: "val.readout"}}
        self.run_frames(30)
        pose = self.ring.poses[0]
        top = rg.GRID_Y + (rg.CELL + rg.GAP)                                      # the middle of the first row
        for x in (-0.06, 0.0, 0.06):                                              # over the first slot and over the last
            point = mu.add(pose.centre, mu.add(mu.mul(pose.u, x), mu.mul(pose.v, top)))
            self.aim_at(point, pose.n)
            r = self.run_frames(1)
            self.assertEqual(r.hover, (0, 0), x)                                  # the first slot of the row, wherever it is hit
            self.assertIsNone(r.slider)
        self.assertEqual(self.ring.slot_centre(0, 0)[0], mu.add(pose.centre, mu.mul(pose.v, top)))   # centred on the panel
        self.sim.set_hand(1, trigger=1.0)
        self.run_frames(1)
        self.assertIsNone(self.ring.slider_drag)
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_frames(1).activated, (0, 0))                    # a tap presses it like a button

    def bar_setup(self):
        self.slider_setup()

    def row_point(self, along, dy):
        """A point on the middle row of the slider panel: `dy` metres from the centre of the row, y up (the bar is at -0.013)."""
        point, n = self.slider_point(along)
        return mu.add(point, mu.mul(self.ring.poses[0].v, dy)), n

    def test_a_slider_is_focused_by_a_tip_that_comes_close_without_touching(self):
        self.bar_setup()
        point, n = self.row_point(0.5, -0.013)
        self.tip_at(point, n, 0.08)
        r = self.run_tip()
        self.assertEqual(r.focus, (0, 4))
        self.assertIsNone(r.hover)                                   # not touching: nothing is pressed here
        self.assertIsNone(r.bar_hover)
        self.assertFalse(r.consume_trigger)
        self.tip_at(point, n, 0.2)
        self.assertIsNone(self.run_tip().focus)                      # too far
        far, n = self.row_point(5.0, -0.013)                         # beside the panel
        self.tip_at(far, n, 0.08)
        self.assertIsNone(self.run_tip().focus)

    def test_the_tip_touching_the_bar_presses_it_and_the_touch_of_the_label_does_not(self):
        self.bar_setup()
        label, n = self.row_point(0.5, 0.015)
        self.tip_at(label, n, 0.02)
        r = self.run_tip()
        self.assertEqual((r.focus, r.hover, r.bar_hover), ((0, 4), (0, 4), None))
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_tip()
        self.assertIsNone(r.slider)
        self.assertIsNone(self.ring.slider_drag)
        self.assertTrue(r.consume_trigger)
        self.sim.set_hand(1, trigger=0.0)
        self.run_tip()
        bar, n = self.row_point(0.3, -0.013)
        self.tip_at(bar, n, 0.02)
        r = self.run_tip()
        self.assertEqual(r.bar_hover, (0, 4))
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_tip()
        self.assertAlmostEqual(r.slider[2], 0.3, places=4)
        self.assertEqual(r.focus, (0, 4))
        label, n = self.row_point(0.9, 0.015)                        # once dragging, the pointer may wander off the bar
        self.tip_at(label, n, 0.1)
        r = self.run_tip()
        self.assertAlmostEqual(r.slider[2], 0.9, places=4)
        self.assertEqual((r.focus, r.bar_hover), ((0, 4), (0, 4)))
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_tip().slider_done, (0, 4))

    def test_the_laser_over_a_bar_slider_focuses_it_and_presses_on_the_bar_only(self):
        self.bar_setup()
        label, n = self.row_point(0.4, 0.015)
        self.aim_at(label, n)
        r = self.run_frames(1)
        self.assertEqual((r.focus, r.hover, r.bar_hover), ((0, 4), (0, 4), None))
        self.sim.set_hand(1, trigger=1.0)
        self.assertIsNone(self.run_frames(1).slider)
        self.sim.set_hand(1, trigger=0.0)
        self.run_frames(1)
        bar, n = self.row_point(0.4, -0.013)
        self.aim_at(bar, n)
        self.assertEqual(self.run_frames(1).bar_hover, (0, 4))
        self.sim.set_hand(1, trigger=1.0)
        self.assertAlmostEqual(self.run_frames(1).slider[2], 0.4, places=4)

    def test_pages_from_the_fixed_index_are_not_lifted_and_not_dropped_on(self):
        self.ring.fixed_from = 1
        self.run_tip(30)
        title, n = self.title_point(1)
        self.tip_at(title, n, 0.02)
        self.run_tip()
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_tip()
        self.assertIsNone(self.ring.lifted)
        self.sim.set_hand(1, trigger=0.0)
        self.run_tip()
        title, n = self.title_point(0)                               # a page below the index is lifted as usual
        self.tip_at(title, n, 0.02)
        self.run_tip()
        self.sim.set_hand(1, trigger=1.0)
        self.run_tip()
        self.assertEqual(self.ring.lifted, 0)
        point, n = self.panel_point(1, 0.5, 0.0)
        self.tip_at(point, n, 0.02)
        r = self.run_tip()
        self.assertIsNone(r.drop_target)                             # over a fixed page: nowhere to drop
        self.assertIsNone(r.drop_marker)

    def test_the_other_rows_of_a_slider_panel_still_hold_faces(self):
        self.slider_setup()
        point, n = self.slot_point(0)
        self.aim_at(point, n)
        self.assertEqual(self.run_frames(1).hover, (0, 0))
        self.sim.set_hand(1, trigger=1.0)
        self.run_frames(1)
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_frames(1).activated, (0, 0))

    def press_face(self, slot, page=0):
        point, n = self.slot_point(slot, page)
        self.aim_at(point, n)
        self.run_frames(1)
        self.sim.set_hand(1, trigger=1.0)
        return self.run_frames(1)

    def test_a_long_hold_on_a_face_lifts_it_instead_of_activating_it(self):
        self.run_frames()
        self.press_face(5)
        r = self.run_frames(int(rg.HOLD_LIFT / 0.02) + 3)
        self.assertEqual(self.ring.lifted_face, (0, 5))
        self.assertEqual(r.lifted_face, (0, 5))
        self.assertTrue(r.consume_trigger)
        self.assertIsNotNone(r.lift_point)
        self.assertEqual(len(self.ring.display_sides()), len(SIDES))           # no extra side: every panel shows a hide slot
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)                   # released over its own slot: nothing happens
        self.assertIsNone(r.activated)
        self.assertIsNone(r.face_dropped)
        self.assertIsNone(self.ring.lifted_face)

    def test_leaving_the_face_while_pressed_cancels_the_press(self):
        self.run_frames()
        self.press_face(5)
        point, n = self.slot_point(6)
        self.aim_at(point, n)
        self.run_frames(2)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertIsNone(r.activated)
        self.assertIsNone(self.ring.press)
        point, n = self.slot_point(5)            # coming back and releasing does not activate either
        self.aim_at(point, n)
        self.press_face(5)
        point, n = self.slot_point(6)
        self.aim_at(point, n)
        self.run_frames(1)
        point, n = self.slot_point(5)
        self.aim_at(point, n)
        self.run_frames(1)
        self.sim.set_hand(1, trigger=0.0)
        self.assertIsNone(self.run_frames(1).activated)

    def test_a_lifted_face_is_dropped_on_another_slot(self):
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        point, n = self.slot_point(6)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual(r.face_target, (0, 6))
        self.assertFalse(r.face_hide)
        self.assertIsNone(r.hover)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertEqual(r.face_dropped, (0, 5, 0, 6))

    def test_slots_the_host_refuses_are_no_drop_target(self):
        self.ring.can_drop = lambda src, dst: dst != (0, 6)
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        point, n = self.slot_point(6)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertIsNone(r.face_target)
        self.sim.set_hand(1, trigger=0.0)
        self.assertIsNone(self.run_frames(1).face_dropped)

    def test_a_slot_the_host_says_is_empty_cannot_be_lifted(self):
        self.ring.can_lift = lambda page, slot: slot != 5
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        self.assertIsNone(self.ring.lifted_face)
        self.sim.set_hand(1, trigger=0.0)
        self.assertIsNone(self.run_frames(1).activated)                       # a long press is not a tap

    def hide_slot_point(self, page=0):
        pose = self.ring.poses[page]
        x = (rg.HIDE_X[0] + rg.HIDE_X[1]) / 2
        y = (rg.TITLE_Y[0] + rg.TITLE_Y[1]) / 2
        return mu.add(pose.centre, mu.add(mu.mul(pose.u, x), mu.mul(pose.v, y))), pose.n

    def test_a_lifted_face_dropped_on_the_hide_slot_of_a_panel_is_hidden(self):
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        self.assertEqual(sorted(self.ring.ghosts), [])                         # a face has no empty side to go to
        point, n = self.hide_slot_point()
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertTrue(r.face_hide)
        self.assertEqual(r.hide_page, 0)
        self.assertIsNone(r.face_target)
        self.assertIsNone(r.hover)
        self.sim.set_hand(1, trigger=0.0)
        self.assertEqual(self.run_frames(1).face_dropped, (0, 5, None, None))

    def test_the_hide_slot_of_another_panel_hides_too_and_its_title_is_still_a_title_elsewhere(self):
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        self.flick(1.0)                                                        # another side to the front
        front = self.ring.front_side()
        point, n = self.hide_slot_point(front)
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual((r.face_hide, r.hide_page), (True, front))
        point, n = self.title_point(front)                                     # the middle of the title bar is no hide slot
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual((r.face_hide, r.hide_page), (False, None))
        self.sim.set_hand(1, trigger=0.0)
        self.assertIsNone(self.run_frames(1).face_dropped)

    def menu_point(self, page=0):
        pose = self.ring.poses[page]
        x = (rg.MENU_X + rg.GRID_W / 2) / 2
        y = (rg.TITLE_Y[0] + rg.TITLE_Y[1]) / 2
        return mu.add(pose.centre, mu.add(mu.mul(pose.u, x), mu.mul(pose.v, y))), pose.n

    def test_the_menu_mark_at_the_end_of_the_title_bar_is_hovered_and_a_tap_on_it_asks_for_the_editor(self):
        self.run_frames()
        point, n = self.menu_point()
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual((r.menu_hover, r.hover_title, r.menu), (0, None, None))
        self.sim.set_hand(1, trigger=1.0)
        r = self.run_frames(1)
        self.assertTrue(r.consume_trigger)
        self.assertIsNone(self.ring.lifted)                                           # a press on the mark does not lift the panel
        self.assertIsNone(r.menu)                                                     # it is the tap that asks
        r = self.run_frames(3)
        self.assertIsNone(r.menu)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertEqual(r.menu, 0)
        self.assertIsNone(self.run_frames(1).menu)

    def test_a_press_on_the_menu_mark_that_leaves_it_asks_for_nothing_and_the_rest_of_the_title_still_lifts(self):
        self.run_frames()
        point, n = self.menu_point()
        self.aim_at(point, n)
        self.run_frames(1)
        self.sim.set_hand(1, trigger=1.0)
        self.run_frames(2)
        point, n = self.slot_point(5)
        self.aim_at(point, n)
        self.run_frames(2)
        self.sim.set_hand(1, trigger=0.0)
        self.assertIsNone(self.run_frames(1).menu)
        self.run_frames(2)
        point, n = self.title_point(0)
        self.aim_at(point, n)
        self.run_frames(1)
        self.sim.set_hand(1, trigger=1.0)
        self.run_frames(1)
        self.assertEqual(self.ring.lifted, 0)

    def test_the_menu_mark_is_no_menu_while_a_panel_or_a_face_is_lifted(self):
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        point, n = self.menu_point()
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual((r.menu_hover, r.face_hide), (None, False))
        self.sim.set_hand(1, trigger=0.0)
        self.run_frames(2)
        point, n = self.title_point(0)
        self.aim_at(point, n)
        self.run_frames(1)
        self.sim.set_hand(1, trigger=1.0)
        self.run_frames(1)
        self.assertEqual(self.ring.lifted, 0)
        point, n = self.menu_point(1)
        self.aim_at(point, n)
        self.assertIsNone(self.run_frames(1).menu_hover)

    def test_without_a_lifted_face_the_place_of_the_hide_slot_is_part_of_the_title_bar(self):
        self.run_frames()
        point, n = self.hide_slot_point()
        self.aim_at(point, n)
        r = self.run_frames(1)
        self.assertEqual((r.hover_title, r.face_hide, r.hide_page), (0, False, None))

    def test_releasing_a_lifted_face_over_nothing_cancels(self):
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        self.sim.set_hand(1, position=(0.3, 1.5, -0.3), point_at=(0.3, 1.5, -2.0))
        self.run_frames(2)
        self.sim.set_hand(1, trigger=0.0)
        r = self.run_frames(1)
        self.assertIsNone(r.face_dropped)
        self.assertIsNone(self.ring.lifted_face)

    def test_the_carousel_stays_while_a_face_is_lifted_without_looking_at_it(self):
        self.run_frames()
        self.press_face(5)
        self.run_frames(25)
        self.sim.set_head(look_at_point=(0.0, 1.6, 2.0))
        self.assertTrue(self.run_frames(10).visible)
        self.assertEqual(self.ring.lifted_face, (0, 5))


class LayoutTest(unittest.TestCase):
    def make(self):
        return lay.Layout([lay.Page("Tools", ["a", "b", None]), lay.Page("View", ["c"])])

    def three(self):
        return lay.Layout([lay.Page("A"), lay.Page("B"), lay.Page("C")])

    def names(self, layout):
        return [p.name for p in layout.pages]

    def test_json_roundtrip_and_padding(self):
        layout = lay.Layout.from_json(self.make().to_json())
        self.assertEqual(self.names(layout), ["Tools", "View"])
        self.assertEqual(len(layout.pages[0].slots), lay.SLOTS)
        self.assertEqual(layout.face_at(0, 1), "b")
        self.assertIsNone(layout.face_at(1, 5))

    def test_sides_and_rows_survive_the_roundtrip_and_old_files_get_a_side_per_page(self):
        layout = self.three()
        layout.move_page(2, 0, 0, None, True)        # C as a row above A
        again = lay.Layout.from_json(layout.to_json())
        self.assertEqual(again.sides(), layout.sides())
        old = json.dumps({"version": 1, "pages": [{"name": "A", "slots": []}, {"name": "B", "slots": []}]})
        self.assertEqual(lay.Layout.from_json(old).sides(), [[[0]], [[1]]])
        stacked = json.dumps({"version": 2, "pages": [{"name": "A", "side": 0}, {"name": "B", "side": 0}]})
        self.assertEqual(lay.Layout.from_json(stacked).sides(), [[[0, 1]]])      # one row

    def test_unknown_faces_become_empty(self):
        layout = lay.Layout.from_json(self.make().to_json(), known_faces={"a", "c"})
        self.assertEqual((layout.face_at(0, 0), layout.face_at(0, 1)), ("a", None))

    def test_swap_and_remove(self):
        layout = self.make()
        layout.swap(0, 0, 1, 0)
        self.assertEqual((layout.face_at(0, 0), layout.face_at(1, 0)), ("c", "a"))
        layout.remove(0, 0)
        self.assertIsNone(layout.face_at(0, 0))

    def test_every_page_starts_on_its_own_side(self):
        self.assertEqual(self.three().sides(), [[[0]], [[1]], [[2]]])

    def test_without_page(self):
        sides = [[[0, 1], [2]], [[3]]]
        self.assertEqual(lay.without_page(sides, 1), [[[0], [2]], [[3]]])
        self.assertEqual(lay.without_page(sides, 2), [[[0, 1]], [[3]]])      # the empty row is gone
        self.assertEqual(lay.without_page(sides, 3), [[[0, 1], [2]], []])    # the empty side stays

    def test_move_page_next_to_another(self):
        layout = self.three()
        layout.move_page(2, 0)                       # C joins the row of A, after it
        self.assertEqual(self.names(layout), ["A", "C", "B"])
        self.assertEqual(layout.sides(), [[[0, 1]], [[2]]])
        layout.move_page(2, 0, 0, 0)                 # B in front of A
        self.assertEqual(self.names(layout), ["B", "A", "C"])
        self.assertEqual(layout.sides(), [[[0, 1, 2]]])

    def test_move_page_above_and_below(self):
        layout = self.three()
        layout.move_page(1, 0, 1, None, True)        # B in a new row above A
        self.assertEqual(self.names(layout), ["A", "B", "C"])
        self.assertEqual(layout.sides(), [[[0], [1]], [[2]]])
        layout.move_page(2, 0, 0, None, True)        # C in a new row below A and B
        self.assertEqual(self.names(layout), ["C", "A", "B"])
        self.assertEqual(layout.sides(), [[[0], [1], [2]]])
        self.assertEqual([p.row for p in layout.pages], [0, 1, 2])
        layout.move_page(0, 0, 3, None, True)        # C to the top (the page is removed first: three rows remain, so row 2)
        self.assertEqual(self.names(layout), ["A", "B", "C"])

    def test_move_page_to_a_new_side_and_empty_sides_vanish(self):
        layout = self.three()
        layout.move_page(0, 3)                       # a new side at the end
        self.assertEqual(self.names(layout), ["B", "C", "A"])
        self.assertEqual(layout.sides(), [[[0]], [[1]], [[2]]])
        layout = self.three()
        layout.move_page(1, 0)
        self.assertEqual(layout.sides(), [[[0, 1]], [[2]]])
        layout.move_page(0, 2)                       # A leaves for a new side, B stays alone on the first
        self.assertEqual(self.names(layout), ["B", "C", "A"])
        self.assertEqual(layout.sides(), [[[0]], [[1]], [[2]]])

    def test_faces_added_since_a_layout_was_saved_are_placed(self):
        default = lay.Layout([lay.Page("Tools", ["a", "b"]), lay.Page("Session", ["x", "y", "z"])])
        saved = lay.Layout([lay.Page("Tools", ["a"]), lay.Page("Session", ["x"])])
        self.assertTrue(saved.add_missing(default))
        self.assertEqual(saved.pages[0].slots[:2], ["a", "b"])               # b joins the page named Tools
        self.assertEqual(saved.pages[1].slots[:3], ["x", "y", "z"])
        self.assertFalse(saved.add_missing(default))                         # nothing left to add
        renamed = lay.Layout([lay.Page("Mine", ["a", "x"])])
        self.assertTrue(renamed.add_missing(default))                        # no page of that name: the first page with room
        self.assertEqual(renamed.pages[0].slots[:5], ["a", "x", "b", "y", "z"])

    def test_a_slider_goes_to_a_free_row(self):
        default = lay.Layout([lay.Page("Session", ["m", "c", None, None, "angle", None, None, None, "length"])])
        saved = lay.Layout([lay.Page("Session", ["m", "c", "old"])])
        self.assertTrue(saved.add_missing(default, wide={"angle", "length"}))
        self.assertEqual(saved.pages[0].slots[4], "angle")                    # row 1 is free
        self.assertEqual(saved.pages[0].slots[8], "length")                   # row 2 is free
        crowded = lay.Layout([lay.Page("Session", ["m", "c", "x", "y", "z", "u", "v", "w", "q", "r", "s", "t"])])
        self.assertFalse(crowded.add_missing(default, wide={"angle", "length"}))   # no free row: nothing is squeezed in

    def test_a_face_moves_to_a_free_slot_or_changes_places(self):
        layout = lay.Layout([lay.Page("A", ["a", "b"]), lay.Page("B", ["c"])])
        self.assertTrue(layout.move_face(0, 0, 1, 5))
        self.assertEqual((layout.face_at(0, 0), layout.face_at(1, 5)), (None, "a"))
        self.assertTrue(layout.move_face(1, 5, 0, 1))                          # onto an occupied slot: swap
        self.assertEqual((layout.face_at(0, 1), layout.face_at(1, 5)), ("a", "b"))
        self.assertFalse(layout.move_face(0, 1, 0, 1))                         # onto itself
        self.assertFalse(layout.move_face(0, 7, 1, 2))                         # an empty slot has no face to move

    def test_sliders_are_not_lifted_and_their_rows_take_no_faces(self):
        layout = lay.Layout([lay.Page("A", ["a", "b", None, None, "s"])])
        wide = {"s"}
        self.assertFalse(layout.can_move_face(0, 4, 0, 8, wide))               # a slider is dragged, not lifted
        self.assertFalse(layout.can_move_face(0, 0, 0, 6, wide))               # a slot in a slider row
        self.assertFalse(layout.can_move_face(0, 0, 0, 4, wide))
        self.assertTrue(layout.can_move_face(0, 0, 0, 9, wide))
        self.assertFalse(layout.hide_face(0, 4, wide))

    def test_hidden_faces_stay_out_of_the_panels_and_come_back_on_request(self):
        default = lay.Layout([lay.Page("Tools", ["a", "b"]), lay.Page("Session", ["x"])])
        layout = lay.Layout([lay.Page("Tools", ["a", "b"]), lay.Page("Session", ["x"])])
        self.assertTrue(layout.hide_face(0, 1))
        self.assertEqual((layout.face_at(0, 1), layout.hidden), (None, ["b"]))
        self.assertFalse(layout.hide_face(0, 1))                               # nothing left in that slot
        self.assertFalse(layout.add_missing(default))                          # hidden is not missing
        again = lay.Layout.from_json(layout.to_json())
        self.assertEqual(again.hidden, ["b"])
        self.assertFalse(again.add_missing(default))
        self.assertEqual(lay.Layout.from_json(layout.to_json(), known_faces={"a", "x"}).hidden, [])
        self.assertTrue(again.show_hidden(default))
        self.assertEqual((again.pages[0].slots[:2], again.hidden), (["a", "b"], []))
        self.assertFalse(again.show_hidden(default))

    def test_hidden_faces_without_room_stay_hidden(self):
        default = lay.Layout([lay.Page("A", ["a"])])
        layout = lay.Layout([lay.Page("A", ["f%d" % i for i in range(lay.SLOTS)])], hidden=["a"])
        self.assertFalse(layout.show_hidden(default))
        self.assertEqual(layout.hidden, ["a"])

    def test_slider_specs_quantize_and_clamp(self):
        angle = defaults.SLIDERS["pointer.angle"]
        self.assertEqual(angle.value(0.0), -30.0)
        self.assertEqual(angle.value(1.0), 60.0)
        self.assertEqual(angle.value(0.5), 15.0)
        self.assertEqual(angle.value(0.5123), 16.0)                           # whole degrees
        self.assertEqual(angle.value(-3.0), -30.0)
        self.assertAlmostEqual(angle.fraction(15.0), 0.5)
        length = defaults.SLIDERS["pointer.length"]
        self.assertEqual(length.value(0.2), 0.04)
        self.assertEqual(length.value(0.21), 0.04)                             # 5 mm steps: 0.042 rounds to 0.040
        self.assertEqual(length.value(0.23), 0.045)
        self.assertAlmostEqual(length.fraction(0.04), 0.2)

    def test_move_page_back_onto_its_own_empty_side_changes_nothing(self):
        layout = self.three()
        layout.move_page(1, 1)
        self.assertEqual(self.names(layout), ["A", "B", "C"])
        self.assertEqual(layout.sides(), [[[0]], [[1]], [[2]]])

    def test_load_falls_back_to_the_default(self):
        default = self.make()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "layout.json")
            self.assertIs(lay.load_layout(default, {"a"}, path), default)         # missing file
            with open(path, "w") as f:
                f.write("not json")
            self.assertIs(lay.load_layout(default, {"a"}, path), default)         # broken file
            lay.save_layout(default, path)
            self.assertEqual(lay.load_layout(None, {"a", "b", "c"}, path).face_at(0, 1), "b")
            with open(path, "w") as f:
                f.write(json.dumps({"pages": []}))
            self.assertIs(lay.load_layout(default, {"a"}, path), default)         # no pages

    def test_wrap_label(self):
        self.assertEqual(lay.wrap_label("Teleport"), ["Teleport"])
        self.assertEqual(lay.wrap_label("Working plane"), ["Working", "plane"])
        self.assertEqual(lay.wrap_label("Extraordinarily"), ["Extraordinarily"])
        self.assertEqual(lay.wrap_label("Reset view now"), ["Reset", "view now"])
        self.assertEqual(lay.wrap_label(""), [""])


if __name__ == "__main__":
    unittest.main()
