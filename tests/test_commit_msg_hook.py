"""The commit-msg tier of sd:1931: `hooks/commit-msg`, installed by `make hooks`.

Git reads trailers from a message's final paragraph only. b0c440ad on sd:1910
put `Needed-by: sd:1910` in a paragraph of its own above the `Authored-with:`
block, `git log --format='%(trailers:key=Needed-by,valueonly)'` printed
nothing, and the pre-commit hook passed it because it reads staged files, not
the message. Three things are held here.

`sd_lib.unread_trailers` agrees with git. Each fixture is committed in a
throwaway repository and read back with `git log --format=%(trailers)`, the
form every sd reader uses; a line the function calls read must come back, and
a line it calls stray must not.

The hook refuses a message whose checked trailer git will not read, names the
line, says how to fix it, and lands no commit. A message that states no
checked trailer commits as before, and `SD_SKIP_HOOKS=1` does not skip it.

`make hooks` links it beside the pre-commit tier, relatively, one per clone.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402

HOOK = REPO_ROOT / "hooks" / "commit-msg"

CONTIGUOUS = (
    "fix: a thing\n\nBody.\n\n"
    "Needed-by: sd:1910\nAuthored-with: claude/anthropic\n"
    "Co-Authored-By: Claude <noreply@example.test>\n"
)
# The b0c440ad shape: one blank line above the authorship block.
SPLIT = (
    "fix: a thing\n\nBody.\n\nNeeded-by: sd:1910\n\n"
    "Authored-with: claude/anthropic\nCo-Authored-By: Claude <noreply@example.test>\n"
)
# The CLAUDE.md shape: `Authored-with:` alone, above the harness lines.
AUTHORED_SPLIT = (
    "fix: a thing\n\nAuthored-with: claude/anthropic\n\n"
    "Co-Authored-By: Claude <noreply@example.test>\nClaude-Session: abc\n"
)
# A final paragraph that is prose with one trailer in it is not a trailer block.
PROSE_LAST = (
    "fix: a thing\n\nAuthored-with: claude/anthropic\n"
    "and then a sentence that is not a trailer\nand another one\nand a third\n"
)
PLAIN = "fix: a thing\n\nNo trailers at all.\n"
QUOTED = "docs: explain\n\n    Authored-with: claude/anthropic\n\nsays who wrote it.\n"
FOLDED = (
    "fix: a thing\n\nAuthored-with: claude/anthropic\n"
    "Co-Authored-By: Claude\n  <noreply@example.test>\n"
)
DIVIDER = (
    "fix: a thing\n\nBody.\n---\nmore body\n\n"
    "Needed-by: sd:3\nAuthored-with: claude/anthropic\n"
)
REPEATED = (
    "fix: a thing\n\nNeeded-by: sd:4\n\n"
    "Needed-by: sd:4\nAuthored-with: claude/anthropic\n"
)

FIXTURES = {
    "CONTIGUOUS": (CONTIGUOUS, ()),
    "SPLIT": (SPLIT, ("Needed-by: sd:1910",)),
    "AUTHORED_SPLIT": (AUTHORED_SPLIT, ("Authored-with: claude/anthropic",)),
    "PROSE_LAST": (PROSE_LAST, ("Authored-with: claude/anthropic",)),
    "PLAIN": (PLAIN, ()),
    "QUOTED": (QUOTED, ()),
    "FOLDED": (FOLDED, ()),
    "DIVIDER": (DIVIDER, ()),
    "REPEATED": (REPEATED, ("Needed-by: sd:4",)),
}


def git(*args: str, cwd: pathlib.Path, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True, check=True
    ).stdout


def clean_env(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.pop("SD_SKIP_HOOKS", None)
    # Git runs the hook through `#!/usr/bin/env python3`, which under the gate
    # can be an interpreter without coverage.py; the harness's sitecustomize
    # then prints its warning on stderr. The hook is outside `.coveragerc`'s
    # include, so nothing is lost by not asking for subprocess coverage.
    env.pop("SD_COVERAGE_PROCESS_START", None)
    env.update(extra)
    return env


def scratch_repository(prefix: str) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix=prefix))
    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.email", "hook@example.invalid", cwd=root)
    git("config", "user.name", "hook", cwd=root)
    return root


def parse(root: pathlib.Path, message: str) -> str:
    return git("interpret-trailers", "--parse", "--no-divider", cwd=root, stdin=message)


class UnreadTrailersAgreeWithGit(unittest.TestCase):
    """The function's verdict, held against git's own reading of a real commit."""

    def setUp(self):
        self.root = scratch_repository("sd-1931-parse-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_each_fixture_names_exactly_the_lines_git_does_not_read(self):
        for name, (message, expected) in FIXTURES.items():
            with self.subTest(name):
                self.assertEqual(expected, sd_lib.unread_trailers(message, parse(self.root, message)))

    def test_a_line_called_read_comes_back_from_git_log_and_a_stray_one_does_not(self):
        for name, (message, _) in FIXTURES.items():
            with self.subTest(name):
                git("commit", "-q", "--allow-empty", "--no-verify", "-F", "-",
                    cwd=self.root, stdin=message)
                logged = git("log", "-1", "--format=%(trailers:unfold)", cwd=self.root)
                stray = sd_lib.unread_trailers(message, parse(self.root, message))
                read = [line for line in sd_lib.unread_trailers(message, "") if line not in stray]
                for line in read:
                    self.assertTrue(any(got.startswith(line) for got in logged.splitlines()),
                                    f"{line!r} was called read, and git log does not return it")
                if stray and name != "REPEATED":
                    for line in stray:
                        self.assertNotIn(line, logged.splitlines(),
                                         f"{line!r} was called stray, and git log returns it")

    def test_the_split_block_is_the_failure_the_item_reports(self):
        """Sanity for the fixture: git log really does lose the demoted key."""
        git("commit", "-q", "--allow-empty", "--no-verify", "-F", "-", cwd=self.root, stdin=SPLIT)
        self.assertEqual(
            "", git("log", "-1", "--format=%(trailers:key=Needed-by,valueonly)", cwd=self.root).strip()
        )


class CommitAuthor(unittest.TestCase):
    """`sd_lib.commit_author` and `states_author`, the two halves the hook calls (sd:1295)."""

    def unread(self):
        raise AssertionError("a reserved author must not read the registry")

    def test_reserved_vendorless_authors_read_no_registry(self):
        for name in ("human", " script "):
            with self.subTest(name):
                self.assertEqual(sd_lib.commit_author(name, self.unread), name.strip())

    def test_an_unreadable_registry_refuses_naming_the_variable(self):
        with self.assertRaisesRegex(sd_lib.TrailerError, "SD_AUTHOR='claude'.*no such file"):
            sd_lib.commit_author("claude", lambda: (None, "no such file"))

    def test_only_an_unindented_line_states_the_author(self):
        self.assertTrue(sd_lib.states_author("x\n\nAuthored-with: human\n"))
        self.assertFalse(sd_lib.states_author(QUOTED))
        self.assertFalse(sd_lib.states_author(PLAIN))

class HookFixture(unittest.TestCase):
    """`hooks/commit-msg` through a real `git commit`, installed by `make hooks`."""

    def setUp(self):
        self.assertTrue(HOOK.is_file(), f"{HOOK} is missing")
        self.root = scratch_repository("sd-1931-hook-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "hooks").mkdir()
        (self.root / "bin").mkdir()
        shutil.copy2(HOOK, self.root / "hooks" / "commit-msg")
        # The pre-commit tier is not under test here; a stub stands in for it
        # so `make hooks` has both files to link.
        stub = self.root / "hooks" / "pre-commit"
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
        for name in ("sd_lib.py", "sd_registry.py"):
            shutil.copy2(REPO_ROOT / "bin" / name, self.root / "bin" / name)
        shutil.copy2(REPO_ROOT / "Makefile", self.root / "Makefile")
        made = subprocess.run(["make", "hooks"], cwd=self.root, env=clean_env(),
                              capture_output=True, text=True, check=False)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        self.made = made

    def commit(self, message: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-F", "-"], cwd=self.root, input=message,
            env=clean_env(**extra), capture_output=True, text=True, check=False,
        )

    def commits(self) -> int:
        result = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=self.root,
                                capture_output=True, text=True, check=False)
        return int(result.stdout.strip()) if result.returncode == 0 else 0


class TheHook(HookFixture):
    """The trailer check: a checked trailer git will not read is refused."""

    def test_make_hooks_links_the_commit_msg_hook_relatively(self):
        link = self.root / ".git" / "hooks" / "commit-msg"
        self.assertTrue(link.is_symlink(), f"{link} is not a symlink")
        self.assertEqual(os.readlink(link), "../../hooks/commit-msg")
        self.assertIn("commit-msg -> ../../hooks/commit-msg", self.made.stdout)
        self.assertIn("pre-commit -> ../../hooks/pre-commit", self.made.stdout)

    def test_a_split_trailer_block_is_refused_by_line_and_lands_nothing(self):
        result = self.commit(SPLIT)
        self.assertNotEqual(result.returncode, 0, "the commit went through")
        self.assertIn("commit-msg: refused", result.stderr)
        self.assertIn("    Needed-by: sd:1910", result.stderr)
        self.assertIn("final paragraph", result.stderr)
        self.assertIn("%(trailers:key=Authored-with,valueonly)", result.stderr)
        self.assertEqual(0, self.commits(), "a commit landed")

    def test_an_authored_with_line_split_from_the_harness_lines_is_refused(self):
        result = self.commit(AUTHORED_SPLIT)
        self.assertNotEqual(result.returncode, 0, "the commit went through")
        self.assertIn("    Authored-with: claude/anthropic", result.stderr)
        self.assertEqual(0, self.commits(), "a commit landed")

    def test_a_contiguous_block_commits_and_git_reads_the_author(self):
        result = self.commit(CONTIGUOUS)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual("claude/anthropic", git(
            "log", "-1", "--format=%(trailers:key=Authored-with,valueonly)", cwd=self.root).strip())

    def test_a_message_with_no_checked_trailer_commits_as_before(self):
        for message in (PLAIN, QUOTED):
            with self.subTest(message=message.splitlines()[0]):
                result = self.commit(message)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual("", result.stderr)

    def test_the_pre_commit_bypass_does_not_skip_the_trailer_check(self):
        result = self.commit(SPLIT, SD_SKIP_HOOKS="1")
        self.assertNotEqual(result.returncode, 0, "SD_SKIP_HOOKS skipped the trailer check")
        self.assertEqual(0, self.commits(), "a commit landed")



class TheHookWritesTheAuthor(HookFixture):
    """sd:1295: `SD_AUTHOR` names the author, and the hook writes `Authored-with:` at commit time.

    Without it a branch whose commits said nothing took one empty `sd
    attribute` commit per review round. The value is what `sd attribute`
    writes for the same name (`sd_lib.attribution_value`), so the two agree.
    """

    def setUp(self):
        super().setUp()
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="sd-1295-home-"))
        self.addCleanup(shutil.rmtree, self.home, ignore_errors=True)
        shared = self.home / ".local" / "share" / "sd"
        shared.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "providers.yaml", shared / "providers.yaml")

    def authored(self, message: str, author: str) -> tuple[subprocess.CompletedProcess[str], str]:
        result = self.commit(message, SD_AUTHOR=author, HOME=str(self.home))
        said = git("log", "-1", "--format=%(trailers:key=Authored-with,valueonly)",
                   cwd=self.root).strip() if self.commits() else ""
        return result, said

    def test_a_registry_entry_is_written_as_entry_and_vendor(self):
        result, said = self.authored(PLAIN, "claude")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(said, "claude/anthropic")

    def test_it_joins_the_final_trailer_paragraph_first(self):
        message = "fix: a thing\n\nBody.\n\nCo-Authored-By: Claude <noreply@example.test>\nClaude-Session: abc\n"
        result, said = self.authored(message, "codex")
        self.assertEqual((result.returncode, said), (0, "codex/openai"), result.stderr)
        body = git("log", "-1", "--format=%B", cwd=self.root).rstrip()
        self.assertTrue(body.endswith("\n\nAuthored-with: codex/openai\nCo-Authored-By: Claude "
                                      "<noreply@example.test>\nClaude-Session: abc"), body)

    def test_script_and_human_need_no_registry(self):
        shutil.rmtree(self.home / ".local")
        for author in ("script", "human"):
            with self.subTest(author):
                result, said = self.authored(PLAIN, author)
                self.assertEqual((result.returncode, said), (0, author), result.stderr)

    def test_a_message_that_says_its_author_keeps_it(self):
        result, said = self.authored("fix: a thing\n\nAuthored-with: human\n", "claude")
        self.assertEqual((result.returncode, said), (0, "human"), result.stderr)

    def test_a_name_nothing_resolves_is_refused_and_lands_nothing(self):
        result, _ = self.authored(PLAIN, "nosuch")
        self.assertNotEqual(result.returncode, 0, "the commit went through")
        self.assertIn("commit-msg: refused", result.stderr)
        self.assertIn("SD_AUTHOR", result.stderr)
        self.assertIn("no registry entry named 'nosuch'", result.stderr)
        self.assertEqual(0, self.commits(), "a commit landed")

    def test_dependabot_is_refused(self):
        """A local commit is never Dependabot's; that claim rests on the identity GitHub writes."""
        result, _ = self.authored(PLAIN, "dependabot")
        self.assertIn("dependabot", result.stderr)
        self.assertEqual(0, self.commits(), "a commit landed")

    def test_without_sd_author_nothing_is_written(self):
        result = self.commit(PLAIN, HOME=str(self.home))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual("", git("log", "-1", "--format=%(trailers:key=Authored-with,valueonly)",
                                 cwd=self.root).strip())

if __name__ == "__main__":
    unittest.main()
