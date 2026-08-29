"""Fixtures for bin/sd_lib.py: real git repositories, real temporary trees.

Nothing here mocks git. Worktree behaviour is the whole point of two of these
tests, and a mocked `git rev-parse` would have agreed with every wrong answer.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402

PRD = """---
title: {title}
status: {status}
created: 2026-08-29
{extra}---

# PRD
"""


def prd(title: str = "An item", status: str = "planning", **extra: str) -> str:
    tail = "".join(f"{key}: {value}\n" for key, value in extra.items())
    return PRD.format(title=title, status=status, extra=tail)


class Fixture(unittest.TestCase):
    """A throwaway directory, and a git repository when one is asked for."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()

    def git(self, cwd: pathlib.Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )

    def make_repo(self, name: str = "repo") -> pathlib.Path:
        root = self.tmp / name
        root.mkdir(parents=True)
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.email", "test@example.com")
        self.git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("seed\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-m", "seed")
        return root

    def add_worktree(self, root: pathlib.Path, name: str = "wt") -> pathlib.Path:
        path = self.tmp / name
        self.git(root, "worktree", "add", "-b", name, str(path))
        self.addCleanup(
            lambda: subprocess.run(
                ["git", "worktree", "remove", "--force", str(path)],
                cwd=str(root),
                check=False,
                capture_output=True,
            )
        )
        return path.resolve()

    def write_local_block(self, root: pathlib.Path, body: str) -> pathlib.Path:
        path = root / sd_lib.LOCAL_FILE_NAME
        path.write_text(
            f"# Local notes\n\n{sd_lib.LOCAL_BLOCK_START}\n{body}{sd_lib.LOCAL_BLOCK_END}\n",
            encoding="utf-8",
        )
        return path

    def write_item(
        self, root: pathlib.Path, relative: str, text: str | None = None
    ) -> pathlib.Path:
        item = root / relative
        item.mkdir(parents=True)
        if text is not None:
            (item / "prd.md").write_text(text, encoding="utf-8")
        return item


class RepoRootTests(Fixture):
    def test_outside_a_repository_is_none(self) -> None:
        outside = self.tmp / "loose"
        outside.mkdir()
        self.assertIsNone(sd_lib.repo_root(outside))

    def test_main_checkout_resolves_to_itself(self) -> None:
        root = self.make_repo()
        nested = root / "a" / "b"
        nested.mkdir(parents=True)
        self.assertEqual(sd_lib.repo_root(nested), root.resolve())
        self.assertEqual(sd_lib.main_worktree_root(root), root.resolve())

    def test_linked_worktree_resolves_to_the_worktree_not_the_checkout(self) -> None:
        root = self.make_repo()
        worktree = self.add_worktree(root)
        self.assertEqual(sd_lib.repo_root(worktree), worktree)
        self.assertNotEqual(sd_lib.repo_root(worktree), root.resolve())
        self.assertEqual(sd_lib.main_worktree_root(worktree), root.resolve())

    def test_a_missing_directory_is_not_a_repository(self) -> None:
        self.assertIsNone(sd_lib.repo_root(self.tmp / "nowhere" / "deeper"))


