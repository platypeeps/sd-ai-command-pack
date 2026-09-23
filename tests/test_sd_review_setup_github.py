"""Fixtures for `bin/sd_setup_github.py`: the opt-in CI lane and its refusals.

Every test here writes into a throwaway git repository. None installs a workflow
into this checkout, and none reaches a network -- the installer writes one file
and reads three, which is the whole of its surface.

The installer is a module rather than more of `bin/sd-review` for two reasons
that point the same way: it writes, and the review lane's proof that it never
writes is a structural read of that one file.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_REVIEW = REPO_ROOT / "bin" / "sd-review"
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_setup_github as setup  # noqa: E402
import sd_setup_guard as guard  # noqa: E402


def load_review() -> Any:
    """Import `bin/sd-review`, which ships without a `.py` suffix."""

    loader = importlib.machinery.SourceFileLoader("sd_review_setup_under_test", str(SD_REVIEW))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


sd_review = load_review()


def install(root: pathlib.Path, **overrides: Any) -> dict:
    """Run the installer with the real seam `bin/sd-review` hands it."""

    return setup.setup_github(
        root,
        setup_args(**overrides),
        load_policy=sd_review.load_policy,
    )

PIN = "0" * 40


def setup_args(**overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "dry_run": False,
        "json": False,
        "force": False,
        "remove_legacy": False,
        "pin": PIN,
        "check": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class SetupFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()

    def make_repo(self, name: str = "repo") -> pathlib.Path:
        root = self.tmp / name
        root.mkdir(parents=True)
        for args in (
            ["init", "--quiet", "--initial-branch", "main"],
            ["config", "user.email", "fixture@example.invalid"],
            ["config", "user.name", "Fixture"],
        ):
            subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)
        (root / "README.md").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "seed"], cwd=str(root), check=True, capture_output=True
        )
        return root

    def set_mode(self, root: pathlib.Path, value: str) -> None:
        (root / sd_lib_local_name()).write_text(
            f"{setup.sd_lib.LOCAL_BLOCK_START}\nmode: {value}\n"
            f"{setup.sd_lib.LOCAL_BLOCK_END}\n",
            encoding="utf-8",
        )

    def workflow(self, root: pathlib.Path) -> pathlib.Path:
        return root / setup.WORKFLOW_RELATIVE_PATH

    def dependabot(self, root: pathlib.Path) -> pathlib.Path:
        return root / guard.DEPENDABOT_RELATIVE_PATH

    def seed_dependabot(self, root: pathlib.Path, text: str) -> pathlib.Path:
        path = self.dependabot(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


def sd_lib_local_name() -> str:
    return setup.sd_lib.LOCAL_FILE_NAME


class ModeTests(SetupFixture):
    def test_full_mode_installs_the_workflow(self) -> None:
        root = self.make_repo()
        result = install(root)
        self.assertEqual(result["status"], "installed")
        self.assertTrue(self.workflow(root).is_file())

    def test_minimal_mode_refuses(self) -> None:
        root = self.make_repo()
        self.set_mode(root, "minimal")
        with self.assertRaises(setup.Refusal) as caught:
            install(root)
        self.assertIn("minimal mode", str(caught.exception))
        self.assertFalse(self.workflow(root).exists())

    def test_guest_mode_refuses(self) -> None:
        root = self.make_repo()
        self.set_mode(root, "guest")
        with self.assertRaises(setup.Refusal) as caught:
            install(root)
        self.assertIn("guest mode", str(caught.exception))
        self.assertFalse(self.workflow(root).exists())


class LegacyTests(SetupFixture):
    def seed_legacy(self, root: pathlib.Path, rel: str) -> pathlib.Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("legacy\n", encoding="utf-8")
        return path

    def test_every_legacy_path_blocks_the_install(self) -> None:
        for rel in setup.LEGACY_ROUTER_PATHS:
            with self.subTest(rel=rel):
                root = self.make_repo(f"repo-{rel.replace('/', '-')}")
                self.seed_legacy(root, rel)
                with self.assertRaises(setup.Refusal) as caught:
                    install(root)
                self.assertIn(rel, str(caught.exception))
                self.assertFalse(self.workflow(root).exists())

    def test_remove_legacy_deletes_it_and_installs(self) -> None:
        root = self.make_repo()
        paths = [self.seed_legacy(root, rel) for rel in setup.LEGACY_ROUTER_PATHS]
        result = install(root, remove_legacy=True)
        self.assertEqual(result["legacy_removed"], list(setup.LEGACY_ROUTER_PATHS))
        self.assertEqual([path.exists() for path in paths], [False, False, False])
        self.assertTrue(self.workflow(root).is_file())

    def test_dry_run_leaves_legacy_in_place(self) -> None:
        root = self.make_repo()
        path = self.seed_legacy(root, setup.LEGACY_ROUTER_PATHS[0])
        result = install(root, remove_legacy=True, dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["legacy_removed"], [])
        self.assertTrue(path.is_file())
        self.assertFalse(self.workflow(root).exists())


class WorkflowContentTests(SetupFixture):
    def test_a_foreign_repository_gets_the_pinned_remote_action(self) -> None:
        root = self.make_repo()
        install(root)
        text = self.workflow(root).read_text(encoding="utf-8")
        self.assertIn(f"uses: {setup.ACTION_REPOSITORY}/{setup.ACTION_SUBPATH}@{PIN}", text)

    def test_the_pack_itself_gets_the_self_repository_reference(self) -> None:
        # The bootstrap the digest cannot close: the pull request installing the
        # lane in the pack would pin a commit that only exists once it merges.
        # `$/` closes it without a digest -- GitHub resolves it to this
        # repository at the commit the workflow is running.
        self.assertEqual(setup.action_reference(None), f"$/{setup.ACTION_SUBPATH}")
        # And specifically not `./`, which resolves against the runner's
        # workspace -- which the checkout step fills with the pull request's
        # head, so the pull request would supply the action that routes it.
        # That is zizmor's `self-repository` audit, and it is the whole reason
        # the pack's own arm of this function is not a path (item 839).
        self.assertNotIn("./", setup.action_reference(None))

    def test_the_packs_own_workflow_is_what_this_build_writes(self) -> None:
        # The pack's `.github/workflows/sd-review-route.yml` is not a
        # hand-maintained file that happens to resemble the template: it is
        # the template's self-install output, tracked. Nothing compared the
        # two, so an edit to either drifted in silence -- and `setup-github`
        # re-run in the pack would then refuse over a file it wrote itself.
        # Found while fixing the `./` reference (item 839), where the fix had
        # to land in both places or in neither.
        tracked = (REPO_ROOT / setup.WORKFLOW_RELATIVE_PATH).read_text(encoding="utf-8")
        self.assertEqual(tracked, setup.workflow_text(setup.action_reference(None)))
        # The self-install writes one file, not two. Its workflow names no pin
        # (`action_reference(None)`), so there is nothing for Dependabot to
        # bump and no guard to hold it: the pack's own `dependabot.yml` carries
        # none, and `--check` in this checkout agrees rather than reporting
        # the guard it would have written as drift (item 940).
        dependabot = (REPO_ROOT / guard.DEPENDABOT_RELATIVE_PATH).read_text(encoding="utf-8")
        self.assertEqual(guard.guard_state(dependabot), "absent")
        stream = io.StringIO()
        code = setup.check_files(REPO_ROOT, setup_args(check=True, pin=None), stream)
        self.assertEqual((code, stream.getvalue()), (0, f"same {setup.WORKFLOW_RELATIVE_PATH}\n"))

    def test_the_lane_holds_no_write_permission_and_requests_nobody(self) -> None:
        root = self.make_repo()
        install(root)
        text = self.workflow(root).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n", text)
        self.assertNotIn("write", text.split("jobs:")[0].split("permissions:")[1])
        for absent in ("requested_reviewers", "gh pr review", "pull-requests:", "GITHUB_TOKEN"):
            self.assertNotIn(absent, text)

    def test_the_header_describes_a_policy_that_may_not_be_there(self) -> None:
        # Found in review of the first consumer install: the header named
        # `.github/sd-review.json` as the thing `route()` runs over, in a
        # repository that has no such file. Most repositories will not have
        # one -- the built-in default is the normal case -- so the generated
        # comment has to describe both arms or it misleads by default.
        header, delimiter, _ = setup.workflow_text("./x").partition("name: sd-review route")
        # Without this the split silently returns the whole file and the two
        # assertions below pass against the body instead of the header.
        self.assertTrue(delimiter, "the workflow no longer carries the name this splits on")
        self.assertIn(".github/sd-review.json", header)
        self.assertIn("built-in default", header)

    def test_the_lane_cannot_pile_up_or_hang(self) -> None:
        # Both found in review of the first consumer installs. Neither is a
        # per-repository convention to be matched: a report-only lane that
        # leaves superseded runs going, or that can hang a runner for six
        # hours, is spending a repository's CI capacity to print a plan
        # nobody is waiting for any more.
        text = setup.workflow_text("./x")
        self.assertIn("cancel-in-progress: true", text)
        self.assertIn("timeout-minutes: 10", text)
        # `workflow_text` is an f-string, where `{{` renders as `{`. Written
        # naively, `${{ ... }}` reaches the file as `${ ... }`: not an error,
        # just a constant group name, so every pull request in a repository
        # would share one concurrency group and cancel each other's runs.
        self.assertIn(
            "group: sd-review-route-${{ github.event.pull_request.number }}", text
        )

    def test_the_lane_checks_out_the_head_not_the_merge_ref(self) -> None:
        # `actions/checkout` defaults to `refs/pull/N/merge` on a
        # `pull_request` event, and GitHub does not create that ref for a
        # pull request with conflicts. The head ref is held for the window
        # the merge ref would lose -- mergeable when the event fires,
        # conflicted by the time the runner checks out -- and for forks,
        # below. An advisory lane that reddens a pull request is the
        # framework making someone's pull request worse, which is the one
        # thing it must never do.
        text = setup.workflow_text("./x")
        self.assertIn(
            "ref: refs/pull/${{ github.event.pull_request.number }}/head", text
        )
        # Not the bare head SHA: `fetch-depth: 0` fetches `+refs/heads/*` and
        # tags, and `actions/checkout` adds a pull refspec only when the ref is
        # one -- so a SHA resolves for a same-repo pull request and fails for a
        # fork, whose head is on no branch here. Asserted because every pull
        # request in these repositories is same-repo today, which means CI
        # cannot show the difference.
        self.assertNotIn("head.sha", text)
        # And `origin` stays this repository, or `origin/<base>` would name the
        # fork's base branch and `route()` would measure the wrong diff.
        # Matched as a YAML key on its own line: the comment above it in the
        # generated file explains why `repository:` is wrong, and a substring
        # check would fire on the explanation.
        keys = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("repository:")
        ]
        self.assertEqual(keys, [])

    def test_the_head_ref_comment_does_not_claim_a_checkout_failure_on_conflicts(self) -> None:
        # The comment above `ref:` said the merge-ref default "fails this job
        # at checkout" on a conflicted pull request. Measured on probe PR
        # #966 (sd:878): GitHub creates no `pull_request` run at all in that
        # state, so no job reaches checkout to fail there. A consumer's
        # installed copy is this function's output, so the generated text
        # is what has to say what was measured (sd:932). Read as prose, with
        # the comment markers and line wraps removed, so the assertions do
        # not depend on where a sentence happens to break.
        prose = " ".join(
            line.strip().lstrip("#").strip() for line in setup.workflow_text("./x").splitlines()
        )
        self.assertNotIn("fails this job at checkout", prose)
        self.assertIn("starts no `pull_request` run at all", prose)
        self.assertIn("#966", prose)

    def test_the_action_referenced_exists_in_this_checkout(self) -> None:
        # A workflow naming an action path that is not shipped is a lane that
        # fails on its first run in every consumer at once.
        self.assertTrue((REPO_ROOT / setup.ACTION_SUBPATH / "action.yml").is_file())

    def test_the_action_points_origin_head_at_the_pull_request_base(self) -> None:
        # The first run of this lane failed with "cannot resolve a base branch":
        # a pull-request checkout is a detached HEAD with no `origin/HEAD` and
        # no local `main`, which is exactly what `sd-review` looks for. Asserted
        # because the failure is invisible until a real pull request runs it.
        action = (REPO_ROOT / setup.ACTION_SUBPATH / "action.yml").read_text(encoding="utf-8")
        self.assertIn('git remote set-head origin "${GITHUB_BASE_REF}"', action)
        self.assertIn("fetch-depth: 0", setup.workflow_text("./x"))


class ReplacementTests(SetupFixture):
    def test_rerunning_reports_unchanged(self) -> None:
        root = self.make_repo()
        install(root)
        result = install(root)
        self.assertEqual(result["status"], "unchanged")

    def test_a_differing_workflow_refuses_without_force(self) -> None:
        root = self.make_repo()
        target = self.workflow(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("name: someone else's lane\n", encoding="utf-8")
        with self.assertRaises(setup.Refusal) as caught:
            install(root)
        self.assertIn("--force", str(caught.exception))
        self.assertEqual(target.read_text(encoding="utf-8"), "name: someone else's lane\n")

    def test_force_replaces_it(self) -> None:
        root = self.make_repo()
        target = self.workflow(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("name: someone else's lane\n", encoding="utf-8")
        result = install(root, force=True)
        self.assertEqual(result["status"], "installed")
        self.assertIn("sd-review route", target.read_text(encoding="utf-8"))


class PinTests(SetupFixture):
    def test_a_dirty_pack_checkout_refuses_to_pin(self) -> None:
        pack = self.make_repo("pack")
        (pack / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        with self.assertRaises(setup.Refusal) as caught:
            setup.resolve_pin(pack, None)
        self.assertIn("uncommitted changes", str(caught.exception))

    def test_a_clean_pack_checkout_pins_its_head(self) -> None:
        pack = self.make_repo("pack")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(pack), check=True, capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(setup.resolve_pin(pack, None), head)

    def test_an_explicit_pin_is_not_second_guessed(self) -> None:
        pack = self.make_repo("pack")
        (pack / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        self.assertEqual(setup.resolve_pin(pack, PIN), PIN)


# platypeeps/people-profiles at origin/main on 2026-09-11, byte for byte: one of
# the six hand-written wordings, and the one that recites the most -- a sibling
# repository, two SHAs, a fix commit and a pull request number.
OLD_WORDING = """\
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    ignore:
      # The review-route pin is set by hand, not by Dependabot. The action runs
      # `bin/sd-review` out of the pinned checkout, so a bump is a behaviour
      # change across the whole pack, not a version number.
      #
      # rwbp-coordinator is the proof. It had no such entry, so Dependabot
      # bumped its pin from cada9b61 to 1ff2b049 unattended; that range
      # introduced a gate refusing any commit without an `Authored-with:`
      # trailer, `route` went red on the bump's own pull request, and it merged
      # anyway because `route` is advisory and `CI Result` was green. Every pull
      # request there was red for the next three days.
      #
      # The refusal itself is fixed upstream (platypeeps/sd-ai-command-pack#799,
      # carried by 505431b8). This entry is for the reason that outlives it: the
      # next behaviour change would arrive the same way.
      - dependency-name: "platypeeps/sd-ai-command-pack/actions/review-route"
