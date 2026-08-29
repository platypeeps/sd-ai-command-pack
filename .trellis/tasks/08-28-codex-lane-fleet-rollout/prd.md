# Roll the local codex review lane out to every fleet consumer

## Goal

Give each of the nine registered fleet consumers a `.sd-ai-command-pack/review.json`
that enables the local `codex` provider and configures the policy fields the
remote gate needs, so a routine review is answered by the subscription-billed
local lane and only escalates to the routed GitHub backend when the local stage
does not terminate.

This task is the deployment half. The upstream half — making `codex` a
first-class configured provider in the pack itself — is
`08-07-default-local-review-lanes`.

## Background

`docs/fleet/consumers.json` registers nine consumers. Eight of them have no
`.sd-ai-command-pack/review.json` at all:

```text
rwbp-coordinator:       review.json ABSENT
loadsmith:              review.json ABSENT
hoa-manager:            review.json ABSENT
rwbp-website:           review.json ABSENT
mezmo_benchmark:        review.json ABSENT
se-ai-command-pack:     review.json ABSENT
people-profiles:        review.json ABSENT
anomaly-metric-creator: review.json ABSENT
sd-github-review:       codex enabled, remoteIntegration.requirement optional
```

The file is not gitignored in the eight — `git ls-files` in each lists the
sibling `.sd-ai-command-pack/manifest.json` and `installed-targets.txt` as
tracked, with no `review.json` entry.

A repository with no config falls back to `_default_config()` in
`templates/scripts/sd-ai-command-pack-review-local.py`, which ships `codex`
deliberately disabled:

```python
"id": "codex",
# Opt-in: codex is an external, subscription-billed tool, and a
# substantive review selects it as a lane rather than a fallback.
"enabled": False,
```

So the local codex lane is live in exactly one consumer today, and the other
eight route every review to the remote backend.

The installer does not ship the file. The only `review.json` anywhere in the
pack source is the pack's own `.sd-ai-command-pack/review.json`, and
`grep -rn "review\.json" installer/` returns no hits. Each consumer's copy is
hand-authored, which is what the standing `sd-status fleet` provider-config
advisory has been reporting.

## Constraints

### The advisory ceiling is a separate policy decision, not a prerequisite

Enabling `codex` is sufficient on its own for the case this rollout is for. A
clean codex run leaves zero outstanding findings, and `_remote_gate` returns
`eligible` with reason `local-stage-terminal` without consulting any ceiling.
`_default_config()` omits `policy.localAdvisorySeverityCeiling`, and that
omission does not stand in the way.

The ceiling governs a different case: what happens when the local lane *does*
find something. Without it, every outstanding finding blocks the gate at any
severity and the review escalates to the routed backend. With it set to
`medium`, findings at or below that severity are released as advisory and no
longer force a round — they are still reported, but they no longer route.

That is a real loosening of the gate, so it is a per-consumer policy decision
this task must make deliberately rather than a box to tick everywhere.
Mandating `medium` fleet-wide would let medium-severity local findings bypass
routed review in nine repositories at once, which is a larger change than
turning the codex lane on and should not ride along with it unexamined.
`sd-github-review` sets `"medium"`; that is one repository's decision, not a
fleet default.

### Codex cannot be a repository's only substantive lane

The `codex` provider maps both exit 1 and exit 2 to `unavailable`:

```json
"outcomeByExitCode": { "0": "clean", "1": "unavailable", "2": "unavailable" }
```

`unavailable` is a member of `TERMINAL_FAILURES`, so a codex invocation that
does not exit cleanly marks the run degraded and `_remote_gate` returns
`eligible-with-limitations`, which the `sd-review` skill rejects for a routed
skip.

A second lane does **not** rescue that. `_blocking_limitations` collects every
limitation whose status is in `TERMINAL_FAILURES` regardless of how many other
providers completed, and `degraded` is set from that list, so a failed codex
degrades the gate whether or not `gito` ran beside it. Configuring an extra
provider to make a codex failure locally terminal would not work, and this task
must not be planned as though it did.

