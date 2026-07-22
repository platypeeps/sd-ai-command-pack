---
name: sd-fleet-refresh
description: Use when a pack release must roll across the consumer fleet — run fleet preflight, sequential canaries, then bounded post-canary waves with deterministic gated merges per docs/FLEET_ROLLOUT.md.
---

# SD Fleet Refresh

Run this project-local skill for `sd-fleet-refresh` and `/sd:fleet-refresh`
style work, from the sd-ai-command-pack source checkout. It rolls the current
pack release across the known consumer repositories: canaries run sequentially,
then manifest-configured post-canary cohorts may overlap within a conservative
bound while merge decisions remain serialized.

`docs/FLEET_ROLLOUT.md` is the procedure authority. This skill orchestrates
exactly that documented procedure — preflight, then per-consumer branch,
install, audit, full-check, PR, watch, and gated merge — and improvises no
steps beyond it. It never touches a dirty consumer tree, and consumer merges
go only through the green + comment-clean housekeeping gate.

## When to use

Run this command after a pack release has merged and tagged, when fleet
consumers are behind the target version in `manifest.json`.

- Run it from the pack source checkout. The fleet manifest
  (`docs/fleet/consumers.json`), the preflight script, and `install.py` all
  live here, and the rollout doc installs from this checkout.
- Use it to refresh the vendored pack files in consumer repositories. It is
  not a general consumer maintenance, upgrade, or code-change command.
- The pack repository's own release flow stays with `sd-finish-work` and
  `sd-housekeeping`; run this command after that release exists.
- Rerunning after an interruption is safe: preflight marks already
  refreshed consumers `at-target`, so a rerun resumes with the remaining
  stale consumers instead of opening duplicate refresh PRs.
- The release must already have a valid full-fleet candidate ledger. Candidate
  validation is a pre-release source workflow, not part of this post-tag
  command; follow `docs/FLEET_ROLLOUT.md` when preparing the release.

## Arguments

Arguments arrive as free text with the invocation. Parse the recognized
`key=value` argument and bare flags before treating remaining bare values as
the positional primary subject. Unknown option-shaped arguments are an error,
not a silent skip: stop and report them before running preflight. This skill
reads no environment variables; every tuning knob is an argument.

- `consumer=<a,b>` — comma-separated fleet consumer names. Limit the run to
  those consumers. Pass each name to preflight via `--consumer`; preflight
  rejects names that are not in the fleet manifest. Without `consumer=`,
  the run covers every consumer in the fleet manifest.
- `no-merge` — bare flag. Stop every consumer at PR-open: open and watch the
  consumer PR, but do not merge it.
- `remote-review` — bare flag. Force the normal configured remote-review loop
  for every refreshed consumer even when the source classifier proves the PR
  qualifies for integration-only review.
- `dry-run` — bare flag. Run preflight and emit the report only; perform no
  consumer mutations.
- `remote=<name>` — Git remote whose immutable `v<version>` tag must match the
  local release tag. Defaults to `origin`. Use an explicit mirror remote when
  `origin` is not the release authority.
- Remaining bare values are consumer names. `sd-fleet-refresh loadsmith
  rwbp-website` is equivalent to `consumer=loadsmith,rwbp-website`. Split bare
  names on whitespace or commas, preserve their order, and de-duplicate exact
  repeats.

Reject bare consumers combined with `consumer=` before preflight. Validate
every normalized consumer against the fleet manifest before mutation; an
unknown name is an error and must never broaden the run to the whole fleet.
Before preflight, report the normalized consumer set (`all` when unfiltered),
merge behavior, review behavior (`auto` or `remote-review`), dry-run state, and
release remote.

## Timing evidence

Timing is mandatory internal observability, not a public fleet option. Do not
add timing arguments or environment variables to an adapter. Create one safe,
unique run ID from the target version and UTC start time, record it in the
active fleet task or session context, and reuse that exact ID after an
interruption. Read selected consumer names and priorities from the fleet
manifest, then initialize the local record before preflight:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-timing.py --repo <absolute-source-root> \
  init --run-id <run-id> --target-version <version> \
  --consumer <name>:<priority> [...]
