import unittest

import support  # noqa: F401
from freecad.BlocksCAD.core import units as un


class UnitsTest(unittest.TestCase):
    def test_system_from_the_document_unit_system(self):
        self.assertIs(un.system_for("Standard (mm, kg, s, °)"), un.METRIC_MM)
        self.assertIs(un.system_for("Metric small parts & CNC (mm, mm/min)"), un.METRIC_MM)
        self.assertIs(un.system_for("FEM (mm, N, s)"), un.METRIC_MM)
        self.assertIs(un.system_for("MKS (m, kg, s, °)"), un.METRIC_M)
        self.assertIs(un.system_for("Meter decimal (m, m², m³)"), un.METRIC_M)
        self.assertIs(un.system_for("Building Euro (cm, m², m³)"), un.METRIC_CM)
        for name in ("US customary (in, lb)", "Imperial decimal (in, lb)", "Building US (ft-in, sqft, cft)",
                     "Imperial for Civil Eng (ft, lb, mph)"):
            self.assertIs(un.system_for(name), un.IMPERIAL)
        self.assertIs(un.system_for(""), un.METRIC_MM)
        self.assertIs(un.system_for(None), un.METRIC_MM)

    def test_unit_follows_the_length(self):
        s = un.METRIC_MM
        self.assertEqual(un.unit_for(s, 0.2).symbol, "µm")
        self.assertEqual(un.unit_for(s, 5).symbol, "mm")
        self.assertEqual(un.unit_for(s, 999).symbol, "mm")
        self.assertEqual(un.unit_for(s, 1000).symbol, "m")
        self.assertEqual(un.unit_for(un.METRIC_CM, 50).symbol, "cm")
        self.assertEqual(un.unit_for(un.IMPERIAL, 25.4).symbol, "in")
        self.assertEqual(un.unit_for(un.IMPERIAL, 400).symbol, "ft")

    def test_nice_step_is_one_two_or_five_times_a_power_of_ten(self):
        self.assertEqual(un.nice_step(1.0), 1.0)
        self.assertEqual(un.nice_step(1.3), 1.0)
        self.assertEqual(un.nice_step(1.6), 2.0)
        self.assertEqual(un.nice_step(3.8), 5.0)
        self.assertEqual(un.nice_step(8.0), 10.0)
        self.assertAlmostEqual(un.nice_step(0.07), 0.05)
        self.assertAlmostEqual(un.nice_step(230.0), 200.0)
        with self.assertRaises(ValueError):
            un.nice_step(0.0)

    def test_format_length(self):
        self.assertEqual(un.format_length(142.0, un.METRIC_MM), "142 mm")
        self.assertEqual(un.format_length(14.26, un.METRIC_MM), "14.3 mm")
        self.assertEqual(un.format_length(1250.0, un.METRIC_MM), "1.25 m")
        self.assertEqual(un.format_length(0.0, un.METRIC_MM), "0 µm")
        self.assertEqual(un.format_length(50.0, un.METRIC_CM), "5 cm")
        self.assertEqual(un.format_length(50.8, un.IMPERIAL), "2 in")
        self.assertEqual(un.format_length(609.6, un.IMPERIAL), "2 ft")
        self.assertEqual(un.format_length(100.0, un.METRIC_MM, un.CM), "10 cm")

    def test_the_resolution_of_a_value_decides_its_digits(self):
        self.assertEqual(un.format_length(100.4, un.METRIC_MM, resolution_mm=0.1), "100.4 mm")
        self.assertEqual(un.format_length(100.0, un.METRIC_MM, resolution_mm=0.1), "100 mm")
        self.assertEqual(un.format_length(23.05, un.METRIC_MM, resolution_mm=0.01), "23.05 mm")
        self.assertEqual(un.format_length(100.4, un.METRIC_MM, resolution_mm=1.0), "100 mm")
        self.assertEqual(un.format_length(1234.5, un.METRIC_MM, resolution_mm=0.1), "1.2345 m")
        self.assertEqual(un.format_length(142.0, un.METRIC_MM, resolution_mm=0.05), "142 mm")

    def test_lengths_under_a_millimetre_can_be_decimals_of_a_millimetre(self):
        decimal = un.without_micrometres(un.METRIC_MM)
        self.assertEqual(un.format_length(0.25, decimal), "0.25 mm")
        self.assertEqual(un.format_length(0.0, decimal), "0 mm")
        self.assertEqual(un.format_length(0.25, un.METRIC_MM), "250 µm")
        self.assertEqual(un.format_length(1250.0, decimal), "1.25 m")
        self.assertIs(un.without_micrometres(un.IMPERIAL), un.IMPERIAL)
        self.assertEqual(un.ruler_spec(decimal, 0.03).unit, un.MM)

    def test_ruler_spec_falls_on_round_numbers(self):
        spec = un.ruler_spec(un.METRIC_MM, 23.0)
        self.assertEqual((spec.unit.symbol, spec.step_mm, spec.minor_mm), ("mm", 20.0, 5.0))
        spec = un.ruler_spec(un.METRIC_MM, 7.0)
        self.assertEqual((spec.step_mm, spec.minor_mm), (5.0, 1.0))
        spec = un.ruler_spec(un.METRIC_MM, 1.0)
        self.assertEqual((spec.step_mm, spec.minor_mm), (1.0, 0.1))
        spec = un.ruler_spec(un.METRIC_MM, 0.03)
        self.assertEqual(spec.unit.symbol, "µm")
        self.assertAlmostEqual(spec.step_mm, 0.02)
        spec = un.ruler_spec(un.IMPERIAL, 60.0)       # about 2.4 in: 2 in steps
        self.assertEqual(spec.unit.symbol, "in")
        self.assertAlmostEqual(spec.step_mm, 50.8)


if __name__ == "__main__":
    unittest.main()
