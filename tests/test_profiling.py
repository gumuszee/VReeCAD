import os
import tempfile
import unittest

import support  # noqa: F401
from freecad.VReeCAD import profiling


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class ProfilerTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        profiling._clock, self._real = self.clock, profiling._clock
        self.addCleanup(setattr, profiling, "_clock", self._real)
        self.out = []
        profiling.print = self.out.append
        self.addCleanup(delattr, profiling, "print")
        self.prof = profiling.FrameProfiler()

    def frame(self, shown, **laps):
        self.prof.frame()
        for name, ms in laps.items():
            self.clock.now += ms / 1000.0
            self.prof.lap(name)
        self.prof.note_shown(shown)

    def test_it_costs_nothing_while_it_is_off(self):
        self.frame(True, ui=3.0)
        self.prof.frame()
        self.assertEqual(self.prof.summary(), {})
        self.assertEqual(self.out, [])

    def test_the_laps_of_the_frames_are_averaged_apart_for_shown_and_hidden(self):
        self.prof.start(interval=1000.0)
        for _ in range(3):
            self.frame(True, ui=2.0, render=6.0)
        for _ in range(2):
            self.frame(False, ui=1.0, render=4.0)
        self.prof.frame()                                        # closes the last frame
        summary = self.prof.summary()
        self.assertEqual(summary[True]["frames"], 3)
        self.assertAlmostEqual(summary[True]["laps"]["ui"], 2.0)
        self.assertAlmostEqual(summary[True]["laps"]["render"], 6.0)
        self.assertAlmostEqual(summary[True]["period_ms"], 8.0)
        self.assertEqual(summary[False]["frames"], 2)
        self.assertAlmostEqual(summary[False]["laps"]["render"], 4.0)

    def test_a_lap_that_is_taken_twice_in_a_frame_adds_up(self):
        self.prof.start(interval=1000.0)
        self.frame(False, ui=1.0)
        self.clock.now += 0.002
        self.prof.lap("ui")
        self.prof.frame()
        self.assertAlmostEqual(self.prof.summary()[False]["laps"]["ui"], 3.0)

    def test_a_summary_line_is_printed_every_interval_and_names_the_laps(self):
        self.prof.start(interval=0.05)
        for _ in range(8):
            self.frame(True, ui=10.0)
        self.prof.frame()
        lines = [line for line in self.out if "carousel shown" in line]
        self.assertTrue(lines)
        self.assertIn("ui 10.00", lines[0])
        self.assertIn("fps", lines[0])

    def test_the_rows_of_every_frame_are_written_to_the_file_when_it_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "frames.csv")
            self.prof.start(interval=1000.0, path=path)
            self.frame(True, ui=2.0)
            self.frame(False, ui=1.0, render=3.0)
            self.prof.frame()
            self.prof.stop()
            with open(path, encoding="utf-8") as file:
                rows = file.read().splitlines()
        self.assertEqual(rows[0], "shown,period_ms,ui_ms,render_ms")
        self.assertEqual(rows[1], "1,2.000,2.000,0.000")
        self.assertEqual(rows[2], "0,4.000,1.000,3.000")

    def test_stopping_prints_what_is_left_and_turns_it_off(self):
        self.prof.start(interval=1000.0)
        self.frame(True, ui=2.0)
        self.prof.frame()
        self.prof.stop()
        self.assertFalse(self.prof.on)
        self.assertTrue(any("carousel shown" in line for line in self.out))


if __name__ == "__main__":
    unittest.main()
