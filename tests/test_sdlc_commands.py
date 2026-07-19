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
            "dry-run",
            "one consumer at a time",
            "FLEET_ROLLOUT.md",
            "fleet-preflight",
        ],
        ["one consumer at a time"],
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
            "adds no new gate logic; every stage's own gates remain "
            "authoritative",
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

    def test_skills_state_unknown_argument_rule_and_scannable_report(self) -> None:
        for name in COMMANDS:
            with self.subTest(skill=name):
                skill = self._skill_text(name)
                self.assertIn("error", skill.split("## Arguments")[1].split("##")[0].lower())
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
                    self.assertIn(
                        f"Resolve the `{name}` skill by name", content
                    )
                    for pin in adapter_pins:
                        self.assertIn(pin, content)
                    self.assertIn("final-report format", content)

    def test_ship_assigns_lifecycle_side_effects_to_one_stage(self) -> None:
        review = self._skill_text("sd-review-pr")
        ship = self._skill_text("sd-ship")
        review_text = " ".join(review.split())
        ship_text = " ".join(ship.split())

        self.assertIn("defer-finish-work", review_text)
        self.assertIn("accepted only from `sd-ship`", review_text)
        self.assertIn("Standalone `sd-review-pr`", review_text)
        self.assertIn("routing in Steps 1.5 and 8", review_text)
        self.assertIn(
            "run the Trellis finish-work flow automatically", review_text
        )
        self.assertIn("Finish-work deferred to Stage 4", review_text)
        review_step_8 = review.split("## Step 8")[1].split("## Final Report")[0]
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
        self.assertIn("one read-only, PR-scoped post-cycle review-learning pass", ship_text)
        self.assertIn("no other ship stage repeats it", ship_text)
        self.assertIn("Stage 2 is also the only review-learning owner", ship_text)
        self.assertNotIn("sd-ai-command-pack-review-learnings.py", ship)

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

        create_step_6 = create_pr.split("## Step 6", 1)[1].split(
            "## Final Report", 1
        )[0]
        create_step_6_text = " ".join(create_step_6.split())
        self.assertIn(
            "verified internal orchestration context", create_step_6_text
        )
        self.assertIn(
            "Do not resolve or invoke `sd-review-pr`", create_step_6_text
        )
        self.assertIn("For every standalone invocation", create_step_6_text)
        self.assertIn(
            "resolve and follow the `sd-review-pr`", create_step_6_text
        )

        safety_text = " ".join(
            create_pr.split("## Safety Rules", 1)[1].split(
                "## Invocation Modes", 1
            )[0].split()
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

        ship_safety = ship.split("## Safety rules", 1)[1].split(
            "## Final report", 1
        )[0]
        ship_safety_text = " ".join(ship_safety.split())
        self.assertIn("Stage 1 always returns after publishing", ship_safety_text)
        self.assertIn("does not run for `until=pr`", ship_safety_text)
        self.assertIn("runs once normally for `until=review`", ship_safety_text)
        self.assertIn(
            "runs once with `defer-finish-work` for `until=merge`",
            ship_safety_text,
        )

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

    def test_usage_guide_documents_ship_lifecycle_ownership(self) -> None:
        guide = GUIDE_TEMPLATE.read_text(encoding="utf-8")
        guide_text = " ".join(guide.split())

        self.assertIn(
            "`until=review` keeps finish-work in `sd-review-pr`", guide_text
        )
        self.assertIn("defers finish-work to Stage 4", guide_text)
        self.assertIn("watches with `no-merge`", guide_text)
        self.assertIn("housekeeping exactly once", guide_text)
        self.assertIn("Stage 2 the only review owner", guide_text)
        self.assertIn("no review for `until=pr`", guide_text)
        self.assertIn("one post-cycle review-learning pass", guide_text)
        self.assertIn("No later ship, watch, finish-work, or housekeeping stage repeats it", guide_text)

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
                        f"The `{name}` command is an operator workflow "
                        "available only",
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
            "one consumer at a time",
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
