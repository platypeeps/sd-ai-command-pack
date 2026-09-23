"""The governed pathspec is derived from the index and declared once.

Two whole-tree greps scan "what runs or governs". Each used to carry its own
copy of the pathspec, the copies were identical, and nothing compared them --
so a name added to one would have silently widened one grep and not the other.
Both now read `tests/governed.py`.

Naming the two directories the copies missed would prove nothing: a check
built from what the author already knows cannot find what they did not know
about. So the derivation is exercised against a throwaway repository holding a
top-level directory this checkout does not have, and this checkout is then
asserted to leave nothing tracked out of the pathspec except the history it
names.
"""

# This module reads the whole checkout, so no changed-files fast path may
# narrow it away. `.github/scripts/select-tests.py` greps for the line below.
# select-tests: always-run

from __future__ import annotations

import ast
import importlib
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import governed as governed_module  # noqa: E402

#: The modules that scan the governed tree. Both must read the one definition.
SCANNERS = ("tests.test_cut_symbols", "tests.test_no_trellis_residue")

NAME = "GOVERNED"


class TheDerivation(unittest.TestCase):
    """It reads the repository, so it finds a directory nobody told it about."""

    def test_a_top_level_directory_nobody_named_is_governed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for rel in ("plugins/thing.py", "bin/tool", "docs/work/note.md",
                        "docs/spec/rules.md", "CHANGELOG.md"):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)

            pathspec = governed_module.governed(root)

        self.assertIn("plugins", pathspec,
                      "a directory the pathspec was not told about is not scanned, "
                      "which is the defect the derivation replaces")
        self.assertIn("bin", pathspec)
        self.assertIn("docs/spec", pathspec)

    def test_history_stays_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for rel in ("docs/work/note.md", "CHANGELOG.md"):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)

            pathspec = governed_module.governed(root)

        self.assertNotIn("docs", pathspec, "docs/work would be scanned as history")
        self.assertNotIn("CHANGELOG.md", pathspec)


class ThisCheckout(unittest.TestCase):
    def test_everything_tracked_is_governed_or_named_history(self) -> None:
        """Enumerated from the index, not from the tuple: a top-level entry
        that is neither scanned nor declared history is the hole."""
        pathspec = set(governed_module.GOVERNED)
        history = set(governed_module.HISTORY)
        stranded = [name for name in governed_module.top_level(REPO_ROOT)
                    if name not in pathspec and name not in history]

        self.assertEqual(stranded, [],
                         f"tracked at the top level, scanned by neither grep, "
                         f"and not declared history: {stranded}")

    def test_the_directories_the_copies_missed_are_in_now(self) -> None:
        """The three this row was raised for, each still tracked."""
        for name in ("contrib", "hooks", "actions"):
            with self.subTest(name=name):
                self.assertTrue((REPO_ROOT / name).is_dir(), f"{name}/ is gone")
                self.assertIn(name, governed_module.GOVERNED)


class OneDefinition(unittest.TestCase):
    def test_both_scanners_read_the_same_object(self) -> None:
        for name in SCANNERS:
            with self.subTest(module=name):
                module = importlib.import_module(name)
                self.assertIs(getattr(module, NAME), governed_module.GOVERNED)

    def test_no_test_module_declares_its_own_copy(self) -> None:
        """A literal assignment anywhere under `tests/` is a second copy, and
        a second copy is what nothing was comparing."""
        offenders = []
        for path in sorted(REPO_ROOT.glob("tests/*.py")):
            if path.name == "governed.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if not any(isinstance(t, ast.Name) and t.id == NAME for t in targets):
                    continue
                if isinstance(node.value, (ast.Tuple, ast.List, ast.Set)):
                    offenders.append(f"{path.name}:{node.lineno}")

        self.assertEqual(offenders, [],
                         f"a second governed pathspec, typed by hand: {offenders}")


if __name__ == "__main__":
    unittest.main()
