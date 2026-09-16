"""Behaviour tests for the dashboard's fleet discovery, its CLI, and what retired.

Real git repositories in a scratch root, because discovery reads the
filesystem and a mocked one would only prove the mock agrees with itself. The
properties worth pinning are the ones a future tab could break without
noticing: that discovery enumerates rather than recites, and that the server's
verb surface stays two (`tests/test_dashboard_actions.py` holds what the write
path is allowed to do). The CLI has no verb left since sd:719 step 4 retired
`index`, and the tests on it assert that. The repository collector itself --
`git_facts`, `collect_repos`, `build_state` and the cache in front of them --
retired with `dashboard/collect.py` at sd:719 step 5, and the tests that read
git facts went with it; `discover_checkouts` moved to `dashboard/work.py`, the
one caller left.
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

from dashboard import server, work  # noqa: E402 - after the path insert


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
        found = work.discover_checkouts(self.root)
        self.assertEqual(
            sorted((group, path.name) for group, path in found),
            [(".", "standalone"), ("platypeeps", "alpha"), ("platypeeps", "beta")],
        )

    def test_a_missing_root_is_empty_rather_than_an_error(self):
        self.assertEqual(work.discover_checkouts(self.root / "nope"), [])


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
    """sd:719 steps 4 and 5: the tracker index and the fleet collectors are gone.

    Step 4: the system dashboard serves PRs and Issues from `sd_db.shadow`
    (system pull request #411), so the pack's own index -- `dashboard/store.py`,
    the two tracker clients, `sd-trackers` and the `index` verb that filled it
    -- retired. Step 5: Operations > Repos and Sessions on the system dashboard
    (system pull request #427) read the fleet through `sd_dashboard/fleet.py`,
    so `dashboard/collect.py`, `dashboard/sessions.py` and `dashboard/skills.py`
    retired with the `/api/state`, `/api/sessions` and `/api/skills` routes.
    Asserted from the filesystem and the tree, never from a string the author
    already knew: a file restored on its own is red here.
    """

    RETIRED = (
        "bin/sd-trackers",
        "dashboard/store.py",
        "dashboard/github.py",
        "dashboard/jira.py",
        "tests/test_sd_trackers.py",
        "tests/test_sd_dashboard_index.py",
        "dashboard/collect.py",
        "dashboard/sessions.py",
        "dashboard/skills.py",
        "tests/test_dashboard_sessions.py",
        "tests/test_dashboard_skills.py",
    )
    RETIRED_MODULES = frozenset({"store", "github", "jira", "collect", "sessions", "skills"})

    @classmethod
    def retired_imports(cls, text: str, relative: str) -> list[str]:
        """Every import statement in `text` that names a retired module.

        Parsed with `ast`, not matched by line (review-1005): a parenthesised
        `from dashboard import (\n    store,\n)` spans lines, and a
        line-anchored regex read it as clean. Four shapes are caught --
        `import dashboard.store`, `from dashboard import store`, the
        package-relative `from . import store`, and `from .store import
        connect`, which names the module before the `import` and which the
        step 4 walk read as an import of `connect` -- and a file `ast` cannot
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
                if module == "dashboard" or (relative_to_dashboard and not module):
                    names = [f"dashboard.{alias.name}" for alias in node.names]
                elif relative_to_dashboard:
                    names = [f"dashboard.{module}"]
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
        multiline = "from dashboard import (\n    work,\n    store,\n)\n"
        self.assertEqual(self.retired_imports(multiline, "bin/x"), ["dashboard.store"])
        self.assertEqual(
            self.retired_imports("import dashboard.jira as j\n", "bin/x"), ["dashboard.jira"])
        self.assertEqual(
            self.retired_imports("from . import work, github\n", "dashboard/y.py"),
            ["dashboard.github"])
        # The fourth shape, `from .collect import discover_checkouts`: step 5's
        # importer grep missed it the way step 4's missed `from . import`, and
        # `dashboard/work.py` carried exactly that line.
        self.assertEqual(
            self.retired_imports("from .collect import discover_checkouts\n", "dashboard/w.py"),
            ["dashboard.collect"])
        self.assertEqual(self.retired_imports("from . import x\n", "tests/z.py"), [])
        self.assertEqual(self.retired_imports("from dashboard import work\n", "bin/x"), [])
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
        self.assertIn("api/now", server.script_source())
