from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

install = _support.install
InstallTestCase = _support.InstallTestCase

GUIDE_TEMPLATE = install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"
README = install.ROOT / "README.md"

SKILL_SECTIONS = (
    "## When to use",
    "## Arguments",
    "## Workflow",
    "## Safety rules",
    "## Final report",
)

# name -> (short form, skill pins, adapter pins)
COMMANDS = {
    "sd-watch-pr": (
        "watch-pr",
        [
            "timeout-minutes=",
            "no-merge",
            "never merges directly",
            "sd-housekeeping",
        ],
        ["sd-housekeeping"],
    ),
    "sd-fix-ci": (
        "fix-ci",
        [
            "real-code",
            "flake",
            "infra",
            "stale-baseline",
            "max-reruns=",
            "weaken tests",
        ],
        ["weaken tests"],
    ),
    "sd-update-deps": (
        "update-deps",
        [
            "include-runtime-minor",
            "dry-run",
            "majors are always manual",
            "sequential",
        ],
        ["Majors are always manual"],
    ),
    "sd-fleet-refresh": (
        "fleet-refresh",
        [
            "consumer=",
            "no-merge",
            "remote-review",
            "dry-run",
            "remote=",
            "bounded post-canary waves",
            "FLEET_ROLLOUT.md",
            "fleet-preflight",
            "fleet-finding-classify",
            "fleet-review-classify",
            "release-identity guard",
            "integration-only",
        ],
        ["bounded isolated waves"],
    ),
    "sd-test-gaps": (
        "test-gaps",
        [
            "file=",
            "max-gaps=",
            "test files and fixtures only",
            "baseline",
        ],
        ["test files and fixtures only"],
    ),
    "sd-ship": (
        "ship",
        [
            "until=pr|review|merge",
            "adds no new gate logic; every stage's own gates remain authoritative",
            "stage · outcome",
            "timeout-minutes=",
        ],
        ["only merge authority"],
    ),
    "sd-retro": (
        "retro",
        [
            "Retro: <topic>",
            "never auto-create",
            "sd-ai-command-pack-record-session.py",
            "explicit user consent",
        ],
        ["explicit user consent"],
    ),
}

POSITIONAL_PRIMARY_INPUTS = {
    "sd-retro": (
        "`sd-retro deployment timeout`",
        '`topic="deployment timeout"`',
    ),
    "sd-test-gaps": (
        "`sd-test-gaps scripts/example.py`",
        "`file=scripts/example.py`",
    ),
    "sd-fleet-refresh": (
        "`sd-fleet-refresh loadsmith rwbp-website`",
        "`consumer=loadsmith,rwbp-website`",
    ),
    "sd-audit-repo": (
        "`sd-audit-repo security testing`",
        "`dimensions=security,testing`",
    ),
    "sd-status": (
        "`sd-status /path/to/repo`",
        "`sd-status --repo /path/to/repo`",
    ),
}


