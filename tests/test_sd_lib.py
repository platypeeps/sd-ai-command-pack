"""Fixtures for bin/sd_lib.py: real git repositories, real temporary trees.

Nothing here mocks git. Worktree behaviour is the whole point of two of these
tests, and a mocked `git rev-parse` would have agreed with every wrong answer.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_db  # noqa: E402 - `make setup` provisions it; `RowActivity` needs one
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

    def test_existing_nonfile_local_paths_refuse_instead_of_looking_absent(self):
        root = self.make_repo()
        local = root / sd_lib.LOCAL_FILE_NAME
        local.mkdir()
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.local_block(root)
        local.rmdir()
        local.symlink_to(root / "missing-target")
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.local_block(root)
        self.assertTrue(local.is_symlink())
        non_directory = root / "file"
        non_directory.write_text("file")
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.local_block(non_directory)

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

    def test_the_marker_check_stands_on_its_own(self) -> None:
        """`local_block_body` is the marker half of `parse_local_block`.

        The installer refreshes a block whose body the grammar refuses, so it
        needs the markers checked without the body parsed: a marker fault
        still raises, a body that is not `key: value` comes back as text, and
        no block at all is None rather than an empty dict.
        """
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.local_block_body(f"{sd_lib.LOCAL_BLOCK_START}\nmode: full\n")
        self.assertEqual(
            sd_lib.local_block_body(
                f"{sd_lib.LOCAL_BLOCK_START}\nnot a pair\n{sd_lib.LOCAL_BLOCK_END}\n"
            ),
            "\nnot a pair\n",
        )
        self.assertIsNone(sd_lib.local_block_body("no block here\n"))


class ModeTests(Fixture):
    def test_declared_modes_and_the_no_line_case_this_fixture_actually_is(self) -> None:
        """No `mode:` line is not a default of `full`; it is a question asked.

        This test used to read `mode(make_repo()) == "full"` and call that the
        default, which is what `bin/sd_lib.py` did and what criterion 11 says is
        wrong: `full` is the most permissive mode, and returning it for every
        repository with no line inverted detection in exactly the cases it
        exists for -- a fork, or a remote you cannot administer. `full` is still
        the right answer *here*, but for a stated reason rather than by default:
        `make_repo` adds no remote, so this is criterion 11's sixth case, where
        there is nobody to expose anything to. `tests/test_mode_detection.py`
        holds the other five and the composition rule; a repository with a
        remote is asked, and every answer but three yeses resolves to `guest`.
        """

        root = self.make_repo()
        self.assertIsNone(sd_lib.git_output(["remote", "get-url", "origin"], root))
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

    def test_pyproject_prefers_the_repo_venv_interpreter(self) -> None:
        # sd:1309: python3 on PATH is the one interpreter guaranteed not to
        # hold the repo's dependencies when they live in .venv.
        for layout in (("bin", "python"), ("Scripts", "python.exe")):
            with self.subTest(layout[0]):
                root = self.repo_with({"pyproject.toml": "[project]\nname = 'x'\n"})
                interpreter = root / ".venv" / layout[0] / layout[1]
                interpreter.parent.mkdir(parents=True)
                interpreter.write_text("", encoding="utf-8")
                interpreter.chmod(0o755)
                with unittest.mock.patch.dict(os.environ):
                    for name in ("VIRTUAL_ENV", "CONDA_PREFIX"):
                        os.environ.pop(name, None)
                    detection = sd_lib.detect_entrypoints(root)
                expected = str(pathlib.PurePosixPath(".venv", *layout))
                self.assertEqual(detection.commands, {"test": [expected, "-m", "pytest"]})
                self.assertIn(expected, detection.reason)

    def test_pyproject_keeps_an_activated_environment(self) -> None:
        # An activated environment (tox, another venv) is the caller's choice;
        # PATH resolves python3 to it, and the repo's .venv must not override.
        root = self.repo_with({"pyproject.toml": "[project]\nname = 'x'\n"})
        interpreter = root / ".venv" / "bin" / "python"
        interpreter.parent.mkdir(parents=True)
        interpreter.write_text("", encoding="utf-8")
        interpreter.chmod(0o755)
        activations = {
            "virtualenv": {"VIRTUAL_ENV": str(root / ".tox" / "py312")},
            "conda": {"CONDA_PREFIX": "/opt/conda/envs/py312", "CONDA_DEFAULT_ENV": "py312"},
            "conda base": {"CONDA_PREFIX": "/opt/conda", "CONDA_DEFAULT_ENV": "base"},
        }
        for label, activated in activations.items():
            with self.subTest(label), unittest.mock.patch.dict(os.environ, activated):
                detection = sd_lib.detect_entrypoints(root)
                self.assertEqual(detection.commands, {"test": ["python3", "-m", "pytest"]})

    def test_pyproject_ignores_a_venv_without_a_runnable_interpreter(self) -> None:
        root = self.repo_with({"pyproject.toml": "[project]\nname = 'x'\n", ".venv/pyvenv.cfg": ""})
        (root / ".venv" / "bin").mkdir()
        (root / ".venv" / "bin" / "python").symlink_to(root / "missing")
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("VIRTUAL_ENV", None)
            detection = sd_lib.detect_entrypoints(root)
        self.assertEqual(detection.commands, {"test": ["python3", "-m", "pytest"]})

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


class CorePolicyReadTests(Fixture):
    def test_supplied_home_and_xdg_select_policy_without_inheriting_the_process(self):
        one, two = self.tmp / "one", self.tmp / "two"
        one_path = one / ".config" / sd_lib.CONFIG_RELATIVE_PATH
        two_path = two / sd_lib.CONFIG_RELATIVE_PATH
        for path, value in ((one_path, "deny"), (two_path, "configured")):
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"config": {"sd": {"external_reviews": value}}}))
        self.assertEqual(sd_lib.core_setting("external_reviews", {"HOME": str(one)}), "deny")
        self.assertEqual(sd_lib.core_setting("external_reviews", {"HOME": str(one), "XDG_CONFIG_HOME": str(two)}), "configured")
        self.assertIsNone(sd_lib.core_setting("external_reviews", {"HOME": str(self.tmp / "fresh")}))

    def test_malformed_policy_never_becomes_a_grant(self):
        env = {"HOME": str(self.tmp)}
        path = self.tmp / ".config" / sd_lib.CONFIG_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        for value in ({"config": []}, {"config": {"sd": []}},
                      {"config": {"sd": {"external_reviews": None}}},
                      {"config": {"sd": {"external_reviews": True}}},
                      {"config": {"sd": {"external_reviews": "allow"}}}):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaises(sd_lib.ConfigError):
                    sd_lib.core_setting("external_reviews", env)

    def test_copilot_review_reads_its_three_words_and_nothing_else(self):
        env = {"HOME": str(self.tmp)}
        path = self.tmp / ".config" / sd_lib.CONFIG_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        self.assertIsNone(sd_lib.core_setting("copilot_review", env))
        for value in ("deep", "never", "always"):
            path.write_text(json.dumps({"config": {"sd": {"copilot_review": value}}}))
            self.assertEqual(sd_lib.core_setting("copilot_review", env), value)
        for value in ("Deep", "true", "", None, True):
            with self.subTest(value=value):
                path.write_text(json.dumps({"config": {"sd": {"copilot_review": value}}}))
                with self.assertRaises(sd_lib.ConfigError):
                    sd_lib.core_setting("copilot_review", env)


class CopilotPolicyResolution(unittest.TestCase):
    """The two pure halves both lanes share (sd:1328): who decides, and
    whether the decided word selects a review of this tier."""

    def test_machine_never_then_repository_then_machine_then_default(self):
        self.assertEqual(sd_lib.copilot_policy(True, "never"), ("never", "machine config"))
        self.assertEqual(sd_lib.copilot_policy(False, "never"), ("never", "machine config"))
        self.assertEqual(sd_lib.copilot_policy(True, "always"), ("deep", "repository"))
        self.assertEqual(sd_lib.copilot_policy(False, "always"), ("never", "repository"))
        self.assertEqual(sd_lib.copilot_policy(False, "deep"), ("never", "repository"))
        self.assertEqual(sd_lib.copilot_policy(None, "always"), ("always", "machine config"))
        self.assertEqual(sd_lib.copilot_policy(None, "never"), ("never", "machine config"))
        self.assertEqual(sd_lib.copilot_policy(None, None), (sd_lib.COPILOT_REVIEW_DEFAULT, "machine default"))

    def test_the_word_selects_by_tier_and_always_respects_skip(self):
        self.assertTrue(sd_lib.copilot_automatic("deep", "deep", 1))
        self.assertFalse(sd_lib.copilot_automatic("deep", "standard", 1))
        self.assertFalse(sd_lib.copilot_automatic("never", "deep", 1))
        self.assertTrue(sd_lib.copilot_automatic("always", "cheap", 1))
        self.assertTrue(sd_lib.copilot_automatic("always", "deep", 1))
        self.assertFalse(sd_lib.copilot_automatic("always", "skip", 0))


class RowActivity(unittest.TestCase):
    """`Rows.activity`: what the database last recorded against an item.

    The half of sd:455 that git cannot answer. A `row` checkout records a
    triage decision as a note against the item and touches no file, so the item
    tree is byte-identical before and after and the only evidence that anything
    happened is in the database.

    **And `updated_at` is not that evidence on its own.** `sd_db.writes.add_note`
    inserts the note and leaves the item row alone -- measured on item 492,
    whose `comment` note stands four and a half hours after an `updated_at`
    that still equals its `created_at`. A reader that stopped at the row would
    have called a freshly-triaged item as idle as an abandoned one, which is
    the defect being fixed rather than a detail of it.
    """

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = pathlib.Path(os.path.realpath(scratch.name))
        sd_db.initialise(home=self.home)
        self.connection = sd_db.connect(sd_db.default_path(self.home), write=True)
        self.addCleanup(self.connection.close)

        self.root = self.home / "checkout"
        self.item_dir = self.root / sd_lib.WORK_DIR / "2026-01-01-x"
        self.item_dir.mkdir(parents=True)
        (self.item_dir / "prd.md").write_text("# x\n", encoding="utf-8")
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"],
                     ["config", "user.name", "T"], ["add", "-A"],
                     ["commit", "-qm", "first"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True,
                           capture_output=True)
        self.root = self.root.resolve()
        sd_db.writes.upsert_repo(self.connection, str(self.root))
        self.item = sd_db.writes.create_item(
            self.connection, kind="work", title="x", status="planning",
            repo=str(self.root), source=sd_lib.ITEM_ROW_SOURCE,
            external_id=sd_lib.external_id(self.root, self.item_dir),
        )

    def read(self) -> str:
        """`Rows` opens the default database, so `HOME` is what points it here."""
        with unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            rows = sd_lib.Rows(self.root)
            try:
                return rows.activity(self.item_dir)
            finally:
                rows.close()

    def test_a_row_with_no_notes_answers_with_its_own_stamp(self) -> None:
        stamp = self.connection.execute(
            "SELECT updated_at FROM item WHERE id = ?", (self.item,)
        ).fetchone()["updated_at"]
        self.assertEqual(self.read(), stamp)

    def test_a_note_is_newer_than_the_row_it_was_written_against(self) -> None:
        """The whole point: the note moves the answer and `updated_at` does not.

        The row and its `opened as` note are backdated first, so the decision
        note is strictly newer on every run. Read in the same second, all three
        stamps were equal and the test proved nothing; read across a second
        boundary, `fetchone()` returned the `opened as` note and the test
        failed on a correct answer (sd:1402).
        """
        before = "2026-01-01T00:00:00+00:00"
        with self.connection:
            self.connection.execute("UPDATE item SET updated_at = ? WHERE id = ?", (before, self.item))
            self.connection.execute("UPDATE note SET timestamp = ? WHERE item = ?", (before, self.item))
        sd_db.add_note(self.connection, self.item, "decision", "triaged live")
        note = self.connection.execute(
            "SELECT timestamp FROM note WHERE item = ? AND kind = 'decision'", (self.item,)
        ).fetchone()["timestamp"]
        after = self.connection.execute(
            "SELECT updated_at FROM item WHERE id = ?", (self.item,)
        ).fetchone()["updated_at"]

        self.assertEqual(after, before, "add_note is not supposed to move the row")
        self.assertGreater(note, before)
        self.assertEqual(self.read(), note)

    def test_an_item_the_database_does_not_hold_answers_empty(self) -> None:
        """Empty is every absence, and it never lowers an age."""
        absent = self.root / sd_lib.WORK_DIR / "2026-01-01-nothing"
        absent.mkdir(parents=True)
        with unittest.mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            rows = sd_lib.Rows(self.root)
            self.addCleanup(rows.close)
            self.assertEqual(rows.activity(absent), "")

    def test_a_file_checkout_has_no_rows_and_answers_empty(self) -> None:
        """`Statuses` without a marker holds no `Rows` at all."""
        statuses = sd_lib.Statuses.of(self.root)
        self.addCleanup(statuses.close)
        self.assertEqual(statuses.source, sd_lib.FROM_FILE)
        self.assertEqual(sd_lib._recorded(statuses, self.item_dir), "")


class DisplayFieldsTests(unittest.TestCase):
    """The membership comes from the row; only the order comes from the caller."""

    def test_a_key_the_caller_never_named_is_still_returned(self) -> None:
        """sd:602. The two contribution renderers dropped these in silence."""
        row = {"url": 1, "blocking_labels": ["blocked"], "revision": "abc"}
        self.assertEqual(
            ["url", "blocking_labels", "revision"],
            sd_lib.display_fields(row, ("url",)),
        )

    def test_named_keys_lead_in_the_caller_s_order_and_the_rest_are_sorted(self) -> None:
        # The named pair is deliberately out of alphabetical order. With
        # ("first", "second") a sort of the named keys is invisible, and the
        # test passes on an implementation that ignores the caller entirely.
        row = {"zeta": 1, "alpha": 2, "second": 3, "first": 4}
        self.assertEqual(
            ["second", "first", "alpha", "zeta"],
            sd_lib.display_fields(row, ("second", "first")),
        )

    def test_a_key_the_header_already_printed_is_not_repeated(self) -> None:
        row = {"title": 1, "lane": 2, "url": 3, "extra": 4}
        self.assertEqual(
            ["url", "extra"],
            sd_lib.display_fields(row, ("url",), ("title", "lane")),
        )

    def test_a_named_key_the_row_lacks_is_still_offered_to_the_caller(self) -> None:
        """The caller filters empties; this function does not read values.

        Returning only present keys would make the order depend on the data,
        so two rows of the same kind would print their fields differently.
        """
        self.assertEqual(["a", "b"], sd_lib.display_fields({}, ("a", "b")))

    def test_a_key_named_twice_in_the_order_is_offered_once(self) -> None:
        """A hand-written tuple acquires a repeat, and it printed twice."""
        row = {"url": 1, "extra": 2}
        self.assertEqual(
            ["url", "local_status", "extra"],
            sd_lib.display_fields(row, ("url", "local_status", "url")),
        )

    def test_the_result_never_repeats_a_key(self) -> None:
        row = {"a": 1, "b": 2}
        fields = sd_lib.display_fields(row, ("a", "a", "b"), ())
        self.assertEqual(sorted(set(fields)), sorted(set(row)))


# -- the aging basis ---------------------------------------------------------
#
# `item_date`, `last_active` and `touched` came out of the 45-day age sweep
# when sd:10's criterion 21 cut it; the cases below came with them. `today`
# is a literal in every one: the rule under test is arithmetic, and a test
# that read the clock would pass or fail depending on the day it ran.


def dated_item(repo: pathlib.Path, name: str, **fields) -> sd_lib.WorkItem:
    """One work item on disk, read back through `work_item`."""
    item = repo / "docs" / "work" / name
    item.mkdir(parents=True)
    lines = ["---", f"title: {name}"]
    lines += [f"{key}: {value}" for key, value in fields.items() if value is not None]
    lines += ["---", "", "# body"]
    (item / "prd.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sd_lib.work_item(item)


class ItemDate(unittest.TestCase):
    """When an item dated itself, and when nothing did."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name) / "repo"
        (self.repo / "docs" / "work").mkdir(parents=True)

    def test_created_is_the_date(self) -> None:
        item = dated_item(self.repo, "2026-07-01-old", status="planning", created="2026-07-01")
        self.assertEqual(sd_lib.item_date(item), datetime.date(2026, 7, 1))

    def test_the_directory_prefix_dates_an_item_whose_frontmatter_does_not(self) -> None:
        """Every templated item carries one, and the bulk-park sorted on it."""
        item = dated_item(self.repo, "2026-01-01-no-created-line", status="planning")
        self.assertEqual(sd_lib.item_date(item), datetime.date(2026, 1, 1))

    def test_created_outranks_the_directory_prefix(self) -> None:
        """The item's own statement about itself wins.

        A directory renamed or copied from another item carries a date that is
        not this item's, so the frontmatter is the more trustworthy of the two
        whenever both exist.
        """
        item = dated_item(self.repo, "2020-01-01-stale-prefix", status="planning",
                          created="2026-08-30")
        self.assertEqual(sd_lib.item_date(item), datetime.date(2026, 8, 30))

    def test_an_unparseable_created_falls_back_rather_than_crashing(self) -> None:
        """`created: soon` is a real thing a person types."""
        item = dated_item(self.repo, "2026-01-01-vague", status="planning", created="soon")
        self.assertEqual(sd_lib.item_date(item), datetime.date(2026, 1, 1))

    def test_a_garbage_date_everywhere_is_undated_not_an_error(self) -> None:
        item = dated_item(self.repo, "2026-13-45-impossible", status="planning", created="nope")
        self.assertIsNone(sd_lib.item_date(item))

    def test_no_date_anywhere_is_undated(self) -> None:
        item = dated_item(self.repo, "untitled-thing", status="planning")
        self.assertIsNone(sd_lib.item_date(item))


