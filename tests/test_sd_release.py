"""The release chain after a merge: its tag and verify (sd:6881, docs/work/2026-10-29-repo-policy/design.md)."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import sd_release  # noqa: E402

from tests.clean_env import clean_environment  # noqa: E402

RELEASE = {"verify": "check-rollout"}
ORG = {"push": "ask", "pr": "ask"}
MANAGED = {"push": "auto", "pr": "auto"}
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test"}


class World:
    """A fake of everything the chain touches; each act appends to `acts`, `fail` names the act that raises."""

    def __init__(self, *, messages=("feat: a thing",), verified=True, frozen=None, fail=None, rulings=None) -> None:
        self.messages, self.verified, self.frozen_reason = list(messages), verified, frozen
        self.fail, self.rulings = fail, rulings or {}
        self.acts: list[str] = []
        self.asked: list[str] = []

    def _act(self, name: str) -> None:
        if self.fail == name:
            raise sd_release.ReleaseError(f"{name} failed")
        self.acts.append(name)

    def last_tag(self):
        return "v0.17.2"

    def tip(self):
        return "abc123"

    def messages_since(self, tag, sha):
        return self.messages

    def frozen(self):
        return self.frozen_reason

    def ruling(self, tag, step, question):
        self.asked.append(step)
        return self.rulings.get(step)

    def push_tag(self, tag, sha):
        self._act(f"push_tag {tag} {sha}")

    def verify(self, command, tag, version, sha):
        self._act(f"verify {command} {version}")
        if not self.verified:
            raise sd_release.ReleaseError("rollout still on 0.17.2")


def run(world, acts=MANAGED, state=None, release=RELEASE):
    return sd_release.advance_release(dict(state or {"step": "version"}), release, acts, world)


class Version(unittest.TestCase):

    def test_the_next_version_comes_from_the_commit_types_since_the_last_tag(self):
        types = ["feat", "fix"]
        self.assertEqual(sd_release.next_tag("v0.17.2", ["fix: a", "doc: b"], types), "v0.17.3")
        self.assertEqual(sd_release.next_tag("v0.17.2", ["fix: a", "feat(x): b"], types), "v0.18.0")
        self.assertEqual(sd_release.next_tag("0.17.2", ["fix!: a"], types), "1.0.0")
        self.assertEqual(sd_release.next_tag("v1.2.3", ["fix: a\n\nBREAKING CHANGE: gone"], types), "v2.0.0")
        self.assertIsNone(sd_release.next_tag("v0.17.2", ["doc: a", "chore: b", "not conventional"], types))
        self.assertEqual(sd_release.next_tag(None, ["feat: first"], types), "v0.1.0")
        self.assertEqual(sd_release.next_tag("v1.0.0", ["perf: faster"], ["perf"]), "v1.0.1")


class Chain(unittest.TestCase):

    def test_a_managed_repository_tags_and_runs_its_verify(self):
        world = World()
        state = run(world)
        self.assertEqual((state["step"], state["tag"], state["reason"]), ("done", "v0.18.0", "released v0.18.0"))
        self.assertEqual(world.acts, ["push_tag v0.18.0 abc123", "verify check-rollout 0.18.0"])

    def test_a_tag_only_release_with_no_verify_ends_after_the_tag(self):
        world = World()
        state = run(world, release={})
        self.assertEqual((state["step"], world.acts), ("done", ["push_tag v0.18.0 abc123"]))

    def test_nothing_to_release_ends_the_chain_with_no_act(self):
        world = World(messages=["doc: words"])
        state = run(world)
        self.assertEqual((state["step"], world.acts), ("done", []))
        self.assertIn("no feat or fix commit", state["reason"])

    def test_release_stops_at_tag_push(self):
        world = World(fail="push_tag v0.18.0 abc123")
        state = run(world)
        self.assertEqual((state["step"], state["failed"], world.acts), ("tag", True, []))
        world.fail = None
        state = run(world, state=state)
        self.assertEqual(state["step"], "done")
        self.assertEqual(world.acts[0], "push_tag v0.18.0 abc123")

    def test_a_freeze_on_the_source_holds_the_tag(self):
        world = World(frozen="incident")
        state = run(world)
        self.assertEqual((state["step"], world.acts), ("tag", []))
        self.assertIn("freeze window holds the tag: incident", state["reason"])
        world.frozen_reason = None
        self.assertEqual(run(world, state=state)["step"], "done")

    def test_failed_verify_reports_and_rolls_nothing_back(self):
        world = World(verified=False)
        state = run(world)
        self.assertEqual((state["step"], state["failed"]), ("stopped", True))
        self.assertIn("v0.18.0 tagged; verify failed: rollout still on 0.17.2", state["reason"])
        self.assertIn("Nothing was rolled back", state["reason"])
        self.assertEqual(world.acts, ["push_tag v0.18.0 abc123", "verify check-rollout 0.18.0"])

    def test_a_tag_the_policy_holds_at_ask_waits_for_a_go_ruling(self):
        world = World()
        state = run(world, acts=ORG)
        self.assertEqual((state["step"], world.acts, world.asked), ("tag", [], ["tag"]))
        self.assertIn("waiting for the operator's ruling on: push the tag v0.18.0 on abc123?", state["reason"])
        world.rulings = {"tag": "Go."}
        state = run(world, acts=ORG, state=state)
        self.assertEqual((state["step"], world.acts[0]), ("done", "push_tag v0.18.0 abc123"))

    def test_any_other_ruling_stops_the_chain(self):
        world = World(rulings={"tag": "not now"})
        state = run(world, acts=ORG)
        self.assertEqual((state["step"], world.acts), ("stopped", []))
        self.assertIn("the operator stopped the chain at tag: not now", state["reason"])

    def test_verify_runs_on_the_tagged_commit_when_the_checkout_is_behind(self):
        """Review: verify ran in the main checkout, which the landing does not always move to origin's tip, so
        a stale checkout's tests passed a release, or new verify files were missing."""
        with tempfile.TemporaryDirectory() as scratch:
            tmp = pathlib.Path(scratch).resolve()

            def git(*argv):
                return subprocess.run(["git", *argv], cwd=main, env=clean_environment(**IDENTITY), check=True,
                                      capture_output=True, text=True).stdout.strip()
            main = tmp / "main"
            main.mkdir()
            git("init", "-q", "-b", "main")
            git("commit", "-q", "--allow-empty", "-m", "feat: old")
            old = git("rev-parse", "HEAD")
            (main / "check.sh").write_text("git rev-parse HEAD > \"$OUT\"\n", encoding="utf-8")
            git("add", "check.sh")
            git("commit", "-q", "-m", "feat: the verify script")
            tagged = git("rev-parse", "HEAD")
            git("switch", "-q", "--detach", old)  # the landing left the checkout behind the tagged commit
            out = tmp / "head"
            world = sd_release.Repositories(main, clean_environment(**IDENTITY, OUT=str(out)), lambda: None, lambda *args: None)
            world.verify('sh check.sh && test "$SD_RELEASE_TAG $SD_RELEASE_VERSION" = "v0.18.0 0.18.0"',
                         "v0.18.0", "0.18.0", tagged)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), tagged)
            with self.assertRaisesRegex(sd_release.ReleaseError, "exited 3"):
                world.verify("exit 3", "v0.18.0", "0.18.0", tagged)
            self.assertEqual((git("rev-parse", "HEAD"), len(git("worktree", "list").splitlines())), (old, 1),
                             "the checkout stays where it was and no worktree is left behind")


