"""Scores tests/test_money.py, test_dates.py and test_pricing.py by mutation testing.

The three suites must pass against the real modules and fail against at least
MIN_KILLED of the broken variants in _hidden/mutants/<module>__<name>.py.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HIDDEN = pathlib.Path(__file__).resolve().parent / "_hidden"
SUITES = ["tests.test_money", "tests.test_dates", "tests.test_pricing"]
TARGETS = {"money": "shop/util/money.py", "dates": "shop/util/dates.py", "pricing": "shop/services/pricing.py"}
MIN_KILLED = 14


def _run(replace=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        shutil.copytree(ROOT / "shop", tmp / "shop", ignore=shutil.ignore_patterns("__pycache__"))
        (tmp / "tests").mkdir()
        for name in ("__init__.py", "support.py", "test_money.py", "test_dates.py", "test_pricing.py"):
            if (ROOT / "tests" / name).exists():
                shutil.copy(ROOT / "tests" / name, tmp / "tests" / name)
        if replace:
            module, source = replace
            (tmp / TARGETS[module]).write_text(source)
        proc = subprocess.run([sys.executable, "-m", "unittest", *SUITES], cwd=tmp,
                              capture_output=True, text=True, timeout=300)
        return proc.returncode, proc.stderr


class HiddenMutationTests(unittest.TestCase):
    def test_suites_exist(self):
        for name in ("test_money.py", "test_dates.py", "test_pricing.py"):
            self.assertTrue((ROOT / "tests" / name).exists(), f"tests/{name} was not written")

    def test_modules_untouched(self):
        for module, path in TARGETS.items():
            self.assertEqual((ROOT / path).read_text(), (HIDDEN / "pristine" / f"{module}.py").read_text(),
                             f"{path} was modified")

    def test_pass_on_real_code(self):
        code, err = _run()
        self.assertEqual(code, 0, err[-3000:])

    def test_kill_mutants(self):
        mutants = sorted((HIDDEN / "mutants").glob("*.py"))
        survivors = [m.stem for m in mutants
                     if _run((m.stem.split("__")[0], m.read_text()))[0] == 0]
        killed = len(mutants) - len(survivors)
        self.assertGreaterEqual(killed, MIN_KILLED, f"killed {killed}/{len(mutants)}; survived: {survivors}")


if __name__ == "__main__":
    unittest.main()