class LastActive(unittest.TestCase):
    """The aging basis: what counts as something happening to an item.

    `item_date` answers when an item began. `last_active` answers when anything
    last happened to it, and it is what the threshold is measured from -- the
    two are different questions, and `idle-planning` read the first one while
    saying the second. This is the one definition `sd-status` reads, so it is
    where the difference is pinned.
    """

    ITEM = datetime.date(2026, 1, 1)

    def last(self, name: str = "2026-01-01-x", activity: str = "",
             marks: dict | None = None) -> datetime.date:
        return sd_lib.last_active(self.ITEM, name, activity, marks)

    def test_an_item_with_no_evidence_ages_from_its_own_date(self) -> None:
        """The floor, and the whole of the old behaviour."""
        self.assertEqual(self.last(), self.ITEM)

    def test_a_commit_on_its_directory_is_activity(self) -> None:
        commit = datetime.date(2026, 9, 5)
        self.assertEqual(self.last(marks={"2026-01-01-x": commit}), commit)

    def test_a_database_stamp_is_activity(self) -> None:
        """A note carries a full timestamp; only its day is read."""
        self.assertEqual(
            self.last(activity="2026-09-06T09:14:00+00:00"),
            datetime.date(2026, 9, 6),
        )

    def test_the_latest_of_the_three_wins_rather_than_the_first_found(self) -> None:
        """A union, not a precedence chain: each source is blind where the
        others see, so the newest evidence is the answer whichever gave it."""
        marks = {"2026-01-01-x": datetime.date(2026, 8, 1)}
        self.assertEqual(
            self.last(activity="2026-09-06T09:14:00+00:00", marks=marks),
            datetime.date(2026, 9, 6),
        )
        self.assertEqual(
            self.last(activity="2026-07-01T09:14:00+00:00", marks=marks),
            datetime.date(2026, 8, 1),
        )

    def test_an_unparseable_stamp_lowers_nothing(self) -> None:
        """Absent evidence degrades to the floor, never below it."""
        self.assertEqual(self.last(activity="not a date"), self.ITEM)
        self.assertEqual(self.last(activity=""), self.ITEM)

    def test_a_commit_on_another_item_is_not_this_item_s_activity(self) -> None:
        self.assertEqual(
            self.last(marks={"2026-01-01-other": datetime.date(2026, 9, 5)}),
            self.ITEM,
        )


