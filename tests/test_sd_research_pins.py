"""`pins` resolves the sibling tree when it is asked for, not when it is imported.

`build_index` maps a pinned `owner/name` onto a checkout on this machine, and
one of the places it looks is the tree the user keeps their clones in. That
tree used to be a module constant -- `SEARCH_ROOT = Path(os.path.expanduser(
"~/repos"))` -- so the answer was frozen into the import and there was no
argument anywhere in the module that could name a different one. Nothing
misbehaved at runtime: a run has one home and the constant named it correctly.
What could not be done was to ask the function about a tree a test had built,
which is why no test called `build_index` at all.

The load-bearing case here is `TheRealHomeIsNeverConsulted`. A test that only
asserts "the injected tree was used" still passes while the import-time read
happens, because the read is not on the path the assertion watches. So the
proof is negative and structural instead: `os.path.expanduser` and
`Path.home` are replaced with functions that raise, the module is imported
fresh under them in a child interpreter, and `build_index` is driven end to
end. Put the constant back and that child does not reach a test -- it dies in
the import.
"""

from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "bin" / "sd_research_pins.py"

#: Two names no real `~/repos` carries, so a run that reached one would be
#: telling on itself rather than quietly agreeing with the seeded tree.
SEEDED = ("sd-pins-probe-alpha", "sd-pins-probe-beta")
SEEDED_OWNER = "sd-pins-probe-owner"


