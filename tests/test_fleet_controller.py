from __future__ import annotations

import copy

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
                    "schemaVersion": 5,
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

    def pass_lane_action(self, controller, state, *, head=HEAD, pr_number=17):
        action = controller.issue_next(state)[0]
        kwargs = {}
        if action["stage"] == "pr-publication":
            kwargs = {"head": head, "pr_number": pr_number}
        elif action["stage"] in controller.PR_HEAD_STAGES:
            kwargs = {"head": head}
        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=action["consumer"],
            result="passed",
            **kwargs,
        )
        return action

    def block_lane_at_merge(self, controller, state):
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "merge":
            self.pass_lane_action(controller, state)
        action = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=action["consumer"],
            result="review-finding",
            reason_code="taskless-finish-work-invalid",
            blocker="taskless-finish-work-invalid",
            pack_blocker=True,
            head=HEAD,
            pr_number=17,
        )
        return action

    def exhaust_lane(
        self,
        controller,
        state,
        *,
        consumer,
        reason_code="temporary-network",
    ):
        """Burn the lane's remaining automatic attempts at its current stage."""
        action = None
        while self.lane_for(state, consumer)["result"] is None:
            action = self.issued_action_for(controller, state, consumer)
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer=consumer,
                result="retryable-failure",
                reason_code=reason_code,
            )
        self.assertEqual(self.lane_for(state, consumer)["result"], "retry-exhausted")
        return action

    def park_for_decision(
        self,
        controller,
        state,
        *,
        consumer="canary-a",
        stage="review",
        reason_code="remote-reviewer-unavailable-delta-reviewed",
    ):
        """Drive a lane to `stage` and park it awaiting a human decision."""
        self.pass_preflight(controller, state)
        while self.lane_for(state, consumer)["stage"] != stage:
            self.pass_lane_action(controller, state)
        action = self.issued_action_for(controller, state, consumer)
        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer=consumer,
            result="operator-decision",
            reason_code=reason_code,
            head=HEAD,
        )
        lane = self.lane_for(state, consumer)
        self.assertEqual((lane["status"], lane["result"]), ("terminal", "operator-decision"))
        return action

    def lane_for(self, state, consumer):
        """Return the lane owned by consumer, independent of lane ordering."""
        for lane in state["lanes"]:
            if lane["name"] == consumer:
                return lane
        self.fail(f"no lane named {consumer!r}")

    def issued_action_for(self, controller, state, consumer):
        """Issue the next actions and return the one owned by consumer."""
        issued = controller.issue_next(state)
        for action in issued:
            if action["consumer"] == consumer:
                return action
        self.fail(
            f"no issued action for {consumer!r}; issued "
            f"{[action['consumer'] for action in issued]!r}"
        )

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

        fleet_manifest = state["fleetManifest"]
        state["fleetManifest"] = "relative-fleet.json"
        with self.assertRaisesRegex(
            controller.FleetControllerError,
            "fleetManifest must be an absolute path",
        ):
            controller.validate_state(state)
        state["fleetManifest"] = fleet_manifest

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

    def _settle_canaries_at_target(self, controller, state) -> None:
        for canary in ("canary-a", "canary-b"):
            action = self.issued_action_for(controller, state, canary)
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer=canary,
                result="at-target",
            )

    def _drive_both_to_merge_waiting(self, controller, state, consumers, pr_numbers):
        # Both wave lanes share an identical stage sequence and are recorded every
        # round, so they advance in lockstep and reach merge/waiting on the same
        # round — before any merge action is issued for a candidate.
        for _ in range(60):
            if all(
                self.lane_for(state, name)["stage"] == "merge"
                and self.lane_for(state, name)["status"] == "waiting"
                and self.lane_for(state, name)["result"] is None
                for name in consumers
            ):
                return
            recorded_any = False
            for action in controller.issue_next(state):
                if action["consumer"] not in consumers or action["stage"] == "merge":
                    continue
                kwargs = {}
                if action["stage"] == "pr-publication":
                    kwargs = {"head": HEAD, "pr_number": pr_numbers[action["consumer"]]}
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
                recorded_any = True
            if not recorded_any:
                break
        self.fail(f"{consumers} never both reached merge/waiting")

    def test_status_show_issued_peeks_issued_action_without_mutation(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        issued = controller.issue_next(state)[0]

        # --show-issued surfaces the already-issued actionId read-only.
        peeked = controller.status_report(state, show_issued=True)
        lane = next(item for item in peeked["lanes"] if item["name"] == issued["consumer"])
        self.assertEqual(lane["issuedActionId"], issued["actionId"])
        # A peek issues nothing new: the lane is still issued, not re-issued.
        self.assertEqual(controller.issue_next(state), [])

        # The field is opt-in: default status output does not carry it.
        default = controller.status_report(state)
        self.assertNotIn("issuedActionId", default["lanes"][0])

    def test_status_report_surfaces_merge_queue_transparency(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        self._settle_canaries_at_target(controller, state)
        self._drive_both_to_merge_waiting(
            controller, state, ("wave-a", "wave-b"), {"wave-a": 20, "wave-b": 21}
        )

        report = controller.status_report(state)
        candidate = report["plan"]["mergeCandidate"]
        self.assertIn(candidate, ("wave-a", "wave-b"))
        other = "wave-b" if candidate == "wave-a" else "wave-a"

        held = next(item for item in report["lanes"] if item["name"] == other)
        self.assertEqual(held["heldBehind"], candidate)
        self.assertIn(f"merge held behind {candidate}", held["queueNote"])
        # The candidate itself is never reported as held behind anyone.
        winner = next(item for item in report["lanes"] if item["name"] == candidate)
        self.assertIsNone(winner["heldBehind"])
        self.assertIsNone(winner["queueNote"])

    def test_parked_canary_allows_wave_progression_only_with_opt_in(self) -> None:
        controller = self.load_controller()
        for allow, expect_wave in ((False, False), (True, True)):
            with self.subTest(allow_parked_canary=allow):
                root = self.make_git_repo_without_trellis()
                fleet, manifest = self.write_inputs(root)
                state = controller.new_state(
                    repo=root,
                    campaign="campaign-1",
                    release="0.37.0",
                    fleet_path=fleet,
                    pack_manifest_path=manifest,
                    allow_parked_canary=allow,
                )
                self.pass_preflight(controller, state)
                # canary-a settles at-target; canary-b is parked (operator-decision).
                first = self.issued_action_for(controller, state, "canary-a")
                controller.record_result(
                    state,
                    action_id=first["actionId"],
                    release="0.37.0",
                    consumer="canary-a",
                    result="at-target",
                )
                parked = self.issued_action_for(controller, state, "canary-b")
                controller.record_result(
                    state,
                    action_id=parked["actionId"],
                    release="0.37.0",
                    consumer="canary-b",
                    result="operator-decision",
                    reason_code="operator-parked",
                )

                issued = controller.issue_next(state)
                started = sorted(action["consumer"] for action in issued)
                if expect_wave:
                    self.assertEqual(started, ["wave-a", "wave-b"])
                    self.assertEqual(state["status"], "active")
                else:
                    self.assertEqual(issued, [])
                    self.assertEqual(state["status"], "blocked")

    def test_load_provenance_validates_operator_decision_input(self) -> None:
        controller = self.load_controller()
        root = self.make_git_repo_without_trellis()
        good = root / "prov.json"
        good.write_text(
            json.dumps({"reasonCode": "operator-parked", "detail": "held by owner"}),
            encoding="utf-8",
        )
        self.assertEqual(
            controller._load_provenance(good)["reasonCode"], "operator-parked"
        )
        for name, body, message in (
            ("bad.json", "{not json", "not valid JSON"),
            ("list.json", "[]", "must be a JSON object"),
            ("nocode.json", '{"detail": "x"}', "must include a 'reasonCode'"),
            ("badtoken.json", '{"reasonCode": "has spaces"}', "reasonCode"),
        ):
            path = root / name
            path.write_text(body, encoding="utf-8")
            with self.subTest(name=name):
                with self.assertRaisesRegex(controller.FleetControllerError, message):
                    controller._load_provenance(path)

    def test_cli_operator_decision_requires_validated_provenance(self) -> None:
        controller = self.load_controller()
        root = self.make_git_repo_without_trellis()
        fleet, manifest = self.write_inputs(root)
        state_home = root.parent / f"{root.name}-op-state"
        common = (
            "--repo", str(root), "--campaign", "op-campaign",
            "--state-home", str(state_home), "--json",
        )
        self.run_cli(
            controller, "plan", *common, "--release", "0.37.0",
            "--fleet", str(fleet), "--manifest", str(manifest),
            "--consumer", "canary-a",
        )
        _s, issued, _e = self.run_cli(controller, "next", *common)
        preflight = issued["actions"][0]
        self.run_cli(
            controller, "record", *common, "--release", "0.37.0",
            "--action-id", preflight["actionId"], "--result", "passed",
        )
        _s, issued2, _e = self.run_cli(controller, "next", *common)
        checkout = issued2["actions"][0]

        # Negative: operator-decision without --provenance is refused.
        status, _out, error = self.run_cli(
            controller, "record", *common, "--release", "0.37.0",
            "--action-id", checkout["actionId"], "--result", "operator-decision",
        )
        self.assertEqual(status, 2)
        self.assertIn("requires --provenance", error)

        # Positive: a validated provenance file supplies the reason code.
        prov = root / "prov.json"
        prov.write_text(json.dumps({"reasonCode": "operator-parked"}), encoding="utf-8")
        status, recorded, error = self.run_cli(
            controller, "record", *common, "--release", "0.37.0",
            "--action-id", checkout["actionId"], "--consumer", "canary-a",
            "--result", "operator-decision", "--provenance", str(prov),
        )
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(recorded["receipt"]["reasonCode"], "operator-parked")
        self.assertEqual(recorded["receipt"]["result"], "operator-decision")

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
        with self.assertRaisesRegex(
            controller.FleetControllerError, "lane's recorded head"
        ):
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer="wave-a",
                result="review-finding",
                reason_code="review-finding",
                head=OTHER_HEAD,
            )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "lane's recorded head"
        ):
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
        self.assertEqual(
            controller._observations(state)["canary-a"]["state"], "pending"
        )
        self.assertEqual(
            controller._eligible_lanes(
                state, {"canStart": [], "mergeCandidate": None}
            ),
            [],
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

    def test_review_head_advance_republishes_and_establishes_new_epoch(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "review":
            self.pass_lane_action(controller, state)

        review = controller.issue_next(state)[0]
        receipt, changed = controller.record_result(
            state,
            action_id=review["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=HEAD,
            pr_number=17,
        )

        self.assertTrue(changed)
        self.assertEqual(receipt["head"], HEAD)
        lane = state["lanes"][0]
        self.assertEqual(lane["stage"], "pr-publication")
        self.assertEqual(lane["attempt"], 2)
        self.assertEqual(lane["head"], HEAD)
        self.assertEqual(lane["prNumber"], 17)
        controller.validate_state(state)

        publication = controller.issue_next(state)[0]
        self.assertEqual(publication["stage"], "pr-publication")
        self.assertEqual(publication["attempt"], 2)
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(
            controller.FleetControllerError, "reuse the current PR number"
        ):
            controller.record_result(
                state,
                action_id=publication["actionId"],
                release="0.37.0",
                consumer="wave-a",
                result="passed",
                head=OTHER_HEAD,
                pr_number=18,
            )
        self.assertEqual(state, before)
        controller.record_result(
            state,
            action_id=publication["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
            head=OTHER_HEAD,
            pr_number=17,
        )
        review = controller.issue_next(state)[0]
        self.assertEqual(review["stage"], "review")
        self.assertEqual(review["attempt"], 2)
        controller.record_result(
            state,
            action_id=review["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
            head=OTHER_HEAD,
        )
        while state["status"] != "complete":
            self.pass_lane_action(controller, state, head=OTHER_HEAD)

        publication_heads = [
            item["head"]
            for item in lane["receipts"]
            if item["stage"] == "pr-publication" and item["result"] == "passed"
        ]
        self.assertEqual(publication_heads, [HEAD, OTHER_HEAD])
        self.assertEqual(lane["head"], OTHER_HEAD)
        self.assertEqual(lane["result"], "merged")
        controller.validate_state(state)

    def test_merge_eligibility_head_advance_routes_to_republication(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "merge-eligibility":
            self.pass_lane_action(controller, state)

        eligibility = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=eligibility["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=HEAD,
            pr_number=17,
        )

        lane = state["lanes"][0]
        self.assertEqual(lane["stage"], "pr-publication")
        self.assertEqual(lane["attempt"], 2)
        self.assertEqual(controller.issue_next(state)[0]["stage"], "pr-publication")
        controller.validate_state(state)

    def test_merge_head_advance_republishes_finish_work_successor(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "merge":
            self.pass_lane_action(controller, state)

        merge = controller.issue_next(state)[0]
        receipt, changed = controller.record_result(
            state,
            action_id=merge["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=HEAD,
            pr_number=17,
        )

        self.assertTrue(changed)
        self.assertEqual(receipt["stage"], "merge")
        self.assertEqual(receipt["head"], HEAD)
        lane = state["lanes"][0]
        self.assertEqual(lane["stage"], "pr-publication")
        self.assertEqual(lane["attempt"], 2)
        self.assertEqual(lane["head"], HEAD)
        self.assertEqual(lane["prNumber"], 17)
        controller.validate_state(state)

        publication = controller.issue_next(state)[0]
        self.assertEqual(publication["stage"], "pr-publication")
        self.assertEqual(publication["attempt"], 2)
        controller.record_result(
            state,
            action_id=publication["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
            head=OTHER_HEAD,
            pr_number=17,
        )
        while state["status"] != "complete":
            self.pass_lane_action(controller, state, head=OTHER_HEAD)

        merge_receipts = [
            item for item in lane["receipts"] if item["stage"] == "merge"
        ]
        self.assertEqual(
            [
                (item["attempt"], item["result"], item["head"])
                for item in merge_receipts
            ],
            [
                (1, "retryable-failure", HEAD),
                (2, "passed", OTHER_HEAD),
            ],
        )
        self.assertEqual(lane["head"], OTHER_HEAD)
        self.assertEqual(lane["result"], "merged")
        controller.validate_state(state)

    def test_second_merge_head_advance_exhausts_bounded_retry(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "merge":
            self.pass_lane_action(controller, state)

        first_merge = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=first_merge["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=HEAD,
            pr_number=17,
        )
        self.pass_lane_action(controller, state, head=OTHER_HEAD)
        while state["lanes"][0]["stage"] != "merge":
            self.pass_lane_action(controller, state, head=OTHER_HEAD)

        second_merge = controller.issue_next(state)[0]
        self.assertEqual(second_merge["attempt"], 2)
        controller.record_result(
            state,
            action_id=second_merge["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=OTHER_HEAD,
            pr_number=17,
        )

        lane = state["lanes"][0]
        self.assertEqual(lane["status"], "terminal")
        self.assertEqual(lane["result"], "retry-exhausted")
        self.assertEqual(lane["blocker"], controller.PR_HEAD_ADVANCED_REASON)
        controller.validate_state(state)

    def test_head_advance_retry_is_bounded_to_two_review_attempts(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "review":
            self.pass_lane_action(controller, state)

        first_review = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=first_review["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=HEAD,
            pr_number=17,
        )
        self.pass_lane_action(controller, state, head=OTHER_HEAD)
        second_review = controller.issue_next(state)[0]
        controller.record_result(
            state,
            action_id=second_review["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=OTHER_HEAD,
            pr_number=17,
        )

        lane = state["lanes"][0]
        self.assertEqual(lane["stage"], "review")
        self.assertEqual(lane["result"], "retry-exhausted")
        self.assertEqual(lane["blocker"], controller.PR_HEAD_ADVANCED_REASON)
        controller.validate_state(state)

    def test_head_advance_reason_rejects_invalid_uses_without_mutation(self) -> None:
        controller = self.load_controller()

        for result, reason_code, blocker, pack_blocker, pr_number, message in (
            (
                "product-failure",
                controller.PR_HEAD_ADVANCED_REASON,
                None,
                False,
                17,
                "requires a retryable-failure",
            ),
            (
                "retryable-failure",
                controller.PR_HEAD_ADVANCED_REASON,
                None,
                False,
                None,
                "requires head and PR number",
            ),
            (
                "retryable-failure",
                controller.PR_HEAD_ADVANCED_REASON,
                "contradiction",
                True,
                17,
                "forbids blocker evidence",
            ),
            (
                "retryable-failure",
                controller.PR_HEAD_ADVANCED_REASON,
                None,
                False,
                18,
                "current PR number",
            ),
        ):
            with self.subTest(message=message):
                _root, _fleet, _manifest, state = self.state(
                    controller, selected=("wave-a",)
                )
                self.pass_preflight(controller, state)
                while state["lanes"][0]["stage"] != "review":
                    self.pass_lane_action(controller, state)
                review = controller.issue_next(state)[0]
                before = copy.deepcopy(state)
                with self.assertRaisesRegex(controller.FleetControllerError, message):
                    controller.record_result(
                        state,
                        action_id=review["actionId"],
                        release="0.37.0",
                        consumer="wave-a",
                        result=result,
                        reason_code=reason_code,
                        blocker=blocker,
                        pack_blocker=pack_blocker,
                        head=HEAD,
                        pr_number=pr_number,
                    )
                self.assertEqual(state, before)

        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "local-checks":
            self.pass_lane_action(controller, state)
        local_checks = controller.issue_next(state)[0]
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(
            controller.FleetControllerError,
            "at review, merge-eligibility, or merge",
        ):
            controller.record_result(
                state,
                action_id=local_checks["actionId"],
                release="0.37.0",
                consumer="wave-a",
                result="retryable-failure",
                reason_code=controller.PR_HEAD_ADVANCED_REASON,
                head=HEAD,
                pr_number=17,
            )
        self.assertEqual(state, before)

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
        with self.assertRaisesRegex(controller.FleetControllerError, "not currently issued"):
            controller.record_result(
                state,
                action_id="f" * 64,
                release="0.37.0",
                consumer=None,
                result="review-finding",
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

        _root, _fleet, _manifest, parked = self.state(
            controller, selected=("canary-a",)
        )
        self.pass_preflight(controller, parked)
        decision = controller.issue_next(parked)[0]
        controller.record_result(
            parked,
            action_id=decision["actionId"],
            release="0.37.0",
            consumer="canary-a",
            result="operator-decision",
            reason_code="operator-approval-required",
        )
        with self.assertRaisesRegex(
            controller.FleetControllerError,
            "requires a terminal ownership-skip",
        ):
            controller.retry_consumer(parked, "canary-a")

    def test_corrective_release_reopens_merge_pack_blocker_at_publication(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        blocked_action = self.block_lane_at_merge(controller, state)
        old_publication = next(
            receipt
            for receipt in state["lanes"][0]["receipts"]
            if receipt["stage"] == "pr-publication"
        )

        recovery, changed = controller.recover_pack_blocker(
            state,
            consumer="wave-a",
            corrective_release="0.38.0",
            actual_release="0.38.0",
        )

        self.assertTrue(changed)
        self.assertEqual(recovery["fromActionId"], blocked_action["actionId"])
        self.assertEqual(recovery["fromHead"], HEAD)
        self.assertEqual(recovery["toStage"], "pr-publication")
        self.assertEqual(state["status"], "active")
        lane = state["lanes"][0]
        self.assertEqual(lane["stage"], "pr-publication")
        self.assertEqual(lane["attempt"], 2)
        self.assertIsNone(lane["result"])
        self.assertFalse(lane["packBlocker"])
        self.assertEqual(lane["receipts"][-1]["result"], "review-finding")
        replay, replay_changed = controller.recover_pack_blocker(
            state,
            consumer="wave-a",
            corrective_release="0.38.0",
            actual_release="0.38.0",
        )
        self.assertFalse(replay_changed)
        self.assertEqual(replay, recovery)
        recovered_state = copy.deepcopy(state)
        with self.assertRaisesRegex(
            controller.FleetControllerError, "already bound to a different release"
        ):
            controller.recover_pack_blocker(
                state,
                consumer="wave-a",
                corrective_release="0.39.0",
                actual_release="0.39.0",
            )
        self.assertEqual(state, recovered_state)

        publication = controller.issue_next(state)[0]
        self.assertEqual(publication["stage"], "pr-publication")
        self.assertEqual(publication["attempt"], 2)
        self.assertNotEqual(publication["actionId"], old_publication["actionId"])
        controller.record_result(
            state,
            action_id=publication["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
            head=OTHER_HEAD,
            pr_number=17,
        )
        review = controller.issue_next(state)[0]
        self.assertEqual(review["stage"], "review")
        self.assertEqual(review["attempt"], 2)
        self.assertNotEqual(
            review["actionId"],
            next(
                receipt["actionId"]
                for receipt in lane["receipts"]
                if receipt["stage"] == "review" and receipt["attempt"] == 1
            ),
        )
        controller.record_result(
            state,
            action_id=review["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
            head=OTHER_HEAD,
        )
        controller.validate_state(state)
        self.assertEqual(state["lanes"][0]["head"], OTHER_HEAD)
        self.assertEqual(
            controller.status_report(state)["recoveries"][0]["correctiveRelease"],
            "0.38.0",
        )

    def test_corrective_recovery_rejects_wrong_release_and_lane_state(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, waiting = self.state(
            controller, selected=("wave-a",)
        )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "must differ"
        ):
            controller.recover_pack_blocker(
                waiting,
                consumer="wave-a",
                corrective_release="0.37.0",
                actual_release="0.37.0",
            )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "current pack manifest"
        ):
            controller.recover_pack_blocker(
                waiting,
                consumer="wave-a",
                corrective_release="0.38.0",
                actual_release="0.39.0",
            )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "no blocker receipt"
        ):
            controller.recover_pack_blocker(
                waiting,
                consumer="wave-a",
                corrective_release="0.38.0",
                actual_release="0.38.0",
            )

        _root, _fleet, _manifest, ownership = self.state(
            controller, selected=("wave-a",)
        )
        self.pass_preflight(controller, ownership)
        action = controller.issue_next(ownership)[0]
        controller.record_result(
            ownership,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="ownership-skip",
            reason_code="active-external-owner",
        )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "terminal merge-stage"
        ):
            controller.recover_pack_blocker(
                ownership,
                consumer="wave-a",
                corrective_release="0.38.0",
                actual_release="0.38.0",
            )

    def test_schema_one_campaign_without_recoveries_is_normalized(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        state.pop("recoveries")

        normalized = controller._normalize_state(state)

        self.assertEqual(normalized["recoveries"], [])
        controller.validate_state(normalized)

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

    def test_git_evidence_compares_the_bound_checkout_digest(self) -> None:
        controller = self.load_controller()
        root = self.make_git_repo_without_trellis()

        self.assertTrue(
            controller._git_evidence(root, controller._digest_path(root))[
                "checkoutDigestMatches"
            ]
        )
        self.assertFalse(
            controller._git_evidence(root, "0" * 64)["checkoutDigestMatches"]
        )

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
        with mock.patch.object(controller.os, "open", return_value=17) as opened:
            self.assertEqual(store._create_lock(), 17)
        flags = opened.call_args.args[1]
        if hasattr(controller.os, "O_NOFOLLOW"):
            self.assertTrue(flags & controller.os.O_NOFOLLOW)
        if hasattr(controller.os, "O_CLOEXEC"):
            self.assertTrue(flags & controller.os.O_CLOEXEC)
        with mock.patch.object(controller.os, "fchmod", None):
            store.write(state)
        self.assertEqual(store.load(), state)
        with mock.patch.object(
            controller.os,
            "open",
            side_effect=PermissionError("lock denied"),
        ), self.assertRaisesRegex(
            controller.FleetControllerError, "lock cannot be created"
        ):
            with store.locked():
                self.fail("lock creation should fail")
        store.lock_path.write_text("stale\n", encoding="utf-8")
        os.utime(store.lock_path, (0, 0))
        with mock.patch.object(
            controller.os,
            "open",
            side_effect=(FileExistsError(), FileExistsError()),
        ), self.assertRaisesRegex(controller.FleetControllerError, "busy"):
            with store.locked():
                self.fail("stale lock race should fail")
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
        with mock.patch.object(
            controller.CampaignStore,
            "_prepare_directory",
            side_effect=PermissionError(13, "Permission denied", "/private/state"),
        ):
            status, output, error = self.run_cli(
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
        self.assertEqual((status, output), (2, None))
        self.assertEqual(
            error, "error: filesystem operation failed: Permission denied\n"
        )
        self.assertNotIn("/private/state", error)

    def test_cli_corrective_recovery_requires_matching_manifest_and_one_mode(self) -> None:
        controller = self.load_controller()
        root, _fleet, manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.block_lane_at_merge(controller, state)
        state_home = root.parent / f"{root.name}-recovery-state"
        store = controller.CampaignStore(root, "campaign-1", state_home)
        with store.locked():
            store.write(state)
        common = (
            "--repo",
            str(root),
            "--campaign",
            "campaign-1",
            "--state-home",
            str(state_home),
            "--json",
        )

        status, output, error = self.run_cli(
            controller,
            "resume",
            *common,
            "--recover-consumer",
            "wave-a",
            "--corrective-release",
            "0.38.0",
        )
        self.assertEqual((status, output), (2, None))
        self.assertIn("current pack manifest", error)

        manifest.write_text(json.dumps({"version": "0.38.0"}), encoding="utf-8")
        status, output, error = self.run_cli(
            controller,
            "resume",
            *common,
            "--recover-consumer",
            "wave-a",
            "--corrective-release",
            "0.38.0",
        )
        self.assertEqual((status, error), (0, ""))
        self.assertTrue(output["changed"])
        self.assertEqual(output["recovery"]["toStage"], "pr-publication")
        self.assertEqual(output["recoveries"], [output["recovery"]])

        status, output, error = self.run_cli(
            controller,
            "resume",
            *common,
            "--recover-consumer",
            "wave-a",
            "--retry-consumer",
            "wave-a",
            "--corrective-release",
            "0.38.0",
        )
        self.assertEqual((status, output), (2, None))
        self.assertIn("only one recovery mode", error)

    def test_exhaustion_recovery_resumes_the_lane_at_the_exhausted_stage(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "local-checks":
            self.pass_lane_action(controller, state)
        exhausted = self.exhaust_lane(controller, state, consumer="canary-a")
        self.assertEqual(state["status"], "blocked")
        receipts = copy.deepcopy(state["lanes"][0]["receipts"])

        recovery, changed = controller.recover_retry_exhausted(
            state,
            consumer="canary-a",
            exhausted_action_id=exhausted["actionId"],
            release="0.37.0",
        )

        self.assertTrue(changed)
        lane = state["lanes"][0]
        self.assertEqual(
            (lane["status"], lane["result"], lane["stage"], lane["attempt"]),
            ("waiting", None, "local-checks", 3),
        )
        self.assertIsNone(lane["blocker"])
        self.assertFalse(lane["packBlocker"])
        self.assertEqual(lane["receipts"], receipts)
        self.assertEqual(state["status"], "active")
        self.assertEqual(
            recovery,
            {
                "consumer": "canary-a",
                "fromActionId": exhausted["actionId"],
                "fromAttempt": 2,
                "fromBlocker": "temporary-network",
                "fromStage": "local-checks",
                "kind": "retry-exhausted",
                "recordedAt": recovery["recordedAt"],
                "toAttempt": 3,
                "toStage": "local-checks",
            },
        )
        self.assertEqual(state["recoveries"], [recovery])

        issued = controller.issue_next(state)

        self.assertIn(
            ("canary-a", "local-checks", 3),
            [(item["consumer"], item["stage"], item["attempt"]) for item in issued],
        )

    def test_exhaustion_recovery_refuses_mismatched_evidence(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        exhausted = self.exhaust_lane(controller, state, consumer="canary-a")
        lane = state["lanes"][0]

        def recover(**overrides):
            arguments = {
                "consumer": "canary-a",
                "exhausted_action_id": exhausted["actionId"],
                "release": "0.37.0",
            }
            arguments.update(overrides)
            return controller.recover_retry_exhausted(state, **arguments)

        with self.assertRaisesRegex(
            controller.FleetControllerError, "release does not match campaign release"
        ):
            recover(release="0.38.0")
        with self.assertRaisesRegex(
            controller.FleetControllerError, "consumer is outside the campaign"
        ):
            recover(consumer="not-a-consumer")
        with self.assertRaisesRegex(
            controller.FleetControllerError, "terminal retry-exhausted lane"
        ):
            recover(consumer="canary-b")
        with self.assertRaisesRegex(
            controller.FleetControllerError, "not the lane's latest receipt"
        ):
            recover(exhausted_action_id="some-other-action")

        lane["blocker"] = "a-different-reason"
        with self.assertRaisesRegex(
            controller.FleetControllerError, "receipt does not match the lane"
        ):
            recover()
        lane["blocker"] = "temporary-network"

        lane["attempt"] = 5
        with self.assertRaisesRegex(
            controller.FleetControllerError, "attempt does not match the lane attempt"
        ):
            recover()
        lane["attempt"] = 2

        self.assertEqual(state["recoveries"], [])

    def test_exhaustion_recovery_refuses_every_other_terminal_result(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        exhausted = self.exhaust_lane(controller, state, consumer="canary-a")
        lane = state["lanes"][0]
        others = controller.TERMINAL_RESULTS - {"retry-exhausted"}
        self.assertEqual(len(others), 8)

        for result in sorted(others):
            lane["result"] = result
            with self.assertRaisesRegex(
                controller.FleetControllerError, "terminal retry-exhausted lane"
            ):
                controller.recover_retry_exhausted(
                    state,
                    consumer="canary-a",
                    exhausted_action_id=exhausted["actionId"],
                    release="0.37.0",
                )

        self.assertEqual(state["recoveries"], [])

    def test_exhaustion_recovery_is_idempotent_and_capped_per_stage(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        while state["lanes"][0]["stage"] != "local-checks":
            self.pass_lane_action(controller, state)

        def recover(action_id):
            return controller.recover_retry_exhausted(
                state,
                consumer="canary-a",
                exhausted_action_id=action_id,
                release="0.37.0",
            )

        def exhaust_again():
            action = next(
                item
                for item in controller.issue_next(state)
                if item["consumer"] == "canary-a"
            )
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer="canary-a",
                result="retryable-failure",
                reason_code="temporary-network",
            )
            self.assertEqual(state["lanes"][0]["result"], "retry-exhausted")
            return action

        first_exhausted = self.exhaust_lane(controller, state, consumer="canary-a")
        first, changed = recover(first_exhausted["actionId"])
        self.assertTrue(changed)
        self.assertEqual(recover(first_exhausted["actionId"]), (first, False))
        self.assertEqual(state["recoveries"], [first])

        # One further automatic attempt is granted, not two: the recovered lane
        # re-terminates on the next retryable failure.
        second_exhausted = exhaust_again()
        self.assertEqual(second_exhausted["attempt"], 3)
        self.assertEqual(state["lanes"][0]["attempt"], 3)

        second, changed = recover(second_exhausted["actionId"])
        self.assertTrue(changed)
        self.assertEqual(second["toAttempt"], 4)
        self.assertEqual(state["lanes"][0]["attempt"], 4)

        third_exhausted = exhaust_again()
        with self.assertRaisesRegex(
            controller.FleetControllerError, "limit is reached"
        ):
            recover(third_exhausted["actionId"])
        # A replay still returns its record once the cap is full.
        self.assertEqual(recover(first_exhausted["actionId"]), (first, False))
        self.assertEqual(state["recoveries"], [first, second])

    def test_cli_exhaustion_recovery_requires_its_own_selector_and_evidence(
        self,
    ) -> None:
        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        exhausted = self.exhaust_lane(controller, state, consumer="canary-a")
        state_home = root.parent / f"{root.name}-exhaustion-state"
        store = controller.CampaignStore(root, "campaign-1", state_home)
        with store.locked():
            store.write(state)
        common = (
            "--repo",
            str(root),
            "--campaign",
            "campaign-1",
            "--state-home",
            str(state_home),
            "--json",
        )
        selector = (
            "--recover-exhausted-consumer",
            "canary-a",
            "--exhausted-action",
            exhausted["actionId"],
        )

        status, output, error = self.run_cli(controller, "resume", *common)
        self.assertEqual((status, error), (0, ""))
        self.assertNotIn("recovery", output)

        status, output, error = self.run_cli(
            controller, "resume", *common, "--exhausted-action", exhausted["actionId"]
        )
        self.assertEqual((status, output), (2, None))
        self.assertIn("exhausted-action requires recover-exhausted-consumer", error)

        status, output, error = self.run_cli(
            controller, "resume", *common, "--recover-exhausted-consumer", "canary-a"
        )
        self.assertEqual((status, output), (2, None))
        self.assertIn("requires exhausted-action", error)

        status, output, error = self.run_cli(controller, "resume", *common, *selector)
        self.assertEqual((status, output), (2, None))
        self.assertIn("requires release", error)

        status, output, error = self.run_cli(
            controller,
            "resume",
            *common,
            *selector,
            "--release",
            "0.37.0",
            "--corrective-release",
            "0.38.0",
        )
        self.assertEqual((status, output), (2, None))
        self.assertIn("corrective-release is valid only with recover-consumer", error)

        status, output, error = self.run_cli(
            controller,
            "resume",
            *common,
            *selector,
            "--release",
            "0.37.0",
            "--retry-consumer",
            "canary-a",
        )
        self.assertEqual((status, output), (2, None))
        self.assertIn("only one recovery mode", error)

        foreign = store.directory / "campaign-2.json"
        foreign.write_bytes(store.state_path.read_bytes())
        status, output, error = self.run_cli(
            controller,
            "resume",
            "--repo",
            str(root),
            "--campaign",
            "campaign-2",
            "--state-home",
            str(state_home),
            "--json",
            *selector,
            "--release",
            "0.37.0",
        )
        self.assertEqual((status, output), (2, None))
        self.assertIn("campaign identity does not match", error)

        status, output, error = self.run_cli(
            controller, "resume", *common, *selector, "--release", "0.37.0"
        )
        self.assertEqual((status, error), (0, ""))
        self.assertTrue(output["changed"])
        self.assertEqual(output["recovery"]["kind"], "retry-exhausted")
        self.assertEqual(output["recovery"]["fromStage"], "checkout-validation")
        self.assertEqual(output["recoveries"], [output["recovery"]])
        persisted = json.loads(store.state_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["schemaVersion"], 2)
        self.assertEqual(persisted["lanes"][0]["status"], "waiting")
        self.assertIsNone(persisted["lanes"][0]["result"])

    def test_exhaustion_recovery_ignores_the_current_pack_manifest_version(
        self,
    ) -> None:
        controller = self.load_controller()
        root, _fleet, manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        exhausted = self.exhaust_lane(controller, state, consumer="canary-a")
        state_home = root.parent / f"{root.name}-stale-manifest-state"
        store = controller.CampaignStore(root, "campaign-1", state_home)
        with store.locked():
            store.write(state)
        # The pack moves on while the campaign stays bound to its own release.
        manifest.write_text(json.dumps({"version": "0.39.0"}), encoding="utf-8")
        (root / "manifest.json").write_text(
            json.dumps({"version": "0.39.0"}), encoding="utf-8"
        )

        status, output, error = self.run_cli(
            controller,
            "resume",
            "--repo",
            str(root),
            "--campaign",
            "campaign-1",
            "--state-home",
            str(state_home),
            "--json",
            "--recover-exhausted-consumer",
            "canary-a",
            "--exhausted-action",
            exhausted["actionId"],
            "--release",
            "0.37.0",
        )

        self.assertEqual((status, error), (0, ""))
        self.assertTrue(output["changed"])
        self.assertEqual(output["recovery"]["kind"], "retry-exhausted")

    def test_schema_one_recovery_rows_migrate_to_the_tagged_union(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        legacy = copy.deepcopy(state)
        legacy["schemaVersion"] = 1
        legacy["recoveries"] = [
            {
                "consumer": "canary-a",
                "correctiveRelease": "0.38.0",
                "fromActionId": "an-earlier-merge-action",
                "fromAttempt": 1,
                "fromBlocker": "taskless-finish-work-invalid",
                "fromHead": HEAD,
                "fromPrNumber": 17,
                "fromStage": "merge",
                "recordedAt": "2026-07-29T00:00:00Z",
                "toAttempt": 2,
                "toStage": "pr-publication",
            }
        ]
        source = copy.deepcopy(legacy)

        normalized = controller._normalize_state(legacy)

        self.assertEqual(normalized["schemaVersion"], 2)
        self.assertEqual(normalized["recoveries"][0]["kind"], "pack-blocker")
        controller.validate_state(normalized)
        # Neither the mapping nor its nested recovery rows are mutated in place.
        self.assertEqual(legacy, source)

        legacy.pop("recoveries")
        normalized = controller._normalize_state(legacy)

        self.assertEqual(normalized["recoveries"], [])
        self.assertEqual(normalized["schemaVersion"], 2)
        controller.validate_state(normalized)
        self.assertEqual(legacy["schemaVersion"], 1)

    def test_schema_one_state_file_migrates_only_on_a_mutating_command(self) -> None:
        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(controller)
        self.pass_preflight(controller, state)
        state_home = root.parent / f"{root.name}-migration-state"
        store = controller.CampaignStore(root, "campaign-1", state_home)
        with store.locked():
            store.write(state)

        def rewrite(payload):
            store.state_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.chmod(store.state_path, 0o600)

        legacy = json.loads(store.state_path.read_text(encoding="utf-8"))
        legacy["schemaVersion"] = 1
        rewrite(legacy)
        before = store.state_path.read_bytes()
        common = (
            "--repo",
            str(root),
            "--campaign",
            "campaign-1",
            "--state-home",
            str(state_home),
            "--json",
        )

        status, output, error = self.run_cli(controller, "validate", *common)
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(output["status"], "valid")
        status, output, error = self.run_cli(controller, "status", *common)
        self.assertEqual((status, error), (0, ""))
        self.assertEqual(store.state_path.read_bytes(), before)

        status, _output, error = self.run_cli(controller, "next", *common)
        self.assertEqual((status, error), (0, ""))
        persisted = json.loads(store.state_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["schemaVersion"], 2)

        persisted["schemaVersion"] = 3
        rewrite(persisted)
        status, output, error = self.run_cli(controller, "validate", *common)
        self.assertEqual((status, output), (2, None))
        self.assertIn("campaign schemaVersion must be 2", error)

    def test_schema_two_state_is_refused_by_a_schema_one_validator(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.assertEqual(state["schemaVersion"], 2)

        # Migration is one-way. A rolled-back controller fails on the version
        # check, which names the cause, rather than on an unknown recovery field.
        with mock.patch.object(controller, "SCHEMA_VERSION", 1):
            with self.assertRaisesRegex(
                controller.FleetControllerError, "campaign schemaVersion must be 1"
            ):
                controller.validate_state(state)

    def test_recovery_rows_are_validated_per_kind(self) -> None:
        controller = self.load_controller()
        exhaustion = {
            "consumer": "canary-a",
            "fromActionId": "an-exhausted-action",
            "fromAttempt": 2,
            "fromBlocker": "temporary-network",
            "fromStage": "local-checks",
            "kind": "retry-exhausted",
            "recordedAt": "2026-07-29T00:00:00Z",
            "toAttempt": 3,
            "toStage": "local-checks",
        }
        pack_blocker = {
            "consumer": "canary-a",
            "correctiveRelease": "0.38.0",
            "fromActionId": "a-merge-action",
            "fromAttempt": 1,
            "fromBlocker": "taskless-finish-work-invalid",
            "fromHead": HEAD,
            "fromPrNumber": 17,
            "fromStage": "merge",
            "kind": "pack-blocker",
            "recordedAt": "2026-07-29T00:00:00Z",
            "toAttempt": 2,
            "toStage": "pr-publication",
        }
        controller.validate_recovery(exhaustion, "recoveries[0]")
        controller.validate_recovery(pack_blocker, "recoveries[1]")

        for field, value in (
            ("correctiveRelease", "0.38.0"),
            ("fromHead", HEAD),
            ("fromPrNumber", 17),
        ):
            with self.assertRaisesRegex(
                controller.FleetControllerError, f"unknown field: {field}"
            ):
                controller.validate_recovery(
                    {**exhaustion, field: value}, "recoveries[0]"
                )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "toStage must match fromStage"
        ):
            controller.validate_recovery(
                {**exhaustion, "toStage": "review"}, "recoveries[0]"
            )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "fromStage is invalid"
        ):
            controller.validate_recovery(
                {**exhaustion, "fromStage": "not-a-stage", "toStage": "not-a-stage"},
                "recoveries[0]",
            )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "fromStage must be merge"
        ):
            controller.validate_recovery(
                {**pack_blocker, "fromStage": "review"}, "recoveries[1]"
            )
        for kind in ("both", None):
            with self.assertRaisesRegex(
                controller.FleetControllerError, "kind is invalid"
            ):
                controller.validate_recovery({**exhaustion, "kind": kind}, "recoveries[0]")
        untagged = {key: value for key, value in exhaustion.items() if key != "kind"}
        with self.assertRaisesRegex(controller.FleetControllerError, "kind is invalid"):
            controller.validate_recovery(untagged, "recoveries[0]")

    def test_pack_blocker_recovery_scans_past_exhaustion_rows(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        self.block_lane_at_merge(controller, state)
        state["recoveries"].append(
            {
                "consumer": "wave-a",
                "fromActionId": "an-earlier-exhausted-action",
                "fromAttempt": 2,
                "fromBlocker": "temporary-network",
                "fromStage": "local-checks",
                "kind": "retry-exhausted",
                "recordedAt": "2026-07-29T00:00:00Z",
                "toAttempt": 3,
                "toStage": "local-checks",
            }
        )

        recovery, changed = controller.recover_pack_blocker(
            state,
            consumer="wave-a",
            corrective_release="0.38.0",
            actual_release="0.38.0",
        )

        self.assertTrue(changed)
        self.assertEqual(recovery["kind"], "pack-blocker")
        self.assertEqual(
            [item["kind"] for item in state["recoveries"]],
            ["retry-exhausted", "pack-blocker"],
        )

    def test_pack_blocker_recovery_never_dereferences_an_exhaustion_row(self) -> None:
        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("wave-a",)
        )
        blocker = self.block_lane_at_merge(controller, state)
        state["recoveries"].append(
            {
                "consumer": "wave-a",
                "fromActionId": blocker["actionId"],
                "fromAttempt": blocker["attempt"],
                "fromBlocker": "temporary-network",
                "fromStage": "local-checks",
                "kind": "retry-exhausted",
                "recordedAt": "2026-07-29T00:00:00Z",
                "toAttempt": 3,
                "toStage": "local-checks",
            }
        )

        # Before the lookup became kind-aware this raised a bare
        # KeyError('correctiveRelease') instead of a typed controller error.
        with self.assertRaisesRegex(
            controller.FleetControllerError, "unique source actions"
        ):
            controller.recover_pack_blocker(
                state,
                consumer="wave-a",
                corrective_release="0.38.0",
                actual_release="0.38.0",
            )
    def test_a_decided_lane_rejoins_the_campaign_and_reaches_merged(self) -> None:
        """The state the controller creates for "a human must decide" was the one
        terminal state it could not accept a decision for.

        `--retry-consumer` wants `ownership-skip`, `--recover-consumer` wants a
        merge-stage pack blocker, `--recover-exhausted-consumer` wants
        `retry-exhausted`. A lane parked on `operator-decision` matched none of
        them, so an operator who decided to proceed had no supported way to
        finish it and the ledger stayed wrong forever.
        """

        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        parked = self.park_for_decision(controller, state)
        receipts_before = copy.deepcopy(state["lanes"][0]["receipts"])

        recovery, changed = controller.record_operator_decision(
            state,
            consumer="canary-a",
            decision="proceed",
            decided_by="operator-sdelmas",
            decision_head=HEAD,
            release="0.37.0",
        )

        self.assertTrue(changed)
        lane = state["lanes"][0]
        self.assertEqual(
            (lane["status"], lane["result"], lane["stage"]),
            ("waiting", None, "review"),
        )
        self.assertIsNone(lane["blocker"])
        # Reviving records the decision; it never rewrites what was received.
        self.assertEqual(lane["receipts"], receipts_before)
        self.assertEqual(
            recovery,
            {
                "consumer": "canary-a",
                "decidedBy": "operator-sdelmas",
                "decision": "proceed",
                "decisionHead": HEAD,
                "fromActionId": parked["actionId"],
                "fromAttempt": parked["attempt"],
                "fromBlocker": "remote-reviewer-unavailable-delta-reviewed",
                "fromStage": "review",
                "kind": "operator-decision",
                "recordedAt": recovery["recordedAt"],
                "toAttempt": parked["attempt"] + 1,
                "toStage": "review",
            },
        )

        while self.lane_for(state, "canary-a")["result"] is None:
            self.pass_lane_action(controller, state)

        lane = state["lanes"][0]
        self.assertEqual((lane["status"], lane["result"]), ("terminal", "merged"))
        # The whole chain survives: the pre-decision receipts are still the
        # prefix of the lane's history, so the ledger shows a lane that was
        # parked, decided, and completed.
        self.assertEqual(lane["receipts"][: len(receipts_before)], receipts_before)
        self.assertEqual(state["recoveries"], [recovery])
        controller.validate_state(state)

    def test_the_decision_path_refuses_every_other_terminal_result(self) -> None:
        """Guarded on `operator-decision` exactly as the other three are guarded
        on their own results."""

        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller)
        self.park_for_decision(controller, state)
        lane = state["lanes"][0]
        others = controller.TERMINAL_RESULTS - {"operator-decision"}
        self.assertEqual(len(others), 8)

        for result in sorted(others):
            lane["result"] = result
            with self.assertRaisesRegex(
                controller.FleetControllerError,
                "terminal operator-decision lane",
            ):
                controller.record_operator_decision(
                    state,
                    consumer="canary-a",
                    decision="proceed",
                    decided_by="operator-sdelmas",
                    decision_head=HEAD,
                    release="0.37.0",
                )

        self.assertEqual(state["recoveries"], [])

    def test_reviving_a_lane_reopens_a_complete_campaign(self) -> None:
        """A campaign is `complete` because every lane is terminal. Reviving one
        means that is no longer true, and the state must say so rather than
        reporting a campaign that still has work as finished."""

        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        self.park_for_decision(controller, state)

        self.assertEqual(state["status"], "complete")
        controller.validate_state(state)
        self.assertEqual(controller.issue_next(state), [])

        controller.record_operator_decision(
            state,
            consumer="canary-a",
            decision="proceed",
            decided_by="operator-sdelmas",
            decision_head=HEAD,
            release="0.37.0",
        )

        self.assertEqual(state["status"], "active")
        controller.validate_state(state)
        issued = controller.issue_next(state)
        self.assertEqual(
            [(item["consumer"], item["stage"]) for item in issued],
            [("canary-a", "review")],
        )

    def test_the_decision_is_bound_to_a_decider_and_a_head(self) -> None:
        """Who decided, and against which head. A lane that moved after the
        operator looked at it cannot inherit their answer, and re-answering the
        same parked action with a different decision is refused rather than
        silently overwriting the record."""

        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        self.park_for_decision(controller, state)

        def decide(**overrides):
            arguments = {
                "consumer": "canary-a",
                "decision": "proceed",
                "decided_by": "operator-sdelmas",
                "decision_head": HEAD,
                "release": "0.37.0",
            }
            arguments.update(overrides)
            return controller.record_operator_decision(state, **arguments)

        with self.assertRaisesRegex(
            controller.FleetControllerError, "head does not match the lane head"
        ):
            decide(decision_head=OTHER_HEAD)
        with self.assertRaisesRegex(
            controller.FleetControllerError, "release does not match campaign release"
        ):
            decide(release="0.38.0")
        with self.assertRaisesRegex(
            controller.FleetControllerError, "decision must be proceed or decline"
        ):
            decide(decision="maybe")
        self.assertEqual(state["recoveries"], [])

        recovery, changed = decide()
        self.assertTrue(changed)
        self.assertEqual(recovery["decidedBy"], "operator-sdelmas")
        self.assertEqual(recovery["decisionHead"], HEAD)

        # Idempotent for the identical decision, refused for a different one.
        repeated, changed_again = decide()
        self.assertFalse(changed_again)
        self.assertEqual(repeated, recovery)
        self.assertEqual(state["recoveries"], [recovery])

    def test_declining_to_proceed_is_recorded_and_leaves_the_lane_terminal(
        self,
    ) -> None:
        """Deciding not to proceed must be a recordable answer, not the state
        reached by nobody ever answering. Both look identical on the lane; only
        the recovery record tells them apart."""

        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        parked = self.park_for_decision(controller, state)
        lane_before = copy.deepcopy(state["lanes"][0])

        recovery, changed = controller.record_operator_decision(
            state,
            consumer="canary-a",
            decision="decline",
            decided_by="operator-sdelmas",
            decision_head=HEAD,
            release="0.37.0",
        )

        self.assertTrue(changed)
        self.assertEqual(state["lanes"][0], lane_before)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(controller.issue_next(state), [])
        self.assertEqual(recovery["decision"], "decline")
        self.assertEqual(recovery["fromActionId"], parked["actionId"])
        self.assertEqual(recovery["toAttempt"], recovery["fromAttempt"])
        controller.validate_state(state)

        # Having declined, the operator cannot then quietly proceed on the same
        # parked action: the answer to one parking is one answer.
        with self.assertRaisesRegex(
            controller.FleetControllerError,
            "already carries a different operator decision",
        ):
            controller.record_operator_decision(
                state,
                consumer="canary-a",
                decision="proceed",
                decided_by="operator-sdelmas",
                decision_head=HEAD,
                release="0.37.0",
            )

    def test_resume_cli_drives_the_operator_decision_path(self) -> None:
        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(
            controller, selected=("canary-a",)
        )
        self.park_for_decision(controller, state)
        state_home = root.parent / f"{root.name}-controller-state"
        store = controller.CampaignStore(root, "campaign-1", state_home)
        with store.locked():
            store.write(state)
        common = [
            "--repo",
            str(root),
            "--campaign",
            "campaign-1",
            "--state-home",
            str(state_home),
            "--json",
        ]

        def resume(*arguments):
            status, output, error = self.run_cli(
                controller, "resume", *common, *arguments
            )
            return status, output, error

        status, _output, error = resume(
            "--decision", "proceed", "--decided-by", "operator-sdelmas"
        )
        self.assertEqual(status, 2)
        self.assertIn("require decide-consumer", error)

        status, output, _error = resume(
            "--decide-consumer",
            "canary-a",
            "--decision",
            "proceed",
            "--decided-by",
            "operator-sdelmas",
            "--decision-head",
            HEAD,
            "--release",
            "0.37.0",
        )

        self.assertEqual(status, 0)
        payload = output
        self.assertEqual(payload["recovery"]["kind"], "operator-decision")
        self.assertEqual(payload["recovery"]["decision"], "proceed")
        self.assertTrue(payload["changed"])
        reloaded = store.load()
        self.assertEqual(reloaded["status"], "active")
        self.assertEqual(reloaded["lanes"][0]["status"], "waiting")


    def finalization_receipt(self, path, *, base, head, paths=(".trellis/workspace/x/journal-1.md",)):
        """A finish-work completion bundle result, as review-preflight emits it."""
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "kind": "trellis-bookkeeping-validation",
                    "status": "valid",
                    "command": "final-bundle",
                    "mode": "completion",
                    "reasonCodes": ["completion_bundle_valid"],
                    "evidence": {
                        "baseOid": base,
                        "headOid": head,
                        "taskDirectories": [],
                        "changedPaths": list(paths),
                    },
                    "findings": [],
                    "advisories": [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def lane_at_merge_eligibility(self, controller, state, *, consumer="wave-a"):
        """Drive a lane to a waiting merge-eligibility stage at HEAD."""
        self.pass_preflight(controller, state)
        while self.lane_for(state, consumer)["stage"] != "merge-eligibility":
            self.pass_lane_action(controller, state)
        return self.issued_action_for(controller, state, consumer)

    def test_a_head_advanced_by_the_lanes_own_finalization_does_not_rewind(
        self,
    ) -> None:
        """The head moves on every lane, for the same reason, every time.

        Stage 2 records the review at H. Stage 2b runs finish-work, whose
        journal commit produces H'. By merge-eligibility the stored head is
        always one commit stale, so the `pr-head-advanced` rewind — which models
        someone else pushing to the PR branch — was the normal path, priced as
        an exception: four records where one was expected.
        """

        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(controller, selected=("wave-a",))
        action = self.lane_at_merge_eligibility(controller, state)
        receipts_before = len(state["lanes"][0]["receipts"])
        receipt_path = self.finalization_receipt(
            root / "finalization.json", base=HEAD, head=OTHER_HEAD
        )
        advance = controller._load_finalization_advance(
            receipt_path, lane_head=HEAD, head=OTHER_HEAD
        )

        receipt, changed = controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="passed",
            head=OTHER_HEAD,
            finalization_advance=advance,
        )

        self.assertTrue(changed)
        lane = state["lanes"][0]
        # One receipt, and the lane moved forward rather than back.
        self.assertEqual(len(lane["receipts"]), receipts_before + 1)
        self.assertEqual(lane["stage"], "merge")
        self.assertEqual(lane["head"], OTHER_HEAD)
        # The chain still says which head each stage validated.
        self.assertEqual(
            [
                (item["stage"], item["head"])
                for item in lane["receipts"]
                if item["stage"] in ("pr-publication", "review", "merge-eligibility")
            ],
            [
                ("pr-publication", HEAD),
                ("review", HEAD),
                ("merge-eligibility", OTHER_HEAD),
            ],
        )
        self.assertEqual(
            receipt["finalizationAdvance"], {"fromHead": HEAD, "toHead": OTHER_HEAD}
        )
        controller.validate_state(state)

        while self.lane_for(state, "wave-a")["result"] is None:
            self.pass_lane_action(controller, state, head=OTHER_HEAD)
        self.assertEqual(state["lanes"][0]["result"], "merged")

    def test_a_head_advanced_by_an_outside_push_still_rewinds(self) -> None:
        """No finalization receipt, no shortcut: the guard this exists for."""

        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller, selected=("wave-a",))
        action = self.lane_at_merge_eligibility(controller, state)

        controller.record_result(
            state,
            action_id=action["actionId"],
            release="0.37.0",
            consumer="wave-a",
            result="retryable-failure",
            reason_code=controller.PR_HEAD_ADVANCED_REASON,
            head=HEAD,
            pr_number=17,
        )

        lane = state["lanes"][0]
        self.assertEqual((lane["stage"], lane["status"]), ("pr-publication", "waiting"))

    def test_the_head_guard_names_what_it_compares(self) -> None:
        """The message said "the current PR head" at the one moment the current
        PR head is demonstrably the other one, sending the operator to verify
        the wrong fact. It now names the head it holds and how to move it."""

        controller = self.load_controller()
        _root, _fleet, _manifest, state = self.state(controller, selected=("wave-a",))
        action = self.lane_at_merge_eligibility(controller, state)

        with self.assertRaises(controller.FleetControllerError) as caught:
            controller.record_result(
                state,
                action_id=action["actionId"],
                release="0.37.0",
                consumer="wave-a",
                result="passed",
                head=OTHER_HEAD,
            )

        message = str(caught.exception)
        self.assertIn(f"lane's recorded head {HEAD}", message)
        self.assertIn("--finalization-receipt", message)
        self.assertIn(OTHER_HEAD, message)
        self.assertNotIn("current PR head", message)

    def test_the_advance_is_proven_from_the_receipt_not_asserted(self) -> None:
        """The controller runs no repository commands, so "this was our own
        finalization" cannot be the caller's word. Every part of the claim is
        read out of the finish-work receipt and compared: where it starts, where
        it ends, and that it touched nothing but task bookkeeping."""

        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(controller, selected=("wave-a",))
        self.lane_at_merge_eligibility(controller, state)
        path = root / "finalization.json"

        def load(**overrides):
            arguments = {"base": HEAD, "head": OTHER_HEAD}
            arguments.update(
                {key: value for key, value in overrides.items() if key != "mutate"}
            )
            self.finalization_receipt(path, **arguments)
            if "mutate" in overrides:
                payload = json.loads(path.read_text(encoding="utf-8"))
                overrides["mutate"](payload)
                path.write_text(json.dumps(payload), encoding="utf-8")
            return controller._load_finalization_advance(
                path, lane_head=HEAD, head=OTHER_HEAD
            )

        self.assertEqual(load(), {"fromHead": HEAD, "toHead": OTHER_HEAD})

        third = "c" * 40
        with self.assertRaisesRegex(
            controller.FleetControllerError, "does not start from the lane's recorded head"
        ):
            load(base=third)
        with self.assertRaisesRegex(
            controller.FleetControllerError, "does not end at the recorded head"
        ):
            load(head=third)
        # A product change in the delta is exactly the case that must rewind.
        with self.assertRaisesRegex(
            controller.FleetControllerError, "outside task bookkeeping"
        ):
            load(paths=(".trellis/workspace/x/journal-1.md", "src/app.py"))
        with self.assertRaisesRegex(
            controller.FleetControllerError, "must be a completion bundle"
        ):
            load(mutate=lambda payload: payload.__setitem__("mode", "planning"))
        with self.assertRaisesRegex(
            controller.FleetControllerError, "valid schema-1 result"
        ):
            load(mutate=lambda payload: payload.__setitem__("status", "invalid"))
        with self.assertRaisesRegex(
            controller.FleetControllerError, "lists no changed paths"
        ):
            load(paths=())

        path.write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(
            controller.FleetControllerError, "not valid JSON"
        ):
            controller._load_finalization_advance(
                path, lane_head=HEAD, head=OTHER_HEAD
            )
        with self.assertRaisesRegex(
            controller.FleetControllerError, "cannot read finalization receipt"
        ):
            controller._load_finalization_advance(
                root / "absent.json", lane_head=HEAD, head=OTHER_HEAD
            )

    def test_a_receipt_cannot_escape_the_bookkeeping_tree_by_traversal(self) -> None:
        """The prefix must bound the tree, not merely start the string.

        The receipt is operator-supplied evidence and the controller runs no
        repository command to corroborate it, so a prefix test is the whole
        boundary. `.trellis/../scripts/x.py` passes that test while naming a
        file outside the tree, which would let a tampered receipt wave a
        product change past the guard that exists to catch exactly that.
        """

        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(controller, selected=("wave-a",))
        self.lane_at_merge_eligibility(controller, state)
        path = root / "finalization.json"

        escapes = (
            ".trellis/../scripts/app.py",
            ".trellis/tasks/../../etc/passwd",
            ".trellis//workspace/x/journal-1.md",
            ".trellis/workspace/x/",
            ".trellis/./workspace/x/journal-1.md",
            ".trellis/workspace\\x\\journal-1.md",
            ".trellis/",
        )
        for entry in escapes:
            with self.subTest(entry=entry):
                self.assertFalse(controller._is_bookkeeping_path(entry))
                self.finalization_receipt(
                    path, base=HEAD, head=OTHER_HEAD, paths=(entry,)
                )
                with self.assertRaisesRegex(
                    controller.FleetControllerError, "outside task bookkeeping"
                ):
                    controller._load_finalization_advance(
                        path, lane_head=HEAD, head=OTHER_HEAD
                    )

        # The ordinary bookkeeping paths a real receipt carries still pass.
        for entry in (
            ".trellis/workspace/x/journal-1.md",
            ".trellis/tasks/archive/2026-08/a-task/task.json",
        ):
            self.assertTrue(controller._is_bookkeeping_path(entry))
        self.assertFalse(controller._is_bookkeeping_path(None))
        self.assertFalse(controller._is_bookkeeping_path("/.trellis/x.md"))

    def test_record_cli_accepts_a_finalization_receipt(self) -> None:
        controller = self.load_controller()
        root, _fleet, _manifest, state = self.state(controller, selected=("wave-a",))
        action = self.lane_at_merge_eligibility(controller, state)
        state_home = root.parent / f"{root.name}-controller-state"
        store = controller.CampaignStore(root, "campaign-1", state_home)
        with store.locked():
            store.write(state)
        receipt_path = self.finalization_receipt(
            root / "finalization.json", base=HEAD, head=OTHER_HEAD
        )

        status, output, _error = self.run_cli(
            controller,
            "record",
            "--repo",
            str(root),
            "--campaign",
            "campaign-1",
            "--state-home",
            str(state_home),
            "--json",
            "--action-id",
            action["actionId"],
            "--release",
            "0.37.0",
            "--consumer",
            "wave-a",
            "--result",
            "passed",
            "--head",
            OTHER_HEAD,
            "--finalization-receipt",
            str(receipt_path),
        )

        self.assertEqual(status, 0)
        self.assertEqual(
            output["receipt"]["finalizationAdvance"],
            {"fromHead": HEAD, "toHead": OTHER_HEAD},
        )
        reloaded = store.load()
        self.assertEqual(reloaded["lanes"][0]["stage"], "merge")
        self.assertEqual(reloaded["lanes"][0]["head"], OTHER_HEAD)


if __name__ == "__main__":
    unittest.main()
