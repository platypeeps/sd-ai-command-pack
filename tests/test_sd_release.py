"""The release chain after a merge: its tag and verify (sd:6881, docs/work/2026-10-29-repo-policy/design.md)."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import sd_release  # noqa: E402

from tests.clean_env import clean_environment  # noqa: E402

RELEASE = {"verify": "check-rollout"}
ORG = {"push": "ask", "pr": "ask"}
MANAGED = {"push": "auto", "pr": "auto"}


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

    def verify(self, command, tag, version):
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

    def test_a_tag_only_verify_runs_in_the_source_checkout(self):
        with tempfile.TemporaryDirectory() as scratch:
            main = pathlib.Path(scratch).resolve()
            world = sd_release.Repositories(main, clean_environment(), lambda: None, lambda *args: None)
            world.verify('pwd > where; echo "$SD_RELEASE_TAG $SD_RELEASE_VERSION" >> where', "v0.18.0", "0.18.0")
            self.assertEqual((main / "where").read_text().split(), [str(main), "v0.18.0", "0.18.0"])
            with self.assertRaisesRegex(sd_release.ReleaseError, "exited 3"):
                world.verify("exit 3", "v0.18.0", "0.18.0")


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


if __name__ == "__main__":
    unittest.main()