```

The helper stores private, atomic state outside the repository and prints a
repository digest rather than an absolute path. Bracket an authoritative
operation with `stage-start` and `stage-end`, using `--fleet` only for
`preflight` and `--consumer <name>` for the remaining stages. A failed,
skipped, or interrupted stage requires a short bounded `--reason` without a
path, credential, review body, or command output. Record each final consumer
with `consumer-end`, then use `report --complete` only after every selected
consumer has an outcome. Repeated identical commands are safe no-ops, and a
new attempt begins only with another `stage-start` after the prior attempt
closed.

The fixed consumer stage mapping is `checkout-validation`, `install`, `audit`,
`local-gate`, `commit-push`, `pr-creation`, `reviewer-wait`, `ci-wait`,
`housekeeping`, and `post-merge-audit`. Start both `reviewer-wait` and
`ci-wait` immediately after PR creation. End the reviewer interval when
`sd-review-pr` returns and the CI interval when `sd-watch-pr` settles, so their
natural overlap is measured instead of double-counted.

If a timing command fails, report the telemetry anomaly and pause further
fleet mutation until the last valid record can be resumed or its input can be
corrected. Never change, erase, or reinterpret an install, audit, review, CI,
finding, or housekeeping result to make telemetry succeed.

## Wave planning

The main fleet controller owns the observation snapshot, scheduler calls,
finding classification, merge order, timing report, and final report. Each
dispatched consumer lane owns exactly one existing checkout, branch, and PR;
no second lane may touch that checkout. Consumer lanes may overlap through
checkout validation, install, audit, local validation, commit/push, PR
creation, review, and CI wait. The controller alone invokes housekeeping and
post-merge audit, one merge candidate at a time.

Before every dispatch or merge decision, write a temporary schema-version-1
snapshot containing every manifest consumer exactly once:

```json
{
  "schemaVersion": 1,
  "consumers": [
    {"name": "rwbp-coordinator", "state": "at-target", "packBlocker": false}
  ]
}
```

Use live preflight, local branch, PR, review, CI, finding, and merge evidence to
assign `pending`, `in-flight`, `ready`, `at-target`, `merged`, `pr-open`,
`skipped`, `failed`, or `blocked`. Never infer `packBlocker`; set it only after
the finding severity gate verifies a pack-owned blocker. Run:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-wave-plan.py \
  --fleet docs/fleet/consumers.json --state <temporary-wave-state.json> --json
```

Append `--no-merge` when that fleet mode is active. In that explicit mode,
`pr-open` canaries unlock the next consumer while the planner holds all merges
and emits no `mergeCandidate`; normal runs still require canaries to be
`at-target` or `merged`.

Delete the temporary snapshot after parsing the result. Start only names in
`canStart`, never exceed `maxConcurrency`, and consider only `mergeCandidate`
for housekeeping. A later ready PR waits for earlier manifest-order consumers.
Any `stopStarting` or `holdMerges` result pauses those actions; a controlled
planner error is an invalid-pause, not permission to fall back to unbounded or
completion-order work. Rerunning the planner from refreshed live evidence is
the resume mechanism: terminal consumers are never restarted.

## Workflow

1. Initialize the timing run, start its fleet-scoped `preflight` stage, then
   run preflight. The matching local `v<manifest-version>` tag must already
   exist; if the release was tagged remotely after the last fetch, fetch tags
   before this step. From the pack checkout, run:

   ```bash
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-fleet-preflight.py
   ```

   Append `--remote <name>` when `remote=` is present. Preflight fails before
   consumer inventory or mutation unless the local tag matches the remote tag,
   the tag is an ancestor of the checkout, the tagged version and installable
   payload match the current source payload, and both tagged and current
   candidate ledgers validate. Do not bypass or substitute a manifest-version
   check for this release-identity guard.

   Append `--consumer <name>` for each entry in the `consumer=` filter. The
   script reads the target version from `manifest.json`, reports consumers
   already at that version as `at-target` — skip them, which prevents
   duplicate empty refresh PRs — and prints the exact install and audit
   commands for every stale consumer. A consumer without a local clone
   cannot be refreshed from this checkout: record it as skipped with that
   reason. End the preflight timing stage as `passed`, or as `failed` with the
   bounded preflight reason before stopping.
2. With `dry-run`: emit the final report from the preflight results and
   stop here. Zero consumer mutations. Record `at-target` for consumers already
   current and `skipped` with reason `dry-run did not mutate consumer` for each
   remaining selected consumer, then complete the timing report.