What a second lane does buy is the outcome rather than the gate:
`_aggregate_outcome` decides from the lanes that were in a position to answer,
so when codex dies the surviving lane still reports what it found instead of
the review reporting nothing. That is a real benefit and a real cost, and it is
a per-consumer judgement, not a precondition.

The consequence for this rollout is narrower than a second-lane requirement: a
codex-only consumer skips routing when codex exits cleanly and routes remotely
when it does not — which is the same remote path that consumer uses today, so
the failure mode is no worse than the status quo.

The two existing precedents are the pack itself (`codex` + `gito`) and
`sd-github-review` (`codex` + `prism-chunked` + `gito`). The latter's
`prism-chunked` entry is an `argv` adapter pointing at a review script that
lives only in the `sd-github-review` checkout, so that provider set is not
portable to the other consumers as-is.

### A codex-only set would regress `scope=codebase`

The second-lane question has a real answer, but it is about scope coverage
rather than failure rescue. The built-in `codex` provider declares
`"scopes": ["worktree", "branch_delta"]` and does not cover `codebase`. The
default configuration these eight consumers fall back to today enables `prism`
and `gito`, both carrying the shared `["worktree", "branch_delta", "codebase"]`
scope list.

So writing a codex-only `review.json` into a consumer takes away a review mode
it currently has: with no enabled provider covering the requested scope,
planning raises `no eligible local review provider satisfies the selected
policy` and `sd-review scope=codebase` stops working in that repository.

Each consumer therefore needs at least one enabled codebase-capable provider
alongside `codex` — or an explicit, recorded decision that the repository is
giving up `scope=codebase`. This is a different requirement from the one the
failure-behaviour section rules out, and both hold at once: a second lane does
not make a codex failure locally terminal, and a second lane is still needed to
keep `codebase` reviewable.

### The file this task adds is inside the fleet's gito exclusion

All eight target consumers blanket-exclude the directory this task writes into:

```text
rwbp-coordinator  .gito/config.toml:41:  ".sd-ai-command-pack/**",
loadsmith         .gito/config.toml:41:  ".sd-ai-command-pack/**",
rwbp-website      .gito/config.toml:41:  ".sd-ai-command-pack/**",
people-profiles   .gito/config.toml:41:  ".sd-ai-command-pack/**",
```

`sd-github-review` is the exception: it replaced the blanket pattern with named
carve-outs (`bin/**`, `installed-targets.txt`, `manifest.json`) that leave
`review.json` reviewable.

Two consequences, and they pull in opposite directions:

- The pull request that lands `review.json` in a blanket-excluding consumer
  presents `gito` with a diff that is entirely excluded. That is the empty-scope
  shape `08-06-local-provider-empty-scope` describes, on the very change this
  task ships.
- After the rollout, `review.json` is repo-owned configuration that a reviewer
  should see, and the blanket pattern hides every future edit to it.

So this task has an ordering dependency on `08-28-gito-blanket-exclusion-fleet`,
which narrows the blanket pattern to named carve-outs fleet-wide. Either that
task lands first in a given consumer, or this task narrows that consumer's
pattern as part of the same change. Landing `review.json` under an unchanged
blanket exclusion is the one sequence to avoid: it is both unreviewable on
arrival and invisible thereafter.

### Routed review stays reachable

`remoteIntegration.requirement` validates against `{"optional", "required"}`
only — there is no value that disables routing. Routed dispatch is skipped
because the local stage produced an eligible gate, not because routing was
turned off. All nine consumers already carry an identical
`config/routed-review-setup-v1.json`; this task does not change it. The
`.gito/config.toml` each also carries is a different matter — see below.

### Prerequisites already met

The Codex CLI is present on the operator machine (`/opt/homebrew/bin/codex`,
`codex-cli 0.150.1`). Codex availability on other machines is out of scope; a
machine without it degrades to the same routed path these consumers use today.

## Requirements

1. Decide the provider set each consumer gets and record the decision per
   consumer rather than assuming one shape fits all nine. Keep at least one
   enabled codebase-capable provider unless the consumer explicitly gives up
   `scope=codebase` and that decision is recorded.
