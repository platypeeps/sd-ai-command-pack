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

- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **The Goal's premise — "ENFORCED tool restriction is the point" — holds on some wave-1
  platforms and not others.** Measured 2026-07-28 from the shipped Trellis agents, which
  are the parent design's named working reference:

  | platform | restriction expression |
  |---|---|
  | claude | `tools: Read, Write, Edit, Bash, Glob, Grep` (comma string) |
  | codex | `sandbox_mode = "workspace-write"` + `[features]` toggles |
  | opencode | `permission: {read: allow, write: allow, …}` map |
  | github | `tools:` YAML sequence (`- read`, `- edit`, `- execute`, `- search`) |
  | gemini | **no `tools:` field in any of the three shipped agents** |

  Read-only renders five different ways, and on gemini it cannot be rendered at all — the
  same platform parent `design.md` §1.5 flags as running subagents *without per-tool
  confirmation*. AC2's "documented limitation where it cannot" is therefore the headline
  for one of three wave-1 platforms, not a footnote. Split the claim: **identity** (agent
  exists, named, dispatchable) holds everywhere; **enforcement** holds on
  claude/codex/opencode/github and not on gemini. Put the split in install/status output.
- **R3 understates the refuter's invocation pattern.** `sd-audit-repo/SKILL.md:70-74`:
  `standard` runs one refuter over P0/P1; `exhaustive` covers P0–P2, uses **2-of-3 refuter
  votes for P0**, and **loops correctness and security until a pass finds nothing new**. The
  agent must be stateless and safe to run three times concurrently on one finding; a body
  written as "the" refuter produces correlated votes, which defeats voting.
- **R5's rationale is wrong; keep the requirement, replace the reason.** Measured: 15
  charters, 60,787 bytes total, largest 4,781 bytes — a single charter is six times under
  Copilot's 30,000-char cap, so the cap does not justify runtime-read for one charter. The
  real reason is that sd-audit-reviewer is **charter-agnostic**: one definition serves all
  15, selected per dispatch by `scripts/sd-ai-command-pack-audit-route.py`. Inlining means
  15 agent definitions and a router that names agents instead of charters.
- **R2's ID rule already exists.** `SKILL.md:154`: "Finding IDs (`A-NNN`) are assigned by
  the orchestrator at ledger-write time, never by reviewers." Likewise the finding schema
  (`SKILL.md:142-149`) and "only the orchestrator writes" (`:171`). The agent bodies
  reproduce these verbatim, which makes them a **two-copy contract** — add a drift test
  comparing the schema block in the agent body against the skill body.
- **No agent may spawn sub-agents.** A reviewer that spawns reviewers breaks
  one-agent-per-charter accounting; a refuter that spawns refuters corrupts the 2-of-3
  vote. Codex already does this structurally in this checkout (`[features] multi_agent =
  false`, with the shipped comment that the spawn tools "are not registered in the
  sub-agent's tool list at all").
- **R6 is a reference, not a rewrite.** `SKILL.md:158-172` already carries the dispatch
  protocol including the capability-first inline fallback, so "behavior without them
  unchanged" needs one sentence per skill and no restructuring.
- Commit order is **sd-audit-refuter → sd-audit-reviewer → sd-ci-triager → R6 sentences**,
  not the listing order: smallest contract first, and the triager waits on
  `07-25-fix-ci-dispatch` being reviewed since it copies that task's result contract.

## Rescope (2026-08-08)

Park note corrected: the original blocker task is archived; this remains
parked by choice, not by dependency. Revisit after 08-08-parallel-work-backlog
ships, which covers the concurrency need this task anticipated.
