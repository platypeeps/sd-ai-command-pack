"""The release chain after a merge: tag, deploy bump, its merge and verify (sd:6881, sd:7014).

docs/work/2026-11-01-release-bump-merge/design.md § Failure table names the test for each row.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import sd_lib  # noqa: E402
import sd_release  # noqa: E402
import sd_repo_policy  # noqa: E402
import sd_ship_jenkins  # noqa: E402

from tests.clean_env import clean_environment  # noqa: E402

RELEASE = {"deploy_repo": "~/repos/org/deploy", "file": "values.yaml", "key": "image.tag", "verify": "check-rollout"}
TAG_ONLY = {"verify": "check-rollout"}
VALUES = "image:\n  repository: org/app\n  tag: \"0.17.2\"  # set by the release\nreplicas: 2\n"
ORG = {"push": "ask", "pr": "ask"}
MANAGED = {"push": "auto", "pr": "auto"}
IDENTITY = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test"}
PR = "https://github.com/org/deploy/pull/7"


class Killed(BaseException):
    """A process killed between two steps: nothing after the raise runs, and no `except Exception` catches it."""


class World:
    """A fake of everything the chain touches; each act appends to `acts`, `fail` names the act that raises.

    `queued` makes a merge only join a merge queue; `merged_at` is the deploy commit GitHub reads MERGED at.
    """

    def __init__(self, *, messages=("feat: a thing",), values=VALUES, checks="green", verified=True,
                 frozen=None, fail=None, rulings=None, queued=False) -> None:
        self.messages, self.values, self.checks, self.verified = list(messages), values, checks, verified
        self.frozen_targets, self.fail, self.rulings, self.queued = frozen or {}, fail, rulings or {}, queued
        self.acts: list[str] = []
        self.asked: list[str] = []
        self.merged_at: str | None = None
        self.verified_at: tuple[str, bool] | None = None

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

    def frozen(self, deploy: bool):
        return self.frozen_targets.get("deploy" if deploy else "source")

    def ruling(self, tag, step, question):
        self.asked.append(step)
        return self.rulings.get(step)

    def push_tag(self, tag, sha):
        self._act(f"push_tag {tag} {sha}")

    def deployed(self):
        return self.values, "dep000"

    def open_bump(self, branch, text, message):
        self._act(f"open_bump {branch}")
        self.values_written, self.message = text, message
        return PR

    def merged(self, url):
        return self.merged_at

    def pr_state(self, url, policy):
        return self.checks

    def merge_bump(self, url):
        self._act(f"merge {url}")
        if not self.queued:
            self.merged_at = "def456"

    def verify(self, command, tag, version, sha, deploy=False):
        self._act(f"verify {command} {version}")
        self.verified_at = (sha, deploy)
        if not self.verified:
            raise sd_release.ReleaseError("rollout still on 0.17.2")


def run(world, acts=MANAGED, deploy_acts=MANAGED, state=None, release=RELEASE, save=lambda state: None):
    return sd_release.advance_release(dict(state or {"step": "version"}), release, acts, world, save=save,
                                      deploy_acts=deploy_acts)


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

    def test_a_dotted_key_is_rewritten_in_place_and_keeps_its_quotes_and_comment(self):
        old, text = sd_release.set_value(VALUES, "image.tag", "0.18.0")
        self.assertEqual(old, "0.17.2")
        self.assertEqual(text, VALUES.replace('"0.17.2"', '"0.18.0"'))
        self.assertEqual(sd_release.set_value(VALUES, "image.missing", "1")[0], None)
        self.assertEqual(sd_release.set_value("a:\n  b:\n    tag: 1\ntag: 2\n", "tag", "3")[1],
                         "a:\n  b:\n    tag: 1\ntag: 3\n")

    def test_a_key_that_holds_no_scalar_is_refused_and_the_file_kept(self):
        for text in ("image:\n  tag:\n    nested: old\n", "image:\n  tag:\n  - a\n",
                     "image:\n  tag:\n    - a\n", "image:\n  tag: |\n    old\n",
                     "image:\n  tag: >-\n    old\n", "image:\n  tag: {a: 1}\n",
                     "image:\n  tag: [a]\n", "image:\n  tag: &x old\n"):
            with self.subTest(text=text), self.assertRaisesRegex(sd_release.ReleaseError, "not a scalar"):
                sd_release.set_value(text, "image.tag", "1.0.1")
        self.assertEqual(sd_release.set_value("image:\n  tag: old\n  pull: x\n", "image.tag", "1")[1],
                         "image:\n  tag: 1\n  pull: x\n")

    def test_the_policy_reader_checks_the_release_keys(self):
        self.assertEqual(sd_lib.declaration_problems("policy", {"release": RELEASE}), [])
        self.assertEqual(sd_lib.declaration_problems("policy", {"release": {"tag": "v1"}}),
                         ["the policy declaration: release: unknown key(s) tag"])
        self.assertEqual(sd_lib.declaration_problems("policy", {"release": {"deploy_repo": "x"}}),
                         ["the policy declaration: release: deploy_repo, file and key are declared together"])


class Chain(unittest.TestCase):

    def test_a_managed_repository_runs_the_whole_chain(self):
        world = World()
        state = run(world)
        self.assertEqual((state["step"], state["tag"], state["reason"]), ("done", "v0.18.0", f"released v0.18.0: {PR}"))
        self.assertEqual(world.acts, ["push_tag v0.18.0 abc123", "open_bump release/v0.18.0",
                                      f"merge {PR}", "verify check-rollout 0.18.0"])
        self.assertIn('tag: "0.18.0"', world.values_written)
        self.assertEqual(world.verified_at, ("def456", True), "verify runs on the merged deploy commit")

    def test_a_tag_only_release_tags_and_runs_its_verify(self):
        world = World()
        state = run(world, release=TAG_ONLY)
        self.assertEqual((state["step"], state["tag"], state["reason"]), ("done", "v0.18.0", "released v0.18.0"))
        self.assertEqual(world.acts, ["push_tag v0.18.0 abc123", "verify check-rollout 0.18.0"])
        self.assertEqual(world.verified_at, ("abc123", False), "verify runs on the tagged source commit")

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

    def test_the_bump_follows_the_deploy_repositorys_commit_convention(self):
        """Review: a deploy policy requiring `Ref: LOG-N` refused the bump's message, so its hooks or CI held it."""
        convention = {"footer": r"^Ref: LOG-\d+$", "types": ["feat", "fix", "chore", "doc"], "aliases": {"docs": "doc"}}
        deploy = {**MANAGED, "commit_convention": convention}
        world = World(messages=["fix: a thing\n\nRef: LOG-12", "feat: b\n\nRef: LOG-12\nRef: LOG-13"])
        state = run(world, deploy_acts=deploy)
        self.assertFalse(state["failed"], state.get("reason"))
        self.assertEqual(sd_repo_policy.check_message(world.message, convention), world.message)
        self.assertTrue(world.message.endswith("\n\nRef: LOG-12\nRef: LOG-13\n"), world.message)
        bare = World(messages=["feat: no ticket"])
        state = run(bare, deploy_acts=deploy)
        self.assertEqual((state["step"], state["failed"]), ("bump", True))
        self.assertIn("no footer line matches ^Ref: LOG-\\d+$", state["reason"])
        self.assertEqual(bare.acts, ["push_tag v0.18.0 abc123"])

    def test_the_bump_keeps_the_deployed_values_v_prefix_and_form(self):
        """Review: a source tag `0.18.0` over a deployed `v0.17.2` wrote `0.18.0`, an image that does not exist."""
        for source, deployed, written in (("0.17.2", "v0.17.2", "v0.18.0"), ("v0.17.2", "v0.17.2", "v0.18.0"),
                                          ("v0.17.2", "0.17.2", "0.18.0"), ("0.17.2", "0.17.2", "0.18.0")):
            with self.subTest(source=source, deployed=deployed):
                world = World(values=VALUES.replace("0.17.2", deployed))
                world.last_tag = lambda source=source: source  # type: ignore[method-assign]
                state = run(world)
                self.assertEqual(state["version"], written)
                self.assertIn(f'tag: "{written}"', world.values_written)

    def test_release_skips_a_bump_already_deployed(self):
        world = World(values=VALUES.replace("0.17.2", "0.18.0"))
        state = run(world)
        self.assertEqual(state["step"], "done")
        self.assertIn("already deploys 0.18.0", state["reason"])
        self.assertEqual(world.acts, ["push_tag v0.18.0 abc123", "verify check-rollout 0.18.0"],
                         "review: a version already deployed is still verified")
        self.assertEqual(world.verified_at, ("dep000", True), "on the deploy commit that holds it")

    def test_freeze_window_stops_the_chain_before_merge(self):
        world = World(frozen={"deploy": "demo until 15:00"})
        state = run(world)
        self.assertEqual(state["step"], "merge")
        self.assertIn("demo until 15:00", state["reason"])
        self.assertNotIn(f"merge {PR}", world.acts)
        world.frozen_targets = {"source": "incident"}
        state = run(world, state=state)
        self.assertEqual(state["step"], "merge", "a freeze on the source holds the deploy merge too")
        world.frozen_targets = {}
        self.assertEqual(run(world, state=state)["step"], "done")

    def test_a_freeze_on_the_source_holds_the_tag(self):
        world = World(frozen={"source": "incident"})
        state = run(world)
        self.assertEqual((state["step"], world.acts), ("tag", []))
        self.assertIn("freeze window holds the tag: incident", state["reason"])
        world.frozen_targets = {}
        self.assertEqual(run(world, state=state)["step"], "done")

    def test_red_or_pending_checks_leave_the_pull_request_open(self):
        for checks in ("pending: 2 of 3 checks running", "red: build failed"):
            world = World(checks=checks)
            state = run(world)
            self.assertEqual(state["step"], "merge")
            self.assertIn(checks, state["reason"])
            self.assertEqual(state["failed"], checks.startswith("red"))

    def test_failed_verify_reports_and_rolls_nothing_back(self):
        for release, done in ((RELEASE, "merged as 0.18.0"), (TAG_ONLY, "tagged")):
            with self.subTest(done=done):
                world = World(verified=False)
                state = run(world, release=release)
                self.assertEqual((state["step"], state["failed"]), ("stopped", True))
                self.assertIn(f"v0.18.0 {done}; verify failed: rollout still on 0.17.2", state["reason"])
                self.assertIn("Nothing was rolled back", state["reason"])
                self.assertEqual(world.acts[-1], "verify check-rollout 0.18.0")

    def test_a_tag_the_policy_holds_at_ask_waits_for_a_go_ruling(self):
        world = World()
        state = run(world, acts=ORG, release=TAG_ONLY)
        self.assertEqual((state["step"], world.acts, world.asked), ("tag", [], ["tag"]))
        self.assertIn("waiting for the operator's ruling on: push the tag v0.18.0 on abc123?", state["reason"])
        world.rulings = {"tag": "Go."}
        state = run(world, acts=ORG, state=state, release=TAG_ONLY)
        self.assertEqual((state["step"], world.acts[0]), ("done", "push_tag v0.18.0 abc123"))

    def test_any_other_ruling_stops_the_chain(self):
        world = World(rulings={"tag": "not now"})
        state = run(world, acts=ORG)
        self.assertEqual((state["step"], world.acts), ("stopped", []))
        self.assertIn("the operator stopped the chain at tag: not now", state["reason"])

    def test_each_act_the_policy_holds_at_ask_waits_for_a_go_ruling(self):
        world = World()
        state = run(world, acts=ORG, deploy_acts=ORG)
        self.assertEqual((state["step"], world.acts, world.asked), ("tag", [], ["tag"]))
        self.assertIn("waiting", state["reason"])
        world.rulings = {"tag": "go", "bump": "go"}
        state = run(world, acts=ORG, deploy_acts=ORG, state=state)
        self.assertEqual(state["step"], "merge")
        self.assertEqual(world.acts, ["push_tag v0.18.0 abc123", "open_bump release/v0.18.0"])
        world.rulings["merge"] = "stop"
        state = run(world, acts=ORG, deploy_acts=ORG, state=state)
        self.assertEqual(state["step"], "stopped")
        self.assertIn("the operator stopped the chain at merge", state["reason"])

    def test_the_bump_asks_when_its_commit_or_push_is_held_at_ask(self):
        """Review: the bump checked only `pr`, though `open_bump` also commits and pushes a branch."""
        for held in ("commit", "push"):
            with self.subTest(held=held):
                world = World()
                state = run(world, deploy_acts={**MANAGED, "commit": "auto", held: "ask"})
                self.assertEqual((state["step"], world.asked), ("bump", ["bump"]))
                self.assertEqual(world.acts, ["push_tag v0.18.0 abc123"], "nothing is committed or pushed")

    def test_a_merge_that_only_queues_the_pull_request_stays_at_merge_until_merged(self):
        """Round 7: `gh pr merge` on a merge-queue branch only queues the PR, and the chain ran verify at once."""
        world = World(queued=True)
        state = run(world)
        self.assertEqual((state["step"], state["failed"]), ("merge", False))
        self.assertIn(f"{PR} is queued to merge", state["reason"])
        self.assertNotIn("verify check-rollout 0.18.0", world.acts, "no verify before GitHub reads MERGED")
        world.merged_at = "def456"  # the queue merged it
        state = run(world, state=state)
        self.assertEqual((state["step"], world.acts.count(f"merge {PR}")), ("done", 1))
        self.assertEqual(world.verified_at, ("def456", True))

    def test_a_kill_after_the_merge_before_its_save_resumes_at_verify(self):
        world, saved = World(), []

        def save(state):
            if state["step"] == "verify":
                raise Killed
            saved.append(dict(state))
        with self.assertRaises(Killed):
            run(world, save=save)
        self.assertEqual(saved[-1]["step"], "merge")
        state = run(world, state=saved[-1])
        self.assertEqual((state["step"], world.acts.count(f"merge {PR}")), ("done", 1), "the merge is not run again")
        self.assertEqual(world.verified_at, ("def456", True))


