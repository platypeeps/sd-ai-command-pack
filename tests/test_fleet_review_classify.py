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
                {
                    "schemaVersion": 3,
                    "consumers": [
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
                    ],
                },
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


if __name__ == "__main__":
    unittest.main()
