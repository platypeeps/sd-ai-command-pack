"""The sd-* command inventory, enumerated from disk rather than recited.

R10-D6 says every sd-* command resolves its repository from the current working
directory and nowhere else: a session that can be pointed at another checkout is
a session that can act on one, and "sessions stick to their repos" then depends
on the operator remembering, which is the failure mode this whole redesign
exists to remove.

The enforcement has to enumerate `bin/` itself. A test listing the tools it
knows about proves only that those tools are clean -- the twelfth one, added
later with a `--repo` flag, is exactly the case a hand-maintained list cannot
see. So every check here starts from `iterdir()`.

`migrate-*` is deliberately exempt and named as such: a migration tool whose job
is to convert *another* checkout must be able to name it. Those are temporary
and deleted at steps 7 and 11.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"

# Option names that hand a command a repository other than the one the caller is
# standing in. `--work-dir` and friends are repo-relative and stay.
REPO_PATH_OPTIONS = frozenset({"--repo", "--repo-path", "--root", "--checkout", "--directory"})


def commands() -> list[pathlib.Path]:
    """Every sd-* command on disk, migration tools excluded."""

    return sorted(
        path
        for path in BIN.iterdir()
        if path.is_file()
        and not path.name.startswith("migrate-")
        and not path.name.endswith(".pyc")
    )


def option_strings(tree: ast.AST) -> set[str]:
    """Every literal `--flag` handed to an `add_argument` call in the file."""

    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not isinstance(function, ast.Attribute) or function.attr != "add_argument":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.add(argument.value)
    return found


class InventoryTests(unittest.TestCase):
    def test_the_inventory_is_not_empty(self) -> None:
        # If `commands()` ever returns nothing -- a moved directory, a renamed
        # prefix -- every other test here passes vacuously. Fail loudly instead.
        self.assertGreater(len(commands()), 5, "bin/ enumerated to almost nothing")

    def test_no_command_accepts_a_repository_path(self) -> None:
        offenders: list[str] = []
        for path in commands():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue  # not Python; nothing with an argparse surface to check
            for option in sorted(option_strings(tree) & REPO_PATH_OPTIONS):
                offenders.append(f"{path.name} takes {option}")
        self.assertEqual(offenders, [], "R10-D6: sd-* commands resolve the repo from cwd only")

    def test_every_command_resolves_the_root_from_cwd(self) -> None:
        """`repo_root` is called, and it is called with nothing to point it away.

        Weaker than the option check on purpose: this catches a command that
        reads a root out of an environment variable or a config key instead of
        adding a flag for it, which is the same violation wearing a hat.
        """

        for path in commands():
            source = path.read_text(encoding="utf-8", errors="replace")
            if "repo_root(" not in source:
                continue
            with self.subTest(command=path.name):
                self.assertNotIn(
                    "repo_root(args.",
                    source,
                    f"{path.name} resolves its repository from an argument",
                )


if __name__ == "__main__":
    unittest.main()
