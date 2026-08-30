"""Consumer removal: what it deletes, what it refuses to, and in what order.

This is the one surface in the pack that deletes files in somebody else's
repository, thousands of them per repository. Every test here builds its own
repository rather than reading one of the real consumers, so the suite says the
same thing on a machine that has none of them checked out -- and so that no
count in this file can go stale against the measurements in the work item.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import unittest
from typing import Any

BIN = pathlib.Path(__file__).resolve().parent.parent / "bin"


def _load(name: str, module_name: str) -> Any:
    path = BIN / name
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_file_location(module_name, str(path), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


migrate_trellis = _load("migrate-trellis", "migrate_trellis_under_test")


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init(repo: pathlib.Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")


def _write(repo: pathlib.Path, rel: str, text: str) -> pathlib.Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _commit(repo: pathlib.Path, message: str = "fixture") -> None:
    _git(repo, "add", "-A", "-f")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


class ConsumerFixture:
    """A consumer repository and the pack checkout its receipt points back at.

    The pack side carries a real `v0.72.0` tag, because the tombstone blob is
    the removal's only baseline for telling an untouched install from a file
    the consumer edited, and a stub that returns bytes without a tag would test
    the wrong thing.
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.repo = root / "consumer"
        self.pack = root / "pack"
        _init(self.repo)
        _init(self.pack)
        self.shipped: dict[str, bytes] = {}

    def ship(self, source: str, target: str, body: str) -> None:
        """Record that the pack shipped `source` and installed it at `target`."""
        self.shipped[target] = body.encode()
        _write(self.pack, source, body)
        _write(self.repo, target, body)
        listing = self.repo / migrate_trellis.PACK_RECEIPT / "installed-targets.txt"
        listing.parent.mkdir(parents=True, exist_ok=True)
        with listing.open("a", encoding="utf-8") as handle:
            handle.write(target + "\n")
        manifest = self.repo / migrate_trellis.PACK_RECEIPT / "manifest.json"
        rows = json.loads(manifest.read_text())["files"] if manifest.exists() else []
        rows.append({"source": source, "target": target})
        manifest.write_text(json.dumps({"files": rows}, indent=2) + "\n", encoding="utf-8")

    def item(self, name: str, *, archive: str | None = None, prd: str = "# Item\n\nbody\n") -> None:
        base = ".trellis/tasks" if archive is None else f".trellis/tasks/archive/{archive}"
        _write(self.repo, f"{base}/{name}/prd.md", prd)

    def seal(self) -> None:
        _commit(self.pack, "pack")
        _git(self.pack, "tag", migrate_trellis.TOMBSTONE_TAG)
        _commit(self.repo, "consumer")

    def plan(self) -> list[Any]:
        return migrate_trellis.consumer_plan(self.repo, self.pack)

    def verdict(self, path: str) -> Any:
        matches = [v for v in self.plan() if v.path == path]
        assert len(matches) <= 1, f"{path} received {len(matches)} verdicts"
        return matches[0] if matches else None


