# Design — wave-1 SD named agents

## Scope boundary

Three agent bodies plus the references that point at them. The kind, the
capability field, the renderer, and the naming rule all come from
`07-25-agent-artifact-kind`, which blocks this task. Nothing here touches
`installer/` or the generator's plumbing.

The roles already exist as prose. `sd-audit-repo/SKILL.md:158-172` already
specifies read-only reviewers, one-charter-each dispatch, refuters that receive
one finding and are told to disprove it, and "only the orchestrator writes".
This task is not inventing roles — it is converting three prose roles into
installable definitions where the platform can *enforce* what the prose asserts.
That distinction is the whole value, and measurement 1 shows it does not hold
uniformly.

## Confirmed measurements

### 1. Five platforms, five different restriction dialects — and gemini has none

Measured from the shipped Trellis agents in this checkout, which are the
working reference the parent design names:

| platform | how restriction is expressed | shape |
|---|---|---|
| claude | `tools: Read, Write, Edit, Bash, Glob, Grep` | comma-separated string, capitalized |
| codex | `sandbox_mode = "workspace-write"` plus `[features]` toggles | TOML sandbox mode + feature flags |
| opencode | `permission: {read: allow, write: allow, …}` with `mode: subagent` | per-permission allow/deny map, lowercase |
| github | `tools:` YAML sequence — `- read`, `- edit`, `- execute`, `- search` | YAML list, lowercase, own vocabulary |
| gemini | **nothing** — no `tools:` field in any of the three shipped agents | not expressible |

"Read-only" therefore renders five different ways: drop `Write, Edit` from a
string; set `sandbox_mode = "read-only"`; set `write: deny, edit: deny`; omit
`edit` and `execute` from a list; and on gemini, **write a sentence and hope**.

This lands hardest exactly where the parent design flagged risk. Parent
`design.md` §1.5: "Gemini subagents run without per-tool confirmation -> tools
scoped tightly in the gemini renderer output." Measured, the gemini dialect in
the working reference offers no scoping mechanism at all. Gemini is the one
platform with *neither* per-tool confirmation *nor* a tool restriction field.

So the Goal's premise — "ENFORCED tool restriction is the point" — is true on
claude, codex, opencode, and github, and false on gemini. AC2 anticipates this
("documented limitation where it cannot"), but the PRD does not say the
exception falls on the platform the parent design singled out. Say it plainly
rather than letting a reader assume enforcement is uniform.

`codex` is the strongest of the five and is worth copying deliberately. The
shipped agent turns off collab tools structurally:

```toml
[features]
multi_agent = false
```

with the comment that `spawn_agent` / `wait_agent` / `list_agents` /
`close_agent` "are not registered in the sub-agent's tool list at all — the
model literally cannot call them." That is the correct posture for all three SD
agents: a reviewer that can spawn reviewers breaks the orchestrator's
one-agent-per-charter accounting.

### 2. The refuter is invoked more than once per finding

R3 says "input = one finding". True, but the orchestrator's depth rules
(`SKILL.md:70-74`) invoke it in three different multiplicities:

- `standard`: one refuter, P0/P1 only.
- `exhaustive`: P0–P2, and **P0 uses 2-of-3 refuter votes**.
- `exhaustive`: correctness and security **loop until a pass** produces nothing
  new.

So the agent definition must be safe to run three times concurrently against
the same finding, and repeatedly across rounds. It must carry no run-scoped
state and must not assume it is the only refuter. Nothing in R3 says this and
an agent body written to "the" refuter voice will read as if it is.

### 3. R5's stated rationale is wrong; the real reason is stronger

R5 justifies runtime-read charters with the Copilot 30,000-char cap. Measured:
15 charters, 60,787 bytes total, largest 4,781 bytes. A single charter inlined
is ~4.8k — six times under the cap. The cap only binds if all 15 are inlined,
which nothing proposes.

The actual reason charters stay runtime-read is structural: **sd-audit-reviewer
is charter-agnostic.** One agent serves 15 charters, selected per dispatch by
the router. Inlining would mean 15 agent definitions instead of one, and the
router (`scripts/sd-ai-command-pack-audit-route.py`) would have to name agents
instead of charters. Keep R5's requirement; replace its reason.

### 4. The finding schema is fixed and ID-free by existing contract

`SKILL.md:142-155` already defines the reviewer output block:

```
[<dimension>] <title>
severity: P0-P3 · effort: S/M/L
evidence: <file:line> (+ short excerpt or command output)
why it matters: <1-2 sentences>
fix sketch: <1-3 sentences>
```

followed by "Finding IDs (`A-NNN`) are assigned by the orchestrator at
ledger-write time, never by reviewers; this prevents ID collisions across
parallel agents." R2's ID rule is therefore a restatement of an existing
invariant, not a new one — the agent body must reproduce the schema verbatim,
and any drift between the agent body and `SKILL.md` is a silent contract split.

### 5. R6 is a reference, not a rewrite

