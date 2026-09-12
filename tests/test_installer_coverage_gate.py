"""Pin the behaviours check-installer-coverage.sh depends on.

The gate replaced a literal `--include=` glob because a glob drifts in two
directions and reports a green 100% through both: a new module lands outside
the pattern unmeasured, or code is deleted and the same 100% then certifies
less. Enumeration closes the first, a declared floor closes the second.

Both guarantees rest on a subtlety worth pinning. Copilot raised the subpackage
case on #609 -- would a `dir/*.py` pathspec miss `dir/sub/mod.py`? -- and the
answer is no, but only because git's default pathspec matching runs wildmatch
without WM_PATHNAME, so `*` crosses `/`. Adding `:(glob)` magic would flip
that and silently shrink the measured set. That is a real trap for a future
reader "tidying" the pathspec, so it is asserted here rather than left to a
comment.

Step 3e narrowed the installer to one file and moved the pathspec to
`bin/sd_install*.py`, which makes the subpackage case *more* live rather than
less: the one honest way this surface grows again is a package beside the
module, and the pathspec has to reach into it on the day that happens.

Which floor is exercised here, and which is not. Raising MIN_FILES fails
before any coverage runs, so it can be probed from a plain unit test. The
statement floor cannot: it reads a report that only exists after `make test`
has combined the coverage datafiles, and a probe run here would fail with "no
data to report" -- rc 1 for the wrong reason, which is worse than no probe.
So MIN_STATEMENTS is checked structurally below and exercised for real on
every `make check`, where the gate runs against combined data.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / ".github/scripts/check-installer-coverage.sh"
PATHSPEC = "bin/sd_install*.py"


def _scratch_repo_listing(root, paths, pathspec):
    """Track `paths` in a throwaway repo and return `git ls-files -- pathspec`."""

    def run(*argv):
        return subprocess.run(
            argv, cwd=root, capture_output=True, text=True, check=True
        )

    run("git", "init", "-q")
    for rel in paths:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n")
    run("git", "add", "-A")
    return run("git", "ls-files", "--", pathspec).stdout.split()


class PathspecSemanticsTests(unittest.TestCase):
    """The pathspec the gate uses must reach into a future subpackage."""

    def test_plain_pathspec_crosses_directory_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            listed = _scratch_repo_listing(
                Path(tmp),
                ["bin/sd_install.py", "bin/sd_install_core/helpers.py"],
                PATHSPEC,
            )

            self.assertIn(
                "bin/sd_install_core/helpers.py",
                listed,
                "plain pathspec must reach a subpackage; if this fails, git's "
                "matching changed and the gate now measures less than it claims",
            )
            self.assertIn("bin/sd_install.py", listed)

    def test_glob_magic_would_break_it(self):
        """The failure mode the comment warns about, demonstrated."""
        with tempfile.TemporaryDirectory() as tmp:
            listed = _scratch_repo_listing(
                Path(tmp),
                ["bin/sd_install_core/helpers.py"],
                f":(glob){PATHSPEC}",
            )

            self.assertNotIn(
                "bin/sd_install_core/helpers.py",
                listed,
                "if :(glob) started crossing separators the warning comment in "
                "check-installer-coverage.sh would be wrong and should be fixed",
            )


class GateContractTests(unittest.TestCase):
    """The gate's own guard rails."""

    def test_gate_measures_the_installer_and_declares_both_floors(self):
        self.assertTrue(GATE.exists(), f"{GATE} is missing")
        source = GATE.read_text()
        self.assertIn(f"git ls-files --deduplicate -- '{PATHSPEC}'", source)
        self.assertIn("MIN_FILES=", source)
        self.assertIn("MIN_STATEMENTS=", source)
        self.assertIn("--fail-under=100", source)

    def test_statement_floor_is_a_real_number_with_a_failure_path(self):
        """A floor of zero would be a declaration that checks nothing."""
        source = GATE.read_text()
        declared = [
            line.split("=", 1)[1].strip()
            for line in source.splitlines()
            if line.startswith("MIN_STATEMENTS=")
        ]
        self.assertEqual(len(declared), 1, "expected exactly one MIN_STATEMENTS")
        self.assertGreater(int(declared[0]), 0)
        self.assertIn('"$statements" -lt "$MIN_STATEMENTS"', source)
        self.assertIn("lower MIN_STATEMENTS in this script", source)

    def test_file_floor_refuses_a_shrunken_surface(self):
        """Raising the floor above the real surface must fail loudly."""
        source = GATE.read_text()
        raised = source.replace("MIN_FILES=1\n", "MIN_FILES=9999\n", 1)
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


class UnmergedIndexTests(unittest.TestCase):
    """The floor counts files, and an unmerged path is one file.

    An unmerged path sits in the index once per merge stage, so a plain
    enumeration hands the gate the same file three times. The count is a
    *floor*, which makes that inflation the one direction a gate must never
    fail in: the surface shrinks below what was declared and the gate says
    yes anyway.

    Exercised against a throwaway repository with the floor raised, the same
    seam `test_file_floor_refuses_a_shrunken_surface` uses -- raising
    MIN_FILES fails before any coverage runs, so the case never needs a
    coverage datafile.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._build()

    def git(self, *argv, check=True):
        return subprocess.run(
            # Identity and signing per invocation, so the fixture does not
            # fail on a host with no `user.email` or one that signs commits.
            ["git", "-C", str(self.root),
             "-c", "user.email=gate@example.invalid",
             "-c", "user.name=coverage gate",
             "-c", "commit.gpgsign=false", *argv],
            capture_output=True, text=True, check=check,
        )

    def _build(self):
        """One installer file, conflicted by a real merge, then resolved.

        Resolved in the working tree and left unstaged, which is the state a
        person runs the suite in: the file on disk is valid Python again and
        nothing warns them, while the index still carries three stages.
        """
        module = self.root / "bin" / "sd_install.py"
        module.parent.mkdir(parents=True)
        (self.root / ".github" / "scripts").mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        module.write_text("x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.git("checkout", "-q", "-b", "other")
        module.write_text("x = 2\n")
        self.git("commit", "-qam", "other")
        self.git("checkout", "-q", "main")
        module.write_text("x = 3\n")
        self.git("commit", "-qam", "mine")
        self.git("merge", "other", check=False)
        module.write_text("x = 4\n")

    def test_the_fixture_really_leaves_three_stages(self):
        """Without this the case below would pass against any clean repo."""
        stages = self.git("ls-files", "-u", "--", PATHSPEC).stdout
        self.assertEqual(
            [line.split("\t")[0].split()[-1] for line in stages.splitlines()],
            ["1", "2", "3"],
        )
        self.assertEqual(
            self.git("ls-files", "--", PATHSPEC).stdout.split(),
            ["bin/sd_install.py"] * 3,
            "this git no longer repeats an unmerged path; if that is now the "
            "default, say so here rather than deleting the case",
        )

    def test_the_floor_is_not_satisfied_by_merge_stages(self):
        """One conflicted file must not add up to a surface of three."""
        source = GATE.read_text().replace("MIN_FILES=1\n", "MIN_FILES=2\n", 1)
        self.assertNotIn("MIN_FILES=1\n", source, "MIN_FILES anchor not found")
        probe = self.root / ".github" / "scripts" / "probe.sh"
        probe.write_text(source)

        result = subprocess.run(
            ["bash", str(probe)], capture_output=True, text=True
        )

        self.assertIn(
            "installer surface is 1 tracked file(s), below the declared floor of 2",
            result.stderr,
            "the gate counted merge stages as files and passed a surface "
            "below its own floor -- a gate failing open:\n"
            + result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
