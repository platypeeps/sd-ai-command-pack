from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

install = _support.install
InstallTestCase = _support.InstallTestCase

SKILL_TEMPLATE = install.ROOT / "templates/.agents/skills/sd-audit-repo/SKILL.md"
CHARTER_DIR = install.ROOT / "templates/.agents/skills/sd-audit-repo/charters"
GUIDE_TEMPLATE = install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md"

ALWAYS_ON_CHARTERS = (
    "architecture",
    "design",
    "correctness",
    "security",
    "testing",
    "documentation",
    "bloat",
    "performance",
    "dependencies",
    "tooling",
    "release-hygiene",
    "improvements",
)
CONDITIONAL_CHARTERS = ("consumer-impact", "observability", "accessibility-i18n")
CHARTER_ROSTER = ALWAYS_ON_CHARTERS + CONDITIONAL_CHARTERS

CHARTER_SECTION_HEADINGS = (
    "## Mission",
    "## Scope",
    "## Out of scope",
    "## Method",
    "## Severity guide",
    "## Output",
)

FINDING_SCHEMA = (
    "[<dimension>] <title>\n"
    "severity: P0-P3 · effort: S/M/L\n"
    "evidence: <file:line> (+ short excerpt or command output)\n"
    "why it matters: <1-2 sentences>\n"
    "fix sketch: <1-3 sentences>\n"
)

PIPELINE_CHAIN = (
    "fingerprint → dimension reviews → adversarial verification → "
    "synthesis → Trellis reconciliation → report + ledger"
)


class AuditRepoTests(InstallTestCase):
    """Format-drift protection for the sd-audit-repo skill and charters."""

    def test_skill_pins_pipeline_report_and_ledger_contract(self) -> None:
        skill = SKILL_TEMPLATE.read_text(encoding="utf-8")
        for text in [
            "name: sd-audit-repo",
            PIPELINE_CHAIN,
            "The pipeline is fixed, mandatory, and ordered",
            # Six mandatory report sections.
            "Verdict",
            "Findings",
            "Trellis reconciliation",
            "Prioritized actions",
            "Ledger delta",
            "Coverage & limits",
            "No section is ever omitted",
            "no silent caps",
            # Scoring rubric.
            "P0 broken/exploitable now",
            "P1 will bite soon or blocks a core guarantee",
            "P2 meaningful debt/risk",
            "P3 polish",
            "S ≤ ~1h · M ≤ ~1 day · L multi-day",
            "Verified (survived refutation)",
            "Plausible (unrefuted but unverified)",
            # Arguments.
            "dimensions=<a,b,c>",
            "Unknown names are an error",
            "depth=quick|standard|deep",
            "2-of-3 refuter votes",
            "follow-up",
            # Ledger rules.
            ".trellis/audit/ledger.md",
            "assigned monotonically and are never reused",
            "becomes `regressed` under the same ID",
            "Humans may edit `notes:` lines freely",
            # Dispatch and safety.
            "Active task: <task path from task.py current>",
            "one read-only sub-agent per applicable charter",
            "Never auto-create Trellis tasks",
            "explicit user consent",
            "Findings without `file:line` evidence are downgraded or dropped",
            # Positioning.
            "`sd-review-local` (provider loop)",
            "`sd-review-pr` (PR loop)",
            "`sd-full-check` (gate)",
        ]:
            self.assertIn(text, skill)

    def test_charter_roster_matches_files_and_skeleton(self) -> None:
        skill = SKILL_TEMPLATE.read_text(encoding="utf-8")
        on_disk = sorted(p.stem for p in CHARTER_DIR.glob("*.md"))
        self.assertEqual(on_disk, sorted(CHARTER_ROSTER))
        for name in CHARTER_ROSTER:
            with self.subTest(charter=name):
                self.assertIn(name, skill)
                charter = (CHARTER_DIR / f"{name}.md").read_text(encoding="utf-8")
                self.assertTrue(
                    charter.startswith(f"# Charter: {name}\n"),
                    f"{name}.md must start with its charter heading",
                )
                for heading in CHARTER_SECTION_HEADINGS:
                    self.assertIn(heading, charter)

    def test_finding_schema_identical_across_skill_and_charters(self) -> None:
        self.assertIn(FINDING_SCHEMA, SKILL_TEMPLATE.read_text(encoding="utf-8"))
        for name in CHARTER_ROSTER:
            with self.subTest(charter=name):
                charter = (CHARTER_DIR / f"{name}.md").read_text(encoding="utf-8")
                self.assertIn(FINDING_SCHEMA, charter)
                self.assertIn("Do not assign finding IDs", charter)

    def test_conditional_charters_state_their_fingerprint_trigger(self) -> None:
        for name in CONDITIONAL_CHARTERS:
            with self.subTest(charter=name):
                charter = (CHARTER_DIR / f"{name}.md").read_text(encoding="utf-8")
                self.assertIn("fingerprint", charter)

    def test_improvements_charter_requires_cited_evidence(self) -> None:
        charter = (CHARTER_DIR / "improvements.md").read_text(encoding="utf-8")
        self.assertIn("cite", charter)

    def test_command_adapters_share_audit_contract(self) -> None:
        adapters = [
            install.ROOT / "templates/.commands/sd-audit-repo.md",
            install.ROOT / "templates/.claude/commands/sd/audit-repo.md",
            install.ROOT / "templates/.gemini/commands/sd/audit-repo.toml",
            install.ROOT / "templates/.github/prompts/sd-audit-repo.prompt.md",
        ]
        for adapter in adapters:
            with self.subTest(adapter=adapter.name):
                content = adapter.read_text(encoding="utf-8")
                for text in [
                    "Resolve the `sd-audit-repo` skill by name",
                    ".agents/skills/sd-audit-repo/charters/",
                    "fingerprint, per-dimension reviewer dispatch, adversarial "
                    "verification, synthesis, Trellis reconciliation",
                    "`dimensions=...`, `depth=quick|standard|deep`, and "
                    "`follow-up`",
                    ".trellis/audit/ledger.md",
                    "explicit user consent",
                    "mandatory final-report format",
                ]:
                    self.assertIn(text, content)

    def test_usage_guide_documents_audit_repo(self) -> None:
        guide = GUIDE_TEMPLATE.read_text(encoding="utf-8")
        for text in [
            "`.agents/skills/sd-audit-repo/SKILL.md`",
            "`.agents/skills/sd-audit-repo/charters/`",
            PIPELINE_CHAIN,
            "Verdict, Findings,\nTrellis reconciliation, Prioritized actions, "
            "Ledger delta, and\nCoverage & limits",
            "unknown names are an error, not a silent skip",
            "`depth=quick|standard|deep`",
            "`.trellis/audit/ledger.md`",
            "monotonic `A-NNN` finding IDs",
            "wait for explicit user consent",
            "periodic\nformal audit, not a per-change review loop",
            "/sd:audit-repo",
            "/sd-audit-repo",
            "`sd-audit-repo`,",
        ]:
            self.assertIn(text, guide)


if __name__ == "__main__":
    _support.unittest.main()
