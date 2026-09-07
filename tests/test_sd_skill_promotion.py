"""Criterion 27: promotion and demotion each produce one pull request.

The criterion asks for a test that asserts the branch content, so these tests
build a whole pack checkout in a temporary directory -- `bin/`, `skills/`,
`contrib/`, a git repository, a bare remote and a `gh` that records what it was
asked to do without leaving the machine -- and then read the branch back out of
git rather than off the filesystem the verb happened to leave behind.

`sd_skill.checkout()` resolves from `__file__` and takes no path, which is
R10-D6. That is why the module is loaded from the temporary `bin/` rather than
pointed at the temporary checkout: there is no flag that would do it.
"""

import ast
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: What `gh` is asked, one argv per line, so a test can assert the shape of the
#: single call that writes -- and that there is exactly one.
GH_RECORDER = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["GH_CALLS"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:2] == ["auth"]:
    sys.exit(0)
print(json.dumps({"html_url": "https://github.com/o/r/pull/1"}))
"""

PATHS = {
    "$comment": ["Requirement 10: a path names what installs.", "Kept by the writer."],
    "paths": {
        "research": {"summary": "sources to brief", "skills": ["sd-research"]},
        "development": {"summary": "prd to merge", "skills": ["sd-ship", "sd-both"]},
        "act": {"summary": "brief to send", "skills": ["sd-both"]},
    },
}


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


class PackCase(unittest.TestCase):
    """A pack checkout of its own, with a remote and a `gh` that never calls out."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "pack"
        (self.root / "bin").mkdir(parents=True)
        for name in ("sd_skill.py", "sd-pr-state"):
            shutil.copy2(REPO_ROOT / "bin" / name, self.root / "bin" / name)
        self.write_skill("skills", "sd-research")
        self.write_skill("skills", "sd-ship")
        self.write_skill("skills", "sd-both")
        self.write_skill("contrib", "sd-candidate")
        self.paths_file = self.root / "skills" / "paths.json"
        self.paths_file.write_text(json.dumps(PATHS, indent=2) + "\n", encoding="utf-8")
        # The real pack ignores it at `.gitignore:7`, and without it the loader
        # below writes a `.pyc` into `bin/` and every verb here refuses a dirty
        # checkout -- an artefact of the harness, not of the code under test.
        (self.root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")

        git(self.root, "init", "--quiet", "--initial-branch", "main")
        git(self.root, "config", "user.email", "t@example.invalid")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "-m", "the pack")
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(self.remote)], check=True)
        # `remote_slug` parses `owner/repo` out of origin's URL rather than
        # asking `gh`, so origin has to *look* like GitHub. `pushInsteadOf`
        # gives it a GitHub URL to read while every push still lands in the bare
        # repository above, which keeps the test off the network. Plain
        # `insteadOf` would not do: it rewrites `git remote get-url` too, and
        # the tool would read the temporary path back.
        git(self.root, "remote", "add", "origin", "git@github.com:o/r.git")
        git(self.root, "config", f"url.{self.remote}.pushInsteadOf", "git@github.com:o/r.git")

        self.calls = self.tmp / "gh-calls"
        fake_bin = self.tmp / "fake-bin"
        fake_bin.mkdir()
        gh = fake_bin / "gh"
        gh.write_text(GH_RECORDER, encoding="utf-8")
        gh.chmod(0o755)
        for key, value in (("GH_CALLS", str(self.calls)),
                           ("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")):
            was = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, v=was: os.environ.__setitem__(k, v) if v
                            else os.environ.pop(k, None))
        self.skill = self.load()

    def write_skill(self, where: str, name: str) -> None:
        directory = self.root / where / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")

    def load(self):
        """`sd_skill` from the temporary `bin/`, so `checkout()` resolves there."""
        if str(REPO_ROOT / "bin") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "bin"))
        path = str(self.root / "bin" / "sd_skill.py")
        loader = importlib.machinery.SourceFileLoader("sd_skill_under_test", path)
        spec = importlib.util.spec_from_file_location("sd_skill_under_test", path, loader=loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def run_verb(self, handler, **kwargs) -> int:
        class Args:
            pass
        args = Args()
        for key, value in kwargs.items():
            setattr(args, key, value)
        return handler(args)

    def gh_calls(self) -> list[list[str]]:
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def on_branch(self, branch: str, path: str) -> str:
        return git(self.root, "show", f"{branch}:{path}")

    def tree(self, branch: str) -> list[str]:
        return git(self.root, "ls-tree", "-r", "--name-only", branch).splitlines()


class ThePromotionBranch(PackCase):
    """The criterion's own assertion, read out of git and not off disk."""

    def test_the_directory_moved_and_the_path_names_it(self):
        self.assertEqual(0, self.run_verb(self.skill.skill_promote,
                                          name="sd-candidate", path="development"))
        files = self.tree("promote/sd-candidate")
        self.assertIn("skills/sd-candidate/SKILL.md", files)
        self.assertNotIn("contrib/sd-candidate/SKILL.md", files)
        paths = json.loads(self.on_branch("promote/sd-candidate", "skills/paths.json"))["paths"]
        self.assertIn("sd-candidate", paths["development"]["skills"])
        self.assertNotIn("sd-candidate", paths["research"]["skills"])

    def test_main_is_untouched(self):
        self.run_verb(self.skill.skill_promote, name="sd-candidate", path="development")
        files = self.tree("main")
        self.assertIn("contrib/sd-candidate/SKILL.md", files)
        self.assertNotIn("skills/sd-candidate/SKILL.md", files)

    def test_the_branch_reached_the_remote(self):
        self.run_verb(self.skill.skill_promote, name="sd-candidate", path="development")
        refs = git(self.root, "ls-remote", "--heads", str(self.remote))
        self.assertIn("refs/heads/promote/sd-candidate", refs)

    def test_the_skills_list_stays_sorted(self):
        self.run_verb(self.skill.skill_promote, name="sd-candidate", path="development")
        paths = json.loads(self.on_branch("promote/sd-candidate", "skills/paths.json"))["paths"]
        self.assertEqual(sorted(paths["development"]["skills"]),
                         paths["development"]["skills"])


class TheDemotionBranch(PackCase):
    def test_the_directory_moved_back(self):
        self.assertEqual(0, self.run_verb(self.skill.skill_demote, name="sd-ship"))
        files = self.tree("demote/sd-ship")
        self.assertIn("contrib/sd-ship/SKILL.md", files)
        self.assertNotIn("skills/sd-ship/SKILL.md", files)

    def test_a_skill_on_two_paths_is_dropped_from_both(self):
        """`paths.json`'s own comment says a skill may ride two paths."""
        self.run_verb(self.skill.skill_demote, name="sd-both")
        paths = json.loads(self.on_branch("demote/sd-both", "skills/paths.json"))["paths"]
        self.assertNotIn("sd-both", paths["development"]["skills"])
        self.assertNotIn("sd-both", paths["act"]["skills"])


class WhatTheWriterMustNotDestroy(PackCase):
    def test_the_comment_block_survives(self):
        """`read_paths` returns `data["paths"]`; a writer using it would drop this."""
        self.run_verb(self.skill.skill_promote, name="sd-candidate", path="development")
        document = json.loads(self.on_branch("promote/sd-candidate", "skills/paths.json"))
        self.assertEqual(PATHS["$comment"], document["$comment"])
        self.assertEqual(["$comment", "paths"], list(document))

    def test_the_other_paths_are_untouched(self):
        self.run_verb(self.skill.skill_promote, name="sd-candidate", path="development")
        paths = json.loads(self.on_branch("promote/sd-candidate", "skills/paths.json"))["paths"]
        self.assertEqual(PATHS["paths"]["research"], paths["research"])
        self.assertEqual(PATHS["paths"]["act"], paths["act"])


class WhatItRefuses(PackCase):
    def refusal(self, handler, **kwargs) -> str:
        with self.assertRaises(self.skill.SkillRefusal) as caught:
            self.run_verb(handler, **kwargs)
        return str(caught.exception)

    def test_a_dirty_checkout(self):
        (self.root / "stray.md").write_text("unrelated work\n", encoding="utf-8")
        self.assertIn("uncommitted changes", self.refusal(
            self.skill.skill_promote, name="sd-candidate", path="development"))

    def test_nothing_is_pushed_when_the_checkout_is_dirty(self):
        (self.root / "stray.md").write_text("unrelated work\n", encoding="utf-8")
        self.refusal(self.skill.skill_promote, name="sd-candidate", path="development")
        self.assertEqual("", git(self.root, "ls-remote", "--heads", str(self.remote)))
        self.assertEqual([], self.gh_calls())

    def test_a_skill_that_is_not_in_contrib(self):
        self.assertIn("available:", self.refusal(
            self.skill.skill_promote, name="sd-absent", path="development"))

    def test_a_path_that_does_not_exist(self):
        self.assertIn("no path named", self.refusal(
            self.skill.skill_promote, name="sd-candidate", path="operations"))

    def test_a_skill_no_path_names(self):
        self.write_skill("skills", "sd-unnamed")
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "-m", "an unnamed directory")
        self.assertIn("nothing to demote", self.refusal(
            self.skill.skill_demote, name="sd-unnamed"))

    def test_promotion_over_an_existing_directory(self):
        self.write_skill("skills", "sd-candidate")
        self.assertIn("would overwrite", self.refusal(
            self.skill.skill_promote, name="sd-candidate", path="development"))


