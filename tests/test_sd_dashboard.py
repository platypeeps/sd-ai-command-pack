"""Behaviour tests for the dashboard's collector and CLI.

Real git repositories in a scratch root, because every fact the collector
reports comes out of `git` and a mocked one would only prove the mock agrees
with itself. The properties worth pinning are the ones a future tab could break
without noticing: that discovery enumerates rather than recites, that a missing
upstream reports absence instead of zero, that the dump is canonical, and that
the server's verb surface stays two (`tests/test_dashboard_actions.py` holds
what the write path is allowed to do).
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

from dashboard import (  # noqa: E402 - after the path insert
    collect,
    github,
    jira,
    server,
    store,
)


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

    def test_a_tilde_in_the_environment_is_expanded(self):
        """A quoted SD_REPO_ROOT="~/repos" arrives with the tilde intact."""
        self.assertEqual(
            collect.repo_root({"SD_REPO_ROOT": "~/repos"}),
            Path.home() / "repos",
        )

    def test_an_empty_environment_value_falls_back_to_the_default(self):
        self.assertEqual(collect.repo_root({"SD_REPO_ROOT": ""}), Path.home() / "repos")

    def test_a_missing_root_is_reported_as_missing_not_as_an_empty_fleet(self):
        state = collect.build_state(self.root / "nope")
        self.assertFalse(state["rootExists"])
        self.assertEqual(state["repos"], [])

    def test_a_real_but_empty_root_is_not_reported_as_missing(self):
        state = collect.build_state(self.root)
        self.assertTrue(state["rootExists"])


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
        """The CLI, with both of its outside edges tied down.

        `index` without `--dump` refreshes the issue index, which means a naive
        harness runs a real `gh` against the network and writes the operator's
        real `~/.cache/sd-ai-command-pack/index.sqlite`. That is exactly what
        happened once while 4b-i was being built, and it is why the redirection
        lives in the shared helper rather than in the one test that needs it:
        the next verb to grow a side effect gets it for free instead of
        discovering it in somebody's home directory.
        """
        out = io.StringIO()
        original_root = collect.repo_root
        original_path = store.index_path
        original_run = github._run
        original_available = github.available
        original_settings = jira.settings
        collect.repo_root = lambda environ=None: self.root  # type: ignore[assignment]
        store.index_path = lambda environ=None: (  # type: ignore[assignment]
            self.root / ".cache" / "index.sqlite"
        )
        # Two patches, doing different jobs. `available` is pinned so the
        # assertion does not depend on whether the machine running the suite
        # happens to have `gh` installed -- it consults `shutil.which` before
        # it ever reaches a runner, so patching only the runner would make this
        # test report NO_GH on a CI image without `gh` and NO_AUTH on a laptop
        # with it. `_run` is patched as the hard stop: whatever the code does,
        # no argv reaches a real binary.
        github.available = lambda runner=None: (False, github.NO_AUTH)  # type: ignore[assignment]
        github._run = lambda argv, runner=None: (1, "", "not logged in")  # type: ignore[assignment]
        # Jira gets the same treatment for the same reason: a machine with the
        # three JIRA_* variables exported would otherwise have this harness
        # open a socket against a real tenant.
        jira.settings = lambda environ=None: {  # type: ignore[assignment]
            "base": "",
            "email": "",
            "token": "",
            "jql": "",
        }
        try:
            code = sd_dashboard.main(list(argv), out=out)
        finally:
            collect.repo_root = original_root  # type: ignore[assignment]
            store.index_path = original_path  # type: ignore[assignment]
            github._run = original_run  # type: ignore[assignment]
            github.available = original_available  # type: ignore[assignment]
            jira.settings = original_settings  # type: ignore[assignment]
        return code, out.getvalue()

    def test_index_reports_counts(self):
        self.make_repo("a")
        code, output = self.run_cli("index")
        self.assertEqual(code, 0)
        self.assertIn("1 repos", output)

    def test_an_unreachable_tracker_is_a_reported_row_not_a_failure(self):
        """The fleet half answered; refusing to print it would be the bug."""
        self.make_repo("a")
        code, output = self.run_cli("index")
        self.assertEqual(code, 0, "an unreachable tracker failed the whole command")
        self.assertIn("1 repos", output)
        self.assertIn("issues[github]: not collected", output)
        self.assertIn(github.NO_AUTH, output)
        # One line per tracker, because a merged total hides that half of them
        # never answered.
        self.assertIn("issues[jira]: not collected", output)

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


class InstallTests(FleetHarness):
    """The one LaunchAgent this pack owns, written to a scratch HOME.

    Never to the real one: this test would otherwise install a service on the
    machine running the suite, and `--uninstall` would delete a plist it did
    not write if the label ever drifted.
    """

    def setUp(self):
        super().setUp()
        self.plist = self.root / "LaunchAgents" / "com.sven.sd-dashboard.plist"
        self.said: list[tuple[str, ...]] = []
        # Captured before the patch, not after: an `addCleanup` whose argument
        # is read after the assignment restores the patch instead of removing
        # it, and the leak shows up in whatever test runs next.
        for module, name in [(sd_dashboard, "PLIST"), (sd_dashboard, "launchctl"),
                             (collect, "repo_root")]:
            self.addCleanup(setattr, module, name, getattr(module, name))
        sd_dashboard.PLIST = self.plist
        sd_dashboard.launchctl = lambda *argv: (self.said.append(argv), (0, ""))[1]
        collect.repo_root = lambda environ=None: self.root  # type: ignore[assignment]

    def install(self, *argv: str) -> str:
        out = io.StringIO()
        sd_dashboard.main(["install", *argv], out=out)
        return out.getvalue()

    def test_the_plist_names_this_checkout_and_the_port_it_was_given(self):
        """Rendered from the command, so a reinstall cannot keep old arguments."""
        self.install("--port", "8767")
        body = self.plist.read_text(encoding="utf-8")
        self.assertIn("<string>8767</string>", body)
        self.assertIn(str(REPO_ROOT / "bin" / "sd-dashboard"), body)
        self.assertIn(f"<string>{self.root}</string>", body)

    def test_it_is_unloaded_before_it_is_loaded(self):
        """`bootstrap` over a loaded label fails, and a stale service is the bug."""
        self.install()
        self.assertEqual([argv[0] for argv in self.said], ["bootout", "bootstrap"])

    def test_uninstall_removes_the_plist_and_the_service(self):
        self.install()
        self.said.clear()
        output = self.install("--uninstall")
        self.assertFalse(self.plist.exists())
        self.assertEqual([argv[0] for argv in self.said], ["bootout"])
        self.assertIn("removed", output)

    def test_launchd_refusing_is_reported_and_not_an_exit_code(self):
        """The plist is written and correct; failing would say it was not."""
        sd_dashboard.launchctl = lambda *argv: (1, "Bootstrap failed: 5: Input/output error")
        out = io.StringIO()
        code = sd_dashboard.main(["install"], out=out)
        self.assertEqual(code, 0)
        self.assertIn("Bootstrap failed", out.getvalue())
        self.assertTrue(self.plist.exists())


class ServerRouteTests(FleetHarness):
    def test_the_handler_reads_and_writes_by_one_verb_each(self):
        """This test used to assert there was no `do_POST` at all.

        6b-7 gave the handler one, and the guarantee moved rather than went:
        writing is POST, POST is Host-allowlisted and token-gated, and no GET
        has a side effect. `tests/test_dashboard_actions.py` is where that is
        pinned; what is left here is the verb surface, which is still two.
        """
        handler = server.make_handler(server.Cache(self.root), "// script")
        self.assertTrue(hasattr(handler, "do_GET"))
        self.assertTrue(hasattr(handler, "do_POST"))
        self.assertFalse(hasattr(handler, "do_PUT"))
        self.assertFalse(hasattr(handler, "do_DELETE"))

    def test_the_client_script_is_readable_from_the_package(self):
        self.assertIn("api/state", server.script_source())
