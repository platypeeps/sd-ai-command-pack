"""The pack's working-directory lookup under a second home (sd:1439).

The library stores a repository under `$HOME` as `~/<relative>`, so the hub
and a laptop with another login read the same rows. The pack derives the
repository from the working directory, which is an absolute path under
*this* machine's home, and every place it turns that into a lookup, a key or
a comparison has to go through `sd_db.paths` -- by way of `sd_lib`'s helpers
-- or it answers "not registered" on the second machine only.

So the store here is written under `HOME=A`, the home and the checkout are
copied to `B`, and the pack's verbs run under `HOME=B` from the copy. Any
verb that refuses, prints the row's own checkout as somewhere else, or reads
no row names a site that still compares the absolute path.

The last test is design.md's grep gate for the pack: a raw `repo WHERE path`
probe under `bin/` bypasses every stored form but one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import sd_db  # noqa: E402
import sd_db.repos  # noqa: E402
import sd_db.workflow  # noqa: E402
import sd_db.writes  # noqa: E402
import sd_lib  # noqa: E402

ITEM = "2026-09-24-a-thing"
KEY = "~/repos/proj"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, timeout=30).stdout.strip()


class TheLookupUnderASecondHome(unittest.TestCase):
    """Written under one home, read and written under another."""

    @classmethod
    def setUpClass(cls):
        """The store and the checkout under `A`, written by the library alone."""
        scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(scratch.cleanup)
        cls.top = Path(scratch.name).resolve()
        first = cls.top / "a"
        checkout = first / "repos" / "proj"
        (checkout / "docs" / "work" / ITEM).mkdir(parents=True)
        git(checkout, "init", "-q", "-b", "main")
        git(checkout, "config", "user.name", "Fixture")
        git(checkout, "config", "user.email", "fixture@example.invalid")
        (checkout / "docs" / "work" / ITEM / "prd.md").write_text(
            "---\ntitle: A thing\ncreated: 2026-09-24\n---\n\nBody.\n", encoding="utf-8")
        git(checkout, "add", "-A")
        git(checkout, "commit", "-qm", "plan a thing")
        sd_db.initialise(home=first)
        with mock.patch.dict(os.environ, {"HOME": str(first)}):
            with sd_db.connect(sd_db.default_path(first), write=True) as connection:
                stored = sd_db.repos.add(connection, checkout, home=first)
                connection.execute("UPDATE repo SET status_source = 'row' WHERE path = ?", (stored,))
                sd_db.workflow.register_work_item(
                    connection, repo=str(checkout), path=f"docs/work/{ITEM}/prd.md",
                    title="A thing", created_at="2026-09-24", who="fixture")
                cls.task = sd_db.writes.create_item(
                    connection, kind="task", title="Written under A", repo=str(checkout))
                row = connection.execute("SELECT repo FROM item WHERE id = ?", (cls.task,)).fetchone()
                connection.commit()
        assert stored == KEY and row["repo"] == KEY, (stored, dict(row))
        cls.first = first

    def setUp(self):
        """A fresh copy of `A` at `B`, and `HOME=B` from here on."""
        self.home = Path(tempfile.mkdtemp(dir=self.top))
        shutil.copytree(self.first, self.home, symlinks=True, dirs_exist_ok=True)
        self.root = self.home / "repos" / "proj"
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, home: Path, cwd: Path, *arguments, code: int = 0):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "sd"), *map(str, arguments)],
            cwd=str(cwd), env={**os.environ, "HOME": str(home)},
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_task_add_here_finds_the_checkout(self):
        state = json.loads(self.call(self.home, self.root, "task", "add", "Written under B",
                                     "--here", "--json").stdout)
        self.assertEqual(state["item"]["repo"], KEY)

    def test_a_row_of_this_checkout_is_not_printed_as_elsewhere(self):
        shown = self.call(self.home, self.root, "task", "edit", self.task,
                          "--priority", 1).stdout
        self.assertNotIn("repo:", shown)

    def test_belongs_to_names_the_key(self):
        moved = json.loads(self.call(self.home, self.home, "task", "edit", self.task,
                                     "--belongs-to", self.root, "--json").stdout)
        self.assertEqual(moved["item"]["repo"], KEY)

    def test_delivery_is_verified_in_this_checkout(self):
        (self.root / "file.txt").write_text("one\n", encoding="utf-8")
        git(self.root, "add", "file.txt")
        git(self.root, "commit", "-qm", f"fix: the thing\n\nDelivers: sd:{self.task}\n")
        sha = git(self.root, "rev-parse", "HEAD")
        done = json.loads(self.call(self.home, self.root, "task", "status", self.task,
                                    "done", "--delivered-by", sha, "--json").stdout)
        self.assertEqual(done["item"]["status"], "done")

    def test_the_work_item_reads_by_its_key(self):
        item_dir = self.root / "docs" / "work" / ITEM
        self.assertEqual(sd_lib.external_id(self.root, item_dir),
                         f"{KEY}::docs/work/{ITEM}/prd.md")
        rows = sd_lib.Rows(self.root)
        self.assertTrue(rows.opened, rows.problem)
        self.assertEqual(rows.base, KEY)
        self.assertEqual(rows.status(item_dir), ("planning", ""))


class NoRawRepoProbe(unittest.TestCase):
    """design.md test 7 for the pack: every `repo` lookup reaches every stored form."""

    def test_only_the_fallback_probes_one_form(self):
        pattern = re.compile(r"\b(?:path|repo)\s*=\s*\?")
        found = []
        for path in sorted((ROOT / "bin").iterdir()):
            if not path.is_file() or path.suffix not in ("", ".py"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            found += [f"{path.name}:{number}" for number, line in enumerate(text.splitlines(), 1)
                      if pattern.search(line)]
        # `sd_lib.repo_row`'s fallback, for a library without `repos.row_for`,
        # which stores one form only.
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("sd_lib.py:"), found)


if __name__ == "__main__":
    unittest.main()
