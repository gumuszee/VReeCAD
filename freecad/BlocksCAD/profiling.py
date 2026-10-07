# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""A frame profiler for the XR loop and the user interface (docs/toolbox.md, `xr_profile.py`). Off by default: while it is off every
call is one attribute test. While it is on, each frame is cut into named laps (`lap("ui")` charges the time since the previous lap
to "ui"), the frames are sorted by whether the carousel is shown (`note_shown`), and every `interval` seconds one summary per
class of frames goes to the Report view: frames per second, the mean and the worst frame period, and the mean milliseconds of each
lap. With a path the same numbers go to a CSV file, one row per frame, written when the profiler stops.

    from freecad.BlocksCAD import profiling
    profiling.PROFILER.start(interval=3.0, path="frames.csv")   # ... wear the headset ... then
    profiling.PROFILER.stop()

The laps are laid out by the host (`commonXR.update_render`, `ui.controller.UiController.update`); the names are free. A lap that is
given before the first `frame()` is dropped."""

import time

_clock = time.perf_counter


class FrameProfiler:
    def __init__(self):
        self.on = False
        self.interval = 3.0
        self.sync_gpu = True              # read by the host: finish the GPU work of an eye before taking its lap
        self.path = None
        self._rows = []
        self._reset()

    def _reset(self):
        self._last = None                 # time of the previous lap
        self._frame_start = None
        self._shown = False
        self._laps = {}                   # lap name -> seconds in the frame being measured
        self._order = []                  # lap names in the order they were first seen
        self._classes = {True: _Stats(), False: _Stats()}
        self._since_report = _clock()

    def start(self, interval=3.0, path=None, sync_gpu=True):
        """Begin to measure. `path`: a CSV file that gets one row per frame (overwritten). `sync_gpu`: the host waits for the GPU at the
        end of each eye, so the laps of the eyes include the GPU time (it also costs some frame rate while measuring)."""
        self.stop()
        self.interval, self.sync_gpu, self.path = interval, sync_gpu, path
        self._reset()
        self._rows = []
        self.on = True
        print(f"BlocksCAD profiler: on, a summary every {interval:g} s" + (f", rows in {path}" if path else ""))

    def stop(self):
        """Stop measuring; the summary of the frames since the last one is printed."""
        if not self.on:
            return
        self.on = False
        self._report()
        if self.path:
            with open(self.path, "w", encoding="utf-8", newline="\n") as file:
                file.write("shown,period_ms," + ",".join(f"{name}_ms" for name in self._order) + "\n")
                for shown, period, laps in self._rows:
                    file.write(f"{int(shown)},{period * 1000:.3f}," + ",".join(f"{laps.get(name, 0.0) * 1000:.3f}" for name in self._order) + "\n")
        self._rows = []
        print("BlocksCAD profiler: off")

    def frame(self):
        """The start of a frame: closes the previous one."""
        if not self.on:
            return
        now = _clock()
        if self._frame_start is not None:
            self._close_frame(now)
        self._frame_start = self._last = now
        self._laps = {}

    def lap(self, name):
        """Charge the time since the previous lap (or the start of the frame) to `name`."""
        if not self.on or self._last is None:
            return
        now = _clock()
        self._laps[name] = self._laps.get(name, 0.0) + now - self._last
        self._last = now

    def note_shown(self, shown):
        """Whether the carousel is shown in this frame: the frames are summed up apart for the two cases."""
        self._shown = bool(shown)

    def _close_frame(self, now):
        period = now - self._frame_start
        for name in self._laps:
            if name not in self._order:
                self._order.append(name)
        self._classes[self._shown].add(period, self._laps)
        if self.path:
            self._rows.append((self._shown, period, self._laps))
        if now - self._since_report >= self.interval:
            self._report()
            self._since_report = now

    def _report(self):
        for shown, stats in self._classes.items():
            if stats.count:
                print(stats.line("carousel shown" if shown else "carousel hidden", self._order))
        self._classes = {True: _Stats(), False: _Stats()}

    def summary(self):
        """The numbers gathered since the last report as {shown: {"frames", "period_ms", "worst_ms", "laps": {name: ms}}}; resets nothing."""
        return {shown: stats.as_dict() for shown, stats in self._classes.items() if stats.count}


class _Stats:
    def __init__(self):
        self.count = 0
        self.total = 0.0
        self.worst = 0.0
        self.periods = []
        self.laps = {}

    def add(self, period, laps):
        self.count += 1
        self.total += period
        self.worst = max(self.worst, period)
        self.periods.append(period)
        for name, seconds in laps.items():
            self.laps[name] = self.laps.get(name, 0.0) + seconds

    def as_dict(self):
        return {"frames": self.count, "period_ms": self.total * 1000.0 / self.count, "worst_ms": self.worst * 1000.0,
                "laps": {name: seconds * 1000.0 / self.count for name, seconds in self.laps.items()}}

    def line(self, title, order):
        mean = self.total / self.count
        ordered = sorted(self.periods)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        laps = " ".join(f"{name} {self.laps[name] * 1000.0 / self.count:.2f}" for name in order if name in self.laps)
        return (f"BlocksCAD profiler, {title}: {self.count} frames, {1.0 / mean:.0f} fps, period mean {mean * 1000:.2f} ms "
                f"p95 {p95 * 1000:.2f} ms worst {self.worst * 1000:.2f} ms | ms per frame: {laps}")


PROFILER = FrameProfiler()
