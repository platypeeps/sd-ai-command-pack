---
name: sd-fleet-refresh
description: Use when a pack release must roll across the consumer fleet through the deterministic campaign controller, source preflight, bounded waves, and serialized housekeeping merges. Campaign invocation is explicit approval for controller-issued in-scope consumer commits, PR-branch pushes, configured GitHub review requests or re-requests, and eligible managed consumer PR merges without another prompt.
model: sonnet
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

## Standing GitHub authority

Invoking the campaign is explicit approval for its ordinary controller-issued,
in-scope consumer GitHub actions: refresh commits, pushes to the dedicated PR
branch, PR creation or reuse, and configured GitHub review requests or
re-requests, plus controller-issued eligible merges through the consumer's
housekeeping lifecycle. Do not ask again solely because a managed consumer diff
will be committed, pushed, published, sent to the configured reviewer, or
merged after its findings are addressed and every gate passes. Omitting
`no-merge` selects this end-to-end merge authority; the explicit `no-merge`
flag remains the opt-out. This does not authorize product-code edits, dirty or
externally owned checkouts, force pushes, default-branch pushes, operator
decisions, destructive actions, or bypassing controller and lifecycle gates.

## Structured decisions

Read
[`../sd-help/references/structured-questions.md`](../sd-help/references/structured-questions.md)
before asking. This skill owns `fleet-refresh.operator-policy`, and asks it only
when the controller emits a genuine operator decision that leaves mutually
exclusive dispositions for a blocked campaign — park it, retry the blocked
consumer, or continue without it. Recommend the lowest-risk park option, bind
the answer to the exact campaign, consumer, release, and head/PR, and never let
a response broaden consumer scope or invent a controller transition. Routine
retries, polling, receipts, optional absence, deterministic transitions, and
actions already authorized by campaign policy never prompt; a noninteractive or
unanswered decision records `operator-decision` and parks without advancing
state.

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
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py plan \
  --repo <absolute-source-root> --campaign <campaign-id> \
  --release <version> [--consumer <name> ...] [--no-merge] --json
```

The controller validates the release, manifest, selected checkout identities,
canary/wave policy, and existing campaign identity. It stores private atomic
state outside every repository. It never runs repository commands or GitHub
mutations itself.

Drive work only from issued actions:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py next \
  --repo <absolute-source-root> --campaign <campaign-id> --json
```

Every action binds the campaign, immutable release, consumer, stage, attempt,
timeout, and whether it may cause a side effect. Execute it once through the
owner named below, then record one normalized receipt:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-controller.py record \
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

A stage gets two automatic attempts; a second `retryable-failure` parks the
lane as terminal `retry-exhausted`. That park is reversible only by the
operator, only after the cause is fixed and proven, and only through
`resume --recover-exhausted-consumer`; see
`references/controller-recovery.md`. The automatic budget itself never widens.

## Action ownership

The controller returns the stage; this map selects its existing action owner
but defines no ordering or transition policy:

- `preflight`: run `sd-ai-command-pack-fleet-preflight.py` with the normalized
  consumers and release remote. Its immutable release, payload, ancestry,
  ledger, and inventory result is the release-identity guard and remains
  authoritative.
