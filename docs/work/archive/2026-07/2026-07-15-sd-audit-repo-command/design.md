# Design: sd-audit-repo

## Component layout

New shipped sources (templates/** is the payload source of truth):

```
templates/.agents/skills/sd-audit-repo/SKILL.md          # orchestrator
templates/.agents/skills/sd-audit-repo/charters/
  architecture.md  design.md  correctness.md  security.md  testing.md
  documentation.md bloat.md   performance.md  dependencies.md tooling.md
  release-hygiene.md improvements.md
  consumer-impact.md observability.md accessibility-i18n.md   # conditional
templates/.commands/sd-audit-repo.md                     # neutral command body
templates/.claude/commands/sd/audit-repo.md              # bespoke Claude adapter
templates/.gemini/commands/sd/audit-repo.toml            # bespoke Gemini adapter
templates/.github/prompts/sd-audit-repo.prompt.md        # bespoke Copilot prompt
```

Manifest wiring mirrors sd-work-designs (~25 entries): SKILL.md fans to the 11
skill targets; the neutral command fans to the 11 platform command/workflow/
prompt targets; the 3 bespoke adapters map 1:1. Charters are shared/always
entries targeting only `.agents/skills/sd-audit-repo/charters/` (single copy,
15 entries) — every platform SKILL.md copy references that canonical repo path,
so no per-platform charter fan-out. Verify during implementation that the
shared platform is installed unconditionally (housekeeping SKILL entry shows
`platform: shared, install: always`); if a platform class exists that skips
shared, fall back to full charter fan-out.

## Orchestrator SKILL.md contract

Sections (mandatory, in order): When to use · Arguments · Pipeline ·
Scoring rubric · Dispatch protocol · Report format · Ledger rules ·
Safety rules · Final report.

### Arguments

- `dimensions=<a,b,c>` — run only the named charters (names = charter file
  stems). Unknown names are an error, not a silent skip.
- `depth=quick|standard|deep` (default standard):
  - quick: no verification stage; each reviewer capped to its top findings.
  - standard: adversarial verification of P0/P1 findings, single refuter.
  - deep: verification of P0–P2; P0 uses 2-of-3 refuter votes; correctness
    and security charters loop until a pass adds nothing new.
- `follow-up` — skip the full sweep: re-verify each open ledger item against
  the current tree (fixed / still-open / regressed) plus a quick regression
  sweep of areas touched since `last-seen` commits.

### Pipeline (fixed order)

1. **Fingerprint** — one inventory pass: languages, size, entry points, build/
   CI setup, test layout, docs map, downstream-consumer signals (manifest,
   published artifacts, dependent-repo references). Selects applicable
   conditional charters and records the selection rationale. Loads
   `.trellis/audit/ledger.md` if present. Output: a scope brief given
   verbatim to every reviewer (repo map + open-ledger summary), so reviewers
   neither re-derive the map nor re-report known-open items as new.
2. **Dimension reviews** — one read-only sub-agent per applicable charter,
   in parallel where the platform supports it. Input: charter + scope brief.
   Output: structured findings per the charter output schema.
3. **Adversarial verification** — per depth rules, independent refuter agents
   receive one finding each with the instruction to disprove it. Refuted →
   dropped and logged in Coverage & limits; survived → confidence=Verified;
   unverified severities keep confidence=Plausible.
4. **Synthesis** — dedupe cross-dimension overlaps (same file/line/root
   cause), merge related findings, rank by severity then effort.
5. **Trellis reconciliation** — read `task.py list` + task prd files;
   classify each finding tracked-accurate / tracked-stale / untracked; draft
   prd-ready task proposals (title, slug, summary, acceptance sketch) for
   untracked P0–P2. Proposals require explicit user consent before creation.
6. **Report + ledger** — emit the canonical report; update the ledger
   (assign IDs to new findings, update last-seen on still-open, mark fixed
   items resolved, flag regressions).

### Scoring rubric (fixed definitions)

- Severity: P0 broken/exploitable now · P1 will bite soon or blocks a core
  guarantee · P2 meaningful debt/risk · P3 polish.
- Effort: S ≤ ~1h · M ≤ ~1 day · L multi-day.
- Confidence: Verified (survived refutation) · Plausible (unrefuted but
  unverified).

### Finding schema (charter output contract)

```
[<dimension>] <title>
severity: P0-P3 · effort: S/M/L
evidence: <file:line> (+ short excerpt or command output)
why it matters: <1-2 sentences>
fix sketch: <1-3 sentences>
```

IDs (`A-NNN`) are assigned by the orchestrator at ledger-write time, never by
reviewers — prevents collisions across parallel agents.

### Report format (mandatory sections)

```
# Repo Audit — <repo> @ <short-sha> — <date>
Mode: full|follow-up · Depth: … · Dimensions: …

## Verdict            <one-paragraph assessment + counts by severity>
## Findings           <grouped by dimension; each finding in schema above + ID>
## Trellis reconciliation  <tracked-accurate / tracked-stale / untracked+proposals>
## Prioritized actions <numbered, severity-then-effort order>
## Ledger delta       <new N · still-open N · fixed N · regressed N>
## Coverage & limits  <dimensions skipped + why, verification caps, refuted-finding log>
```

No section is ever omitted (housekeeping precedent); empty sections state
their emptiness explicitly.

### Ledger format — `.trellis/audit/ledger.md` (committed)

```
# Audit ledger
<one preamble line: purpose + "managed by sd-audit-repo">

## A-013 — <title>
status: open|fixed|regressed  severity: P1  effort: M  confidence: Verified
dimension: security
first-seen: 2026-07-15 @ abc1234   last-seen: 2026-07-20 @ def5678
evidence: path/to/file.py:88
notes: <optional, human-editable>
```

Rules: IDs monotonic and never reused; `fixed` entries are kept (history),
not deleted; a `fixed` finding that reappears becomes `regressed` under the
same ID; humans may edit `notes:` freely — the skill preserves unknown lines
within an entry.

## Charter template (common skeleton for all 15)

```
# Charter: <dimension>
Mission        <one paragraph>
Scope          <what to examine — concrete artifact types and questions>
Out of scope   <what belongs to sibling charters — dedupe by construction>
Method         <suggested probes: commands, file patterns, heuristics>
Severity guide <P0-P3 calibration examples specific to this dimension>
Output         <the finding schema, restated>
```

`improvements.md` additionally requires every suggestion to cite the concrete
observed gap that motivates it (evidence discipline for the least
evidence-bound charter).

## Dispatch & platform degradation

Reuse the pack's existing platform-class language: sub-agent dispatch
platforms fan out one read-only research-type agent per charter in parallel;
inline platforms iterate charters sequentially in one context and are advised
to prefer `depth=quick` or a dimension filter. All dispatches follow the
sub-agent protocol (Active task prefix when a Trellis task is active).
Reviewers are read-only; only the orchestrator writes (report display +
ledger file).

## Tradeoffs decided

- One orchestrator skill + charters, not N skills: 12 separate commands would
  cost ~150 extra manifest entries and fragment UX; dimension filter covers
  the "just security" case.
- Committed ledger: cross-session/-developer follow-up beats occasional PR
  churn; journals set the precedent for committed workflow artifacts.
- Charters single-copy under shared `.agents/`: 15 entries instead of 165;
  acceptable coupling since shared installs always.
- `improvements` stays a charter (dedicated forward-looking pass) with an
  evidence-citation requirement to control speculation.

## Compatibility, rollout, rollback

Purely additive: no existing command, script, or adapter changes semantics.
Consumers receive it on their next fleet refresh. Rollback = revert the PR;
ledgers already written into consumer repos are inert markdown. Version bump
0.10.5 → 0.11.0 (new feature, minor bump — matches 0.7.0/0.8.0 precedent for
new commands).

## Testing design

- Registry/parity: extend the command-registry-derived tests so
  sd-audit-repo's neutral fan-out is covered like existing commands; add
  charter-file parity (template ↔ installed) — first multi-file skill, so the
  parity helper may need to iterate a directory rather than a single file.
- Format-drift tests (test_audit_repo.py, mirroring test_housekeeping.py):
  assert mandatory report section names, rubric strings, ledger path, charter
  roster names, and argument names in SKILL.md; assert the usage-guide section
  stays in sync.
- Charter completeness test: every roster name in SKILL.md has a charter file
  and every charter file contains the template's section headings.
- install-audit: expected-target count grows; no test weakening.