"""

# A consumer's file the pack has never touched: two entries, the first with an
# `ignore:` list of its own, and comments the consumer wrote.
NO_GUARD = """\
version: 2
updates:
  # Actions first.
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
    ignore:
      # Major bumps by hand.
      - dependency-name: "actions/checkout"
        update-types: ["version-update:semver-major"]

  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
"""


class GuardTests(SetupFixture):
    """The Dependabot guard is written from one template, beside the workflow."""

    def test_the_guard_names_the_action_the_workflow_pins(self) -> None:
        # Two constants in two modules; the guard module cannot import the
        # installer to share one without a cycle, so the agreement is asserted.
        self.assertEqual(guard.DEPENDENCY, f"{setup.ACTION_REPOSITORY}/{setup.ACTION_SUBPATH}")

    def test_the_guard_recites_no_incident(self) -> None:
        # Five of the seven hand-written copies named a fix commit and a pull
        # request beside the real pin, and were stale the day it moved.
        block = guard.guard_block("")
        for stale in ("505431b8", "#799", "cada9b61", "1ff2b049", "rwbp-coordinator", "three days"):
            self.assertNotIn(stale, block)
        self.assertIn("actions/review-route/README.md", block)
        self.assertIn("--pin <sha> --force", block)

    def test_the_guard_module_writes_nothing(self) -> None:
        # Text in, text out: the installer is the one writer in the lane.
        source = (REPO_ROOT / "bin" / "sd_setup_guard.py").read_text(encoding="utf-8")
        self.assertNotIn(".write_text(", source)
        self.assertNotIn("open(", source)

    def test_an_absent_file_is_created_minimal(self) -> None:
        root = self.make_repo()
        result = install(root)
        self.assertEqual(result["guard"], "missing")
        text = self.dependabot(root).read_text(encoding="utf-8")
        self.assertEqual(text, guard.minimal_file())
        self.assertTrue(text.startswith("version: 2\nupdates:\n"))
        self.assertIn("open-pull-requests-limit: 5", text)
        self.assertTrue(text.endswith(guard.guard_block("      ")))

    def test_an_entry_without_the_guard_gains_it_and_keeps_its_own_lines(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(root, NO_GUARD)
        result = install(root)
        self.assertEqual(result["guard"], "absent")
        text = self.dependabot(root).read_text(encoding="utf-8")
        # Every line the consumer wrote is still there, in order.
        remaining = iter(text.splitlines())
        for line in NO_GUARD.splitlines():
            self.assertIn(line, remaining, f"consumer line dropped: {line!r}")
        # The guard is inside the github-actions entry's list, not the pip one.
        actions, pip = text.split("- package-ecosystem: pip")
        self.assertIn(guard.guard_block("      "), actions)
        self.assertNotIn("sd-ai-command-pack", pip)
        self.assertEqual(guard.guard_state(text), "same")

    def test_an_entry_without_an_ignore_list_gets_one(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(root, NO_GUARD.replace("    ignore:\n", "").split("      # Major")[0]
                             + "\n  - package-ecosystem: pip\n    directory: /\n")
        install(root)
        text = self.dependabot(root).read_text(encoding="utf-8")
        self.assertIn("    ignore:\n" + guard.guard_block("      "), text)
        self.assertEqual(guard.guard_state(text), "same")

    def test_an_old_wording_refuses_without_force(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(root, OLD_WORDING)
        with self.assertRaises(setup.Refusal) as caught:
            install(root)
        self.assertIn("--force", str(caught.exception))
        self.assertIn(str(guard.DEPENDABOT_RELATIVE_PATH), str(caught.exception))
        self.assertEqual(self.dependabot(root).read_text(encoding="utf-8"), OLD_WORDING)
        self.assertFalse(self.workflow(root).exists())

    def test_force_converges_an_old_wording_on_the_template(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(root, OLD_WORDING)
        result = install(root, force=True)
        self.assertEqual(result["guard"], "differs")
        text = self.dependabot(root).read_text(encoding="utf-8")
        self.assertEqual(text, guard.minimal_file())
        self.assertNotIn("505431b8", text)

    def test_the_transform_is_idempotent(self) -> None:
        for name, text in (("old", OLD_WORDING), ("none", NO_GUARD), ("minimal", guard.minimal_file())):
            with self.subTest(name=name):
                once = guard.rendered(text)
                self.assertEqual(guard.rendered(once), once)
                self.assertEqual(guard.guard_state(once), "same")

    def test_a_file_with_no_entry_at_all_refuses_by_name(self) -> None:
        with self.assertRaises(guard.GuardError) as caught:
            guard.rendered("version: 2\nupdates: []\n")
        self.assertIn("package-ecosystem", str(caught.exception))

    def test_rerunning_is_unchanged_and_dry_run_shows_both(self) -> None:
        root = self.make_repo()
        install(root)
        self.assertEqual(install(root)["status"], "unchanged")
        result = install(root, dry_run=True)
        self.assertEqual(result["would_write_dependabot"], guard.minimal_file())
        self.assertIn("sd-review route", result["would_write"])


class SelfInstallTests(SetupFixture):
    """The pack's own checkout: the workflow is written, `dependabot.yml` is not.

    `action_reference(None)` writes `$/actions/review-route`, a reference with
    no pin in it, so the self-install has no dependency for Dependabot to bump
    and nothing for the guard to hold. Found by the sd:932 lane, which saw
    `setup-github --force` in its worktree write a guard for a dependency the
    pack's workflow does not name (item 940). The pack is whichever checkout
    the installer runs from, so these tests point `pack_root` at the fixture.
    """

    def as_pack(self, root: pathlib.Path) -> Any:
        return mock.patch.object(setup, "pack_root", return_value=root)

    def test_no_dependabot_file_is_created(self) -> None:
        root = self.make_repo()
        with self.as_pack(root):
            result = install(root)
        self.assertEqual((result["pin"], result["action"]), (None, setup.action_reference(None)))
        self.assertEqual(result["guard"], "missing")
        self.assertTrue(self.workflow(root).is_file())
        self.assertFalse(self.dependabot(root).exists())

    def test_an_existing_file_keeps_its_bytes_and_a_rerun_is_unchanged(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(root, NO_GUARD)
        with self.as_pack(root):
            self.assertEqual(install(root)["status"], "installed")
            self.assertEqual(install(root)["status"], "unchanged")
            result = install(root, dry_run=True)
        self.assertEqual(self.dependabot(root).read_text(encoding="utf-8"), NO_GUARD)
        self.assertNotIn(guard.DEPENDENCY, self.dependabot(root).read_text(encoding="utf-8"))
        # Dry run shows the file as it would stand after the run: as it is.
        self.assertEqual(result["would_write_dependabot"], NO_GUARD)

    def test_a_hand_written_guard_is_still_read_and_left_alone(self) -> None:
        # Skipping the write must not skip the read: a guard someone put in the
        # pack's own file by hand is reported as it is found, and neither
        # refused over nor replaced, because there is no pin for it to guard.
        root = self.make_repo()
        self.seed_dependabot(root, OLD_WORDING)
        with self.as_pack(root):
            result = install(root)
        self.assertEqual(result["guard"], "differs")
        self.assertEqual(self.dependabot(root).read_text(encoding="utf-8"), OLD_WORDING)

    def test_check_reports_the_workflow_only(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(root, OLD_WORDING)
        stream = io.StringIO()
        with self.as_pack(root):
            install(root)
            code = setup.check_files(root, setup_args(check=True, pin=None), stream)
        self.assertEqual((code, stream.getvalue()), (0, f"same {setup.WORKFLOW_RELATIVE_PATH}\n"))


#: `mezmo/mezmo-world-simulator`'s file, trimmed to the entry under test: it
#: pins `actions/docs-gate` only, and hand-adapted the pack's guard for it.
DOCS_GATE_CONSUMER = """\
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    ignore:
{guard}
      # `dtolnay/rust-toolchain` is referenced by a ref named after a Rust
      # release, so Dependabot version-compares the action's own branch names.
      - dependency-name: "dtolnay/rust-toolchain"
