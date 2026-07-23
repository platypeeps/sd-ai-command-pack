from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
contextlib = _support.contextlib
io = _support.io
os = _support.os
Path = _support.Path
mock = _support.mock
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

CONTROLLER = PACK_ROOT / "scripts/sd-ai-command-pack-fleet-controller.py"
HEAD = "a" * 40
OTHER_HEAD = "b" * 40


class FleetControllerTests(InstallTestCase):
    def load_controller(self):
        return self.load_module_from_path(
            CONTROLLER,
            f"sd_ai_command_pack_fleet_controller_{id(self)}",
        )

    def write_inputs(self, root: Path):
        consumers = ("canary-a", "canary-b", "wave-a", "wave-b")
        fleet = root / "fleet.json"
        manifest = root / "manifest.json"
        fleet.write_text(
            json.dumps(
                {
                    "schemaVersion": 4,
                    "rolloutPolicy": {
                        "defaultConcurrency": 2,
                        "cohorts": [
                            {
                                "name": "canary",
                                "strategy": "sequential",
                                "consumers": ["canary-a", "canary-b"],
                            },
                            {
                                "name": "wave",
                                "strategy": "bounded-parallel",
                                "maxConcurrency": 2,
                                "consumers": ["wave-a", "wave-b"],
                            },
                        ],
                    },
                    "consumers": [
                        {
                            "name": name,
                            "github": f"example/{name}",
                            "pathHint": str(root / name),
                            "platforms": ["github"],
                            "rolloutPriority": index * 10,
                            "candidateTimeoutSeconds": 60,
                            "candidatePrepare": [],
                            "candidateChecks": [["python3", "check.py"]],
                        }
                        for index, name in enumerate(consumers, start=1)
                    ],
                }
            ),
            encoding="utf-8",
        )
        manifest.write_text(json.dumps({"version": "0.37.0"}), encoding="utf-8")
        return fleet, manifest

    def state(self, controller, *, selected=(), no_merge=False):
        root = self.make_git_repo_without_trellis()
        fleet, manifest = self.write_inputs(root)
        state = controller.new_state(
            repo=root,
            campaign="campaign-1",
            release="0.37.0",
            fleet_path=fleet,
            pack_manifest_path=manifest,
            selected=selected,
            no_merge=no_merge,
        )
        return root, fleet, manifest, state

    def pass_preflight(self, controller, state):
        action = controller.issue_next(state)[0]
        receipt, changed = controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=None,
            result="passed",
        )
        self.assertTrue(changed)
        self.assertEqual(receipt["stage"], "preflight")

    def pass_lane_action(self, controller, state):
        action = controller.issue_next(state)[0]
        kwargs = {}
        if action["stage"] == "pr-publication":
            kwargs = {"head": HEAD, "pr_number": 17}
        elif action["stage"] in controller.PR_HEAD_STAGES:
            kwargs = {"head": HEAD}
        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=action["consumer"],
            result="passed",
            **kwargs,
        )
        return action

    def run_cli(self, controller, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = controller.main(list(arguments))
        output = stdout.getvalue().strip()
        return status, json.loads(output) if output else None, stderr.getvalue()

    def test_plan_binds_release_manifest_checkout_and_order(self) -> None:
        controller = self.load_controller()
        root, fleet, manifest, state = self.state(controller)

        self.assertEqual(state["release"], "0.37.0")
        self.assertEqual(
            [lane["name"] for lane in state["lanes"]],
            ["canary-a", "canary-b", "wave-a", "wave-b"],
        )
        self.assertEqual(state["fleetManifest"], str(fleet.resolve()))
        self.assertEqual(state["repositoryDigest"], controller._digest_path(root))
        controller.validate_state(state)

        checkout_path = state["lanes"][0]["checkoutPath"]
        state["lanes"][0]["checkoutPath"] = str(root / "redirected-checkout")
        with self.assertRaisesRegex(
            controller.FleetControllerError,
            "checkoutDigest does not match checkoutPath",
        ):
            controller.validate_state(state)
        state["lanes"][0]["checkoutPath"] = checkout_path
        checkout_digest = state["lanes"][0]["checkoutDigest"]
        state["lanes"][0]["checkoutPath"] = "relative-checkout"
        state["lanes"][0]["checkoutDigest"] = controller._digest_path(
            Path("relative-checkout")
        )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "checkoutPath must be absolute"
        ):
            controller.validate_state(state)
        state["lanes"][0]["checkoutPath"] = checkout_path
        state["lanes"][0]["checkoutDigest"] = checkout_digest
        updated_at = state["updatedAt"]
        state["updatedAt"] = ""
        with self.assertRaisesRegex(
            controller.FleetControllerError, "updatedAt must be a UTC timestamp"
        ):
            controller.validate_state(state)
        state["updatedAt"] = updated_at
        state["lanes"][0]["status"] = "terminal"
        with self.assertRaisesRegex(
            controller.FleetControllerError,
            "terminal status and result must be consistent",
        ):
            controller.validate_state(state)
        state["lanes"][0]["status"] = "waiting"
        state["lanes"][0]["result"] = "at-target"
        with self.assertRaisesRegex(
            controller.FleetControllerError,
            "terminal status and result must be consistent",
        ):
            controller.validate_state(state)
        state["lanes"][0]["result"] = None

        manifest.write_text(json.dumps({"version": "0.38.0"}), encoding="utf-8")
        with self.assertRaisesRegex(controller.FleetControllerError, "does not match"):
            controller.new_state(
                repo=root,
                campaign="campaign-2",
                release="0.37.0",
                fleet_path=fleet,
                pack_manifest_path=manifest,
            )

    def test_preflight_issue_and_record_are_idempotent(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)

        action = controller.issue_next(state)[0]
        self.assertEqual(action["stage"], "preflight")
        self.assertEqual(controller.issue_next(state), [])
        receipt, changed = controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=None,
            result="passed",
        )
        replay, replay_changed = controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=None,
            result="passed",
        )

        self.assertTrue(changed)
        self.assertFalse(replay_changed)
        self.assertEqual(replay, receipt)
        with self.assertRaisesRegex(controller.FleetControllerError, "conflicting"):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer=None,
                result="product-failure",
                reason_code="bad-preflight",
            )

    def test_canaries_gate_starts_and_post_canary_wave_is_bounded(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)

        first = controller.issue_next(state)
        self.assertEqual([item["consumer"] for item in first], ["canary-a"])
        controller.record_result(
            state,
            action_id=first[0]["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="at-target",
        )
        second = controller.issue_next(state)
        self.assertEqual([item["consumer"] for item in second], ["canary-b"])
        controller.record_result(
            state,
            action_id=second[0]["actionId"],
            release="0.37.0",
            consumer="canary-b",
            result="at-target",
        )

        wave = controller.issue_next(state)
        self.assertEqual(
            [item["consumer"] for item in wave], ["wave-a", "wave-b"]
        )
        self.assertEqual(len(wave), 2)

    def test_canary_ownership_skip_blocks_later_waves(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        action = controller.issue_next(state)[0]

        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="ownership-skip",
            reason_code="active-external-owner",
        )

        self.assertEqual(state["status"], "blocked")
        self.assertEqual(controller.issue_next(state), [])
        report = controller.status_report(state)
        self.assertTrue(report["plan"]["stopStarting"])

    def test_full_lane_progression_requires_exact_pr_head(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)

        while state["lanes"][0]["stage"] != "pr-publication":
            self.pass_lane_action(controller, state)
        self.pass_lane_action(controller, state)
        action = controller.issue_next(state)[0]
        self.assertEqual(action["stage"], "review")
        with self.assertRaisesRegex(controller.FleetControllerError, "requires head"):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer="wave-a",
                result="review-finding",
                reason_code="review-finding",
            )
        with self.assertRaisesRegex(controller.FleetControllerError, "current PR head"):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer="wave-a",
                result="review-finding",
                reason_code="review-finding",
                head=OTHER_HEAD,
            )
        with self.assertRaisesRegex(controller.FleetControllerError, "current PR head"):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer="wave-a",
                result="passed",
                head=OTHER_HEAD,
            )
        self.assertEqual(state["lanes"][0]["status"], "issued")
        persisted = json.loads(json.dumps(state))
        controller.record_result(
            persisted,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="review-finding",
            reason_code="review-finding",
            head=HEAD,
        )
        persisted["lanes"][0]["receipts"][-1]["head"] = OTHER_HEAD
        with self.assertRaisesRegex(controller.FleetControllerError, "current PR head"):
            controller.validate_state(persisted)

        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
            head=HEAD,
        )
        while state["status"] != "complete":
            self.pass_lane_action(controller, state)

        lane = state["lanes"][0]
        self.assertEqual(lane["result"], "merged")
        self.assertEqual(lane["prNumber"], 17)
        self.assertEqual(controller.issue_next(state), [])

    def test_lane_receipt_replay_uses_original_action_identity(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)
        action = controller.issue_next(state)[0]
        receipt, changed = controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
        )

        self.assertTrue(changed)
        self.assertEqual(state["lanes"][0]["stage"], "install-update")
        replay, replay_changed = controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
        )

        self.assertEqual(replay, receipt)
        self.assertFalse(replay_changed)

    def test_no_merge_finishes_at_pr_open(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",), no_merge=True
        )
        self.pass_preflight(controller, state)

        while state["status"] != "complete":
            self.pass_lane_action(controller, state)

        self.assertEqual(state["lanes"][0]["result"], "pr-open")
        self.assertNotIn(
            "merge", [receipt["stage"] for receipt in state["lanes"][0]["receipts"]]
        )

    def test_retryable_failures_retry_once_then_park(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        self.pass_preflight(controller, state)
        first = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=first["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="retryable-failure",
            reason_code="temporary-network",
        )
        second = controller.issue_next(state)[0]

        self.assertNotEqual(first["actionId"], second["actionId"])
        self.assertEqual(second["attempt"], 2)
        controller.record_result(
            state,
            action_id=second["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="retryable-failure",
            reason_code="temporary-network",
        )
        self.assertEqual(state["lanes"][0]["result"], "retry-exhausted")

    def test_wrong_release_and_consumer_receipts_are_rejected(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        action = controller.issue_next(state)[0]

        with self.assertRaisesRegex(controller.FleetControllerError, "release"):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.36.0",
                consumer=None,
                result="passed",
            )
        with self.assertRaisesRegex(controller.FleetControllerError, "forbids blocker"):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer=None,
                result="passed",
                blocker="contradiction",
            )
        with self.assertRaisesRegex(controller.FleetControllerError, "forbids blocker"):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer=None,
                result="passed",
                pack_blocker=True,
            )
        with self.assertRaisesRegex(controller.FleetControllerError, "not currently issued"):
            controller.record_result(
                state,
                action_id="f" * 64,
                release="0.37.0",
                consumer=None,
                result="passed",
            )

    def test_persisted_receipts_revalidate_build_invariants(self) -> None:
        controller = self.load_controller()

        def action(stage):
            return {
                "actionId": "c" * 64,
                "attempt": 1,
                "consumer": "canary-a",
                "release": "0.37.0",
                "stage": stage,
            }

        missing_reason = controller._build_receipt(
            action("checkout-validation"),
            result="retryable-failure",
            reason_code="temporary-network",
            blocker=None,
            pack_blocker=False,
            head=None,
            pr_number=None,
        )
        missing_reason["reasonCode"] = None
        contradictory_success = controller._build_receipt(
            action("checkout-validation"),
            result="passed",
            reason_code=None,
            blocker=None,
            pack_blocker=False,
            head=None,
            pr_number=None,
        )
        contradictory_success["packBlocker"] = True
        missing_review_head = controller._build_receipt(
            action("review"),
            result="review-finding",
            reason_code="review-finding",
            blocker=None,
            pack_blocker=False,
            head=HEAD,
            pr_number=17,
        )
        missing_review_head["head"] = None
        incomplete_publication = controller._build_receipt(
            action("pr-publication"),
            result="passed",
            reason_code=None,
            blocker=None,
            pack_blocker=False,
            head=HEAD,
            pr_number=17,
        )
        incomplete_publication["prNumber"] = None

        for receipt, message in (
            (missing_reason, "requires a reason code"),
            (contradictory_success, "forbids blocker evidence"),
            (missing_review_head, "requires head"),
            (incomplete_publication, "requires head and PR number"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                controller.FleetControllerError, message
            ):
                controller.validate_receipt(receipt, "persisted receipt")

    def test_resume_reports_issued_action_without_replaying_it(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        self.pass_preflight(controller, state)
        action = controller.issue_next(state)[0]

        report = controller.resume_report(state)

        self.assertEqual(controller.issue_next(state), [])
        self.assertEqual(
            report["reconciliation"][0]["action"]["actionId"], action["actionId"]
        )
        self.assertEqual(
            set(report["reconciliation"][0]["action"]),
            {"actionId", "attempt", "consumer", "release", "stage"},
        )
        self.assertEqual(
            report["reconciliation"][0]["reasonCode"],
            "issued-action-needs-reconciliation",
        )
        self.assertFalse(report["reconciliation"][0]["evidence"]["exists"])
        self.assertFalse(
            report["reconciliation"][0]["evidence"]["checkoutDigestMatches"]
        )

    def test_ambiguous_action_blocks_until_explicit_reconciliation(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        self.pass_preflight(controller, state)
        action = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="ambiguous",
            reason_code="checkout-result-unknown",
        )

        self.assertEqual(state["status"], "blocked")
        self.assertEqual(controller.issue_next(state), [])
        report = controller.resume_report(state)
        self.assertEqual(
            report["reconciliation"][0]["action"]["actionId"], action["actionId"]
        )
        self.assertEqual(
            set(report["reconciliation"][0]["action"]),
            {"actionId", "attempt", "consumer", "release", "stage"},
        )
        self.assertIsNone(controller.status_report(state)["plan"])
        receipt, changed = controller.resolve_reconciliation(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="passed",
        )

        self.assertTrue(changed)
        self.assertEqual(receipt["result"], "passed")
        self.assertEqual(state["lanes"][0]["stage"], "install-update")
        self.assertEqual(state["status"], "active")
        replay, replay_changed = controller.resolve_reconciliation(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="passed",
        )
        self.assertEqual(replay, receipt)
        self.assertFalse(replay_changed)

    def test_preflight_ambiguity_preserves_original_action_identity(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        action = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=None,
            result="ambiguous",
            reason_code="preflight-result-unknown",
        )

        report = controller.resume_report(state)

        self.assertEqual(
            report["reconciliation"][0]["action"]["actionId"], action["actionId"]
        )
        self.assertEqual(
            report["reconciliation"][0]["reasonCode"],
            "ambiguous-recorded-result",
        )

    def test_explicit_resume_retries_cleared_ownership_skip(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        self.pass_preflight(controller, state)
        action = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="ownership-skip",
            reason_code="active-external-owner",
        )

        controller.retry_consumer(state, "canary-a")
        resumed = controller.issue_next(state)[0]

        self.assertEqual(resumed["attempt"], 2)
        self.assertNotEqual(resumed["actionId"], action["actionId"])

    def test_manifest_drift_and_invalid_concurrency_fail_closed(self) -> None:
        controller = self.load_controller()
        _root, fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        original = json.loads(fleet.read_text(encoding="utf-8"))
        original["description"] = "drift"
        fleet.write_text(json.dumps(original), encoding="utf-8")

        with self.assertRaisesRegex(controller.FleetControllerError, "changed"):
            controller.issue_next(state)

    def test_wave_planner_errors_are_reported_as_controller_errors(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)

        with mock.patch.object(
            controller.WAVE_PLANNER,
            "plan_rollout",
            side_effect=controller.WAVE_PLANNER.FleetWavePlanError(
                "cohort concurrency exceeded"
            ),
        ):
            with self.assertRaisesRegex(
                controller.FleetControllerError, "concurrency exceeded"
            ):
                controller.issue_next(state)

    def test_manifest_digest_uses_the_validated_read(self) -> None:
        controller = self.load_controller()
        root = self.make_git_repo_without_trellis()
        fleet, _manifest = self.write_inputs(root)
        expected = controller.hashlib.sha256(fleet.read_bytes()).hexdigest()

        with mock.patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("manifest must not be read twice"),
        ):
            _payload, _consumers, _policy, digest = controller._manifest(fleet)

        self.assertEqual(digest, expected)

    def test_store_is_private_atomic_and_rejects_cross_repo_state(self) -> None:
        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(controller)
        state_home = root.parent / f"{root.name}-campaign-state"
        store = controller.CampaignStore(root, "campaign-1", state_home)

        store.directory.mkdir(parents=True, mode=0o755)
        os.chmod(store.directory, 0o755)
        with store.locked():
            self.assertEqual(store.directory.stat().st_mode & 0o777, 0o700)
            store.write(state)
        loaded = store.load()

        self.assertEqual(loaded, state)
        self.assertEqual(store.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(store.state_path.stat().st_mode & 0o777, 0o600)
        with mock.patch.object(controller.os, "fchmod", None):
            store.write(state)
        self.assertEqual(store.load(), state)
        other = self.make_git_repo_without_trellis()
        wrong = controller.CampaignStore(other, "campaign-1", state_home)
        wrong.directory.mkdir(parents=True)
        wrong.state_path.write_bytes(store.state_path.read_bytes())
        with self.assertRaisesRegex(controller.FleetControllerError, "repository identity"):
            wrong.load()

        linked_home = root.parent / f"{root.name}-linked-state"
        os.symlink(state_home, linked_home)
        with self.assertRaisesRegex(controller.FleetControllerError, "symlink"):
            controller.CampaignStore(root, "campaign-1", linked_home)

    def test_planning_identity_ignores_progress_but_not_scope(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        pristine = json.loads(json.dumps(state))
        self.pass_preflight(controller, state)

        self.assertEqual(
            controller._planning_identity(state),
            controller._planning_identity(pristine),
        )
        pristine["noMerge"] = True
        self.assertNotEqual(
            controller._planning_identity(state),
            controller._planning_identity(pristine),
        )

    def test_identifier_and_json_boundaries_fail_closed(self) -> None:
        controller = self.load_controller()
        root = self.make_git_repo_without_trellis()

        with self.assertRaisesRegex(controller.FleetControllerError, "safe identifier"):
            controller.safe_token("contains/slash", "campaign")
        with self.assertRaisesRegex(controller.FleetControllerError, "full Git SHA"):
            controller.full_sha("A" * 40, "head")

        missing = root / "missing.json"
        with self.assertRaisesRegex(controller.FleetControllerError, "is missing"):
            controller._load_json(missing, "test input")
        with self.assertRaisesRegex(controller.FleetControllerError, "regular file"):
            controller._load_json(root, "test input")

        invalid = root / "invalid.json"
        invalid.write_bytes(b"\xff")
        with self.assertRaisesRegex(controller.FleetControllerError, "UTF-8 JSON"):
            controller._load_json(invalid, "test input")
        invalid.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(controller.FleetControllerError, "JSON object"):
            controller._load_json(invalid, "test input")

        with self.assertRaisesRegex(controller.FleetControllerError, "serializable"):
            controller._json_bytes({"unsupported": object()})
        with self.assertRaisesRegex(controller.FleetControllerError, "exceeds"):
            controller._json_bytes({"large": "x" * controller.MAX_STATE_BYTES})

    def test_cli_campaign_lifecycle_and_controlled_error(self) -> None:
        controller = self.load_controller()
        root = self.make_git_repo_without_trellis()
        fleet, manifest = self.write_inputs(root)
        state_home = root.parent / f"{root.name}-cli-state"
        common = (
            "--repo",
            str(root),
            "--campaign",
            "cli-campaign",
            "--state-home",
            str(state_home),
            "--json",
        )

        status, planned, error = self.run_cli(
            controller,
            "plan",
            *common,
            "--release",
            "0.37.0",
            "--fleet",
            str(fleet),
            "--manifest",
            str(manifest),
            "--consumer",
            "canary-a",
        )
        self.assertEqual((status, error), (0, ""))
        self.assertTrue(planned["changed"])
        status, replayed, _error = self.run_cli(
            controller,
            "plan",
            *common,
            "--release",
            "0.37.0",
            "--fleet",
            str(fleet),
            "--manifest",
            str(manifest),
            "--consumer",
            "canary-a",
        )
        self.assertEqual(status, 0)
        self.assertFalse(replayed["changed"])

        _status, issued, _error = self.run_cli(controller, "next", *common)
        preflight = issued["actions"][0]
        _status, resumed, _error = self.run_cli(controller, "resume", *common)
        self.assertEqual(
            resumed["reconciliation"][0]["action"]["actionId"],
            preflight["actionId"],
        )
        _status, recorded, _error = self.run_cli(
            controller,
            "record",
            *common,
            "--release",
            "0.37.0",
            "--action-id",
            preflight["actionId"],
            "--result",
            "passed",
        )
        self.assertTrue(recorded["changed"])

        status, replayed, error = self.run_cli(
            controller,
            "plan",
            *common,
            "--release",
            "0.37.0",
            "--fleet",
            str(fleet),
            "--manifest",
            str(manifest),
            "--consumer",
            "canary-a",
        )
        self.assertEqual((status, error), (0, ""))
        self.assertFalse(replayed["changed"])
        self.assertEqual(replayed["preflight"]["receiptCount"], 1)

        _status, issued, _error = self.run_cli(controller, "next", *common)
        checkout = issued["actions"][0]
        _status, recorded, _error = self.run_cli(
            controller,
            "record",
            *common,
            "--release",
            "0.37.0",
            "--action-id",
            checkout["actionId"],
            "--consumer",
            "canary-a",
            "--result",
            "at-target",
        )
        self.assertEqual(recorded["status"], "complete")
        _status, report, _error = self.run_cli(controller, "status", *common)
        self.assertEqual(report["lanes"][0]["result"], "at-target")
        _status, valid, _error = self.run_cli(controller, "validate", *common)
        self.assertEqual(valid["status"], "valid")

        status, _output, error = self.run_cli(
            controller,
            "record",
            *common,
            "--release",
            "0.36.0",
            "--action-id",
            "f" * 64,
            "--result",
            "passed",
        )
        self.assertEqual(status, 2)
        self.assertIn("release", error)


if __name__ == "__main__":
    unittest.main()