class LocalBlockTests(Fixture):
    def test_missing_file_is_empty(self) -> None:
        root = self.make_repo()
        self.assertEqual(sd_lib.local_block(root), {})

    def test_file_without_the_block_is_empty(self) -> None:
        root = self.make_repo()
        (root / sd_lib.LOCAL_FILE_NAME).write_text("just notes\n", encoding="utf-8")
        self.assertEqual(sd_lib.local_block(root), {})

    def test_scalars_comments_and_quotes(self) -> None:
        root = self.make_repo()
        self.write_local_block(
            root,
            "# a comment line\n"
            "mode: minimal\n"
            "check: make ci   # trailing comment\n"
            'title: "a # inside quotes"\n'
            "\n",
        )
        self.assertEqual(
            sd_lib.local_block(root),
            {"mode": "minimal", "check": "make ci", "title": "a # inside quotes"},
        )

    def test_a_linked_worktree_reads_the_main_checkout_copy(self) -> None:
        root = self.make_repo()
        self.write_local_block(root, "mode: guest\n")
        worktree = self.add_worktree(root)
        self.assertFalse((worktree / sd_lib.LOCAL_FILE_NAME).exists())
        self.assertEqual(sd_lib.local_block(worktree), {"mode": "guest"})
        self.assertEqual(sd_lib.local_block_path(worktree), root.resolve() / "CLAUDE.local.md")

    def test_malformed_blocks_are_controlled_errors(self) -> None:
        cases = [
            ("no end marker", f"{sd_lib.LOCAL_BLOCK_START}\nmode: full\n"),
            ("end without start", f"{sd_lib.LOCAL_BLOCK_END}\n"),
            (
                "duplicate start",
                f"{sd_lib.LOCAL_BLOCK_START}\n{sd_lib.LOCAL_BLOCK_START}\n"
                f"{sd_lib.LOCAL_BLOCK_END}\n",
            ),
            (
                "duplicate end",
                f"{sd_lib.LOCAL_BLOCK_START}\n{sd_lib.LOCAL_BLOCK_END}\n"
                f"{sd_lib.LOCAL_BLOCK_END}\n",
            ),
            (
                "line that is not key: value",
                f"{sd_lib.LOCAL_BLOCK_START}\nnot a pair\n{sd_lib.LOCAL_BLOCK_END}\n",
            ),
        ]
        for label, text in cases:
            with self.subTest(label):
                with self.assertRaises(sd_lib.ConfigError):
                    sd_lib.parse_local_block(text)


class ModeTests(Fixture):
    def test_default_and_declared_modes(self) -> None:
        root = self.make_repo()
        self.assertEqual(sd_lib.mode(root), "full")
        for value in sd_lib.MODES:
            with self.subTest(value):
                self.write_local_block(root, f"mode: {value}\n")
                self.assertEqual(sd_lib.mode(root), value)

    def test_unknown_mode_is_a_controlled_error(self) -> None:
        root = self.make_repo()
        self.write_local_block(root, "mode: readonly\n")
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.mode(root)


class MachineConfigTests(Fixture):
    def config_at(self, home: pathlib.Path) -> pathlib.Path:
        path = home / sd_lib.CONFIG_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_missing_file_is_empty(self) -> None:
        self.assertEqual(sd_lib.machine_config(self.tmp / "absent.json"), {})

    def test_reads_json(self) -> None:
        path = self.config_at(self.tmp / "cfg")
        path.write_text(json.dumps({"repos": {"a": 1}}), encoding="utf-8")
        self.assertEqual(sd_lib.machine_config(path), {"repos": {"a": 1}})

    def test_malformed_json_is_a_controlled_error(self) -> None:
        path = self.config_at(self.tmp / "cfg")
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.machine_config(path)

    def test_non_object_json_is_a_controlled_error(self) -> None:
        path = self.config_at(self.tmp / "cfg")
        path.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.machine_config(path)

    def test_default_path_follows_xdg_config_home(self) -> None:
        home = self.tmp / "xdg"
        path = self.config_at(home)
        path.write_text(json.dumps({"seen": True}), encoding="utf-8")
        previous = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(home)
        try:
            self.assertEqual(sd_lib.machine_config_path(), path)
            self.assertEqual(sd_lib.machine_config(), {"seen": True})
        finally:
            if previous is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = previous


