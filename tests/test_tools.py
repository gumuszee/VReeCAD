import unittest

import support  # noqa: F401
from freecad.VReeCAD.tools import base, manager, registry


class TickLimitTest(unittest.TestCase):
    def setUp(self):
        self.sent, self.t = [], [0.0]
        self.haptic = base.tick_limited(lambda *args: self.sent.append(args), interval=0.15, now=lambda: self.t[0])

    def test_ticks_of_a_hand_come_at_most_every_interval(self):
        for i in range(10):                                 # a tick every 20 ms for 200 ms
            self.t[0] = 0.02 * i
            self.haptic(0, 0.08, 0.008)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0], (0, 0.08, 0.008))

    def test_each_hand_has_its_own_interval(self):
        self.haptic(0, 0.08, 0.008)
        self.haptic(1, 0.08, 0.008)
        self.assertEqual([s[0] for s in self.sent], [0, 1])

    def test_a_strong_pulse_always_goes_through(self):
        self.haptic(0, 0.08, 0.008)
        self.haptic(0, 0.3, 0.02)
        self.haptic(0, 0.5, 0.04)
        self.assertEqual([s[1] for s in self.sent], [0.08, 0.3, 0.5])


class Recorder(base.Tool):
    name = "test_recorder"
    label = "Recorder"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.log = []

    def activate(self):
        self.log.append("activate")

    def deactivate(self):
        self.log.append("deactivate")

    def update(self, frame):
        self.log.append(("update", frame))


class Other(base.Tool):
    name = "test_other"
    label = "Other"


class ToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        registry.register(Recorder)
        registry.register(Other)

    @classmethod
    def tearDownClass(cls):
        registry.unregister("test_recorder")
        registry.unregister("test_other")

    def test_registry(self):
        self.assertIn("test_recorder", registry.names())
        self.assertEqual(registry.label_of("test_recorder"), "Recorder")
        with self.assertRaises(ValueError):
            registry.register(type("Dup", (base.Tool,), {"name": "test_recorder"}))

    def test_manager_lifecycle(self):
        mgr = manager.ToolManager(base.ToolContext())
        rec = mgr.activate("test_recorder")
        mgr.update("f1")
        mgr.activate("test_recorder")   # no-op when already active
        mgr.activate("test_other")
        mgr.update("f2")                # goes to the other tool, not the recorder
        self.assertEqual(rec.log, ["activate", ("update", "f1"), "deactivate"])
        self.assertEqual(mgr.active_name, "test_other")

    def test_unknown_tool(self):
        with self.assertRaises(KeyError):
            manager.ToolManager(base.ToolContext()).activate("does_not_exist")

    def test_context_off_hand(self):
        self.assertEqual(base.ToolContext(dominant=1).off_hand, 0)


if __name__ == "__main__":
    unittest.main()