"""


class BothActionsTests(SetupFixture):
    """The pack ships two actions and the guard reader knows both.

    `DEPENDENCY`, the guard item pattern and the pin pattern were all keyed to
    `actions/review-route`, the action `setup-github` installs. The one
    consumer that pins `actions/docs-gate` instead carries a correct,
    hand-adapted guard for it, and `guard_state()` called that file `absent` --
    so a census built on this reader miscounted the fleet by one, in the
    direction of "nobody guards it".
    """

    def guarded(self, action: str) -> str:
        return DOCS_GATE_CONSUMER.format(guard=guard.guard_block("      ", action).rstrip("\n"))

    def test_every_shipped_action_has_guard_text(self) -> None:
        """Enumerated from `actions/`, not from a list beside the constant.

        A third action landing with no wording here is the failure this
        catches: it would ship a consumer the reader again calls `absent`.
        """
        shipped = {
            path.name
            for path in (REPO_ROOT / "actions").iterdir()
            if path.is_dir() and (path / "action.yml").is_file()
        }
        self.assertEqual(shipped, set(guard.ACTIONS))
        for action in guard.ACTIONS:
            with self.subTest(action=action):
                block = guard.guard_block("", action)
                self.assertIn(f"actions/{action}/README.md", block)
                self.assertIn(f'- dependency-name: "{guard.dependency_name(action)}"', block)
                for other in guard.ACTIONS:
                    if other != action:
                        self.assertNotIn(f"actions/{other}/README.md", block)

    def test_the_review_route_guard_is_unchanged(self) -> None:
        """Eight consumers carry these bytes today and must keep reading `same`."""
        self.assertEqual(guard.guard_block(""), guard.guard_block("", "review-route"))
        self.assertIn("`sd-review setup-github --pin <sha> --force`", guard.guard_block(""))

    def test_a_docs_gate_guard_reads_as_present(self) -> None:
        text = self.guarded("docs-gate")
        self.assertEqual(guard.guard_state(text), "same")
        self.assertEqual(guard.guard_state(text, "docs-gate"), "same")

    def test_rendering_docs_gate_is_idempotent_and_adds_no_second_item(self) -> None:
        """Writing is per-action and reading is not: `rendered` renders the
        action it is given, so a docs-gate consumer converges on its own guard
        and never gains a review-route item for an action it does not pin."""
        text = self.guarded("docs-gate")
        self.assertEqual(guard.rendered(text, "docs-gate"), text)
        self.assertNotIn("actions/review-route", guard.rendered(text, "docs-gate"))

    def test_the_installers_action_still_appends_beside_another_guard(self) -> None:
        """The installer writes review-route and must keep doing so: a
        docs-gate item is another action's guard, not this one's, so it is
        left standing and the review-route guard lands beside it."""
        both = guard.rendered(self.guarded("docs-gate"))
        self.assertIn(guard.guard_block("      ", "docs-gate"), both)
        self.assertIn(guard.guard_block("      ", "review-route"), both)
        self.assertEqual(guard.rendered(both), both)

    def test_the_hand_adapted_wording_differs_rather_than_vanishing(self) -> None:
        """The live defect, in one assertion: the shipped file cites the wrong
        README, and the reader must say so instead of `absent`."""
        hand = self.guarded("docs-gate").replace(
            "actions/docs-gate/README.md", "actions/review-route/README.md"
        )
        self.assertEqual(guard.guard_state(hand), "differs")
        self.assertEqual(guard.rendered(hand, "docs-gate"), self.guarded("docs-gate"))

    def test_the_pin_is_read_for_either_action(self) -> None:
        workflow = (
            "      - uses: platypeeps/sd-ai-command-pack/actions/docs-gate@" + PIN + "\n"
        )
        self.assertIsNone(guard.read_pin(workflow))
        self.assertEqual(guard.read_pin(workflow, "docs-gate"), PIN)
        self.assertEqual(guard.pinned_actions(workflow), ("docs-gate",))

    def test_an_unknown_action_is_refused_by_name(self) -> None:
        with self.assertRaises(guard.GuardError) as caught:
            guard.guard_block("", "no-such-action")
        self.assertIn("no-such-action", str(caught.exception))


# A consumer that pins both actions: the docs-gate guard at the template
# wording, and above -- ahead of it in the `ignore:` list -- nothing; the
# review-route item comes second, carrying prose its own team wrote.
HAND_WRITTEN_REVIEW_ROUTE = """\
      # The sd-ai-command-pack pin is set by hand. Ask #platform before moving
      # it: the release train pins the same sha in three sibling repositories.
      - dependency-name: "platypeeps/sd-ai-command-pack/actions/review-route"