class Saved(unittest.TestCase):

    def test_each_step_is_saved_before_the_next_external_act(self):
        """Review: a kill after the tag push left the stored step at version, and the restart, finding the new
        tag as the last one, released nothing and never ran the verify, nor opened the bump."""
        for release, steps, act in ((TAG_ONLY, ["tag", "verify"], "verify"), (RELEASE, ["tag", "bump"], "open_bump")):
            with self.subTest(steps=steps):
                world, saved = World(), []

                def killed(*args, **kwargs):
                    raise Killed
                setattr(world, act, killed)
                with self.assertRaises(Killed):
                    run(world, release=release, save=lambda state, saved=saved: saved.append(dict(state)))
                self.assertEqual([state["step"] for state in saved], steps)
                self.assertEqual((saved[-1]["tag"], saved[-1]["sha"]), ("v0.18.0", "abc123"))

    def test_a_chain_tagged_before_the_policy_named_a_deploy_bumps_before_its_verify(self):
        """Older state: PR 1 stored a tag-only chain at verify; the policy then gained `deploy_repo`."""
        world = World()
        stored = {"step": "verify", "tag": "v0.18.0", "sha": "abc123", "last": "v0.17.2", "version": "0.18.0"}
        state = run(world, state=stored)
        self.assertEqual((state["step"], state["failed"]), ("done", False), state.get("reason"))
        self.assertEqual(world.acts, ["open_bump release/v0.18.0", f"merge {PR}", "verify check-rollout 0.18.0"])
        self.assertEqual(world.verified_at, ("def456", True))

    def test_a_deploy_step_whose_policy_dropped_the_deploy_fails_rather_than_acts(self):
        """Older state: a chain stored at bump or merge, then the policy dropped `deploy_repo`."""
        for step in ("bump", "merge"):
            with self.subTest(step=step):
                world = World()
                stored = {"step": step, "tag": "v0.18.0", "sha": "abc123", "last": "v0.17.2", "pr": PR}
                state = run(world, state=stored, release=TAG_ONLY)
                self.assertEqual((state["step"], state["failed"], world.acts), (step, True, []))
                self.assertIn("no longer declares deploy_repo", state["reason"])

    def test_a_deploy_step_with_no_deploy_policy_fails_rather_than_acts(self):
        world = World()
        state = sd_release.advance_release({"step": "version"}, RELEASE, MANAGED, world)
        self.assertEqual((state["step"], state["failed"]), ("bump", True))
        self.assertIn("the deploy repository's policy was not read", state["reason"])
        self.assertEqual(world.acts, ["push_tag v0.18.0 abc123"])


