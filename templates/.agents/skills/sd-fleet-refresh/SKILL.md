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

Arguments arrive as free text with the invocation, as `key=value` pairs and
bare flags. Unknown argument names are an error, not a silent skip: stop and
report them before running preflight. This skill reads no environment
variables; every tuning knob is an argument.

- `consumer=<a,b>` — comma-separated fleet consumer names. Limit the run to
  those consumers. Pass each name to preflight via `--consumer`; preflight
  rejects names that are not in the fleet manifest. Without `consumer=`,
  the run covers every consumer in the fleet manifest.
- `no-merge` — bare flag. Stop every consumer at PR-open: open and watch the
  consumer PR, but do not merge it.
- `dry-run` — bare flag. Run preflight and emit the report only; perform no
  consumer mutations.

## Workflow

1. Preflight first. From the pack checkout, run:

   ```bash
   bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
     scripts/sd-ai-command-pack-fleet-preflight.py
   ```

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
      default branch.
   3. Install the pack release per `docs/FLEET_ROLLOUT.md`: run the
      preflight-printed `python3 install.py <repo> --force --platform ...`
      command from the pack checkout, then the printed install-audit
      command with its `--expected-platform` set.
   4. Run the consumer's full-check gate — its `make full-check` or the
      consumer-documented equivalent. If the gate fails, do not open a PR:
      record the consumer as skipped with the failure summary, leave the
      local branch for inspection, and continue to the next consumer.
   5. Commit the refreshed files, push the branch, and open the consumer
      PR.
   6. Watch the PR to settled: required checks complete and review state
      final.
   7. Merge via the consumer's housekeeping gate: green, comment-clean,
      mergeable, heads identical. With `no-merge`, leave the PR open and
      record the consumer as PR-open.
   8. Confirm post-merge provenance reads the target version and the
      install audit passes, per the rollout doc. Finish the consumer's
      housekeeping cleanup — default branch checked out, refresh branch
      deleted, refs pruned — then move to the next consumer.
4. Aggregate the per-consumer outcomes into the fleet status table and the
   fleet version summary for the final report.

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
- `dry-run` runs preflight only and performs zero consumer mutations.

## Final report

The final report is mandatory-shaped: every item below appears in every run,
and an empty item states its emptiness explicitly (write `none`). Keep it
scannable — bullets and short lines, one point per line, no paragraph blobs.

- Per-consumer status table: one row per fleet consumer in the run —
  consumer · before-version · result. Result is exactly one of `at-target`,
  `refreshed+merged`, `PR-open`, or `skipped+<reason>`. The before-version
  is the installed pack version preflight reported at run start, or
  `unknown` when preflight could not read it.
- Fleet version summary: the target version, how many consumers are at
  target after the run, and which consumers remain stale.
- Follow-ups: open consumer PRs to watch, skipped consumers to revisit, and
  any anomalies — or `none`.

Example shape for a mixed run:

```
- Target: 0.12.0
- Fleet:
  - repo-a · 0.12.0 · at-target
  - repo-b · 0.10.5 · refreshed+merged
  - repo-c · 0.11.0 · PR-open (no-merge)
  - repo-d · 0.11.0 · skipped+dirty working tree
  - repo-e · unknown · skipped+no local clone
- Fleet versions: 2 of 5 at target; repo-c pending merge; repo-d and
  repo-e stale
- Follow-ups:
  1. Merge repo-c PR #12 via its housekeeping gate once review settles.
  2. Clean repo-d's working tree, then rerun with consumer=repo-d.
  3. Clone repo-e at its fleet-manifest path, then rerun with
     consumer=repo-e.
```
