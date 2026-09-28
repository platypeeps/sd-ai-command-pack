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

The one named exception (sd:1910): the lane commands in `LANE_COMMANDS` take
`-C <dir>`, which changes the working directory before anything resolves, as
`git -C` does. The permission layer that approves a command line sees `-C`
there and does not see a `cd <dir> &&` in front of the same command, so the
visible form is the one to allow. `-C` on any other file under `bin/` is an
offender like `--repo` is.
"""

# This module reads the whole checkout, so no changed-files fast path may
# narrow it away. `.github/scripts/select-tests.py` greps for the line below.
# select-tests: always-run

from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"

# Option names that hand a command a repository other than the one the caller is
# standing in. `--work-dir` and friends are repo-relative and stay.
REPO_PATH_OPTIONS = frozenset({"--repo", "--repo-path", "--root", "--checkout", "--directory"})

# The lane commands R10-D6 names: the only files under `bin/` that may declare
# `-C`. A sixth is an offender; a long spelling is one of the banned above.
DIRECTORY_OPTION = "-C"
LANE_COMMANDS = frozenset({"sd-ship", "sd-check", "sd-review", "sd-review-ack", "sd-pr-state"})


def scanned_files() -> list[pathlib.Path]:
    """Everything in `bin/` except the migration tools.

    Deliberately wider than the eleven commands: it also catches the library
    modules (`sd_lib.py`, `sd_route.py`), which is the point. Those are
    underscore-named, so a `sd-`-prefix filter would drop them from the scan
    and lose coverage exactly where a repo-path argument would do the most
    damage -- a root resolved wrongly in the shared library is wrong for every
    command that imports it.
    """

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
        # If the scan ever returns nothing -- a moved directory, a renamed
        # prefix -- every other test here passes vacuously. Fail loudly instead.
        self.assertGreater(len(scanned_files()), 5, "bin/ enumerated to almost nothing")

    def test_the_scan_actually_reaches_commands(self) -> None:
        """Non-empty is not enough: it must contain dash-named commands.

        `scanned_files()` is wide on purpose, so a `bin/` holding only library
        modules would still satisfy the count above while covering no command
        at all. This pins the half that the count cannot see.
        """

        dash_named = [p.name for p in scanned_files() if p.name.startswith("sd-")]
        self.assertGreater(len(dash_named), 5, f"no sd-* commands in the scan: {dash_named}")

    def test_no_command_accepts_a_repository_path(self) -> None:
        offenders: list[str] = []
        for path in scanned_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue  # not Python; nothing with an argparse surface to check
            options = option_strings(tree)
            for option in sorted(options & REPO_PATH_OPTIONS):
                offenders.append(f"{path.name} takes {option}")
            if DIRECTORY_OPTION in options and path.name not in LANE_COMMANDS:
                offenders.append(f"{path.name} takes {DIRECTORY_OPTION}, which only the lane commands may")
        self.assertEqual(offenders, [], "R10-D6: sd-* commands resolve the repo from cwd only")

    def test_every_command_resolves_the_root_from_cwd(self) -> None:
        """Where `repo_root` is called, it is called with nothing to point it away.

        Scoped honestly: files that never mention `repo_root(` are skipped, so
        this proves nothing about a command that resolves a root some other
        way. It is the option check above that carries the weight; this one
        adds the case where someone keeps `repo_root` but feeds it a value read
        from config or the environment instead of adding a flag -- the same
        violation wearing a hat.
        """

        for path in scanned_files():
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