"""


def consumer(*blocks: str) -> str:
    """One github-actions entry whose `ignore:` list holds `blocks`, in order."""

    return (
        'version: 2\nupdates:\n'
        '  - package-ecosystem: "github-actions"\n'
        '    directory: "/"\n'
        '    schedule:\n'
        '      interval: "weekly"\n'
        "    open-pull-requests-limit: 5\n"
        "    ignore:\n" + "".join(blocks)
    )


class GuardActionTests(SetupFixture):
    """The write gate reads the guard for the action the installer writes.

    `guard_state()` without an action answers about whichever of the pack's
    actions the file guards first -- the reading a fleet census wants, and the
    wrong question for a gate standing in front of a per-action write.
    `rendered()` replaces the review-route block; the gate has to be asked
    about the review-route block, or it reports on a different one.
    """

    def test_a_hand_written_review_route_guard_is_not_silently_replaced(self) -> None:
        """docs-gate guard first, review-route guard second and hand-written.

        The action-blind read stops at the docs-gate block, says `same`, and
        lets the write through: the team's prose is replaced by the template
        and the report calls the run unchanged.
        """
        root = self.make_repo()
        text = consumer(guard.guard_block("      ", "docs-gate"), HAND_WRITTEN_REVIEW_ROUTE)
        self.seed_dependabot(root, text)
        with self.assertRaises(setup.Refusal) as caught:
            install(root)
        self.assertIn("--force", str(caught.exception))
        self.assertEqual(self.dependabot(root).read_text(encoding="utf-8"), text)

    def test_the_report_names_the_state_of_the_block_it_writes(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(
            root, consumer(guard.guard_block("      ", "docs-gate"), HAND_WRITTEN_REVIEW_ROUTE)
        )
        result = install(root, force=True)
        self.assertEqual(result["guard"], "differs")
        text = self.dependabot(root).read_text(encoding="utf-8")
        self.assertIn(guard.guard_block("      ", "docs-gate"), text)
        self.assertIn(guard.guard_block("      ", "review-route"), text)
        self.assertNotIn("#platform", text)

    def test_a_differing_docs_gate_guard_does_not_refuse_this_install(self) -> None:
        """The other direction: a guard for an action this run does not write.

        The file holds one item, for docs-gate, at a wording that differs from
        the template. The action-blind read says `differs` and the run refuses
        by naming a review-route guard the file does not carry.
        """
        root = self.make_repo()
        stale = guard.guard_block("      ", "docs-gate").replace(
            "actions/docs-gate/README.md", "actions/review-route/README.md"
        )
        self.seed_dependabot(root, consumer(stale))
        result = install(root)
        self.assertEqual(result["guard"], "absent")
        text = self.dependabot(root).read_text(encoding="utf-8")
        self.assertIn(stale, text)
        self.assertIn(guard.guard_block("      ", "review-route"), text)

    def test_the_gate_is_the_only_action_blind_read_left(self) -> None:
        """Every `guard_state` call in the installer names its action."""

        source = (REPO_ROOT / "bin" / "sd_setup_github.py").read_text(encoding="utf-8")
        calls = [
            line
            for line in source.splitlines()
            if "guard_state(" in line and not line.lstrip().startswith("#")
        ]
        self.assertTrue(calls)
        for line in calls:
            self.assertIn("DEFAULT_ACTION", line, f"action-blind write gate: {line.strip()}")


TWO_ENTRY_CONSUMER = """\
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    ignore:
{guard}
  - package-ecosystem: "github-actions"
    directory: "/.github/actions/inner"
    schedule:
      interval: "weekly"
    ignore:
{second}
"""

SECOND_UNGUARDED = """\
      # The inner action set is bumped by hand too.
      - dependency-name: "actions/checkout"