3. Initialize the wave snapshot from preflight and drive every start and merge
   decision through the wave planner. The manifest's canary cohort remains
   strictly sequential and must be fully merged, audited, and free of
   pack-owned blockers before a later cohort starts. After that gate, dispatch
   only the planner's bounded `canStart` set. AMC remains in its configured solo
   final cohort. Do not reorder from incidental local paths, completion time,
   or manifest editing order.

   For each dispatched consumer, run steps 1-8 below in its isolated lane.
   Those lanes may overlap only when the planner permits it. A lane reports
   `ready` after review, finding disposition, and CI settle. The controller
   then runs steps 9-10 only for the planner's single `mergeCandidate`, refreshes
   live observations, and asks the planner again:
   1. Start `checkout-validation`, verify the consumer checkout has a clean
      working tree, and create a refresh branch from its current default
      branch. If it is dirty, end the stage and consumer as skipped with the
      reason. Never stash, reset, clean, or install over it.
   2. Record the exact full base commit before installation;
      integration-only classification is bound to that commit, not a moving
      branch name.
   3. Bracket `install` and `audit` separately. Install the pack release per
      `docs/FLEET_ROLLOUT.md`: run the
      preflight-printed `python3 install.py <repo> --force --platform ...`
      command from the pack checkout, then the printed install-audit
      command with its `--expected-platform` set.
   4. Run every `candidatePrepare` command reported by preflight, in manifest
      order and from the consumer checkout. These deterministic generators are
      part of the real refresh shape, not candidate-validation-only setup.
      Then bracket `local-gate` and run the consumer's full-check gate — its
      `make full-check` or the
      consumer-documented equivalent. If preparation or the gate fails, do not
      open a PR:
      record the consumer as skipped with the failure summary, leave the
      local branch for inspection, classify the finding, record the precise
      outcome, and refresh the wave plan.
   5. Bracket `commit-push`. Commit the refreshed files. Before pushing, run
      the source-side
      classifier against the exact base and current head:

      ```bash
      bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
        scripts/sd-ai-command-pack-fleet-review-classify.py \
        --consumer <name> --repo <consumer-path> \
        --base-commit <full-base-sha> --remote <release-remote> --json
      ```

      Run this command from the pack source checkout. Exit `0` selects the
      `integration-only` profile unless `remote-review` was supplied. Any
      nonzero result, malformed output, head mismatch, or explicit override
      selects the normal configured remote-review profile; never reinterpret a
      classifier failure as permission to skip review.
   6. Push within `commit-push`, then bracket `pr-creation` while opening the
      consumer PR. Immediately after the PR exists, start both `reviewer-wait`
      and `ci-wait`. Resolve `sd-review-pr` and run it as the sole review owner,
      then end `reviewer-wait`. For an eligible auto-classified branch,
      supply this exact trusted internal context:

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

      This is internal orchestration context, not a user-facing argument. The
      review owner reruns the classifier and suppresses only a new configured
      remote implementation-review request. It still runs the deterministic
      consumer gate, dispositions first-review advisories, inspects all
      existing comments and unresolved threads, checks CI, addresses valid
      findings, and performs the one PR-scoped learning pass. If
      classification no longer matches the exact PR head, it falls back to the
      normal remote-review convergence loop. For non-qualifying branches or
      `remote-review`, invoke the normal `sd-review-pr` profile with trusted
      `caller: sd-fleet-refresh`, `review-profile: remote`,
      `return-after: review-result`, and `defer-finish-work: true` context, but
      no integration-only classifier fields.
   7. Before watch or merge, apply the finding severity gate below to every
      verified finding surfaced by install, audit, consumer checks, review, or
      existing feedback. If there are no verified findings, record zero
      finding observations and continue. Exit `0` permits the run to continue
      only after observation replies, allowed thread resolution, and follow-up
      capture are complete. Exit `1` or `2` pauses before this PR or another
      consumer can be merged or mutated.
   8. Run `sd-watch-pr` with its internal `no-merge` handoff so required
      checks and review state settle without duplicating housekeeping. End
      `ci-wait` with the exact settled outcome.
   9. After the lane reports `ready`, return control to the controller. Only
      when the planner returns this consumer as `mergeCandidate`, bracket
      `housekeeping`, then merge via the consumer's housekeeping gate:
      green, comment-clean,
      mergeable, heads identical. With `no-merge`, leave the PR open and
      record the consumer as PR-open instead of invoking housekeeping.
   10. Bracket `post-merge-audit`. Confirm post-merge provenance reads the
      target version and the
      install audit passes, per the rollout doc. Finish the consumer's
      housekeeping cleanup — default branch checked out, refresh branch
      deleted, refs pruned — then record `refreshed-merged` and move to the
      next planner decision. `no-merge` records `pr-open`; unavailable, dirty,
      blocked, or failed consumers use their matching timing outcome and
      bounded reason.
