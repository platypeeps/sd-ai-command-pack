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
os = _support.os
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase


class WorkLoopTests(InstallTestCase):
    """Tests for durable autonomous work-loop state and selection."""

    def load_module(self):
        return self.load_module_from_path(
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-work-loop.py",
            "sd_ai_command_pack_work_loop",
        )

    def make_repo(self, remote: str | None = None) -> Path:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-work-loop-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo"
        root.mkdir()
        self.run_git(root, "init", "--initial-branch=main")
        self.run_git(root, "config", "user.name", "Work Loop Test")
        self.run_git(root, "config", "user.email", "work-loop@example.com")
        (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        self.run_git(root, "add", "README.md")
        self.run_git(root, "commit", "-m", "seed")
        if remote:
            self.run_git(root, "remote", "add", "origin", remote)
        return root

    def make_state(self, module, repo: Path, state_root: Path, **kwargs):
        identity = module.repository_identity(repo)
        focus = module.normalize_focus()
        state = module.new_state(
            identity,
            mode=kwargs.get("mode", "backlog"),
            selector=kwargs.get("selector", "all"),
            focus=kwargs.get("focus", focus),
            until=kwargs.get("until", "merge"),
            run_id=kwargs.get("run_id", "run-1"),
        )
        state_path, lock_path = module.state_paths(identity, state_root)
        module.acquire_lock(lock_path, state)
        module.atomic_write_json(state_path, state)
        return state, state_path, lock_path

    def commit_file(
        self, module, root: Path, name: str, content: str, message: str
    ) -> str:
        (root / name).write_text(content, encoding="utf-8")
        self.run_git(root, "add", name)
        self.run_git(root, "commit", "-m", message)
        commit = module.run_git(root, "rev-parse", "HEAD")
        self.assertIsNotNone(commit)
        return commit

    def make_shipping_state(self, module, root: Path) -> tuple[dict, str]:
        initial = module.run_git(root, "rev-parse", "HEAD")
        self.assertIsNotNone(initial)
        self.run_git(root, "switch", "-c", "codex/task-one")
        feature_head = self.commit_file(
            module, root, "feature.txt", "first\n", "feature commit"
        )
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        module.transition_state(
            state,
            "selected",
            updates={"task": "task-one", "baseBranch": "main"},
        )
        module.transition_state(state, "planning")
        module.transition_state(state, "implementing")
        module.update_evidence(
            state,
            {"branch": "codex/task-one", "head": feature_head},
            repo=root,
        )
        module.transition_state(state, "validating")
        module.transition_state(state, "shipping")
        return state, initial

    def test_state_root_precedence_and_platform_fallbacks(self) -> None:
        module = self.load_module()

        self.assertEqual(
            module.resolve_state_root(
                environ={
                    "SD_AI_COMMAND_PACK_STATE_HOME": "/tmp/override",
                    "XDG_STATE_HOME": "/tmp/xdg",
                },
                home=Path("/home/test"),
            ),
            Path("/tmp/override"),
        )
        self.assertEqual(
            module.resolve_state_root(
                environ={"XDG_STATE_HOME": "/tmp/xdg"},
                home=Path("/home/test"),
            ),
            Path("/tmp/xdg/sd-ai-command-pack"),
        )
        self.assertEqual(
            module.resolve_state_root(
                environ={"LOCALAPPDATA": "C:/Users/Test/AppData/Local"},
                home=Path("/home/test"),
                os_name="nt",
            ),
            Path("C:/Users/Test/AppData/Local/sd-ai-command-pack/state"),
        )
        self.assertEqual(
            module.resolve_state_root(environ={}, home=Path("/home/test")),
            Path("/home/test/.local/state/sd-ai-command-pack"),
        )

    def test_relative_explicit_state_root_fails_closed(self) -> None:
        module = self.load_module()

        with self.assertRaisesRegex(module.WorkLoopError, "must be an absolute path"):
            module.resolve_state_root(
                environ={"SD_AI_COMMAND_PACK_STATE_HOME": "relative/state"}
            )
        with self.assertRaisesRegex(module.WorkLoopError, "--state-home"):
            module._state_root_arg("relative/state")

    def test_repository_identity_normalizes_git_remote_forms(self) -> None:
        module = self.load_module()
        root = self.make_repo("git@github.com:platypeeps/example.git")

        identity = module.repository_identity(root)

        self.assertEqual(
            identity["remote"], "ssh://github.com/platypeeps/example"
        )
        self.assertEqual(identity["label"], "example")
        self.assertEqual(len(identity["digest"]), 64)
        self.assertEqual(
            module.canonical_remote("HTTPS://GitHub.COM/platypeeps/example.git/"),
            "https://github.com/platypeeps/example",
        )
        self.assertEqual(
            module.canonical_remote("C:/Users/Test/Example.git"),
            "c:/users/test/example",
        )

    def test_repository_identity_strips_remote_credentials_before_persistence(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        identity = module.repository_identity(
            root,
            remote="https://token-user:secret-value@GitHub.com/platypeeps/example.git",
        )
        state = module.new_state(
            identity,
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        serialized = module._json_payload(state)

        self.assertEqual(identity["remote"], "https://github.com/platypeeps/example")
        self.assertNotIn("token-user", serialized)
        self.assertNotIn("secret-value", serialized)
        self.assertEqual(
            module.canonical_remote("git@github.com:platypeeps/example.git"),
            "ssh://github.com/platypeeps/example",
        )

    def test_focus_normalization_supports_bare_ordered_and_structured(self) -> None:
        module = self.load_module()

        bare = module.normalize_focus(bare=" CI pipeline ")
        ordered = module.normalize_focus(
            preferred=["priority:P1", "release automation"]
        )

        self.assertEqual(bare["mode"], "prefer")
        self.assertEqual(bare["original"], ["CI pipeline"])
        self.assertEqual(ordered["selectors"][0]["field"], "priority")
        self.assertEqual(ordered["selectors"][0]["value"], "p1")
        self.assertEqual(ordered["selectors"][1]["kind"], "natural")

    def test_focus_normalization_rejects_ambiguous_or_malformed_modes(self) -> None:
        module = self.load_module()

        cases = (
            {"bare": "CI", "preferred": ["release"]},
            {"preferred": ["CI"], "only": ["testing"]},
            {"preferred": [""]},
            {"preferred": ["prioritty:P1"]},
            {"only": ["scope:"]},
        )
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(module.WorkLoopError):
                    module.normalize_focus(**values)

    def test_focus_ranking_preserves_bands_and_backlog_fallback(self) -> None:
        module = self.load_module()
        candidates = [
            {
                "id": "release-task",
                "title": "Release automation",
                "status": "planning",
                "priority": "P1",
                "createdAt": "2026-01-01",
                "artifactsComplete": True,
            },
            {
                "id": "ci-task",
                "title": "Harden CI pipeline",
                "status": "planning",
                "priority": "P3",
                "createdAt": "2026-01-02",
                "artifactsComplete": False,
            },
            {
                "id": "ordinary-task",
                "title": "Improve docs",
                "status": "in_progress",
                "priority": "P0",
                "createdAt": "2026-01-03",
                "artifactsComplete": True,
            },
        ]
        focus = module.normalize_focus(preferred=["CI pipeline", "release"])

        ranked = module.rank_candidates(candidates, focus)

        self.assertEqual(
            [item["id"] for item in ranked],
            ["ci-task", "release-task", "ordinary-task"],
        )
        self.assertIn("title contains ci pipeline", ranked[0]["focusEvidence"])
        self.assertFalse(ranked[-1]["focusMatch"])

    def test_focus_only_never_broadens_and_structured_matches_are_exact(self) -> None:
        module = self.load_module()
        candidates = [
            {"id": "one", "priority": "P1", "status": "planning"},
            {"id": "two", "priority": "P10", "status": "planning"},
        ]

        ranked = module.rank_candidates(
            candidates, module.normalize_focus(only=["priority:P1"])
        )

        self.assertEqual([item["id"] for item in ranked], ["one"])
        self.assertEqual(ranked[0]["focusMatchKind"], "structured")

    def test_atomic_state_is_private_and_rejects_secret_keys(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        state, state_path, _lock_path = self.make_state(module, root, state_root)

        self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(state_path.parent.stat().st_mode & 0o777, 0o700)
        state["apiToken"] = "do-not-store"
        with self.assertRaisesRegex(module.WorkLoopError, "secret-like key"):
            module.validate_state(state)

    def test_validate_state_rejects_incomplete_or_malformed_focus(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(preferred=["CI pipeline"]),
            until="merge",
            run_id="run-1",
        )
        invalid_focus_values = (
            {"mode": "prefer"},
            {"mode": "prefer", "original": ["CI pipeline"], "selectors": []},
            {"mode": "none", "original": ["CI"], "selectors": []},
            {
                "mode": "prefer",
                "original": ["CI"],
                "selectors": [{"kind": "natural", "field": "priority", "value": "ci"}],
            },
        )

        for focus in invalid_focus_values:
            with self.subTest(focus=focus):
                candidate = dict(state)
                candidate["focus"] = focus
                with self.assertRaisesRegex(module.WorkLoopError, "focus"):
                    module.validate_state(candidate)

    def test_validate_state_rejects_missing_or_wrong_typed_snapshot_fields(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        invalid_updates = (
            ("mode", None),
            ("selector", ["all"]),
            ("until", "release"),
            ("current", {}),
            ("contextHealth", {"level": "green"}),
            ("checkpoint", {"state": "none"}),
            ("heartbeatAt", 123),
        )

        for key, value in invalid_updates:
            with self.subTest(key=key, value=value):
                candidate = dict(state)
                candidate[key] = value
                with self.assertRaises(module.WorkLoopError):
                    module.validate_state(candidate)

    def test_atomic_write_preserves_prior_state_when_replace_fails(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        target = root.parent / "state/state.json"
        module.atomic_write_json(target, {"value": "before"})

        with mock.patch.object(module.os, "replace", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(OSError, "blocked"):
                module.atomic_write_json(target, {"value": "after"})

        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": "before"})
        self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_atomic_write_succeeds_when_chmod_is_unsupported(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        target = root.parent / "state/state.json"

        with (
            mock.patch.object(
                module.Path, "chmod", side_effect=OSError("unsupported")
            ) as path_chmod,
            mock.patch.object(
                module.os,
                "chmod",
                side_effect=AssertionError("direct chmod must not be used"),
            ) as direct_chmod,
        ):
            module.atomic_write_json(target, {"value": "written"})

        direct_chmod.assert_not_called()
        path_chmod.assert_has_calls([mock.call(0o700), mock.call(0o600)])
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": "written"})
        self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_validation_and_persistence_use_the_same_size_limit(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(preferred=["CI pipeline"]),
            until="merge",
            run_id="run-1",
        )
        compact_size = len(json.dumps(state, sort_keys=True).encode("utf-8"))
        disk_size = len(module._json_payload(state).encode("utf-8"))
        self.assertGreater(disk_size, compact_size)

        with mock.patch.object(module, "MAX_LEDGER_BYTES", disk_size - 1):
            with self.assertRaisesRegex(module.WorkLoopError, "exceeds"):
                module.validate_state(state)
            with self.assertRaisesRegex(module.WorkLoopError, "oversized"):
                module.atomic_write_json(root.parent / "state/state.json", state)

    def test_lock_rejects_concurrency_and_requires_explicit_stale_recovery(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        first, _state_path, lock_path = self.make_state(module, root, state_root)
        second = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-2",
        )

        with self.assertRaisesRegex(module.WorkLoopError, "active work-loop lock"):
            module.acquire_lock(lock_path, second)

        lock = module.read_json(lock_path)
        lock["runId"] = first["runId"]
        lock["pid"] = 99999999
        lock["hostname"] = "different-host"
        lock["heartbeatAt"] = "2000-01-01T00:00:00Z"
        module.atomic_write_json(lock_path, lock)
        with self.assertRaisesRegex(module.WorkLoopError, "stale work-loop lock"):
            module.acquire_lock(lock_path, second)
        module.acquire_lock(lock_path, second, recover_stale=True)
        self.assertEqual(module.read_json(lock_path)["runId"], "run-2")

        module.release_lock(lock_path, second["runId"])
        lock_path.write_text("{broken\n", encoding="utf-8")
        corrupt_lock = lock_path.read_bytes()
        with self.assertRaisesRegex(module.WorkLoopError, "unreadable"):
            module.acquire_lock(lock_path, first)
        self.assertEqual(lock_path.read_bytes(), corrupt_lock)

        module.acquire_lock(lock_path, first, recover_stale=True)
        self.assertEqual(module.read_json(lock_path)["runId"], first["runId"])

        module.release_lock(lock_path, first["runId"])
        malformed_lock = {
            "schemaVersion": module.SCHEMA_VERSION,
            "runId": "other-run",
            "repositoryDigest": first["repository"]["digest"],
            "pid": 99999999,
            "hostname": "different-host",
            "acquiredAt": "2000-01-01T00:00:00Z",
        }
        module.atomic_write_json(lock_path, malformed_lock)
        malformed_bytes = lock_path.read_bytes()
        with self.assertRaisesRegex(module.WorkLoopError, "malformed"):
            module.acquire_lock(lock_path, first)
        self.assertEqual(lock_path.read_bytes(), malformed_bytes)

        module.acquire_lock(lock_path, first, recover_stale=True)
        self.assertEqual(module.read_json(lock_path)["runId"], first["runId"])

    def test_legal_transitions_increment_iteration_and_clear_current_state(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )

        module.transition_state(state, "selected", updates={"task": "task-one"})
        module.transition_state(state, "planning")
        module.transition_state(state, "implementing")
        module.update_evidence(state, {"branch": "main"}, repo=root)
        module.transition_state(state, "validating")
        module.transition_state(state, "shipping")
        module.transition_state(state, "followups")
        module.transition_state(state, "complete")
        module.transition_state(state, "inventory")

        self.assertEqual(state["iteration"], 2)
        self.assertIsNone(state["current"]["task"])
        self.assertIsNone(state["current"]["branch"])
        with self.assertRaisesRegex(module.WorkLoopError, "illegal"):
            module.transition_state(state, "shipping")

    def test_every_lifecycle_phase_survives_persisted_resume(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        state, state_path, _lock_path = self.make_state(module, root, state_root)
        transitions = (
            ("selected", {"task": "task-one"}),
            ("planning", None),
            ("implementing", None),
            ("validating", None),
            ("shipping", None),
            ("followups", None),
            ("complete", None),
            ("inventory", None),
        )

        for phase, updates in transitions:
            with self.subTest(phase=phase):
                module.transition_state(state, phase, updates=updates)
                if phase == "implementing":
                    module.update_evidence(state, {"branch": "main"}, repo=root)
                if phase == "shipping":
                    module.update_evidence(state, {"prNumber": 42}, repo=root)
                module.atomic_write_json(state_path, state)
                state = module.read_json(state_path)
                module.validate_state(state)
                self.assertEqual(state["phase"], phase)

        self.assertEqual(state["iteration"], 2)

    def test_transition_rejects_stable_identity_replacement_before_phase_change(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        module.transition_state(state, "selected", updates={"task": "task-one"})
        module.transition_state(
            state, "planning", updates={"task": "task-one   "}
        )
        self.assertEqual(state["current"]["task"], "task-one")

        with self.assertRaisesRegex(module.WorkLoopError, "stable"):
            module.transition_state(
                state, "implementing", updates={"task": "different-task"}
            )

        self.assertEqual(state["phase"], "planning")
        self.assertEqual(state["current"]["task"], "task-one")

    def test_transition_rejects_mutable_evidence_updates(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        invalid_updates = (
            {"branch": "main"},
            {"head": "HEAD"},
            {"prNumber": 42},
            {"prUrl": "https://example.test/pull/42"},
            {"lastShippedSha": "HEAD"},
        )

        for updates in invalid_updates:
            with self.subTest(updates=updates):
                state = module.new_state(
                    module.repository_identity(root),
                    mode="backlog",
                    selector="all",
                    focus=module.normalize_focus(),
                    until="merge",
                    run_id="run-1",
                )
                with self.assertRaisesRegex(module.WorkLoopError, "evidence command"):
                    module.transition_state(state, "selected", updates=updates)
                self.assertEqual(state["phase"], "inventory")

    def test_result_history_is_bounded_and_updates_cost_counters(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )

        for index in range(module.MAX_HISTORY + 3):
            state["phase"] = "followups"
            state["iteration"] = index + 1
            module.record_result(
                state,
                task=f"task-{index}",
                outcome="completed",
                pr_number=100 + index,
                pr_url=f"https://example.test/pr/{index}",
                review_rounds=2,
                ci_retries=1,
                decisions=[f"decision {index}"],
                followups=[f"follow-up {index}"],
            )

        self.assertEqual(len(state["iterations"]), module.MAX_HISTORY)
        self.assertEqual(state["iterations"][0]["task"], "task-3")
        self.assertEqual(state["counters"]["completed"], module.MAX_HISTORY + 3)
        self.assertEqual(state["counters"]["mergedPrs"], module.MAX_HISTORY + 3)
        self.assertEqual(state["counters"]["reviewRounds"], 2 * (module.MAX_HISTORY + 3))

    def test_evidence_tracks_publish_review_finish_and_squash_merge(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state, main_head = self.make_shipping_state(module, root)
        feature_head = state["current"]["head"]

        state["checkpoint"] = {
            "state": "ready",
            "target": "shipping",
            "reason": "old recovery",
        }
        module.update_evidence(state, {"head": "HEAD"}, repo=root)
        self.assertEqual(state["checkpoint"]["state"], "ready")
        module.update_evidence(
            state,
            {
                "task": state["current"]["task"],
                "branch": state["current"]["branch"],
                "prNumber": 42,
                "prUrl": "https://example.test/pull/42",
                "head": "HEAD",
                "baseBranch": state["current"]["baseBranch"],
                "lastShippedSha": "HEAD",
            },
            repo=root,
        )
        self.assertEqual(state["checkpoint"]["state"], "none")
        self.assertEqual(state["current"]["head"], feature_head)
        self.assertEqual(state["current"]["lastShippedSha"], feature_head)

        review_head = self.commit_file(
            module, root, "feature.txt", "review fix\n", "review fix"
        )
        module.update_evidence(state, {"head": review_head}, repo=root)
        finish_head = self.commit_file(
            module, root, "journal.md", "session\n", "finish work"
        )
        module.update_evidence(
            state,
            {"head": finish_head, "lastShippedSha": finish_head},
            repo=root,
        )

        self.run_git(root, "switch", "main")
        merged_head = self.commit_file(
            module, root, "merged.txt", "squashed\n", "squash merge result"
        )
        self.assertNotEqual(main_head, merged_head)
        module.update_evidence(
            state,
            {"branch": "main", "head": merged_head},
            repo=root,
        )

        self.assertEqual(state["current"]["branch"], "main")
        self.assertEqual(state["current"]["head"], merged_head)
        self.assertEqual(state["current"]["lastShippedSha"], finish_head)
        self.assertEqual(state["phase"], "shipping")
        self.assertEqual(state["contextHealth"]["level"], "green")

    def test_evidence_rejects_identity_branch_pr_and_commit_conflicts(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state, _main_head = self.make_shipping_state(module, root)
        feature_head = state["current"]["head"]
        module.update_evidence(
            state,
            {
                "prNumber": 42,
                "prUrl": "https://example.test/pull/42",
                "lastShippedSha": feature_head,
            },
            repo=root,
        )

        invalid_updates = (
            ({"task": "different-task"}, "stable"),
            ({"baseBranch": "develop"}, "stable"),
            ({"branch": "other"}, "merge boundary"),
            ({"prNumber": 43}, "request number"),
            ({"prUrl": "https://example.test/pull/43"}, "request URL"),
            ({"unknown": "value"}, "unknown"),
        )
        for updates, error in invalid_updates:
            with self.subTest(updates=updates):
                with self.assertRaisesRegex(module.WorkLoopError, error):
                    module.update_evidence(state, updates, repo=root)

        self.run_git(root, "switch", "-c", "sibling", "main")
        sibling = self.commit_file(
            module, root, "sibling.txt", "sibling\n", "sibling commit"
        )
        with self.assertRaisesRegex(module.WorkLoopError, "recorded branch"):
            module.update_evidence(state, {"head": sibling}, repo=root)
        self.run_git(root, "branch", "-D", "codex/task-one")
        with self.assertRaisesRegex(module.WorkLoopError, "descendant"):
            module.update_evidence(state, {"head": sibling}, repo=root)
        self.run_git(root, "branch", "-f", "codex/task-one", sibling)
        with self.assertRaisesRegex(module.WorkLoopError, "descendant"):
            module.update_evidence(state, {"head": sibling}, repo=root)
        with self.assertRaisesRegex(module.WorkLoopError, "local Git commit"):
            module.update_evidence(state, {"head": "not-a-commit"}, repo=root)

    def test_head_evidence_allows_missing_recorded_branch_ref(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state, _main_head = self.make_shipping_state(module, root)
        descendant = self.commit_file(
            module, root, "followup.txt", "followup\n", "followup commit"
        )
        self.run_git(root, "switch", "main")
        self.run_git(root, "branch", "-D", "codex/task-one")

        module.update_evidence(state, {"head": descendant}, repo=root)

        self.assertEqual(state["current"]["branch"], "codex/task-one")
        self.assertEqual(state["current"]["head"], descendant)

    def test_last_shipped_evidence_falls_back_to_recorded_branch_tip(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        head = module.run_git(root, "rev-parse", "HEAD")
        self.assertIsNotNone(head)
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        module.transition_state(
            state,
            "selected",
            updates={"task": "task-one", "baseBranch": "main"},
        )
        module.transition_state(state, "planning")
        module.transition_state(state, "implementing")
        module.update_evidence(state, {"branch": "main"}, repo=root)
        module.transition_state(state, "validating")
        module.transition_state(state, "shipping")

        module.update_evidence(state, {"lastShippedSha": head}, repo=root)

        self.assertEqual(state["current"]["lastShippedSha"], head)
        self.assertIsNone(state["current"]["head"])

    def test_last_shipped_evidence_requires_recorded_head_or_branch(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        head = module.run_git(root, "rev-parse", "HEAD")
        self.assertIsNotNone(head)
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        module.transition_state(state, "selected", updates={"task": "task-one"})
        module.transition_state(state, "planning")
        module.transition_state(state, "implementing")
        module.transition_state(state, "validating")
        module.transition_state(state, "shipping")

        with self.assertRaisesRegex(
            module.WorkLoopError, "requires a verifiable recorded head or branch"
        ):
            module.update_evidence(state, {"lastShippedSha": head}, repo=root)

    def test_evidence_initializes_schema_one_state_and_rejects_idle_phase(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        head = module.run_git(root, "rev-parse", "HEAD")
        self.assertEqual(state["schemaVersion"], 1)
        with self.assertRaisesRegex(module.WorkLoopError, "inventory"):
            module.update_evidence(state, {"head": head}, repo=root)

        module.transition_state(state, "selected", updates={"task": "task-one"})
        with self.assertRaisesRegex(module.WorkLoopError, "not a local Git branch"):
            module.update_evidence(
                state,
                {"branch": "does-not-exist", "baseBranch": "main"},
                repo=root,
            )
        module.update_evidence(
            state,
            {"branch": "main", "baseBranch": "main", "head": head},
            repo=root,
        )
        module.validate_state(state)
        self.assertEqual(state["current"]["head"], head)

    def test_evidence_rejects_malformed_and_unverifiable_values(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state, _main_head = self.make_shipping_state(module, root)
        before = dict(state["current"])

        invalid_updates = (
            ({"head": ""}, "non-empty"),
            ({"head": ["not", "a", "string"]}, "non-empty"),
            ({"prNumber": True}, "positive integer"),
            ({"prNumber": 0}, "positive integer"),
            ({"prNumber": 42, "prUrl": "https://example.test/pull/not-42"}, "match"),
            ({"head": "--help"}, "local Git commit"),
        )
        for updates, error in invalid_updates:
            with self.subTest(updates=updates):
                with self.assertRaisesRegex(module.WorkLoopError, error):
                    module.update_evidence(state, updates, repo=root)
                self.assertEqual(state["current"], before)

        with (
            mock.patch.object(
                module,
                "_branch_commit",
                return_value=state["current"]["head"],
            ),
            mock.patch.object(module, "run_git", return_value=None),
        ):
            with self.assertRaisesRegex(module.WorkLoopError, "local Git commit"):
                module.update_evidence(
                    state, {"head": state["current"]["head"]}, repo=root
                )
        self.assertEqual(state["current"], before)

    def test_failed_cli_evidence_update_preserves_ledger_bytes(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        state, _main_head = self.make_shipping_state(module, root)
        state_path, lock_path = module.state_paths(
            module.repository_identity(root), state_root
        )
        module.acquire_lock(lock_path, state)
        module.atomic_write_json(state_path, state)
        before = state_path.read_bytes()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "evidence",
                    "--repo",
                    str(root),
                    "--run-id",
                    state["runId"],
                    "--task",
                    "different-task",
                    "--head",
                    "not-a-commit",
                ]
            )

        self.assertEqual(result, 2)
        self.assertIn("stable", stderr.getvalue())
        self.assertEqual(state_path.read_bytes(), before)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "evidence",
                    "--repo",
                    str(root),
                    "--run-id",
                    state["runId"],
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("at least one", stderr.getvalue())
        self.assertEqual(state_path.read_bytes(), before)

    def test_transition_cli_does_not_advertise_evidence_only_arguments(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        state, state_path, _lock_path = self.make_state(module, root, state_root)
        before = state_path.read_bytes()
        stderr = io.StringIO()

        with (
            contextlib.redirect_stderr(stderr),
            self.assertRaises(SystemExit) as exit_error,
        ):
            module.main(
                [
                    "--state-home",
                    str(state_root),
                    "transition",
                    "--repo",
                    str(root),
                    "--run-id",
                    state["runId"],
                    "--phase",
                    "selected",
                    "--task",
                    "task-one",
                    "--head",
                    "HEAD",
                ]
            )

        self.assertEqual(exit_error.exception.code, 2)
        self.assertIn("unrecognized arguments: --head HEAD", stderr.getvalue())
        self.assertEqual(state_path.read_bytes(), before)

        help_text = module.build_parser()._subparsers._group_actions[0].choices[
            "transition"
        ].format_help()
        self.assertNotIn("--head", help_text)
        self.assertNotIn("--branch", help_text)
        self.assertNotIn("--pr-number", help_text)
        self.assertNotIn("--pr-url", help_text)
        self.assertNotIn("--last-shipped-sha", help_text)
        self.assertIn("--task", help_text)
        self.assertIn("--base-branch", help_text)

    def test_reconciliation_classifies_context_health_from_evidence(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )
        module.transition_state(state, "selected", updates={"task": "task-one"})
        module.update_evidence(state, {"branch": "main"}, repo=root)

        module.reconcile_state(state, {}, signal="continuation-summary")
        self.assertEqual(state["contextHealth"]["level"], "amber")
        self.assertEqual(state["contextHealth"]["epoch"], 1)

        module.reconcile_state(
            state,
            {"task": "task-one   ", "branch": "main   "},
        )
        self.assertEqual(state["contextHealth"]["level"], "green")
        self.assertEqual(state["contextHealth"]["epoch"], 1)
        self.assertEqual(state["contextHealth"]["reasons"], [])

        module.reconcile_state(state, {"task": "different-task"})
        self.assertEqual(state["contextHealth"]["level"], "red")
        self.assertEqual(state["checkpoint"]["state"], "blocked")
        module.reconcile_state(state, {})
        self.assertEqual(state["contextHealth"]["level"], "red")
        self.assertEqual(state["checkpoint"]["state"], "blocked")
        module.reconcile_state(state, {"phase": state["phase"]})
        self.assertEqual(state["contextHealth"]["level"], "red")
        self.assertEqual(state["checkpoint"]["state"], "blocked")
        module.reconcile_state(state, {"task": "task-one"})
        self.assertEqual(state["contextHealth"]["level"], "red")
        self.assertEqual(state["checkpoint"]["state"], "blocked")
        module.reconcile_state(state, {"task": "task-one", "branch": "main"})
        self.assertEqual(state["contextHealth"]["level"], "green")
        self.assertEqual(state["checkpoint"]["state"], "none")

    def test_verified_live_advance_is_idempotent_and_unverified_advance_is_red(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )

        module.reconcile_state(
            state, {"phase": "planning"}, verified_live_advance=True
        )
        self.assertEqual(state["phase"], "planning")
        self.assertEqual(state["contextHealth"]["level"], "amber")

        module.reconcile_state(state, {"phase": "planning"})
        self.assertEqual(state["contextHealth"]["level"], "green")

        module.reconcile_state(state, {"phase": "shipping"})
        self.assertEqual(state["phase"], "planning")
        self.assertEqual(state["contextHealth"]["level"], "red")

    def test_reconcile_requires_complete_current_evidence_to_clear_checkpoint(
        self,
    ) -> None:
        module = self.load_module()
        root = self.make_repo()
        state, _main_head = self.make_shipping_state(module, root)
        module.update_evidence(
            state,
            {
                "prNumber": 42,
                "prUrl": "https://example.test/pull/42",
            },
            repo=root,
        )

        module.reconcile_state(state, {"prNumber": 43}, repo=root)
        self.assertEqual(state["contextHealth"]["level"], "red")
        self.assertEqual(state["checkpoint"]["state"], "blocked")

        module.reconcile_state(state, {"head": state["current"]["head"]}, repo=root)
        self.assertEqual(state["contextHealth"]["level"], "red")
        self.assertEqual(state["checkpoint"]["state"], "blocked")

        complete_evidence = {
            key: value
            for key, value in state["current"].items()
            if value is not None
        }
        module.reconcile_state(state, complete_evidence, repo=root)
        self.assertEqual(state["contextHealth"]["level"], "green")
        self.assertEqual(state["checkpoint"]["state"], "none")

    def test_verified_reconcile_updates_same_phase_evidence_and_clears_checkpoint(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state, _main_head = self.make_shipping_state(module, root)
        prior_head = state["current"]["head"]
        next_head = self.commit_file(
            module, root, "feature.txt", "next\n", "next feature commit"
        )
        state["checkpoint"] = {
            "state": "blocked",
            "target": "shipping",
            "reason": "stale mismatch",
        }
        state["contextHealth"] = {
            "level": "red",
            "epoch": 2,
            "reasons": ["stale mismatch"],
        }

        module.reconcile_state(
            state,
            {
                "phase": "shipping",
                "task": state["current"]["task"],
                "branch": state["current"]["branch"],
                "head": next_head,
                "baseBranch": state["current"]["baseBranch"],
                "prNumber": 42,
                "prUrl": "https://example.test/pull/42",
                "lastShippedSha": prior_head,
            },
            verified_live_advance=True,
            repo=root,
        )

        self.assertEqual(state["current"]["head"], next_head)
        self.assertEqual(state["current"]["prNumber"], 42)
        self.assertEqual(state["contextHealth"]["level"], "green")
        self.assertEqual(state["checkpoint"]["state"], "none")

        module.reconcile_state(state, {"task": "different-task"}, repo=root)
        self.assertEqual(state["contextHealth"]["level"], "red")
        self.assertEqual(state["checkpoint"]["state"], "blocked")

    def test_verified_reconcile_validates_merge_evidence_at_observed_phase(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state, _main_head = self.make_shipping_state(module, root)
        feature_head = state["current"]["head"]
        module.update_evidence(
            state,
            {
                "prNumber": 42,
                "prUrl": "https://example.test/pull/42",
                "lastShippedSha": feature_head,
            },
            repo=root,
        )
        module.transition_state(state, "validating")
        self.run_git(root, "switch", "main")
        merged_head = self.commit_file(
            module, root, "merged.txt", "merged\n", "merged result"
        )

        module.reconcile_state(
            state,
            {"phase": "followups", "branch": "main", "head": merged_head},
            verified_live_advance=True,
            repo=root,
        )

        self.assertEqual(state["phase"], "followups")
        self.assertEqual(state["current"]["branch"], "main")
        self.assertEqual(state["current"]["head"], merged_head)
        self.assertEqual(state["contextHealth"]["level"], "amber")

    def test_status_snapshot_is_read_only_and_reports_active_paused_and_invalid(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"

        self.assertEqual(
            module.status_snapshot(root, state_root=state_root), {"status": "none"}
        )
        state, state_path, _lock_path = self.make_state(module, root, state_root)
        active = module.status_snapshot(root, state_root=state_root)
        self.assertEqual(active["runId"], state["runId"])
        self.assertEqual(active["status"], "active")
        self.assertTrue(active["lock"]["present"])

        state_path.write_text("not-json\n", encoding="utf-8")
        invalid = module.status_snapshot(root, state_root=state_root)
        self.assertEqual(invalid["status"], "invalid")
        self.assertIn("cannot read", invalid["error"])

        state["mode"] = None
        module.atomic_write_json(state_path, state)
        malformed = module.status_snapshot(root, state_root=state_root)
        self.assertEqual(malformed["status"], "invalid")
        self.assertIn("mode", malformed["error"])

    def test_cli_resumes_paused_run_and_does_not_create_repo_state(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "start",
                    "--repo",
                    str(root),
                    "--bare-focus",
                    "CI pipeline",
                    "--json",
                ]
            )
        self.assertEqual(result, 0, stdout.getvalue())
        started = json.loads(stdout.getvalue())

        pause_stdout = io.StringIO()
        with contextlib.redirect_stdout(pause_stdout):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "stop",
                    "--repo",
                    str(root),
                    "--run-id",
                    started["runId"],
                    "--status",
                    "paused",
                    "--reason",
                    "operator pause",
                    "--json",
                ]
            )
        self.assertEqual(result, 0, pause_stdout.getvalue())
        paused = json.loads(pause_stdout.getvalue())
        self.assertEqual(paused["phase"], "checkpoint")
        self.assertEqual(paused["checkpoint"]["target"], "inventory")

        resumed_stdout = io.StringIO()
        with contextlib.redirect_stdout(resumed_stdout):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "start",
                    "--repo",
                    str(root),
                    "--json",
                ]
            )
        self.assertEqual(result, 0, resumed_stdout.getvalue())
        resumed = json.loads(resumed_stdout.getvalue())
        self.assertEqual(resumed["runId"], started["runId"])
        self.assertEqual(resumed["focus"], ["CI pipeline"])
        self.assertEqual(resumed["status"], "active")
        self.assertEqual(resumed["phase"], "checkpoint")
        self.assertFalse((root / ".sd-ai-command-pack/work-loop.json").exists())

    def test_cli_resume_rejects_conflicting_configuration_and_focus(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        state, _state_path, _lock_path = self.make_state(
            module,
            root,
            state_root,
            focus=module.normalize_focus(preferred=["CI pipeline"]),
        )
        module.release_lock(_lock_path, state["runId"])
        state["status"] = "paused"
        module.atomic_write_json(_state_path, state)

        conflicts = (
            (["--mode", "designs"], "--mode"),
            (["--selector", "needs-design"], "--selector"),
            (["--until", "design"], "--until"),
            (["--focus-only", "release"], "focus subcommand"),
        )
        for extra_args, expected in conflicts:
            with self.subTest(extra_args=extra_args):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = module.main(
                        [
                            "--state-home",
                            str(state_root),
                            "start",
                            "--repo",
                            str(root),
                            *extra_args,
                        ]
                    )
                self.assertEqual(result, 2)
                self.assertIn(expected, stderr.getvalue())
                self.assertEqual(module.read_json(_state_path)["status"], "paused")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "start",
                    "--repo",
                    str(root),
                    "--mode",
                    "backlog",
                    "--selector",
                    "all",
                    "--until",
                    "merge",
                    "--focus",
                    "CI pipeline",
                    "--json",
                ]
            )
        self.assertEqual(result, 0, stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["runId"], state["runId"])

    def test_cli_focus_changes_require_an_explicit_mode_and_task_boundary(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        state, state_path, _lock_path = self.make_state(module, root, state_root)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "focus",
                    "--repo",
                    str(root),
                    "--run-id",
                    state["runId"],
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("requires --clear", stderr.getvalue())

        active = module.read_json(state_path)
        module.transition_state(active, "selected", updates={"task": "task-one"})
        module.atomic_write_json(state_path, active)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "focus",
                    "--repo",
                    str(root),
                    "--run-id",
                    state["runId"],
                    "--prefer",
                    "CI pipeline",
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("task boundary", stderr.getvalue())

    def test_two_iteration_run_records_compact_results(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state = module.new_state(
            module.repository_identity(root),
            mode="backlog",
            selector="all",
            focus=module.normalize_focus(),
            until="merge",
            run_id="run-1",
        )

        for index in range(2):
            module.transition_state(
                state, "selected", updates={"task": f"task-{index + 1}"}
            )
            module.transition_state(state, "planning")
            module.transition_state(state, "implementing")
            module.transition_state(state, "validating")
            module.transition_state(state, "shipping")
            module.transition_state(state, "followups")
            module.record_result(
                state,
                task=f"task-{index + 1}",
                outcome="completed",
                pr_number=100 + index,
                pr_url=f"https://example.test/pr/{100 + index}",
                review_rounds=1,
                ci_retries=0,
                decisions=[f"selected task-{index + 1}"],
                followups=[],
            )
            module.transition_state(state, "inventory")

        self.assertEqual(state["iteration"], 3)
        self.assertEqual(state["counters"]["completed"], 2)
        self.assertEqual(state["counters"]["mergedPrs"], 2)
        self.assertEqual(
            [result["task"] for result in state["iterations"]],
            ["task-1", "task-2"],
        )

    def test_rank_candidate_file_pins_strict_utf8_decoding(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        self.make_state(module, root, state_root)
        candidates = root.parent / "candidates.json"
        candidates.write_text("[]\n", encoding="utf-8")
        calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        original_read_text = module.Path.read_text

        def tracked_read_text(path, *args, **kwargs):
            if path == candidates:
                calls.append((args, kwargs))
            return original_read_text(path, *args, **kwargs)

        stdout = io.StringIO()
        with (
            mock.patch.object(module.Path, "read_text", tracked_read_text),
            contextlib.redirect_stdout(stdout),
        ):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "rank",
                    "--repo",
                    str(root),
                    "--candidates-file",
                    str(candidates),
                    "--json",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {"candidates": [], "count": 0})
        self.assertEqual(
            calls,
            [((), {"encoding": "utf-8", "errors": "strict"})],
        )

    def test_public_cli_drives_a_complete_iteration(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        state, _state_path, _lock_path = self.make_state(
            module,
            root,
            state_root,
            focus=module.normalize_focus(preferred=["CI pipeline"]),
        )
        common = [
            "--state-home",
            str(state_root),
        ]

        def invoke(command: str, *arguments: str) -> dict[str, object]:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = module.main(
                    [
                        *common,
                        command,
                        "--repo",
                        str(root),
                        *arguments,
                        "--json",
                    ]
                )
            self.assertEqual(result, 0, stdout.getvalue())
            return json.loads(stdout.getvalue())

        status = invoke("status")
        self.assertEqual(status["runId"], state["runId"])

        candidates = root.parent / "candidates.json"
        candidates.write_text(
            json.dumps(
                [
                    {"id": "docs", "title": "Improve docs"},
                    {"id": "ci", "title": "Harden CI pipeline"},
                ]
            ),
            encoding="utf-8",
        )
        ranked = invoke("rank", "--candidates-file", str(candidates))
        self.assertEqual(ranked["candidates"][0]["id"], "ci")

        human_stdout = io.StringIO()
        with contextlib.redirect_stdout(human_stdout):
            result = module.main(
                [
                    *common,
                    "rank",
                    "--repo",
                    str(root),
                    "--candidates-file",
                    str(candidates),
                ]
            )
        self.assertEqual(result, 0, human_stdout.getvalue())
        self.assertIn("count: 2", human_stdout.getvalue())
        self.assertIn("- ci", human_stdout.getvalue())

        transition_args = ["--run-id", state["runId"], "--phase"]
        initial_head = module.run_git(root, "rev-parse", "HEAD")
        self.assertIsNotNone(initial_head)
        invoke(
            "transition",
            *transition_args,
            "selected",
            "--task",
            "ci",
            "--base-branch",
            "main",
        )
        invoke(
            "evidence",
            "--run-id",
            state["runId"],
            "--head",
            initial_head,
        )
        reconciled = invoke(
            "reconcile",
            "--run-id",
            state["runId"],
            "--observed-phase",
            "selected",
            "--task",
            "ci",
            "--head",
            initial_head,
        )
        self.assertEqual(reconciled["contextHealth"]["level"], "green")
        for phase in ("planning", "implementing", "validating", "shipping"):
            invoke("transition", *transition_args, phase)
        shipped = invoke(
            "evidence",
            "--run-id",
            state["runId"],
            "--pr-number",
            "42",
            "--pr-url",
            "https://example.test/pull/42",
            "--last-shipped-sha",
            initial_head,
        )
        self.assertEqual(shipped["current"]["prNumber"], 42)
        invoke("transition", *transition_args, "followups")
        completed = invoke(
            "result",
            "--run-id",
            state["runId"],
            "--task",
            "ci",
            "--outcome",
            "completed",
            "--pr-number",
            "42",
            "--pr-url",
            "https://example.test/pr/42",
            "--review-rounds",
            "2",
            "--decision",
            "selected CI first",
        )
        self.assertEqual(completed["counters"]["completed"], 1)

        invoke("transition", *transition_args, "inventory")
        focused = invoke("focus", "--run-id", state["runId"], "--clear")
        self.assertEqual(focused["focus"]["mode"], "none")
        invoke(
            "checkpoint",
            "--run-id",
            state["runId"],
            "--target",
            "next task",
            "--reason",
            "iteration boundary",
        )
        invoke("heartbeat", "--run-id", state["runId"])
        stopped = invoke(
            "stop",
            "--run-id",
            state["runId"],
            "--status",
            "completed",
            "--reason",
            "backlog exhausted",
        )
        self.assertEqual(stopped["status"], "completed")
        self.assertEqual(stopped["phase"], "stopped")

    def test_cli_rejects_unknown_run_before_mutating_state(self) -> None:
        module = self.load_module()
        root = self.make_repo()
        state_root = root.parent / "state"
        _state, state_path, _lock = self.make_state(module, root, state_root)
        before = state_path.read_bytes()
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            result = module.main(
                [
                    "--state-home",
                    str(state_root),
                    "transition",
                    "--repo",
                    str(root),
                    "--run-id",
                    "wrong-run",
                    "--phase",
                    "selected",
                ]
            )

        self.assertEqual(result, 2)
        self.assertIn("state belongs to run", stderr.getvalue())
        self.assertEqual(state_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
