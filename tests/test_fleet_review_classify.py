from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
io = _support.io
json = _support.json
fleet_manifest = _support.fleet_manifest
mock = _support.mock
Path = _support.Path
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

CLASSIFIER = PACK_ROOT / "scripts/sd-ai-command-pack-fleet-review-classify.py"


class FleetReviewClassifyTests(InstallTestCase):
    def load_classifier(self):
        return self.load_module_from_path(
            CLASSIFIER,
            f"sd_ai_command_pack_fleet_review_classify_{id(self)}",
        )

    def write_receipt(self, root: Path, targets: list[str]) -> None:
        path = root / ".sd-ai-command-pack/installed-targets.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{target}\n" for target in targets), encoding="utf-8")

    def write_fleet(self, root: Path) -> Path:
        path = root.parent / f"{root.name}-fleet.json"
        path.write_text(
            json.dumps(
                fleet_manifest(
                    [
                        {
                            "name": "fixture",
                            "github": "example/fixture",
                            "pathHint": str(root),
                            "platforms": ["github"],
                            "rolloutPriority": 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["node", "check.mjs"]],
                        }
                    ]
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def make_refresh(
        self,
        *,
        base_targets: list[str] | None = None,
        current_targets: list[str] | None = None,
        product_change: bool = False,
        newly_tracked: list[str] | None = None,
        finalization: dict | None = None,
        extra_trellis: dict[str, str] | None = None,
    ) -> tuple[object, Path, str, Path]:
        classifier = self.load_classifier()
        root = self.make_git_repo_without_trellis()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        base_targets = base_targets or ["managed.txt"]
        current_targets = current_targets or ["managed.txt"]
        for target in base_targets:
            if target.startswith(".") or "/" in target or "\\" in target:
                continue
            (root / target).write_text(f"base {target}\n", encoding="utf-8")
        self.write_receipt(root, base_targets)
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "base install")
        base_commit = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(root, "switch", "-c", "refresh")

        for target in set(base_targets) - set(current_targets):
            candidate = root / target
            if candidate.is_file():
                candidate.unlink()
        for target in current_targets:
            candidate = root / target
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(f"current {target}\n", encoding="utf-8")
        self.write_receipt(root, current_targets)
        if product_change:
            (root / "product.txt").write_text("consumer code\n", encoding="utf-8")
        # Files newly tracked on the refresh branch that are deliberately kept
        # out of the receipt: a Trellis-owned adapter a consumer un-ignores must
        # not silently join the pack-vouched set.
        for path in newly_tracked or []:
            candidate = root / path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(f"newly tracked {path}\n", encoding="utf-8")
        # What sd-ai-command-pack-fleet-publish.py folds into the reviewed head:
        # the lane's own task archive and the journal recording it.
        if finalization is not None:
            slug = finalization.get("slug", "08-29-refresh-to-1-2-3")
            archive = root / ".trellis/tasks/archive/2026-08" / slug
            archive.mkdir(parents=True, exist_ok=True)
            (archive / "prd.md").write_text("# refresh\n", encoding="utf-8")
            (archive / "task.json").write_text(
                json.dumps(
                    {
                        "id": slug,
                        "status": finalization.get("status", "completed"),
                        "assignee": finalization.get("assignee", "sdelmas"),
                        "branch": finalization.get("branch", "refresh"),
                        "base_branch": "main",
                    }
                ),
                encoding="utf-8",
            )
            workspace = root / ".trellis/workspace" / finalization.get(
                "journal_owner", finalization.get("assignee", "sdelmas")
            )
            workspace.mkdir(parents=True, exist_ok=True)
            (workspace / "index.md").write_text("# index\n", encoding="utf-8")
            (workspace / "journal-1.md").write_text("# journal\n", encoding="utf-8")
        for path, content in (extra_trellis or {}).items():
            candidate = root / path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(content, encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "refresh pack")
        return classifier, root, base_commit, self.write_fleet(root)

    def release_verifier(self, classifier):
        def verify(_repo: Path, **_kwargs):
            return classifier.ReleaseIdentity(
                status="verified",
                version="1.2.3",
                tag="v1.2.3",
                commit_sha="a" * 40,
                payload_digest="sha256:" + "b" * 64,
            )

        return verify

    def inspection_runner(self, root: Path):
        def inspect(repo: Path) -> dict[str, object]:
            return {
                "schemaVersion": 1,
                "pack": "sd-ai-command-pack",
                "target": str(repo.resolve()),
                "sourceVersion": "1.2.3",
                "installedVersion": "1.2.3",
                "state": "current",
                "changeCount": 0,
                "platforms": {"installed": ["github"], "active": ["github"]},
                "audit": {"requested": True, "status": "passed", "exitCode": 0},
            }

        return inspect

    def classify(self, classifier, root: Path, base_commit: str, fleet: Path):
        return classifier.classify_review(
            consumer_name="fixture",
            repo=root,
            base_commit=base_commit,
            manifest_path=root.parent / "source/manifest.json",
            fleet_path=fleet,
            ledger_path=root.parent / "source/candidate-validation.json",
            release_verifier=self.release_verifier(classifier),
            inspection_runner=self.inspection_runner(root),
        )

    def test_qualifies_pure_installer_managed_refresh(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh()

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertTrue(result.eligible)
        self.assertEqual(result.classification, "integration-only")
        self.assertEqual(result.changed_paths, ("managed.txt",))
        self.assertEqual(result.disallowed_paths, ())
        self.assertEqual(result.installed_version, "1.2.3")
        payload = result.as_json()
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["releaseIdentity"]["tag"], "v1.2.3")
        self.assertEqual(json.loads(json.dumps(payload, sort_keys=True)), payload)

    def test_qualifies_retired_target_from_base_receipt(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh(
            base_targets=["managed.txt", "retired.txt"],
            current_targets=["managed.txt"],
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertTrue(result.eligible, result.reasons)
        self.assertIn("retired.txt", result.changed_paths)
        self.assertIn("retired.txt", result.allowed_paths)

    def test_consumer_owned_change_requires_remote_review(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh(product_change=True)

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertEqual(result.classification, "remote-review-required")
        self.assertEqual(result.disallowed_paths, ("product.txt",))
        self.assertIn("consumer-owned or unclassified", result.reasons[0])

    def test_newly_tracked_trellis_adapter_stays_outside_pack_vouch(self) -> None:
        # A consumer relaxes its ignore policy so a Trellis-owned platform
        # adapter becomes newly tracked in the refresh diff. Because the pack
        # installer never wrote it to installed-targets.txt or provenance, it is
        # not in the receipt-derived allowed set, so the classifier must fall
        # back to remote review rather than treat it as a pack-vouched target.
        adapter = ".claude/agents/trellis-implement.md"
        classifier, root, base_commit, fleet = self.make_refresh(
            newly_tracked=[adapter],
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertEqual(result.classification, "remote-review-required")
        self.assertIn(adapter, result.changed_paths)
        self.assertIn(adapter, result.disallowed_paths)
        self.assertNotIn(adapter, result.allowed_paths)
        self.assertIn("consumer-owned or unclassified", result.reasons[0])

    def test_dirty_tree_requires_remote_review(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh()
        (root / "managed.txt").write_text("uncommitted\n", encoding="utf-8")

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertIn("working tree is not clean", result.reasons[0])

    def test_unsafe_base_receipt_requires_remote_review(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh(
            base_targets=["../outside.txt"],
            current_targets=["managed.txt"],
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertIn("base installed-targets receipt has unsafe entry", result.reasons[0])

    def test_non_ancestor_base_requires_remote_review(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh()
        refresh_head = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(root, "switch", "--detach", base_commit)
        (root / "sibling.txt").write_text("sibling\n", encoding="utf-8")
        self.run_git(root, "add", "sibling.txt")
        self.run_git(root, "commit", "-m", "sibling")
        sibling = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(root, "switch", "--detach", refresh_head)

        result = self.classify(classifier, root, sibling, fleet)

        self.assertFalse(result.eligible)
        self.assertIn("is not an ancestor", result.reasons[0])

    def test_stale_release_or_failed_audit_requires_remote_review(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh()

        def stale_release(_repo: Path, **_kwargs):
            raise classifier.ReleaseIdentityError("candidate ledger is stale")

        stale = classifier.classify_review(
            consumer_name="fixture",
            repo=root,
            base_commit=base_commit,
            manifest_path=root.parent / "source/manifest.json",
            fleet_path=fleet,
            ledger_path=root.parent / "source/candidate-validation.json",
            release_verifier=stale_release,
            inspection_runner=self.inspection_runner(root),
        )
        failed_audit_payload = self.inspection_runner(root)(root)
        failed_audit_payload["state"] = "invalid"
        failed_audit = classifier.classify_review(
            consumer_name="fixture",
            repo=root,
            base_commit=base_commit,
            manifest_path=root.parent / "source/manifest.json",
            fleet_path=fleet,
            ledger_path=root.parent / "source/candidate-validation.json",
            release_verifier=self.release_verifier(classifier),
            inspection_runner=lambda _repo: failed_audit_payload,
        )

        self.assertFalse(stale.eligible)
        self.assertIn("candidate ledger is stale", stale.reasons[0])
        self.assertFalse(failed_audit.eligible)
        self.assertIn("inspection state is 'invalid'", failed_audit.reasons[0])

    def test_receipt_parser_rejects_duplicates_and_windows_paths(self) -> None:
        classifier = self.load_classifier()

        for content, message in (
            ("same.txt\nsame.txt\n", "duplicate"),
            ("dir\\file.txt\n", "unsafe"),
            ("C:\\outside.txt\n", "unsafe"),
        ):
            with self.subTest(content=content):
                with self.assertRaisesRegex(
                    classifier.FleetReviewClassificationError,
                    message,
                ):
                    classifier.parse_installed_targets(content, "fixture receipt")

        with self.assertRaisesRegex(
            classifier.FleetReviewClassificationError,
            "contains no installed targets",
        ):
            classifier.parse_installed_targets("\n# comment only\n", "empty receipt")

    def test_path_decoding_and_diagnostics_fail_closed(self) -> None:
        classifier = self.load_classifier()

        detail = classifier._bounded_detail("word " * 20, limit=24)
        self.assertEqual(len(detail), 24)
        self.assertTrue(detail.endswith("..."))
        for raw, message in (
            (b"\xff\0", "non-UTF-8"),
            (b"../outside.txt\0", "unsafe path"),
        ):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(
                    classifier.FleetReviewClassificationError,
                    message,
                ):
                    classifier._decode_git_paths(raw, "fixture diff")

        with mock.patch.object(classifier, "_git_bytes", return_value=b"\xff"):
            with self.assertRaisesRegex(
                classifier.FleetReviewClassificationError,
                "not valid UTF-8",
            ):
                classifier.installed_targets_at_commit(Path("/tmp/repo"), "a" * 40)

    def test_install_inspection_bounds_failures_and_json(self) -> None:
        classifier = self.load_classifier()
        repo = self.make_git_repo_without_trellis()
        valid = {
            "state": "current",
            "target": str(repo),
        }
        completed = classifier.subprocess.CompletedProcess(
            ["install.py"],
            0,
            stdout=json.dumps(valid),
            stderr="",
        )

        with mock.patch.object(classifier.subprocess, "run", return_value=completed):
            self.assertEqual(classifier.run_install_inspection(repo), valid)
        with mock.patch.object(
            classifier.subprocess,
            "run",
            side_effect=OSError("python unavailable"),
        ):
            with self.assertRaisesRegex(
                classifier.FleetReviewClassificationError,
                "failed to start or timed out",
            ):
                classifier.run_install_inspection(repo)
        invalid = classifier.subprocess.CompletedProcess(
            ["install.py"],
            3,
            stdout="refresh required\n",
            stderr="",
        )
        with mock.patch.object(classifier.subprocess, "run", return_value=invalid):
            with self.assertRaisesRegex(
                classifier.FleetReviewClassificationError,
                "exited 3: refresh required",
            ):
                classifier.run_install_inspection(repo)

        for stdout, message in (
            ("{", "did not return valid JSON"),
            ("[]", "must contain an object"),
        ):
            malformed = classifier.subprocess.CompletedProcess(
                ["install.py"],
                0,
                stdout=stdout,
                stderr="",
            )
            with self.subTest(stdout=stdout):
                with mock.patch.object(
                    classifier.subprocess,
                    "run",
                    return_value=malformed,
                ):
                    with self.assertRaisesRegex(
                        classifier.FleetReviewClassificationError,
                        message,
                    ):
                        classifier.run_install_inspection(repo)

    def test_inspection_schema_rejects_every_review_boundary(self) -> None:
        classifier = self.load_classifier()
        repo = self.make_git_repo_without_trellis().resolve()
        valid = self.inspection_runner(repo)(repo)
        cases = (
            ({"sourceVersion": "0.0.0"}, "source version"),
            ({"installedVersion": "0.0.0"}, "provenance version"),
            ({"target": str(repo.parent)}, "target does not match"),
            ({"changeCount": True}, "planned changes"),
            ({"platforms": None}, "platforms must be an object"),
            ({"platforms": {"installed": [1]}}, "must be a string array"),
            ({"platforms": {"installed": ["codex"]}}, "fleet manifest"),
            ({"audit": None}, "audit must be an object"),
            (
                {"audit": {"requested": True, "status": "failed", "exitCode": 1}},
                "exact install audit did not pass",
            ),
        )

        for replacements, message in cases:
            payload = json.loads(json.dumps(valid))
            payload.update(replacements)
            with self.subTest(replacements=replacements):
                with self.assertRaisesRegex(
                    classifier.FleetReviewClassificationError,
                    message,
                ):
                    classifier.validate_inspection(
                        payload,
                        repo=repo,
                        release_version="1.2.3",
                        expected_platforms=("github",),
                    )

    def test_human_output_exposes_evidence_and_reasons(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh(product_change=True)
        result = self.classify(classifier, root, base_commit, fleet)

        output = classifier.render_human(result)

        self.assertIn("remote-review-required", output)
        self.assertIn("release: v1.2.3", output)
        self.assertIn("disallowed paths:", output)
        self.assertIn("- product.txt", output)
        self.assertIn("reasons:", output)

    def test_main_returns_classification_exit_and_json(self) -> None:
        classifier = self.load_classifier()
        result = classifier.FleetReviewClassification(
            eligible=False,
            consumer="fixture",
            repository="/tmp/fixture",
            base_commit=None,
            head_commit=None,
            release_identity=None,
            installed_version=None,
            installed_platforms=(),
            changed_paths=(),
            allowed_paths=(),
            disallowed_paths=(),
            reasons=("not eligible",),
        )
        output = io.StringIO()

        with (
            mock.patch.object(classifier, "classify_review", return_value=result),
            contextlib.redirect_stdout(output),
        ):
            exit_code = classifier.main(
                [
                    "--consumer",
                    "fixture",
                    "--repo",
                    "/tmp/fixture",
                    "--base-commit",
                    "a" * 40,
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            json.loads(output.getvalue())["classification"],
            "remote-review-required",
        )


    def test_the_publishers_own_finalization_no_longer_blocks_eligibility(
        self,
    ) -> None:
        """`integration-only` was unreachable by construction.

        `sd-ai-command-pack-fleet-publish.py` folds the lane's task archive and
        the journal it records into the reviewed head before this classifier
        ever runs, so those paths were in every lane's diff and every lane
        classified `remote-review-required` — on a change no human and no
        product edit contributed. Seven publishing lanes of campaign
        fleet-0.71.63-20260829T025500Z and every lane of the campaigns before it
        failed for exactly these six paths.
        """

        classifier, root, base_commit, fleet = self.make_refresh(
            finalization={"slug": "08-29-refresh-to-1-2-3"}
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertTrue(result.eligible, result.reasons)
        self.assertEqual(result.classification, "integration-only")
        self.assertEqual(result.disallowed_paths, ())
        for path in (
            ".trellis/tasks/archive/2026-08/08-29-refresh-to-1-2-3/task.json",
            ".trellis/tasks/archive/2026-08/08-29-refresh-to-1-2-3/prd.md",
            ".trellis/workspace/sdelmas/index.md",
            ".trellis/workspace/sdelmas/journal-1.md",
        ):
            self.assertIn(path, result.changed_paths)
            self.assertIn(path, result.allowed_paths)

    def test_an_unrelated_trellis_edit_still_requires_remote_review(self) -> None:
        """The admission is the publisher's own output, not `.trellis/**`."""

        unrelated = ".trellis/tasks/08-30-someone-elses-work/prd.md"
        classifier, root, base_commit, fleet = self.make_refresh(
            finalization={"slug": "08-29-refresh-to-1-2-3"},
            extra_trellis={unrelated: "# smuggled\n"},
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertEqual(result.classification, "remote-review-required")
        self.assertEqual(result.disallowed_paths, (unrelated,))
        self.assertNotIn(unrelated, result.allowed_paths)

    def test_another_developers_journal_is_not_this_lanes_finalization(self) -> None:
        """The journal admitted is the one belonging to the archived task's
        assignee; a second developer's workspace has nothing vouching for it."""

        classifier, root, base_commit, fleet = self.make_refresh(
            finalization={"assignee": "sdelmas", "journal_owner": "someone-else"}
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertEqual(
            result.disallowed_paths,
            (
                ".trellis/workspace/someone-else/index.md",
                ".trellis/workspace/someone-else/journal-1.md",
            ),
        )

    def test_an_archived_task_from_another_branch_proves_nothing(self) -> None:
        """What makes the archive *this lane's* is that its record names this
        branch. An archive carried in from elsewhere is not evidence."""

        classifier, root, base_commit, fleet = self.make_refresh(
            finalization={"branch": "task/unrelated"}
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertIn("belongs to another branch", result.reasons[0])

    def test_an_incomplete_or_duplicated_archive_is_refused(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh(
            finalization={"status": "in_progress"}
        )
        result = self.classify(classifier, root, base_commit, fleet)
        self.assertFalse(result.eligible)
        self.assertIn("is not completed", result.reasons[0])

        classifier, root, base_commit, fleet = self.make_refresh(
            finalization={"slug": "08-29-refresh-to-1-2-3"},
            extra_trellis={
                ".trellis/tasks/archive/2026-08/08-29-a-second-task/task.json": "{}\n"
            },
        )
        result = self.classify(classifier, root, base_commit, fleet)
        self.assertFalse(result.eligible)
        self.assertIn("exactly one archived task directory", result.reasons[0])

    def test_a_workspace_change_with_no_archive_proves_nothing(self) -> None:
        classifier, root, base_commit, fleet = self.make_refresh(
            extra_trellis={".trellis/workspace/sdelmas/journal-1.md": "# journal\n"}
        )

        result = self.classify(classifier, root, base_commit, fleet)

        self.assertFalse(result.eligible)
        self.assertIn("exactly one archived task directory", result.reasons[0])


if __name__ == "__main__":
    unittest.main()
