# Design: SD commands as cross-platform sub-agents

Status: ACCEPTED (user, 2026-07-25). Section 1 is binding for all child tasks. Section 2's
open work is distributed to the child tasks listed in `prd.md` (Task map); each child
completes its own detailed design before its `task.py start`.

## 1. Settled design inputs (cross-platform strategy - binding)

Source: `research/cross-platform-agent-support.md` (do not re-litigate without new
evidence). SE twin: se-ai-command-pack `.trellis/tasks/07-25-agent-artifacts/`.

1. One canonical agent source format: neutral Markdown + YAML frontmatter, body = system
   prompt, authored under `templates/`. Trellis's `.trellis/agents/` -> five-platform
   fan-out in this checkout is the working reference.
2. Capability gating via the registry, mirroring `structured_question_tool`:
   - New `PlatformInfo` field (e.g. `subagent_support`) with values for: native-file
     (claude, gemini, github, opencode, cursor, kiro, droid, codebuddy, antigravity),
     native-file-toml (codex), none (devin, trae, qoder, zcode, pi, reasonix, shared).
   - Only native-file platforms get agent manifest rows; renderer picks MD dialect, TOML
     (codex), or JSON (kiro) per platform.
3. Manifest/installer delta: fifth kind `agent`; rows carry the same provenance, removal,
   and drift semantics as existing kinds; gitignore-tuple invariants extended.
4. Dispatch protocol in command bodies stays capability-first prose (the sd-audit-repo
   pattern is the house template); generator may inject platform-specific dispatch notes
   via the existing bounded insertion mechanisms (`CLAUDE_COMMAND_BODY_INSERTIONS` shape,
   generalized per capability rather than per platform name where possible).
5. Trust and safety constraints:
   - Sub-agents inherit checkout-trust preflight classification; dispatch prompts restate it.
   - Gemini subagents run without per-tool confirmation -> tools scoped tightly in the
     gemini renderer output.
   - Codex project-scope agents load only in trusted projects -> installer/status output
     documents this.
   - Class-2 platforms (no hook injection): dispatch prompts open with explicit context
     (Trellis `Active task:` convention).
6. Known wrinkles with binding disposition:
   - Cursor auto-loads `.claude/agents/` and `.codex/agents/`: agent names must be
     collision-safe (`sd-` prefix) and the design must decide whether cursor gets its own
     rows or relies on cross-reading (record the decision).
   - Copilot `.agent.md` body cap 30,000 chars: charters are runtime-read references,
     never inlined into agent bodies.
7. First named agents (enforced restriction is the point): sd-audit-reviewer and
   sd-audit-refuter (read-only; per-charter payloads), sd-ci-triager (read logs, no push).
   Deliberate serializations in sd-update-deps merges, sd-work-backlog, sd-housekeeping
   are out of scope for parallelization.

## 2. Open design work (distributed to child tasks - see prd.md Task map)

- Wave-1 platform set (claude+codex pilot vs all ~10 supporters) and renderer table.
- Exact frontmatter dialect mapping per platform (tools vocab, model names, permission maps).
- How agent rows interact with `sd-check`'s typed contract and `--audit` inspection.
- Charter-to-agent payload wiring for sd-audit-repo (runtime read paths).
- sd-fix-ci per-job dispatch design (log isolation contract, result schema back to parent).
- Test plan: registry invariants, generator byte-stability, installer round-trip, removal.
- Rollout/rollback: version bump, changelog, fleet-refresh implications, retirement path.
