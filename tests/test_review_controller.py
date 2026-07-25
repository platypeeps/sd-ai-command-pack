from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

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

    def write_descriptor(self, root: Path, *, contract: int = 1) -> Path:
        path = root / "config/routed-review-setup-v1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
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
                        "checkName": "sd-github-review/receipt",
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

        path = root / ".sd-ai-command-pack/review.json"
        path.parent.mkdir(parents=True)
        config = default | {
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
        self.assertEqual(local_config["remoteIntegration"], parsed)

        config["remoteIntegration"]["descriptorPath"] = "../escape.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(controller.ReviewError, "stay inside"):
            controller.load_review_configuration(root)
        with self.assertRaisesRegex(local_stage.ReviewInputError, "stay inside"):
            local_stage.load_config(root)

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
        (root / "new.txt").write_text("first\n", encoding="utf-8")
        second = controller._worktree_digest(root)
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
                artifact_root=self.artifact_root(root),
                args=args,
                local_policy="optional",
            )
        self.assertIn("--finding-family", captured[1])
        self.assertNotIn("bash", captured[1])

        request = {"value": "literal"}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(controller, "run_gh", return_value=completed) as run_gh:
            controller._dispatch(
                root,
                workflow=".github/workflows/sd-review.yml",
                request=request,
            )
        argv = run_gh.call_args.args[0]
        self.assertEqual(argv[:3], ["workflow", "run", ".github/workflows/sd-review.yml"])
        self.assertIn('review-request={"value":"literal"}', argv)
        failed = mock.Mock(returncode=1, stdout="", stderr="failed")
        with mock.patch.object(controller, "run_gh", return_value=failed):
            with self.assertRaisesRegex(controller.CommandError, "uncertain"):
                controller._dispatch(
                    root,
                    workflow=".github/workflows/sd-review.yml",
                    request=request,
                )

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
        thread_payload = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [],
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                            }
                        }
                    }
                }
            }
        ]
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
            if context == "collect paginated review threads":
                return thread_payload
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

        def fake_gh(_args, *, context, **_kwargs):
            if context == "collect paginated review threads":
                return thread_payload
            if context == "collect paginated review-thread comments":
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
        thread_payload = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    {
                                        "id": "unrelated-thread",
                                        "isResolved": False,
                                        "isOutdated": False,
                                        "comments": {
                                            "nodes": [
                                                {
                                                    "id": "unrelated-comment",
                                                    "body": "Unrelated inline feedback",
                                                    "author": {"login": "someone-else"},
                                                }
                                            ],
                                            "pageInfo": {"hasNextPage": False},
                                        },
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        ]

        def fake_gh(_args, *, context, **_kwargs):
            if context == "collect paginated review threads":
                return thread_payload
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
            "backend": None,
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
        threads = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {"reviewThreads": {"nodes": []}}
                    }
                }
            }
        ]
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
            if context == "collect paginated review threads":
                return threads
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
        capability: dict[str, object] | None = None,
        remote: str = "auto",
        receipt: dict[str, object] | None = None,
        observation: dict[str, object] | None = None,
        check_status: str = "passed",
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
        with patches[0], patches[1]:
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
