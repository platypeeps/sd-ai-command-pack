# Design — per-job dispatch protocol for sd-fix-ci

## Scope boundary

Prose only. No script changes, no registry changes, no new manifest kind — that
is Tier 2 (`07-25-agent-artifact-kind`). This task adds a dispatch section to an
existing command's authored body and regenerates the fan-out.

It is the pilot: `07-25-dispatch-rollout` R1 inherits whatever pattern lands
here, and `07-25-worker-agents` turns this protocol's worker into a named
`sd-ci-triager` agent. Getting the shape wrong here propagates to four commands
and one agent definition.

## Where the section goes, and why the PRD's "canonical body" is ambiguous

There are **two** hand-authored bodies per command:

| layer | file | size | contains |
|---|---|---|---|
| command source | `.github/command-sources/sd-fix-ci.md` | 16 lines | routing to the skill, safety headline, report contract |
| skill body | `templates/.agents/skills/sd-fix-ci/SKILL.md` | 157 lines | the actual workflow |

Everything else is generated: `.github/scripts/generate-command-surfaces.py`
writes `templates/.commands/<name>.md` and the per-platform adapters
(`.claude/commands/sd/fix-ci.md`, `.gemini/commands/sd/fix-ci.toml`,
`.opencode/commands/sd-fix-ci.md`, `.github/prompts/sd-fix-ci.prompt.md`, …).

The reference implementation puts its dispatch protocol in the **skill body** —
`templates/.agents/skills/sd-audit-repo/SKILL.md:156` opens `## Dispatch
protocol`. Match that. The 16-line command source stays 16 lines.

## The correction R3 needs: the house template does not restate trust

R1 names the sd-audit-repo protocol as the house template. R3 asks for the
checkout-trust classification to be "restated in every dispatch prompt".
Measured, those two requirements point in different directions:

- `templates/.agents/skills/sd-audit-repo/SKILL.md` contains **zero**
  occurrences of "trust", "untrusted", or "indeterminate". Its dispatch
  protocol restates the *Active task prefix*, not trust.
- The checkout-trust block is **generator-injected**, not authored.
  `.github/scripts/generate-command-surfaces.py:179-184` defines
  `CHECKOUT_TRUST_POLICY_MARKER` and the policy prose; the generator emits it
  into command adapters based on `CommandInfo.executes_checkout_code` /
  `trusted_static_only` (`installer/registry.py:726`, `:728`). That is why the
  block appears at `.claude/commands/sd/fix-ci.md:27` but nowhere in
  `.github/command-sources/sd-fix-ci.md`.

So implementing R3 literally — writing trust-classification prose into
`SKILL.md` — makes sd-fix-ci the first skill body to carry trust language, and
diverges from the very template R1 names.

**Design position:** the skill does not re-derive trust. The dispatch protocol
carries forward the state the *command layer already resolved*, in one line, in
the same shape audit-repo uses for the Active-task prefix:

> Every dispatch prompt restates the command's resolved
> `checkout-trust: <state> (<reason-code>)` before the role-specific
> instructions. Workers do not reclassify; a worker result cannot change the
> state or unlock a gate the command closed.

That satisfies R3's intent (the worker cannot be tricked into acting outside
the resolved trust state) without duplicating a generator-owned classifier into
a hand-authored file. It is also the line `07-25-dispatch-rollout` will copy
three more times, so it should be one sentence, not a section.

## The dispatch unit is already in the workflow

`SKILL.md:75` — "Classify every failing job before acting on any of them, so
the report reflects the whole run." Step 3 is a pure classification pass over
independent jobs with no cross-job writes. That is the parallel unit; no
restructuring of the workflow is needed to expose it.

Step 4 (act on each class) is **not** parallelizable and must stay with the
parent: it pushes commits, opens PRs via `sd-create-pr`, and spends a shared
rerun budget (`max-reruns=N`, default 1, `SKILL.md:113`). A budget shared across
parallel workers is a race. R2's "workers are read-only; fixes are applied by
the parent" is exactly right and is the load-bearing constraint.

### Run-level facts the parent must resolve once

Two of the four classes need evidence that is identical for every job:

- `stale-baseline` — "the branch is behind the default branch" (`SKILL.md:87`).
  A property of the run, not the job.
- the PR-head/local-HEAD mismatch note (`SKILL.md:68-70`), which the report
  must carry.

If each worker re-derives these, they each spend `gh`/`git` calls and can
disagree with each other inside one report. The parent resolves them once and
passes them in the shared change context R2 already specifies as worker input.