class FixtureCase(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.fixture = ConsumerFixture(self.root)


class ReceiptAuthorityTests(FixtureCase):
    def test_untouched_install_is_deleted(self) -> None:
        self.fixture.ship("templates/prompt.md", ".github/prompts/x.prompt.md", "shipped\n")
        self.fixture.seal()
        verdict = self.fixture.verdict(".github/prompts/x.prompt.md")
        self.assertEqual(("delete", "pack-receipt"), (verdict.action, verdict.authority))

    def test_edited_install_is_kept(self) -> None:
        self.fixture.ship("templates/prompt.md", ".github/prompts/x.prompt.md", "shipped\n")
        _write(self.fixture.repo, ".github/prompts/x.prompt.md", "shipped\nand edited\n")
        self.fixture.seal()
        verdict = self.fixture.verdict(".github/prompts/x.prompt.md")
        self.assertEqual("keep", verdict.action)
        self.assertIn("edited", verdict.reason)

    def test_receipted_file_with_no_baseline_is_kept(self) -> None:
        """A receipt naming a source the tombstone never carried decides nothing."""
        _write(self.fixture.repo, ".github/prompts/y.prompt.md", "who knows\n")
        listing = self.fixture.repo / migrate_trellis.PACK_RECEIPT / "installed-targets.txt"
        listing.parent.mkdir(parents=True, exist_ok=True)
        listing.write_text(".github/prompts/y.prompt.md\n", encoding="utf-8")
        self.fixture.seal()
        verdict = self.fixture.verdict(".github/prompts/y.prompt.md")
        self.assertEqual("keep", verdict.action)
        self.assertIn("no v0.72.0 baseline", verdict.reason)

    def test_trellis_hash_match_deletes_and_drift_keeps(self) -> None:
        same = _write(self.fixture.repo, ".claude/hooks/session-start.py", "print(1)\n")
        drifted = _write(self.fixture.repo, ".claude/hooks/inject.py", "print(2)\n")
        _write(
            self.fixture.repo,
            migrate_trellis.TRELLIS_HASHES,
            json.dumps(
                {
                    "__version": 2,
                    "hashes": {
                        ".claude/hooks/session-start.py": migrate_trellis.sha256_of(same),
                        ".claude/hooks/inject.py": "0" * 64,
                    },
                }
            ),
        )
        self.fixture.seal()
        self.assertEqual("delete", self.fixture.verdict(".claude/hooks/session-start.py").action)
        self.assertEqual(
            "keep", self.fixture.verdict(str(drifted.relative_to(self.fixture.repo))).action
        )


class SurfaceNameTests(FixtureCase):
    def test_framework_namespaces_go_on_name_alone(self) -> None:
        for rel in (
            ".claude/skills/trellis-start/SKILL.md",
            ".claude/skills/sd-review/SKILL.md",
            ".claude/skills/security-best-practices/SKILL.md",
        ):
            _write(self.fixture.repo, rel, "content that never mentions the framework\n")
        self.fixture.seal()
        for rel in (
            ".claude/skills/trellis-start/SKILL.md",
            ".claude/skills/sd-review/SKILL.md",
            ".claude/skills/security-best-practices/SKILL.md",
        ):
            verdict = self.fixture.verdict(rel)
            self.assertEqual(
                ("delete", "surface-name"),
                (verdict.action, verdict.authority),
                rel,
            )

    def test_repo_own_skill_is_kept_and_reported(self) -> None:
        _write(self.fixture.repo, ".claude/skills/loadsmith-swift-app/SKILL.md", "ours\n")
        self.fixture.seal()
        verdict = self.fixture.verdict(".claude/skills/loadsmith-swift-app/SKILL.md")
        self.assertEqual(("keep", "none"), (verdict.action, verdict.authority))

    def test_loose_runtime_file_needs_content_evidence(self) -> None:
        _write(self.fixture.repo, ".opencode/lib/ours.js", "export const x = 1\n")
        _write(self.fixture.repo, ".opencode/lib/theirs.js", "// trellis context loader\n")
        self.fixture.seal()
        self.assertEqual("keep", self.fixture.verdict(".opencode/lib/ours.js").action)
        self.assertEqual(
            ("delete", "name+content"),
            (
                self.fixture.verdict(".opencode/lib/theirs.js").action,
                self.fixture.verdict(".opencode/lib/theirs.js").authority,
            ),
        )


class AgentsFileTests(FixtureCase):
    BLOCKS = (
        "<!-- TRELLIS:START -->\ntrellis prose\n<!-- TRELLIS:END -->\n"
        "<!-- SD-AI-COMMAND-PACK:ROUTING:START -->\nrouting\n"
        "<!-- SD-AI-COMMAND-PACK:ROUTING:END -->\n"
    )

    def test_both_marked_blocks_are_stripped_and_prose_survives(self) -> None:
        _write(
            self.fixture.repo,
            "AGENTS.md",
            f"# Our repo\n\nours before.\n\n{self.BLOCKS}\nours after.\n",
        )
        self.fixture.seal()
        verdict = self.fixture.verdict("AGENTS.md")
        self.assertEqual("edit", verdict.action)
        migrate_trellis.apply_consumer_plan(self.fixture.repo, [verdict])
        text = (self.fixture.repo / "AGENTS.md").read_text()
        self.assertIn("ours before.", text)
        self.assertIn("ours after.", text)
        for begin, end in migrate_trellis.AGENTS_MARKERS:
            self.assertNotIn(begin, text)
            self.assertNotIn(end, text)

    def test_file_that_is_only_blocks_is_planned_as_a_deletion(self) -> None:
        """The plan has to name the outcome; `edit` that unlinks is a lie."""
        _write(self.fixture.repo, "AGENTS.md", self.BLOCKS)
        self.fixture.seal()
        self.assertEqual("delete", self.fixture.verdict("AGENTS.md").action)

    def test_unmarked_file_is_never_touched(self) -> None:
        _write(self.fixture.repo, "AGENTS.md", "# Ours alone\n")
        self.fixture.seal()
        self.assertEqual("keep", self.fixture.verdict("AGENTS.md").action)


class StructuredFileTests(FixtureCase):
    def test_settings_keeps_repo_entries_and_drops_framework_ones(self) -> None:
        payload = {
            "env": {"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1", "OURS": "keep"},
            "statusLine": {"command": ".claude/hooks/statusline.py"},
            "hooks": {
                "SessionStart": [{"hooks": [{"command": ".claude/hooks/session-start.py"}]}],
                "Stop": [{"hooks": [{"command": "./our-own-check.sh"}]}],
            },
        }
        remaining = migrate_trellis.prune_framework_settings(payload)
        self.assertEqual({"OURS": "keep"}, remaining["env"])
        self.assertNotIn("statusLine", remaining)
        self.assertEqual(["Stop"], list(remaining["hooks"]))

    def test_settings_file_goes_only_when_nothing_of_theirs_remains(self) -> None:
        _write(
            self.fixture.repo,
            ".claude/settings.json",
            json.dumps({"statusLine": {"command": ".claude/hooks/statusline.py"}}),
        )
        _write(
            self.fixture.repo,
            ".gemini/settings.json",
            json.dumps({"statusLine": {"command": ".claude/hooks/statusline.py"}, "ours": True}),
        )
        self.fixture.seal()
        self.assertEqual("delete", self.fixture.verdict(".claude/settings.json").action)
        self.assertEqual("edit", self.fixture.verdict(".gemini/settings.json").action)

    def test_opencode_stub_waits_for_its_plugins(self) -> None:
        stub = json.dumps({"dependencies": {"@opencode-ai/plugin": "^1"}})
        _write(self.fixture.repo, ".opencode/package.json", stub)
        _write(self.fixture.repo, ".opencode/plugins/ours.js", "export const ours = 1\n")
        self.fixture.seal()
        self.assertEqual("keep", self.fixture.verdict(".opencode/package.json").action)

        _write(self.fixture.repo, ".opencode/plugins/ours.js", "// trellis session hook\n")
        _commit(self.fixture.repo, "framework plugin")
        verdict = self.fixture.verdict(".opencode/package.json")
        self.assertEqual(("delete", "structured"), (verdict.action, verdict.authority))

    def test_package_json_goes_by_what_survives_not_by_what_it_contains(self) -> None:
        """A two-line `{"type": "module"}` was surviving an emptied tree."""
        _write(self.fixture.repo, ".opencode/package.json", json.dumps({"type": "module"}))
        _write(self.fixture.repo, ".opencode/plugins/p.js", "// trellis\n")
        self.fixture.seal()
        self.assertEqual("delete", self.fixture.verdict(".opencode/package.json").action)


class ImportBeforeRemovalTests(FixtureCase):
    """The removal deletes `.trellis/tasks`. The items have to land first."""

    def run_consumer(self, *, apply: bool) -> int:
        """Same call the CLI makes, with its report kept out of the test output."""
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                return migrate_trellis.run_consumer(
                    self.fixture.repo, self.fixture.pack, apply=apply
                )

    def test_apply_imports_every_item_before_deleting_the_tree(self) -> None:
        self.fixture.item("06-01-alpha")
        self.fixture.item("07-02-beta", archive="2026-07")
        self.fixture.seal()
        self.assertEqual(0, self.run_consumer(apply=True))
        self.assertFalse((self.fixture.repo / ".trellis").exists())
        work = self.fixture.repo / "docs" / "work"
        self.assertTrue((work / "2026-06-01-alpha" / "prd.md").is_file())
        self.assertTrue((work / "archive" / "2026-07" / "2026-07-02-beta" / "prd.md").is_file())

    def test_dry_run_writes_nothing(self) -> None:
        self.fixture.item("06-01-alpha")
        self.fixture.seal()
        before = subprocess.run(
            ["git", "-C", str(self.fixture.repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.run_consumer(apply=False)
        after = subprocess.run(
            ["git", "-C", str(self.fixture.repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertEqual(before, after)
        self.assertTrue((self.fixture.repo / ".trellis" / "tasks").is_dir())

    def test_an_item_with_no_prd_stops_the_run_before_anything_is_deleted(self) -> None:
        self.fixture.item("06-01-alpha")
        _write(self.fixture.repo, ".trellis/tasks/06-02-broken/notes.md", "no prd here\n")
        self.fixture.seal()
        self.assertEqual(1, self.run_consumer(apply=True))
        self.assertTrue((self.fixture.repo / ".trellis" / "tasks").is_dir())

    def test_a_directory_with_no_files_at_all_is_not_an_item(self) -> None:
        """`people-profiles` carries one: an untracked shell with an empty subdir."""
        self.fixture.item("06-01-alpha")
        (self.fixture.repo / ".trellis/tasks/00-bootstrap/research").mkdir(parents=True)
        self.fixture.seal()
        planned = migrate_trellis.planned_imports(self.fixture.repo)
        self.assertEqual(["06-01-alpha"], [item.source.name for item in planned])


class EmptyDirectoryTests(FixtureCase):
    def test_pruning_follows_the_deletions_rather_than_a_list_of_trees(self) -> None:
        """`.prism/` and `.gito/` were the two a hand-kept tree list had missed."""
        self.fixture.ship("templates/rules.json", ".prism/rules.json", "{}\n")
        self.fixture.ship("templates/config.toml", ".gito/config.toml", "x = 1\n")
        self.fixture.seal()
        verdicts = self.fixture.plan()
        migrate_trellis.apply_consumer_plan(self.fixture.repo, verdicts)
        self.assertFalse((self.fixture.repo / ".prism").exists())
        self.assertFalse((self.fixture.repo / ".gito").exists())

    def test_a_directory_still_holding_something_survives(self) -> None:
        self.fixture.ship("templates/rules.json", ".prism/rules.json", "{}\n")
        _write(self.fixture.repo, ".prism/ours.json", "{}\n")
        self.fixture.seal()
        migrate_trellis.apply_consumer_plan(self.fixture.repo, self.fixture.plan())
        self.assertTrue((self.fixture.repo / ".prism" / "ours.json").is_file())


class DerivedTreeTests(FixtureCase):
    """The tree set is enumerated, because the kept one was wrong."""

    def test_a_tree_no_list_mentioned_is_found_and_classified(self) -> None:
        _write(self.fixture.repo, ".codex/agents/trellis-check.toml", "name = 'x'\n")
        _write(self.fixture.repo, ".codex/skills/ours-own-thing/SKILL.md", "ours\n")
        self.fixture.seal()
        self.assertIn(".codex", migrate_trellis.platform_trees(self.fixture.repo))
        self.assertEqual("delete", self.fixture.verdict(".codex/agents/trellis-check.toml").action)
        self.assertEqual("keep", self.fixture.verdict(".codex/skills/ours-own-thing/SKILL.md").action)

    def test_a_nested_tree_is_read_against_its_own_prefix(self) -> None:
        """`.github/copilot/hooks/` makes `.github/copilot` the tree, not `.github`."""
        _write(self.fixture.repo, ".github/copilot/hooks/session-start.py", "# trellis\n")
        self.fixture.seal()
        self.assertIn(".github/copilot", migrate_trellis.platform_trees(self.fixture.repo))
        self.assertEqual(
            "delete", self.fixture.verdict(".github/copilot/hooks/session-start.py").action
        )

    def test_the_wholesale_trees_are_not_also_walked(self) -> None:
        """`.trellis/` has the shape of a platform tree and one owner already."""
        self.fixture.item("06-01-alpha")
        _write(self.fixture.repo, ".trellis/agents/trellis-check.md", "x\n")
        self.fixture.seal()
        self.assertNotIn(".trellis", migrate_trellis.platform_trees(self.fixture.repo))
        paths = [v.path for v in self.fixture.plan()]
        self.assertEqual(sorted(set(paths)), sorted(paths))

    def test_a_framework_named_file_at_a_trees_root_is_reached(self) -> None:
        _write(self.fixture.repo, ".github/agents/trellis-check.agent.md", "x\n")
        _write(self.fixture.repo, ".github/sd-github-review.json", "{}\n")
        _write(self.fixture.repo, ".github/dependabot.yml", "version: 2\n")
        self.fixture.seal()
        self.assertEqual("delete", self.fixture.verdict(".github/sd-github-review.json").action)
        self.assertIsNone(self.fixture.verdict(".github/dependabot.yml"))

    def test_an_empty_tree_set_classifies_nothing(self) -> None:
        """`git ls-files` with no pathspec lists the whole repository."""
        _write(self.fixture.repo, "src/main.py", "print(1)\n")
        self.fixture.seal()
        self.assertEqual((), migrate_trellis.platform_trees(self.fixture.repo))
        self.assertIsNone(self.fixture.verdict("src/main.py"))


class DanglingReferenceTests(FixtureCase):
    def test_a_surviving_file_naming_a_deleted_path_is_reported(self) -> None:
        _write(self.fixture.repo, ".claude/agents/trellis-check.md", "x\n")
        _write(self.fixture.repo, "scripts/ours.sh", "cat .claude/agents/trellis-check.md\n")
        _write(self.fixture.repo, "scripts/unrelated.sh", "echo hello\n")
        self.fixture.seal()
        doomed = {v.path for v in self.fixture.plan() if v.action == "delete"}
        found = migrate_trellis.dangling_references(self.fixture.repo, doomed)
        self.assertEqual([".claude/agents/trellis-check.md"], found["scripts/ours.sh"])
        self.assertNotIn("scripts/unrelated.sh", found)

    def test_a_file_that_is_itself_being_deleted_is_not_reported(self) -> None:
        _write(self.fixture.repo, ".claude/agents/trellis-check.md", "x\n")
        _write(self.fixture.repo, ".claude/agents/trellis-run.md", ".claude/agents/trellis-check.md\n")
        self.fixture.seal()
        doomed = {v.path for v in self.fixture.plan() if v.action == "delete"}
        self.assertEqual({}, migrate_trellis.dangling_references(self.fixture.repo, doomed))


class WholesaleTests(FixtureCase):
    def test_router_workflows_go_and_the_repos_own_lanes_stay(self) -> None:
        for name in migrate_trellis.ROUTER_WORKFLOWS:
            _write(self.fixture.repo, f".github/workflows/{name}", "on: push\n")
        _write(self.fixture.repo, ".github/workflows/ci.yml", "on: push\n")
        self.fixture.seal()
        for name in migrate_trellis.ROUTER_WORKFLOWS:
            self.assertEqual("delete", self.fixture.verdict(f".github/workflows/{name}").action)
        self.assertIsNone(self.fixture.verdict(".github/workflows/ci.yml"))

    def test_every_path_receives_at_most_one_verdict(self) -> None:
        """Two authorities reaching one path is how a keep and a delete collide."""
        self.fixture.ship("templates/rules.json", ".prism/rules.json", "{}\n")
        self.fixture.item("06-01-alpha")
        _write(self.fixture.repo, ".opencode/package.json", json.dumps({"dependencies": {}}))
        _write(self.fixture.repo, ".claude/settings.json", json.dumps({"ours": 1}))
        _write(self.fixture.repo, "AGENTS.md", AgentsFileTests.BLOCKS)
        self.fixture.seal()
        paths = [verdict.path for verdict in self.fixture.plan()]
        self.assertEqual(sorted(set(paths)), sorted(paths))


if __name__ == "__main__":
    unittest.main()
