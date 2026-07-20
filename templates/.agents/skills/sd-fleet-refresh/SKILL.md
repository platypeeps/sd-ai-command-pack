---
name: sd-fleet-refresh
description: Use when a pack release must roll across the consumer fleet — run the fleet preflight, then refresh each stale consumer sequentially (branch, install, full-check, PR, watch, gated merge) per docs/FLEET_ROLLOUT.md.
---

# SD Fleet Refresh

Run this project-local skill for `sd-fleet-refresh` and `/sd:fleet-refresh`
style work, from the sd-ai-command-pack source checkout. It rolls the current
pack release across the known consumer repositories, one consumer at a time.

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

## Workflow

1. Preflight first. The matching local `v<manifest-version>` tag must already
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
   reason.
2. With `dry-run`: emit the final report from the preflight results and
   stop here. Zero consumer mutations.
3. Refresh stale consumers strictly sequentially in the preflight's explicit
   priority order, one consumer at a time. Coordinator, loadsmith, and HOA are
   the fast canaries; AMC runs last. Do not reorder from incidental local path
   or manifest editing order.
   Start the next consumer only after the previous one resolves as
   refreshed+merged, PR-open under `no-merge`, or skipped:
   1. Verify the consumer checkout has a clean working tree. If it is
      dirty, skip this consumer and record the reason. Never stash, reset,
      or clean it, and never install into it.
   2. Create a refresh branch in the consumer checkout from its current
      default branch. Record the exact full base commit before installation;
      integration-only classification is bound to that commit, not a moving
      branch name.
   3. Install the pack release per `docs/FLEET_ROLLOUT.md`: run the
      preflight-printed `python3 install.py <repo> --force --platform ...`
      command from the pack checkout, then the printed install-audit
      command with its `--expected-platform` set.
   4. Run the consumer's full-check gate — its `make full-check` or the
      consumer-documented equivalent. If the gate fails, do not open a PR:
      record the consumer as skipped with the failure summary, leave the
      local branch for inspection, and continue to the next consumer.
   5. Commit the refreshed files. Before pushing, run the source-side
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
   6. Push the branch and open the consumer PR. Resolve `sd-review-pr` and run
      it as the sole review owner. For an eligible auto-classified branch,
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
   7. Run `sd-watch-pr` with its internal `no-merge` handoff so required
      checks and review state settle without duplicating housekeeping.
   8. Merge via the consumer's housekeeping gate: green, comment-clean,
      mergeable, heads identical. With `no-merge`, leave the PR open and
      record the consumer as PR-open instead of invoking housekeeping.
   9. Confirm post-merge provenance reads the target version and the
      install audit passes, per the rollout doc. Finish the consumer's
      housekeeping cleanup — default branch checked out, refresh branch
      deleted, refs pruned — then move to the next consumer.
4. Aggregate the per-consumer outcomes into the fleet status table and the
   fleet version summary for the final report.

## Corrective campaign

When any rollout step surfaces a verified pack-owned correctness, security,
install/audit, or compatibility blocker:

1. Immediately pause consumer mutation before selecting or preparing another
   release. Keep the original fleet task available to resume later.
2. Reuse or create one source-owned Trellis corrective task. Record every
   verified finding in a single ledger with this shape:

   `ID | Contract family | Evidence | Severity | Disposition | Fix | Regression`

   Exact duplicates reuse the owning row instead of creating another task or
   release trigger.
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
- Refresh one consumer at a time. Never run parallel consumer refreshes and
  never interleave consumer branches.
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
- Stop the rollout for correctness, security, install/audit, or compatibility
  defects in the released pack. Record low-risk hardening, style, or unrelated
  consumer findings as follow-up work instead of forcing a patch release.
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
- Follow-ups:
  1. Merge repo-c PR #12 via its housekeeping gate once review settles.
  2. Clean repo-d's working tree, then rerun with consumer=repo-d.
  3. Clone repo-e at its fleet-manifest path, then rerun with
     consumer=repo-e.
```
