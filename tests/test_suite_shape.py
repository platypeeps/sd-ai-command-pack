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
import unittest

TESTS = pathlib.Path(__file__).resolve().parent


def main_guard_line(tree: ast.Module) -> int | None:
    """The line of the module's `if __name__ == "__main__":`, if it has one."""

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"):
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

    def test_the_check_can_see_a_runner_block_at_all(self) -> None:
        """The control.

        `main_guard_line` returning `None` for every module would make the
        test above pass over an entire suite of offenders without comparing
        anything.
        """

        found = [path.name for path in sorted(TESTS.glob("test_*.py"))
                 if main_guard_line(ast.parse(path.read_text(encoding="utf-8"))) is not None]
        self.assertGreater(len(found), 20, f"only {len(found)} modules have a runner block")


if __name__ == "__main__":
    unittest.main()
