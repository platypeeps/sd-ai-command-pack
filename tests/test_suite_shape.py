"""Every test in `tests/` is reachable however the file is run.

`unittest discover` imports a module and collects from it afterwards, so a
`if __name__ == "__main__": unittest.main()` block sitting halfway down the
file is invisible to CI. Run that same file directly and `unittest.main()`
executes at the line it appears on -- before the classes below it exist -- and
those tests are silently skipped. Two files in this suite had drifted into
that shape, hiding 32 and 70 tests respectively from direct execution.

The check enumerates `tests/` and parses each module rather than naming the
files that were wrong when it was written; the next file to grow a class after
its runner block is the one a hand-kept list would miss.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import tempfile
import unittest
import warnings

TESTS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS.parent


def main_guard_line(tree: ast.Module) -> int | None:
    """The line of the module's `if __name__ == "__main__":`, if it has one.

    The operator and the comparand are both checked, not just the left-hand
    name. A predicate matching any top-level `if` that mentions `__name__`
    would also claim `if __name__ != "__main__"` and `if __name__ in NAMES`,
    which run in the opposite case or in no particular case -- and reporting a
    guard line for a block that is not a guard would fail modules that are
    shaped correctly.
    """

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1):
            continue
        right = test.comparators[0]
        if isinstance(right, ast.Constant) and right.value == "__main__":
            return node.lineno
    return None


class SuiteShapeTests(unittest.TestCase):
    def test_no_module_defines_anything_after_its_runner_block(self) -> None:
        offenders = []
        for path in sorted(TESTS.glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            guard = main_guard_line(tree)
            if guard is None:
                continue
            after = [n.name for n in tree.body
                     if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.lineno > guard]
            if after:
                offenders.append(f"{path.name}: {', '.join(after)} defined after line {guard}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_the_predicate_recognises_a_guard_and_rejects_near_misses(self) -> None:
        """The control, as a fixture rather than as a count.

        `main_guard_line` returning `None` for every module would make the test
        above pass over an entire suite of offenders without comparing
        anything. Asserting that against the repository's own file count made
        the control brittle in the ordinary direction -- reorganising the suite
        would fail it while the invariant still held -- so the predicate is
        exercised directly instead. The near-misses are the ones the earlier,
        looser predicate wrongly claimed.
        """

        self.assertEqual(
            main_guard_line(ast.parse('if __name__ == "__main__":\n    main()\n')), 1)
        for near_miss in ('if __name__ != "__main__":\n    main()\n',
                          'if __name__ in NAMES:\n    main()\n',
                          'if __name__ == "__test__":\n    main()\n',
                          'def f():\n    if __name__ == "__main__":\n        main()\n'):
            self.assertIsNone(main_guard_line(ast.parse(near_miss)), near_miss)

    def test_the_scan_reaches_the_real_suite(self) -> None:
        """The other half: a live predicate pointed at nothing proves nothing.

        Separate from the fixture above because they fail for different
        reasons. This one goes wrong when the glob or the directory moves, and
        it asserts the tree was found rather than anything about the shape of
        what is in it.
        """

        self.assertNotEqual(list(TESTS.glob("test_*.py")), [], "the suite was not reached")


def tracked_sources(root: pathlib.Path = REPO_ROOT) -> list[pathlib.Path]:
    """Every tracked Python source under `root`, found by asking git.

    `-z` and a NUL split rather than `.split()` on whitespace. Git prints a
    path containing a space *unquoted* -- `has space.py` arrives verbatim, not
    as `"has space.py"` -- so splitting on whitespace tore it into `has` and
    `space.py`. Neither of those is a file, the `is_file()` guard below dropped
    both, and the source left the scan with nothing printed and the run still
    green. That is the failure worth naming: not a wrong answer but a check
    that had quietly stopped covering a file while continuing to report
    success. No tracked path in this repository holds whitespace today, so this
    was latent rather than live; what it cost was that the first one added
    would have been skipped in silence.

    `--deduplicate` because the index holds an unmerged path once per merge
    stage and plain `ls-files` prints it once per stage, so a file being merged
    was parsed three times and named three times in one failure message. The
    verdict was never wrong here -- results are collected into lists and
    compared -- which is precisely why nothing ever surfaced it.

    `root` is the test seam and is kept off the callers below deliberately: the
    cases point the enumeration at a throwaway repository, because nothing
    about a clean checkout tells any of these behaviours apart.
    """

    listed = subprocess.run(
        ["git", "ls-files", "-z", "--deduplicate"],
        cwd=root, capture_output=True, text=True, check=True)
    found = []
    for name in listed.stdout.split("\0"):
        if not name:
            continue
        path = root / name
        if not path.is_file():
            continue
        if path.suffix == ".py":
            found.append(path)
            continue
        # The `bin/sd-*` commands carry no suffix; a shebang naming python
        # is what makes them python, and reading it is how the check finds
        # a command added later without being told about it.
        head = path.read_bytes()[:64]
        if head.startswith(b"#!") and b"python" in head:
            found.append(path)
    return found


class SourceWarningTests(unittest.TestCase):
    """No tracked source emits a `SyntaxWarning` when Python reads it.

    Found the ordinary way -- running `bin/sd` by hand printed an invalid
    escape sequence warning on every invocation, from a docstring written
    earlier the same day. The suite was green throughout, because warnings do
    not fail tests, and no reviewer saw it, because a warning appears when the
    tool is used rather than when the diff is read. Python 3.12 raised this
    class from DeprecationWarning and 3.15 makes it a SyntaxError, so the same
    docstring that only prints noise today stops the program later.

    Enumerated from `git ls-files` rather than from a list of the files that
    were wrong once.
    """

    def test_no_tracked_source_warns_when_python_reads_it(self) -> None:
        noisy = []
        for path in tracked_sources():
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    ast.parse(path.read_text(encoding="utf-8"))
                except (SyntaxError, UnicodeDecodeError):
                    continue
            for warning in caught:
                if issubclass(warning.category, SyntaxWarning):
                    noisy.append(f"{path.relative_to(REPO_ROOT)}: {warning.message}")
        self.assertEqual(noisy, [], "\n".join(noisy))

    def test_the_source_scan_reaches_the_commands(self) -> None:
        """The control: an empty list would make the test above vacuous."""

        found = tracked_sources()
        self.assertNotEqual(found, [], "no tracked source was scanned")
        self.assertIn(REPO_ROOT / "bin" / "sd", found, "the main entry point was not scanned")


def _git(root: pathlib.Path):
    """A git runner bound to `root`.

    Identity and signing are passed per invocation rather than read from the
    machine, so neither fixture fails on a host with no `user.email` or one
    that signs every commit.
    """

    def run(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "user.email=shape@example.invalid",
             "-c", "user.name=suite shape", "-c", "commit.gpgsign=false", *argv],
            cwd=root, capture_output=True, text=True, check=check)

    return run


def _repo_with_a_source_being_merged(root: pathlib.Path) -> None:
    """Leave `root` holding `f.py` unmerged in the index, resolved on disk.

    A real merge rather than a hand-built index: the three stages have to come
    from git's own conflict machinery, or the fixture restates the belief under
    test instead of evidencing it.

    The working tree is then repaired and deliberately not staged, because that
    is the state this is actually met in -- the conflict has been fixed in the
    editor, the file on disk is valid Python again so nothing warns about it,
    and the index still carries three stages until somebody runs `git add`.
    """

    git = _git(root)
    source = root / "f.py"
    git("init", "-q", "-b", "main", ".")
    source.write_text("VALUE = 0\n")
    git("add", "f.py")
    git("commit", "-qm", "base")
    git("checkout", "-q", "-b", "other")
    source.write_text("VALUE = 1\n")
    git("commit", "-qam", "other")
    git("checkout", "-q", "main")
    source.write_text("VALUE = 2\n")
    git("commit", "-qam", "mine")
    git("merge", "other", check=False)
    source.write_text("VALUE = 3\n")  # resolved in the editor, left unstaged


def _repo_with_a_spaced_path(root: pathlib.Path) -> None:
    """Leave `root` tracking `has space.py` beside an ordinary source.

    The second file is the point of the pair: it is what keeps the scan
    looking healthy while the first one is being dropped.
    """

    git = _git(root)
    (root / "has space.py").write_text("SPACED = True\n")
    (root / "plain.py").write_text("PLAIN = True\n")
    git("init", "-q", "-b", "main", ".")
    git("add", "-A")
    git("commit", "-qm", "base")


class EnumerationTests(unittest.TestCase):
    """What `tracked_sources` reports when a name or an index is unusual.

    Nothing about a clean checkout separates the fixed behaviour from the
    broken one, so each case builds a real repository and asserts its premise
    before its conclusion. Drop a premise and the conclusion would pass against
    any ordinary repository, which is how both of these survived.
    """

    def test_a_path_with_a_space_arrives_once_and_whole(self) -> None:
        """The unconditional defect of the two, and the one that loses a file.

        Splitting git's output on whitespace turns one real path into two that
        do not exist. The `is_file()` guard then drops both, so the source is
        not reported wrongly -- it is not reported at all, while the scan goes
        on looking healthy because the other file is still in the list.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            _repo_with_a_spaced_path(root)

            raw = subprocess.run(
                ["git", "ls-files"], cwd=root,
                capture_output=True, text=True, check=True).stdout
            self.assertIn(
                "has space.py\n", raw,
                "this git quoted the spaced path instead of printing it "
                "plainly, so the defect is not reproduced here; say so rather "
                "than deleting the case")
            self.assertEqual(
                raw.split(), ["has", "space.py", "plain.py"],
                "whitespace splitting no longer tears the path in two, so the "
                "assertion below would prove nothing")
            self.assertFalse(
                (root / "has").exists() or (root / "space.py").exists(),
                "both fragments must be nonexistent paths; that is what makes "
                "the file's disappearance silent rather than an error")

            self.assertEqual(
                tracked_sources(root=root),
                [root / "has space.py", root / "plain.py"],
                "a tracked path containing a space was split into two "
                "nonexistent paths and dropped, so the source left the scan "
                "with nothing printed and the run still green")

    def test_a_source_being_merged_arrives_once(self) -> None:
        """An unmerged path must arrive once, not once per merge stage.

        Cosmetic, and recorded as such: these results are collected into lists
        and compared, so no verdict moves. What moves is the failure message,
        which names the file being merged three times to a reader who is
        already looking for what they just broke.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            _repo_with_a_source_being_merged(root)

            stages = subprocess.run(
                ["git", "ls-files", "-u", "--", "f.py"], cwd=root,
                capture_output=True, text=True, check=True).stdout
            self.assertEqual(
                [line.split("\t")[0].split()[-1] for line in stages.splitlines()],
                ["1", "2", "3"],
                "the fixture did not leave an unmerged index, so the case "
                "below proves nothing")

            repeated = subprocess.run(
                ["git", "ls-files", "-z", "--", "f.py"], cwd=root,
                capture_output=True, text=True, check=True).stdout
            self.assertEqual(
                [name for name in repeated.split("\0") if name],
                ["f.py", "f.py", "f.py"],
                "this git no longer repeats an unmerged path; if that is now "
                "the default, say so here rather than deleting the case")

            self.assertEqual(
                tracked_sources(root=root), [root / "f.py"],
                "a file being merged joined the scan once per merge stage, so "
                "it is parsed three times and named three times in one report")

    def test_the_seam_reads_the_repository_it_is_pointed_at(self) -> None:
        """`root` must move the enumeration, not merely be accepted.

        A seam that were ignored would let both cases above read this
        repository, find neither a spaced path nor a conflict, and pass
        whatever the helper does.
        """

        with tempfile.TemporaryDirectory() as home:
            root = pathlib.Path(home)
            _repo_with_a_spaced_path(root)
            self.assertEqual(tracked_sources(root=root),
                             [root / "has space.py", root / "plain.py"])
            self.assertNotIn(root / "plain.py", tracked_sources())


if __name__ == "__main__":
    unittest.main()
