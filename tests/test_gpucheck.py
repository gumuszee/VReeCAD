import os
import tempfile
import unittest

import support  # noqa: F401
from freecad.VReeCAD import gpucheck

RADV = "AMD Radeon 780M Graphics (radeonsi, phoenix, ACO, DRM 3.64, 7.2.11-200.nobara.fc44.x86_64)"
RTX = "NVIDIA GeForce RTX 4070 Laptop GPU/PCIe/SSE2"


class RendererVendorTest(unittest.TestCase):
    def test_the_vendor_is_read_from_the_renderer_string(self):
        self.assertEqual(gpucheck.renderer_vendor(RADV), gpucheck.AMD)
        self.assertEqual(gpucheck.renderer_vendor(RTX), gpucheck.NVIDIA)
        self.assertEqual(gpucheck.renderer_vendor("Mesa Intel(R) Graphics (ADL GT2)"), gpucheck.INTEL)
        self.assertEqual(gpucheck.renderer_vendor("llvmpipe (LLVM 22.1.8, 256 bits)"), gpucheck.SOFTWARE)
        self.assertEqual(gpucheck.renderer_vendor("zink Vulkan 1.3(NVIDIA GeForce RTX 4070 (NVIDIA_PROPRIETARY))"), gpucheck.NVIDIA)
        self.assertEqual(gpucheck.renderer_vendor("Apple M2"), gpucheck.UNKNOWN)
        self.assertEqual(gpucheck.renderer_vendor(None), gpucheck.UNKNOWN)


class GpuVendorsTest(unittest.TestCase):
    def make(self, root, card, vendor):
        d = os.path.join(root, card, "device")
        os.makedirs(d)
        with open(os.path.join(d, "vendor"), "w") as f:
            f.write(vendor + "\n")

    def test_the_cards_of_the_drm_folder_give_the_vendors_and_connectors_are_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            self.make(root, "card1", "0x1002")
            self.make(root, "card2", "0x10de")
            self.make(root, "card2-HDMI-A-1", "0x8086")
            self.assertEqual(gpucheck.gpu_vendors(root), {gpucheck.AMD, gpucheck.NVIDIA})

    def test_an_unknown_vendor_and_a_missing_folder_give_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            self.make(root, "card0", "0x1234")
            self.assertEqual(gpucheck.gpu_vendors(root), set())
        self.assertEqual(gpucheck.gpu_vendors("/nonexistent/drm"), set())


class CheckTest(unittest.TestCase):
    both = {gpucheck.AMD, gpucheck.NVIDIA}

    def test_the_igpu_renderer_with_an_nvidia_gpu_present_warns_and_names_the_launch_command(self):
        text = gpucheck.check(RADV, self.both, "Linux", {})
        self.assertIn("AMD Radeon 780M", text)
        self.assertIn("__NV_PRIME_RENDER_OFFLOAD=1", text)
        self.assertIn("__GLX_VENDOR_LIBRARY_NAME=nvidia", text)
        self.assertIn("__EGL_VENDOR_LIBRARY_FILENAMES=", text)
        self.assertIn(gpucheck.SKIP_ENV, text)

    def test_a_software_renderer_with_an_nvidia_gpu_present_warns(self):
        self.assertIsNotNone(gpucheck.check("llvmpipe (LLVM 22.1.8, 256 bits)", {gpucheck.NVIDIA}, "Linux", {}))

    def test_the_nvidia_renderer_does_not_warn(self):
        self.assertIsNone(gpucheck.check(RTX, self.both, "Linux", {}))

    def test_a_machine_without_an_nvidia_gpu_does_not_warn(self):
        self.assertIsNone(gpucheck.check(RADV, {gpucheck.AMD}, "Linux", {}))
        self.assertIsNone(gpucheck.check(RADV, {gpucheck.AMD, gpucheck.INTEL}, "Linux", {}))

    def test_an_unknown_or_unreadable_renderer_does_not_warn(self):
        self.assertIsNone(gpucheck.check("Apple M2", self.both, "Linux", {}))
        self.assertIsNone(gpucheck.check(None, self.both, "Linux", {}))
        self.assertIsNone(gpucheck.check("", self.both, "Linux", {}))

    def test_other_systems_do_not_warn(self):
        self.assertIsNone(gpucheck.check(RADV, self.both, "Windows", {}))
        self.assertIsNone(gpucheck.check(RADV, self.both, "Darwin", {}))

    def test_the_environment_variable_turns_the_check_off(self):
        self.assertIsNone(gpucheck.check(RADV, self.both, "Linux", {gpucheck.SKIP_ENV: "1"}))
        self.assertIsNotNone(gpucheck.check(RADV, self.both, "Linux", {gpucheck.SKIP_ENV: ""}))


class LaunchCommandTest(unittest.TestCase):
    def test_the_command_uses_the_nvidia_egl_vendor_file_found_on_the_system(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "15_nvidia.json")
            open(path, "w").close()
            self.assertIn(f"__EGL_VENDOR_LIBRARY_FILENAMES={path} ", gpucheck.nvidia_launch_command((os.path.join(root, "*nvidia*.json"),)))

    def test_the_command_falls_back_to_the_default_vendor_file_path(self):
        self.assertIn("/usr/share/glvnd/egl_vendor.d/10_nvidia.json", gpucheck.nvidia_launch_command(("/nonexistent/*nvidia*.json",)))


if __name__ == "__main__":
    unittest.main()