Per-job evidence stays per-job: "the same job passing on the same commit
earlier" (`SKILL.md:81-83`) is scoped to one job's history and belongs to the
worker.

## The log-fetch mechanism decides whether the goal is met

The PRD's goal is "the parent context stops absorbing every job's full log
output". The current workflow fetches logs with
`gh run view <run-id> --log-failed` (`SKILL.md:73`) — **one call returning every
failing job's log**. If the parent runs that and then splits the blob per
worker, it has already absorbed everything and the task delivers nothing.

The mechanism that actually delivers the goal is per-job fetch. `gh` supports
it: `-j, --job string  View a specific job ID from a run` combined with
`--log-failed` ("View the log for any failed steps in a run or specific job").
So the parent enumerates jobs with `gh run view <run-id>` (job identities only,
cheap) and passes each worker its **job id**; the worker fetches its own log.

Two costs to state rather than discover:

- `gh`'s own help warns that when it cannot associate jobs with logs from the
  zip, it falls back to per-job API fetches which are "slower and more
  resource-intensive", and that the operation fails outright if more than 25
  job logs are missing. Per-job fetching walks into that path deliberately. On
  a wide matrix this is more API calls, not fewer.
- Every `gh` call must go through
  `bash scripts/sd-ai-command-pack-toolchain.sh run -- gh …` (`SKILL.md:27-33`).
  N parallel workers means N toolchain cache setups. That is a known cost, not
  a defect, but it is worth measuring in the pilot because
  `07-25-dispatch-rollout` multiplies it by three commands.

Bound the fan-out. `max-reruns=N` exists but there is no cap on failing jobs; a
red matrix build can present a dozen. Either reuse an existing bound or state
that the parent classifies in batches — but decide it here, because
`sd-test-gaps` in the rollout task has `max-gaps` and `sd-fleet-refresh` has
waves, and this is the one command with no natural bound.

## Contract

Worker input (R2), all supplied by the parent:

- job identity: run id + job id + job name
- resolved `checkout-trust: <state> (<reason-code>)`
- run-level change context: base/head, behind-default-branch status,
  PR-head/local-HEAD match
- `Active task: <path>` prefix when a Trellis task is active — the audit-repo
  convention (`SKILL.md:163-165`) and the sub-agent dispatch protocol in the
  workflow guide

Worker output:

- exactly one class from `real-code | flake | infra | stale-baseline`
- evidence quotes — log lines, not summaries; `SKILL.md:94` requires concrete
  flake evidence
- a suggested fix or rerun disposition, **as a proposal**

Worker is read-only: no writes, no `gh run rerun`, no pushes.

Parent owns: job enumeration, result assembly, the `real-code`/`flake` tiebreak
(`SKILL.md:91-93` — prefer `real-code` and reproduce locally), all of step 4,
the rerun budget, and the final report.

## Compatibility

The report contract is unchanged (R4). `SKILL.md:150-152` specifies one bullet
per failing job in the shape
`<job> · <real-code|flake|infra|stale-baseline> · <evidence one-liner>`.
Dispatch changes how those bullets are produced, not what they look like — that
is the property the pilot proves and the rollout inherits.

R5 (inline platforms unchanged) is what makes this safe to ship without the
Tier 2 work: on a platform with no sub-agents, the fallback prose collapses to
today's sequential loop and the outcome is identical.

## Rollout and rollback

One commit: `SKILL.md` edit, `make generate`, catalog regeneration, changelog +
version bump. Reverts cleanly — the section is additive prose and removing it
restores the sequential path that never stopped working.

The real rollout risk is not this commit; it is that `07-25-dispatch-rollout`
copies the pattern before this one is reviewed. That ordering is already stated
in both PRDs and must hold.

## Risk

1. **Delivering the section without the per-job log fetch.** The dispatch prose
   reads correct, the parent still runs `--log-failed` over the whole run, and
   the stated goal is silently not met. Nothing in the acceptance criteria
   catches it.
2. **Trust language duplicated into the skill body.** Creates a second,
   hand-maintained copy of a generator-owned classification that will drift
   from `generate-command-surfaces.py`.
3. **Unbounded fan-out.** No cap on failing jobs; a wide red matrix dispatches
   as many workers as there are red legs, each with its own toolchain cache
   setup and `gh` API cost.
4. **Rerun budget leaking into workers.** `max-reruns` is a shared counter.
   Any worker able to rerun makes the bound unenforceable.
