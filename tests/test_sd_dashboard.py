"""Behaviour tests for what is left of the pack dashboard, and what retired.

Two things survive to be tested: `bin/sd-dashboard`, a parser with no verb
that answers usage and points at the system dashboard, and the tree under
`dashboard/`, which since sd:719 step 6 holds `dashboard/__init__.py` alone.
Everything else went in order: the tracker index and its clients at step 4,
the fleet collectors at step 5, and at step 6 the Now ranking, the action
runner, the work collector, the server and the client script, whose views
are served by the system dashboard (system pull request #428). Step 7
deletes the directory, the CLI and this module's tracked-files test with it.
Asserted from the filesystem and the tree, never from a string the author
already knew: a file restored on its own is red here.
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
    """sd:719 steps 4, 5 and 6: the index, the fleet collectors and the views are gone.

    Step 4: the system dashboard serves PRs and Issues from `sd_db.shadow`
    (system pull request #411), so the pack's own index -- `dashboard/store.py`,
    the two tracker clients, `sd-trackers` and the `index` verb that filled it
    -- retired. Step 5: Operations > Repos and Sessions on the system dashboard
    (system pull request #427) read the fleet through `sd_dashboard/fleet.py`,
    so `dashboard/collect.py`, `dashboard/sessions.py` and `dashboard/skills.py`
    retired with the `/api/state`, `/api/sessions` and `/api/skills` routes.
    Step 6: Today on the system dashboard opens with the Now ranking, served
    from `sd_dashboard/now_screen.py` through `/api/now` (system pull request
    #428), and `sd work deliver` is the write `deliver` used to make, so
    `dashboard/now.py`, `dashboard/actions.py`, `dashboard/work.py`,
    `dashboard/server.py` and `dashboard/app.js` retired with their four test
    modules. Asserted from the filesystem and the tree, never from a string the
    author already knew: a file restored on its own is red here.
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
        "dashboard/now.py",
        "dashboard/actions.py",
        "dashboard/work.py",
        "dashboard/server.py",
        "dashboard/app.js",
        "tests/test_dashboard_now.py",
        "tests/test_dashboard_work.py",
        "tests/test_dashboard_deliver.py",
        "tests/test_dashboard_actions.py",
    )
    RETIRED_MODULES = frozenset({
        "store", "github", "jira", "collect", "sessions", "skills",
        "now", "actions", "work", "server",
    })

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
        self.assertEqual(
            self.retired_imports(multiline, "bin/x"), ["dashboard.work", "dashboard.store"])
        self.assertEqual(
            self.retired_imports("import dashboard.jira as j\n", "bin/x"), ["dashboard.jira"])
        self.assertEqual(
            self.retired_imports("from . import work, github\n", "dashboard/y.py"),
            ["dashboard.work", "dashboard.github"])
        # The fourth shape, `from .collect import discover_checkouts`: step 5's
        # importer grep missed it the way step 4's missed `from . import`, and
        # `dashboard/work.py` carried exactly that line.
        self.assertEqual(
            self.retired_imports("from .collect import discover_checkouts\n", "dashboard/w.py"),
            ["dashboard.collect"])
        self.assertEqual(self.retired_imports("from . import x\n", "tests/z.py"), [])
        # `work` was the survivor this line named until step 6 retired it too;
        # the package itself is the one name left that is not retired.
        self.assertEqual(
            self.retired_imports("from dashboard import work\n", "bin/x"), ["dashboard.work"])
        self.assertEqual(self.retired_imports("import dashboard\n", "bin/x"), [])
        self.assertEqual(self.retired_imports("#!/bin/sh\necho store\n", "bin/sh"), [])


class StepSixEndState(FleetHarness):
    """What the tree and the CLI look like between step 6 and step 7.

    Step 7 deletes `dashboard/`, `bin/sd-dashboard` and the three ceilings in
    one commit, and this class goes with them: a test that the directory
    holds one file cannot outlive the directory. Until then it is the end
    state step 6 claims, read from the tree rather than from the deletion
    list above.
    """

    def test_the_package_marker_is_the_only_tracked_file_under_dashboard(self):
        listed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--deduplicate", "--", "dashboard"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(listed, ["dashboard/__init__.py"], f"tracked under dashboard/: {listed}")

    def test_help_still_exits_zero_and_names_the_system_dashboard(self):
        """The CLI outlives its verbs by one step, and its usage says where to go."""
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "sd-dashboard"), "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage: sd-dashboard", completed.stdout)
        self.assertIn("system dashboard", completed.stdout)


if __name__ == "__main__":
    unittest.main()