class ItemDirectory(unittest.TestCase):
    """Which item a tracked path belongs to, for `touched`'s one `git log`."""

    def resolve(self, path: str) -> str:
        return sd_lib._item_directory(path, "docs/work")

    def test_a_file_in_an_item_names_that_item(self) -> None:
        self.assertEqual(self.resolve("docs/work/2026-01-01-x/prd.md"), "2026-01-01-x")

    def test_an_archived_item_is_named_through_its_month(self) -> None:
        self.assertEqual(
            self.resolve("docs/work/archive/2026-08/2026-01-01-x/prd.md"),
            "2026-01-01-x",
        )

    def test_a_file_directly_in_the_work_directory_names_no_item(self) -> None:
        """`.status-source` lives there and is not an item."""
        self.assertEqual(self.resolve("docs/work/.status-source"), "")

    def test_a_path_outside_the_work_directory_names_no_item(self) -> None:
        self.assertEqual(self.resolve("bin/sd-status"), "")


class Touched(unittest.TestCase):
    """One `git log` per root, and what it maps."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name) / "repo"
        (self.repo / "docs" / "work").mkdir(parents=True)
        self.at("init", "--quiet", "--initial-branch=main")
        self.at("config", "user.email", "t@example.com")
        self.at("config", "user.name", "t")
        self.at("config", "commit.gpgsign", "false")

    def at(self, *args: str, when: str | None = None) -> None:
        """One git call in the fixture repository.

        Not named `run`: that is `TestCase.run`, and overriding it stops the
        case from running at all -- which it did, loudly, on the first draft.
        """
        env = {**os.environ}
        if when:
            env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = when
        subprocess.run(["git", *args], cwd=self.repo, check=True,
                       capture_output=True, env=env)

    def commit(self, name: str, when: str) -> None:
        """One item, written as a real item and committed on a chosen day."""
        item = self.repo / "docs" / "work" / name
        if item.exists():
            (item / "touched").write_text(when, encoding="utf-8")
        else:
            dated_item(self.repo, name, status="planning")
        self.at("add", "-A")
        self.at("commit", "--quiet", "-m", f"touch {name}", when=when)

    def test_each_item_maps_to_the_day_it_was_last_committed_to(self) -> None:
        self.commit("2026-01-01-a", "2026-08-01T12:00:00 +0000")
        self.commit("2026-01-01-b", "2026-09-05T12:00:00 +0000")
        self.assertEqual(
            sd_lib.touched(self.repo),
            {"2026-01-01-a": datetime.date(2026, 8, 1),
             "2026-01-01-b": datetime.date(2026, 9, 5)},
        )

    def test_the_latest_commit_wins_and_not_the_first_one(self) -> None:
        """`git log` is newest first, so the first sighting is the latest."""
        self.commit("2026-01-01-a", "2026-08-01T12:00:00 +0000")
        self.commit("2026-01-01-a", "2026-09-05T12:00:00 +0000")
        self.assertEqual(
            sd_lib.touched(self.repo), {"2026-01-01-a": datetime.date(2026, 9, 5)}
        )

    def test_a_directory_that_is_not_a_checkout_is_empty_and_not_an_error(self) -> None:
        """Git refusing and git finding nothing leave the age on its other two
        sources, so there is no third state for a caller to handle."""
        loose = self.repo.parent / "not-a-checkout"
        loose.mkdir()
        self.assertEqual(sd_lib.touched(loose), {})


class SetupStaysLocalTests(unittest.TestCase):
    """`make setup` provisions the checkout it stands in, never a borrowed one.

    The virtualenv fallback that lets a worktree *use* the main checkout's
    environment must not let it *rewrite* one: `setup` would install this
    branch's pinned requirements over the environment another session is
    running on. Borrowing is for commands that consume an environment.
    """

    MAKEFILE = pathlib.Path(__file__).resolve().parents[1] / "Makefile"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.main = self.tmp / "main"
        self.main.mkdir()
        self.git("init", "-q", "-b", "main", cwd=self.main)
        (self.main / "Makefile").write_text(
            self.MAKEFILE.read_text(encoding="utf-8"), encoding="utf-8")
        # A real executable, because the fallback tests for one.
        venv_python = self.main / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
        venv_python.chmod(0o755)
        self.git("add", "Makefile", cwd=self.main)
        self.git("-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "-q", "-m", "makefile", cwd=self.main)
        self.linked = self.tmp / "linked"
        self.git("worktree", "add", "-q", str(self.linked), cwd=self.main)

    def git(self, *args: str, cwd: pathlib.Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True, text=True)

    def make(self, target: str, *extra: str) -> str:
        done = subprocess.run(["make", "-s", "-n", target, *extra],
                              cwd=self.linked, capture_output=True, text=True)
        return done.stdout

    def test_setup_in_a_worktree_does_not_touch_the_main_virtualenv(self) -> None:
        recipe = self.make("setup")
        self.assertIn('-m venv ".venv"', recipe)
        self.assertNotIn(str(self.main / ".venv"), recipe)

    def test_an_explicit_venv_is_still_honoured(self) -> None:
        """`origin` distinguishes a deliberate VENV from this Makefile's default."""

        recipe = self.make("setup", f"VENV={self.tmp}/chosen")
        self.assertIn(f'-m venv "{self.tmp}/chosen"', recipe)