class Saved(unittest.TestCase):

    def test_each_step_is_saved_before_the_next_external_act(self):
        """Review: a kill after the tag push left the stored step at version, and the restart, finding the new
        tag as the last one, released nothing and never ran the verify."""
        world, saved = World(), []

        def killed(*args):
            raise KeyboardInterrupt
        world.verify = killed
        with self.assertRaises(KeyboardInterrupt):
            sd_release.advance_release({"step": "version"}, RELEASE, MANAGED, world,
                                       save=lambda state: saved.append(dict(state)))
        self.assertEqual([state["step"] for state in saved], ["tag", "verify"])
        self.assertEqual((saved[-1]["tag"], saved[-1]["sha"], saved[-1]["version"]), ("v0.18.0", "abc123", "0.18.0"))


class OnOrigin(unittest.TestCase):
    """Review: the chain read release history from local tags, which `git fetch --tags` does not prove are on
    origin. Each test puts a local ref at odds with origin's; the chain must read origin's."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        tmp = pathlib.Path(scratch.name).resolve()
        self.origin, self.main = tmp / "origin.git", tmp / "main"
        self.git(tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git(tmp, "clone", "-q", str(self.origin), str(self.main))
        self.first = self.commit("feat: one")
        self.git(self.main, "tag", "v0.1.0")
        self.git(self.main, "push", "-q", "origin", "HEAD:main", "refs/tags/v0.1.0")
        self.world = sd_release.Repositories(self.main, clean_environment(**IDENTITY), lambda: None,
                                             lambda *args: None)

    def git(self, cwd, *argv):
        return subprocess.run(["git", "-C", str(cwd), *argv], env=clean_environment(**IDENTITY), check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, message):
        self.git(self.main, "commit", "-q", "--allow-empty", "-m", message)
        return self.git(self.main, "rev-parse", "HEAD")

    def next(self):
        world = sd_release.Repositories(self.main, clean_environment(**IDENTITY), lambda: None, lambda *args: None)
        last = world.last_tag()
        return last, sd_release.next_tag(last, world.messages_since(last, world.tip()), ["feat", "fix"])

    def test_an_unpublished_local_tag_on_a_merged_commit_sets_no_version(self):
        self.commit("fix: two")
        self.git(self.main, "tag", "v9.0.0")  # never pushed
        self.git(self.main, "push", "-q", "origin", "HEAD:main")
        self.assertEqual(self.next(), ("v0.1.0", "v0.1.1"))

    def test_a_local_tag_moved_off_origins_commit_does_not_shorten_the_span(self):
        self.commit("fix: two")
        self.git(self.main, "tag", "-f", "v0.1.0")  # the local v0.1.0 now names the fix, origin's the feat
        self.git(self.main, "push", "-q", "origin", "HEAD:main")
        self.assertEqual(self.next(), ("v0.1.0", "v0.1.1"))

    def test_a_rerun_after_a_failed_push_computes_and_pushes_the_same_tag(self):
        sha = self.commit("feat: two")
        self.git(self.main, "push", "-q", "origin", "HEAD:main")
        self.git(self.main, "tag", "v0.2.0", sha)  # `push_tag` tagged here, then its push failed
        self.assertEqual(self.next(), ("v0.1.0", "v0.2.0"))
        self.world.push_tag("v0.2.0", sha)
        self.assertEqual(self.git(self.origin, "rev-parse", "refs/tags/v0.2.0^{commit}"), sha)

    def test_an_annotated_tag_origin_holds_on_the_commit_counts_as_pushed(self):
        sha = self.commit("feat: two")
        self.git(self.main, "tag", "-a", "-m", "release", "v0.2.0", sha)
        self.git(self.main, "push", "-q", "origin", "HEAD:main", "refs/tags/v0.2.0")
        self.world.push_tag("v0.2.0", sha)  # its ref names the tag object; its peeled line the commit
        self.assertEqual(self.next(), ("v0.2.0", None))
        with self.assertRaisesRegex(sd_release.ReleaseError, "origin already has v0.2.0 on"):
            self.world.push_tag("v0.2.0", self.first)

    def test_an_ambient_git_dir_the_given_environment_omits_never_reaches_git(self):
        """Lane review: `{**os.environ, **environ}` put back the GIT_DIR `clean_environment` dropped, so git ran
        in that repository, and a test's `push_tag` could tag and push the operator's real checkout."""
        decoy = self.main.parent / "decoy"
        self.git(self.main.parent, "init", "-q", "-b", "main", str(decoy))
        self.git(decoy, "commit", "-q", "--allow-empty", "-m", "decoy")
        sha = self.commit("feat: two")
        self.git(self.main, "push", "-q", "origin", "HEAD:main")
        with mock.patch.dict(os.environ, {"GIT_DIR": str(decoy / ".git")}):
            world = sd_release.Repositories(self.main, clean_environment(**IDENTITY), lambda: None,
                                            lambda *args: None)
            self.assertEqual(world.tip(), sha)
            world.push_tag("v0.2.0", sha)
        self.assertEqual(self.git(self.origin, "rev-parse", "refs/tags/v0.2.0^{commit}"), sha)
        self.assertEqual(self.git(decoy, "tag", "--list"), "", "the decoy repository is never tagged")

    def test_a_local_tag_on_another_commit_is_refused_not_published(self):
        sha = self.commit("feat: two")
        self.git(self.main, "push", "-q", "origin", "HEAD:main")
        self.git(self.main, "tag", "v0.2.0", self.first)
        with self.assertRaisesRegex(sd_release.ReleaseError, "the local tag v0.2.0 is on"):
            self.world.push_tag("v0.2.0", sha)
        self.assertEqual(self.git(self.origin, "tag", "--list", "v0.2.0"), "")


if __name__ == "__main__":
    unittest.main()
