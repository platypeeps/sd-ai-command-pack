# Author wave-1 SD named agents

Parent: `.trellis/tasks/07-25-agent-artifacts` (Tier 2 content). Settled inputs: parent
`design.md` section 1 and `research/cross-platform-agent-support.md`.

## Goal

Ship the first named SD agents where ENFORCED tool restriction is the point:
sd-audit-reviewer and sd-audit-refuter (read-only, wired to the 15 audit charters) and
sd-ci-triager (reads CI logs, cannot push or write) — replacing prose-only role
descriptions with installable, tool-restricted definitions on supporting platforms.

## Requirements

- R1: Canonical agents authored as neutral MD + frontmatter under the format established
  by 07-25-agent-artifact-kind; collision-safe `sd-` names.
- R2: sd-audit-reviewer: input = one charter + scope brief; read-only toolset; output =
  findings in the ledger schema WITHOUT IDs (orchestrator assigns IDs — preserves the
  existing sd-audit-repo collision rule).
- R3: sd-audit-refuter: input = one finding; read-only; output = refute/uphold verdict
  with evidence; prompted to refute by default.
- R4: sd-ci-triager: input = one failing job + logs; tools limited to read/log
  inspection; output = the classification contract from 07-25-fix-ci-dispatch.
- R5: Charters are referenced as runtime-read paths, never inlined (Copilot 30k cap).
- R6: sd-audit-repo and sd-fix-ci dispatch sections reference the named agents as an
  optional enhancement; behavior without them (built-in sub-agents or inline) unchanged.
- R7: Dispatch prompts open with explicit context (class-2 platforms have no hook
  injection); trust classification restated per parent design.

## Acceptance Criteria

- [ ] Three agents render and install on the wave-1 platform set; capability-`none`
      platforms unaffected.
- [ ] Tool restriction verified per platform dialect (read-only where the dialect can
      express it; documented limitation where it cannot).
- [ ] sd-audit-repo/sd-fix-ci reference the agents without requiring them.
- [ ] Version bump + changelog; catalog and docs updated.

## Dependencies / order

- BLOCKED by 07-25-agent-artifact-kind (plumbing). Aligns with 07-25-fix-ci-dispatch
  (shared triage contract).

## Notes

- Complex task: needs `design.md` + `implement.md` before start.