- `checkout-validation`: confirm the configured checkout exists and is clean,
  has no live no-touch/loop owner, capture the exact base commit, and create one
  isolated refresh branch. Before installation, create and activate one
  dedicated lightweight Trellis task for this consumer and target release when
  no current task exists. Give its PRD the immutable release identity, managed
  scope, preparation/check commands, and finish-work expectation; bind it to
  the refresh branch.

  Tag every acceptance criterion with the evidence that would settle it, so the
  publish stage can tick what the run actually proved instead of leaving an
  archive that reports verified work as unverified:

  ```text
  - [ ] <!-- verify: install-audit release=<version> platforms=<a,b,c> --> The install audit passes ...
  - [ ] <!-- verify: tracked-mode path=<repo-relative path> mode=100755 --> ... is tracked 100755 ...
  - [ ] <!-- verify: bundle-shape --> Published as one PR whose head carries work, archive, and journal.
  - [ ] <!-- verify: lane-evidence id=check-command --> The declared check command passes.
  - [ ] <!-- verify: lane-evidence id=deterministic-gate --> The deterministic gate passes or its findings are dispositioned with zero blockers.
  ```

  The comment is invisible in rendered Markdown, so the criterion reads exactly
  as authored. Put the asserted version and platform set in the tag: the publish
  helper takes no release argument, so a criterion naming a version it cannot
  read is left unticked rather than ticked on an exit code alone.

  `install-audit`, `tracked-mode`, and `bundle-shape` are proved by the helper
  from the consumer tree. `lane-evidence` is not — it carries a result from a
  stage that ran earlier, and the operator supplies it at `pr-publication`.

  An untagged criterion, an unknown tag id, and a `lane-evidence` id with no
  supplied result are all left unticked and named in a generated disposition
  block. That is deliberate: an archive that silently reports unverified work as
  verified is worse than the defect this replaces, so the verifier never infers
  a criterion's meaning from its prose.

  Set the PR target as part of task creation:

  ```bash
  python3 ./.trellis/scripts/task.py create "<title>" --description "<summary>" \
    --base-branch <default-branch>
  ```

  Without `--base-branch`, `create` resolves the base from `origin/HEAD` and
  falls back to the **checked-out branch** — which at this stage is the refresh
  branch, and the review preflight then rejects the lane at `focused-candidate`
  under its root-task rule. Passing the flag closes that window rather than
  repairing it afterwards; `set-base-branch` remains the repair for a task that
  already exists. Reordering creation before the branch switch is not a
  substitute: it produces the right answer only by accident of which branch
  happens to be checked out.

  The flag requires the supported vendored-Trellis floor. A consumer below the
  floor is a violation to upgrade, not a case to write a fallback for — see
  `.trellis/spec/tooling/vendored-trellis-compatibility.md`.

  Then validate the seeded task mechanically before advancing, from **this
  source checkout** against the consumer:

  ```bash
  SD_PACK_TOOLCHAIN=""
  for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
    "scripts/sd-ai-command-pack-toolchain.sh" \
    "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
    if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
  done
  [ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

  bash "$SD_PACK_TOOLCHAIN" run -- sd-ai-command-pack-review-preflight.mjs seeded-task \
    --repo <absolute consumer checkout> --task-dir <consumer-relative task dir> --json
  ```

  Require schema version 1 and `status: valid` with `seeded_task_valid`. Any
  other status is a checkout-validation failure: report the findings verbatim —
  each names the offending file and what must change, with a line number when
  the finding is line-scoped (the `base_branch` and `description` findings are
  field-level and have none) — and do not advance. It rejects
  an empty `description`, a `base_branch` that is not the consumer's default
  branch, `TBD` placeholders left in `prd.md`, `_example` scaffold rows still in
  `implement.jsonl` / `check.jsonl`, and a context row citing a path under the
  seeded task's **own** directory, which `task.py archive` would dangle inside
  the same completion bundle that publishes it.

  Run it from the source checkout, never the consumer's installed copy: this
  stage runs *before* `install-update`, so the consumer still carries the
  previous release, whose preflight exits `2` with
  `unknown review-preflight command`. Leave the pack's default-branch override
  environment variable unset for the whole lane — under `--repo` it outranks the
  consumer's own `origin/HEAD` and would decide the very rule this gate
  enforces. The receipt's `evidence.defaultBranchSource` records which one
  answered.

  This replaces the prose description assertion that used to live here. The
  guard was always meant to be belt-and-suspenders against an upstream
  `task.py create` that tolerates an empty description; as prose it could be and
  was skipped, and consumers reached `focused-candidate` with
  `field description must be a non-empty string`.

  An unrelated current task, dirty Trellis state, or externally owned checkout
  means `ownership-skip`; never repurpose another task, stash, reset, clean, or
  install.
- `install-update` and `install-audit`: run only the commands printed by
  preflight. The installer, provenance, and audit remain authoritative.
- `candidate-prepare`, `focused-candidate`, and `local-checks`: run the
  manifest-ordered preparation/check commands and the consumer's documented
  full local gate.
