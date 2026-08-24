from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
json = _support.json
mock = _support.mock
os = _support.os
tempfile = _support.tempfile
Path = _support.Path
InstallTestCase = _support.InstallTestCase
PACK_ROOT = _support.PACK_ROOT


class ReviewControllerTests(InstallTestCase):
    SCRIPT = PACK_ROOT / "templates/scripts/sd-ai-command-pack-review.py"
    LOCAL_SCRIPT = (
        PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-local.py"
    )

    def load_controller(self):
        return self.load_module_from_path(
            self.SCRIPT,
            f"sd_ai_command_pack_review_{id(self)}",
        )

    def load_local_stage(self):
        return self.load_module_from_path(
            self.LOCAL_SCRIPT,
            f"sd_ai_command_pack_review_local_config_{id(self)}",
        )

    def make_repo(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="sd-review-controller-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        root.mkdir()
        self.run_git(root, "init", "--initial-branch=main")
        self.run_git(root, "config", "user.name", "Review Controller Test")
        self.run_git(root, "config", "user.email", "review@example.com")
        (root / "README.md").write_text("# fixture\n", encoding="utf-8")
        self.run_git(root, "add", "README.md")
        self.run_git(root, "commit", "-m", "seed")
        self.run_git(root, "switch", "-c", "feature")
        return root

    def artifact_root(self, repo: Path) -> Path:
        root = repo.parent / "artifacts"
        root.mkdir(mode=0o700, exist_ok=True)
        os.chmod(root, 0o700)
        return root

    @staticmethod
    def pr(controller, repo: Path) -> dict[str, object]:
        return {
            "number": 42,
            "head": controller._git(repo, "rev-parse", "HEAD"),
            "headRefName": "feature",
            "baseRefName": "main",
            "base": "origin/main",
            "url": "https://github.com/platypeeps/example/pull/42",
            "draft": False,
            "repository": {"owner": "platypeeps", "name": "example"},
        }

    @staticmethod
    def local_report(
        controller,
        pr: dict[str, object],
        *,
        status: str = "clean",
        cost: str = "low",
        quality: str = "standard",
    ) -> dict[str, object]:
        receipt = {
            "schemaVersion": 1,
            "receiptId": "local-receipt",
            "target": {
                "head": pr["head"],
                "contentDigest": "1" * 64,
            },
            "plan": {
                "configurationDigest": "2" * 64,
                "policyId": "first-substantive-head",
            },
            "outcome": status,
            "attempts": [
                {
                    "provider": {
                        "id": "prism",
                        "costTier": cost,
                        "qualityTier": quality,
                    },
                    "durationMs": 12,
                }
            ],
            "findings": [],
        }
        return {
            "schemaVersion": 1,
            "status": status,
            "receipt": receipt,
        }

    @staticmethod
    def capability() -> dict[str, object]:
        return {
            "state": "ready",
            "reason": "compatible-enabled-workflow",
            "workflow": {
                "path": ".github/workflows/sd-review.yml",
                "name": "SD routed review",
            },
            "checkName": "sd-github-review/receipt",
            "actionReference": (
                "platypeeps/sd-github-review@"
                "8636a3983d18de17c49907a4c48170a61b1bb713"
            ),
        }

    @staticmethod
    def none_receipt(request: dict[str, object]) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "receiptId": "receipt-none",
            "logicalDispatchId": request["logicalDispatchId"],
            "requestFingerprint": request["requestFingerprint"],
            "repository": request["repository"],
            "pullRequestNumber": request["pullRequestNumber"],
            "headSha": request["headSha"],
            "attempt": request["attempt"],
            "selectedRoute": "none",
            "backend": None,
            "reason": "policy selected none",
            "policyVersion": request["policyVersion"],
            "dispatch": {
                "status": "skipped",
                "phase": "not-started",
                "idempotencyKey": request["logicalDispatchId"],
                "completedAt": "2026-07-25T00:00:00Z",
            },
            "correlationIds": [request["correlationId"]],
        }

    @staticmethod
    def routed_receipt(
        request: dict[str, object],
        *,
        phase: str,
        status: str = "requested",
    ) -> dict[str, object]:
        """A routed receipt at one point in the lane's two-write sequence.

        The lane publishes the receipt when its route step begins, carrying
        `phase: "started"`, and rewrites it seconds later with the terminal
        phase and a `completedAt`. A fixture that only ever produces the second
        write cannot exercise the window the poller actually lands in.
        """

        dispatch: dict[str, object] = {
            "status": status,
            "phase": phase,
            "idempotencyKey": request["logicalDispatchId"],
            "startedAt": "2026-07-25T00:00:00Z",
            "workflowUrl": (
                "https://github.com/platypeeps/example/actions/runs/1"
            ),
        }
        if phase != "started":
            dispatch["completedAt"] = "2026-07-25T00:00:04Z"
        return {
            "schemaVersion": 1,
            "receiptId": "receipt-copilot",
            "logicalDispatchId": request["logicalDispatchId"],
            "requestFingerprint": request["requestFingerprint"],
            "repository": request["repository"],
            "pullRequestNumber": request["pullRequestNumber"],
            "headSha": request["headSha"],
            "attempt": request["attempt"],
            "selectedRoute": "copilot",
            "backend": {
                "id": "github-copilot",
                "kind": "copilot",
                "label": "GitHub Copilot",
                "costTier": "medium",
                "qualityTier": "advanced",
                "capabilities": ["inline-comments", "review"],
                "findingChannels": ["inline-comment", "review"],
                "reviewAuthors": ["copilot-pull-request-reviewer[bot]"],
                "checkNames": [],
                "limitations": ["GitHub-managed model selection"],
                "supportsRerequest": True,
            },
            "reason": "review floor required copilot",
            "policyVersion": request["policyVersion"],
            "dispatch": dispatch,
            "correlationIds": [request["correlationId"]],
        }

    def write_descriptor(
        self,
        root: Path,
        *,
        schema_version: object = 1,
        contract: object = 1,
        check_name: str = "sd-github-review/receipt",
    ) -> Path:
        path = root / "config/routed-review-setup-v1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": schema_version,
                    "integrationId": "sd-github-review",
                    "workflow": {
                        "name": "SD routed review",
                        "path": ".github/workflows/sd-review.yml",
                    },
                    "contractMajor": contract,
                    "supportedIntents": [
                        "auto",
                        "cheap",
                        "deep",
                        "copilot",
                        "none",
                    ],
                    "supportedOperations": ["route", "finalize", "query"],
                    "durableReceipt": {
                        "supported": True,
                        "checkName": check_name,
                    },
                    "actionReference": (
                        "platypeeps/sd-github-review@"
                        "8636a3983d18de17c49907a4c48170a61b1bb713"
                    ),
                    "noninteractive": True,
                    "checkoutRequired": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_configuration_is_shared_strict_and_path_safe(self) -> None:
        controller = self.load_controller()
        local_stage = self.load_local_stage()
        root = self.make_repo()
        default, remote = controller.load_review_configuration(root)
        self.assertEqual(remote["requirement"], "optional")
        self.assertEqual(len(default["providers"]), 2)
        local_default, _providers, _policy = local_stage.load_config(root)
        self.assertEqual(default, local_default)
        self.assertEqual(
            controller._configuration_digest(default),
            local_stage._digest(local_default),
        )

        path = root / ".sd-ai-command-pack/review.json"
        path.parent.mkdir(parents=True)
        config = default | {
            "providers": [
                default["providers"][0]
                | {"version": "prism-r\u00e9view-v1"},
                default["providers"][1],
            ],
            "remoteIntegration": {
                "requirement": "required",
                "descriptorPath": "config/custom-review.json",
                "receiptPolls": 2,
                "pollSeconds": 0,
                "roundLimit": 3,
            }
        }
        path.write_text(json.dumps(config), encoding="utf-8")
        normalized, parsed = controller.load_review_configuration(root)
        self.assertEqual(parsed["requirement"], "required")
        self.assertEqual(normalized["remoteIntegration"], parsed)
        local_config, _providers, _policy = local_stage.load_config(root)
        self.assertEqual(local_config, normalized)
        self.assertEqual(
            controller._configuration_digest(normalized),
            local_stage._digest(local_config),
        )

        config["remoteIntegration"]["descriptorPath"] = "../escape.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(controller.ReviewError, "stay inside"):
            controller.load_review_configuration(root)
        with self.assertRaisesRegex(local_stage.ReviewInputError, "stay inside"):
            local_stage.load_config(root)

        config["schemaVersion"] = True
        config["remoteIntegration"]["descriptorPath"] = "config/custom-review.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(controller.ReviewError, "schemaVersion"):
            controller.load_review_configuration(root)

    def test_json_path_and_bound_helpers_fail_closed(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        path = root / "value.json"
        path.write_text("{bad", encoding="utf-8")
        with self.assertRaisesRegex(controller.ReviewError, "cannot read"):
            controller._read_json(path, limit=100, label="fixture")
        path.write_text('"oversized"', encoding="utf-8")
        with self.assertRaisesRegex(controller.ReviewError, "exceeds"):
            controller._read_json(path, limit=2, label="fixture")
        with self.assertRaisesRegex(controller.ReviewError, "bounded relative"):
            controller._safe_relative_path("", field="fixture")
        with self.assertRaisesRegex(controller.ReviewError, "stay inside"):
            controller._safe_relative_path("/absolute", field="fixture")
        with self.assertRaisesRegex(controller.ReviewError, "must be an integer"):
            controller._bounded_integer(
                True,
                field="fixture",
                minimum=1,
                maximum=2,
            )
        with self.assertRaisesRegex(controller.ReviewError, "between"):
            controller._bounded_integer(
                3,
                field="fixture",
                minimum=1,
                maximum=2,
            )
        self.assertTrue(controller._bounded("x" * 2_000).endswith("..."))

    def test_worktree_digest_and_state_identity_bind_untracked_bytes(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        first = controller._worktree_digest(root)
        (root / "new.txt").write_bytes(b"x" * (1024 * 1024 + 1))
        with mock.patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("untracked files must be hashed incrementally"),
        ), mock.patch.object(
            controller,
            "_digest",
            wraps=controller._digest,
        ) as digest:
            second = controller._worktree_digest(root)
        digest_input = digest.call_args.args[0]
        self.assertNotIn("trackedDiff", digest_input)
        self.assertRegex(digest_input["trackedDiffDigest"], r"[0-9a-f]{64}\Z")
        (root / "new.txt").write_text("second\n", encoding="utf-8")
        third = controller._worktree_digest(root)
        self.assertEqual(len({first, second, third}), 3)

        identity = controller._state_identity(
            repo=root,
            scope="changes",
            controls={"local": "auto"},
            pr=None,
            base="origin/main",
            worktree_digest=third,
        )
        attempt = controller._attempt_id(identity, None)
        state_path = self.artifact_root(root) / "state.json"
        state = controller._load_or_create_state(
            state_path,
            attempt_id=attempt,
            identity=identity,
        )
        controller._advance(state_path, state, "check", check={"status": "passed"})
        resumed = controller._load_or_create_state(
            state_path,
            attempt_id=attempt,
            identity=identity,
        )
        self.assertEqual(resumed["phase"], "check")
        with self.assertRaisesRegex(controller.ReviewError, "conflicts"):
            controller._load_or_create_state(
                state_path,
                attempt_id=attempt,
                identity={**identity, "worktreeDigest": "0" * 64},
            )

    def test_scope_resolution_is_deterministic(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        with mock.patch.object(controller, "_is_dirty", return_value=True):
            self.assertEqual(controller.resolve_scope(root, "auto", None), ("changes", None))
        with mock.patch.object(controller, "_is_dirty", return_value=False), mock.patch.object(
            controller, "_discover_branch_pr", return_value=42
        ):
            self.assertEqual(controller.resolve_scope(root, "auto", None), ("pr", 42))
        with self.assertRaisesRegex(controller.ReviewError, "requires"):
            with mock.patch.object(controller, "_discover_branch_pr", return_value=None):
                controller.resolve_scope(root, "pr", None)
        with self.assertRaisesRegex(controller.ReviewError, "cannot be combined"):
            controller.resolve_scope(root, "codebase", 42)

    def test_pr_and_repository_evidence_require_exact_live_head(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        head = self.git_output(root, "rev-parse", "HEAD")
        pr_value = {
            "number": 42,
            "headRefOid": head,
            "headRefName": "feature",
            "baseRefName": "main",
            "state": "OPEN",
            "isDraft": False,
            "url": "https://github.com/platypeeps/example/pull/42",
        }

        def evidence(args, **_kwargs):
            return (
                {"nameWithOwner": "platypeeps/example"}
                if args[:2] == ["repo", "view"]
                else pr_value
            )

        with mock.patch.object(controller, "_gh_json", side_effect=evidence):
            self.assertEqual(controller._pr_evidence(root, 42)["head"], head)
        with mock.patch.object(controller, "_gh_json", return_value={"bad": True}):
            with self.assertRaisesRegex(controller.ReviewError, "does not match"):
                controller._pr_evidence(root, 42)
        with mock.patch.object(
            controller,
            "_gh_json",
            return_value={**pr_value, "headRefOid": "a" * 40},
        ):
            with self.assertRaisesRegex(controller.ReviewError, "local HEAD"):
                controller._pr_evidence(root, 42)

    def test_router_summary_maps_local_tiers_and_never_grants_failure_confidence(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        report = self.local_report(
            controller,
            pr,
            cost="none",
            quality="deep",
        )
        summary = controller._router_local_summary(
            report,
            repository=pr["repository"],
            pr_number=42,
            head=pr["head"],
        )
        self.assertEqual(summary["providers"][0]["costTier"], "free")
        self.assertEqual(summary["providers"][0]["qualityTier"], "advanced")
        self.assertEqual(summary["confidence"], 90)

        failed = self.local_report(controller, pr, status="failed")
        failed_summary = controller._router_local_summary(
            failed,
            repository=pr["repository"],
            pr_number=42,
            head=pr["head"],
        )
        self.assertEqual(failed_summary["confidence"], 0)
        failed["receipt"]["findings"] = [
            {"disposition": "outstanding"},
            {"disposition": "fix"},
            {"disposition": "fixed"},
            {"disposition": "rebutted"},
            {"disposition": "resolved"},
        ]
        disposition_summary = controller._router_local_summary(
            failed,
            repository=pr["repository"],
            pr_number=42,
            head=pr["head"],
        )
        self.assertEqual(
            disposition_summary["dispositionCounts"],
            {"total": 5, "unresolved": 2, "fixed": 1, "rebutted": 2},
        )

        skipped = self.local_report(controller, pr, status="skipped")
        skipped["receipt"]["attempts"] = []
        skipped["receipt"]["plan"]["policyId"] = "bookkeeping-successor"
        skipped_summary = controller._router_local_summary(
            skipped,
            repository=pr["repository"],
            pr_number=42,
            head=pr["head"],
        )
        self.assertEqual(skipped_summary["skipReason"], "bookkeeping-successor")
        self.assertEqual(skipped_summary["confidence"], 0)

    def test_request_identity_excludes_correlation_but_receipt_requires_it(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        with mock.patch.object(controller.uuid, "uuid4") as uuid4:
            uuid4.return_value.hex = "a" * 32
            first = controller._remote_request(
                repository=pr["repository"],
                pr=pr,
                route="auto",
                attempt=1,
                local_summary=None,
                policy_reference=self.capability()["actionReference"],
            )
            uuid4.return_value.hex = "b" * 32
            second = controller._remote_request(
                repository=pr["repository"],
                pr=pr,
                route="auto",
                attempt=1,
                local_summary=None,
                policy_reference=self.capability()["actionReference"],
            )
        self.assertEqual(first["logicalDispatchId"], second["logicalDispatchId"])
        self.assertEqual(first["requestFingerprint"], second["requestFingerprint"])
        self.assertNotEqual(first["correlationId"], second["correlationId"])

        receipt = self.none_receipt(first)
        check = {
            "name": "sd-github-review/receipt",
            "head_sha": first["headSha"],
            "external_id": first["logicalDispatchId"],
            "output": {
                "text": controller.RECEIPT_MARKER + controller._canonical_text(receipt)
            },
        }
        decoded = controller._decode_receipt_check(
            check,
            check_name="sd-github-review/receipt",
            request=first,
        )
        self.assertEqual(decoded, receipt)
        for field in ("schemaVersion", "pullRequestNumber", "attempt"):
            invalid = receipt | {field: True}
            check["output"] = {
                "text": controller.RECEIPT_MARKER
                + controller._canonical_text(invalid)
            }
            with self.assertRaisesRegex(controller.ReviewError, field):
                controller._decode_receipt_check(
                    check,
                    check_name="sd-github-review/receipt",
                    request=first,
                )
        check["output"] = {
            "text": controller.RECEIPT_MARKER
            + controller._canonical_text(receipt)
        }
        observed = receipt | {
            "observations": {
                "latencyMs": controller.MAX_REMOTE_LATENCY_MS,
                "costTier": "low",
            }
        }
        check["output"] = {
            "text": controller.RECEIPT_MARKER
            + controller._canonical_text(observed)
        }
        self.assertEqual(
            controller._decode_receipt_check(
                check,
                check_name="sd-github-review/receipt",
                request=first,
            )["observations"]["latencyMs"],
            controller.MAX_REMOTE_LATENCY_MS,
        )
        for latency in (True, -1, controller.MAX_REMOTE_LATENCY_MS + 1, "1"):
            invalid = receipt | {
                "observations": {"latencyMs": latency, "costTier": "low"}
            }
            check["output"] = {
                "text": controller.RECEIPT_MARKER
                + controller._canonical_text(invalid)
            }
            with self.assertRaisesRegex(controller.ReviewError, "latencyMs"):
                controller._decode_receipt_check(
                    check,
                    check_name="sd-github-review/receipt",
                    request=first,
                )
        check["output"] = {
            "text": controller.RECEIPT_MARKER
            + controller._canonical_text(receipt)
        }
        check["external_id"] = "0" * 64
        with self.assertRaisesRegex(controller.ReviewError, "external_id"):
            controller._decode_receipt_check(
                check,
                check_name="sd-github-review/receipt",
                request=first,
            )

    def test_capability_distinguishes_absent_incompatible_and_ready(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        remote = {
            "descriptorPath": "config/routed-review-setup-v1.json",
        }
        repository = {"owner": "platypeeps", "name": "example"}
        self.assertEqual(
            controller._capability(
                root,
                remote=remote,
                repository=repository,
                intent="auto",
            )["state"],
            "absent",
        )
        self.write_descriptor(root, contract=2)
        self.assertEqual(
            controller._capability(
                root,
                remote=remote,
                repository=repository,
                intent="auto",
            )["state"],
            "incompatible",
        )
        for field in ("schemaVersion", "contractMajor"):
            self.write_descriptor(
                root,
                schema_version=True if field == "schemaVersion" else 1,
                contract=True if field == "contractMajor" else 1,
            )
            self.assertEqual(
                controller._capability(
                    root,
                    remote=remote,
                    repository=repository,
                    intent="auto",
                )["state"],
                "incompatible",
            )
        descriptor = self.write_descriptor(root)
        descriptor.write_text("{\n", encoding="utf-8")
        malformed = controller._capability(
            root,
            remote=remote,
            repository=repository,
            intent="auto",
        )
        self.assertEqual(malformed["state"], "invalid")
        self.assertIn("cannot read routed-review setup descriptor", malformed["reason"])
        self.write_descriptor(root, check_name="custom/receipt")
        incompatible = controller._capability(
            root,
            remote=remote,
            repository=repository,
            intent="auto",
        )
        self.assertEqual(incompatible["state"], "incompatible")
        self.assertEqual(incompatible["reason"], "unsupported-receipt-check-name")
        self.write_descriptor(root)
        metadata = {
            "state": "active",
            "path": ".github/workflows/sd-review.yml",
            "name": "SD routed review",
        }
        with mock.patch.object(controller, "_gh_json", return_value=metadata):
            capability = controller._capability(
                root,
                remote=remote,
                repository=repository,
                intent="auto",
            )
        self.assertEqual(capability["state"], "ready")
        with mock.patch.object(
            controller,
            "_gh_json",
            side_effect=controller.CommandError("offline"),
        ):
            unavailable = controller._capability(
                root,
                remote=remote,
                repository=repository,
                intent="auto",
            )
        self.assertEqual(unavailable["state"], "unavailable")

    def test_subprocess_composition_and_dispatch_use_argv(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        scripts = root / "scripts"
        scripts.mkdir()
        for name in (
            "sd-ai-command-pack-check.py",
            "sd-ai-command-pack-review-local.py",
        ):
            (scripts / name).write_text("# fixture\n", encoding="utf-8")
        args = controller.parse_args(
            [
                "--repo",
                str(root),
                "--scope",
                "branch",
                "--attempt-id",
                "attempt-1",
                "--finding-family",
                "boundary-validation",
                "--json",
            ]
        )
        captured: list[list[str]] = []

        def json_process(command, **_kwargs):
            captured.append(command)
            command_name = Path(command[1]).name
            if command_name.endswith("check.py"):
                return 0, {"schemaVersion": 1, "status": "passed"}
            return 0, {"schemaVersion": 1, "status": "clean"}

        with mock.patch.object(controller, "_json_process", side_effect=json_process):
            self.assertEqual(controller._run_check(root)["status"], "passed")
            controller._run_local(
                root,
                scope="branch",
                base="origin/main",
                head="HEAD",
                attempt_id="attempt-1",
                args=args,
                local_policy="optional",
            )
        self.assertIn("--finding-family", captured[1])
        self.assertNotIn("bash", captured[1])
        # The coordinator must never forward its private artifact root: the
        # local stage requires an in-repo, git-ignored root and owns that
        # default itself. This assertion pins the intentional removal.
        self.assertNotIn("--artifact-root", captured[1])

        request = {"value": "literal"}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(
            controller,
            "_default_branch",
            return_value="main",
        ), mock.patch.object(controller, "run_gh", return_value=completed) as run_gh:
            controller._dispatch(
                root,
                workflow=".github/workflows/sd-review.yml",
                request=request,
            )
        argv = run_gh.call_args.args[0]
        self.assertEqual(argv[:3], ["workflow", "run", ".github/workflows/sd-review.yml"])
        self.assertIn('review-request={"value":"literal"}', argv)
        failed = mock.Mock(returncode=1, stdout="", stderr="failed")
        with mock.patch.object(
            controller,
            "_default_branch",
            return_value="main",
        ), mock.patch.object(controller, "run_gh", return_value=failed):
            with self.assertRaisesRegex(controller.CommandError, "uncertain"):
                controller._dispatch(
                    root,
                    workflow=".github/workflows/sd-review.yml",
                    request=request,
                )

    def test_default_branch_uses_symbolic_or_unambiguous_remote_ref(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        head = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(root, "update-ref", "refs/remotes/origin/main", head)
        self.assertEqual(controller._default_branch(root), "main")

        self.run_git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.assertEqual(controller._default_branch(root), "main")

        ambiguous = self.make_repo()
        ambiguous_head = self.git_output(ambiguous, "rev-parse", "HEAD")
        self.run_git(ambiguous, "update-ref", "refs/remotes/origin/main", ambiguous_head)
        self.run_git(ambiguous, "update-ref", "refs/remotes/origin/master", ambiguous_head)
        with self.assertRaisesRegex(controller.ReviewError, "default branch"):
            controller._default_branch(ambiguous)

        missing = self.make_repo()
        with self.assertRaisesRegex(controller.ReviewError, "default branch"):
            controller._default_branch(missing)

    def test_json_command_and_github_boundaries_preserve_typed_failures(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        helper = root / "json-helper.py"
        helper.write_text('print("{\\\"status\\\": \\\"ok\\\"}")\n', encoding="utf-8")
        code, payload = controller._json_process(
            [controller.sys.executable, str(helper)],
            repo=root,
            context="run JSON fixture",
            timeout=10,
        )
        self.assertEqual((code, payload["status"]), (0, "ok"))
        helper.write_text('print("not-json")\n', encoding="utf-8")
        with self.assertRaisesRegex(controller.ReviewError, "did not return JSON"):
            controller._json_process(
                [controller.sys.executable, str(helper)],
                repo=root,
                context="run malformed fixture",
                timeout=10,
            )

        success = mock.Mock(returncode=0, stdout='{"ok": true}', stderr="")
        with mock.patch.object(controller, "run_gh", return_value=success):
            self.assertEqual(
                controller._gh_json(["api", "fixture"], repo=root, context="query"),
                {"ok": True},
            )
        failure = mock.Mock(returncode=1, stdout="", stderr="offline")
        with mock.patch.object(controller, "run_gh", return_value=failure):
            with self.assertRaisesRegex(controller.CommandError, "failed to query"):
                controller._gh_json(["api", "fixture"], repo=root, context="query")

    def test_receipt_query_is_exact_and_rejects_duplicates(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        request = controller._remote_request(
            repository=pr["repository"],
            pr=pr,
            route="auto",
            attempt=1,
            local_summary=None,
            policy_reference=self.capability()["actionReference"],
        )
        raw = {
            "external_id": request["logicalDispatchId"],
            "name": "sd-github-review/receipt",
        }
        receipt = self.none_receipt(request)
        with mock.patch.object(
            controller,
            "_gh_json",
            return_value={"check_runs": [raw]},
        ), mock.patch.object(
            controller,
            "_decode_receipt_check",
            return_value=receipt,
        ) as decode:
            result = controller._query_receipt(
                root,
                repository=pr["repository"],
                check_name="sd-github-review/receipt",
                request=request,
            )
        self.assertEqual(result, receipt)
        decode.assert_called_once()

        with mock.patch.object(
            controller,
            "_gh_json",
            return_value={"check_runs": [raw, raw]},
        ), mock.patch.object(
            controller,
            "_decode_receipt_check",
            return_value=receipt,
        ):
            with self.assertRaisesRegex(controller.ReviewError, "multiple"):
                controller._query_receipt(
                    root,
                    repository=pr["repository"],
                    check_name="sd-github-review/receipt",
                    request=request,
                )
        with mock.patch.object(controller, "_gh_json", return_value=[]):
            with self.assertRaisesRegex(controller.ReviewError, "invalid payload"):
                controller._query_receipt(
                    root,
                    repository=pr["repository"],
                    check_name="sd-github-review/receipt",
                    request=request,
                )

    def test_observation_collects_declared_conversation_and_check_channels(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        receipt = {
            "selectedRoute": "cheap",
            "backend": {
                "reviewAuthors": ["review-bot[bot]"],
                "checkNames": ["review/findings"],
                "findingChannels": ["conversation-comment", "check"],
            },
            "dispatch": {"status": "requested", "phase": "acknowledged"},
        }
        issue_comments = [
            [
                {
                    "id": 7,
                    "html_url": "https://example.test/comment/7",
                    "body": "Please add a boundary test",
                    "user": {"login": "review-bot[bot]"},
                }
            ]
        ]
        checks = [
            {
                "name": "review/findings",
                "bucket": "pass",
                "state": "SUCCESS",
            }
        ]

        def fake_gh(_args, *, context, **_kwargs):
            if context == "collect pull request conversation comments":
                return issue_comments
            if context == "collect pull request checks":
                return checks
            self.fail(f"unexpected GitHub context: {context}")

        with mock.patch.object(controller, "_gh_json", side_effect=fake_gh):
            observation = controller._collect_observation(
                root,
                pr=pr,
                receipt=receipt,
                receipt_check_name="sd-github-review/receipt",
            )
        self.assertEqual(observation["status"], "findings")
        self.assertTrue(observation["materialized"])
        self.assertEqual(len(observation["conversationComments"]), 1)

    def test_nested_thread_pagination_preserves_unresolved_findings(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        receipt = {
            "selectedRoute": "copilot",
            "backend": {
                "reviewAuthors": ["review-bot[bot]"],
                "checkNames": [],
                "findingChannels": ["inline-comment"],
            },
            "dispatch": {"status": "requested", "phase": "observed"},
        }
        thread_payload = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    {
                                        "id": "thread-1",
                                        "isResolved": False,
                                        "isOutdated": False,
                                        "comments": {
                                            "nodes": [],
                                            "pageInfo": {"hasNextPage": True},
                                        },
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        ]
        nested = [
            {
                "data": {
                    "node": {
                        "comments": {
                            "nodes": [
                                {
                                    "id": "comment-1",
                                    "body": "Fix the exact-head guard",
                                    "author": {"login": "review-bot[bot]"},
                                }
                            ]
                        }
                    }
                }
            }
        ]

        def fake_gh(args, *, context, **_kwargs):
            if context == "collect paginated review threads":
                query = next(item for item in args if item.startswith("query="))
                self.assertIn("$endCursor:String", query)
                self.assertIn("after:$endCursor", query)
                self.assertNotIn("$cursor", query)
                return thread_payload
            if context == "collect paginated review-thread comments":
                query = next(item for item in args if item.startswith("query="))
                self.assertIn("$endCursor:String", query)
                self.assertIn("after:$endCursor", query)
                self.assertNotIn("$cursor", query)
                return nested
            if context == "collect pull request checks":
                return []
            self.fail(f"unexpected GitHub context: {context}")

        with mock.patch.object(controller, "_gh_json", side_effect=fake_gh):
            observation = controller._collect_observation(
                root,
                pr=pr,
                receipt=receipt,
                receipt_check_name="sd-github-review/receipt",
            )
        self.assertEqual(observation["status"], "findings")
        self.assertEqual(observation["reviewThreads"]["unresolved"], 1)

    def test_undeclared_inline_threads_do_not_become_findings(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        receipt = {
            "selectedRoute": "none",
            "backend": None,
            "dispatch": {"status": "skipped", "phase": "not-started"},
        }

        def fake_gh(_args, *, context, **_kwargs):
            if context == "collect pull request checks":
                return []
            self.fail(f"unexpected GitHub context: {context}")

        with mock.patch.object(controller, "_gh_json", side_effect=fake_gh):
            observation = controller._collect_observation(
                root,
                pr=pr,
                receipt=receipt,
                receipt_check_name="sd-github-review/receipt",
            )
        self.assertEqual(observation["status"], "clean")
        self.assertEqual(observation["reviewThreads"]["unresolved"], 0)

    def test_review_thread_pagination_rejects_more_than_one_thousand_rows(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        receipt = {
            "selectedRoute": "none",
            "backend": {
                "reviewAuthors": [],
                "checkNames": [],
                "findingChannels": ["inline-comment"],
            },
            "dispatch": {"status": "skipped", "phase": "not-started"},
        }
        rows = [
            {
                "id": f"thread-{index}",
                "isResolved": True,
                "isOutdated": False,
                "comments": {"nodes": [], "pageInfo": {"hasNextPage": False}},
            }
            for index in range(1_001)
        ]
        thread_payload = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {"reviewThreads": {"nodes": rows}}
                    }
                }
            }
        ]

        with mock.patch.object(
            controller,
            "_gh_json",
            return_value=thread_payload,
        ):
            with self.assertRaisesRegex(
                controller.ReviewError,
                "review threads exceed 1000 rows",
            ):
                controller._collect_observation(
                    root,
                    pr=pr,
                    receipt=receipt,
                    receipt_check_name="sd-github-review/receipt",
                )

    def test_remote_rebuttal_disposition_clears_only_matching_stable_id(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        receipt = {
            "selectedRoute": "cheap",
            "backend": {
                "reviewAuthors": ["review-bot[bot]"],
                "checkNames": [],
                "findingChannels": ["conversation-comment"],
            },
            "dispatch": {"status": "requested", "phase": "acknowledged"},
        }
        comments = [
            [
                {
                    "id": 7,
                    "body": "This is incorrect",
                    "user": {"login": "review-bot[bot]"},
                }
            ]
        ]

        def fake_gh(_args, *, context, **_kwargs):
            if context == "collect pull request conversation comments":
                return comments
            if context == "collect pull request checks":
                return []
            self.fail(f"unexpected GitHub context: {context}")

        with mock.patch.object(controller, "_gh_json", side_effect=fake_gh):
            finding = controller._collect_observation(
                root,
                pr=pr,
                receipt=receipt,
                receipt_check_name="sd-github-review/receipt",
            )
            settled = controller._collect_observation(
                root,
                pr=pr,
                receipt=receipt,
                receipt_check_name="sd-github-review/receipt",
                dispositions={"7": "rebutted"},
            )
        self.assertEqual(finding["status"], "findings")
        self.assertEqual(settled["status"], "clean")
        self.assertEqual(settled["dispositions"], {"7": "rebutted"})
        with self.assertRaisesRegex(controller.ReviewError, "stable-id"):
            controller._parse_remote_dispositions(["7=fixed"])

    def test_successful_dispatch_without_declared_channel_is_pending(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        receipt = {
            "selectedRoute": "copilot",
            "backend": {
                "reviewAuthors": ["copilot-pull-request-reviewer[bot]"],
                "checkNames": [],
                "findingChannels": ["review", "inline-comment"],
            },
            "dispatch": {"status": "requested", "phase": "observed"},
        }
        thread_payload = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {"reviewThreads": {"nodes": []}}
                    }
                }
            }
        ]

        def fake_gh(_args, *, context, **_kwargs):
            if context == "collect paginated review threads":
                return thread_payload
            if context == "collect pull request reviews":
                return [[]]
            if context == "collect pull request checks":
                return []
            self.fail(f"unexpected GitHub context: {context}")

        with mock.patch.object(controller, "_gh_json", side_effect=fake_gh):
            observation = controller._collect_observation(
                root,
                pr=pr,
                receipt=receipt,
                receipt_check_name="sd-github-review/receipt",
            )
        self.assertEqual(observation["status"], "pending")
        self.assertFalse(observation["materialized"])

    def run_with_mocks(
        self,
        controller,
        root: Path,
        *,
        scope: str,
        local_status: str = "clean",
        local_diagnostic: str | None = None,
        capability: dict[str, object] | None = None,
        remote: str = "auto",
        receipt: dict[str, object] | None = None,
        observation: dict[str, object] | None = None,
        check_status: str = "passed",
        local_receipt_extra: dict[str, object] | None = None,
    ):
        pr = self.pr(controller, root) if scope == "pr" else None
        args = controller.parse_args(
            [
                "--repo",
                str(root),
                "--scope",
                scope,
                "--remote",
                remote,
                "--artifact-root",
                str(self.artifact_root(root)),
                "--json",
                *(["--pr-number", "42"] if scope == "pr" else []),
            ]
        )
        local = self.local_report(
            controller,
            pr
            or {
                "head": controller._git(root, "rev-parse", "HEAD"),
                "repository": {"owner": "platypeeps", "name": "example"},
            },
            status=local_status,
        )
        if local_diagnostic is not None:
            local["diagnostic"] = local_diagnostic
        if local_receipt_extra is not None:
            local["receipt"].update(local_receipt_extra)
        patches = [
            mock.patch.object(
                controller,
                "_run_check",
                return_value={"schemaVersion": 1, "status": check_status},
            ),
            mock.patch.object(controller, "_run_local", return_value=local),
        ]
        if pr is not None:
            patches.extend(
                [
                    mock.patch.object(controller, "_pr_evidence", return_value=pr),
                    mock.patch.object(
                        controller,
                        "_capability",
                        return_value=capability or self.capability(),
                    ),
                    mock.patch.object(controller, "_query_receipt", return_value=receipt),
                    mock.patch.object(controller, "_dispatch"),
                    mock.patch.object(
                        controller,
                        "_collect_observation",
                        return_value=observation
                        or {
                            "status": "clean",
                            "materialized": True,
                            "reviewThreads": {"total": 0, "unresolved": 0, "items": []},
                            "conversationComments": [],
                            "reviews": [],
                            "checks": {"total": 0, "blocking": [], "backend": []},
                        },
                    ),
                ]
            )
        with patches[0], patches[1], mock.patch.object(
            controller,
            "_default_branch",
            return_value="main",
        ):
            if len(patches) == 2:
                return controller.run(args), None
            with patches[2], patches[3], patches[4] as query, patches[5] as dispatch, patches[6]:
                if receipt is None:
                    calls = 0

                    def routed_receipt(*_args, **kwargs):
                        nonlocal calls
                        calls += 1
                        if calls == 1:
                            return None
                        return self.none_receipt(kwargs["request"])

                    query.side_effect = routed_receipt
                return controller.run(args), dispatch

    def test_run_composes_non_pr_local_and_optional_absence(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        (code, report), _dispatch = self.run_with_mocks(
            controller,
            root,
            scope="branch",
            remote="none",
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "ready")

        absent = {"state": "absent", "reason": "setup-descriptor-absent"}
        (code, report), _dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            local_status="skipped",
            capability=absent,
        )
        self.assertEqual(code, 3)
        self.assertEqual(report["status"], "indeterminate")
        self.assertIn("clean local review", report["diagnostic"] or "")

    def test_branch_scope_derives_unconfigured_base_from_origin_head(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        head = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(root, "update-ref", "refs/remotes/origin/master", head)
        args = controller.parse_args(
            [
                "--repo",
                str(root),
                "--scope",
                "branch",
                "--remote",
                "none",
                "--artifact-root",
                str(self.artifact_root(root)),
                "--json",
            ]
        )
        local = self.local_report(
            controller,
            {
                "head": head,
                "repository": {"owner": "platypeeps", "name": "example"},
            },
        )
        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            return_value=local,
        ) as run_local:
            code, report = controller.run(args)
        self.assertEqual((code, report["status"]), (0, "ready"))
        self.assertEqual(run_local.call_args.kwargs["base"], "origin/master")

    def test_run_blocks_local_failure_before_remote_dispatch(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            local_status="unavailable",
        )
        self.assertEqual(code, 3)
        self.assertEqual(report["status"], "failed")
        dispatch.assert_not_called()

    def test_run_early_gate_and_capability_outcomes(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            check_status="failed",
        )
        self.assertEqual((code, report["status"]), (1, "blocked"))
        dispatch.assert_not_called()

        root = self.make_repo()
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            local_status="findings",
        )
        self.assertEqual((code, report["status"]), (1, "findings"))
        dispatch.assert_not_called()

        root = self.make_repo()
        blocked_diagnostic = (
            "an approved review.round-extension decision is required"
        )
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            local_status="blocked",
            local_diagnostic=blocked_diagnostic,
        )
        self.assertEqual((code, report["status"]), (1, "blocked"))
        self.assertEqual(report["diagnostic"], blocked_diagnostic)
        self.assertEqual(report["limitations"], ["local-policy-blocked"])
        dispatch.assert_not_called()

        root = self.make_repo()
        invalid_diagnostic = "review configuration policy is invalid"
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            local_status="invalid",
            local_diagnostic=invalid_diagnostic,
        )
        self.assertEqual((code, report["status"]), (2, "invalid"))
        self.assertEqual(report["diagnostic"], invalid_diagnostic)
        self.assertEqual(report["limitations"], ["local-invalid"])
        dispatch.assert_not_called()

        root = self.make_repo()
        invalid = {"state": "invalid", "reason": "bad descriptor"}
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            capability=invalid,
        )
        self.assertEqual((code, report["status"]), (3, "indeterminate"))
        dispatch.assert_not_called()

        root = self.make_repo()
        absent = {"state": "absent", "reason": "not configured"}
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            capability=absent,
            remote="cheap",
        )
        self.assertEqual((code, report["status"]), (1, "blocked"))
        dispatch.assert_not_called()

    def test_local_disposition_rerun_reaches_the_stage_and_records_rebuttals(
        self,
    ) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        head = self.git_output(root, "rev-parse", "HEAD")

        def review_args(*dispositions: str):
            return controller.parse_args(
                [
                    "--repo",
                    str(root),
                    "--scope",
                    "branch",
                    "--remote",
                    "none",
                    "--artifact-root",
                    str(artifacts),
                    "--json",
                    *[
                        item
                        for value in dispositions
                        for item in ("--local-disposition", value)
                    ],
                ]
            )

        captured: list[list[str]] = []

        def json_process(command, **_kwargs):
            captured.append(command)
            if Path(command[1]).name.endswith("check.py"):
                return 0, {"schemaVersion": 1, "status": "passed"}
            # The stage revalidates its stored receipt and applies rebuttals
            # without re-running a provider, so the outcome stays "findings".
            rebutted = "id-1=rebutted" in command
            return 0, {
                "schemaVersion": 1,
                "outcome": "findings",
                "status": "findings",
                "receipt": {
                    "schemaVersion": 1,
                    "receiptId": "local-receipt",
                    "target": {"head": head, "contentDigest": "1" * 64},
                    "plan": {
                        "configurationDigest": "2" * 64,
                        "policyId": "first-substantive-head",
                    },
                    "outcome": "findings",
                    "attempts": [
                        {
                            "provider": {
                                "id": "prism",
                                "costTier": "low",
                                "qualityTier": "standard",
                            },
                            "durationMs": 12,
                        }
                    ],
                    "findings": [
                        {
                            "id": "id-1",
                            "disposition": "rebutted" if rebutted else "outstanding",
                        }
                    ],
                    "disposition": {
                        "outstanding": 0 if rebutted else 1,
                        "localDispositions": {"id-1": "rebutted"} if rebutted else {},
                    },
                },
            }

        with mock.patch.object(
            controller,
            "_json_process",
            side_effect=json_process,
        ), mock.patch.object(controller, "_default_branch", return_value="main"):
            first_code, first_report = controller.run(review_args())
            second_code, second_report = controller.run(review_args("id-1=rebutted"))
        self.assertEqual((first_code, first_report["status"]), (1, "findings"))
        self.assertEqual((second_code, second_report["status"]), (0, "ready"))
        stage_commands = [
            command
            for command in captured
            if Path(command[1]).name.endswith("review-local.py")
        ]
        self.assertEqual(len(stage_commands), 2)
        self.assertNotIn("--local-disposition", stage_commands[0])
        self.assertIn("--local-disposition", stage_commands[1])
        self.assertIn("id-1=rebutted", stage_commands[1])
        state_files = list(artifacts.glob("review-*.json"))
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "ready")
        self.assertEqual(
            state["local"]["receipt"]["disposition"],
            {"outstanding": 0, "localDispositions": {"id-1": "rebutted"}},
        )

    def test_miscited_pair_reaches_the_stage_intact_and_the_router_accepts_it(
        self,
    ) -> None:
        """The citation survives the controller, and the router buckets the value.

        Two failures this pins, both across the file boundary from where the
        `miscited` ground is implemented. The controller parses each pair and
        **re-serializes** it before forwarding, so a citation is exactly the kind
        of thing that gets silently dropped in transit. And the router's local
        finding loop ends in `else: raise` -- a disposition it does not know is
        not miscounted, it is refused, so the whole receipt would be rejected.
        """

        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        head = self.git_output(root, "rev-parse", "HEAD")
        pair = "id-1=miscited@src/other.py:41"

        def review_args(*dispositions: str):
            return controller.parse_args(
                [
                    "--repo",
                    str(root),
                    "--scope",
                    "branch",
                    "--remote",
                    "none",
                    "--artifact-root",
                    str(artifacts),
                    "--json",
                    *[
                        item
                        for value in dispositions
                        for item in ("--local-disposition", value)
                    ],
                ]
            )

        captured: list[list[str]] = []

        def json_process(command, **_kwargs):
            captured.append(command)
            if Path(command[1]).name.endswith("check.py"):
                return 0, {"schemaVersion": 1, "status": "passed"}
            miscited = pair in command
            return 0, {
                "schemaVersion": 1,
                "outcome": "findings",
                "status": "findings",
                "receipt": {
                    "schemaVersion": 1,
                    "receiptId": "local-receipt",
                    "target": {"head": head, "contentDigest": "1" * 64},
                    "plan": {
                        "configurationDigest": "2" * 64,
                        "policyId": "first-substantive-head",
                    },
                    "outcome": "findings",
                    "attempts": [
                        {
                            "provider": {
                                "id": "prism",
                                "costTier": "low",
                                "qualityTier": "standard",
                            },
                            "durationMs": 12,
                        }
                    ],
                    "findings": [
                        {
                            "id": "id-1",
                            "disposition": "miscited" if miscited else "outstanding",
                        }
                    ],
                    "disposition": {
                        "outstanding": 0 if miscited else 1,
                        "localDispositions": {"id-1": "miscited"} if miscited else {},
                    },
                },
            }

        with mock.patch.object(
            controller,
            "_json_process",
            side_effect=json_process,
        ), mock.patch.object(controller, "_default_branch", return_value="main"):
            first_code, _ = controller.run(review_args())
            second_code, second_report = controller.run(review_args(pair))

        self.assertEqual(first_code, 1)
        self.assertEqual((second_code, second_report["status"]), (0, "ready"))
        stage_commands = [
            command
            for command in captured
            if Path(command[1]).name.endswith("review-local.py")
        ]
        # Verbatim, citation included -- not "id-1=miscited" with the evidence
        # dropped on the way through.
        self.assertIn(pair, stage_commands[1])

    def test_router_summary_buckets_miscited_instead_of_rejecting_the_receipt(
        self,
    ) -> None:
        """`_router_local_summary`'s disposition loop ends in `else: raise`.

        A disposition it does not know is not miscounted, it is refused -- the
        whole receipt is rejected. Reachability is narrow but real: the loop is
        skipped for `outcome: "findings"`, so an ordinary findings receipt never
        gets there, but a provider that emits findings and then exits non-zero
        produces a `failed` receipt that still lists them, and that shape does
        reach it. `miscited` belongs in the `rebutted` bucket for the same
        reason `resolved` does: terminal, with no fix-commit evidence.
        """

        controller = self.load_controller()
        head = "a" * 40

        def report(outcome: str, disposition: str) -> dict:
            return {
                "receipt": {
                    "receiptId": "local-receipt",
                    "target": {"head": head, "contentDigest": "1" * 64},
                    "plan": {
                        "configurationDigest": "2" * 64,
                        "policyId": "first-substantive-head",
                    },
                    "outcome": outcome,
                    "attempts": [
                        {
                            "provider": {
                                "id": "prism",
                                "costTier": "low",
                                "qualityTier": "standard",
                            },
                            "durationMs": 12,
                        }
                    ],
                    "findings": [{"id": "id-1", "disposition": disposition}],
                }
            }

        def summarize(outcome: str, disposition: str):
            return controller._router_local_summary(
                report(outcome, disposition),
                repository={"owner": "platypeeps", "name": "sd-github-review"},
                pr_number=1,
                head=head,
            )

        for outcome in ("failed", "unavailable", "cancelled", "skipped"):
            with self.subTest(outcome=outcome):
                self.assertEqual(
                    summarize(outcome, "miscited")["dispositionCounts"],
                    {"total": 1, "unresolved": 0, "fixed": 0, "rebutted": 1},
                )
        # The narrow reachability itself, so a future change that starts
        # summarizing findings receipts does not pass this file silently.
        self.assertIsNone(summarize("findings", "miscited"))

    def test_controller_rejects_a_malformed_miscited_pair_before_the_stage(
        self,
    ) -> None:
        controller = self.load_controller()

        for token, expected in (
            ("id-1=miscited", "<path>:<line>"),
            ("id-1=miscited@a=b.py:3", "cannot contain '='"),
            ("id-1=rebutted@src/app.py:3", "<stable-id>=rebutted or"),
            ("id-1=dismissed", "<stable-id>=rebutted or"),
        ):
            with self.subTest(token=token):
                with self.assertRaises(controller.ReviewError) as caught:
                    controller._parse_local_dispositions([token])
                self.assertIn(expected, str(caught.exception))

    def branch_review_args(self, controller, root: Path, artifacts: Path, *extra: str):
        """A repeatable `scope=branch` invocation against one attempt.

        The attempt key is a function of the repository, scope, base, head,
        worktree bytes and controls, so repeated calls against an unchanged
        checkout resolve to the same private state file. That is what makes the
        caching tests below observe a resume rather than a fresh attempt.
        """

        return controller.parse_args(
            [
                "--repo",
                str(root),
                "--scope",
                "branch",
                "--remote",
                "none",
                "--artifact-root",
                str(artifacts),
                "--json",
                *extra,
            ]
        )

    def test_failed_check_is_recomputed_on_the_next_invocation(self) -> None:
        # A registered check may read an input the attempt key does not cover:
        # `pack.review-scope` reads the pull-request body. Caching its failure
        # pinned the attempt to that verdict, so the operator's own remediation
        # — editing the body — could not clear it.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)

        with mock.patch.object(
            controller,
            "_run_check",
            side_effect=[
                {"schemaVersion": 1, "status": "failed"},
                {"schemaVersion": 1, "status": "passed"},
            ],
        ) as run_check, mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(
                controller,
                {"head": self.git_output(root, "rev-parse", "HEAD")},
            ),
        ), mock.patch.object(controller, "_default_branch", return_value="main"):
            first = controller.run(self.branch_review_args(controller, root, artifacts))
            second = controller.run(self.branch_review_args(controller, root, artifacts))

        self.assertEqual((first[0], first[1]["status"]), (1, "blocked"))
        self.assertEqual(first[1]["limitations"], ["deterministic-check-not-passed"])
        self.assertEqual((second[0], second[1]["status"]), (0, "ready"))
        self.assertEqual(run_check.call_count, 2)
        # The blocked report carries the failing row it computed, and a phase
        # that still names the last stage that actually completed — where a
        # resume re-enters. Naming `check` here would assert a completed check
        # and disagree with the state file the resume reads.
        self.assertEqual(first[1]["check"], {"schemaVersion": 1, "status": "failed"})
        self.assertEqual(first[1]["phase"], "capability")
        state_files = list(artifacts.glob("review-*.json"))
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["check"], {"schemaVersion": 1, "status": "passed"})

    def test_unchanged_passing_stages_still_replay_except_the_check(self) -> None:
        # The idempotency guarantee the recompute must not cost: a plain
        # re-invocation after an interruption resumes past completed work. The
        # deterministic check is the one stage deliberately outside that
        # guarantee — it is cheap, idempotent, and reads inputs the attempt key
        # does not cover — so it recomputes while the expensive local stage,
        # whose inputs the key does cover, still replays from state.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ) as run_check, mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(
                controller,
                {"head": self.git_output(root, "rev-parse", "HEAD")},
            ),
        ) as run_local, mock.patch.object(
            controller, "_default_branch", return_value="main"
        ):
            first = controller.run(self.branch_review_args(controller, root, artifacts))
            second = controller.run(self.branch_review_args(controller, root, artifacts))

        self.assertEqual((first[0], first[1]["status"]), (0, "ready"))
        self.assertEqual((second[0], second[1]["status"]), (0, "ready"))
        self.assertEqual(run_check.call_count, 2)
        self.assertEqual(run_local.call_count, 1)

    def test_stored_passing_check_is_recomputed_and_can_still_block(self) -> None:
        # The stale-pass direction, and the worse half of this defect: a stored
        # pass makes the gate report `ready` for a tree whose live input has
        # since broken. `pack.review-scope` reads the pull-request body, so the
        # break needs no commit and leaves the head — and therefore the attempt
        # key — untouched.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)

        with mock.patch.object(
            controller,
            "_run_check",
            side_effect=[
                {"schemaVersion": 1, "status": "passed"},
                {"schemaVersion": 1, "status": "failed"},
            ],
        ) as run_check, mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(
                controller,
                {"head": self.git_output(root, "rev-parse", "HEAD")},
            ),
        ), mock.patch.object(controller, "_default_branch", return_value="main"):
            first = controller.run(self.branch_review_args(controller, root, artifacts))
            second = controller.run(self.branch_review_args(controller, root, artifacts))

        self.assertEqual((first[0], first[1]["status"]), (0, "ready"))
        self.assertEqual((second[0], second[1]["status"]), (1, "blocked"))
        self.assertEqual(second[1]["limitations"], ["deterministic-check-not-passed"])
        self.assertEqual(run_check.call_count, 2)
        # The blocked report carries the row this run computed, not the stored
        # one it replaced.
        self.assertEqual(second[1]["check"], {"schemaVersion": 1, "status": "failed"})

    def test_recomputing_the_check_does_not_rewind_the_attempt_phase(self) -> None:
        # `_record_stage(resumable=True)` delegates to `_advance`, which assigns
        # `phase` unconditionally. Naming `check` on every invocation would move
        # the phase backwards on a resume that already completed later stages,
        # and `phase` is where a resume re-enters.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(
                controller,
                {"head": self.git_output(root, "rev-parse", "HEAD")},
            ),
        ), mock.patch.object(controller, "_default_branch", return_value="main"):
            controller.run(self.branch_review_args(controller, root, artifacts))
            state_files = list(artifacts.glob("review-*.json"))
            self.assertEqual(len(state_files), 1)
            after_first = json.loads(state_files[0].read_text(encoding="utf-8"))
            second = controller.run(self.branch_review_args(controller, root, artifacts))

        after_second = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertNotEqual(after_first["phase"], "check")
        self.assertEqual(after_second["phase"], after_first["phase"])
        self.assertEqual(second[1]["phase"], after_first["phase"])

    def test_the_gate_agrees_with_a_direct_check_run_in_both_directions(self) -> None:
        # A stub cannot show the coordinator and the CLI agreeing, because it
        # replaces the one thing under test. This runs the real subprocess
        # through `_run_check` against a check helper whose verdict turns on a
        # file outside the attempt key — the fixture's stand-in for the live
        # pull-request body — and pre-seeds the state with the opposite verdict
        # in each direction.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        live_input = root.parent / "live-input"
        helper = root.parent / "sd-ai-command-pack-check.py"
        helper.write_text(
            "import json, pathlib, sys\n"
            f"marker = pathlib.Path({str(live_input)!r})\n"
            "status = 'passed' if marker.is_file() else 'failed'\n"
            "print(json.dumps({'schemaVersion': 1, 'status': status}))\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )

        def gate_verdict() -> tuple[int, str]:
            outcome = controller.run(
                self.branch_review_args(controller, root, artifacts)
            )
            return outcome[0], outcome[1]["status"]

        with mock.patch.object(controller, "CHECK_SCRIPT", helper), mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(
                controller,
                {"head": self.git_output(root, "rev-parse", "HEAD")},
            ),
        ), mock.patch.object(controller, "_default_branch", return_value="main"):
            # Direction one: seed a stored pass, then break the live input.
            live_input.write_text("present\n", encoding="utf-8")
            self.assertEqual(gate_verdict(), (0, "ready"))
            live_input.unlink()
            self.assertEqual(controller._run_check(root)["status"], "failed")
            self.assertEqual(gate_verdict(), (1, "blocked"))

            # Direction two: the stored verdict is now a failure the state file
            # never kept; remedying the live input clears the gate at the same
            # head, with no new attempt id.
            live_input.write_text("present\n", encoding="utf-8")
            self.assertEqual(controller._run_check(root)["status"], "passed")
            self.assertEqual(gate_verdict(), (0, "ready"))

    def test_rejected_disposition_neither_replays_nor_evicts_the_report(self) -> None:
        # An `invalid` local report rejects the caller's `--local-disposition`
        # argv, which the attempt key does not cover. Caching it replayed the
        # rejection on the next invocation even with no dispositions at all.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        head = self.git_output(root, "rev-parse", "HEAD")
        clean = self.local_report(controller, {"head": head})
        rejected = self.local_report(controller, {"head": head}, status="invalid")
        rejected["diagnostic"] = "local disposition ids match no finding at this head"

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            side_effect=[clean, rejected],
        ) as run_local, mock.patch.object(
            controller, "_default_branch", return_value="main"
        ):
            first = controller.run(self.branch_review_args(controller, root, artifacts))
            second = controller.run(
                self.branch_review_args(
                    controller, root, artifacts, "--local-disposition", "id-1=rebutted"
                )
            )
            third = controller.run(self.branch_review_args(controller, root, artifacts))

        self.assertEqual((first[0], first[1]["status"]), (0, "ready"))
        self.assertEqual((second[0], second[1]["status"]), (2, "invalid"))
        self.assertEqual(second[1]["limitations"], ["local-invalid"])
        # The third invocation supplies no dispositions, so it must read the
        # stored clean report rather than re-run the stage or replay the
        # rejection: the durable report the first invocation stored survived.
        self.assertEqual((third[0], third[1]["status"]), (0, "ready"))
        self.assertEqual(run_local.call_count, 2)
        state_files = list(artifacts.glob("review-*.json"))
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["local"], clean)

    def test_rejected_disposition_without_a_stored_report_recomputes(self) -> None:
        # The companion of the test above, and the arm that actually recomputes.
        # With a report already stored, a rejection leaves the stored one in
        # place and the next invocation reuses it. With nothing stored — the
        # very first invocation supplied dispositions and was rejected — there
        # is no durable report to fall back on, so the next invocation must run
        # the stage rather than replay the rejection.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        head = self.git_output(root, "rev-parse", "HEAD")
        clean = self.local_report(controller, {"head": head})
        rejected = self.local_report(controller, {"head": head}, status="invalid")
        rejected["diagnostic"] = "local disposition ids match no finding at this head"

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            side_effect=[rejected, clean],
        ) as run_local, mock.patch.object(
            controller, "_default_branch", return_value="main"
        ):
            first = controller.run(
                self.branch_review_args(
                    controller, root, artifacts, "--local-disposition", "id-1=rebutted"
                )
            )
            second = controller.run(self.branch_review_args(controller, root, artifacts))

        self.assertEqual((first[0], first[1]["status"]), (2, "invalid"))
        self.assertEqual((second[0], second[1]["status"]), (0, "ready"))
        self.assertEqual(run_local.call_count, 2)
        state_files = list(artifacts.glob("review-*.json"))
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["local"], clean)

    def test_local_provider_failure_is_recomputed_on_the_next_invocation(self) -> None:
        # Provider reachability is environmental, not a function of the attempt
        # key, so an `unavailable` report is a verdict the next invocation is
        # entitled to recompute rather than completed work to resume from.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        head = self.git_output(root, "rev-parse", "HEAD")

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            side_effect=[
                self.local_report(controller, {"head": head}, status="unavailable"),
                self.local_report(controller, {"head": head}),
            ],
        ) as run_local, mock.patch.object(
            controller, "_default_branch", return_value="main"
        ):
            first = controller.run(self.branch_review_args(controller, root, artifacts))
            second = controller.run(self.branch_review_args(controller, root, artifacts))

        self.assertEqual((first[0], first[1]["status"]), (3, "failed"))
        self.assertEqual(first[1]["limitations"], ["local-unavailable"])
        self.assertEqual((second[0], second[1]["status"]), (0, "ready"))
        self.assertEqual(run_local.call_count, 2)

    def test_policy_blocked_local_report_stays_cached(self) -> None:
        # The complement of the three tests above, and the reason the
        # non-resumable set is enumerated rather than "anything that is not
        # clean": local policy is decided by the configuration digest, which the
        # attempt key does cover, so replaying a `blocked` report is correct.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        head = self.git_output(root, "rev-parse", "HEAD")
        blocked = self.local_report(controller, {"head": head}, status="blocked")
        blocked["diagnostic"] = "an approved review.round-extension decision is required"

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            return_value=blocked,
        ) as run_local, mock.patch.object(
            controller, "_default_branch", return_value="main"
        ):
            first = controller.run(self.branch_review_args(controller, root, artifacts))
            second = controller.run(self.branch_review_args(controller, root, artifacts))

        self.assertEqual((first[0], first[1]["status"]), (1, "blocked"))
        self.assertEqual((second[0], second[1]["status"]), (1, "blocked"))
        self.assertEqual(run_local.call_count, 1)

    def test_local_disposition_rerun_keeps_an_advanced_phase(self) -> None:
        # Refreshing a cached local report must not rewind the phase: the
        # remote channel reads it to choose between reconciliation, dispatch,
        # and receipt polling. A rewind would strand a dispatch that already
        # needs reconciliation in the receipt-polling path instead.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        pr = self.pr(controller, root)

        def review_args(*dispositions: str):
            return controller.parse_args(
                [
                    "--repo",
                    str(root),
                    "--scope",
                    "pr",
                    "--pr-number",
                    "42",
                    "--artifact-root",
                    str(artifacts),
                    "--json",
                    *[
                        item
                        for value in dispositions
                        for item in ("--local-disposition", value)
                    ],
                ]
            )

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(controller, pr),
        ), mock.patch.object(
            controller, "_pr_evidence", return_value=pr
        ), mock.patch.object(
            controller, "_capability", return_value=self.capability()
        ), mock.patch.object(
            controller, "_query_receipt", return_value=None
        ), mock.patch.object(
            controller, "_default_branch", return_value="main"
        ), mock.patch.object(
            controller,
            "_dispatch",
            side_effect=controller.CommandError("workflow dispatch failed"),
        ):
            first_code, first_report = controller.run(review_args())
            second_code, second_report = controller.run(review_args("id-1=rebutted"))
        self.assertEqual((first_code, first_report["status"]), (3, "indeterminate"))
        self.assertEqual((second_code, second_report["status"]), (3, "indeterminate"))
        self.assertEqual(
            second_report["limitations"], ["remote-dispatch-reconciliation-required"]
        )
        state_files = list(artifacts.glob("review-*.json"))
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "reconciliation-required")

    def routed_review_context(self, controller, root: Path, artifacts: Path):
        """Mocks for a `scope=pr` routed review, and its repeatable args.

        Everything except the receipt query is fixed, so the tests below vary
        one thing: what the durable receipt looks like at each poll.
        """

        pr = self.pr(controller, root)
        args = controller.parse_args(
            [
                "--repo",
                str(root),
                "--scope",
                "pr",
                "--pr-number",
                "42",
                "--artifact-root",
                str(artifacts),
                "--json",
            ]
        )
        observation = {
            "status": "clean",
            "materialized": True,
            "reviewThreads": {"total": 0, "unresolved": 0, "items": []},
            "conversationComments": [],
            "reviews": [],
            "checks": {"total": 0, "blocking": [], "backend": []},
        }
        patches = (
            mock.patch.object(
                controller,
                "_run_check",
                return_value={"schemaVersion": 1, "status": "passed"},
            ),
            mock.patch.object(
                controller,
                "_run_local",
                return_value=self.local_report(controller, pr),
            ),
            mock.patch.object(controller, "_pr_evidence", return_value=pr),
            mock.patch.object(
                controller, "_capability", return_value=self.capability()
            ),
            mock.patch.object(
                controller, "_collect_observation", return_value=observation
            ),
            mock.patch.object(controller, "_default_branch", return_value="main"),
            mock.patch.object(controller.time, "sleep"),
        )
        return args, patches

    def test_in_flight_receipt_is_polled_until_it_settles(self) -> None:
        # The lane publishes the receipt at `phase: "started"` and rewrites it
        # to a terminal phase seconds later. Breaking out of the poll loop on
        # the first receipt that merely exists caches the in-flight write, and
        # nothing re-queries a receipt that is already stored, so the attempt
        # wedged instead of resolving.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        args, patches = self.routed_review_context(controller, root, artifacts)
        # The real sequence: the pre-dispatch query finds nothing, the route is
        # dispatched, and the first poll lands inside the lane's two-write
        # window before the second sees the terminal write.
        phases = iter([None, "started", "observed"])

        def query(*_args, **kwargs):
            phase = next(phases)
            if phase is None:
                return None
            return self.routed_receipt(kwargs["request"], phase=phase)

        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            receipt_query = stack.enter_context(
                mock.patch.object(controller, "_query_receipt", side_effect=query)
            )
            dispatch = stack.enter_context(
                mock.patch.object(controller, "_dispatch")
            )
            code, report = controller.run(args)

        self.assertEqual((code, report["status"]), (0, "ready"))
        self.assertEqual(report["limitations"], [])
        self.assertEqual(
            report["remote"]["receipt"]["dispatch"]["phase"], "observed"
        )
        # Three queries: the empty pre-dispatch check, the in-flight write,
        # then the terminal one. One dispatch: polling must never route again.
        self.assertEqual(receipt_query.call_count, 3)
        self.assertEqual(dispatch.call_count, 1)

    def test_in_flight_receipt_is_refreshed_by_the_next_invocation(self) -> None:
        # Exhausting the poll budget on an in-flight receipt is a legitimate
        # `remote-reconciliation-required`, but it must stay recoverable: the
        # unchanged attempt the skill tells callers to rerun has to re-query
        # the stored receipt rather than replay it.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        args, patches = self.routed_review_context(controller, root, artifacts)

        pending = iter([None])

        def still_running(*_args, **kwargs):
            # Empty once so the route is dispatched, then in flight for the
            # rest of the poll budget.
            if next(pending, "started") is None:
                return None
            return self.routed_receipt(kwargs["request"], phase="started")

        def settled(*_args, **kwargs):
            return self.routed_receipt(kwargs["request"], phase="observed")

        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            receipt_query = stack.enter_context(
                mock.patch.object(
                    controller, "_query_receipt", side_effect=still_running
                )
            )
            dispatch = stack.enter_context(
                mock.patch.object(controller, "_dispatch")
            )
            first_code, first_report = controller.run(args)
            first_queries = receipt_query.call_count
            receipt_query.side_effect = settled
            second_code, second_report = controller.run(args)

        self.assertEqual((first_code, first_report["status"]), (3, "indeterminate"))
        self.assertEqual(
            first_report["limitations"], ["remote-reconciliation-required"]
        )
        self.assertEqual((second_code, second_report["status"]), (0, "ready"))
        self.assertEqual(
            second_report["remote"]["receipt"]["dispatch"]["phase"], "observed"
        )
        # The first run spends its whole budget; the second re-queries the
        # stored receipt without dispatching again.
        self.assertGreater(first_queries, 1)
        self.assertGreater(receipt_query.call_count, first_queries)
        self.assertEqual(dispatch.call_count, 1)

    def test_settled_receipt_phases_are_not_polled_again(self) -> None:
        # `not-started` is what a skipped `route: none` dispatch carries, and it
        # is terminal for that route. Treating every non-`observed` phase as
        # in-flight would burn the poll budget on a receipt that is already
        # final.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        args, patches = self.routed_review_context(controller, root, artifacts)

        def query(*_args, **kwargs):
            return self.none_receipt(kwargs["request"])

        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            receipt_query = stack.enter_context(
                mock.patch.object(controller, "_query_receipt", side_effect=query)
            )
            stack.enter_context(mock.patch.object(controller, "_dispatch"))
            code, report = controller.run(args)

        self.assertEqual((code, report["status"]), (0, "ready"))
        self.assertEqual(receipt_query.call_count, 1)

    def test_failed_dispatch_receipt_is_reported_without_polling(self) -> None:
        # A failed dispatch is terminal-bad. Reconciling it is the operator's
        # job; polling it would only delay the diagnostic by the poll budget.
        controller = self.load_controller()
        root = self.make_repo()
        artifacts = self.artifact_root(root)
        args, patches = self.routed_review_context(controller, root, artifacts)

        def query(*_args, **kwargs):
            return self.routed_receipt(
                kwargs["request"], phase="observed", status="failed"
            )

        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            receipt_query = stack.enter_context(
                mock.patch.object(controller, "_query_receipt", side_effect=query)
            )
            stack.enter_context(mock.patch.object(controller, "_dispatch"))
            code, report = controller.run(args)

        self.assertEqual((code, report["status"]), (3, "indeterminate"))
        self.assertEqual(report["limitations"], ["remote-reconciliation-required"])
        self.assertEqual(receipt_query.call_count, 1)

    def run_routed_review_with_dispatch_status(
        self, controller, root: Path, artifacts: Path, *, status: str
    ):
        """One routed review through the lane's real two-write sequence.

        The pre-dispatch query finds nothing, the route is dispatched, the
        first poll lands on the in-flight `started` write, and the second sees
        the terminal one. A fixture that only ever produces the terminal write
        would not exercise the window the poller actually lands in.
        """

        args, patches = self.routed_review_context(controller, root, artifacts)
        phases = iter([None, "started", "observed"])

        def query(*_args, **kwargs):
            # Settle on the terminal write once the scripted sequence is spent.
            # These tests assert on the report's limitations, not on how many
            # times the poller queried, and `test_in_flight_receipt_is_polled_
            # until_it_settles` already owns the call-count guarantee. Letting
            # the iterator run dry would turn any future change in poll budget
            # into a bare `StopIteration` instead of a legible assertion.
            phase = next(phases, "observed")
            if phase is None:
                return None
            return self.routed_receipt(
                kwargs["request"], phase=phase, status=status
            )

        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(
                mock.patch.object(controller, "_query_receipt", side_effect=query)
            )
            stack.enter_context(mock.patch.object(controller, "_dispatch"))
            return controller.run(args)

    def test_already_present_dispatch_qualifies_remote_confidence(self) -> None:
        # `already-present` means the reviewer was on the pull request before
        # the Action routed, so something else summoned it -- here, the `main`
        # ruleset's `copilot_code_review` rule. The receipt has always carried
        # the discriminator; the report claimed full remote confidence anyway.
        controller = self.load_controller()
        root = self.make_repo()
        code, report = self.run_routed_review_with_dispatch_status(
            controller, root, self.artifact_root(root), status="already-present"
        )

        self.assertEqual((code, report["status"]), (0, "ready"))
        self.assertEqual(
            report["limitations"], ["remote-evidence-not-dispatch-caused"]
        )
        self.assertEqual(
            report["remote"]["receipt"]["dispatch"]["status"], "already-present"
        )

    def test_requested_dispatch_claims_remote_confidence(self) -> None:
        # The dispatch that actually summoned the reviewer owns the evidence it
        # caused. Qualifying this case too would make the limitation noise.
        controller = self.load_controller()
        root = self.make_repo()
        code, report = self.run_routed_review_with_dispatch_status(
            controller, root, self.artifact_root(root), status="requested"
        )

        self.assertEqual((code, report["status"]), (0, "ready"))
        self.assertEqual(report["limitations"], [])

    def test_dispatch_status_does_not_change_harvested_findings(self) -> None:
        # The failure mode being fixed is overclaimed confidence, not
        # oversupplied evidence. `_collect_observation` must be blind to
        # `dispatch.status`: a real Copilot finding cannot become invisible
        # because the ruleset requested the reviewer first.
        controller = self.load_controller()
        root = self.make_repo()
        pr = self.pr(controller, root)
        request = {
            "logicalDispatchId": "dispatch-1",
            "requestFingerprint": "fingerprint-1",
            "repository": "platypeeps/example",
            "pullRequestNumber": 42,
            "headSha": pr["head"],
            "attempt": 1,
            "policyVersion": 1,
            "correlationId": "correlation-1",
        }
        reviews = [
            {
                "id": 7,
                "html_url": "https://github.com/platypeeps/example/pull/42#r7",
                "state": "CHANGES_REQUESTED",
                "body": "this needs a guard",
                "commit_id": pr["head"],
                "user": {"login": "copilot-pull-request-reviewer[bot]"},
            }
        ]

        def observe(status: str) -> dict[str, object]:
            with mock.patch.object(
                controller, "_collect_review_threads", return_value=[]
            ), mock.patch.object(
                controller, "_paginated_rest_array", return_value=reviews
            ), mock.patch.object(
                controller, "_gh_json", return_value=[]
            ):
                return controller._collect_observation(
                    root,
                    pr=pr,
                    receipt=self.routed_receipt(
                        request, phase="observed", status=status
                    ),
                    receipt_check_name="sd-github-review/receipt",
                )

        caused = observe("requested")
        piggybacked = observe("already-present")

        self.assertEqual(caused["status"], "findings")
        self.assertEqual(caused, piggybacked)
        self.assertEqual(len(piggybacked["reviews"]), 1)

    def test_fully_rebutted_local_stage_routes_like_a_clean_one(self) -> None:
        controller = self.load_controller()
        absent = {"state": "absent", "reason": "setup-descriptor-absent"}
        (clean_code, clean_report), clean_dispatch = self.run_with_mocks(
            controller,
            self.make_repo(),
            scope="pr",
            capability=absent,
        )
        (code, report), dispatch = self.run_with_mocks(
            controller,
            self.make_repo(),
            scope="pr",
            local_status="findings",
            capability=absent,
            local_receipt_extra={
                "findings": [{"id": "id-1", "disposition": "rebutted"}],
                "disposition": {
                    "outstanding": 0,
                    "localDispositions": {"id-1": "rebutted"},
                },
            },
        )
        self.assertEqual((clean_code, clean_report["status"]), (0, "ready"))
        self.assertEqual((code, report["status"]), (0, "ready"))
        self.assertEqual(report["phase"], clean_report["phase"])
        self.assertEqual(report["limitations"], clean_report["limitations"])
        self.assertTrue(report["exactHeadReady"])
        # Provider evidence stays exactly as the stage recorded it; only the
        # caller-owned disposition count moved the gate.
        self.assertEqual(report["local"]["receipt"]["outcome"], "findings")
        clean_dispatch.assert_not_called()
        dispatch.assert_not_called()

    def test_outstanding_local_findings_still_block_remote_routing(self) -> None:
        controller = self.load_controller()
        (code, report), dispatch = self.run_with_mocks(
            controller,
            self.make_repo(),
            scope="pr",
            local_status="findings",
            local_receipt_extra={
                "findings": [
                    {"id": "id-1", "disposition": "outstanding"},
                    {"id": "id-2", "disposition": "rebutted"},
                ],
                "disposition": {
                    "outstanding": 1,
                    "localDispositions": {"id-2": "rebutted"},
                },
            },
        )
        self.assertEqual((code, report["status"]), (1, "findings"))
        dispatch.assert_not_called()

    def test_findings_outcome_listing_no_findings_still_blocks(self) -> None:
        # The local stage blocks a provider that claims findings but lists none
        # (nothing is inspectable or rebuttable), so a zero outstanding count on
        # an empty findings list must not open the router either.
        controller = self.load_controller()
        (code, report), dispatch = self.run_with_mocks(
            controller,
            self.make_repo(),
            scope="pr",
            local_status="findings",
            local_receipt_extra={
                "findings": [],
                "disposition": {"outstanding": 0, "localDispositions": {}},
            },
        )
        self.assertEqual((code, report["status"]), (1, "findings"))
        dispatch.assert_not_called()

    def test_unreadable_local_disposition_block_fails_closed(self) -> None:
        controller = self.load_controller()
        for extra in (
            None,
            {"disposition": ["not-a-mapping"]},
            {"disposition": {}},
            {"disposition": {"outstanding": "0"}},
            {"disposition": {"outstanding": True}},
            {"disposition": {"outstanding": -1}},
        ):
            with self.subTest(disposition=extra):
                (code, report), dispatch = self.run_with_mocks(
                    controller,
                    self.make_repo(),
                    scope="pr",
                    local_status="findings",
                    local_receipt_extra=extra,
                )
                self.assertEqual((code, report["status"]), (1, "findings"))
                dispatch.assert_not_called()

    def test_run_remote_none_and_observation_terminals(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
            remote="none",
        )
        self.assertEqual((code, report["status"]), (0, "ready"))
        dispatch.assert_not_called()

        for observed, expected_code in (("findings", 1), ("blocked", 1), ("pending", 3)):
            root = self.make_repo()
            observation = {
                "status": observed,
                "materialized": observed != "pending",
                "reviewThreads": {"total": 0, "unresolved": 0, "items": []},
                "conversationComments": [],
                "reviews": [],
                "checks": {"total": 0, "blocking": [], "backend": []},
            }
            (code, report), _dispatch = self.run_with_mocks(
                controller,
                root,
                scope="pr",
                observation=observation,
            )
            self.assertEqual(code, expected_code)
            self.assertEqual(report["status"], observed)

    def test_run_dispatches_once_and_reaches_exact_head_ready(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        (code, report), dispatch = self.run_with_mocks(
            controller,
            root,
            scope="pr",
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "ready")
        dispatch.assert_called_once()
        state_files = list(self.artifact_root(root).glob("review-*.json"))
        self.assertEqual(len(state_files), 1)
        state = json.loads(state_files[0].read_text(encoding="utf-8"))
        self.assertEqual(state["phase"], "ready")

    def test_report_reads_remote_latency_from_durable_observation_state(self) -> None:
        controller = self.load_controller()
        report = controller._report(
            state={
                "phase": "ready",
                "identity": {},
                "remoteReceipt": {
                    "selectedRoute": "copilot",
                    "backend": {"id": "copilot", "costTier": "high"},
                },
                "observation": {"latencyMs": 321},
            },
            status="ready",
        )
        self.assertEqual(report["economics"]["remote"]["latencyMs"], 321)

    def test_round_limit_fails_before_side_effects(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        args = controller.parse_args(
            ["--repo", str(root), "--scope", "branch", "--attempt", "6"]
        )
        with mock.patch.object(controller, "_run_check") as check:
            with self.assertRaisesRegex(controller.ReviewError, "roundLimit"):
                controller.run(args)
        check.assert_not_called()

        authorized = controller.parse_args(
            [
                "--repo",
                str(root),
                "--scope",
                "branch",
                "--base",
                "origin/main",
                "--attempt",
                "6",
                "--round-extension-authorized",
            ]
        )
        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(
                controller,
                {
                    "head": self.git_output(root, "rev-parse", "HEAD"),
                    "repository": {"owner": "platypeeps", "name": "example"},
                },
            ),
        ), mock.patch.object(
            controller,
            "_artifact_root",
            return_value=self.artifact_root(root),
        ):
            code, report = controller.run(authorized)
        self.assertEqual((code, report["status"]), (0, "ready"))

    def test_bookkeeping_reentry_has_its_own_bounded_round_budget(self) -> None:
        controller = self.load_controller()
        root = self.make_repo()
        evidence = root / "bookkeeping-evidence.json"
        evidence.write_text("{}", encoding="utf-8")

        def reentry_args(attempt: str) -> object:
            return controller.parse_args(
                [
                    "--repo",
                    str(root),
                    "--scope",
                    "branch",
                    "--base",
                    "origin/main",
                    "--attempt",
                    attempt,
                    "--successor",
                    "bookkeeping",
                    "--bookkeeping-evidence",
                    str(evidence),
                ]
            )

        with mock.patch.object(
            controller,
            "_run_check",
            return_value={"schemaVersion": 1, "status": "passed"},
        ), mock.patch.object(
            controller,
            "_run_local",
            return_value=self.local_report(
                controller,
                {
                    "head": self.git_output(root, "rev-parse", "HEAD"),
                    "repository": {"owner": "platypeeps", "name": "example"},
                },
            ),
        ), mock.patch.object(
            controller,
            "_artifact_root",
            return_value=self.artifact_root(root),
        ):
            code, report = controller.run(reentry_args("7"))
        self.assertEqual((code, report["status"]), (0, "ready"))

        # Beyond the fixed re-entry grant the decision is still required.
        with mock.patch.object(controller, "_run_check") as check:
            with self.assertRaisesRegex(controller.ReviewError, "roundLimit"):
                controller.run(reentry_args("8"))
        check.assert_not_called()

        # The grant needs the evidence flag, not just the successor class.
        no_evidence = controller.parse_args(
            [
                "--repo",
                str(root),
                "--scope",
                "branch",
                "--attempt",
                "6",
                "--successor",
                "bookkeeping",
            ]
        )
        with mock.patch.object(controller, "_run_check") as check:
            with self.assertRaisesRegex(controller.ReviewError, "roundLimit"):
                controller.run(no_evidence)
        check.assert_not_called()

        # An explicit --local override skips the planning branch that
        # validates the evidence, and --family-evidence can flip the
        # effective successor to repeated-family inside the local stage,
        # which also skips it; each keeps the unextended limit even with the
        # successor class and an evidence path present.
        for extra in (
            ["--local", "none"],
            ["--local", "all"],
            ["--family-evidence", str(evidence)],
        ):
            overridden = controller.parse_args(
                [
                    "--repo",
                    str(root),
                    "--scope",
                    "branch",
                    "--attempt",
                    "6",
                    "--successor",
                    "bookkeeping",
                    "--bookkeeping-evidence",
                    str(evidence),
                    *extra,
                ]
            )
            with mock.patch.object(controller, "_run_check") as check:
                with self.assertRaisesRegex(
                    controller.ReviewError, "roundLimit"
                ):
                    controller.run(overridden)
            check.assert_not_called()

    def test_controller_does_not_expose_an_unbound_head_override(self) -> None:
        controller = self.load_controller()
        with mock.patch.object(controller.sys, "stderr"), self.assertRaises(SystemExit):
            controller.parse_args(["--head", "origin/main"])

    def test_human_report_and_main_invalid_result_are_stable(self) -> None:
        controller = self.load_controller()
        report = {
            "status": "ready",
            "scope": "branch",
            "phase": "ready",
            "routerCapability": {"state": "skipped", "reason": "non-pr-scope"},
            "diagnostic": None,
            "limitations": [],
        }
        with mock.patch("builtins.print") as output:
            controller._print_human(report)
        self.assertTrue(output.called)
        with mock.patch.object(
            controller,
            "run",
            side_effect=controller.ReviewError("bad invocation"),
        ), mock.patch("builtins.print") as output:
            code = controller.main(["--json"])
        self.assertEqual(code, 2)
        payload = json.loads(output.call_args.args[0])
        self.assertEqual(payload["status"], "invalid")
