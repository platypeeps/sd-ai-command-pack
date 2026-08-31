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
import importlib.machinery
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_REVIEW = REPO_ROOT / "bin" / "sd-review"
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_setup_github as setup  # noqa: E402


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
        backends=sd_review.BACKENDS,
    )

PIN = "0" * 40


def setup_args(**overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "dry_run": False,
        "json": False,
        "force": False,
        "remove_legacy": False,
        "pin": PIN,
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

    def test_the_pack_itself_gets_the_local_path(self) -> None:
        # The bootstrap the digest cannot close: the pull request installing the
        # lane in the pack would pin a commit that only exists once it merges.
        self.assertEqual(setup.action_reference(None), f"./{setup.ACTION_SUBPATH}")

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
        # pull request with conflicts -- so the default fails this job at
        # checkout on exactly the pull requests already in trouble. An
        # advisory lane that reddens a conflicted pull request is the
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


class CliTests(SetupFixture):
    def test_the_subcommand_does_not_disturb_the_default_parser(self) -> None:
        args = sd_review.build_parser().parse_args(["--scope", "pr", "--explain"])
        self.assertEqual(args.scope, "pr")
        self.assertTrue(args.explain)

    def test_render_names_what_the_lane_will_not_do(self) -> None:
        root = self.make_repo()
        result = install(root, dry_run=True)
        stream = io.StringIO()
        setup.render(result, stream)
        text = stream.getvalue()
        self.assertIn("copilot", text)
        self.assertIn("requests nobody", text)


if __name__ == "__main__":
    unittest.main()
