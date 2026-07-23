# Add portable structured question contracts

## Goal

Use host-native structured questions at genuine decision boundaries while
keeping canonical skills portable and avoiding approval fatigue. Generate
`AskUserQuestion` guidance for capable Claude adapters, equivalent host-native
guidance where supported, and a safe concise plain-question or stop behavior
where no structured capability exists.

## Evidence

- The canonical skill/template surfaces currently contain no
  `AskUserQuestion` or portable structured-interaction contract.
- Current decision points are described ad hoc in `sd-help`, `sd-create-pr`,
  `sd-work-backlog`, `sd-audit-repo`, `sd-retro`, `sd-review-local`,
  `sd-review-pr`, `sd-update-spec`, and delegated finish-work flows.
- `.github/scripts/generate-command-surfaces.py` already performs
  platform-specific prompt rewrites, providing an appropriate adapter boundary.
- Anthropic documents `AskUserQuestion` as a host tool with short headers,
  described options, and optional multi-select:
  <https://code.claude.com/docs/en/agent-sdk/typescript> and
  <https://code.claude.com/docs/en/agent-sdk/user-input>.

## Dependencies

- This task owns the canonical interaction taxonomy, capability registry, and
  adapter-generation rules.
- `07-22-integrate-routed-review-backends` consumes it for unified review.
- `07-22-streamline-backlog-design-workflows`,
  `07-22-harden-review-learnings-boundaries`,
  `07-22-optimize-audit-charter-routing`, and
  `07-22-determinize-fleet-refresh-orchestration` consume it at their documented
  exceptional decision points.
- It does not grant additional mutation or merge authority to any consumer.
- `platypeeps/sd-github-review` is explicitly not an interactive consumer. The
  command pack resolves any user choice before constructing route intent; the
  event-driven router returns typed failure for ambiguity and never invokes
  `AskUserQuestion`.

## Requirements

- R1: Define a host-neutral canonical instruction: use the host-native
  structured-question capability when available; otherwise ask one concise
  plain-text question when interactive, or stop/park according to the owning
  skill's noninteractive policy.
- R2: Add a generated platform capability registry. Claude-capable adapters
  explicitly name `AskUserQuestion`; adapters for other hosts name only tools
  supported by that host. Unsupported tool names must not leak into neutral
  canonical content or unrelated generated surfaces.
- R3: Use a conservative common question shape: normally one question, no more
  than three in a true batch; header at most 12 characters; 2-3 mutually
  exclusive options unless multi-select is intentional; recommended option
  first; each option states consequence/trade-off; preserve a free-text escape
  where the host supports it.
- R4: Use multi-select only for independent finding/task/file selection. Group
  or paginate choices that exceed host limits instead of truncating silently.
- R5: Record decision categories in canonical metadata or shared guidance:
  ambiguous scope, higher-risk mutation, external path, blocked-run
  disposition, finding/task batch, and bounded budget extension.
- R6: Do not ask for actions already authorized by the invocation and safety
  contract: deterministic checks, ordinary low-risk in-scope fixes, bounded
  retries/polls, review-thread replies/resolution, normal backlog iterations,
  or housekeeping merge after all gates pass.
- R7: Do not use a question to override trust, exact-head, required-review,
  failed-closed, no-touch, or destructive-operation boundaries.
- R8: Define noninteractive behavior per decision category. Higher-risk or
  ambiguous mutation stops; optional nonblocking preferences use documented
  defaults only when the owning skill already authorizes that default.
- R9: Include the selected answer and resulting scope/authority in the final
  report without exposing hidden tool payloads.

## Initial Application Matrix

| Skill/workflow | Structured question use | Do not ask |
| --- | --- | --- |
| `sd-help` | One ambiguous route choice | Clearly matched commands |
| `sd-review` | Higher-risk fix, scope expansion, finding batch, round-budget extension | Normal low-risk fixes, polling, optional-router absence, thread resolution |
| `sd-create-pr` | Ambiguous file inclusion or force-push boundary if retained | Normal publish/reuse path |
| `sd-work-backlog` | Unavoidable blocker/parking or explicit run extension | Each iteration or authorized lifecycle step |
| `sd-audit-repo` / `sd-retro` | Multi-select proposed follow-up tasks | Running the requested analysis |
| `sd-review-learnings` | Exact external write target | Default scan or explicit repository-local update |
| `sd-update-spec` | Genuinely ambiguous architecture/ownership scope | Normal bounded spec refresh |
| finish-work flows | Ambiguous task-owned versus unrelated file decision | Ordinary task-scoped archive/journal work |

## Acceptance Criteria

- [ ] Claude adapters use `AskUserQuestion` at every matrix-approved boundary
  and nowhere else.
- [ ] Neutral canonical skills and non-Claude adapters contain no unsupported
  `AskUserQuestion` assumption.
- [ ] Capability-present, capability-absent interactive, and noninteractive
  fixtures produce the documented structured, plain, or stop behavior.
- [ ] Schema tests enforce header length, option count, recommendation order,
  exclusivity/multi-select semantics, consequence text, and batching limits.
- [ ] Tests prove invocation-authorized actions do not acquire redundant
  confirmation prompts.
- [ ] Questions cannot override trust, exact-head, required-review, no-touch,
  or destructive boundaries.
- [ ] Generated parity, adapter snapshots, focused workflow tests, `make sync`,
  and `make check` pass.

## Out Of Scope

- Making `AskUserQuestion` a mandatory runtime dependency for every platform.
- Replacing evidence gathering with user questions.
- Asking users to approve routine automated work already covered by a command.
- Adding compatibility aliases while skills are otherwise consolidated.