2. Author `.sd-ai-command-pack/review.json` in each consumer that lacks one,
   with `codex` enabled. Decide `policy.localAdvisorySeverityCeiling`
   separately and per consumer, recording the reason when it is set; omitting
   it is the strict default and an acceptable outcome.
3. Land each consumer's file through that repository's own normal gated flow.
   This task does not merge on their behalf.
4. Roll out in the cohort order `docs/fleet/consumers.json` declares — canary
   (`rwbp-coordinator`, `loadsmith`, `hoa-manager`), then post-canary, then
   final — and confirm a real review run on the canary before continuing.
5. Leave `sd-github-review` as it stands unless the chosen fleet shape
   contradicts it, in which case reconcile it explicitly.
6. For each consumer, ensure its `.gito/config.toml` no longer blanket-excludes
   `review.json` before or in the same change that adds the file — either by
   sequencing `08-28-gito-blanket-exclusion-fleet` ahead of it in that
   consumer, or by narrowing that consumer's pattern here. Record which route
   each consumer took.

## Out of scope

- Making `codex` enabled by default in `_default_config()`. That is
  `08-07-default-local-review-lanes`, and it must not be pre-empted here.
- Adding `gemini` or `kimi` lanes (`08-07-plugin-review-provider-lanes`,
  parked).
- Changing the routed backend or its descriptor. `.gito/config.toml` is in
  scope only for the narrow exclusion change requirement 6 describes; the
  broader fleet-wide narrowing remains `08-28-gito-blanket-exclusion-fleet`.
- Teaching the installer to ship `review.json`. Whether the rollout should be
  hand-authored once or generated is a real question, but answering it changes
  the installer contract and belongs in its own task.

## Acceptance criteria

1. Running the fleet enumeration below reports `codex=True` for all nine
   consumers, with no `ABSENT` rows:

   ```bash
   for p in <each consumer pathHint>; do
     python3 - "$p/.sd-ai-command-pack/review.json" <<'EOF'
   import json,sys
   d=json.load(open(sys.argv[1]))
   print([(x["id"],x["enabled"]) for x in d["providers"]],
         d["policy"].get("localAdvisorySeverityCeiling"))
   EOF
   done
   ```

2. Every consumer whose config sets `localAdvisorySeverityCeiling` has a
   recorded reason for that choice; consumers that omit it are recorded as
   deliberately strict. A non-null ceiling everywhere is not the target.
3. Every consumer's config either enables a provider whose `scopes` include
   `codebase`, or carries a recorded decision that the repository has given up
   `scope=codebase`. Verify with the local stage helper, which is what owns
   `--plan-only` — `sd-review` has no such control:

   ```bash
   bash "$SD_PACK_TOOLCHAIN" run-python -- \
     sd-ai-command-pack-review-local.py --repo . --scope codebase \
     --plan-only --json
   ```

   Confirm it plans rather than raising `no eligible local review provider
   satisfies the selected policy`.
4. On at least one canary consumer, a real `sd-review` run over a non-trivial
   branch produces a receipt whose `remoteGate.state` is `eligible` and whose
   selected providers include `codex`, with zero routed rounds. Capture the
   receipt as evidence; a passing config check alone does not satisfy this.
5. No consumer carrying a `review.json` still matches it against a
   `.sd-ai-command-pack/**` blanket pattern. Verify by grepping every
   consumer's `.gito/config.toml` for the blanket string and expecting zero
   hits among repositories this task touched.
6. The `sd-status fleet` provider-config advisory is re-read after the rollout
   and its post-rollout text recorded — note that `08-16-fleet-local-config-advisory`
   describes this advisory as firing whenever a consumer owns the file, so it
   may not clear, and this criterion is satisfied by recording the observed
   behaviour, not by the advisory disappearing.

## Known blocker

`sd-status fleet` currently cannot run on this machine:

```text
error: fleet configuration not found; run install.py TARGET --configure-fleet
       from the sd-ai-command-pack source checkout
```

Acceptance criterion 6 depends on it. Criterion 5 does not: the exclusion
check greps each consumer's `.gito/config.toml` directly and stays verifiable
while the fleet profile is missing. Either configure the fleet profile as a
first step, or record criterion 6 as unverifiable and say so explicitly.