4. Aggregate the per-consumer outcomes into the fleet status table and the
   fleet version summary for the final report. Render a partial timing report
   after an interruption. When every selected consumer has an outcome, run
   `report --run-id <run-id> --complete` and include its summary.

## Finding severity gate

For every batch of verified findings, construct a temporary schema-version-1
JSON file and run this source-only, read-only command from the pack checkout:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-finding-classify.py \
  --input <temporary-findings.json> --json
```

The input has a non-empty `findings` array. Every row contains a unique safe
`id`, `contractFamily`, `summary`, `evidence`, and `reviewer`, with optional
repository-relative `path` and positive `line`. Contract family is exactly one
of `correctness`, `security`, `install-audit`, `compatibility`, `hardening`,
`style`, `test-implementation`, `documentation`, `diagnostics`, or
`consumer-unrelated`. Use `impact: blocker` plus concrete `impactEvidence` to
escalate a normally deferred family. An operator may explicitly set
`overrideDisposition` only together with `overrideRationale`; never infer an
override from prose, a public flag, or an environment variable.

Interpret the result by owner rows, not raw observation count:

- Exit `0`, `continue-with-follow-ups`: correctness is not being dismissed.
  Reply with evidence to every observation and resolve its thread only when
  repository policy permits. Create or reuse one source or consumer Trellis
  follow-up per deferred owner when work remains, record its task identifier,
  then continue the rollout.
- Exit `1`, `pause-corrective-release`: stop before watch, merge, or the next
  consumer mutation. Feed all blocker owners into one corrective campaign;
  do not create one release or task per observation.
- Exit `2`, `invalid-pause`, malformed output, or unavailable command: fail
  closed and pause for input correction. Never reinterpret an invalid result
  as deferred work.

Exact duplicates have the same normalized reviewer, path, line, and summary.
The first observation owns their timing disposition, release trigger, and
follow-up task. Every duplicate still receives its own evidence-backed reply
and allowed thread resolution. Conflicting duplicate policy is invalid input.
Delete the temporary file after capturing the deterministic result, and retain
the owner, duplicate, escalation, and override evidence in the fleet report.

## Corrective campaign

When the finding severity gate returns `pause-corrective-release` for a
verified pack-owned blocker:

1. Immediately pause consumer mutation before selecting or preparing another
   release. Keep the original fleet task available to resume later.
2. Reuse or create one source-owned Trellis corrective task. Record every
   verified finding in a single ledger with this shape:

   `ID | Contract family | Evidence | Severity | Disposition | Fix | Regression`

   Use classifier owner rows for this ledger. Exact duplicates reuse the
   owning row instead of creating another task or release trigger.
3. Run a bounded contract-surface sweep around the failure before choosing the
   corrective version. Cover equivalent producers and consumers, mutation
   paths, persisted and dynamically loaded data, normalization and nullability,
   CLI exposure, human and JSON output, failure behavior, and generated or
   template mirrors where applicable. Record excluded adjacent surfaces.
4. Iterate with focused source tests and optional partial candidate diagnostics
   using `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-fleet-candidate-check.py --consumer <name>`.
   Partial runs are diagnostic and must never replace the canonical candidate
   ledger.
5. After the finding ledger and regressions converge, freeze the payload,
   select one corrective version, update release surfaces once, and run one
   canonical full-fleet candidate validation with the no-filter command. Only
   that canonical run may update `docs/fleet/candidate-validation.json`.
6. Merge and tag through the source lifecycle, then resume the original fleet
   task from a fresh preflight rather than creating a duplicate rollout task.

An urgent independent security defect may ship before the broader campaign
only when waiting would increase risk. Record that reason and keep the remaining
campaign open.

## Safety rules

- `docs/FLEET_ROLLOUT.md` is the procedure authority. Follow its refresh
  shape exactly; do not invent steps it does not document.
- This skill never touches a dirty consumer tree. Dirty means skip and
  report — never stash, reset, clean, or install over local changes.
- Keep canaries sequential. After they succeed, overlap only the scheduler's
  bounded `canStart` set. Never share a checkout, branch, or PR between lanes,
  and keep housekeeping merges serialized in manifest order.
- Consumer merges go only through the green + comment-clean housekeeping
  gate. Never merge a red, commented, or behind consumer PR, and never
  force a merge that GitHub refuses.
- Never force-push in any consumer repository.
- Never create or clone consumer checkouts from this command. Refresh only
  consumers that already have a local clone at the fleet-manifest path.
- Skipped consumers are always reported with their reasons. A silent skip
  is a defect.
- Change only the files the pack installer writes, plus its receipts and
  provenance. Never edit consumer product code.
- Run the finding severity gate for verified findings before watch, merge, or
  another consumer mutation. Invalid classification pauses. Default blocker
  families are correctness, security, install/audit, and compatibility;
  normally deferred findings still require replies, allowed thread resolution,
  and one recorded follow-up per owner when work remains.
- Consumer review focuses on selected-platform wiring, provenance, secrets,
  docs accuracy, and repo-owned migrations. Pack-owned implementation is
  reviewed in the source PR, not line-by-line in every refresh PR.
- Integration-only review is allowed only after the source classifier returns
  eligible for the exact consumer head and `sd-review-pr` rechecks it. The
  profile skips only a new remote-review request; it never skips existing
  feedback, deterministic gates, CI, watch, or housekeeping.
- `remote-review` always forces the normal review path. Classifier ambiguity,
  unavailable proof, or any consumer-owned path also falls back to that path.
- Never begin consumer inventory or mutation after a failed release-identity
  guard. Fetch missing tags or correct the release evidence, then rerun
  preflight.
- `dry-run` runs preflight only and performs zero consumer mutations.
- Timing state is internal, local, and mandatory. Never print its filesystem
  path or store secrets, absolute paths, command output, or review text in a
  reason. A telemetry anomaly pauses new mutation but never changes a delivery
  gate's authoritative result.

## Final report

The final report is mandatory-shaped: every item below appears in every run,
and an empty item states its emptiness explicitly (write `none`). Keep it
scannable — bullets and short lines, one point per line, no paragraph blobs.

- Per-consumer status table: one row per fleet consumer in the run —
  consumer · before-version · review-profile · result. Review profile is
  `integration-only`, `remote`, or `n/a`. Result is exactly one of
  `at-target`, `refreshed+merged`, `PR-open`, or `skipped+<reason>`. The
  before-version is the installed pack version preflight reported at run
  start, or `unknown` when preflight could not read it.
- Fleet version summary: the target version, how many consumers are at
  target after the run, and which consumers remain stale.
- Finding disposition summary: blocker owners, deferred owners, duplicate
  observation count, explicit overrides with rationale, and follow-up task
  identifiers — or `none` for each empty category.
- Timing summary: run ID and state, aggregate critical path, active wall time,
  summed stage elapsed, slowest consumer, slowest stage, reviewer/CI overlap,
  retry count, and telemetry anomalies — or `none` for every empty category.
- Follow-ups: open consumer PRs to watch, skipped consumers to revisit, and
  any anomalies — or `none`.

Example shape for a mixed run:

```
- Target: 0.12.0
- Fleet:
  - repo-a · 0.12.0 · n/a · at-target
  - repo-b · 0.10.5 · integration-only · refreshed+merged
  - repo-c · 0.11.0 · remote · PR-open (no-merge)
  - repo-d · 0.11.0 · n/a · skipped+dirty working tree
  - repo-e · unknown · n/a · skipped+no local clone
- Fleet versions: 2 of 5 at target; repo-c pending merge; repo-d and
  repo-e stale
- Findings: blockers none; deferred F-12 -> task 07-20-doc-follow-up;
  duplicates 1 (F-13 -> F-12); overrides none
- Timing: run fleet-0.12.0-20260720T153000Z completed; critical path 31m;
  active wall 29m; stage elapsed 38m; slowest consumer repo-c 16m;
  slowest stage ci-wait 18m; reviewer/CI overlap 7m; retries 0;
  anomalies none
- Follow-ups:
  1. Merge repo-c PR #12 via its housekeeping gate once review settles.
  2. Clean repo-d's working tree, then rerun with consumer=repo-d.
  3. Clone repo-e at its fleet-manifest path, then rerun with
     consumer=repo-e.
```