class SdlcCommandsTests(InstallTestCase):
    """Format-drift protection for the six SDLC edge-loop command skills."""

    def _skill_text(self, name: str) -> str:
        path = install.ROOT / f"templates/.agents/skills/{name}/SKILL.md"
        return path.read_text(encoding="utf-8")

    def test_skill_sections_frontmatter_and_pins(self) -> None:
        for name, (_short, pins, _adapter_pins) in COMMANDS.items():
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                self.assertIn(f"name: {name}", skill)
                self.assertIn("description: Use when", skill)
                last = -1
                for section in SKILL_SECTIONS:
                    pos = skill.find(section)
                    self.assertGreater(pos, last, f"{name}: {section} order")
                    last = pos
                for pin in pins:
                    self.assertIn(pin, skill, f"{name}: missing pin {pin!r}")

    def test_skills_declare_no_environment_variables(self) -> None:
        for name in COMMANDS:
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                self.assertNotIn("SD_AI_COMMAND_PACK_", skill)

    def test_update_deps_delegates_eligibility_and_merge_to_housekeeping(self) -> None:
        skill = self._skill_text("sd-update-deps")

        self.assertIn(
            "bash scripts/sd-ai-command-pack-housekeeping.sh --dependency-pr <number>",
            skill,
        )
        self.assertIn("schema-versioned PR eligibility", skill)
        self.assertNotIn("```bash\ngh pr merge", skill)
        self.assertIn("must not invoke\n  `gh pr merge`", skill)

    def test_skills_state_unknown_argument_rule_and_scannable_report(self) -> None:
        for name in COMMANDS:
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                self.assertIn(
                    "error", skill.split("## Arguments")[1].split("##")[0].lower()
                )
                report = skill.split("## Final report")[1]
                self.assertIn("explicitly", report)

    def test_commands_document_fail_closed_positional_primary_inputs(self) -> None:
        for name, pins in POSITIONAL_PRIMARY_INPUTS.items():
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                arguments = skill.split("## Arguments", 1)[1].split("##", 1)[0]
                normalized_arguments = " ".join(arguments.split())
                for pin in pins:
                    self.assertIn(pin, normalized_arguments)
                self.assertIn("positional", arguments.lower())
                self.assertIn("reject", arguments.lower())
                self.assertIn("before", arguments.lower())

        fleet = self._skill_text("sd-fleet-refresh")
        audit = self._skill_text("sd-audit-repo")
        status = self._skill_text("sd-status")
        self.assertIn("normalized", fleet.split("## Workflow", 1)[0].lower())
        self.assertIn("normalized", audit.split("## Pipeline", 1)[0].lower())
        self.assertNotIn("[fleet|REPO_PATH] [--repo PATH]", status)
        self.assertIn("sd-ai-command-pack-status.py --repo PATH", status)

        guide = GUIDE_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("`sd-status --repo /path/to/repo`", guide)

    def test_command_adapters_share_contract(self) -> None:
        for name, (short, _pins, adapter_pins) in COMMANDS.items():
            adapters = [
                install.ROOT / f"templates/.commands/{name}.md",
                install.ROOT / f"templates/.claude/commands/sd/{short}.md",
                install.ROOT / f"templates/.gemini/commands/sd/{short}.toml",
                install.ROOT / f"templates/.github/prompts/{name}.prompt.md",
            ]
            for adapter in adapters:
                with self.subTest(adapter=adapter.name):
                    content = adapter.read_text(encoding="utf-8")
                    self.assertIn(f"Resolve the `{name}` skill by name", content)
                    for pin in adapter_pins:
                        self.assertIn(pin, content)
                    self.assertIn("final-report format", content)

    def test_fleet_refresh_batches_corrective_release_findings(self) -> None:
        fleet = self._skill_text("sd-fleet-refresh")
        recovery = (
            install.ROOT
            / "templates/.agents/skills/sd-fleet-refresh/references/controller-recovery.md"
        ).read_text(encoding="utf-8")
        recovery_text = " ".join(recovery.split())

        skill_pins = (
            "## Corrective campaign",
            "pause consumer mutation",
            "ID | Contract family | Evidence | Severity | Disposition | Fix | Regression",
            "bounded contract-surface sweep",
            "partial candidate diagnostics",
            "scripts/sd-ai-command-pack-fleet-candidate-check.py",
            "must never replace the canonical candidate ledger",
            "select one corrective version",
            "one canonical full-fleet candidate validation",
            "urgent independent security defect",
            "resume the original fleet task",
        )
        for pin in skill_pins:
            self.assertIn(pin.casefold(), recovery_text.casefold())
        self.assertIn("references/controller-recovery.md", fleet)
        self.assertIn("only when", fleet.casefold())

    def test_fleet_refresh_records_internal_timing_without_public_controls(
        self,
    ) -> None:
        fleet = self._skill_text("sd-fleet-refresh")
        fleet_text = " ".join(fleet.split())
        recovery_text = " ".join(
            (
                install.ROOT
                / "templates/.agents/skills/sd-fleet-refresh/references/controller-recovery.md"
            )
            .read_text(encoding="utf-8")
            .split()
        )
        guide_normalized = " ".join(
            (install.ROOT / "docs/FLEET_ROLLOUT.md").read_text(encoding="utf-8").split()
        )
        arguments = fleet.split("## Arguments", 1)[1].split("## Timing evidence", 1)[0]
        for pin in (
            "scripts/sd-ai-command-pack-fleet-timing.py",
            "start both `reviewer-wait` and `ci-wait`",
            "report --run-id <run-id> --complete",
            "never changes a delivery gate's authoritative result",
        ):
            self.assertIn(pin.casefold(), fleet_text.casefold())
        timing = fleet.split("## Timing evidence", 1)[1].split("## Workflow", 1)[0]
        self.assertLess(
            timing.casefold().index("before executing"),
            timing.casefold().index("preflight action"),
        )
        for public_control in ("timing=", "run-id=", "state-home="):
            self.assertNotIn(public_control, arguments)

        for adapter in (
            install.ROOT / "templates/.commands/sd-fleet-refresh.md",
            install.ROOT / "templates/.claude/commands/sd/fleet-refresh.md",
            install.ROOT / "templates/.gemini/commands/sd/fleet-refresh.toml",
            install.ROOT / "templates/.github/prompts/sd-fleet-refresh.prompt.md",
        ):
            with self.subTest(adapter=adapter.name):
                content = adapter.read_text(encoding="utf-8")
                self.assertNotIn("fleet-timing", content)
                self.assertNotIn("state-home", content)

        ordered_recovery_pins = (
            "pause consumer mutation",
            "bounded contract-surface sweep",
            "select one corrective version",
            "one canonical full-fleet candidate validation",
            "resume the original fleet task",
        )
        positions = [
            recovery_text.casefold().index(pin) for pin in ordered_recovery_pins
        ]
        self.assertEqual(positions, sorted(positions))

        for pin in (
            "## Corrective Campaign",
            "Exact duplicates reuse the owning row",
            "Partial runs remain diagnostic",
            "Only the no-filter canonical command",
            "original fleet task",
        ):
            self.assertIn(pin.casefold(), guide_normalized.casefold())

    def test_fleet_finding_severity_gate_is_fail_closed_and_observation_complete(
        self,
    ) -> None:
        fleet = self._skill_text("sd-fleet-refresh")
        guide = (install.ROOT / "docs/FLEET_ROLLOUT.md").read_text(encoding="utf-8")
        fleet_text = " ".join(fleet.split())
        guide_text = " ".join(guide.split())

        for pin in (
            "## Finding severity gate",
            "sd-ai-command-pack-fleet-finding-classify.py",
            "continue-with-follow-ups",
            "pause-corrective-release",
            "invalid-pause",
            "Reply with evidence to every observation",
            "one source or consumer Trellis follow-up per deferred owner",
            "Every duplicate still receives its own evidence-backed reply",
            "overrideDisposition",
            "overrideRationale",
            "before watch or merge",
        ):
            self.assertIn(pin.casefold(), fleet_text.casefold())

        ordered_pins = (
            "run the finding severity gate",
            "settle required checks",
            "consumer's `sd-housekeeping` gate",
        )
        positions = [
            fleet_text.casefold().index(pin.casefold()) for pin in ordered_pins
        ]
        self.assertEqual(positions, sorted(positions))

        for pin in (
            "contractFamily",
            "impactEvidence",
            "Conflicting family, impact, or override policy",
            "follow-up task IDs",
        ):
            self.assertIn(pin.casefold(), guide_text.casefold())

        for adapter in (
            install.ROOT / "templates/.commands/sd-fleet-refresh.md",
            install.ROOT / "templates/.claude/commands/sd/fleet-refresh.md",
            install.ROOT / "templates/.gemini/commands/sd/fleet-refresh.toml",
            install.ROOT / "templates/.github/prompts/sd-fleet-refresh.prompt.md",
        ):
            with self.subTest(adapter=adapter):
                content = adapter.read_text(encoding="utf-8")
                self.assertNotIn("overrideDisposition", content)
                self.assertNotIn("impactEvidence", content)

    def test_fleet_refresh_uses_bounded_manifest_ordered_waves(self) -> None:
        fleet = self._skill_text("sd-fleet-refresh")
        fleet_text = " ".join(fleet.split())
        guide = " ".join(
            (install.ROOT / "docs/FLEET_ROLLOUT.md").read_text(encoding="utf-8").split()
        )

        for pin in (
            "## Campaign controller",
            "sd-ai-command-pack-fleet-controller.py",
            "sequential canaries",
            "canStart",
            "maxConcurrency",
            "single eligible action",
            "--pack-blocker",
            "one existing checkout, branch, and PR",
            "controller alone invokes housekeeping",
            "terminal consumers are never restarted",
        ):
            self.assertIn(pin.casefold(), fleet_text.casefold())
        self.assertNotIn("temporary schema-version-1 snapshot", fleet_text)

        for pin in (
            "schema-version-4 manifest",
            "bounded post-canary cohort with concurrency two",
            "one at a time in manifest order",
            "pack blocker stops new starts and holds unsettled merges",
        ):
            self.assertIn(pin.casefold(), guide.casefold())

        arguments = fleet.split("## Arguments", 1)[1].split(
            "## Campaign controller", 1
        )[0]
        for public_adapter in (
            install.ROOT / "templates/.commands/sd-fleet-refresh.md",
            install.ROOT / "templates/.claude/commands/sd/fleet-refresh.md",
            install.ROOT / "templates/.gemini/commands/sd/fleet-refresh.toml",
            install.ROOT / "templates/.github/prompts/sd-fleet-refresh.prompt.md",
        ):
            content = public_adapter.read_text(encoding="utf-8")
            self.assertNotIn("--state", content)
            self.assertNotIn("maxConcurrency=", content)
        self.assertNotIn("--state", arguments)

    def test_ship_assigns_lifecycle_side_effects_to_one_stage(self) -> None:
        review = self._skill_text("sd-review-pr")
        ship = self._skill_text("sd-ship")
        review_text = " ".join(review.split())
        ship_text = " ".join(ship.split())

        self.assertIn("defer-finish-work", review_text)
        self.assertIn("accepted from `sd-ship`", review_text)
        self.assertIn("active `sd-fleet-refresh`", review_text)
        self.assertIn("Standalone `sd-review-pr`", review_text)
        self.assertIn("routing in Steps 1.5 and 8", review_text)
        self.assertIn("run the SD finish-work flow automatically", review_text)
        self.assertIn("Finish-work deferred to Stage 4", review_text)
        review_step_8 = review.split("## Step 8")[1].split("## Final Report")[0]
        self.assertIn("Resolve the `sd-finish-work` skill by name", review_step_8)
        self.assertIn("scripts/sd-ai-command-pack-record-session.py", review_step_8)
        self.assertNotIn(".agents/skills/trellis-finish-work/SKILL.md", review_step_8)
        self.assertNotIn("Resolve the `trellis-finish-work` skill", review_step_8)
        self.assertEqual(
            review_step_8.count(
                'PR_STATE=$(gh pr view "$PR_NUMBER" --json state --jq .state)'
            ),
            2,
        )

        self.assertIn("`until=review`", ship_text)
        self.assertIn("without `defer-finish-work`", ship_text)
        self.assertIn("with `defer-finish-work`", ship_text)
        self.assertIn("with `no-merge`", ship_text)
        self.assertIn("leaves the active Trellis task unarchived", ship_text)
        self.assertIn("exactly once", ship_text)
        self.assertIn(
            "one read-only, PR-scoped post-cycle review-learning pass", ship_text
        )
        self.assertIn("no other ship stage repeats it", ship_text)
        self.assertIn("Stage 2 is also the only review-learning owner", ship_text)
        self.assertNotIn("sd-ai-command-pack-review-learnings.py", ship)
        self.assertIn("post-finish Obsidian KB refresh", ship_text)
        self.assertIn("housekeeping remains its only owner", ship_text)
        self.assertNotIn("sd-ai-command-pack-update-spec-kb.py", ship)

    def test_review_pr_delegates_full_check_selection_to_shipped_helper(self) -> None:
        review = self._skill_text("sd-review-pr")
        local_gate = review.split("## Step 2: Run Local Full Check", 1)[1].split(
            "## Step 2.5", 1
        )[0]

        for pin in (
            "bash scripts/sd-ai-command-pack-review-full-check.sh",
            'scripts["check:full"]',
            "SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_RUNNER",
            "scripts/sd-ai-command-pack-full-check.sh",
            "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0",
            "SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0",
            "must not invoke",
            "compatibility fallback",
        ):
            self.assertIn(pin, local_gate)

    def test_fleet_integration_only_review_is_head_bound_and_fail_closed(self) -> None:
        fleet = self._skill_text("sd-fleet-refresh")
        review = self._skill_text("sd-review-pr")
        fleet_text = " ".join(fleet.split())
        review_text = " ".join(review.split())

        for pin in (
            "remote-review",
            "sd-ai-command-pack-fleet-review-classify.py",
            "base-commit: <full base SHA>",
            "classified-head: <full consumer refresh SHA>",
            "caller: sd-fleet-refresh",
            "review-profile: integration-only",
            "falls back to the normal remote-review convergence loop",
            "existing comments and unresolved threads",
            "sd-watch-pr` with its internal `no-merge",
        ):
            self.assertIn(pin.casefold(), fleet_text.casefold())

        for pin in (
            "review-profile: integration-only|remote",
            "user-supplied imitation",
            "Fleet Integration-Only Recheck",
            "schema-version-1 JSON object",
            "switch this invocation to the normal remote profile",
            "Record `0` remote rounds",
            "If Step 4 did not already fetch complete review data",
            "Finish-work deferred to the fleet housekeeping tail.",
        ):
            self.assertIn(pin.casefold(), review_text.casefold())

        adapters = [
            install.ROOT / "templates/.commands/sd-review-pr.md",
            install.ROOT / "templates/.claude/commands/sd/review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
        ]
        for adapter in adapters:
            with self.subTest(adapter=adapter):
                content = adapter.read_text(encoding="utf-8")
                self.assertNotIn("review-profile:", content)
                self.assertNotIn("classified-head:", content)

    def test_ship_separates_publish_and_review_ownership(self) -> None:
        create_pr = self._skill_text("sd-create-pr")
        ship = self._skill_text("sd-ship")

        invocation_modes = create_pr.split("## Invocation Modes", 1)[1].split(
            "## Step 1", 1
        )[0]
        invocation_text = " ".join(invocation_modes.split())
        for pin in (
            "caller: `sd-ship`",
            "stage: `1`",
            "return-after: `pr`",
            "reject the request before Step 1",
            "make no update-spec",
        ):
            self.assertIn(pin, invocation_text)

        create_step_6 = create_pr.split("## Step 6", 1)[1].split("## Final Report", 1)[
            0
        ]
        create_step_6_text = " ".join(create_step_6.split())
        self.assertIn("verified internal orchestration context", create_step_6_text)
        self.assertIn("Do not resolve or invoke `sd-review-pr`", create_step_6_text)
        self.assertIn("For every standalone invocation", create_step_6_text)
        self.assertIn("resolve and follow the `sd-review-pr`", create_step_6_text)

        safety_text = " ".join(
            create_pr.split("## Safety Rules", 1)[1]
            .split("## Invocation Modes", 1)[0]
            .split()
        )
        self.assertIn("In standalone mode, also resolve `sd-review-pr`", safety_text)
        self.assertIn("the composite owns `sd-review-pr` resolution", safety_text)

        ship_stage_1 = ship.split("2. Stage 1", 1)[1].split("3. Stage 2", 1)[0]
        ship_stage_1_text = " ".join(ship_stage_1.split())
        for pin in (
            "caller: sd-ship",
            "stage: 1",
            "return-after: pr",
            "without entering `sd-create-pr`'s standalone review handoff",
            "stop the chain here without running review",
        ):
            self.assertIn(pin, ship_stage_1_text)

        ship_safety = ship.split("## Safety rules", 1)[1].split("## Final report", 1)[0]
        ship_safety_text = " ".join(ship_safety.split())
        self.assertIn("Stage 1 always returns after publishing", ship_safety_text)
        self.assertIn("does not run for `until=pr`", ship_safety_text)
        self.assertIn("runs once normally for `until=review`", ship_safety_text)
        self.assertIn(
            "runs once with `defer-finish-work` for `until=merge`",
            ship_safety_text,
        )

    def test_create_pr_prepares_tooling_only_fill_body_before_handoff(self) -> None:
        create_pr = self._skill_text("sd-create-pr")
        step_5 = create_pr.split("## Step 5", 1)[1].split("## Step 6", 1)[0]
        normalized = " ".join(step_5.split())

        for pin in (
            'if ! gh pr create --base "$BASE_BRANCH" --fill; then',
            "PR_BODY_FILE= CHANGED_FILES_FILE=",
            "if ! PR_BODY_FILE=$(mktemp",
            "if ! CHANGED_FILES_FILE=$(mktemp",
            'if ! git diff --name-only -z "$BASE_REF"...HEAD',
            "if ! gh pr view --json body --jq .body",
            "--prepare-tooling-body",
            'if ! gh pr edit --body-file "$PR_BODY_FILE"; then',
            "PR creation failed; stop before Step 6.",
            "cannot create secure PR-body temporary file; stop before Step 6.",
            "cannot create secure changed-files temporary file; stop before Step 6.",
            "cannot capture NUL-delimited changed paths; stop before Step 6.",
            "cannot fetch GitHub's auto-filled PR body; stop before Step 6.",
            "automatic PR-body update failed; stop before Step 6.",
            "mixed-scope",
            "stop before Step 6",
            "secure regular temporary",
        ):
            self.assertIn(pin, normalized)

        self.assertIn("user-provided body", normalized)
        self.assertIn("byte-for-byte", normalized)
        self.assertIn("standalone", normalized)
        self.assertIn("verified `sd-ship` Stage 1", normalized)
        self.assertNotIn("gh pr edit --body ", step_5)
        self.assertNotIn("gh pr create --body ", step_5)
        self.assertNotIn("keeping GitHub's auto-filled body unchanged", step_5)

    def test_create_pr_runs_review_preflight_before_publication(self) -> None:
        create_pr = self._skill_text("sd-create-pr")
        step_3 = create_pr.split("## Step 3", 1)[1].split("## Step 4", 1)[0]
        normalized = " ".join(step_3.split())

        preflight = "node scripts/sd-ai-command-pack-review-preflight.mjs"
        self.assertIn('git diff --check "$BASE_REF"...HEAD', step_3)
        self.assertIn(preflight, step_3)
        self.assertLess(
            step_3.index(preflight), step_3.index("git add <intended paths>")
        )
        self.assertIn("stop before staging, committing, or pushing", normalized)
        self.assertIn(
            "Do not treat a later `sd-review-pr` run as a substitute", normalized
        )
        self.assertIn("reinstall sd-ai-command-pack before publishing", normalized)

        final_report = create_pr.split("## Final Report", 1)[1]
        self.assertIn("Pre-publication review preflight result", final_report)

    def test_create_pr_adapters_do_not_expose_internal_ship_context(self) -> None:
        adapters = [
            install.ROOT / "templates/.commands/sd-create-pr.md",
            install.ROOT / "templates/.claude/commands/sd/create-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/create-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-create-pr.prompt.md",
        ]
        for adapter in adapters:
            content = adapter.read_text(encoding="utf-8")
            normalized_content = content.replace("`", "")
            with self.subTest(adapter=adapter.name):
                for internal_control in (
                    "publish-only",
                    "caller=",
                    "stage=",
                    "return-after=",
                    "caller: sd-ship",
                    "stage: 1",
                    "return-after: pr",
                ):
                    self.assertNotIn(internal_control, normalized_content)

    def test_work_backlog_is_the_single_resumable_full_cycle_controller(self) -> None:
        backlog = self._skill_text("sd-work-backlog")
        ship = self._skill_text("sd-ship")
        backlog_text = " ".join(backlog.split())
        ship_text = " ".join(ship.split())

        for pin in (
            "canonical autonomous work-loop controller",
            "sd-ai-command-pack-work-loop.py",
            "focus-only=",
            "focused_backlog_exhausted",
            "Around a natural clean boundary between approximately eight and twelve",
            "caller: sd-work-backlog",
            "return-after: merge-result",
            "A clean nested housekeeping report is a return value",
            "Do not emit the overall final response while the helper remains active",
            "selector=needs-design",
            "recovery.reasonCode",
            "Load only the exact reported reference",
        ):
            self.assertIn(pin, backlog_text)
        self.assertNotIn("start --repo . --mode backlog", backlog_text)
        self.assertIn("SD_SHIP_MERGE_RESULT", ship_text)
        self.assertIn("trusted `sd-work-backlog` context", ship_text)
        self.assertIn("does not change stage order", ship_text)
        self.assertIn(
            "after follow-up task creation and before recording the iteration result",
            backlog_text,
        )
        self.assertIn("sd-ai-command-pack-update-spec-kb.py --if-present", backlog_text)
        self.assertIn("blocks the iteration", backlog_text)

    def test_update_spec_routes_flat_optional_references(self) -> None:
        skill_path = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        )
        skill = skill_path.read_text(encoding="utf-8")
        normalized = " ".join(skill.split())
        references = (
            "references/repository-map.md",
            "references/architecture.md",
            "references/obsidian-kb.md",
        )

        self.assertIn("A routine spec-only run loads no optional reference", normalized)
        self.assertIn("load each at most once", normalized)
        self.assertIn("never follow a reference from another reference", normalized)
        self.assertIn("missing, unreadable, empty, escaping, or contradictory", normalized)
        self.assertIn(
            "bash scripts/sd-ai-command-pack-toolchain.sh run-python -- "
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            normalized,
        )
        for relative in references:
            with self.subTest(reference=relative):
                self.assertEqual(skill.count(relative), 2)
                content = (skill_path.parent / relative).read_text(encoding="utf-8")
                self.assertTrue(content.strip())
                self.assertNotIn("references/", content)

    def test_work_loop_adapters_forward_arguments_and_do_not_duplicate_policy(
        self,
    ) -> None:
        adapter = install.ROOT / "templates/.commands/sd-work-backlog.md"
        content = " ".join(adapter.read_text(encoding="utf-8").split())
        self.assertIn("Pass all invocation arguments unchanged", content)
        self.assertIn("focus=", content)
        self.assertIn("focus-only=", content)
        self.assertIn("selector=all|needs-design", content)
        self.assertIn("until=design|merge", content)
        self.assertIn("Resolve the `sd-work-backlog` skill by name", content)

    def test_status_skill_declares_read_only_work_loop_inventory(self) -> None:
        status = " ".join(self._skill_text("sd-status").split())
        for pin in (
            "user-local autonomous work-loop state",
            "run ID, mode, selector/focus, iteration, phase",
            "Do not acquire or refresh its lock",
            "absent state is `none`",
            "`F-*` rows",
            "`T-*` rows enumerate every valid unarchived Trellis task",
            "`R-*` rows enumerate open top-level Trellis tasks",
            "report-local selector",
        ):
            self.assertIn(pin, status)

    def test_usage_guide_documents_ship_lifecycle_ownership(self) -> None:
        guide = GUIDE_TEMPLATE.read_text(encoding="utf-8")
        guide_text = " ".join(guide.split())

        self.assertIn("`until=review` keeps finish-work in `sd-review-pr`", guide_text)
        self.assertIn("defers finish-work to Stage 4", guide_text)
        self.assertIn("watches with `no-merge`", guide_text)
        self.assertIn("housekeeping exactly once", guide_text)
        self.assertIn("Stage 2 the only review owner", guide_text)
        self.assertIn("no review for `until=pr`", guide_text)
        self.assertIn("one post-cycle review-learning pass", guide_text)
        self.assertIn(
            "No later ship, watch, finish-work, or housekeeping stage repeats it",
            guide_text,
        )

    def test_usage_guide_documents_all_six(self) -> None:
        guide = GUIDE_TEMPLATE.read_text(encoding="utf-8")
        for name, (short, _pins, _apins) in COMMANDS.items():
            with self.subTest(command=name):
                if name in install.SOURCE_ONLY_COMMAND_NAMES:
                    self.assertNotIn(
                        f"`.agents/skills/{name}/SKILL.md`",
                        guide,
                    )
                    self.assertNotIn(f"/sd:{short}", guide)
                    self.assertNotIn(f"/sd-{short}", guide)
                    self.assertIn(
                        f"The `{name}` command is an operator workflow available only",
                        guide,
                    )
                    continue
                self.assertIn(f"`.agents/skills/{name}/SKILL.md`", guide)
                self.assertIn(f"/sd:{short}", guide)
                self.assertIn(f"/sd-{short}", guide)
                self.assertIn(f"The `{name}` command", guide)
        for pin in [
            "whose gate remains the only merge authority",
            "never deletes, skips, or weakens tests",
            "Majors are\nalways manual",
            "manifest-defined canaries\nsequentially",
            "test files and fixtures only",
            "auto-creates tasks and makes no code changes",
        ]:
            self.assertIn(pin, guide)

    def test_readme_documents_all_six(self) -> None:
        readme = README.read_text(encoding="utf-8")
        for name in COMMANDS:
            with self.subTest(command=name):
                self.assertIn(f"### {name}", readme)


if __name__ == "__main__":
    _support.unittest.main()