class BorrowedEnvironmentTests(unittest.TestCase):
    """A worktree borrows the main checkout's virtualenv only when it fits.

    The fallback that lets a linked worktree use the environment the main
    checkout provisioned assumed the two were interchangeable. They are not.
    A branch that moves a pin in requirements-dev.txt or
    requirements-security.txt would lint, test and audit against another
    branch's versions, and `make audit` would go on promising the
    requirements-security.txt scanner while running whatever the other branch
    installed -- a misleading pass or a misleading failure, with nothing said
    either way.

    So `make setup` leaves a copy of the two files inside the environment it
    provisions, and the borrow is allowed only where those copies are this
    tree's. Everything here reads `make -n`: the decision is a variable, so it
    is settled before a recipe would run.

    A `.venv` the checkout carries as a real directory is its own environment
    and is not checked. A `.venv` that is a symlink into another checkout is
    checked, because that is the same borrow under a local name, and it is
    how sd:1020 says a worktree here gets an environment -- but on a proven
    mismatch only, so an environment that predates the record goes on working.
    """

    MAKEFILE = pathlib.Path(__file__).resolve().parents[1] / "Makefile"
    REQUIREMENTS = ("requirements-dev.txt", "requirements-security.txt")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.main = self.tmp / "main"
        self.main.mkdir()
        self.git("init", "-q", "-b", "main", cwd=self.main)
        (self.main / "Makefile").write_text(
            self.MAKEFILE.read_text(encoding="utf-8"), encoding="utf-8")
        for name in self.REQUIREMENTS:
            (self.main / name).write_text(f"# {name}\n", encoding="utf-8")
        self.git("add", "-A", cwd=self.main)
        self.git("-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "-q", "-m", "base", cwd=self.main)
        # A real executable, because the fallback tests for one, and beside it
        # the record a `make setup` of this same tree would have left.
        venv_python = self.main / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
        venv_python.chmod(0o755)
        self.record = self.main / ".venv" / "sd-requirements"
        self.record.mkdir()
        for name in self.REQUIREMENTS:
            (self.record / name).write_text(f"# {name}\n", encoding="utf-8")
        self.linked = self.tmp / "linked"
        self.git("worktree", "add", "-q", str(self.linked), cwd=self.main)

    def git(self, *args: str, cwd: pathlib.Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True, text=True)

    def make(self, *argv: str, cwd: pathlib.Path | None = None
             ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["make", "-s", "-n", *argv],
                              cwd=cwd or self.linked,
                              capture_output=True, text=True)

    def move_a_pin(self, name: str = "requirements-dev.txt") -> None:
        (self.linked / name).write_text(f"# {name}\nmoved==2\n", encoding="utf-8")

    def mark_mid_provision(self) -> pathlib.Path:
        """The file `make setup` leaves in an environment while it builds it."""

        marker = self.main / ".venv" / "sd-provisioning"
        marker.write_text("building\n", encoding="utf-8")
        return marker

    def test_a_mid_provision_environment_is_refused_through_the_link(self) -> None:
        """The reviewer's state: record gone, marker present, sd:1020 link.

        `setup` removes the record before it mutates anything, so from the
        outside a half-built environment looks exactly like one provisioned
        before the record existed -- and the symlink path treats that as
        legacy and borrows it with a note. The marker is what tells the two
        apart, and on this path it has to refuse and not merely say so: the
        packages are being replaced while the borrower reads them.
        """

        self.symlink_the_environment()
        self.record.rename(self.main / ".venv" / "not-the-record")
        self.mark_mid_provision()
        done = self.make("docs-lint")
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("refusing-to-borrow", done.stderr)
        self.assertIn("mid-provision", done.stderr)
        self.assertNotIn("records no provisioning", done.stderr)
        self.assertNotIn(str(self.main / ".venv" / "bin" / "python"), done.stdout)

    def test_a_mid_provision_environment_is_refused_on_the_strict_path(self) -> None:
        """The same fact on the other path, with the record still in place.

        The record matching proves the requirements agree; it says nothing
        about whether the packages behind them are the ones installed. So the
        marker is checked before the record is compared, not after it fails.
        """

        self.mark_mid_provision()
        done = self.make("docs-lint")
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("mid-provision", done.stderr)

    def test_the_refusal_names_the_checkout_to_finish_it_in(self) -> None:
        """`make setup VENV=.venv` is the wrong remedy for a marked environment.

        Forking a second environment out of a run that is still going is not
        what the reader wants, and a marker left by a killed `make` has to be
        recoverable rather than permanent: the way out is to finish the
        provision where it started.
        """

        self.mark_mid_provision()
        done = self.make("docs-lint")
        self.assertIn(f"run 'make setup' in {self.main}", done.stderr)
        self.assertNotIn("VENV=.venv", done.stderr)

    def test_setup_still_runs_in_a_worktree_refused_for_the_marker(self) -> None:
        """The refusal fires at expansion, and `setup` reaches SETUP_VENV."""

        self.symlink_the_environment()
        self.mark_mid_provision()
        done = self.make("setup", "VENV=.venv")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_an_unmarked_environment_with_no_record_is_still_legacy(self) -> None:
        """The pin: absence of the record without the marker keeps its meaning.

        This is every machine on the day the record landed, and the marker
        must not turn it into a refusal. The note is the whole of the
        difference, and it is the one this same state got before the marker
        existed.
        """

        self.symlink_the_environment()
        self.record.rename(self.main / ".venv" / "not-the-record")
        self.assertFalse((self.main / ".venv" / "sd-provisioning").exists())
        done = self.make("docs-lint")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("records no provisioning", done.stderr)
        self.assertNotIn("refusing-to-borrow", done.stderr)

    def test_every_implementation_spells_the_marker_the_same(self) -> None:
        """Three writers of one name, and no import between them.

        The Makefile writes the file; `bin/sd_lib.py` and `hooks/pre-commit`
        read it. The Makefile cannot import either, so the name is shared by
        spelling -- which is only safe while something fails when one of the
        three is renamed alone.
        """

        root = pathlib.Path(__file__).resolve().parents[1]
        self.assertEqual(sd_lib.MID_PROVISION, "sd-provisioning")
        for path in (root / "Makefile", root / "hooks" / "pre-commit"):
            self.assertIn(sd_lib.MID_PROVISION, path.read_text(encoding="utf-8"),
                          f"{path.name} does not name the marker")

    def test_an_environment_that_matches_is_borrowed(self) -> None:
        done = self.make("docs-lint")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(str(self.main / ".venv" / "bin" / "python"), done.stdout)

    def test_a_moved_pin_refuses_and_names_the_file(self) -> None:
        self.move_a_pin("requirements-security.txt")
        done = self.make("docs-lint")
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("requirements-security.txt", done.stderr)
        self.assertIn("make setup VENV=.venv", done.stderr)
        self.assertNotIn(str(self.main / ".venv"), done.stdout)

    def test_an_environment_with_no_record_refuses(self) -> None:
        """The case every machine is in the day this lands.

        An environment provisioned before the record existed cannot say what
        it holds, so it is refused rather than borrowed on the assumption
        that it fits.
        """

        self.record.rename(self.main / ".venv" / "not-the-record")
        done = self.make("docs-lint")
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("does not record what it was provisioned from", done.stderr)

    def test_an_explicit_venv_is_honoured_even_when_the_borrow_is_refused(self) -> None:
        """`VENV=` is a deliberate choice; the check is on the automatic borrow."""

        self.move_a_pin()
        done = self.make("docs-lint", f"VENV={self.tmp}/chosen")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"{self.tmp}/chosen/bin/python", done.stdout)

    def test_setup_is_still_runnable_in_a_worktree_that_was_refused(self) -> None:
        """The refusal names `make setup`, so `make setup` must not refuse."""

        self.move_a_pin()
        done = self.make("setup")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('-m venv ".venv"', done.stdout)

    # That `setup` records what it provisioned is asserted in
    # `ProvisioningRecordTests`, against a `make setup` that actually runs.
    # It was a `make -n` text match here until the recipe learned to publish
    # the record by renaming a directory built beside it -- at which point the
    # match broke while the behaviour it stood for was unchanged, which is
    # what a test of a recipe's spelling is worth.

    def symlink_the_environment(self) -> None:
        """What sd:1020 does by hand: a `.venv` link into the main checkout.

        It passes `[ -x .venv/bin/python ]`, so it is a borrow wearing a local
        name, and it is the usual way a worktree here gets an environment.
        """

        (self.linked / ".venv").symlink_to(self.main / ".venv")

    def test_a_symlinked_environment_that_matches_is_used(self) -> None:
        self.symlink_the_environment()
        done = self.make("docs-lint")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('".venv/bin/python"', done.stdout)

    def test_a_symlinked_environment_is_compared_too(self) -> None:
        """The hole a local-first test would leave: a link is not an own one."""

        self.symlink_the_environment()
        self.move_a_pin()
        done = self.make("docs-lint")
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("requirements-dev.txt", done.stderr)
        # Named by what it points at, which is the environment at issue.
        self.assertIn(str(self.main / ".venv"), done.stderr)

    def test_a_symlinked_environment_with_no_record_runs_and_says_so(self) -> None:
        """Proven mismatch only, where the automatic borrow is strict -- and
        a note, because a lenient pass has to be legible as one.

        The link is not this Makefile's doing, and refusing an environment
        that predates the record would strand every checkout carrying one.
        The day it is provisioned again the case is covered like any other,
        which `test_a_symlinked_environment_is_compared_too` is.

        Until then the rule covers nothing in the case that actually occurs
        on this machine, so it says so on stderr: an exit code that cannot be
        told from the check having run is the shape this repository refuses
        elsewhere. sd:1349 is the row; the note is how a reader finds it.
        """

        self.symlink_the_environment()
        self.record.rename(self.main / ".venv" / "not-the-record")
        self.move_a_pin()
        done = self.make("docs-lint")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('".venv/bin/python"', done.stdout)
        self.assertIn("records no provisioning", done.stderr)
        self.assertIn(str(self.main / ".venv"), done.stderr)
        self.assertIn(f"Run 'make setup' in {self.main}", done.stderr)

    def test_a_matching_symlinked_environment_stays_quiet(self) -> None:
        """The note is the absent-record case, not every symlink."""

        self.symlink_the_environment()
        done = self.make("docs-lint")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("records no provisioning", done.stderr)

    def test_a_checkout_with_its_own_environment_is_never_checked(self) -> None:
        """Nothing was borrowed, so there is nothing to be compatible with."""

        (self.main / "requirements-dev.txt").write_text("moved==2\n",
                                                        encoding="utf-8")
        done = self.make("docs-lint", cwd=self.main)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('".venv/bin/python"', done.stdout)