`SKILL.md:158-172` already carries the dispatch protocol, and
`07-25-fix-ci-dispatch` is adding the equivalent to sd-fix-ci. R6 asks those
sections to *mention* the named agents as an optional enhancement. The
behavior-without-them clause is already satisfied by the existing
capability-first fallback ("On inline platforms, work through the selected
charters sequentially in one context"). One sentence per skill, no restructuring.

## The central tension

The Goal promises enforcement; measurement 1 says enforcement is a per-platform
property ranging from structural (codex feature toggles) to absent (gemini).

The resolution is not to drop gemini — the agent still works there and still
carries its instructions — but to stop treating "installable, tool-restricted
definition" as one thing. Two separable properties:

- **Identity**: the agent exists, is named `sd-*`, is dispatchable, and carries
  a fixed role prompt. True on all wave-1 platforms.
- **Enforcement**: the host mechanically prevents the disallowed tool call.
  True on claude, codex, opencode, github. False on gemini.

Ship both, claim only what each platform delivers, and put the split in the
install/status output rather than in a design doc nobody reads at runtime.

## Contract

**sd-audit-reviewer** — input: one charter path + the fingerprint scope brief,
verbatim, nothing else (`SKILL.md:166-168`: reviewers do not read other charters
and do not re-derive the inventory). Output: zero or more findings in the
`SKILL.md:142-149` schema, no IDs. Read-only. No sub-agent spawning.

**sd-audit-refuter** — input: one finding. Output: refute/uphold with evidence.
Prompted to refute by default; default to refuted when uncertain. Read-only,
stateless, safe to run 3× concurrently on one finding and across repeated
rounds (measurement 2).

**sd-ci-triager** — input: run id + job id + job name, that job's `--log-failed`
output, and the run-level change context resolved by the parent. Output: exactly
one of `real-code | flake | infra | stale-baseline`, evidence quotes, and a
proposed fix or rerun disposition. Read-only: no writes, **no `gh run rerun`**,
no pushes. That contract is owned by `07-25-fix-ci-dispatch`; this task copies
it and must not re-derive it.

**All three** — `sd-` prefixed; dispatch prompts open with
`Active task: <path from task.py current>` when a Trellis task is active (R7,
matching `SKILL.md:163-165`); the command's already-resolved
`checkout-trust: <state> (<reason-code>)` is restated and never recomputed by
the worker.

## Compatibility

R6's "without requiring them" is what makes this task independently shippable:
on a platform with no agent rows, or a host that does not resolve `sd-*` agents,
both skills fall back to built-in sub-agents or the inline path, which is
today's behavior.

The three agent bodies duplicate contracts that live in skill bodies — the
finding schema (`SKILL.md:142-149`), the ID rule (`:154`), and the sd-fix-ci
classification vocabulary. Duplication is unavoidable (the agent body *is* the
system prompt) but it is now a two-copy contract. A drift test that compares the
schema block in the agent body against the skill body is cheap and is the only
thing preventing a silent split.

## Rollout and rollback

Three commits, one agent each, in dependency order:

1. **sd-audit-refuter** first. Smallest contract, single input, no charter
   wiring, and it is the agent whose invocation pattern is most constrained
   (measurement 2) — getting statelessness right here sets the house shape.
2. **sd-audit-reviewer** second. Adds charter path wiring and the finding
   schema duplication.
3. **sd-ci-triager** third, and only after `07-25-fix-ci-dispatch` is reviewed,
   since it consumes that task's result contract verbatim.

Then one commit for the R6 reference sentences in both skill bodies.

Rollback of any agent commit removes its rows on the next removal pass and both
skills fall back to their capability-first inline paths. The R6 sentences are
the only thing that could dangle — revert them together with the agent they
name, or a skill body references an agent that no longer installs.

## Risk

1. **Claiming uniform enforcement.** Gemini renders an agent whose read-only
   posture is prose only, and it is also the platform that runs subagents
   without per-tool confirmation. A `sd-audit-reviewer` that writes files on
   gemini violates "only the orchestrator writes" (`SKILL.md:171`) with nothing
   to stop it. This must be in install/status output, not just in AC2.
2. **A refuter body written as a singleton.** 2-of-3 voting and
   loop-until-clean invoke it concurrently and repeatedly; any run-scoped
   assumption produces correlated votes, which defeats the point of voting.
3. **Finding-schema drift** between the agent body and `SKILL.md:142-149`.
   Two copies, no test, and the ledger is downstream of both.
4. **An agent that can spawn agents.** Breaks one-agent-per-charter accounting
   and the refuter vote count. Codex shows the structural fix; the other
   dialects need it stated explicitly.
5. **Copying the sd-fix-ci contract before it is reviewed.** The triager's
   entire output shape is owned by `07-25-fix-ci-dispatch`.
6. **Inlining charters** to dodge runtime path resolution. Turns one
   charter-agnostic agent into 15 and forces the router to name agents.
