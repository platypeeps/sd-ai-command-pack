from __future__ import annotations

import re

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

# The one exempt environment variable, matched as a whole name. A plain
# substring removal would also consume the prefix of a longer name such as
# `SD_AI_COMMAND_PACK_TOOLCHAIN_EXTRA`, leaving a tail that no longer contains
# the forbidden prefix -- so the exemption would silently excuse every variable
# whose name starts with the exempt one. The continuation class is `\w` rather
# than the uppercase env-var convention: the test exists to catch a name nobody
# expected, and a lowercase tail is exactly that kind of name.
TOOLCHAIN_VARIABLE_RE = re.compile(r"SD_AI_COMMAND_PACK_TOOLCHAIN(?!\w)")

SKILL_SECTIONS = (
    "## When to use",
    "## Arguments",
    "## Workflow",
    "## Safety rules",
    "## Final report",
)

# name -> (short form, skill pins, adapter pins)
COMMANDS = {
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
        """No skill takes environment tuning of its own.

        `SD_AI_COMMAND_PACK_TOOLCHAIN` is exempt and is not a counterexample:
        it is not a tuning surface of any skill but the first candidate of the
        shared resolution bootstrap, byte-identical in every skill that invokes
        a helper and pinned by .github/scripts/check-helper-resolution.py. It
        selects which install answers, never what a workflow does. Any other
        `SD_AI_COMMAND_PACK_` name is still a violation.
        """

        for name in COMMANDS:
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                remaining = TOOLCHAIN_VARIABLE_RE.sub("", skill)
                self.assertNotIn("SD_AI_COMMAND_PACK_", remaining)

    def test_the_exemption_does_not_cover_a_longer_variable_name(self) -> None:
        """The exemption is one name, not a prefix every name may extend."""

        self.assertEqual(
            TOOLCHAIN_VARIABLE_RE.sub("", "$SD_AI_COMMAND_PACK_TOOLCHAIN"), "$"
        )
        self.assertIn(
            "SD_AI_COMMAND_PACK_",
            TOOLCHAIN_VARIABLE_RE.sub("", "$SD_AI_COMMAND_PACK_TOOLCHAIN_EXTRA"),
        )
        self.assertIn(
            "SD_AI_COMMAND_PACK_",
            TOOLCHAIN_VARIABLE_RE.sub("", "$SD_AI_COMMAND_PACK_TOOLCHAIN_extra"),
        )

    def test_update_deps_delegates_eligibility_and_merge_to_housekeeping(self) -> None:
        skill = self._skill_text("sd-update-deps")

        self.assertIn(
            'bash "$SD_PACK_TOOLCHAIN" run -- '
            "sd-ai-command-pack-housekeeping.sh --dependency-pr <number>",
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
                    if name == "sd-fleet-refresh":
                        # Source-only skill: the command reads its checkout file
                        # directly instead of resolving it by name.
                        self.assertIn(
                            "Load the fleet-refresh procedure by reading "
                            "`.agents/skills/sd-fleet-refresh/SKILL.md`",
                            content,
                        )
                    else:
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
            "sd-ai-command-pack-fleet-candidate-check.py",
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

    def test_fleet_refresh_prepares_task_lifecycle_and_append_only_recovery(self) -> None:
        fleet = " ".join(self._skill_text("sd-fleet-refresh").split())
        recovery = " ".join(
            (
                install.ROOT
                / "templates/.agents/skills/sd-fleet-refresh/references/controller-recovery.md"
            )
            .read_text(encoding="utf-8")
            .split()
        )

        for pin in (
            "create and activate one dedicated lightweight Trellis task",
            "immutable release identity",
            "bind it to the refresh branch",
            "dedicated consumer task artifacts",
            "complete the dedicated task through `sd-finish-work`",
            # The ordinary case: the journal commit moves the head on every
            # lane, and the receipt that produced it proves the advance.
            "record the issued action at the new head and pass that same "
            "finish-work receipt as `--finalization-receipt <path>`",
            # The rewind stays, for a head that moved for another reason.
            "reserve `retryable-failure --reason-code pr-head-advanced` "
            "against the old published head",
            "pass it to housekeeping without running finish-work again",
        ):
            self.assertIn(pin.casefold(), fleet.casefold())
        for pin in (
            "--recover-consumer <name>",
            "--corrective-release <version>",
            "task.py create --no-start",
            "preserve the failed finish-work journal commit",
            "never deletes the blocker receipt",
            "or replays the prior merge action",
            "do not widen ordinary journal-only recovery",
        ):
            self.assertIn(pin.casefold(), recovery.casefold())

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
            "bracket every stage with `stage-run`",
            "`reviewer-wait` and `ci-wait`, both started immediately after the",
            # The stranding cause: the skill named no command for closing a lane.
            "every selected consumer needs `consumer-end --run-id <run-id> "
            "--consumer <name> --outcome <outcome>`",
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
            "schema-version-5 manifest",
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
        self.assertNotIn("defer-finish-work", ship)
        self.assertNotIn("sd-review-pr", ship)
        self.assertIn("Stage 2 — `sd-review scope=pr`", ship_text)
        self.assertIn(
            "never merges, archives Trellis work, or runs housekeeping", ship_text
        )
        self.assertIn("`no-merge` is not an sd-ship argument", ship_text)
        self.assertIn("leaving the PR unmerged for a later resume", ship_text)
        self.assertIn(
            "keeps whatever state Stage 2b's finalization already established",
            ship_text,
        )
        self.assertIn("exactly once", ship_text)
        self.assertIn(
            "one read-only, PR-scoped post-cycle review-learning pass", ship_text
        )
        self.assertIn("no other ship stage repeats it", ship_text)
        self.assertIn("Stage 2b is the only review-learning owner", ship_text)
        self.assertNotIn("sd-ai-command-pack-review-learnings.py", ship)
        # Per-`until=` truth table: learning 0/1/1, finish-work 0/1/1 with
        # one owner — Stage 2b in both modes; Stage 4 only consumes the receipt.
        self.assertIn(
            "under both `until=review` and `until=merge`",
            ship_text,
        )
        self.assertIn("never for `until=pr`", ship_text)
        self.assertIn(
            "run the SD finish-work flow exactly once, bound to the exact head "
            "Stage 2 reviewed",
            ship_text,
        )
        self.assertIn("zero finish-work flow invocations", ship_text)
        self.assertIn("re-enter Stage 2's check/review loop for that head, once", ship_text)
        self.assertIn("A second finalization head is a defect", ship_text)
        self.assertIn(
            "the learning pass and finalization never run again", ship_text
        )
        self.assertIn(
            "Stage 2 itself never runs finish-work under any `until=` value",
            ship_text,
        )
        self.assertIn("Stage 2b owns finalization in both `until=` modes", ship_text)
        self.assertIn("post-archive-review-successor recovery", ship_text)
        self.assertIn("journal-only-recovery scope rules", ship_text)
        self.assertIn("that atomic recheck is the double-run guard", ship_text)
        self.assertIn(
            "Finish-work owner and outcome: Stage 2b in both `until=` modes",
            ship_text,
        )
        self.assertIn("post-finish Obsidian KB refresh", ship_text)
        self.assertIn("housekeeping remains its only owner", ship_text)
        self.assertNotIn("sd-ai-command-pack-update-spec-kb.py", ship)

    def test_ship_watch_coordinator_is_read_only_and_bounded(self) -> None:
        ship = self._skill_text("sd-ship")
        ship_text = " ".join(ship.split())
        coordinator = (
            install.ROOT
            / "templates/.agents/skills/sd-ship/references/watch-coordinator.md"
        ).read_text(encoding="utf-8")
        coordinator_text = " ".join(coordinator.split())

        self.assertIn("read-only 20-second poll of the eligibility probe", ship_text)
        self.assertIn("`timeout-minutes × 3` attempts", ship_text)
        for outcome in (
            "`settled-green`",
            "`settled-blocked`",
            "`timed-out`",
            "`probe-failed`",
        ):
            self.assertIn(outcome, ship_text)
            self.assertIn(outcome, coordinator_text)
        self.assertIn(
            "Only `settled-green` continues the chain to Stage 4", ship_text
        )

        self.assertIn(
            "it has no adapter, no catalog row, and no direct user invocation",
            coordinator_text,
        )
        self.assertIn(
            "never merges, never mutates local or remote state, and never hands "
            "off to housekeeping",
            coordinator_text,
        )
        self.assertIn("sd-ai-command-pack-pr-eligibility.py", coordinator_text)
        self.assertIn("--dependency-pr-number", coordinator_text)
        self.assertIn("Interval: 20 seconds between probes", coordinator_text)
        self.assertIn(
            "Stop at the ceiling regardless of state", coordinator_text
        )
        self.assertIn(
            "classification keys on `checks.items`, not on reason codes",
            coordinator_text,
        )
        self.assertIn(
            "do not add a second pagination path", coordinator_text
        )
        self.assertIn(
            "must not treat an absent thread list in a blocked report",
            coordinator_text,
        )

    def test_finish_work_gates_archive_and_single_push_with_one_validator(self) -> None:
        finish = self._skill_text("sd-finish-work")
        review = self._skill_text("sd-review-pr")
        housekeeping = self._skill_text("sd-housekeeping")
        ship = self._skill_text("sd-ship")
        finish_text = " ".join(finish.split())
        review_text = " ".join(review.split())
        housekeeping_text = " ".join(housekeeping.split())
        ship_text = " ".join(ship.split())

        validator = "sd-ai-command-pack-review-preflight.mjs"
        self.assertEqual(finish.count(validator), 2)
        self.assertLess(finish.index("pre-archive"), finish.index("task.py archive"))
        self.assertIn("final-bundle --mode <completion|planning>", finish)
        self.assertIn("pre_archive_valid", finish)
        self.assertIn("evidence.planningSubtype: journal-only-recovery", finish)
        self.assertIn("post-archive-review-successor", finish)
        self.assertIn("callers never select a third mode", finish_text)
        self.assertIn("does not retroactively apply", finish_text)
        self.assertIn("preserve archive and journal commits locally", finish_text)
        self.assertIn("Only after validation", finish)
        self.assertIn("one final push", finish_text)
        self.assertIn("private schema-version-1 JSON receipt", review_text)
        self.assertIn("independently recomputes and compares the proof", housekeeping_text)
        self.assertIn("--finish-work-receipt", housekeeping_text)
        self.assertIn("--finish-work-receipt", ship_text)
        for text in (finish_text, review_text, housekeeping_text, ship_text):
            self.assertNotIn("--finish-work-head", text)

    def test_review_pr_consumes_typed_sd_check_without_legacy_selection(self) -> None:
        review = self._skill_text("sd-review-pr")
        local_gate = review.split("## Step 2: Run Typed Deterministic Check", 1)[1].split(
            "## Step 2.5", 1
        )[0]

        for pin in (
            "sd-ai-command-pack-check.py --json",
            "schema-version-1 JSON",
            ".sd-ai-command-pack/check.json",
            "state guard passed",
        ):
            self.assertIn(pin, local_gate)
        for legacy in (
            'scripts["check:full"]',
            "SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_RUNNER",
            "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0",
            "SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0",
        ):
            self.assertNotIn(legacy, local_gate)

    def test_fleet_integration_only_review_is_head_bound_and_fail_closed(self) -> None:
        """Ownership after the port: the recheck procedure lives in
        ``sd-fleet-refresh``, the trusted profile lives in ``sd-review``, and
        ``sd-review-pr`` keeps only its own still-working path plus a pointer.
        """
        fleet = self._skill_text("sd-fleet-refresh")
        review_pr = self._skill_text("sd-review-pr")
        review = self._skill_text("sd-review")
        fleet_text = " ".join(fleet.split())
        review_pr_text = " ".join(review_pr.split())
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
            "through the read-only watch coordinator",
            # The recheck procedure itself moved here; it is no longer inlined
            # anywhere that ships.
            "Fleet Integration-Only Recheck",
            "schema-version-1 JSON object",
            "switch this invocation to the normal remote profile",
        ):
            self.assertIn(pin.casefold(), fleet_text.casefold())

        # The fleet now calls sd-review, not sd-review-pr.
        self.assertIn("invoke `sd-review` once".casefold(), fleet_text.casefold())
        self.assertNotIn("sd-review-pr".casefold(), fleet_text.casefold())

        for pin in (
            "review-profile: integration-only|remote",
            "user-supplied imitation",
            "Record `0` remote rounds",
            "Finish-work deferred to the fleet housekeeping tail.",
        ):
            self.assertIn(pin.casefold(), review_text.casefold())

        # sd-review ships, so it references the classifier by name rather than
        # inlining it; inlining would pull the script into its surface closure.
        self.assertNotIn(
            "sd-ai-command-pack-fleet-review-classify.py".casefold(),
            review_text.casefold(),
        )

        # sd-review-pr still runs its own path until the surface is deleted,
        # but the procedure is a pointer now, not a second live copy.
        for pin in (
            "review-profile: integration-only|remote",
            "user-supplied imitation",
            "Fleet Integration-Only Recheck",
            "Record `0` remote rounds",
            "If Step 4 did not already fetch complete review data",
            "Finish-work deferred to the fleet housekeeping tail.",
        ):
            self.assertIn(pin.casefold(), review_pr_text.casefold())
        self.assertNotIn(
            "sd-ai-command-pack-fleet-review-classify.py".casefold(),
            review_pr_text.casefold(),
        )

        adapters = [
            install.ROOT / "templates/.commands/sd-review-pr.md",
            install.ROOT / "templates/.claude/commands/sd/review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
            # sd-review now carries the trusted profile, so its adapters are
            # the new place a forged context could leak into argv.
            install.ROOT / "templates/.commands/sd-review.md",
            install.ROOT / "templates/.claude/commands/sd/review.md",
            install.ROOT / "templates/.gemini/commands/sd/review.toml",
            install.ROOT / "templates/.github/prompts/sd-review.prompt.md",
        ]
        # The security property is that *no* trusted-context field reaches
        # argv, not just the two most obvious ones. Checking a subset lets a
        # regression in `caller:` or `source-root:` through silently.
        trusted_fields = (
            "caller:",
            "review-profile:",
            "source-root:",
            "consumer:",
            "base-commit:",
            "release-remote:",
            "classified-head:",
            "return-after:",
            "defer-finish-work:",
        )
        for adapter in adapters:
            with self.subTest(adapter=adapter):
                content = adapter.read_text(encoding="utf-8")
                for field in trusted_fields:
                    self.assertNotIn(
                        field,
                        content,
                        f"{adapter.name} exposes trusted-context field {field!r} "
                        "as adapter text; it must stay context-only",
                    )

    def test_ship_separates_publish_and_review_ownership(self) -> None:
        create_pr = self._skill_text("sd-create-pr")
        ship = self._skill_text("sd-ship")

        invocation_modes = create_pr.split("## Invocation Modes", 1)[1].split(
            "## Step 1", 1
        )[0]
        invocation_text = " ".join(invocation_modes.split())
        for pin in (
            "one behavior in every invocation",
            "no composite-only delegation mode or internal orchestration context",
            "`sd-ship` Stage 1 invokes this same public flow",
            "reject the request before Step 1",
            "make no update-spec",
        ):
            self.assertIn(pin, invocation_text)
        for removed_control in ("caller: `sd-ship`", "stage: `1`", "return-after: `pr`"):
            self.assertNotIn(removed_control, invocation_text)

        create_step_6 = create_pr.split("## Step 6", 1)[1].split("## Final Report", 1)[
            0
        ]
        create_step_6_text = " ".join(create_step_6.split())
        self.assertNotIn("orchestration context", create_step_6_text)
        self.assertIn(
            "Do not resolve or invoke any review skill", create_step_6_text
        )
        self.assertIn(
            "in every invocation, including `sd-ship` Stage 1", create_step_6_text
        )
        self.assertIn(
            "names the next command instead: `sd-review scope=pr`",
            create_step_6_text,
        )
        self.assertIn("A composite caller reads the Step 5", create_step_6_text)

        safety_text = " ".join(
            create_pr.split("## Safety Rules", 1)[1]
            .split("## Invocation Modes", 1)[0]
            .split()
        )
        self.assertIn(
            "never resolves or invokes a review skill in any mode", safety_text
        )
        self.assertIn(
            "review ownership stays with `sd-review scope=pr`", safety_text
        )

        ship_stage_1 = ship.split("2. Stage 1", 1)[1].split("3. Stage 2", 1)[0]
        ship_stage_1_text = " ".join(ship_stage_1.split())
        for pin in (
            "run its public publish-only flow",
            "reports the next command instead of running review",
            "never resolves or invokes a review skill in any mode",
            "stop the chain here without running review",
        ):
            self.assertIn(pin, ship_stage_1_text)
        for removed_control in ("caller: sd-ship", "stage: 1", "return-after: pr"):
            self.assertNotIn(removed_control, ship_stage_1_text)

        ship_safety = ship.split("## Safety rules", 1)[1].split("## Final report", 1)[0]
        ship_safety_text = " ".join(ship_safety.split())
        self.assertIn("Stage 1 always returns after publishing", ship_safety_text)
        self.assertIn("does not run for `until=pr`", ship_safety_text)
        self.assertIn(
            "runs the same review-only loop once each for `until=review` and "
            "`until=merge`",
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
            # Exit 3 is "nothing to declare", not "mixed": a mixed diff is
            # declared with the generated paths named, which is what keeps the
            # heading in place through sd-ship finalization.
            "nothing to declare",
            "stop before Step 6",
            "secure regular temporary",
        ):
            self.assertIn(pin, normalized)

        self.assertIn("user-provided body", normalized)
        self.assertIn("byte-for-byte", normalized)
        self.assertIn("every invocation, including `sd-ship` Stage 1", normalized)
        self.assertNotIn("gh pr edit --body ", step_5)
        self.assertNotIn("gh pr create --body ", step_5)
        self.assertNotIn("keeping GitHub's auto-filled body unchanged", step_5)

    def test_create_pr_runs_review_preflight_before_publication(self) -> None:
        create_pr = self._skill_text("sd-create-pr")
        step_3 = create_pr.split("## Step 3", 1)[1].split("## Step 4", 1)[0]
        normalized = " ".join(step_3.split())

        preflight = 'bash "$SD_PACK_TOOLCHAIN" run -- sd-ai-command-pack-review-preflight.mjs'
        self.assertIn('git diff --check "$BASE_REF"...HEAD', step_3)
        self.assertIn(preflight, step_3)
        self.assertLess(
            step_3.index(preflight), step_3.index("git add <intended paths>")
        )
        self.assertIn("stop before staging, committing, or pushing", normalized)
        self.assertIn(
            "Do not treat a later `sd-review scope=pr` run as a substitute", normalized
        )
        # The bootstrap's failure branch is now the only diagnosis; the
        # separate command -v guard that could disagree with the call is gone.
        self.assertIn("Reinstall the command pack.", normalized)
        self.assertNotIn("command -v sd-ai-command-pack-review-preflight.mjs", normalized)

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
            'bash "$SD_PACK_TOOLCHAIN" run-python -- '
            "sd-ai-command-pack-update-spec-kb.py",
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
            "roadmap-like Markdown/text files",
            "path and line evidence",
            "report-local selector",
        ):
            self.assertIn(pin, status)

    def test_usage_guide_documents_ship_lifecycle_ownership(self) -> None:
        guide = GUIDE_TEMPLATE.read_text(encoding="utf-8")
        guide_text = " ".join(guide.split())

        self.assertIn("Stage 2b runs finish-work in both `until=` modes", guide_text)
        self.assertIn("zero finish-work flow invocations of its own", guide_text)
        self.assertIn("re-enters Stage 2 once for that head", guide_text)
        self.assertIn("second finalization head stops the chain as a defect", guide_text)
        self.assertIn("passes Stage 2b's retained receipt through `--finish-work-receipt`", guide_text)
        self.assertIn("direct read-only final-bundle validator invocation", guide_text)
        self.assertIn(
            "runs the internal read-only watch coordinator in Stage 3", guide_text
        )
        self.assertIn("housekeeping exactly once", guide_text)
        self.assertIn("Stage 2 is the only review owner", guide_text)
        self.assertIn("no review for `until=pr`", guide_text)
        self.assertIn("Stage 2b owns the one post-cycle review-learning pass", guide_text)
        self.assertIn(
            "for both `until=review` and `until=merge`. No other ship stage repeats it",
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