class DeriveStatusTests(Fixture):
    def test_each_declared_status(self) -> None:
        root = self.tmp / "tree"
        for status in sd_lib.ITEM_STATUSES:
            with self.subTest(status):
                extra = {"branch": "task/x"} if status == "in_progress" else {}
                item = self.write_item(
                    root,
                    f"docs/work/2026-08-29-{status}",
                    prd(status=status, **extra),
                )
                report = sd_lib.status_report(item)
                self.assertEqual(sd_lib.derive_status(item), status)
                self.assertEqual(report.inconsistencies, ())
                self.assertFalse(report.archived)

    def test_archive_location_beats_the_frontmatter(self) -> None:
        root = self.tmp / "tree"
        item = self.write_item(
            root,
            "docs/work/archive/2026-06/2026-06-01-old",
            prd(status="planning"),
        )
        report = sd_lib.status_report(item)
        self.assertEqual(report.status, "done")
        self.assertTrue(report.archived)

    def test_in_progress_without_a_branch_is_reported_not_raised(self) -> None:
        root = self.tmp / "tree"
        item = self.write_item(
            root, "docs/work/2026-08-29-loose", prd(status="in_progress")
        )
        report = sd_lib.status_report(item)
        self.assertEqual(report.status, "in_progress")
        self.assertEqual(len(report.inconsistencies), 1)
        self.assertIn("branch", report.inconsistencies[0])

    def test_unknown_and_missing_frontmatter(self) -> None:
        root = self.tmp / "tree"
        cases = [
            ("unknown status", prd(status="blocked")),
            ("no frontmatter", "# PRD\n"),
            ("no prd at all", None),
        ]
        for index, (label, text) in enumerate(cases):
            with self.subTest(label):
                item = self.write_item(root, f"docs/work/2026-08-29-bad{index}", text)
                report = sd_lib.status_report(item)
                self.assertEqual(report.status, "unknown")
                self.assertTrue(report.inconsistencies)


class WorkItemsTests(Fixture):
    def test_enumerates_active_and_archived_from_the_filesystem(self) -> None:
        root = self.tmp / "tree"
        self.write_item(
            root,
            "docs/work/2026-08-29-alpha",
            prd(title="Alpha", status="in_progress", branch="task/alpha"),
        )
        self.write_item(root, "docs/work/2026-08-28-beta", prd(title="Beta", status="ready"))
        self.write_item(
            root,
            "docs/work/archive/2026-06/2026-06-01-gamma",
            prd(title="Gamma", status="ready"),
        )
        (root / "docs/work/README.md").write_text("index\n", encoding="utf-8")

        items = sd_lib.work_items(root)
        self.assertEqual([item.slug for item in items], ["beta", "alpha", "gamma"])
        by_slug = {item.slug: item for item in items}
        self.assertEqual(by_slug["alpha"].status, "in_progress")
        self.assertEqual(by_slug["alpha"].branch, "task/alpha")
        self.assertEqual(by_slug["alpha"].title, "Alpha")
        self.assertEqual(by_slug["alpha"].created, "2026-08-29")
        self.assertFalse(by_slug["alpha"].archived)
        self.assertEqual(by_slug["gamma"].status, "done")
        self.assertTrue(by_slug["gamma"].archived)

    def test_no_work_directory_is_an_empty_list(self) -> None:
        self.assertEqual(sd_lib.work_items(self.tmp / "empty"), [])


