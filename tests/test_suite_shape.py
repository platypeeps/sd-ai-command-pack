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

    def tracked_sources(self) -> list[pathlib.Path]:
        listed = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        found = []
        for name in listed.stdout.split():
            path = REPO_ROOT / name
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

    def test_no_tracked_source_warns_when_python_reads_it(self) -> None:
        noisy = []
        for path in self.tracked_sources():
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

        found = self.tracked_sources()
        self.assertNotEqual(found, [], "no tracked source was scanned")
        self.assertIn(REPO_ROOT / "bin" / "sd", found, "the main entry point was not scanned")


if __name__ == "__main__":
    unittest.main()