def load():
    """Import `bin/sd_research_pins.py` by path -- `bin/` is not a package."""
    name = "sd_research_pins_under_test"
    loader = importlib.machinery.SourceFileLoader(name, str(MODULE))
    spec = importlib.util.spec_from_file_location(name, str(MODULE), loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def module_level(tree: ast.Module):
    """Every statement that runs at import, including indented ones.

    A module-level `if` or `try` body executes on import exactly as the top
    level does, so "module level" is a matter of what encloses a statement,
    not of what column it starts in. Function and class bodies are the real
    boundary, and they are the only thing skipped here.
    """
    stack = list(tree.body)
    while stack:
        stmt = stack.pop(0)
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        yield stmt
        for field in ("body", "orelse", "finalbody"):
            stack.extend(getattr(stmt, field, None) or [])


def seed(root: Path) -> Path:
    """A `<root>/<owner>/<name>` tree of checkouts, the shape `glob("*/*")` reads.

    `.git` is a directory and nothing else: `build_index` filters on its
    existence, and `slug` falls back to the directory name when `git remote`
    cannot answer. That keeps the fixture from depending on a real clone.
    """
    for name in SEEDED:
        (root / SEEDED_OWNER / name / ".git").mkdir(parents=True)
    return root


#: Run in a child interpreter, because the point is what happens at *import*
#: and this process has already imported the module. Both names are replaced
#: before the module is loaded, so an import-time read cannot slip past.
PROBE = r"""
import importlib.machinery, importlib.util, json, os, pathlib, sys

def fatal(*_args, **_kwargs):
    raise AssertionError("the real home was consulted")

os.path.expanduser = fatal
pathlib.Path.home = fatal

module_path, repo, siblings = sys.argv[1:4]
loader = importlib.machinery.SourceFileLoader("pins_probe", module_path)
spec = importlib.util.spec_from_file_location("pins_probe", module_path, loader=loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

index = module.build_index(repo, siblings=siblings)
print(json.dumps(sorted(index)))
"""


class TheDefaultIsStillTheAgentsOwnRepos(unittest.TestCase):
    """An injection point, not a move. `pins` must keep finding real clones."""

    def test_search_root_names_the_users_repos_directory(self) -> None:
        self.assertEqual(load().search_root(), Path(os.path.expanduser("~/repos")))

    def test_the_module_holds_no_home_at_import_time(self) -> None:
        """The constant is gone, and nothing may put one back under another name.

        This asks the syntax tree, not the text. The first version of this
        test skipped any line starting with a space, which is the same
        column-zero assumption that made the first sweep for this defect miss
        `bin/sd-dashboard` -- a module-level read nested in an `if` or a `try`
        is indented, executes at import all the same, and a `startswith` guard
        cannot see it. Walking the module body catches it wherever it sits.
        """
        tree = ast.parse(MODULE.read_bytes())
        for stmt in module_level(tree):
            if not isinstance(stmt, ast.Assign | ast.AnnAssign | ast.AugAssign):
                continue
            if stmt.value is None:
                continue
            shown = ast.unparse(stmt)
            for mark in ("expanduser", "Path.home"):
                self.assertNotIn(
                    mark, shown, f"module level home read at line {stmt.lineno}: {shown}")


class TheSiblingTreeIsTheOneTheCallerNames(unittest.TestCase):
    """What the injection buys: `build_index` against a tree the test built."""

    def test_the_index_is_exactly_the_seeded_checkouts(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            siblings = seed(Path(scratch) / "repos")
            (Path(scratch) / "doc").mkdir()
            index = load().build_index(Path(scratch) / "doc", siblings=siblings)
        self.assertEqual(sorted(index), sorted(SEEDED))
        self.assertEqual(index[SEEDED[0]], siblings / SEEDED_OWNER / SEEDED[0])

    def test_a_tree_that_is_not_there_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            (Path(scratch) / "doc").mkdir()
            index = load().build_index(
                Path(scratch) / "doc", siblings=Path(scratch) / "absent")
        self.assertEqual(index, {})


class TheRealHomeIsNeverConsulted(unittest.TestCase):
    """The structural half, and the one that cannot be satisfied by accident.

    Asserting that the seeded names came back proves the injected tree was
    read. It does not prove the real home was not *also* read on the way --
    an import-time constant is off to one side of that assertion and survives
    it intact. Making the two ways of spelling "home" raise, and then getting
    all the way to an answer, is what proves the absence.
    """

    def probe(self, repo: Path, siblings: Path) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as home:
            script = Path(home) / "probe.py"
            script.write_text(PROBE, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(script), str(MODULE), str(repo), str(siblings)],
                capture_output=True, text=True, timeout=120)

    def test_import_and_build_index_survive_a_fatal_home(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            siblings = seed(Path(scratch) / "repos")
            (Path(scratch) / "doc").mkdir()
            done = self.probe(Path(scratch) / "doc", siblings)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("the real home was consulted", done.stderr)
        self.assertEqual(json.loads(done.stdout), sorted(SEEDED))


WORKFLOW = """\
name: probe
jobs:
  probe:
    env:
      SYSTEM_REVISION: 1111111111111111111111111111111111111111
      PACK_REVISION: 2222222222222222222222222222222222222222
    steps:
      - uses: owner/pack-repo/actions/review-route@3333333333333333333333333333333333333333
      - uses: actions/checkout@4444444444444444444444444444444444444444 # v7.0.1
        with:
          repository: owner/system-repo
          ref: 5555555555555555555555555555555555555555
      - uses: actions/checkout@4444444444444444444444444444444444444444 # v7.0.1
        with:
          repository: owner/pack-repo
          ref: ${{ env.PACK_REVISION }}
"""


class FleetPinFormsTests(unittest.TestCase):
    """The four forms no ecosystem can see, read out of one workflow file.

    `uses:` names its repository; `ref:` does not, and `<NAME>_REVISION:` names
    only a word. The item's inventory was assembled by hand; this pins the
    reading so the next one is not.
    """

    def setUp(self) -> None:
        self.module = load()

    def sites(self):
        return self.module.workflow_sites(WORKFLOW)

    def test_a_uses_pin_is_read_through_a_subdirectory_action(self) -> None:
        self.assertIn(("owner/pack-repo", "3" * 40, "uses", 8), self.sites())

    def test_a_literal_ref_takes_the_repository_of_its_with_block(self) -> None:
        self.assertIn(("owner/system-repo", "5" * 40, "ref", 12), self.sites())

    def test_a_revision_env_resolves_through_the_ref_that_reads_it(self) -> None:
        """`PACK_REVISION` means the command pack because the file says so."""

        self.assertIn(("owner/pack-repo", "2" * 40, "env", 6), self.sites())

    def test_an_unconsumed_revision_env_falls_back_to_its_name(self) -> None:
        self.assertIn(("system", "1" * 40, "env", 5), self.sites())

    def test_a_third_party_action_pin_is_still_read_here(self) -> None:
        """Filtering third parties is `fleet`'s job, not the reader's."""

        self.assertIn(("actions/checkout", "4" * 40, "uses", 9), self.sites())

    def test_a_tarball_manifest_takes_its_repository_from_its_filename(self) -> None:
        found = self.module.manifest_sites(
            "/x/.github/dependencies/system-source.json",
            '{\n  "archive_sha256": "ab",\n  "source_commit": "%s"\n}\n' % ("6" * 40),
        )
        self.assertEqual(found, [("system", "6" * 40, "manifest", 3)])


class CheckoutsAtBothDepthsTests(unittest.TestCase):
    """`~/repos/system` is one level deep and is half of what the fleet pins.

    `build_index` walked `*/*` only, so the one repository that sits beside the
    org directories rather than inside one was invisible to it, and every pin
    of `system` answered "no checkout".
    """

    def test_a_checkout_directly_under_the_root_is_found(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "system" / ".git").mkdir(parents=True)
            (root / "owner" / "nested" / ".git").mkdir(parents=True)
            found = [p.name for p in load().checkouts(root)]
        self.assertEqual(sorted(found), ["nested", "system"])

    def test_an_org_directory_is_not_itself_a_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "owner" / "nested" / ".git").mkdir(parents=True)
            found = [p.name for p in load().checkouts(root)]
        self.assertEqual(found, ["nested"])


class FleetReportTests(unittest.TestCase):
    """End to end against a tree the test built, with real commits behind it."""

    def git(self, cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True, text=True)

    def upstream(self, root: Path, name: str, commits: int) -> str:
        repo = root / "owner" / name
        repo.mkdir(parents=True)
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "config", "user.email", "probe@example.invalid")
        self.git(repo, "config", "user.name", "probe")
        first = ""
        for n in range(commits):
            (repo / "f.txt").write_text(str(n))
            self.git(repo, "add", "f.txt")
            self.git(repo, "commit", "-q", "-m", f"c{n}")
            if not first:
                first = subprocess.run(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"],
                    capture_output=True, text=True, check=True).stdout.strip()
        return first

    def test_the_report_names_the_stale_site_and_leaves_third_parties_out(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            old = self.upstream(root, "system-probe", commits=4)
            consumer = root / "owner" / "consumer-probe"
            flow = consumer / ".github" / "workflows"
            flow.mkdir(parents=True)
            (consumer / ".git").mkdir()
            (flow / "tests.yml").write_text(
                "jobs:\n  t:\n    steps:\n"
                "      - uses: actions/checkout@%s # v7.0.1\n"
                "        with:\n"
                "          repository: owner/system-probe\n"
                "          ref: %s\n" % ("4" * 40, old)
            )
            rows = load().fleet(root)

        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["target"], "system-probe")
        self.assertEqual(rows[0]["where"], ".github/workflows/tests.yml:7")
        self.assertEqual(rows[0]["status"], "behind 3")

    def test_a_pin_at_the_tip_reads_current(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            self.upstream(root, "system-probe", commits=1)
            tip = subprocess.run(
                ["git", "-C", str(root / "owner" / "system-probe"), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True).stdout.strip()
            consumer = root / "owner" / "consumer-probe"
            flow = consumer / ".github" / "workflows"
            flow.mkdir(parents=True)
            (consumer / ".git").mkdir()
            (flow / "x.yml").write_text(
                "jobs:\n  t:\n    steps:\n      - uses: owner/system-probe@%s\n" % tip
            )
            rows = load().fleet(root)

        self.assertEqual([r["status"] for r in rows], ["current"])

    def test_a_repo_pinning_itself_is_not_a_fleet_pin(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            sha = self.upstream(root, "self-probe", commits=2)
            flow = root / "owner" / "self-probe" / ".github" / "workflows"
            flow.mkdir(parents=True)
            (flow / "x.yml").write_text(
                "jobs:\n  t:\n    steps:\n      - uses: owner/self-probe@%s\n" % sha
            )
            self.assertEqual(load().fleet(root), [])


if __name__ == "__main__":
    unittest.main()
