import os
import shutil
import subprocess
import tempfile
import unittest

from lookout.core import slogging
from lookout.core.package import package


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        slogging.setup("INFO", False, "")

    def test_package(self):
        root = os.path.dirname(__file__)
        with tempfile.TemporaryDirectory(prefix="lookout-sdk-ml-test-") as tmpdir:
            shutil.copy(os.path.join(root, "..", "examples", "my_analyzer.py"),
                        os.path.join(tmpdir, "my_analyzer.py"))
            self.assertEqual(1, package(
                True, True, tmpdir, ["my_analyzer"], "", "src-d/ml", "vmarkovtsev", "secret"))
            self.assertEqual(2, package(
                False, True, tmpdir, ["my_analyzer"], "", "src-d/ml", "vmarkovtsev", "secret"))
            os.chdir(tmpdir)
            with tempfile.TemporaryDirectory(prefix="lookout-sdk-ml-test-") as tmpdir2:
                self.assertIsNone(package(
                    False, True, tmpdir2, ["my_analyzer"], "", "src-d/ml", "vmarkovtsev",
                    "secret"))
                try:
                    subprocess.check_call(["docker", "version"])
                except FileNotFoundError:
                    return
                subprocess.check_call(["docker", "build", "-t", "my", tmpdir2])
                subprocess.check_call(["docker", "run", "-it", "--rm", "my", "list"])


if __name__ == "__main__":
    unittest.main()
