"""Behaviour tests for the read-only dashboard.

Real git repositories in a scratch root, because every fact the collector
reports comes out of `git` and a mocked one would only prove the mock agrees
with itself. The properties worth pinning are the ones a future tab could break
without noticing: that discovery enumerates rather than recites, that a missing
upstream reports absence instead of zero, that the dump is canonical, and that
the server has no write path at all.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dashboard import collect, server  # noqa: E402 - after the path insert


def load_cli():
    path = REPO_ROOT / "bin" / "sd-dashboard"
    loader = importlib.machinery.SourceFileLoader("sd_dashboard", str(path))
    spec = importlib.util.spec_from_file_location(
        "sd_dashboard", str(path), loader=loader
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sd_dashboard = load_cli()


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


class FleetHarness(unittest.TestCase):
    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self._scratch.cleanup)
        self.root = Path(self._scratch.name).resolve()

    def make_repo(self, relative: str, *, dirty: bool = False) -> Path:
        path = self.root / relative
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        git(path, "config", "user.email", "test@example.com")
        git(path, "config", "user.name", "Test")
        (path / "README.md").write_text("hello\n", encoding="utf-8")
        git(path, "add", "README.md")
        git(path, "commit", "-qm", "first commit")
        if dirty:
            (path / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")
        return path


class DiscoveryTests(FleetHarness):
    def test_both_grouped_and_top_level_checkouts_are_found(self):
        self.make_repo("platypeeps/alpha")
        self.make_repo("platypeeps/beta")
        self.make_repo("standalone")
        (self.root / "not-a-repo").mkdir()
        found = collect.discover_checkouts(self.root)
        self.assertEqual(
            sorted((group, path.name) for group, path in found),
            [(".", "standalone"), ("platypeeps", "alpha"), ("platypeeps", "beta")],
        )

    def test_a_missing_root_is_empty_rather_than_an_error(self):
        self.assertEqual(collect.discover_checkouts(self.root / "nope"), [])

    def test_a_directory_that_is_not_a_checkout_yields_no_facts(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.assertIsNone(collect.git_facts(plain))


class FactTests(FleetHarness):
    def test_dirt_is_counted_and_a_clean_tree_reports_zero(self):
        clean = collect.git_facts(self.make_repo("clean"))
        dirty = collect.git_facts(self.make_repo("dirty", dirty=True))
        self.assertEqual(clean["dirty"], 0)
        self.assertEqual(dirty["dirty"], 1)

    def test_no_upstream_reports_absence_not_zero(self):
        """`None` and `0` mean different things and the page renders them apart."""
        facts = collect.git_facts(self.make_repo("solo"))
        self.assertIsNone(facts["ahead"])
        self.assertIsNone(facts["behind"])

    def test_the_subject_and_branch_come_back(self):
        facts = collect.git_facts(self.make_repo("named"))
        self.assertEqual(facts["branch"], "main")
        self.assertEqual(facts["subject"], "first commit")

    def test_a_non_github_remote_leaves_the_web_link_empty(self):
        path = self.make_repo("local-remote")
        git(path, "remote", "add", "origin", "/srv/git/local-remote.git")
        self.assertEqual(collect.git_facts(path)["web"], "")

    def test_a_github_remote_becomes_a_web_link(self):
        path = self.make_repo("gh")
        git(path, "remote", "add", "origin", "git@github.com:owner/gh.git")
        self.assertEqual(collect.git_facts(path)["web"], "https://github.com/owner/gh")

    def test_git_that_fails_returns_empty_rather_than_raising(self):
        self.assertEqual(collect.run(["git", "--not-a-real-flag"]), "")

    def test_a_missing_binary_returns_empty(self):
        self.assertEqual(collect.run(["definitely-not-a-binary-here"]), "")


class StateTests(FleetHarness):
    def test_counts_match_the_fleet(self):
        self.make_repo("a")
        self.make_repo("group/b", dirty=True)
        state = collect.build_state(self.root)
        self.assertEqual(state["counts"]["repos"], 2)
        self.assertEqual(state["counts"]["dirty"], 1)
        self.assertEqual(state["counts"]["ahead"], 0)

    def test_an_empty_root_collects_nothing_without_starting_a_pool(self):
        state = collect.build_state(self.root)
        self.assertEqual(state["repos"], [])
        self.assertEqual(state["counts"]["repos"], 0)

    def test_the_root_comes_from_the_environment(self):
        self.assertEqual(
            collect.repo_root({"SD_REPO_ROOT": "/tmp/elsewhere"}),
            Path("/tmp/elsewhere"),
        )


class CacheTests(FleetHarness):
    def test_a_second_read_inside_the_window_does_not_recollect(self):
        self.make_repo("one")
        cache = server.Cache(self.root, seconds=60)
        first = cache.state(now=100.0)
        self.make_repo("two")
        second = cache.state(now=110.0)
        self.assertEqual(len(second["repos"]), len(first["repos"]))

    def test_the_window_expiring_recollects(self):
        self.make_repo("one")
        cache = server.Cache(self.root, seconds=5)
        cache.state(now=100.0)
        self.make_repo("two")
        self.assertEqual(len(cache.state(now=200.0)["repos"]), 2)

    def test_the_default_clock_is_used_when_none_is_given(self):
        cache = server.Cache(self.root, seconds=60)
        self.assertEqual(cache.state()["counts"]["repos"], 0)


class CommandLineTests(FleetHarness):
    def run_cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        original = collect.repo_root
        collect.repo_root = lambda environ=None: self.root  # type: ignore[assignment]
        try:
            code = sd_dashboard.main(list(argv), out=out)
        finally:
            collect.repo_root = original  # type: ignore[assignment]
        return code, out.getvalue()

    def test_index_reports_counts(self):
        self.make_repo("a")
        code, output = self.run_cli("index")
        self.assertEqual(code, 0)
        self.assertIn("1 repos", output)

    def test_dump_is_json_and_identical_across_runs(self):
        self.make_repo("a")
        self.make_repo("group/b")
        first = self.run_cli("index", "--dump")[1]
        second = self.run_cli("index", "--dump")[1]
        self.assertEqual(first, second, "the dump is not canonical")
        self.assertEqual(json.loads(first)["counts"]["repos"], 2)

    def test_no_verb_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_cli()

    def test_no_verb_accepts_a_repository_path(self):
        """R10-D6: the dashboard reads many repos, and is aimed at none."""
        banned = {"--repo", "--repo-path", "--root", "--checkout", "--directory"}
        parser = sd_dashboard.build_parser()
        actions = list(parser._actions)
        for action in parser._actions:
            if hasattr(action, "choices") and action.choices:
                for sub in action.choices.values():
                    actions.extend(sub._actions)
        named = {opt for action in actions for opt in action.option_strings}
        self.assertEqual(named & banned, set())


class ServerRouteTests(FleetHarness):
    def test_the_handler_serves_three_paths_and_refuses_the_rest(self):
        handler = server.make_handler(server.Cache(self.root), "// script")
        self.assertTrue(hasattr(handler, "do_GET"))
        self.assertFalse(hasattr(handler, "do_POST"), "the view grew a write path")
        self.assertFalse(hasattr(handler, "do_PUT"))
        self.assertFalse(hasattr(handler, "do_DELETE"))

    def test_the_client_script_is_readable_from_the_package(self):
        self.assertIn("api/state", server.script_source())
