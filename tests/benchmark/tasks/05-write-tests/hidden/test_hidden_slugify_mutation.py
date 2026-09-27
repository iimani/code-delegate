"""Scores the model's tests/test_text.py by mutation testing.

The suite must pass against the real slugify and fail against at least
MIN_KILLED of the bundled broken variants (hidden/mutants/*.py).
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HIDDEN = pathlib.Path(__file__).resolve().parent / "_hidden"
MIN_KILLED = 4


def _run_suite(app_text_source):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        shutil.copytree(ROOT / "app", tmp / "app")
        (tmp / "tests").mkdir()
        (tmp / "tests" / "__init__.py").write_text("")
        shutil.copy(ROOT / "tests" / "test_text.py", tmp / "tests" / "test_text.py")
        (tmp / "app" / "text.py").write_text(app_text_source)
        proc = subprocess.run([sys.executable, "-m", "unittest", "tests.test_text"],
                              cwd=tmp, capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stderr


class HiddenMutationTests(unittest.TestCase):
    def test_suite_exists(self):
        self.assertTrue((ROOT / "tests" / "test_text.py").exists(), "tests/test_text.py was not written")

    def test_implementation_untouched(self):
        self.assertEqual((ROOT / "app" / "text.py").read_text(),
                         (HIDDEN / "pristine_text.py").read_text(),
                         "app/text.py was modified")

    def test_passes_on_real_implementation(self):
        code, err = _run_suite((HIDDEN / "pristine_text.py").read_text())
        self.assertEqual(code, 0, err[-2000:])

    def test_kills_mutants(self):
        survivors = []
        mutants = sorted((HIDDEN / "mutants").glob("*.py"))
        for mutant in mutants:
            code, _ = _run_suite(mutant.read_text())
            if code == 0:
                survivors.append(mutant.stem)
        killed = len(mutants) - len(survivors)
        self.assertGreaterEqual(killed, MIN_KILLED,
                                f"killed {killed}/{len(mutants)}; survived: {survivors}")


if __name__ == "__main__":
    unittest.main()