class TheFirstWriteToGitHub(PackCase):
    def test_it_is_one_post_and_only_one(self):
        self.run_verb(self.skill.skill_promote, name="sd-candidate", path="development")
        posts = [call for call in self.gh_calls() if "--method" in call]
        self.assertEqual(1, len(posts), self.gh_calls())
        call = posts[0]
        self.assertEqual(["api", "--method", "POST"], call[:3])
        self.assertTrue(call[3].endswith("/pulls"), call[3])
        fields = dict(pair.split("=", 1) for pair in call[5::2])
        self.assertEqual("promote/sd-candidate", fields["head"])
        self.assertEqual("main", fields["base"])
        self.assertIn("sd-candidate", fields["title"])

    def test_the_url_is_what_the_verb_prints(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.run_verb(self.skill.skill_promote, name="sd-candidate", path="development")
        self.assertEqual("https://github.com/o/r/pull/1", out.getvalue().strip())


class WhereThePullRequestIsOpened(unittest.TestCase):
    """"Opened by the library and never by the dashboard directly."""

    def test_the_dashboard_writes_to_neither_github_nor_a_remote(self):
        offenders = []
        for path in sorted((REPO_ROOT / "dashboard").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            # Reads are not the question. `dashboard/github.py:156` runs
            # `gh api graphql` to search pull requests, and criterion 27 forbids
            # the dashboard *opening* one, which is a write.
            for verb in ("--method", "git push", "pr create", '"push"'):
                if verb in text:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {verb}")
        self.assertEqual([], offenders)

    def test_the_library_is_the_only_place_that_posts(self):
        """One `--method` anywhere in `bin/`, and it is the promotion opener."""
        writers = []
        for path in sorted((REPO_ROOT / "bin").iterdir()):
            if path.is_dir():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:  # pragma: no cover - bin/ holds no binaries
                continue
            if '"--method"' in text:
                writers.append(path.name)
        self.assertEqual(["sd_skill.py"], writers)

    def test_the_opener_shares_one_body_with_both_directions(self):
        """The direction is a parameter, so the git half cannot drift apart."""
        module = ast.parse((REPO_ROOT / "bin" / "sd_skill.py").read_text(encoding="utf-8"))
        callers = [
            node.name for node in module.body
            if isinstance(node, ast.FunctionDef)
            and any(isinstance(inner, ast.Call)
                    and getattr(inner.func, "id", "") == "move_in_a_pull_request"
                    for inner in ast.walk(node))
        ]
        self.assertEqual(["skill_promote", "skill_demote"], callers)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
