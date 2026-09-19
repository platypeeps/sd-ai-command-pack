"""sd:789 -- what `sd-status` says about a mode the remote lowered.

Criterion 11 of sd:10 asks for two things when a `mode: full` repository's
remote starts answering `no`: that the item carries a demotion note, which
`tests/test_guest_artifact_refusal.py` covers, and "that `sd-status` names the
artifacts already in the shared tree" (`prd.md:1385-1389`, and the requirement
text at `:866-868`: "What is already in the shared tree from before the answer
changed is the operator's to move, and `sd-status` names it").

The refusal keeps new planning artifacts out. It can do nothing about what the
shared tree was already carrying on the day the answer changed, and moving
those needs their paths, not their number. So the list is enumerated from the
remote's default branch as this checkout last saw it, and every expectation
below is enumerated from the fixture repository at runtime -- `git ls-tree`
over the same three trees `sd_lib.GUEST_REFUSED_DIRS` names -- rather than
typed out here, so a tree that gains a file cannot leave the test behind.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402


def _load_status():
    """`bin/sd-status` as a module, under a name of this file's own.

    Loaded here rather than imported from `tests/test_sd_status.py`, which
    owns its own copy under `sd_status_under_test`: two modules loading one
    file is cheaper than two test files sharing one module object, and this
    file is meant to be readable without the other one.
    """
    path = REPO_ROOT / "bin" / "sd-status"
    loader = importlib.machinery.SourceFileLoader("sd_status_shared_tree", str(path))
    spec = importlib.util.spec_from_file_location("sd_status_shared_tree", str(path), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sd_status_shared_tree"] = module
    loader.exec_module(module)
    return module


status = _load_status()

LOWERED = sd_lib.RemoteAnswer(False, True, "sven/thing lets mallory push too")


class SharedTree(unittest.TestCase):
    """A repository whose remote default branch already carries planning artifacts."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.root = self.tmp / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main", ".")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("remote", "add", "origin", "https://github.com/sven/thing.git")

    def git(self, *args: str) -> str:
        done = subprocess.run(["git", *args], cwd=str(self.root), check=True,
                              capture_output=True, text=True)
        return done.stdout.strip()

    def commit(self, *paths: str) -> str:
        for name in paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{name}\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "seed")
        return self.git("rev-parse", "HEAD")

    def publish(self, commit: str | None = None) -> None:
        """Make the shared tree what this checkout last saw on `origin/main`."""

        self.git("update-ref", "refs/remotes/origin/main", commit or self.git("rev-parse", "HEAD"))

    def carried(self) -> list[str]:
        """What the shared branch carries under the three trees, asked of git.

        The expectation is enumerated here, from the repository and from
        `sd_lib.GUEST_REFUSED_DIRS`, so neither a fourth tree nor a file this
        test never mentions can pass unnoticed.
        """

        listed = self.git("ls-tree", "-r", "--name-only", "refs/remotes/origin/main")
        return sorted(
            name for name in listed.splitlines()
            if any(name == d or name.startswith(d + "/") for d in sd_lib.GUEST_REFUSED_DIRS)
        )

    # -- the helper ---------------------------------------------------------

    def test_every_planning_artifact_the_shared_branch_carries_is_named(self) -> None:
        self.commit(
            "docs/work/2026-01-01-a-thing/prd.md",
            "docs/work/2026-01-01-a-thing/design.md",
            "docs/spec/a.md",
            "docs/decisions/d.md",
            "README.md",
        )
        self.publish()
        expected = self.carried()
        self.assertEqual(len(expected), 4, expected)
        self.assertEqual(list(sd_lib.shared_tree_artifacts(self.root)), expected)

    def test_nothing_outside_the_three_trees_is_named(self) -> None:
        self.commit("README.md", "bin/tool.py", "docs/workbook/a.md", "docs/specification.md")
        self.publish()
        self.assertEqual(self.carried(), [])
        self.assertEqual(sd_lib.shared_tree_artifacts(self.root), ())

    def test_an_artifact_only_this_branch_carries_is_not_in_the_shared_tree(self) -> None:
        """The question is what the shared tree holds, not what this checkout does."""

        shared = self.commit("README.md")
        self.publish(shared)
        self.git("checkout", "-q", "-b", "topic")
        self.commit("docs/work/2026-01-01-a-thing/prd.md")
        (self.root / "docs/spec").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/spec/uncommitted.md").write_text("draft\n", encoding="utf-8")
        self.assertEqual(sd_lib.shared_tree_artifacts(self.root), ())

    def test_a_checkout_with_no_remote_has_no_shared_tree(self) -> None:
        self.git("remote", "remove", "origin")
        self.commit("docs/work/i/prd.md")
        self.assertEqual(sd_lib.shared_tree_artifacts(self.root), ())

    def test_a_remote_this_clone_has_never_fetched_names_nothing(self) -> None:
        """No ref, no answer -- and nothing is fetched to go and find out."""

        self.commit("docs/work/i/prd.md")
        self.assertIsNone(sd_lib.git_output(["rev-parse", "--verify", "--quiet",
                                             "refs/remotes/origin/main"], self.root))
        self.assertEqual(sd_lib.shared_tree_artifacts(self.root), ())

    # -- the section --------------------------------------------------------

    def setup_with(self, resolved: str, lowered: sd_lib.RemoteAnswer | None) -> dict[str, Any]:
        with mock.patch.object(sd_lib, "mode_answer", return_value=(resolved, lowered)):
            return status.setup_section(self.root)

    def test_a_lowered_mode_carries_the_reason_and_the_list(self) -> None:
        self.commit("docs/work/2026-01-01-a-thing/prd.md", "docs/decisions/d.md")
        self.publish()
        section = self.setup_with("guest", LOWERED)
        self.assertEqual(section["demoted"], LOWERED.reason)
        self.assertEqual(section["shared_tree"], self.carried())

    def test_a_full_repository_is_not_asked_to_move_its_own_documents(self) -> None:
        """`full` is where `docs/work/` belongs, so there is nothing to name."""

        self.commit("docs/work/2026-01-01-a-thing/prd.md")
        self.publish()
        self.assertTrue(self.carried())
        section = self.setup_with("full", None)
        self.assertEqual(section["shared_tree"], [])
        self.assertEqual(section["demoted"], "")

    def test_a_written_guest_names_the_list_with_no_demotion_reason(self) -> None:
        """Nobody lowered anything; the artifacts are still the operator's to move."""

        self.commit("docs/spec/a.md")
        self.publish()
        section = self.setup_with("guest", None)
        self.assertEqual(section["demoted"], "")
        self.assertEqual(section["shared_tree"], self.carried())

    # -- the report ---------------------------------------------------------

    def rendered(self, section: dict[str, Any]) -> str:
        stream = io.StringIO()
        status.render(self.report(section), stream)
        return stream.getvalue()

    def report(self, section: dict[str, Any]) -> dict[str, Any]:
        """The smallest whole report `render` accepts, with `setup` under test."""

        return {
            "repo": str(self.root),
            "pack": {"root": str(self.root), "branch": "main", "head": "0000000", "dirty": False},
            "inventory": {"rows": [], "unchecked": []},
            "abnormalities": {"summary": "clear", "classes": [], "findings": [],
                              "unchecked": []},
            "work": {"available": False, "reason": "no database", "status_source": "file",
                     "total": 0, "active": 0, "counts": {}, "items": []},
            "pull_requests": {"repo": "sven/thing", "pull_requests": [],
                              "available": False, "reason": "no gh"},
            "setup": section,
            "protection": {"available": False, "reason": "no remote", "gaps": [],
                           "accepted": [], "detail": {}},
            "handoff": {"packet": {"pending": False, "detail": "none written"}},
            "backends": [],
            "residue": [],
            "issues": {"available": False, "reason": "no index", "needs_you": [], "other": []},
            "jira": {"available": False, "reason": "no database", "freshness": None, "rows": []},
            "threads": {"available": False, "reason": "no database", "rows": []},
            "contributions": {"available": False, "reason": "no database", "rows": []},
            "pending": [], "actions": [], "next": None,
        }

    def test_the_report_prints_every_path_under_detected_setup(self) -> None:
        self.commit("docs/work/2026-01-01-a-thing/prd.md", "docs/spec/a.md", "docs/decisions/d.md")
        self.publish()
        section = self.setup_with("guest", LOWERED)
        text = self.rendered(section)
        self.assertIn(f"lowered to guest: {LOWERED.reason}", text)
        block = text.split("detected setup", 1)[1]
        for path in self.carried():
            self.assertIn(f"\n    {path}\n", block, path)
        self.assertNotIn("more\n", block)

    def test_a_long_list_shows_ten_and_says_how_many_it_did_not(self) -> None:
        self.commit(*[f"docs/work/2026-01-{day:02d}-a-thing/prd.md" for day in range(1, 15)])
        self.publish()
        carried = self.carried()
        self.assertEqual(len(carried), 14)
        text = self.rendered(self.setup_with("guest", LOWERED))
        block = text.split("detected setup", 1)[1]
        for path in carried[:10]:
            self.assertIn(f"\n    {path}\n", block, path)
        for path in carried[10:]:
            self.assertNotIn(path, block, path)
        self.assertIn("... and 4 more", block)

    def test_a_repository_with_nothing_to_move_prints_no_such_lines(self) -> None:
        self.commit("README.md")
        self.publish()
        text = self.rendered(self.setup_with("full", None))
        self.assertIn("detected setup", text)
        self.assertNotIn("shared tree", text)
        self.assertNotIn("lowered to guest", text)


if __name__ == "__main__":
    unittest.main()
