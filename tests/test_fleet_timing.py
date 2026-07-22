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
os = _support.os
Path = _support.Path
unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

TIMING = PACK_ROOT / "scripts/sd-ai-command-pack-fleet-timing.py"
SECOND = 1_000_000_000


class FleetTimingTests(InstallTestCase):
    def load_timing(self):
        return self.load_module_from_path(
            TIMING,
            f"sd_ai_command_pack_fleet_timing_{id(self)}",
        )

    def reading(self, timing, seconds: int):
        return timing.ClockReading(seconds * SECOND, seconds * SECOND)

    def make_store(self, timing):
        repo = self.make_git_repo_without_trellis()
        state_home = repo.parent / f"{repo.name}-state"
        store = timing.timing_store(repo, "run-1", state_home)
        return repo, state_home, store

    def state(self, timing, *consumers: tuple[str, int]):
        return timing.new_state(
            "run-1",
            "0.23.16",
            "a" * 64,
            consumers or (("alpha", 20), ("canary", 10)),
            self.reading(timing, 1),
        )

    def clone(self, value):
        return json.loads(json.dumps(value))

    def test_system_reading_uses_process_independent_monotonic_clock(self) -> None:
        timing = self.load_timing()

        with (
            mock.patch.object(timing.time, "time_ns", return_value=11),
            mock.patch.object(
                timing.time, "CLOCK_MONOTONIC", 17, create=True
            ),
            mock.patch.object(
                timing.time,
                "clock_gettime_ns",
                return_value=23,
                create=True,
            ) as clock_gettime_ns,
            mock.patch.object(timing.time, "monotonic_ns") as monotonic_ns,
        ):
            reading = timing.system_reading()

        self.assertEqual(reading, timing.ClockReading(11, 23))
        clock_gettime_ns.assert_called_once_with(17)
        monotonic_ns.assert_not_called()

    def test_system_reading_falls_back_when_clock_gettime_is_unavailable(self) -> None:
        timing = self.load_timing()

        with (
            mock.patch.object(timing.time, "time_ns", return_value=11),
            mock.patch.object(
                timing.time, "clock_gettime_ns", None, create=True
            ),
            mock.patch.object(
                timing.time, "CLOCK_MONOTONIC", None, create=True
            ),
            mock.patch.object(
                timing.time, "monotonic_ns", return_value=29
            ) as monotonic_ns,
        ):
            reading = timing.system_reading()

        self.assertEqual(reading, timing.ClockReading(11, 29))
        monotonic_ns.assert_called_once_with()

    def test_new_state_sorts_consumers_and_rejects_duplicate_identity(self) -> None:
        timing = self.load_timing()

        state = self.state(timing)

        self.assertEqual(
            [(item["name"], item["priority"]) for item in state["consumers"]],
            [("canary", 10), ("alpha", 20)],
        )
        for consumers, message in (
            ((("same", 10), ("same", 20)), "names must be unique"),
            ((("one", 10), ("two", 10)), "priorities must be unique"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(timing.FleetTimingError, message):
                    self.state(timing, *consumers)
        with self.assertRaisesRegex(timing.FleetTimingError, "at least one"):
            timing.new_state(
                "run-1", "0.23.16", "a" * 64, (), self.reading(timing, 1)
            )

    def test_initialize_is_private_atomic_and_resumable(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)

        state, changed = timing.initialize_store(
            store,
            "run-1",
            "0.23.16",
            (("canary", 10), ("alpha", 20)),
            self.reading(timing, 1),
        )
        resumed, resumed_changed = timing.initialize_store(
            store,
            "run-1",
            "0.23.16",
            (("canary", 10), ("alpha", 20)),
            self.reading(timing, 2),
        )

        self.assertTrue(changed)
        self.assertFalse(resumed_changed)
        self.assertEqual(resumed, state)
        self.assertEqual(store.state_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(store.state_path.parent.stat().st_mode & 0o777, 0o700)
        with self.assertRaisesRegex(timing.FleetTimingError, "identity does not match"):
            timing.initialize_store(
                store,
                "run-1",
                "0.23.17",
                (("canary", 10), ("alpha", 20)),
                self.reading(timing, 3),
            )

    def test_stage_lifecycle_is_idempotent_and_retry_is_derived(self) -> None:
        timing = self.load_timing()
        state = self.state(timing, ("canary", 10))

        self.assertTrue(
            timing.start_stage(
                state,
                consumer_name="canary",
                stage_name="install",
                reading=self.reading(timing, 10),
            )
        )
        self.assertFalse(
            timing.start_stage(
                state,
                consumer_name="canary",
                stage_name="install",
                reading=self.reading(timing, 11),
            )
        )
        self.assertTrue(
            timing.end_stage(
                state,
                consumer_name="canary",
                stage_name="install",
                outcome="failed",
                reason="installer returned exit 1",
                reading=self.reading(timing, 12),
            )
        )
        self.assertFalse(
            timing.end_stage(
                state,
                consumer_name="canary",
                stage_name="install",
                outcome="failed",
                reason="installer returned exit 1",
                reading=self.reading(timing, 13),
            )
        )
        self.assertTrue(
            timing.start_stage(
                state,
                consumer_name="canary",
                stage_name="install",
                reading=self.reading(timing, 14),
            )
        )
        timing.end_stage(
            state,
            consumer_name="canary",
            stage_name="install",
            outcome="passed",
            reason=None,
            reading=self.reading(timing, 19),
        )

        summary = timing.build_summary(state, self.reading(timing, 20))
        self.assertEqual(summary["aggregate"]["retryCount"], 1)
        self.assertEqual(summary["consumers"][0]["stages"][0]["attempts"], 2)
        with self.assertRaisesRegex(timing.FleetTimingError, "no active attempt"):
            timing.end_stage(
                state,
                consumer_name="canary",
                stage_name="install",
                outcome="skipped",
                reason="not applicable",
                reading=self.reading(timing, 20),
            )

    def test_overlap_math_uses_wall_union_and_monotonic_elapsed(self) -> None:
        timing = self.load_timing()
        state = self.state(timing, ("canary", 10))

        for stage, second in (("reviewer-wait", 10), ("ci-wait", 20)):
            timing.start_stage(
                state,
                consumer_name="canary",
                stage_name=stage,
                reading=self.reading(timing, second),
            )
        timing.end_stage(
            state,
            consumer_name="canary",
            stage_name="reviewer-wait",
            outcome="passed",
            reason=None,
            reading=self.reading(timing, 30),
        )
        timing.end_stage(
            state,
            consumer_name="canary",
            stage_name="ci-wait",
            outcome="passed",
            reason=None,
            reading=self.reading(timing, 40),
        )
        timing.end_consumer(
            state, name="canary", outcome="refreshed-merged", reason=None
        )
        timing.complete_state(state, self.reading(timing, 41))

        summary = timing.build_summary(state, self.reading(timing, 99))
        consumer = summary["consumers"][0]
        self.assertEqual(consumer["criticalPathNs"], 30 * SECOND)
        self.assertEqual(consumer["activeWallNs"], 30 * SECOND)
        self.assertEqual(consumer["summedStageElapsedNs"], 40 * SECOND)
        self.assertEqual(consumer["reviewerCiOverlapNs"], 10 * SECOND)
        self.assertEqual(summary["aggregate"]["slowestStage"]["name"], "reviewer-wait")

    def test_aggregate_overlap_intersects_run_wide_interval_unions(self) -> None:
        timing = self.load_timing()
        state = self.state(timing)

        for consumer in ("canary", "alpha"):
            timing.start_stage(
                state,
                consumer_name=consumer,
                stage_name="reviewer-wait",
                reading=self.reading(timing, 10),
            )
            timing.start_stage(
                state,
                consumer_name=consumer,
                stage_name="ci-wait",
                reading=self.reading(timing, 20),
            )
            timing.end_stage(
                state,
                consumer_name=consumer,
                stage_name="reviewer-wait",
                outcome="passed",
                reason=None,
                reading=self.reading(timing, 30),
            )
            timing.end_stage(
                state,
                consumer_name=consumer,
                stage_name="ci-wait",
                outcome="passed",
                reason=None,
                reading=self.reading(timing, 40),
            )
            timing.end_consumer(
                state, name=consumer, outcome="refreshed-merged", reason=None
            )

        summary = timing.build_summary(state, self.reading(timing, 41))

        self.assertEqual(
            [item["reviewerCiOverlapNs"] for item in summary["consumers"]],
            [10 * SECOND, 10 * SECOND],
        )
        self.assertEqual(summary["aggregate"]["reviewerCiOverlapNs"], 10 * SECOND)

    def test_active_summary_completion_and_consumer_rules_fail_closed(self) -> None:
        timing = self.load_timing()
        state = self.state(timing, ("canary", 10))
        timing.start_stage(
            state,
            consumer_name=None,
            stage_name="preflight",
            reading=self.reading(timing, 2),
        )

        active = timing.build_summary(state, self.reading(timing, 5))
        self.assertEqual(active["aggregate"]["activeAttempts"], 1)
        self.assertEqual(active["fleetStages"][0]["elapsedNs"], 3 * SECOND)
        with self.assertRaisesRegex(timing.FleetTimingError, "active stages"):
            timing.complete_state(state, self.reading(timing, 6))
        with self.assertRaisesRegex(timing.FleetTimingError, "fleet-scoped"):
            timing.start_stage(
                state,
                consumer_name="canary",
                stage_name="preflight",
                reading=self.reading(timing, 6),
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "fleet scope"):
            timing.start_stage(
                state,
                consumer_name=None,
                stage_name="install",
                reading=self.reading(timing, 6),
            )
        timing.end_stage(
            state,
            consumer_name=None,
            stage_name="preflight",
            outcome="passed",
            reason=None,
            reading=self.reading(timing, 7),
        )
        with self.assertRaisesRegex(timing.FleetTimingError, "without consumer outcomes"):
            timing.complete_state(state, self.reading(timing, 8))
        with self.assertRaisesRegex(timing.FleetTimingError, "reason is required"):
            timing.end_consumer(state, name="canary", outcome="blocked", reason=None)
        self.assertTrue(
            timing.end_consumer(
                state,
                name="canary",
                outcome="blocked",
                reason="approval is unavailable",
            )
        )
        self.assertFalse(
            timing.end_consumer(
                state,
                name="canary",
                outcome="blocked",
                reason="approval is unavailable",
            )
        )
        timing.complete_state(state, self.reading(timing, 9))
        self.assertFalse(timing.complete_state(state, self.reading(timing, 10)))
        with self.assertRaisesRegex(timing.FleetTimingError, "completed timing run"):
            timing.start_stage(
                state,
                consumer_name="canary",
                stage_name="audit",
                reading=self.reading(timing, 11),
            )

    def test_monotonic_clock_cannot_move_backwards(self) -> None:
        timing = self.load_timing()
        state = self.state(timing, ("canary", 10))
        timing.start_stage(
            state,
            consumer_name="canary",
            stage_name="audit",
            reading=self.reading(timing, 10),
        )
        backwards = timing.ClockReading(20 * SECOND, 9 * SECOND)

        with self.assertRaisesRegex(timing.FleetTimingError, "moved backwards"):
            timing.end_stage(
                state,
                consumer_name="canary",
                stage_name="audit",
                outcome="passed",
                reason=None,
                reading=backwards,
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "moved backwards"):
            timing.build_summary(state, backwards)

    def test_strict_state_schema_rejects_malformed_records(self) -> None:
        timing = self.load_timing()
        valid = self.state(timing, ("canary", 10))
        cases = []
        wrong_schema = self.clone(valid)
        wrong_schema["schemaVersion"] = True
        cases.append((wrong_schema, "schemaVersion"))
        unknown = self.clone(valid)
        unknown["extra"] = True
        cases.append((unknown, "unknown field"))
        duplicate_priority = self.state(timing)
        duplicate_priority["consumers"][1]["priority"] = 10
        cases.append((duplicate_priority, "duplicate consumer priorities"))
        unordered = self.state(timing)
        unordered["consumers"].reverse()
        cases.append((unordered, "not in rollout priority order"))
        completed_active = self.clone(valid)
        completed_active["status"] = "completed"
        completed_active["completedAtWallNs"] = 2 * SECOND
        cases.append((completed_active, "active consumers"))

        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(timing.FleetTimingError, message):
                    timing.validate_state(payload)

        malformed_attempt = self.clone(valid)
        malformed_attempt["consumers"][0]["stages"] = [
            {
                "name": "audit",
                "attempts": [
                    {
                        "attempt": 2,
                        "startedWallNs": SECOND,
                        "startedMonotonicNs": SECOND,
                        "endedWallNs": None,
                        "elapsedNs": None,
                        "outcome": None,
                        "reason": None,
                    }
                ],
            }
        ]
        with self.assertRaisesRegex(timing.FleetTimingError, "not sequential"):
            timing.validate_state(malformed_attempt)

    def test_validation_helpers_cover_fail_closed_boundaries(self) -> None:
        timing = self.load_timing()
        with self.assertRaisesRegex(timing.FleetTimingError, "missing field"):
            timing._strict_fields({}, frozenset({"required"}), "value")
        with self.assertRaisesRegex(timing.FleetTimingError, "must be an object"):
            timing._object([], "value")
        with self.assertRaisesRegex(timing.FleetTimingError, "must be an array"):
            timing._array({}, "value")
        with self.assertRaisesRegex(timing.FleetTimingError, "integer"):
            timing._integer(True, "value")
        with self.assertRaisesRegex(timing.FleetTimingError, "must be a string"):
            timing.safe_reason(1, "reason")
        with self.assertRaisesRegex(timing.FleetTimingError, "must not be empty"):
            timing.safe_reason("   ", "reason")
        with self.assertRaisesRegex(timing.FleetTimingError, "is invalid"):
            timing._optional_outcome("unknown", timing.STAGE_OUTCOMES, "outcome")
        with self.assertRaisesRegex(timing.FleetTimingError, "not JSON serializable"):
            timing._json_payload({"value": {1}})
        with mock.patch.object(timing, "MAX_STATE_BYTES", 2):
            with self.assertRaisesRegex(timing.FleetTimingError, "exceeds"):
                timing._json_payload({"value": "large"})

        active_attempt = {
            "attempt": 1,
            "startedWallNs": SECOND,
            "startedMonotonicNs": SECOND,
            "endedWallNs": None,
            "elapsedNs": None,
            "outcome": None,
            "reason": None,
        }
        mismatched_end = self.clone(active_attempt)
        mismatched_end["endedWallNs"] = 2 * SECOND
        with self.assertRaisesRegex(timing.FleetTimingError, "all null or all populated"):
            timing.validate_attempt(mismatched_end, "attempt")
        active_reason = self.clone(active_attempt)
        active_reason["reason"] = "still active"
        with self.assertRaisesRegex(timing.FleetTimingError, "cannot have a reason"):
            timing.validate_attempt(active_reason, "attempt")
        passed_reason = self.clone(active_attempt)
        passed_reason.update(
            {
                "endedWallNs": 2 * SECOND,
                "elapsedNs": SECOND,
                "outcome": "passed",
                "reason": "not allowed",
            }
        )
        with self.assertRaisesRegex(timing.FleetTimingError, "forbids a reason"):
            timing.validate_attempt(passed_reason, "attempt")

        with self.assertRaisesRegex(timing.FleetTimingError, "not a supported stage"):
            timing.validate_stage(
                {"name": "unknown", "attempts": [active_attempt]},
                "stage",
                fleet_scope=False,
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "invalid for fleet"):
            timing.validate_stage(
                {"name": "audit", "attempts": [active_attempt]},
                "stage",
                fleet_scope=True,
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "must be non-empty"):
            timing.validate_stage(
                {"name": "audit", "attempts": []}, "stage", fleet_scope=False
            )
        second_active = self.clone(active_attempt)
        second_active["attempt"] = 2
        with self.assertRaisesRegex(timing.FleetTimingError, "last and unique"):
            timing.validate_stage(
                {"name": "audit", "attempts": [active_attempt, second_active]},
                "stage",
                fleet_scope=False,
            )

    def test_state_consumer_and_stage_validation_error_matrix(self) -> None:
        timing = self.load_timing()
        valid = self.state(timing, ("canary", 10))
        cases: list[tuple[dict[str, object], str]] = []
        for field, value, message in (
            ("repositoryDigest", "bad", "repositoryDigest"),
            ("status", "paused", "status is invalid"),
            ("completedAtWallNs", SECOND, "completion fields disagree"),
        ):
            payload = self.clone(valid)
            payload[field] = value
            cases.append((payload, message))
        no_consumers = self.clone(valid)
        no_consumers["consumers"] = []
        cases.append((no_consumers, "must be non-empty"))
        duplicate_name = self.state(timing)
        duplicate_name["consumers"][1]["name"] = "canary"
        cases.append((duplicate_name, "duplicate consumer names"))
        fleet_duplicate = self.clone(valid)
        attempt = {
            "attempt": 1,
            "startedWallNs": SECOND,
            "startedMonotonicNs": SECOND,
            "endedWallNs": 2 * SECOND,
            "elapsedNs": SECOND,
            "outcome": "passed",
            "reason": None,
        }
        fleet_duplicate["fleetStages"] = [
            {"name": "preflight", "attempts": [attempt]},
            {"name": "preflight", "attempts": [attempt]},
        ]
        cases.append((fleet_duplicate, "duplicate fleet stages"))

        for payload, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(timing.FleetTimingError, message):
                    timing.validate_state(payload)

        consumer = self.clone(valid["consumers"][0])
        consumer["reason"] = "premature"
        with self.assertRaisesRegex(timing.FleetTimingError, "active consumer"):
            timing.validate_consumer(consumer, "consumer")
        consumer["outcome"] = "at-target"
        with self.assertRaisesRegex(timing.FleetTimingError, "forbids a reason"):
            timing.validate_consumer(consumer, "consumer")
        consumer["outcome"] = "failed"
        consumer["reason"] = None
        with self.assertRaisesRegex(timing.FleetTimingError, "requires a reason"):
            timing.validate_consumer(consumer, "consumer")

        duplicate_stages = self.clone(valid["consumers"][0])
        duplicate_stages["stages"] = [
            {"name": "audit", "attempts": [attempt]},
            {"name": "audit", "attempts": [attempt]},
        ]
        with self.assertRaisesRegex(timing.FleetTimingError, "duplicate stages"):
            timing.validate_consumer(duplicate_stages, "consumer")

    def test_repository_state_file_and_process_errors_are_normalized(self) -> None:
        timing = self.load_timing()
        repo = self.make_git_repo_without_trellis()
        relative = repo.relative_to(Path.cwd()) if repo.is_relative_to(Path.cwd()) else repo
        self.assertEqual(timing.resolve_repository(relative), repo.resolve())
        missing = repo / "missing"
        with self.assertRaisesRegex(timing.FleetTimingError, "cannot resolve"):
            timing.resolve_repository(missing)
        regular_file = repo / "file.txt"
        regular_file.write_text("value", encoding="utf-8")
        with self.assertRaisesRegex(timing.FleetTimingError, "must be a directory"):
            timing.resolve_repository(regular_file)

        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(repo)}, clear=False):
            self.assertEqual(
                timing.resolve_state_root(), repo / "sd-ai-command-pack"
            )

        missing_json = repo / "missing.json"
        with self.assertRaisesRegex(timing.FleetTimingError, "does not exist"):
            timing.read_json_file(missing_json, "fixture")
        malformed = repo / "malformed.json"
        malformed.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(timing.FleetTimingError, "cannot read"):
            timing.read_json_file(malformed, "fixture")
        target = repo / "target.json"
        target.write_text("{}", encoding="utf-8")
        link = repo / "link.json"
        link.symlink_to(target.name)
        with self.assertRaisesRegex(timing.FleetTimingError, "must not be a symlink"):
            timing.read_json_file(link, "fixture")

        self.assertFalse(timing.process_alive(True))
        self.assertFalse(timing.process_alive(-1))
        with mock.patch.object(timing.os, "kill", side_effect=PermissionError):
            self.assertTrue(timing.process_alive(1))

    def test_storage_and_lock_errors_do_not_escape_as_raw_oserrors(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)
        state = timing.new_state(
            "run-1",
            "0.23.16",
            store.repository_digest,
            (("canary", 10),),
            self.reading(timing, 1),
        )
        with mock.patch.object(timing.tempfile, "mkstemp", side_effect=OSError("full")):
            with self.assertRaisesRegex(timing.FleetTimingError, "temporary timing state"):
                timing.atomic_write_state(store, state)

        timing.ensure_private_directory(store.state_path.parent)
        store.state_path.symlink_to(store.state_path.parent / "missing-target")
        with self.assertRaisesRegex(timing.FleetTimingError, "must not be a symlink"):
            timing.atomic_write_state(store, state)
        store.state_path.unlink()

        with mock.patch.object(timing.os, "open", side_effect=OSError("denied")):
            with self.assertRaisesRegex(timing.FleetTimingError, "cannot acquire"):
                with timing.operation_lock(
                    store,
                    "run-1",
                    reading_fn=lambda: self.reading(timing, 1),
                    wait_seconds=0,
                ):
                    self.fail("lock must not be acquired")

        for value, message in (
            ("canary", "NAME:PRIORITY"),
            ("canary:nope", "must be an integer"),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(timing.FleetTimingError, message):
                    timing.parse_consumer(value)

    def test_operation_errors_preserve_existing_state(self) -> None:
        timing = self.load_timing()
        state = self.state(timing, ("canary", 10))
        with self.assertRaisesRegex(timing.FleetTimingError, "unsupported timing stage"):
            timing.start_stage(
                state,
                consumer_name="canary",
                stage_name="unknown",
                reading=self.reading(timing, 2),
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "unknown timing consumer"):
            timing.start_stage(
                state,
                consumer_name="missing",
                stage_name="audit",
                reading=self.reading(timing, 2),
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "stage outcome is invalid"):
            timing.end_stage(
                state,
                consumer_name="canary",
                stage_name="audit",
                outcome="unknown",
                reason=None,
                reading=self.reading(timing, 2),
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "no attempt"):
            timing.end_stage(
                state,
                consumer_name="canary",
                stage_name="audit",
                outcome="passed",
                reason=None,
                reading=self.reading(timing, 2),
            )
        with self.assertRaisesRegex(timing.FleetTimingError, "outcome is invalid"):
            timing.end_consumer(state, name="canary", outcome="unknown", reason=None)
        timing.start_stage(
            state,
            consumer_name="canary",
            stage_name="audit",
            reading=self.reading(timing, 2),
        )
        with self.assertRaisesRegex(timing.FleetTimingError, "active stage"):
            timing.end_consumer(
                state, name="canary", outcome="refreshed-merged", reason=None
            )

    def test_reason_and_identifier_privacy_rules(self) -> None:
        timing = self.load_timing()

        for value, message in (
            ("contains\na newline", "control character"),
            ("see /Users/example/project", "absolute or home-relative"),
            ("see (/Users/example/project)", "absolute or home-relative"),
            ('see "/Users/example/project"', "absolute or home-relative"),
            ("see-/Users/example/project", "absolute or home-relative"),
            ("see)/Users/example/project", "absolute or home-relative"),
            (r"see C:\\Users\\example\\project", "absolute or home-relative"),
            (r"see \\\\server\\share", "absolute or home-relative"),
            ("see https://github.com/org/repo", "remote URL"),
            ("see git@github.com:org/repo", "remote URL"),
            ("token=ghp_abcdefghijklmnopqrstuvwxyz", "secret-like"),
            ("x" * 501, "exceeds"),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(timing.FleetTimingError, message):
                    timing.safe_reason(value, "reason")
        with self.assertRaisesRegex(timing.FleetTimingError, "safe identifier"):
            timing.safe_token("../unsafe", "run ID")
        self.assertEqual(
            timing.safe_reason("  bounded   operator reason  ", "reason"),
            "bounded operator reason",
        )
        self.assertEqual(
            timing.safe_reason("relative/path reference", "reason"),
            "relative/path reference",
        )

    def test_store_rejects_relative_state_home_and_symlinks(self) -> None:
        timing = self.load_timing()
        repo = self.make_git_repo_without_trellis()
        with self.assertRaisesRegex(timing.FleetTimingError, "absolute path"):
            timing.timing_store(repo, "run-1", Path("relative-state"))

        state_home = repo.parent / f"{repo.name}-state"
        target = repo.parent / f"{repo.name}-target"
        target.mkdir()
        state_home.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(timing.FleetTimingError, "must not be a symlink"):
            timing.timing_store(repo, "run-1", state_home)

    def test_stale_dead_lock_is_recovered(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)
        timing.ensure_private_directory(store.lock_path.parent)
        store.lock_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runId": "run-1",
                    "repositoryDigest": store.repository_digest,
                    "pid": 99_999_999,
                    "hostname": "test-host",
                    "acquiredAtWallNs": SECOND,
                }
            ),
            encoding="utf-8",
        )

        with timing.operation_lock(
            store,
            "run-1",
            reading_fn=lambda: self.reading(timing, 100),
            wait_seconds=0,
        ):
            self.assertTrue(store.lock_path.exists())
        self.assertFalse(store.lock_path.exists())

    def test_lock_schema_rejects_boolean_version(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)
        lock = {
            "schemaVersion": True,
            "runId": "run-1",
            "repositoryDigest": store.repository_digest,
            "pid": os.getpid(),
            "hostname": "test-host",
            "acquiredAtWallNs": SECOND,
        }

        with self.assertRaisesRegex(timing.FleetTimingError, "must be an integer"):
            timing._validate_lock(lock, store, "run-1")

    def test_transient_invalid_lock_is_retried_until_writer_finishes(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)
        timing.ensure_private_directory(store.lock_path.parent)
        store.lock_path.write_text("{", encoding="utf-8")

        def finish_interrupted_write(_seconds: float) -> None:
            store.lock_path.unlink()

        with mock.patch.object(
            timing.time, "sleep", side_effect=finish_interrupted_write
        ):
            with timing.operation_lock(
                store,
                "run-1",
                reading_fn=lambda: self.reading(timing, 100),
                wait_seconds=1,
            ):
                self.assertTrue(store.lock_path.exists())
        self.assertFalse(store.lock_path.exists())

    def test_persistent_invalid_lock_uses_bounded_busy_error(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)
        timing.ensure_private_directory(store.lock_path.parent)
        store.lock_path.write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(timing.FleetTimingError, "busy"):
            with timing.operation_lock(
                store,
                "run-1",
                reading_fn=lambda: self.reading(timing, 100),
                wait_seconds=0,
            ):
                self.fail("lock must not be acquired")
        self.assertTrue(store.lock_path.exists())

    def test_live_lock_times_out_without_removing_owner(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)
        timing.ensure_private_directory(store.lock_path.parent)
        store.lock_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "runId": "run-1",
                    "repositoryDigest": store.repository_digest,
                    "pid": os.getpid(),
                    "hostname": "test-host",
                    "acquiredAtWallNs": 100 * SECOND,
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(timing.FleetTimingError, "busy"):
            with timing.operation_lock(
                store,
                "run-1",
                reading_fn=lambda: self.reading(timing, 100),
                wait_seconds=0,
            ):
                self.fail("lock must not be acquired")
        self.assertTrue(store.lock_path.exists())

    def test_mutation_persists_partial_state_for_resume(self) -> None:
        timing = self.load_timing()
        _repo, _state_home, store = self.make_store(timing)
        timing.initialize_store(
            store,
            "run-1",
            "0.23.16",
            (("canary", 10),),
            self.reading(timing, 1),
        )

        state, changed = timing.mutate_state(
            store,
            "run-1",
            self.reading(timing, 2),
            lambda current: timing.start_stage(
                current,
                consumer_name="canary",
                stage_name="checkout-validation",
                reading=self.reading(timing, 2),
            ),
        )
        resumed = timing.load_state(store, "run-1")

        self.assertTrue(changed)
        self.assertEqual(resumed, state)
        attempt = resumed["consumers"][0]["stages"][0]["attempts"][0]
        self.assertIsNone(attempt["endedWallNs"])
        _unchanged, changed_again = timing.mutate_state(
            store,
            "run-1",
            self.reading(timing, 3),
            lambda current: timing.start_stage(
                current,
                consumer_name="canary",
                stage_name="checkout-validation",
                reading=self.reading(timing, 3),
            ),
        )
        self.assertFalse(changed_again)

    def test_cli_json_and_human_output_hide_local_state_path(self) -> None:
        timing = self.load_timing()
        repo = self.make_git_repo_without_trellis()
        state_home = repo.parent / f"{repo.name}-state"
        common = ["--repo", str(repo), "--state-home", str(state_home)]

        json_output = io.StringIO()
        with mock.patch.object(
            timing, "system_reading", return_value=self.reading(timing, 1)
        ), contextlib.redirect_stdout(json_output):
            exit_code = timing.main(
                [
                    *common,
                    "--json",
                    "init",
                    "--run-id",
                    "run-1",
                    "--target-version",
                    "0.23.16",
                    "--consumer",
                    "canary:10",
                ]
            )
        payload = json.loads(json_output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["changed"])
        self.assertNotIn(str(repo), json_output.getvalue())
        self.assertNotIn(str(state_home), json_output.getvalue())

        human_output = io.StringIO()
        with mock.patch.object(
            timing, "system_reading", return_value=self.reading(timing, 2)
        ), contextlib.redirect_stdout(human_output):
            exit_code = timing.main([*common, "report", "--run-id", "run-1"])
        self.assertEqual(exit_code, 0)
        self.assertIn("fleet timing: active run run-1", human_output.getvalue())
        self.assertIn("active wall: 0.000s", human_output.getvalue())
        self.assertIn("critical 0.000s · active 0.000s", human_output.getvalue())
        self.assertIn("changed: no", human_output.getvalue())

    def test_cli_errors_are_stable_and_do_not_trace_back(self) -> None:
        timing = self.load_timing()
        repo = self.make_git_repo_without_trellis()
        state_home = repo.parent / f"{repo.name}-state"
        common = ["--repo", str(repo), "--state-home", str(state_home), "--json"]
        with contextlib.redirect_stdout(io.StringIO()):
            timing.main(
                [
                    *common,
                    "init",
                    "--run-id",
                    "run-1",
                    "--target-version",
                    "0.23.16",
                    "--consumer",
                    "canary:10",
                ]
            )
            timing.main(
                [
                    *common,
                    "stage-start",
                    "--run-id",
                    "run-1",
                    "--consumer",
                    "canary",
                    "--stage",
                    "audit",
                ]
            )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = timing.main(
                [
                    *common,
                    "stage-end",
                    "--run-id",
                    "run-1",
                    "--consumer",
                    "canary",
                    "--stage",
                    "audit",
                    "--outcome",
                    "failed",
                    "--reason",
                    "token=ghp_abcdefghijklmnopqrstuvwxyz",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "error")
        self.assertIn("secret-like", payload["error"])
        self.assertNotIn("Traceback", output.getvalue())

    def test_cli_redacts_paths_from_wrapped_os_errors(self) -> None:
        timing = self.load_timing()
        repo = self.make_git_repo_without_trellis()
        leaked_path = repo / "private state" / "run-1.json"
        failure = timing.FleetTimingError(
            f"cannot read timing state: [Errno 13] Permission denied: '{leaked_path}'"
        )
        output = io.StringIO()
        with mock.patch.object(
            timing, "timing_store", side_effect=failure
        ), contextlib.redirect_stdout(output):
            exit_code = timing.main(
                ["--repo", str(repo), "--json", "report", "--run-id", "run-1"]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertIn("<path>", payload["error"])
        self.assertNotIn(str(repo), output.getvalue())
        self.assertNotIn("private state", output.getvalue())


if __name__ == "__main__":
    unittest.main()
