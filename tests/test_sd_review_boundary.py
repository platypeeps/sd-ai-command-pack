"""The boundaries bin/sd-review must not cross, asserted rather than promised.

Two of them are absences, and an absence is only ever proved structurally:

  * **Findings are never posted.** The tool has no network client and no code
    path that hands a finding to GitHub. This file reads the source's import
    graph and its call sites, so adding `import urllib.request` or a `gh pr
    comment` argv fails here even if no other test notices.
  * **The repository comes from cwd (R10-D6).** No option accepts a path to a
    repository, so a session cannot be pointed at another checkout.

These read the file as text and as an AST. That is deliberate: a mock-based
test would only prove the mocked path does not post.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_REVIEW = REPO_ROOT / "bin" / "sd-review"
SOURCE = SD_REVIEW.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

BIN_FILES = tuple(
    path for path in sorted((REPO_ROOT / "bin").iterdir()) if path.is_file()
)
# `sd_lib` and `sd_route` are shared core, budgeted on the design's core line
# rather than the lane's. Everything else `bin/sd-review` imports out of `bin/`
# is the lane, derived from the import graph so a module added to the lane
# starts counting against it without anyone remembering to add it here.
SHARED_CORE = frozenset({"sd_lib", "sd_route"})


def _bin_imports(path: pathlib.Path) -> frozenset:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return frozenset(names)


_BIN_MODULES = {path.stem: path for path in BIN_FILES}
REVIEW_LANE = frozenset(
    [SD_REVIEW]
    + [
        _BIN_MODULES[name]
        for name in _bin_imports(SD_REVIEW)
        if name in _BIN_MODULES and name not in SHARED_CORE
    ]
)

# Modules that can reach a network, plus the ones that wrap a client. A tool
# that never posts a finding has no business importing any of them.
NETWORK_MODULES = frozenset(
    {
        "http",
        "http.client",
        "httplib",
        "urllib",
        "urllib.request",
        "urllib.error",
        "socket",
        "ssl",
        "ftplib",
        "smtplib",
        "telnetlib",
        "xmlrpc",
        "asyncio",
        "requests",
        "httpx",
        "aiohttp",
        "urllib3",
    }
)

# Argv fragments that would publish a finding. `gh` is the pack's usual client,
# so the check is on the words, not on one spelling of the client.
POSTING_FRAGMENTS = (
    "pr comment",
    "pr review",
    "pr edit",
    "issue comment",
    "api repos",
    "/pulls/",
    "/reviews",
    "check-runs",
    "--add-label",
    "add-label",
    "create-review",
    "submit_pending",
)


def imported_names() -> set[str]:
    names: set[str] = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class NeverPostsTests(unittest.TestCase):
    def test_no_network_module_is_imported(self) -> None:
        offending = sorted(
            name
            for name in imported_names()
            if name in NETWORK_MODULES or name.split(".")[0] in NETWORK_MODULES
        )
        self.assertEqual(offending, [], f"sd-review imports network module(s): {offending}")

    def test_every_import_is_from_the_standard_library_or_this_repository(self) -> None:
        allowed = {
            "__future__",
            "argparse",
            "json",
            "os",
            "pathlib",
            "re",
            "subprocess",
            "sys",
            "tempfile",
            "typing",
            "sd_lib",
            "sd_route",
            # The installer, imported inside the one dispatch branch. It is in
            # this repository and is itself held to the never-posts assertions
            # below, so it widens the allow-list without widening the boundary.
            "sd_setup_github",
        }
        self.assertEqual(sorted(imported_names() - allowed), [])

    def test_no_posting_argv_fragment_appears_anywhere_in_the_source(self) -> None:
        lowered = SOURCE.lower()
        found = [fragment for fragment in POSTING_FRAGMENTS if fragment in lowered]
        self.assertEqual(found, [], f"sd-review contains posting fragment(s): {found}")

    def test_the_gh_client_is_never_invoked(self) -> None:
        for node in ast.walk(TREE):
            if isinstance(node, ast.Constant) and node.value == "gh":
                self.fail("sd-review names the gh client; this lane never posts")

    def test_the_only_subprocess_call_is_the_injectable_runner(self) -> None:
        calls = [
            node
            for node in ast.walk(TREE)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        self.assertEqual(len(calls), 1, "subprocess is started in more than one place")
        enclosing = [
            node.name
            for node in ast.walk(TREE)
            if isinstance(node, ast.FunctionDef) and calls[0] in list(ast.walk(node))
        ]
        self.assertIn("subprocess_runner", enclosing)

    def test_the_result_object_records_that_nothing_was_posted(self) -> None:
        self.assertIn('"posted": False', SOURCE)

    def test_nothing_is_opened_for_writing_outside_the_attempt_directory(self) -> None:
        # `write_text` appears once, seeding the codex output schema into the
        # temporary attempt directory. A second one would be a finding sink.
        self.assertEqual(SOURCE.count(".write_text("), 1)
        self.assertNotIn('open(', SOURCE.replace('.open("r"', ""))


class RepoFromCwdTests(unittest.TestCase):
    def test_no_option_takes_a_repository_path(self) -> None:
        for node in ast.walk(TREE):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
                continue
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    self.assertNotIn(
                        argument.value,
                        {"--repo", "--repository", "--path", "--root", "--cwd", "--dir"},
                        "R10-D6: sd-review resolves its repository from cwd only",
                    )

    def test_repo_root_is_resolved_from_the_process_working_directory(self) -> None:
        self.assertIn("sd_lib.repo_root(None)", SOURCE)


class SetupGithubLivesElsewhereTests(unittest.TestCase):
    """The installer landed at step 3-d; the boundary it must respect did not move.

    This class replaced one that asserted no subcommand existed. It exists now
    because `setup-github` *writes a workflow file*, and the proof above --
    "nothing here is opened for writing" -- is a structural read of this one
    file. Keeping the installer in `bin/sd_setup_github.py` is what lets that
    proof stay literal instead of growing an exception, so these assertions are
    about where the code is, not about whether it exists.
    """

    def test_the_dispatch_is_here_and_the_implementation_is_not(self) -> None:
        self.assertIn("SETUP_GITHUB_SEAM", SOURCE)
        self.assertIn("sd_setup_github", SOURCE)
        # No subparsers: they would make every existing invocation
        # positional-first and break `sd-review --scope pr`. Asserted against
        # the call graph, not the text, so the prose explaining the choice is
        # not itself a violation of it.
        calls = [
            node
            for node in ast.walk(TREE)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_subparsers"
        ]
        self.assertEqual(calls, [])
        # The workflow this pack installs is named in the installer, never here.
        self.assertNotIn("sd-review-route.yml", SOURCE)

    def test_the_installer_module_exists_and_is_the_one_that_writes(self) -> None:
        installer = (REPO_ROOT / "bin" / "sd_setup_github.py").read_text(encoding="utf-8")
        self.assertIn("sd-review-route.yml", installer)
        self.assertEqual(installer.count(".write_text("), 1)

    def test_the_installer_never_posts_either(self) -> None:
        installer = (REPO_ROOT / "bin" / "sd_setup_github.py").read_text(encoding="utf-8")
        tree = ast.parse(installer)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        offending = sorted(
            name for name in imported
            if name in NETWORK_MODULES or name.split(".")[0] in NETWORK_MODULES
        )
        self.assertEqual(offending, [])
        lowered = installer.lower()
        self.assertEqual([f for f in POSTING_FRAGMENTS if f in lowered], [])
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "gh":
                self.fail("the installer names the gh client; this lane never posts")


def _lines(path: pathlib.Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


class LineBudgetTests(unittest.TestCase):
    """Budgets measured over what they name, enumerated from the filesystem.

    Both assertions below used to be written against a remembered list rather
    than the tree, and both were wrong in the same direction: the sub-cap read
    one file while naming a lane, so splitting the lane in two hid 294 lines
    from it; the ceiling summed every file in `bin/` while the design places
    `migrate-*` outside the cap, so the migration tool was silently spending
    the backbone's budget. Deriving each set here is what keeps a future split
    or a new module from escaping the number that governs it.
    """

    def test_the_review_lane_stays_under_its_sub_cap(self) -> None:
        # The whole lane, not the entry point: `bin/sd-review` plus every
        # bin/ module it imports. A cap that measures one file is a cap you
        # can duck by adding a second file.
        lane = sorted(REVIEW_LANE)
        total = sum(_lines(path) for path in lane)
        self.assertLessEqual(
            total,
            1700,
            f"the review lane is {total} lines across {[p.name for p in lane]}",
        )

    def test_bin_stays_under_its_ceiling(self) -> None:
        # `migrate-*` is outside the ceiling by design and carries its own,
        # because it is deleted at step 7 and its lines are not the backbone's.
        counted = [path for path in BIN_FILES if not path.name.startswith("migrate-")]
        total = sum(_lines(path) for path in counted)
        self.assertLessEqual(total, 8000, f"bin/ is {total} lines")

    def test_the_shared_core_exemption_names_files_that_exist(self) -> None:
        # The one hand-written name in the lane's derivation. A rename that
        # emptied it would silently move core lines onto the lane's budget --
        # or, worse, quietly shrink the lane and hide a real overrun.
        missing = sorted(name for name in SHARED_CORE if name not in _BIN_MODULES)
        self.assertEqual(missing, [])

    def test_the_migration_tools_stay_under_theirs(self) -> None:
        migrations = [path for path in BIN_FILES if path.name.startswith("migrate-")]
        total = sum(_lines(path) for path in migrations)
        self.assertLessEqual(
            total,
            1500,
            f"migrate-* is {total} lines across {[p.name for p in migrations]}",
        )


if __name__ == "__main__":
    unittest.main()