def git(cwd, *argv):
    return subprocess.run(["git", "-C", str(cwd), *argv], env=clean_environment(**IDENTITY), check=True,
                          capture_output=True, text=True).stdout.strip()


class OnOrigin(unittest.TestCase):
    """Review: the chain read release history from local tags, which `git fetch --tags` does not prove are on
    origin. Each test puts a local ref at odds with origin's; the chain must read origin's."""

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        tmp = pathlib.Path(scratch.name).resolve()
        self.origin, self.main = tmp / "origin.git", tmp / "main"
        git(tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp, "clone", "-q", str(self.origin), str(self.main))
        self.first = self.commit("feat: one")
        git(self.main, "tag", "v0.1.0")
        git(self.main, "push", "-q", "origin", "HEAD:main", "refs/tags/v0.1.0")
        self.world = self.repositories()

    def repositories(self, **environ):
        return sd_release.Repositories(self.main, clean_environment(**IDENTITY, **environ), lambda deploy: None,
                                       lambda *args: None)

    def commit(self, message):
        git(self.main, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.main, "rev-parse", "HEAD")

    def next(self):
        world = self.repositories()
        last = world.last_tag()
        return last, sd_release.next_tag(last, world.messages_since(last, world.tip()), ["feat", "fix"])

    def test_an_unpublished_local_tag_on_a_merged_commit_sets_no_version(self):
        self.commit("fix: two")
        git(self.main, "tag", "v9.0.0")  # never pushed
        git(self.main, "push", "-q", "origin", "HEAD:main")
        self.assertEqual(self.next(), ("v0.1.0", "v0.1.1"))

    def test_a_local_tag_moved_off_origins_commit_does_not_shorten_the_span(self):
        self.commit("fix: two")
        git(self.main, "tag", "-f", "v0.1.0")  # the local v0.1.0 now names the fix, origin's the feat
        git(self.main, "push", "-q", "origin", "HEAD:main")
        self.assertEqual(self.next(), ("v0.1.0", "v0.1.1"))

    def test_a_rerun_after_a_failed_push_computes_and_pushes_the_same_tag(self):
        sha = self.commit("feat: two")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        git(self.main, "tag", "v0.2.0", sha)  # `push_tag` tagged here, then its push failed
        self.assertEqual(self.next(), ("v0.1.0", "v0.2.0"))
        self.world.push_tag("v0.2.0", sha)
        self.assertEqual(git(self.origin, "rev-parse", "refs/tags/v0.2.0^{commit}"), sha)

    def test_an_annotated_tag_origin_holds_on_the_commit_counts_as_pushed(self):
        sha = self.commit("feat: two")
        git(self.main, "tag", "-a", "-m", "release", "v0.2.0", sha)
        git(self.main, "push", "-q", "origin", "HEAD:main", "refs/tags/v0.2.0")
        self.world.push_tag("v0.2.0", sha)  # its ref names the tag object; its peeled line the commit
        self.assertEqual(self.next(), ("v0.2.0", None))
        with self.assertRaisesRegex(sd_release.ReleaseError, "origin already has v0.2.0 on"):
            self.world.push_tag("v0.2.0", self.first)

    def test_a_resumed_run_reads_origins_tags_before_the_messages_since_one(self):
        """A run that resumes past `version` never called `last_tag`, so `messages_since` knew no tag of origin's
        and refused the bump's footer read."""
        self.commit("fix: two")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        world = self.repositories()
        self.assertEqual(world.messages_since("v0.1.0", world.tip()), ["fix: two"])

    def test_an_ambient_git_dir_the_given_environment_omits_never_reaches_git(self):
        """Lane review: `{**os.environ, **environ}` put back the GIT_DIR `clean_environment` dropped, so git ran
        in that repository, and a test's `push_tag` could tag and push the operator's real checkout."""
        decoy = self.main.parent / "decoy"
        git(self.main.parent, "init", "-q", "-b", "main", str(decoy))
        git(decoy, "commit", "-q", "--allow-empty", "-m", "decoy")
        sha = self.commit("feat: two")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        with mock.patch.dict(os.environ, {"GIT_DIR": str(decoy / ".git")}):
            world = self.repositories()
            self.assertEqual(world.tip(), sha)
            world.push_tag("v0.2.0", sha)
        self.assertEqual(git(self.origin, "rev-parse", "refs/tags/v0.2.0^{commit}"), sha)
        self.assertEqual(git(decoy, "tag", "--list"), "", "the decoy repository is never tagged")

    def test_the_tip_is_origins_advertised_default_branch_not_a_stale_origin_head(self):
        """Re-review: `git fetch` does not move the local `origin/HEAD`, so after origin's default moved from
        master to main, keeping master, the chain released master's tip."""
        git(self.main, "push", "-q", "origin", "HEAD:master")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/master")
        git(self.main, "remote", "set-head", "origin", "master")  # what a clone made before the move
        sha = self.commit("feat: two")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")
        self.assertEqual(self.world.tip(), sha)
        self.assertEqual(self.next(), ("v0.1.0", "v0.2.0"))

    def test_an_origin_that_advertises_no_default_branch_is_unknown(self):
        git(self.main, "remote", "set-head", "origin", "main")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/gone")
        with self.assertRaisesRegex(sd_release.ReleaseError, "origin advertises no default branch"):
            self.world.tip()

    def test_a_local_tag_on_another_commit_is_refused_not_published(self):
        sha = self.commit("feat: two")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        git(self.main, "tag", "v0.2.0", self.first)
        with self.assertRaisesRegex(sd_release.ReleaseError, "the local tag v0.2.0 is on"):
            self.world.push_tag("v0.2.0", sha)
        self.assertEqual(git(self.origin, "tag", "--list", "v0.2.0"), "")

    def test_verify_runs_on_the_tagged_commit_when_the_checkout_is_behind(self):
        """Review: verify ran in the main checkout, which the landing does not always move to origin's tip, so
        a stale checkout's tests passed a release, or new verify files were missing."""
        (self.main / "check.sh").write_text("git rev-parse HEAD > \"$OUT\"\n", encoding="utf-8")
        git(self.main, "add", "check.sh")
        git(self.main, "commit", "-q", "-m", "feat: the verify script")
        tagged = git(self.main, "rev-parse", "HEAD")
        git(self.main, "switch", "-q", "--detach", self.first)  # the landing left the checkout behind the tag
        out = self.main.parent / "head"
        world = self.repositories(OUT=str(out))
        world.verify('sh check.sh && test "$SD_RELEASE_TAG $SD_RELEASE_VERSION" = "v0.18.0 0.18.0"',
                     "v0.18.0", "0.18.0", tagged)
        self.assertEqual(out.read_text(encoding="utf-8").strip(), tagged)
        with self.assertRaisesRegex(sd_release.ReleaseError, "exited 3"):
            world.verify("exit 3", "v0.18.0", "0.18.0", tagged)
        self.assertEqual((git(self.main, "rev-parse", "HEAD"), len(git(self.main, "worktree", "list").splitlines())),
                         (self.first, 1), "the checkout stays where it was and no worktree is left behind")