- `pr-publication`: commit only the dedicated consumer task artifacts,
  installer-managed output, receipts/provenance, and deterministic preparation
  output. Classify the exact base/head with
  `sd-ai-command-pack-fleet-review-classify.py`, push, and create or reuse one
  PR. Record the published head and PR number. Fold finish-work into the
  reviewed head with `sd-ai-command-pack-fleet-publish.py`: it makes the work
  commit (pack + active task + a pre-computed post-archive `repomix-map` on
  repomix-indexed consumers), then archives the task and records the journal via
  the shipped `record-session` wrapper so the pushed head already carries all
  bookkeeping. Immediately before the archive it ticks the acceptance criteria
  it can prove and reports the rest; pass one
  `--criterion-evidence <id>=verified|unverified[:<note>]` for each
  `lane-evidence` tag in the PRD, taking the verdict from the stage that
  produced it — `check-command` from `local-checks`, `deterministic-gate` from
  the finding severity gate. A malformed value is rejected outright, because a
  typo that read as "unverified" would be indistinguishable from a stage that
  legitimately could not verify. The unticked set comes back as
  `uncheckedCriteria` in the helper's result. It refuses to run on a tree dirty outside the managed allowlist,
  transactionally restores the task on any error, asserts the completion delta
  is `.trellis`-only, and never pushes on an invalid receipt — so the merge
  stage sees zero head-advance and no successor to reclassify. When a prior
  merge action
  returned here because `sd-finish-work` advanced the PR, do not create another
  commit or push: verify the retained finish-work receipt names the current
  local and remote PR head, reclassify that exact successor, reuse the existing
  PR, and record the new publication epoch. A corrective recovery may instead
  reuse this stage to append and validate missing task evidence before pushing
  a replacement head; neither path replays the earlier merge action.
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
  through the read-only watch coordinator
  (`../sd-ship/references/watch-coordinator.md`) until it reports
  `settled-green`, and prove the recorded head remains green, comment-clean,
  and mergeable. Any other coordinator outcome stops this action with its
  report.
- `merge`: only the controller's single eligible action may invoke the
  consumer's `sd-housekeeping` gate. Complete the dedicated task through
  `sd-finish-work` and retain its exact-head receipt. Compare the resulting
  local and remote PR head with the controller's published head before invoking
  housekeeping. If finish-work advanced the PR, record the issued merge action
  as `retryable-failure --reason-code pr-head-advanced` against the old
  published full head and existing PR number, retain the receipt, and stop this
  action before housekeeping; the controller will issue a bounded successor
  publication, review, and eligibility cycle. On the next merge action, when
  the retained receipt names the unchanged reviewed head, pass it to
  housekeeping without running finish-work again. The controller alone invokes
  housekeeping; it never merges in completion order.
  Execute that issued merge without another approval prompt, including when
  the head contains
  in-scope changes that addressed rollout review findings; campaign invocation
  already authorizes this normal end-to-end action.
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
   campaign, invalid state, an ownership retry, an exhausted retry budget, or a
   corrective release is actually present.
6. Run controller `validate` and `status`, complete timing, and render the final
   report from receipts. Do not reconstruct a lane history from chat.

## Finding severity gate

For each non-empty batch of verified findings, create a temporary
schema-version-1 findings file and run:

```bash
SD_PACK_TOOLCHAIN=""
for candidate in "${SD_AI_COMMAND_PACK_TOOLCHAIN:-}" \
  "scripts/sd-ai-command-pack-toolchain.sh" \
  "$HOME/.agents/bin/sd-ai-command-pack-toolchain.sh"; do
  if [ -f "$candidate" ]; then SD_PACK_TOOLCHAIN="$candidate"; break; fi
done
[ -n "$SD_PACK_TOOLCHAIN" ] || { printf '%s\n' "error: sd-ai-command-pack toolchain not found; checked SD_AI_COMMAND_PACK_TOOLCHAIN, scripts/, and \$HOME/.agents/bin. Reinstall the command pack." >&2; exit 1; }

bash "$SD_PACK_TOOLCHAIN" run-python -- \
  sd-ai-command-pack-fleet-finding-classify.py \
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
- Change only the dedicated task artifacts, installer-managed files, receipts,
  provenance, and repo-owned deterministic preparation output. Never edit
  consumer product code.
- Preflight release identity, candidate evidence, install/audit, local checks,
  review, complete thread polling, CI, exact-head eligibility, housekeeping,
  and post-merge audit keep their existing authority.
- A verified pack blocker stops new starts and holds unsettled merges. A
  controller or telemetry error pauses mutation; prompt prose never overrides
  an invalid transition.
- In merge-capable mode, do not ask again before an eligible controller-issued
  consumer merge, including after in-scope finding remediation. Ask only when
  the controller emits a genuine operator decision; `no-merge` remains the
  explicit way to stop before merge.
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
