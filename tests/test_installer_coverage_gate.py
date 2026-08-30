"""Pin the behaviours check-installer-coverage.sh depends on.

The gate replaced a literal `--include="install.py,installer/*"` glob because a
glob drifts in two directions and reports a green 100% through both: a new
module lands outside the pattern unmeasured, or code is deleted and the same
100% then certifies less. Enumeration closes the first, a declared file floor
closes the second.

Both guarantees rest on a subtlety worth pinning. Copilot raised the subpackage
case on #609 -- would `installer/*.py` miss `installer/sub/mod.py`? -- and the
answer is no, but only because git's default pathspec matching runs wildmatch
without WM_PATHNAME, so `*` crosses `/`. Adding `:(glob)` magic would flip
that and silently shrink the measured set. That is a real trap for a future
reader "tidying" the pathspec, so it is asserted here rather than left to a
comment.
"""

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / ".github/scripts/check-installer-coverage.sh"


class PathspecSemanticsTests(unittest.TestCase):
    """The pathspec the gate uses must reach into subpackages."""

    def test_plain_pathspec_crosses_directory_separator(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = lambda *a: subprocess.run(  # noqa: E731
                a, cwd=root, capture_output=True, text=True, check=True
            )
            run("git", "init", "-q")
            (root / "installer" / "sub").mkdir(parents=True)
            (root / "installer" / "flat.py").write_text("x = 1\n")
            (root / "installer" / "sub" / "nested.py").write_text("y = 2\n")
            run("git", "add", "-A")

            listed = run("git", "ls-files", "--", "installer/*.py").stdout.split()

            self.assertIn(
                "installer/sub/nested.py",
                listed,
                "plain pathspec must reach a subpackage; if this fails, git's "
                "matching changed and the gate now measures less than it claims",
            )
            self.assertIn("installer/flat.py", listed)

    def test_glob_magic_would_break_it(self):
        """The failure mode the comment warns about, demonstrated."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = lambda *a: subprocess.run(  # noqa: E731
                a, cwd=root, capture_output=True, text=True, check=True
            )
            run("git", "init", "-q")
            (root / "installer" / "sub").mkdir(parents=True)
            (root / "installer" / "sub" / "nested.py").write_text("y = 2\n")
            run("git", "add", "-A")

            listed = run(
                "git", "ls-files", "--", ":(glob)installer/*.py"
            ).stdout.split()

            self.assertNotIn(
                "installer/sub/nested.py",
                listed,
                "if :(glob) started crossing separators the warning comment in "
                "check-installer-coverage.sh would be wrong and should be fixed",
            )


class GateContractTests(unittest.TestCase):
    """The gate's own guard rails."""

    def test_gate_is_executable_and_declares_a_floor(self):
        self.assertTrue(GATE.exists(), f"{GATE} is missing")
        source = GATE.read_text()
        self.assertIn("MIN_FILES=", source)
        self.assertIn("--fail-under=100", source)

    def test_floor_refuses_a_shrunken_surface(self):
        """Raising the floor above the real surface must fail loudly."""
        source = GATE.read_text()
        self.assertIn("MIN_FILES=", source)
        raised = source.replace("MIN_FILES=17", "MIN_FILES=9999", 1)
        self.assertNotEqual(raised, source, "MIN_FILES anchor not found")

        probe = REPO_ROOT / ".github/scripts/.floor-probe.sh"
        probe.write_text(raised)
        try:
            result = subprocess.run(
                ["bash", str(probe)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
        finally:
            probe.unlink()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("below the declared floor", result.stderr)


if __name__ == "__main__":
    unittest.main()
