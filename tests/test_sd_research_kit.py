"""The research kit's entrypoint: its verb surface and its two invariants.

`.coveragerc` keeps the non-installer `bin/` tools out of the 100% gate because
their interesting branches depend on optional local CLIs, and covers them with
focused tests instead. This is that file for `sd-research-kit`.

Two things are worth pinning rather than the whole surface. The kit took
`render [repo_dir]` and `checklinks [repo_dir ...]` before it moved into this
pack, and R10-D6 says a command resolves its repository from the current working
directory and nowhere else -- `test_verb_inventory` cannot see that, because it
reads `add_argument` calls and this tool parses its own argv. And the renderer's
stylesheet is inlined as Python because `bin/` holds Python only, so the thing
that would silently regress is the CSS going missing from the rendered page.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KIT = REPO_ROOT / "bin" / "sd-research-kit"
VERBS = ("render", "checklinks", "review", "pins", "conventions")


def load_kit():
    """Load the entrypoint, which has no `.py` suffix to infer a loader from.

    `spec_from_file_location` returns None for an extensionless path, so the
    loader is named explicitly. This is the same shape `bin/` itself uses to
    reach its sibling modules.
    """

    name = "sd_research_kit_under_test"
    loader = importlib.machinery.SourceFileLoader(name, str(KIT))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def run(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(KIT), *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )


class VerbSurfaceTests(unittest.TestCase):
    def test_help_exits_zero_and_names_every_verb(self) -> None:
        result = run("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for verb in VERBS:
            self.assertIn(verb, result.stdout, f"{verb} missing from usage")

    def test_an_unknown_verb_fails(self) -> None:
        result = run("publish")
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage:", result.stderr)

    def test_no_verb_fails(self) -> None:
        self.assertEqual(run().returncode, 1)


class RepositoryFromCwdTests(unittest.TestCase):
    """R10-D6, asserted on the surface that actually parses the argument."""

    def test_no_verb_accepts_a_path(self) -> None:
        offenders = []
        for verb in VERBS:
            result = run(verb, ".")
            if result.returncode == 0 or "takes no arguments" not in result.stderr:
                offenders.append(verb)
        self.assertEqual(
            offenders,
            [],
            "R10-D6: these verbs accepted a path argument, so the command can be "
            "pointed at a checkout the caller is not standing in",
        )

    def test_the_usage_says_so(self) -> None:
        self.assertIn("There is no repo argument", run("--help").stdout)


class ConventionsTests(unittest.TestCase):
    def test_conventions_prints_a_path_that_exists(self) -> None:
        """The standard is a shipped skill reference; a moved file breaks silently.

        `conventions` is how every research repo's own CLAUDE.md is told where the
        standard lives, so a stale path here is a broken pointer in six other
        repositories rather than a broken one here.
        """

        result = run("conventions")
        self.assertEqual(result.returncode, 0, result.stderr)
        printed = Path(result.stdout.strip())
        self.assertTrue(printed.is_file(), f"{printed} does not exist")
        self.assertEqual(
            printed,
            REPO_ROOT / "skills" / "sd-research-repo" / "references" / "conventions.md",
        )


class InlinedStylesheetTests(unittest.TestCase):
    def test_the_renderer_carries_its_css(self) -> None:
        kit = load_kit()
        tokens = kit.load("sd_research_tokens")
        self.assertIn(":root", tokens.TOKENS_CSS)
        self.assertGreater(len(tokens.TOKENS_CSS), 4000, "stylesheet looks truncated")

    def test_no_stylesheet_file_ships_beside_the_renderer(self) -> None:
        """`bin/` is Python only; a `.css` there fails the lint target loudly."""

        self.assertEqual(list((REPO_ROOT / "bin").glob("*.css")), [])


class CacheVenvTests(unittest.TestCase):
    def test_the_bootstrap_venv_never_lands_beside_the_script(self) -> None:
        kit = load_kit()
        venv = kit.cache_venv()
        self.assertNotIn(str(REPO_ROOT / "bin"), str(venv))
        self.assertEqual(venv.name, "venv")
        self.assertEqual(venv.parent.name, "sd-research-kit")

    def test_xdg_cache_home_is_honoured(self) -> None:
        kit = load_kit()
        with unittest.mock.patch.dict("os.environ", {"XDG_CACHE_HOME": "/tmp/xdg-probe"}):
            self.assertEqual(
                kit.cache_venv(), Path("/tmp/xdg-probe/sd-research-kit/venv")
            )


class WorkItemCoverageTests(unittest.TestCase):
    """`review` used to pass a repository whose work items were failing.

    The research conventions govern the documents in `research.conf.py`;
    `sd-plan` governs the items under `docs/work/`. A repository can follow both
    at once, and until the two linters were connected this one printed
    "Mechanical checks pass" while `sd-docs-lint` returned 1 in the same
    directory -- true about this tool's scope, false about the repository.
    """

    def make_repo(self, tmp: Path, *, work: bool) -> Path:
        (tmp / "research.conf.py").write_text('PROJECT = "probe"\nDOCS = []\n')
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        if work:
            item = tmp / "docs" / "work" / "2026-01-01-probe"
            item.mkdir(parents=True)
            (item / "prd.md").write_text(
                "---\ntitle: probe\nstatus: draft\ncreated: 2026-01-01\n---\n# Probe\n"
            )
        return tmp

    def test_a_failing_work_item_fails_the_review(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = self.make_repo(Path(raw), work=True)
            result = run("review", cwd=repo)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("2026-01-01-probe", result.stdout)
        self.assertIn("status 'draft' is not one of", result.stdout)

    def test_the_paths_are_reported_repo_relative(self) -> None:
        """The lint resolves its root through git, which returns the real path.

        On macOS a temporary directory is `/var/...` to the caller and
        `/private/var/...` to git, so a prefix strip against the caller's cwd
        alone shortens nothing and the review prints absolute paths beside
        repo-relative document names.
        """

        with tempfile.TemporaryDirectory() as raw:
            repo = self.make_repo(Path(raw), work=True)
            result = run("review", cwd=repo)
        self.assertIn("FAIL docs/work/2026-01-01-probe/prd.md", result.stdout)

    def test_a_missing_linter_is_a_failure_not_a_pass(self) -> None:
        """A gate that cannot run has not been passed.

        Warning and returning 0 would reproduce this function's own bug one
        level down -- a clean review precisely when the checking is absent.
        """

        module = load_kit().load("sd_research_review")
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "docs" / "work").mkdir(parents=True)
            real = os.path.exists
            with unittest.mock.patch.object(
                module.os.path,
                "exists",
                lambda p: False if str(p).endswith("sd-docs-lint") else real(p),
            ):
                self.assertEqual(module.work_items(str(repo)), 1)

    def test_a_repository_with_no_work_directory_is_untouched(self) -> None:
        """The cost is paid only by repositories that keep work items."""

        with tempfile.TemporaryDirectory() as raw:
            repo = self.make_repo(Path(raw), work=False)
            result = run("review", cwd=repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Mechanical checks pass", result.stdout)
        self.assertNotIn("docs/work", result.stdout)


if __name__ == "__main__":
    unittest.main()
