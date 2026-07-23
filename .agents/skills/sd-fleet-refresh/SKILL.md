---
name: sd-fleet-refresh
description: Use when a pack release must roll across the consumer fleet through the deterministic campaign controller, source preflight, bounded waves, and serialized housekeeping merges.
---

# SD Fleet Refresh

Run this source-checkout-only skill after a pack release is merged and tagged.
It refreshes the configured consumers without touching dirty or externally
owned checkouts. `docs/FLEET_ROLLOUT.md` owns the delivery procedure; the
versioned fleet controller owns campaign state, ordering, concurrency, retries,
receipts, and the next eligible action.
It preserves sequential canaries and bounded post-canary waves while keeping
merges serialized.

The skill interprets controller output, invokes the action owner, explains
material exceptions, and renders the final report. Never reconstruct or
override campaign state from conversation history.

## When to use

- Run from the `sd-ai-command-pack` source checkout after its immutable
  `v<version>` release and full-fleet candidate ledger exist.
- Use only for installer-managed refreshes of consumers already listed in
  `docs/fleet/consumers.json` and already cloned at their configured path.
- Rerun an existing campaign through `resume`; never invent a second campaign
  to hide an issued or ambiguous side effect.
- Use `sd-finish-work` and `sd-housekeeping` for this source repository's own
  release. This skill owns only the post-release consumer rollout.

## Arguments

Arguments arrive as free text. Parse recognized `key=value` arguments and bare
flags before treating remaining bare values as the positional primary subject.
Reject unknown option-shaped input before planning or mutation.

- `consumer=<a,b>` selects named consumers. Remaining bare names are the same
  positional form: `sd-fleet-refresh loadsmith rwbp-website` is equivalent to
  `consumer=loadsmith,rwbp-website`. Preserve order, de-duplicate exact repeats,
  and reject mixed positional plus explicit consumer input.
- `no-merge` records PR-open completion and never issues a merge action.
- `remote-review` forces the configured remote review path instead of the
  eligible integration-only profile.
- `dry-run` performs verified release/fleet preflight and reports without
  issuing a consumer action.
- `remote=<name>` selects the immutable release-authority remote; default
  `origin`.

Validate the normalized consumers against the fleet manifest. An unknown name
is an error and must never broaden to the full fleet. Report the normalized
consumer set, merge mode, review mode, dry-run state, and release remote before
starting.

Campaign IDs, state locations, action IDs, attempts, and checkout overrides are
trusted internal context, not public arguments. Do not expose them through a
platform adapter.

## Campaign controller

Choose one safe campaign ID from the target version and UTC start time, record
it in the active task/session, and reuse it after interruption. Create or
idempotently reopen the campaign before preflight:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py plan \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --release <version> [--consumer <name> ...] [--no-merge] --json
```

The controller validates the release, manifest, selected checkout identities,
canary/wave policy, and existing campaign identity. It stores private atomic
state outside every repository. It never runs repository commands or GitHub
mutations itself.

Drive work only from issued actions:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py next \
  --repo <absolute-source-root> --campaign <campaign-id> --json
```

Every action binds the campaign, immutable release, consumer, stage, attempt,
timeout, and whether it may cause a side effect. Execute it once through the
owner named below, then record one normalized receipt:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py record \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --release <version> --action-id <full-action-id> \
  [--consumer <name>] --result <result> [receipt evidence] --json
