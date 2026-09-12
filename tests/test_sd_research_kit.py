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
TEMPLATE = REPO_ROOT / "skills" / "sd-research-repo" / "templates" / "CLAUDE.md"


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
        # `review` now also checks CLAUDE.md against the pack's template, and a
        # repo without one is maximal drift. These tests are about work items,
        # so they start from a repo that is in sync on the other axis.
        (tmp / "CLAUDE.md").write_text(TEMPLATE.read_text(encoding="utf-8"))
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


class TemplateDriftTests(unittest.TestCase):
    """Nothing looked at `CLAUDE.md`, so three findings sat for six weeks.

    The five research repos all descend from one snapshot of
    `skills/sd-research-repo/templates/CLAUDE.md` and all carry local content of
    their own. A detector that called every difference drift would fire on every
    repo forever; one that called none would be what we had. These pin the line
    between the two.
    """

    def setUp(self) -> None:
        self.module = load_kit().load("sd_research_review")
        self.template = TEMPLATE.read_text(encoding="utf-8")

    def findings(self, repo_text: str):
        return self.module.drift(self.template, repo_text)[0]

    def test_a_verbatim_copy_has_no_findings(self) -> None:
        self.assertEqual(self.findings(self.template), [])

    def test_a_whole_local_section_is_not_drift(self) -> None:
        """Every research repo adds sections. That is the repo doing its job."""

        local = self.template + (
            "\n## Fan-out, and the filenames a subagent cannot write\n\n"
            "Reading fans out; writing does not.\n"
        )
        self.assertEqual(self.findings(local), [])

    def test_a_local_paragraph_inside_a_shared_section_is_not_drift(self) -> None:
        text = self.template.replace(
            "## Style\n",
            "## Style\n\nThis repo also spells Jira tickets `PROJ-123`.\n",
        )
        self.assertEqual(self.findings(text), [])

    def test_a_filled_in_url_is_not_drift(self) -> None:
        """The template describes the Notion folder; the repo writes the URL."""

        aside = "the repo's own Notion folder — put its URL here when the repo is set up"
        self.assertIn(aside, self.template, "the template's fill-in prompt moved")
        text = self.template.replace(aside, "https://app.notion.com/p/3c9f52b1578281")
        self.assertEqual(self.findings(text), [])

    def test_a_filled_in_slot_is_not_drift(self) -> None:
        slot = "<absolute path to this document in the checkout>"
        self.assertIn(slot, self.template, "the template's path slot moved")
        text = self.template.replace(slot, "/Users/probe/repos/research/x/00-overview/y.md")
        self.assertEqual(self.findings(text), [])

    def test_a_reworded_template_paragraph_is_drift(self) -> None:
        """The failure that actually happened: the repo kept the old wording."""

        current = "**Do not publish research as an artifact**"
        self.assertIn(current, self.template)
        text = self.template.replace(current, "**Do not publish research as a Claude artifact.**")
        found = self.findings(text)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0][1], "reworded")
        self.assertIn("Publishing", found[0][0])

    def test_a_missing_template_section_is_drift(self) -> None:
        head = "## Main document — START HERE"
        self.assertIn(head, self.template)
        before, _, rest = self.template.partition(head)
        text = before + rest.partition("\n## ")[1] + rest.partition("\n## ")[2]
        found = self.findings(text)
        self.assertIn(("`%s`" % head, "section is missing", ""), found)

    def test_a_dropped_paragraph_is_drift(self) -> None:
        gone = "Use only the directories this repo needs; do not invent new ones.\n"
        self.assertIn(gone, self.template)
        found = self.findings(self.template.replace(gone, ""))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0][1], "gone")

    def test_local_content_is_counted_not_reported(self) -> None:
        text = self.template + "\n## Local\n\nOne local block.\n"
        found, local = self.module.drift(self.template, text)
        self.assertEqual(found, [])
        self.assertEqual(local, 1)

    def test_a_repo_with_no_claude_md_fails_the_review(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(self.module.template_drift(raw), 1)

    def test_a_missing_template_is_a_failure_not_a_pass(self) -> None:
        """Same rule as the missing linter: a gate that cannot run has not passed."""

        with tempfile.TemporaryDirectory() as raw:
            (Path(raw) / "CLAUDE.md").write_text(self.template)
            with unittest.mock.patch.object(self.module, "TEMPLATE", raw + "/nope.md"):
                self.assertEqual(self.module.template_drift(raw), 1)

    def test_a_fenced_example_heading_does_not_invent_a_section(self) -> None:
        """Both files fence a markdown example whose body starts `## 1. First section`."""

        heads = [head for head, _ in self.module.sections(self.template)]
        self.assertNotIn("1. First section", heads)

    def test_review_reports_the_drift_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "research.conf.py").write_text('PROJECT = "probe"\nDOCS = []\n')
            (repo / "CLAUDE.md").write_text(
                self.template.replace(
                    "**Do not publish research as an artifact**",
                    "**Do not publish research as a Claude artifact.**",
                )
            )
            result = run("review", cwd=repo)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL CLAUDE.md", result.stdout)
        self.assertIn("Publishing", result.stdout)

    def test_review_says_in_sync_when_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            (repo / "research.conf.py").write_text('PROJECT = "probe"\nDOCS = []\n')
            (repo / "CLAUDE.md").write_text(self.template)
            result = run("review", cwd=repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CLAUDE.md: in sync with the template", result.stdout)


if __name__ == "__main__":
    unittest.main()
