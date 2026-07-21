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

WAVE_PLAN = PACK_ROOT / "scripts/sd-ai-command-pack-fleet-wave-plan.py"


class FleetWavePlanTests(InstallTestCase):
    def load_planner(self):
        return self.load_module_from_path(
            WAVE_PLAN,
            f"sd_ai_command_pack_fleet_wave_plan_{id(self)}",
        )

    def consumers(self, planner):
        return [
            planner.fleet_lib.FleetConsumer(
                name=name,
                github=f"example/{name}",
                path_hint=f"~/{name}",
                platforms=("github",),
                rollout_priority=index * 10,
                candidate_timeout_seconds=60,
                candidate_prepare=(),
                candidate_checks=(("python", "check.py"),),
            )
            for index, name in enumerate(
                ("canary-a", "canary-b", "wave-a", "wave-b", "wave-c", "final"),
                start=1,
            )
        ]

    def policy(self, planner):
        cohort = planner.fleet_lib.FleetRolloutCohort
        return planner.fleet_lib.FleetRolloutPolicy(
            default_concurrency=2,
            cohorts=(
                cohort("canary", "sequential", 1, ("canary-a", "canary-b")),
                cohort(
                    "post-canary",
                    "bounded-parallel",
                    2,
                    ("wave-a", "wave-b", "wave-c"),
                ),
                cohort("final", "sequential", 1, ("final",)),
            ),
        )

    def observations(self, **states):
        names = ("canary-a", "canary-b", "wave-a", "wave-b", "wave-c", "final")
        return {
            name: {
                "state": states.get(name, "pending"),
                "packBlocker": False,
            }
            for name in names
        }

    def manifest(self):
        names = ("canary-a", "canary-b", "wave-a", "wave-b", "wave-c", "final")
        return {
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
                        "name": "post-canary",
                        "strategy": "bounded-parallel",
                        "maxConcurrency": 2,
                        "consumers": ["wave-a", "wave-b", "wave-c"],
                    },
                    {
                        "name": "final",
                        "strategy": "sequential",
                        "consumers": ["final"],
                    },
                ],
            },
            "consumers": [
                {
                    "name": name,
                    "github": f"example/{name}",
                    "pathHint": f"~/{name}",
                    "platforms": ["github"],
                    "rolloutPriority": index * 10,
                    "candidateTimeoutSeconds": 60,
                    "candidatePrepare": [],
                    "candidateChecks": [["python", "check.py"]],
                }
                for index, name in enumerate(names, start=1)
            ],
        }

    def state_payload(self, **states):
        observations = self.observations(**states)
        return {
            "schemaVersion": 1,
            "consumers": [
                {"name": name, **row} for name, row in observations.items()
            ],
        }

    def test_canaries_are_strictly_sequential_and_gate_later_cohorts(self) -> None:
        planner = self.load_planner()
        policy = self.policy(planner)

        initial = planner.plan_rollout(policy, self.observations())
        after_first = planner.plan_rollout(
            policy, self.observations(**{"canary-a": "merged"})
        )
        canary_failure = planner.plan_rollout(
            policy, self.observations(**{"canary-a": "failed"})
        )

        self.assertEqual(initial["canStart"], ["canary-a"])
        self.assertEqual(after_first["canStart"], ["canary-b"])
        self.assertEqual(canary_failure["canStart"], [])
        self.assertTrue(canary_failure["stopStarting"])
        self.assertTrue(canary_failure["holdMerges"])

    def test_post_canary_starts_are_bounded_and_resumable(self) -> None:
        planner = self.load_planner()
        policy = self.policy(planner)
        canaries = {"canary-a": "merged", "canary-b": "at-target"}

        initial = planner.plan_rollout(policy, self.observations(**canaries))
        resumed = planner.plan_rollout(
            policy,
            self.observations(
                **canaries,
                **{"wave-a": "merged", "wave-b": "in-flight"},
            ),
        )

        self.assertEqual(initial["canStart"], ["wave-a", "wave-b"])
        self.assertEqual(resumed["canStart"], ["wave-c"])
        self.assertNotIn("wave-a", resumed["canStart"])

    def test_merge_candidate_waits_for_manifest_order(self) -> None:
        planner = self.load_planner()
        policy = self.policy(planner)
        base = {"canary-a": "merged", "canary-b": "merged"}

        later_ready = planner.plan_rollout(
            policy,
            self.observations(**base, **{"wave-a": "in-flight", "wave-b": "ready"}),
        )
        first_ready = planner.plan_rollout(
            policy,
            self.observations(**base, **{"wave-a": "ready", "wave-b": "ready"}),
        )

        self.assertIsNone(later_ready["mergeCandidate"])
        self.assertEqual(first_ready["mergeCandidate"], "wave-a")

    def test_non_blocking_failure_allows_progress_and_final_cohort(self) -> None:
        planner = self.load_planner()
        policy = self.policy(planner)
        state = self.observations(
            **{
                "canary-a": "merged",
                "canary-b": "merged",
                "wave-a": "failed",
                "wave-b": "merged",
                "wave-c": "skipped",
            }
        )

        plan = planner.plan_rollout(policy, state)

        self.assertEqual(plan["cohort"], "final")
        self.assertEqual(plan["canStart"], ["final"])

    def test_pack_blocker_stops_starts_and_holds_merges(self) -> None:
        planner = self.load_planner()
        state = self.observations(
            **{"canary-a": "merged", "canary-b": "merged", "wave-a": "ready"}
        )
        state["wave-b"]["packBlocker"] = True

        plan = planner.plan_rollout(self.policy(planner), state)

        self.assertEqual(plan["canStart"], [])
        self.assertIsNone(plan["mergeCandidate"])
        self.assertTrue(plan["stopStarting"])
        self.assertTrue(plan["holdMerges"])
        self.assertIn("wave-b", plan["reason"])

    def test_completion_waiting_and_concurrency_overflow(self) -> None:
        planner = self.load_planner()
        policy = self.policy(planner)
        all_done = self.observations(
            **{
                name: "merged"
                for name in ("canary-a", "canary-b", "wave-a", "wave-b", "wave-c", "final")
            }
        )
        waiting = self.observations(
            **{"canary-a": "in-flight"}
        )
        overflow = self.observations(
            **{
                "canary-a": "merged",
                "canary-b": "merged",
                "wave-a": "in-flight",
                "wave-b": "ready",
                "wave-c": "in-flight",
            }
        )

        self.assertTrue(planner.plan_rollout(policy, all_done)["complete"])
        self.assertIn("waiting", planner.plan_rollout(policy, waiting)["reason"])
        with self.assertRaisesRegex(planner.FleetWavePlanError, "concurrency"):
            planner.plan_rollout(policy, overflow)

    def test_observation_parser_rejects_unsafe_shapes(self) -> None:
        planner = self.load_planner()
        consumers = self.consumers(planner)
        valid = self.state_payload()
        cases = (
            {},
            {**valid, "extra": True},
            {**valid, "schemaVersion": 0},
            {**valid, "consumers": "bad"},
            {**valid, "consumers": valid["consumers"][:-1]},
            {**valid, "consumers": valid["consumers"] + [valid["consumers"][0]]},
            {
                **valid,
                "consumers": [{**valid["consumers"][0], "state": "unknown"}]
                + valid["consumers"][1:],
            },
            {
                **valid,
                "consumers": [{**valid["consumers"][0], "packBlocker": "no"}]
                + valid["consumers"][1:],
            },
        )

        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(planner.FleetWavePlanError):
                    planner.parse_observations(payload, consumers)

    def test_manifest_parser_rejects_unsafe_rollout_policies(self) -> None:
        planner = self.load_planner()
        fleet_lib = planner.fleet_lib
        valid = self.manifest()
        consumers = fleet_lib.parse_fleet_consumers(valid)
        policy_cases = (
            None,
            {},
            {"defaultConcurrency": 2, "cohorts": [], "unknown": True},
            {"defaultConcurrency": 0, "cohorts": []},
            {"defaultConcurrency": True, "cohorts": []},
            {"defaultConcurrency": 2, "cohorts": []},
            {"defaultConcurrency": 2, "cohorts": ["bad"]},
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": [consumer.name for consumer in consumers],
                        "unknown": True,
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "maxConcurrency": True,
                        "consumers": [consumer.name for consumer in consumers],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "maxConcurrency": 1.0,
                        "consumers": [consumer.name for consumer in consumers],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": ["canary-a"],
                    },
                    {
                        "name": "wave",
                        "strategy": "bounded-parallel",
                        "maxConcurrency": 3,
                        "consumers": [consumer.name for consumer in consumers[1:]],
                    },
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "../canary",
                        "strategy": "sequential",
                        "consumers": [consumer.name for consumer in consumers],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "invalid",
                        "consumers": [consumer.name for consumer in consumers],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "maxConcurrency": 2,
                        "consumers": [consumer.name for consumer in consumers],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": ["canary-a"],
                    },
                    {
                        "name": "CANARY",
                        "strategy": "bounded-parallel",
                        "maxConcurrency": 3,
                        "consumers": [consumer.name for consumer in consumers[1:]],
                    },
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": [consumer.name for consumer in consumers],
                    },
                    {
                        "name": "later",
                        "strategy": "bounded-parallel",
                        "maxConcurrency": 2,
                        "consumers": [],
                    },
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": [1],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": [
                            *[consumer.name for consumer in consumers[:-1]],
                            "unknown",
                        ],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": [
                            *[consumer.name for consumer in consumers],
                            consumers[-1].name,
                        ],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "first",
                        "strategy": "sequential",
                        "consumers": [consumer.name for consumer in consumers],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "bounded-parallel",
                        "maxConcurrency": 2,
                        "consumers": [consumer.name for consumer in consumers],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": [consumer.name for consumer in consumers[:-1]],
                    }
                ],
            },
            {
                "defaultConcurrency": 2,
                "cohorts": [
                    {
                        "name": "canary",
                        "strategy": "sequential",
                        "consumers": [consumer.name for consumer in reversed(consumers)],
                    }
                ],
            },
        )

        for rollout_policy in policy_cases:
            manifest = {**valid, "rolloutPolicy": rollout_policy}
            with self.subTest(rollout_policy=rollout_policy):
                with self.assertRaises(fleet_lib.FleetConfigError):
                    fleet_lib.parse_fleet_consumers(manifest)

        root = self.make_git_repo_without_trellis()
        manifest_path = root / "fleet.json"
        manifest_path.write_text(json.dumps(valid), encoding="utf-8")
        loaded = fleet_lib.load_fleet_rollout_policy(manifest_path)
        self.assertEqual(loaded.cohorts[1].name, "post-canary")

    def test_consumer_parser_preserves_caller_label_in_errors(self) -> None:
        planner = self.load_planner()
        fleet_lib = planner.fleet_lib
        manifest = self.manifest()

        malformed_row = {**manifest, "consumers": ["bad"]}
        with self.assertRaisesRegex(
            fleet_lib.FleetConfigError,
            r"custom fleet source consumers\[0\]",
        ):
            fleet_lib.parse_fleet_consumers(malformed_row, "custom fleet source")

        invalid_consumer = {
            **manifest,
            "consumers": [{**manifest["consumers"][0], "github": "invalid"}],
        }
        with self.assertRaisesRegex(
            fleet_lib.FleetConfigError,
            "custom fleet source consumer canary-a",
        ):
            fleet_lib.parse_fleet_consumers(invalid_consumer, "custom fleet source")

    def test_cli_renders_json_and_human_plans(self) -> None:
        planner = self.load_planner()
        root = self.make_git_repo_without_trellis()
        fleet = root / "fleet.json"
        state = root / "state.json"
        fleet.write_text(json.dumps(self.manifest()), encoding="utf-8")
        state.write_text(json.dumps(self.state_payload()), encoding="utf-8")

        for extra, expected in ((["--json"], '"canStart":["canary-a"]'), ([], "cohort: canary")):
            output = io.StringIO()
            with self.subTest(extra=extra), contextlib.redirect_stdout(output):
                result = planner.main(["--fleet", str(fleet), "--state", str(state), *extra])
            self.assertEqual(result, 0)
            self.assertIn(expected, output.getvalue())

    def test_cli_errors_are_controlled_and_do_not_echo_paths(self) -> None:
        planner = self.load_planner()
        root = self.make_git_repo_without_trellis()
        missing = root / "private-name.json"
        errors = io.StringIO()

        with contextlib.redirect_stderr(errors):
            result = planner.main(["--fleet", str(missing), "--state", str(missing)])

        self.assertEqual(result, 2)
        self.assertIn("fleet manifest is missing", errors.getvalue())
        self.assertNotIn(str(missing), errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def test_json_loader_rejects_symlink_large_and_non_object_inputs(self) -> None:
        planner = self.load_planner()
        root = self.make_git_repo_without_trellis()
        source = root / "source.json"
        source.write_text("[]", encoding="utf-8")
        link = root / "link.json"
        link.symlink_to(source)
        large = root / "large.json"
        large.write_text("x" * (planner.MAX_STATE_BYTES + 1), encoding="utf-8")

        with self.assertRaisesRegex(planner.FleetWavePlanError, "regular file"):
            planner._load_json_object(link, "state")
        with self.assertRaisesRegex(planner.FleetWavePlanError, "exceeds"):
            planner._load_json_object(large, "state")
        with self.assertRaisesRegex(planner.FleetWavePlanError, "JSON object"):
            planner._load_json_object(source, "state")

    def test_json_loader_rejects_path_swapped_to_symlink_before_open(self) -> None:
        planner = self.load_planner()
        root = self.make_git_repo_without_trellis()
        state = root / "state.json"
        target = root / "target.json"
        state.write_text("{}", encoding="utf-8")
        target.write_text("{}", encoding="utf-8")
        original_open = planner.os.open

        def swap_then_open(path, flags):
            state.unlink()
            state.symlink_to(target)
            return original_open(path, flags)

        with mock.patch.object(planner.os, "open", side_effect=swap_then_open):
            with self.assertRaisesRegex(
                planner.FleetWavePlanError,
                "cannot be opened safely",
            ):
                planner._load_json_object(state, "state")


if __name__ == "__main__":
    unittest.main()