```

Results are `passed`, `at-target`, `retryable-failure`, `product-failure`,
`review-finding`, `ownership-skip`, `permanent-incompatibility`,
`operator-decision`, or `ambiguous`. Every non-success result requires a safe,
bounded `--reason-code`; verified blockers may also supply `--blocker` and
`--pack-blocker`. PR publication records `--head <full-sha>` and
`--pr-number <number>`. Review, merge eligibility, merge, and post-merge
verification record that same exact `--head`; stale heads fail closed.

Repeating an identical receipt is a no-op. A conflicting receipt, wrong
release or consumer, skipped stage, duplicate action, changed fleet manifest,
or invalid concurrent start is rejected. Never edit controller state manually.

## Action ownership

The controller returns the stage; this map selects its existing action owner
but defines no ordering or transition policy:

- `preflight`: run `sd-ai-command-pack-fleet-preflight.py` with the normalized
  consumers and release remote. Its immutable release, payload, ancestry,
  ledger, and inventory result is the release-identity guard and remains
  authoritative.
- `checkout-validation`: confirm the configured checkout exists and is clean,
  has no live no-touch/loop owner, capture the exact base commit, and create one
  isolated refresh branch. Dirty or externally owned means `ownership-skip`;
  never stash, reset, clean, or install.
- `install-update` and `install-audit`: run only the commands printed by
  preflight. The installer, provenance, and audit remain authoritative.
- `candidate-prepare`, `focused-candidate`, and `local-checks`: run the
  manifest-ordered preparation/check commands and the consumer's documented
  full local gate.
- `pr-publication`: commit only installer-managed output, classify the exact
  base/head with `sd-ai-command-pack-fleet-review-classify.py`, push, and create
  or reuse one PR. Record the published head and PR number.
- `review`: invoke `sd-review-pr` once with trusted `caller: sd-fleet-refresh`,
  `return-after: review-result`, and `defer-finish-work: true`. Supply either
  the exact-head `integration-only` context or the normal `remote` profile.
  Existing comments and unresolved threads are always inspected. Classifier
  ambiguity falls back to the normal remote-review convergence loop;
  `remote-review` selects that same normal path explicitly.

  ```text
  caller: sd-fleet-refresh
  review-profile: integration-only
  source-root: <absolute pack source checkout>
  consumer: <fleet manifest name>
  base-commit: <full base SHA>
  release-remote: <source release remote>
  classified-head: <full consumer refresh SHA>
  return-after: review-result
  defer-finish-work: true
  ```
- `merge-eligibility`: run the finding severity gate, settle required checks
  through `sd-watch-pr` with its internal `no-merge` handoff, and prove the
  recorded head remains green, comment-clean, and mergeable.
- `merge`: only the controller's single eligible action may invoke the
  consumer's `sd-housekeeping` gate. The controller alone invokes housekeeping;
  it never merges in completion order.
- `post-merge-verification`: verify the installed target version, install audit,
  clean default branch, deleted refresh branch, and pruned refs.

Call `next` again only after every issued action has a receipt. It may issue
sequential canaries or a bounded `canStart` wave up to `maxConcurrency`, and it
issues at most one manifest-ordered merge candidate. Each lane owns one
existing checkout, branch, and PR. Terminal consumers are never restarted.

## Timing evidence

Initialize `scripts/sd-ai-command-pack-fleet-timing.py` before executing the
controller's preflight action, then bracket the corresponding delivery work.
Start both `reviewer-wait` and `ci-wait` immediately after the PR exists; end
`reviewer-wait` when review returns and end `ci-wait` when checks settle. Use
`report --run-id <run-id> --complete` only after every selected consumer has a
terminal controller result.

Timing remains mandatory internal observability. It is private, resumable, and
never changes a delivery gate's authoritative result. Do not put paths,
credentials, command output, review text, or secrets in timing reasons. A
timing failure pauses new mutation until the last valid record is reconciled.

## Workflow

1. Normalize and validate arguments. Resolve the release version, controller
   campaign ID, timing run ID, selected consumers, and existing checkout paths.
2. Run controller `plan`, initialize timing, call `next`, and execute the issued
   `preflight` action. Record its exact result. With `dry-run`, finalize the
   read-only report here and issue no consumer action.
3. Repeatedly call controller `next`. Execute only returned actions, within the
   returned timeout and one-checkout ownership boundary, and record every
   result before requesting more work.
4. Before recording a verified finding, run the finding severity gate below.
   Use `review-finding --pack-blocker` for a pack-owned blocker; use the
   controller's normalized non-blocking result for deferred or consumer-local
   work after replies, allowed resolution, and follow-up capture are complete.
5. After interruption or when no action is returned but work is not complete,
   run controller `resume` and do not replay an issued side effect. Load
   `references/controller-recovery.md` only when reconciliation, a blocked
   campaign, invalid state, an ownership retry, or a corrective release is
   actually present.
6. Run controller `validate` and `status`, complete timing, and render the final
   report from receipts. Do not reconstruct a lane history from chat.

## Finding severity gate

For each non-empty batch of verified findings, create a temporary
schema-version-1 findings file and run:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-finding-classify.py \
  --input <temporary-findings.json> --json
```

Each row has a unique safe `id`, `contractFamily`, `summary`, `evidence`, and
`reviewer`, with optional repository-relative `path` and positive `line`.
`impact: blocker` requires concrete `impactEvidence`; an explicit
`overrideDisposition` requires `overrideRationale`. Never infer an override
from prose, a public flag, or an environment variable.

- `continue-with-follow-ups`: reply with evidence to every observation,
  resolve allowed threads, and create or reuse one source or consumer Trellis
  follow-up per deferred owner before recording the stage result.
- `pause-corrective-release`: record `review-finding --pack-blocker`, stop
  before watch or merge, then load the recovery reference.
- `invalid-pause`, exit `2`, malformed output, or an unavailable command: fail
  closed and load the recovery reference. Never reinterpret invalid input as
  deferred work.

Exact duplicates share the first owner's timing disposition and follow-up.
Every duplicate still receives its own evidence-backed reply and allowed
thread resolution.

## Safety rules

- Execute only a current controller action for the configured consumer path.
  Never broaden scope through discovery, a typo, or missing state.
- Never touch a dirty, missing, or externally owned consumer checkout; never
  stash, reset, clean, force-push, clone, or create a new checkout here.
- Change only installer-managed files, receipts, provenance, and repo-owned
  deterministic preparation output. Never edit consumer product code.
- Preflight release identity, candidate evidence, install/audit, local checks,
  review, complete thread polling, CI, exact-head eligibility, housekeeping,
  and post-merge audit keep their existing authority.
- A verified pack blocker stops new starts and holds unsettled merges. A
  controller or telemetry error pauses mutation; prompt prose never overrides
  an invalid transition.
- Use the portable structured-question contract only for a genuinely ambiguous
  operator policy choice. Normal retries, polling, receipts, and optional
  absence do not prompt.

## Final report

Always include each section; state empty values explicitly as `none`.

- Campaign: ID, immutable release, controller schema/status, selected mode,
  preflight receipt, and validation result.
- Fleet: one row per selected consumer with before-version, review profile,
  controller stage/result, exact head/PR when present, and blocker/reason.
- Scheduling: canary/wave outcomes, concurrency actually used, serialized merge
  order, retries, reconciliation actions, and remaining next action.
- Findings: blocker/deferred owners, duplicates, overrides with rationale, and
  follow-up task identifiers.
- Timing: run state, critical path, active wall, summed stage time, slowest
  consumer/stage, reviewer/CI overlap, retries, and anomalies.
- Follow-ups: open PRs, skipped consumers, ownership retries, corrective work,
  and controller/timing anomalies.
