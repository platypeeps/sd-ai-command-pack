"""Behaviour tests for the dashboard's collector and CLI.

Real git repositories in a scratch root, because every fact the collector
reports comes out of `git` and a mocked one would only prove the mock agrees
with itself. The properties worth pinning are the ones a future tab could break
without noticing: that discovery enumerates rather than recites, that a missing
upstream reports absence instead of zero, and that the server's verb surface
stays two (`tests/test_dashboard_actions.py` holds what the write path is
allowed to do). The CLI has no verb left since sd:719 step 4 retired `index`,
and the tests on it assert that.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.machinery
import importlib.util
import io
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
        out = io.StringIO()
        code = sd_dashboard.main(list(argv), out=out)
        return code, out.getvalue()

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


class RetiredTrackerIndexTests(FleetHarness):
    """sd:719 step 4: the legacy tracker index is gone from the pack.

    The system dashboard serves PRs and Issues from `sd_db.shadow` (system
    pull request #411), so the pack's own index -- `dashboard/store.py`, the
    two tracker clients, `sd-trackers` and the `index` verb that filled it --
    retires. Asserted from the filesystem and the index, never from a string
    the author already knew: a file restored on its own is red here.
    """

    RETIRED = (
        "bin/sd-trackers",
        "dashboard/store.py",
        "dashboard/github.py",
        "dashboard/jira.py",
        "tests/test_sd_trackers.py",
        "tests/test_sd_dashboard_index.py",
    )
    RETIRED_MODULES = frozenset({"store", "github", "jira"})

    @classmethod
    def retired_imports(cls, text: str, relative: str) -> list[str]:
        """Every import statement in `text` that names a retired module.

        Parsed with `ast`, not matched by line (review-1005): a parenthesised
        `from dashboard import (\n    store,\n)` spans lines, and a
        line-anchored regex read it as clean. Three shapes are caught --
        `import dashboard.store`, `from dashboard import store` and the
        package-relative `from . import store` -- and a file `ast` cannot
        parse is not a Python importer.
        """
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            return []
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                relative_to_dashboard = node.level and relative.startswith("dashboard/")
                if module == "dashboard" or relative_to_dashboard:
                    names = [f"dashboard.{alias.name}" for alias in node.names]
                else:
                    names = [module]
            else:
                continue
            found.extend(
                name for name in names
                if name.startswith("dashboard.") and name.split(".")[1] in cls.RETIRED_MODULES
            )
        return found

    def test_no_verb_remains_and_index_exits_two_with_usage(self):
        """`index` went the way `serve` and `install` did: the parser refuses it.

        Asserted whole, as step 1's test asserted `{"index"}`: a parser
        registration restored on its own is a failure here, not a warning
        somebody reads later.
        """
        parser = sd_dashboard.build_parser()
        verbs = [action for action in parser._actions
                 if hasattr(action, "choices") and action.choices]
        self.assertEqual(verbs, [], f"a verb is still registered: {verbs}")
        for gone in ("index", "serve", "install"):
            with self.subTest(verb=gone), \
                    contextlib.redirect_stderr(io.StringIO()) as err, \
                    self.assertRaises(SystemExit) as raised:
                sd_dashboard.main([gone])
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("usage: sd-dashboard", err.getvalue())
            self.assertIn("invalid choice", err.getvalue())

    def test_the_index_and_its_clients_are_not_in_the_tree(self):
        listed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--deduplicate", "--", *self.RETIRED],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(listed, [], f"still tracked: {listed}")
        present = [path for path in self.RETIRED if (REPO_ROOT / path).exists()]
        self.assertEqual(present, [], f"still on disk: {present}")

    def test_nothing_imports_the_retired_modules(self):
        """Every tracked Python file under bin/, dashboard/ and tests/, read rather than recited."""
        listed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--deduplicate", "--",
             "bin", "dashboard", "tests"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        importers = []
        for relative in listed:
            path = REPO_ROOT / relative
            if path.suffix not in ("", ".py") or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in self.retired_imports(text, relative):
                importers.append(f"{relative}: {name}")
        self.assertEqual(importers, [], f"still import the retired modules: {importers}")

    def test_a_parenthesised_import_is_seen(self):
        """The shape a line-anchored regex missed (review-1005), plus the other two."""
        multiline = "from dashboard import (\n    collect,\n    store,\n)\n"
        self.assertEqual(self.retired_imports(multiline, "bin/x"), ["dashboard.store"])
        self.assertEqual(
            self.retired_imports("import dashboard.jira as j\n", "bin/x"), ["dashboard.jira"])
        self.assertEqual(
            self.retired_imports("from . import collect, github\n", "dashboard/y.py"),
            ["dashboard.github"])
        self.assertEqual(self.retired_imports("from . import x\n", "tests/z.py"), [])
        self.assertEqual(self.retired_imports("from dashboard import collect\n", "bin/x"), [])
        self.assertEqual(self.retired_imports("#!/bin/sh\necho store\n", "bin/sh"), [])


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