HEAD = "4" * 40
URL = "https://github.com/org/deploy/pull/8"


class Gh(sd_release.Repositories):
    """The real git, with `gh` answered from `answers` by its verb; an Exception answer raises."""

    def __init__(self, deploy: pathlib.Path, answers: dict, main: pathlib.Path | None = None) -> None:
        super().__init__(main or deploy.parent / "app", clean_environment(**IDENTITY), lambda deploy: None,
                         lambda *args: None, deploy=deploy, file="values.yaml")
        self.answers, self.gh = answers, []

    def _run(self, *argv, **options):
        if argv[0] != "gh":
            return super()._run(*argv, **options)
        self.gh.append(argv)
        return self.answer(argv)

    def answer(self, argv):
        answer = self.answers[argv[1] if argv[1] == "api" else argv[2]].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class OnDisk(unittest.TestCase):

    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.tmp = pathlib.Path(scratch.name).resolve()
        self.origin = self.tmp / "deploy.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.deploy = self.tmp / "deploy"
        git(self.tmp, "clone", "-q", str(self.origin), str(self.deploy))
        (self.deploy / "values.yaml").write_text(VALUES, encoding="utf-8")
        git(self.deploy, "add", "values.yaml")
        git(self.deploy, "commit", "-q", "-m", "values")
        git(self.deploy, "push", "-q", "origin", "HEAD:main")

    def branch_tip(self):
        return subprocess.run(["git", "-C", str(self.origin), "rev-parse", "-q", "--verify",
                               "refs/heads/release/app-v0.18.0"], capture_output=True, text=True, check=False,
                              env=clean_environment()).stdout.strip()

    def test_a_failed_push_leaves_nothing_on_origin_and_a_rerun_pushes(self):
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho refused by the test >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        world = Gh(self.deploy, {"list": ["[]", "[]"], "create": [URL]})
        text, message = VALUES.replace("0.17.2", "0.18.0"), "chore: release 0.18.0\n\nSet image.tag.\n"
        with self.assertRaisesRegex(sd_release.ReleaseError, "git push -q exited"):
            world.open_bump("release/v0.18.0", text, message)
        self.assertEqual(self.branch_tip(), "", "nothing on origin")
        self.assertEqual(len(git(self.deploy, "worktree", "list").splitlines()), 1, "no worktree left behind")
        self.assertNotIn("create", [argv[2] for argv in world.gh])
        hook.unlink()
        self.assertEqual(world.open_bump("release/v0.18.0", text, message), URL)
        self.assertEqual(git(self.origin, "show", "refs/heads/release/app-v0.18.0:values.yaml"), text.rstrip("\n"))

    def test_a_branch_pushed_before_a_failed_pr_create_is_reused(self):
        """Review: the retry made a new commit from main and its push was rejected as non-fast-forward."""
        world = Gh(self.deploy, {"list": ["[]", "[]"], "create": [sd_release.ReleaseError("gh: HTTP 502"), URL]})
        text, message = VALUES.replace("0.17.2", "0.18.0"), "chore: release 0.18.0\n\nSet image.tag.\n"
        with self.assertRaises(sd_release.ReleaseError):
            world.open_bump("release/v0.18.0", text, message)
        pushed = self.branch_tip()
        world.env.update(GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
        self.assertEqual(world.open_bump("release/v0.18.0", text, message), URL)
        self.assertEqual(self.branch_tip(), pushed)

    def test_a_pushed_branch_with_other_content_is_not_reused(self):
        world = Gh(self.deploy, {"list": ["[]", "[]"], "create": [sd_release.ReleaseError("gh: HTTP 502")]})
        with self.assertRaises(sd_release.ReleaseError):
            world.open_bump("release/v0.18.0", VALUES.replace("0.17.2", "0.18.0"), "chore: release\n\nb\n")
        with self.assertRaisesRegex(sd_release.ReleaseError, "holds another values.yaml"):
            world.open_bump("release/v0.18.0", VALUES.replace("0.17.2", "0.19.0"), "chore: release\n\nb\n")

    def test_a_kill_after_the_pr_is_opened_finds_it_by_its_head_branch(self):
        state = {"step": "bump", "tag": "v0.18.0", "sha": "abc123", "last": "v0.17.2"}
        first = Gh(self.deploy, {"list": ["[]"], "create": [URL]})

        def save(saved):
            if saved["step"] == "merge":
                raise Killed  # after `gh pr create`, before the step that holds its URL is stored
        with self.assertRaises(Killed):
            sd_release.advance_release(dict(state), RELEASE, MANAGED, first, save=save, deploy_acts=MANAGED)
        pushed = self.branch_tip()
        listed = json.dumps([{"url": URL}])
        pending = json.dumps({"state": "OPEN", "number": 8, "headRefOid": pushed, "statusCheckRollup": []})
        rerun = Gh(self.deploy, {"list": [listed], "view": [pending, pending]})
        state = sd_release.advance_release(dict(state), RELEASE, MANAGED, rerun, deploy_acts=MANAGED)
        self.assertEqual((state["step"], state["pr"]), ("merge", URL), state.get("reason"))
        self.assertEqual(rerun.gh[0][:5], ("gh", "pr", "list", "--head", "release/app-v0.18.0"))
        self.assertNotIn("create", [argv[2] for argv in rerun.gh], "no second PR is opened")
        self.assertEqual(self.branch_tip(), pushed, "and no second push")

    def test_an_open_pr_on_the_branch_with_other_content_is_not_reused(self):
        """Evidence: the PR a rerun finds by its branch name must hold this bump, not another one."""
        world = Gh(self.deploy, {"list": ["[]"], "create": [URL]})
        world.open_bump("release/v0.18.0", VALUES.replace("0.17.2", "0.18.0"), "chore: release\n\nb\n")
        rerun = Gh(self.deploy, {"list": [json.dumps([{"url": URL}])]})
        with self.assertRaisesRegex(sd_release.ReleaseError, "holds another values.yaml"):
            rerun.open_bump("release/v0.18.0", VALUES.replace("0.17.2", "0.19.0"), "chore: release\n\nb\n")

    def test_file_reads_keep_leading_and_trailing_whitespace(self):
        """Review: `_run` stripped `git show` output, so a bump dropped a first-line indent and a `|+` block's
        kept newlines, and a re-pushed branch with the same file compared unequal."""
        kept = "  image:\n    tag: \"0.17.2\"\nnotes: |+\n  kept\n\n\n"
        (self.deploy / "values.yaml").write_text(kept, encoding="utf-8")
        git(self.deploy, "commit", "-q", "-am", "whitespace")
        git(self.deploy, "push", "-q", "origin", "HEAD:main")
        world = Gh(self.deploy, {"list": ["[]", "[]"], "create": [sd_release.ReleaseError("gh: HTTP 502"), URL]})
        self.assertEqual(world.deployed(), (kept, git(self.deploy, "rev-parse", "HEAD")))
        text = kept.replace("0.17.2", "0.18.0")
        with self.assertRaises(sd_release.ReleaseError):
            world.open_bump("release/v0.18.0", text, "chore: release 0.18.0\n\nb\n")
        self.assertEqual(world.open_bump("release/v0.18.0", text, "chore: release 0.18.0\n\nb\n"), URL)

    def test_verify_runs_in_a_detached_deploy_worktree_at_the_merged_commit(self):
        """The deploy checkout never fetched the merge, so a verify there read the old values."""
        upstream = self.tmp / "upstream"
        git(self.tmp, "clone", "-q", str(self.origin), str(upstream))
        (upstream / "values.yaml").write_text(VALUES.replace("0.17.2", "0.18.0"), encoding="utf-8")
        git(upstream, "commit", "-q", "-am", "chore: release 0.18.0")
        git(upstream, "push", "-q", "origin", "HEAD:main")
        merged, behind = git(upstream, "rev-parse", "HEAD"), git(self.deploy, "rev-parse", "HEAD")
        out = self.tmp / "verified"
        world = Gh(self.deploy, {})
        world.env["OUT"] = str(out)
        world.verify('grep -q "$SD_RELEASE_VERSION" values.yaml && git rev-parse HEAD > "$OUT"', "v0.18.0", "0.18.0",
                     merged, deploy=True)
        self.assertEqual(out.read_text(encoding="utf-8").strip(), merged)
        self.assertEqual((git(self.deploy, "rev-parse", "HEAD"), len(git(self.deploy, "worktree", "list").splitlines())),
                         (behind, 1), "the deploy checkout stays where it was and no worktree is left behind")
        with self.assertRaisesRegex(sd_release.ReleaseError, "is not on origin's default branch"):
            world.verify("true", "v0.18.0", "0.18.0", "5" * 40, deploy=True)

    def view(self):
        return json.dumps({"state": "OPEN", "number": 8, "headRefOid": HEAD,
                           "statusCheckRollup": [{"name": "lint", "conclusion": "SUCCESS"}]})

    def test_the_deploy_policy_gates_the_merge_as_sd_ship_does(self):
        """Review: one green GitHub check merged the deploy PR while the policy's approval or Jenkins build was
        missing; and the merge is bound to the head the gates read."""
        approved = json.dumps({"user": {"login": "pat", "type": "User"}, "state": "APPROVED", "commit_id": HEAD})
        world = Gh(self.deploy, {"view": [self.view()] * 4, "api": ["", approved], "merge": [""]})
        policy = {"review": {"human": 1}}
        self.assertEqual(world.pr_state(URL, policy),
                         f"pending: the deploy policy requires 1 human approval of {HEAD[:12]}; 0 approve it")
        self.assertEqual(world.pr_state(URL, policy), "green")
        world.merge_bump(URL)
        self.assertEqual(world.gh[-1], ("gh", "pr", "merge", URL, "--squash", "--match-head-commit", HEAD))
        ci = {"provider": "jenkins", "url": "https://jenkins.example", "job": "deploy/PR-{pr}"}
        red = {"result": "FAILURE", "building": False, "url": "https://jenkins.example/job/deploy/1"}
        with mock.patch.object(sd_ship_jenkins, "head_build", return_value=red):
            self.assertEqual(world.pr_state(URL, {"ci": ci}),
                             f"red: Jenkins build https://jenkins.example/job/deploy/1 of {HEAD[:12]} is FAILURE")
        with mock.patch.object(sd_ship_jenkins, "head_build", side_effect=sd_ship_jenkins.jenkins_unreachable(ci, "x")):
            self.assertTrue(world.pr_state(URL, {"ci": ci}).startswith("pending: Jenkins at https://jenkins.example"))

    def test_a_jenkins_only_deploy_repo_merges_on_its_green_build_with_no_github_check(self):
        """Review: an empty statusCheckRollup returned pending before the Jenkins gate ran, so it never merged."""
        bare = json.dumps({"state": "OPEN", "number": 8, "headRefOid": HEAD, "statusCheckRollup": []})
        world = Gh(self.deploy, {"view": [bare] * 3})
        ci = {"provider": "jenkins", "url": "https://jenkins.example", "job": "deploy/PR-{pr}"}
        green = {"result": "SUCCESS", "building": False, "url": "https://jenkins.example/job/deploy/2"}
        with mock.patch.object(sd_ship_jenkins, "head_build", return_value=green) as read:
            self.assertEqual(world.pr_state(URL, {"ci": ci}), "green")
        read.assert_called()
        red = {**green, "result": "FAILURE"}
        with mock.patch.object(sd_ship_jenkins, "head_build", return_value=red):
            self.assertTrue(world.pr_state(URL, {"ci": ci}).startswith("red: Jenkins build"))
        self.assertEqual(world.pr_state(URL, {}), "pending: no check has reported yet")

    def test_a_merge_queue_add_reads_as_not_merged(self):
        """`gh pr merge` exits 0 when it only queues the PR; merged is what `gh pr view` reads."""
        queued = json.dumps({"state": "OPEN", "mergeCommit": None})
        done = json.dumps({"state": "MERGED", "mergeCommit": {"oid": HEAD}})
        world = Gh(self.deploy, {"view": [queued, done, json.dumps({"state": "MERGED", "mergeCommit": None})]})
        self.assertIsNone(world.merged(URL))
        self.assertEqual(world.merged(URL), HEAD)
        with self.assertRaisesRegex(sd_release.ReleaseError, "MERGED with no merge commit"):
            world.merged(URL)


class GitHubOnDisk(Gh):
    """`gh` as GitHub would answer it for one deploy PR, its merge a real squash on the bare deploy origin."""

    def __init__(self, deploy, main, github: dict) -> None:
        super().__init__(deploy, {}, main=main)
        self.github = github  # shared across a kill and its rerun, as GitHub is

    def answer(self, argv):
        pr, verb = self.github, argv[2]
        if verb == "list":
            return json.dumps([{"url": URL}] if pr.get("head") else [])
        if verb == "create":
            pr["head"] = argv[argv.index("--head") + 1]
            return URL
        tip = git(pr["origin"], "rev-parse", f"refs/heads/{pr['head']}")
        if verb == "view" and argv[-1] == "state,mergeCommit":
            return json.dumps({"state": "MERGED" if pr.get("merged") else "OPEN",
                               "mergeCommit": {"oid": pr["merged"]} if pr.get("merged") else None})
        if verb == "view":
            return json.dumps({"state": "OPEN", "number": 8, "headRefOid": tip,
                               "statusCheckRollup": [{"name": "lint", "conclusion": "SUCCESS"}]})
        if verb == "merge":
            if argv[argv.index("--match-head-commit") + 1] != tip:
                raise sd_release.ReleaseError("gh pr merge exited 1: the head moved")
            message = git(pr["origin"], "log", "-1", "--format=%B", tip)
            squashed = git(pr["origin"], "commit-tree", f"{tip}^{{tree}}", "-p", "main", "-m", message)
            git(pr["origin"], "update-ref", "refs/heads/main", squashed)  # a squash: a commit no checkout holds
            pr["merged"] = squashed
            return ""
        raise AssertionError(f"unexpected gh call {argv}")


class EndToEnd(unittest.TestCase):

    def test_a_deploy_release_runs_version_through_verify_against_bare_origins(self):
        """Acceptance: version, tag, bump, merge and verify over real source and deploy origins, with a kill
        after the PR opens and a fresh process resuming it; only `gh` is a fake."""
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        tmp = pathlib.Path(scratch.name).resolve()
        for name in ("app", "deploy"):
            git(tmp, "init", "-q", "--bare", "-b", "main", str(tmp / f"{name}.git"))
            git(tmp, "clone", "-q", str(tmp / f"{name}.git"), str(tmp / name))
        app, deploy = tmp / "app", tmp / "deploy"
        git(app, "commit", "-q", "--allow-empty", "-m", "feat: first")
        git(app, "tag", "v0.17.2")
        git(app, "commit", "-q", "--allow-empty", "-m", "feat: the thing\n\nRef: LOG-7")
        git(app, "push", "-q", "origin", "HEAD:main", "refs/tags/v0.17.2")
        tip = git(app, "rev-parse", "HEAD")
        (deploy / "values.yaml").write_text(VALUES.replace("0.17.2", "v0.17.2"), encoding="utf-8")
        (deploy / "check.sh").write_text('grep -q "tag: \\"$SD_RELEASE_VERSION\\"" values.yaml\n'
                                         'git rev-parse HEAD > "$OUT"\n', encoding="utf-8")
        git(deploy, "add", "values.yaml", "check.sh")
        git(deploy, "commit", "-q", "-m", "values")
        git(deploy, "push", "-q", "origin", "HEAD:main")
        before = git(deploy, "rev-parse", "HEAD")
        release = {"deploy_repo": str(deploy), "file": "values.yaml", "key": "image.tag", "verify": "sh check.sh"}
        deploy_acts = {**MANAGED, "commit_convention": {"footer": r"^Ref: LOG-\d+$"}}
        github, saved, killed, out = {"origin": tmp / "deploy.git"}, [], [], tmp / "verified"

        def world():
            made = GitHubOnDisk(deploy, app, github)
            made.env["OUT"] = str(out)
            return made

        def save(state):
            if state["step"] == "merge" and not killed:
                killed.append(state["pr"])
                raise Killed  # after `gh pr create`, before its URL is stored
            saved.append(dict(state))
        with self.assertRaises(Killed):
            sd_release.advance_release({"step": "version"}, release, MANAGED, world(), save=save,
                                       deploy_acts=deploy_acts)
        self.assertEqual((saved[-1]["step"], saved[-1]["tag"]), ("bump", "v0.18.0"))
        state = sd_release.advance_release(dict(saved[-1]), release, MANAGED, world(), save=save,
                                           deploy_acts=deploy_acts)
        self.assertEqual((state["step"], state["failed"], state["reason"]), ("done", False, f"released v0.18.0: {URL}"))
        self.assertEqual(git(tmp / "app.git", "rev-parse", "refs/tags/v0.18.0^{commit}"), tip)
        merged = git(tmp / "deploy.git", "rev-parse", "refs/heads/main")
        self.assertEqual((git(tmp / "deploy.git", "rev-parse", "main^"), github["merged"]), (before, merged))
        self.assertIn('tag: "v0.18.0"', git(tmp / "deploy.git", "show", "main:values.yaml"))
        self.assertEqual(git(tmp / "deploy.git", "log", "-1", "--format=%B", "main"),
                         "chore: release v0.18.0\n\nSet image.tag in values.yaml to v0.18.0.\n\nRef: LOG-7")
        self.assertEqual(out.read_text(encoding="utf-8").strip(), merged, "verify ran on the merged commit")
        self.assertEqual((git(deploy, "rev-parse", "HEAD"), len(git(deploy, "worktree", "list").splitlines())),
                         (before, 1), "the deploy checkout stays put and keeps no worktree")


if __name__ == "__main__":
    unittest.main()