class EntrypointTests(Fixture):
    _made = 0

    def repo_with(self, files: dict[str, str]) -> pathlib.Path:
        EntrypointTests._made += 1
        root = self.tmp / f"tree{EntrypointTests._made}"
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_autodetect_branches(self) -> None:
        makefile = ".PHONY: check test lint\n\ncheck: test lint\n\ntest:\n\techo t\n\nlint:\n\techo l\n"
        taskfile = "version: '3'\n\ntasks:\n  test:\n    cmds:\n      - echo t\n  lint:\n    cmds:\n      - echo l\n"
        package = json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}})
        cases = [
            (
                "makefile",
                {"Makefile": makefile},
                "makefile",
                {"check": ["make", "check"], "test": ["make", "test"], "lint": ["make", "lint"]},
            ),
            (
                "taskfile",
                {"Taskfile.yml": taskfile},
                "taskfile",
                {"test": ["task", "test"], "lint": ["task", "lint"]},
            ),
            (
                "package.json",
                {"package.json": package},
                "package.json",
                {"test": ["npm", "run", "test"], "lint": ["npm", "run", "lint"]},
            ),
            (
                "cargo",
                {"Cargo.toml": "[package]\nname = 'x'\n"},
                "cargo",
                {"check": ["cargo", "check"], "test": ["cargo", "test"]},
            ),
            (
                "pyproject",
                {"pyproject.toml": "[project]\nname = 'x'\n"},
                "pyproject",
                {"test": ["python3", "-m", "pytest"]},
            ),
            ("nothing", {"README.md": "hi\n"}, None, {}),
        ]
        for label, files, source, commands in cases:
            with self.subTest(label):
                root = self.repo_with(files)
                detection = sd_lib.detect_entrypoints(root)
                self.assertEqual(detection.source, source)
                self.assertEqual(detection.commands, commands)
                self.assertEqual(sd_lib.entrypoints(root), commands)
                self.assertTrue(detection.reason)

    def test_probe_order_stops_at_the_first_hit(self) -> None:
        root = self.repo_with(
            {
                "Makefile": "check:\n\techo c\n",
                "Taskfile.yml": "tasks:\n  test:\n    cmds:\n      - echo t\n",
                "package.json": json.dumps({"scripts": {"test": "jest"}}),
            }
        )
        self.assertEqual(sd_lib.detect_entrypoints(root).source, "makefile")

    def test_a_makefile_without_those_targets_does_not_stop_the_search(self) -> None:
        root = self.repo_with(
            {
                "Makefile": "build:\n\techo b\n\ninstall:\n\techo i\n",
                "package.json": json.dumps({"scripts": {"test": "jest"}}),
            }
        )
        detection = sd_lib.detect_entrypoints(root)
        self.assertEqual(detection.source, "package.json")
        self.assertEqual(detection.commands, {"test": ["npm", "run", "test"]})

    def test_the_local_block_wins(self) -> None:
        root = self.make_repo()
        (root / "Makefile").write_text("check:\n\techo c\n", encoding="utf-8")
        self.write_local_block(root, "check: ./ci.sh --fast\nlint: ruff check .\n")
        detection = sd_lib.detect_entrypoints(root)
        self.assertEqual(detection.source, "local-block")
        self.assertEqual(
            detection.commands,
            {"check": ["./ci.sh", "--fast"], "lint": ["ruff", "check", "."]},
        )

    def test_an_unparseable_local_command_is_a_controlled_error(self) -> None:
        root = self.make_repo()
        self.write_local_block(root, "check: ./ci.sh 'unbalanced\n")
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.detect_entrypoints(root)

    def test_a_malformed_package_json_is_a_controlled_error(self) -> None:
        root = self.repo_with({"package.json": "{oops"})
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.detect_entrypoints(root)


class SharedParserTests(unittest.TestCase):
    """bin/sd-docs-lint reads frontmatter through this module, not a twin."""

    def test_docs_lint_imports_the_shared_parser(self) -> None:
        import importlib.machinery
        import importlib.util

        path = REPO_ROOT / "bin" / "sd-docs-lint"
        loader = importlib.machinery.SourceFileLoader("sd_docs_lint_shared", str(path))
        spec = importlib.util.spec_from_loader("sd_docs_lint_shared", loader)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIs(module.parse_frontmatter, sd_lib.parse_frontmatter)

    def test_frontmatter_conventions_are_unchanged(self) -> None:
        cases: list[tuple[str, str, dict[str, str] | None]] = [
            ("plain", "---\ntitle: A\nstatus: ready\n---\n", {"title": "A", "status": "ready"}),
            ("quoted", '---\ntitle: "PARKED: a thing"\n---\n', {"title": "PARKED: a thing"}),
            ("no block", "# PRD\n", None),
            ("unterminated", "---\ntitle: A\n", None),
            ("hash is literal", "---\ntitle: a # b\n---\n", {"title": "a # b"}),
        ]
        for label, text, expected in cases:
            with self.subTest(label):
                self.assertEqual(sd_lib.parse_frontmatter(text), expected)


if __name__ == "__main__":
    unittest.main()