"""

SECOND_STALE = """\
      # Bump this by hand, in its own commit.
      - dependency-name: "platypeeps/sd-ai-command-pack/actions/review-route"
"""


class EveryEntryTests(SetupFixture):
    """A verdict about the file, not about whichever entry comes first.

    Dependabot allows more than one `github-actions` entry -- separate
    `directory:` scopes, or the same scope twice -- and each carries its own
    `ignore:` list. The reader stopped at the first match and reported the
    answer as though it covered the file, so a consumer whose second entry is
    unguarded or carries a stale wording read `same`. The Copilot round in
    `tests/fixtures/sd-543-review-round.json` named it: "aggregate verdicts
    must inspect all matching action blocks."
    """

    def consumer(self, second: str) -> str:
        return TWO_ENTRY_CONSUMER.format(
            guard=guard.guard_block("      ").rstrip("\n"),
            second=second.rstrip("\n"),
        )

    def test_a_second_unguarded_entry_is_not_reported_as_same(self) -> None:
        text = self.consumer(SECOND_UNGUARDED)
        self.assertEqual(guard.guard_states(text), ("same", "absent"))
        self.assertEqual(guard.guard_state(text), "absent")

    def test_a_second_entry_with_a_stale_wording_reports_differs(self) -> None:
        """`differs` outranks `absent`: it is the verdict `--force` gates on."""
        text = self.consumer(SECOND_STALE)
        self.assertEqual(guard.guard_states(text), ("same", "differs"))
        self.assertEqual(guard.guard_state(text), "differs")

    def test_rendering_guards_every_entry_and_stays_idempotent(self) -> None:
        for name, second in (("unguarded", SECOND_UNGUARDED), ("stale", SECOND_STALE)):
            with self.subTest(name=name):
                once = guard.rendered(self.consumer(second))
                self.assertEqual(once.count(guard.guard_block("      ")), 2)
                self.assertEqual(guard.guard_states(once), ("same", "same"))
                self.assertEqual(guard.rendered(once), once)

    def test_the_installer_refuses_a_stale_second_entry_without_force(self) -> None:
        """The write gate reads the folded verdict, so the refusal reaches the
        entry it used to walk past."""
        root = self.make_repo()
        text = self.consumer(SECOND_STALE)
        self.seed_dependabot(root, text)
        with self.assertRaises(setup.Refusal) as caught:
            install(root)
        self.assertIn("--force", str(caught.exception))
        self.assertEqual(self.dependabot(root).read_text(encoding="utf-8"), text)

    def test_force_converges_every_entry_on_the_template(self) -> None:
        root = self.make_repo()
        self.seed_dependabot(root, self.consumer(SECOND_STALE))
        result = install(root, force=True)
        self.assertEqual(result["guard"], "differs")
        written = self.dependabot(root).read_text(encoding="utf-8")
        self.assertEqual(written.count(guard.guard_block("      ")), 2)
        self.assertEqual(guard.guard_state(written), "same")


class CheckTests(SetupFixture):
    """`--check` renders at the repository's own pin and writes nothing."""

    def run_check(self, root: pathlib.Path, **overrides: Any) -> tuple[int, str]:
        stream = io.StringIO()
        code = setup.check_files(root, setup_args(check=True, **{"pin": None, **overrides}), stream)
        return code, stream.getvalue()

    def test_a_fresh_install_is_same_twice(self) -> None:
        root = self.make_repo()
        install(root)
        code, out = self.run_check(root)
        self.assertEqual(code, 0)
        self.assertEqual(
            out, f"same {setup.WORKFLOW_RELATIVE_PATH}\nsame {guard.DEPENDABOT_RELATIVE_PATH}\n"
        )

    def test_an_old_wording_differs_with_a_diff_and_exit_1(self) -> None:
        root = self.make_repo()
        install(root)
        self.seed_dependabot(root, OLD_WORDING)
        before = {p: p.read_text(encoding="utf-8") for p in (self.workflow(root), self.dependabot(root))}
        code, out = self.run_check(root)
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(lines[0], f"same {setup.WORKFLOW_RELATIVE_PATH}")
        self.assertEqual(lines[1], f"DIFFERS {guard.DEPENDABOT_RELATIVE_PATH}")
        self.assertIn("-      # rwbp-coordinator is the proof. It had no such entry, so Dependabot", lines)
        self.assertIn("+      # The sd-ai-command-pack pin is set by hand, not by Dependabot. The action", lines)
        # Nothing moved on disk.
        self.assertEqual({p: p.read_text(encoding="utf-8") for p in before}, before)

    def test_the_pin_is_read_from_the_tracked_workflow(self) -> None:
        # Rendering at the pack's HEAD would report every consumer as drifted
        # the day after any pack commit; the check is of the template.
        root = self.make_repo()
        install(root)
        self.assertEqual(guard.read_pin(self.workflow(root).read_text(encoding="utf-8")), PIN)
        code, out = self.run_check(root)
        self.assertEqual((code, out.count("same")), (0, 2))

    def test_an_edited_workflow_differs(self) -> None:
        root = self.make_repo()
        install(root)
        path = self.workflow(root)
        path.write_text(path.read_text(encoding="utf-8").replace("timeout-minutes: 10", "timeout-minutes: 60"))
        code, out = self.run_check(root)
        self.assertEqual(code, 1)
        self.assertIn(f"DIFFERS {setup.WORKFLOW_RELATIVE_PATH}", out)
        self.assertIn("-    timeout-minutes: 60", out)

    def test_no_workflow_and_no_pin_refuses(self) -> None:
        root = self.make_repo()
        with self.assertRaises(setup.Refusal) as caught:
            self.run_check(root)
        self.assertIn("--pin", str(caught.exception))

    def test_an_explicit_pin_renders_a_missing_pair_as_differs(self) -> None:
        root = self.make_repo()
        code, out = self.run_check(root, pin=PIN)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("DIFFERS"), 2)
        self.assertFalse(self.workflow(root).exists())
        self.assertFalse(self.dependabot(root).exists())


class CliTests(SetupFixture):
    def test_the_subcommand_does_not_disturb_the_default_parser(self) -> None:
        args = sd_review.build_parser().parse_args(["--scope", "pr", "--explain"])
        self.assertEqual(args.scope, "pr")
        self.assertTrue(args.explain)

    def test_check_is_dispatched_before_any_write(self) -> None:
        root = self.make_repo()
        install(root)
        cwd = pathlib.Path.cwd()
        import os

        os.chdir(root)
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = setup.main(["--check"], load_policy=sd_review.load_policy)
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().count("same "), 2)

    def test_render_names_what_the_lane_will_not_do(self) -> None:
        """It used to list the GitHub-lane backends it was not going to ask.
        There is no such list now -- the lane asks nobody at all, which is the
        stronger sentence and the one it prints."""

        root = self.make_repo()
        result = install(root, dry_run=True)
        stream = io.StringIO()
        setup.render(result, stream)
        text = stream.getvalue()
        self.assertIn("every provider", text)
        self.assertIn("requests nobody", text)


if __name__ == "__main__":
    unittest.main()