class ProvisioningRecordTests(unittest.TestCase):
    """`make setup` and the record it leaves, in the two orders that matter.

    The record is what lets a worktree borrow an environment, so a record
    that is present while the environment is in motion is worse than none:
    it is a claim of compatibility made about packages that are being
    replaced. And the recipe has to be runnable in the state its own refusal
    recommends it from, which is a worktree whose `.venv` is an sd:1020 link.

    These run `make setup` for real, against a stand-in interpreter, because
    what is under test is the order of the steps and the state each failure
    leaves behind -- neither of which `make -n` can show.
    """

    MAKEFILE = pathlib.Path(__file__).resolve().parents[1] / "Makefile"
    REQUIREMENTS = ("requirements-dev.txt", "requirements-security.txt")

    #: Stands in for the interpreter the recipe calls. `-m venv <dir>` copies
    #: it to <dir>/bin/python, so the steps after it run it too, and each
    #: step's exit code is an environment variable the test sets. It mirrors
    #: the one real behaviour the recipe now works around -- CPython's venv
    #: refuses a path that is a symlink -- and
    #: `test_the_real_interpreter_refuses_a_symlinked_target` is what keeps
    #: that mirror honest rather than convenient.
    STUB = """#!/bin/sh
last=""
for a in "$@"; do last="$a"; done
case " $* " in
  *" -m venv "*)
    if [ -L "$last" ]; then
      echo "Error: Unable to create directory '$last'" >&2
      exit 1
    fi
    mkdir -p "$last/bin" || exit 1
    cp "$0" "$last/bin/python" || exit 1
    chmod +x "$last/bin/python"
    exit 0
    ;;
  *" -m pip "*) exit "${STUB_PIP_EXIT:-0}" ;;
  *"--provision-library"*) exit "${STUB_PROVISION_EXIT:-0}" ;;
esac
exit 0
"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.stub = self.tmp / "stub-python"
        self.stub.write_text(self.STUB, encoding="utf-8")
        self.stub.chmod(0o755)

        self.main = self.tmp / "main"
        self.main.mkdir()
        self.git("init", "-q", "-b", "main", cwd=self.main)
        (self.main / "Makefile").write_text(
            self.MAKEFILE.read_text(encoding="utf-8"), encoding="utf-8")
        for name in self.REQUIREMENTS:
            (self.main / name).write_text(f"# {name}\n", encoding="utf-8")
        self.git("add", "-A", cwd=self.main)
        self.git("-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "-q", "-m", "base", cwd=self.main)
        # An environment in the main checkout, with the record `make setup`
        # would have left, so a worktree linking to it is the live shape.
        self.main_venv = self.main / ".venv"
        (self.main_venv / "bin").mkdir(parents=True)
        (self.main_venv / "bin" / "python").write_text("#!/bin/sh\n",
                                                       encoding="utf-8")
        (self.main_venv / "bin" / "python").chmod(0o755)
        (self.main_venv / "sd-requirements").mkdir()
        for name in self.REQUIREMENTS:
            (self.main_venv / "sd-requirements" / name).write_text(
                f"# {name}\n", encoding="utf-8")

        self.linked = self.tmp / "linked"
        self.git("worktree", "add", "-q", str(self.linked), cwd=self.main)
        self.record = self.linked / ".venv" / "sd-requirements"

    def git(self, *args: str, cwd: pathlib.Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True, text=True)

    def setup(self, venv: str = ".venv", **env: str) -> subprocess.CompletedProcess[str]:
        """The command the borrow refusal recommends, verbatim."""

        return subprocess.run(
            ["make", "-s", "setup", f"PYTHON={self.stub}", f"VENV={venv}"],
            cwd=self.linked, capture_output=True, text=True,
            env={**os.environ, **env})

    def dry_run(self, target: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["make", "-s", "-n", target], cwd=self.linked,
                              capture_output=True, text=True)

    def move_a_pin(self) -> None:
        (self.linked / "requirements-dev.txt").write_text(
            "# requirements-dev.txt\nmoved==2\n", encoding="utf-8")

    def test_a_successful_provision_publishes_the_record(self) -> None:
        done = self.setup()
        self.assertEqual(done.returncode, 0, done.stderr)
        for name in self.REQUIREMENTS:
            self.assertEqual((self.record / name).read_text(encoding="utf-8"),
                             (self.linked / name).read_text(encoding="utf-8"))
        # Nothing is left of the directory the record was published from.
        self.assertFalse((self.linked / ".venv" / ".sd-requirements.new").exists())

    def test_a_failed_provision_leaves_no_record(self) -> None:
        """A re-provision that dies mid-flight must not leave a stale claim.

        The record used to be written last and nothing removed it first, so
        the previous run's copy sat beside packages this run had already
        changed. A worktree comparing against it matched, passed the borrow
        check, and ran the versions the failed run had half-installed.
        """

        self.assertEqual(self.setup().returncode, 0)
        self.assertTrue(self.record.is_dir(), "the first run should record")
        self.move_a_pin()
        done = self.setup(STUB_PROVISION_EXIT="1")
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertFalse(self.record.exists(),
                         "a record survived a provision that failed")

    def test_the_recovery_the_refusal_recommends_detaches_the_link(self) -> None:
        """The combined case: a refused symlinked worktree, then the remedy.

        `python -m venv` refuses a symlinked path, so the recommendation in
        the refusal -- `make setup VENV=.venv` -- used to fail in exactly the
        configuration that produced the refusal.
        """

        (self.linked / ".venv").symlink_to(self.main_venv)
        self.move_a_pin()
        refused = self.dry_run("docs-lint")
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("refusing-to-borrow", refused.stderr)

        done = self.setup()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("detaching .venv", done.stderr)
        self.assertIn(str(self.main_venv), done.stderr)
        self.assertFalse((self.linked / ".venv").is_symlink(),
                         "the link should be gone")
        self.assertTrue((self.linked / ".venv" / "bin" / "python").exists())
        # The environment behind the link, and its record, are untouched --
        # the detach precedes the record removal for this reason.
        self.assertTrue((self.main_venv / "bin" / "python").exists())
        for name in self.REQUIREMENTS:
            self.assertTrue((self.main_venv / "sd-requirements" / name).is_file())

        after = self.dry_run("docs-lint")
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertIn('".venv/bin/python"', after.stdout)
        self.assertNotIn("records no provisioning", after.stderr)

    def test_a_killed_provision_is_refused_and_then_recoverable(self) -> None:
        """The marker's full life: written, honoured, and cleared by a retry.

        A marker that outlived its run would brick the worktree, since the
        thing it refuses is the thing that would clear it. It does not: the
        refusal sends the reader back to `make setup`, which rewrites the
        marker over the dead one and removes it when the run completes.
        """

        failed = self.setup(STUB_PROVISION_EXIT="1")
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        marker = self.linked / ".venv" / "sd-provisioning"
        self.assertTrue(marker.is_file(), "the marker should outlive the run")

        refused = self.dry_run("docs-lint")
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("mid-provision", refused.stderr)

        done = self.setup()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(marker.exists(), "a completed run should clear it")
        self.assertTrue(self.record.is_dir())
        after = self.dry_run("docs-lint")
        self.assertEqual(after.returncode, 0, after.stderr)

    def test_no_mutation_happens_unless_the_marker_exists(self) -> None:
        """The block's contract, asked at the two commands that can be stepped over.

        A recipe line is one shell with `;` between commands and no `set -e`,
        so a command that fails is stepped over and the line's status is the
        last command's. That is not a hypothetical here: both halves below
        used to pass, quietly, with the mutation already done.

        Asked as the contract rather than as two exit codes, because what
        matters is not which command reported what -- it is that the record is
        removed only after a marker exists to say why it is missing. Codex's
        note on the first pass was that setup and the symlink refusal were
        each covered and their combination was not; this is the combination.
        """

        # The marker cannot be written: a directory sits where the file goes,
        # so the redirection fails. Without `|| exit 1` the `rm -rf` runs
        # anyway on a line that exits 0, and the record is gone with no marker
        # to say why -- the absence the borrow paths read as legacy.
        #
        # The next step is failed deliberately, and that is what makes this
        # discriminating rather than merely red. Left to run on, the old
        # recipe republished the record at the end and failed only on its own
        # `rm -f` of the directory in the marker's place: a nonzero exit, a
        # record present, and nothing said about the window in between. What
        # is under test is the state after the mutation, so the run has to
        # stop there.
        self.assertEqual(self.setup().returncode, 0)
        self.assertTrue(self.record.is_dir())
        (self.linked / ".venv" / "sd-provisioning").mkdir()
        blocked = self.setup(STUB_PIP_EXIT="1")
        self.assertNotEqual(blocked.returncode, 0,
                            "a failed marker write reported success")
        self.assertTrue(self.record.is_dir(),
                        "the record was removed without a marker to explain it")

        # The link cannot be removed: its parent is read-only. `mkdir -p` on a
        # symlink to an existing directory succeeds, so an unchecked `rm`
        # leaves the marker written *through* the link and the record removed
        # from the environment every other worktree borrows from. This half is
        # about the other checkout, not this one.
        held = self.linked / "held"
        held.mkdir()
        (held / "env").symlink_to(self.main_venv)
        held.chmod(0o555)
        self.addCleanup(held.chmod, 0o755)
        through = self.setup(venv="held/env")
        self.assertNotEqual(through.returncode, 0,
                            "a failed detach reported success")
        self.assertTrue((held / "env").is_symlink(),
                        "the link is still the thing that could not be removed")
        self.assertFalse((self.main_venv / "sd-provisioning").exists(),
                         "the marker was written through the link")
        for name in self.REQUIREMENTS:
            self.assertTrue((self.main_venv / "sd-requirements" / name).is_file(),
                            "the borrowed-from environment lost its record")

    def test_the_marker_precedes_the_record_removal(self) -> None:
        """Ordering, read off the state a failure leaves rather than the text.

        The window the marker closes opens at the first mutation. Failing the
        very next step is the narrowest way to ask whether the marker was
        already there when that step ran.
        """

        self.assertEqual(self.setup().returncode, 0)
        self.assertTrue(self.record.is_dir())
        failed = self.setup(STUB_PIP_EXIT="1")
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        self.assertFalse(self.record.exists(), "the record should be gone")
        self.assertTrue((self.linked / ".venv" / "sd-provisioning").is_file(),
                        "the marker should have been written before the removal")

    def test_the_real_interpreter_refuses_a_symlinked_target(self) -> None:
        """The premise the stand-in mirrors, asked of the real interpreter.

        Nothing is built: venv refuses before it creates anything, which is
        why this costs a process and not an environment.
        """

        target = self.tmp / "link-to-a-directory"
        (self.tmp / "a-directory").mkdir()
        target.symlink_to(self.tmp / "a-directory")
        done = subprocess.run([sys.executable, "-m", "venv", str(target)],
                              capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("Unable to create directory", done.stderr + done.stdout)


class ProvisionedLibraryTests(unittest.TestCase):
    """Which checkouts the `sd_db` probe will look in.

    `make setup` provisions one virtualenv, into the checkout it ran in. The
    doctrine puts every writer in a linked worktree, which has none, so until
    2026-09-22 every entrypoint run in one found no `sd_db` and answered from
    git instead -- `sd-review` reported `registry_unavailable` and asked for a
    library that was already installed in the main checkout.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()

    def git(self, *args: str, cwd: pathlib.Path) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True, text=True)

    def test_a_linked_worktree_offers_the_main_checkout_too(self) -> None:
        main = self.tmp / "main"
        main.mkdir()
        self.git("init", "-q", "-b", "main", cwd=main)
        self.git("-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "-q", "--allow-empty", "-m", "root", cwd=main)
        linked = self.tmp / "linked"
        self.git("worktree", "add", "-q", str(linked), cwd=main)

        # The probe reads its own location, so it is asked from each checkout
        # in turn by pointing `__file__` at that checkout's `bin/`.
        for root in (main, linked):
            (root / "bin").mkdir(exist_ok=True)
        with unittest.mock.patch.object(
                sd_lib, "__file__", str(linked / "bin" / "sd_lib.py")):
            roots = sd_lib._checkouts_that_may_hold_a_venv()
        self.assertEqual(roots, [linked, main])

    def test_the_main_checkout_offers_only_itself(self) -> None:
        """No second entry, so a checkout with its own virtualenv keeps it."""

        main = self.tmp / "solo"
        main.mkdir()
        self.git("init", "-q", "-b", "main", cwd=main)
        (main / "bin").mkdir()
        with unittest.mock.patch.object(
                sd_lib, "__file__", str(main / "bin" / "sd_lib.py")):
            self.assertEqual(sd_lib._checkouts_that_may_hold_a_venv(), [main])

    def test_a_mid_provision_checkout_is_not_offered(self) -> None:
        """A marked `.venv` is skipped, so the probe never reads into it.

        The `site-packages` under an environment `make setup` is rebuilding
        belongs to the run that is still going, to one that died, or to
        neither. Answering from git is the same fallback an unprovisioned
        checkout already gets, and it is the better of the two.
        """

        main = self.tmp / "main"
        main.mkdir()
        self.git("init", "-q", "-b", "main", cwd=main)
        self.git("-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "-q", "--allow-empty", "-m", "root", cwd=main)
        linked = self.tmp / "linked"
        self.git("worktree", "add", "-q", str(linked), cwd=main)
        for root in (main, linked):
            (root / "bin").mkdir(exist_ok=True)
        (main / ".venv").mkdir()
        (main / ".venv" / sd_lib.MID_PROVISION).write_text("building\n",
                                                           encoding="utf-8")
        with unittest.mock.patch.object(
                sd_lib, "__file__", str(linked / "bin" / "sd_lib.py")):
            self.assertEqual(sd_lib._checkouts_that_may_hold_a_venv(), [linked])

    def test_a_local_environment_wins_an_equal_version_in_the_main_checkout(self) -> None:
        """Checkout order outranks the version sort, not the other way round.

        Ranking every candidate in one list sorts by version first, so two
        equal versions fall back to comparing paths -- and a worktree that
        deliberately provisioned its own copy loses to the main checkout on
        nothing but the spelling of its directory. The names here are chosen
        so that the wrong implementation fails: `z-main` sorts above
        `a-linked`.
        """

        linked, main = self.tmp / "a-linked", self.tmp / "z-main"
        for root in (linked, main):
            (root / ".venv/lib/python3.13/site-packages/sd_db").mkdir(parents=True)
        with unittest.mock.patch.object(
                sd_lib, "_checkouts_that_may_hold_a_venv", lambda: [linked, main]):
            found = sd_lib._provisioned_library_paths()
        self.assertEqual(len(found), 2)
        self.assertTrue(found[0].startswith(str(linked)), found)

    def test_newest_first_still_holds_inside_one_checkout(self) -> None:
        """The rebuilt-virtualenv case the version sort was written for."""

        root = self.tmp / "one"
        for version in ("3.9", "3.13"):
            (root / f".venv/lib/python{version}/site-packages/sd_db").mkdir(parents=True)
        with unittest.mock.patch.object(
                sd_lib, "_checkouts_that_may_hold_a_venv", lambda: [root]):
            found = sd_lib._provisioned_library_paths()
        self.assertEqual([p.split("/lib/")[1].split("/")[0] for p in found],
                         ["python3.13", "python3.9"])

    def test_outside_a_repository_it_is_still_one_root(self) -> None:
        """Git refusing is not an error here; the probe just has one place."""

        loose = self.tmp / "loose"
        (loose / "bin").mkdir(parents=True)
        with unittest.mock.patch.object(
                sd_lib, "__file__", str(loose / "bin" / "sd_lib.py")):
            self.assertEqual(sd_lib._checkouts_that_may_hold_a_venv(), [loose])


if __name__ == "__main__":
    unittest.main()
