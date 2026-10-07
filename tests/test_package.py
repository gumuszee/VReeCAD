import os
import re
import unittest
import xml.etree.ElementTree as ET

import support  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = {"p": "https://wiki.freecad.org/Package_Metadata"}


def package():
    return ET.parse(os.path.join(ROOT, "package.xml")).getroot()


class PackageTest(unittest.TestCase):
    """The metadata that the Addon Manager reads (package.xml) matches the repository."""

    def test_the_files_the_metadata_names_exist(self):
        root = package()
        self.assertTrue(os.path.isfile(os.path.join(ROOT, root.find("p:license", NS).get("file"))))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, root.find("p:icon", NS).text)))
        workbench = root.find("p:content/p:workbench", NS)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, workbench.find("p:icon", NS).text)))
        self.assertTrue(os.path.isdir(os.path.join(ROOT, "freecad", "BlocksCAD")))

    def test_the_workbench_class_is_the_one_the_gui_registers(self):
        classname = package().find("p:content/p:workbench/p:classname", NS).text
        with open(os.path.join(ROOT, "freecad", "BlocksCAD", "init_gui.py"), encoding="utf-8") as f:
            self.assertIn(f"class {classname}", f.read())

    def test_the_python_packages_are_declared_as_such_and_the_code_needs_no_others(self):
        declared = {d.text for d in package().findall("p:content/p:workbench/p:depend", NS)}
        self.assertEqual(declared, {"pyopenxr", "PyOpenGL"})
        for d in package().findall("p:content/p:workbench/p:depend", NS):
            self.assertEqual(d.get("type"), "python")

    def test_the_version_has_three_numbers_and_the_readme_names_it(self):
        version = package().find("p:version", NS).text
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            self.assertRegex(f.read(), r"\| Version \| " + re.escape(version) + r" \|")

    def test_the_addon_has_no_development_dependency(self):
        """No module of the addon imports the development tooling (docs/design.md, D5)."""
        pattern = re.compile(r"^\s*(?:from|import)\s+(?:tools|fc_rpc|freecad_mcp)\b", re.M)
        for folder, _, files in os.walk(os.path.join(ROOT, "freecad")):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(folder, name), encoding="utf-8") as f:
                        self.assertIsNone(pattern.search(f.read()), os.path.join(folder, name))


if __name__ == "__main__":
    unittest.main()
