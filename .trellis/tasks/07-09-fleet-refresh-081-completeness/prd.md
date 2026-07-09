# Fleet refresh to 0.8.1 with install completeness verification

## Goal

Roll 0.8.1 out to every consumer repo, and make the rollout self-checking
so partial installs cannot pass silently again. This refresh also repairs
the two consumers whose 0.7.0 install is already broken.

## Problem

The 2026-07-09 cross-repo sweep found the whole fleet six payload versions
behind (provenance 0.7.0 vs pack 0.8.1), with zero open refresh PRs and no
rollout mechanism — the `07-06-close-fleet-refresh-loop` task reconciled a
ledger, it did not build a loop, and the fleet re-opened within hours.

Two consumers have broken 0.7.0 installs the audit cannot detect:
- **hoa-manager** (rollout PR #97) and **rwbp-coordinator** (PR #98) each
  received every sd-work-backlog surface *except*
  `.claude/commands/sd/work-backlog.md` — absent from disk, receipts, and
  provenance. The audit passes because it only verifies provenance-vouched
  files, and provenance was written by the same faulty run. A 0.8.1
  `--force` refresh repairs both as a side effect.

The refreshed inventory is also wrong: the archived close-loop PRD lists
five consumers and dismisses the sixth as a misreading — but **hoa-manager
is a real sixth consumer** (rollout PRs #86/#87/#97, provenance 0.7.0),
and it is one of the two broken repos. `rwbp-coordinator` additionally
carries the `.cursor` platform (12 extra targets), so the fleet is not
homogeneous.

Rollout hygiene has failed twice: anomaly-metric-creator merged #226 **and**
#227 (the latter an empty commit whose message falsely claims a 12-file
refresh), and mezmo_benchmark merged #336 **and** #337 — duplicate PRs per
version with no dedupe.

The 0.7.0→0.8.1 gap contains two real integrity fixes every consumer lacks:
0.7.1 preflight symlink hardening (a silent review-gate bypass) and 0.8.1
recorder retry-safety (journal duplication) — note the recorder fix depends
on `07-09-recorder-untracked-workspace` to be effective in local-only repos.

## Requirements

- R1: A checked-in fleet manifest enumerates every real consumer with its
  GitHub slug and enabled platform set: anomaly-metric-creator, loadsmith,
  hoa-manager, rwbp-coordinator (+`.cursor`), rwbp-website,
  answerbook/mezmo_benchmark. Stale local clones
  (`green-button-manager` = loadsmith, `trellis-review-pr-pack` = the pack)
  are explicitly excluded — see `07-09-shell-hook-hardening` note / handled
  by operator cleanup.
- R2: A rollout preflight checks each consumer's current
  `.sd-ai-command-pack/provenance.json` version before opening a refresh
  PR, and skips (or no-ops) repos already at target — preventing the
  duplicate-PR / empty-commit pattern.
- R3: A post-install completeness check compares the installed target set
  against the manifest's expected targets for the repo's enabled platforms
  and fails when any expected target is missing — independent of provenance
  (which the faulty run itself wrote). This is the audit gap that let #97/#98
  pass; pairs with `07-09-drift-gate-absence-blindness` R-audit.
- R4: Execute the 0.8.1 refresh across all six consumers via PRs; confirm
  each merges green and each post-merge provenance reads 0.8.1 with the
  complete target set (hoa-manager and rwbp-coordinator regain
  `.claude/commands/sd/work-backlog.md`).

## Acceptance Criteria

- [ ] Fleet manifest committed and referenced by the rollout runbook /
      tooling.
- [ ] Rollout preflight demonstrably skips an at-target repo (no empty PR).
- [ ] Completeness check fails on a synthesized missing-target install and
      passes on a complete one.
- [ ] All six consumers at provenance 0.8.1, audits pass, and the two
      previously-broken repos have the work-backlog Claude command present
      in git + receipts + provenance.
- [ ] `07-06-close-fleet-refresh-loop` archived PRD corrected (or a
      superseding note added) to include hoa-manager.

## Non-goals

- Fully automated unattended rollout (scheduled cron opening PRs across
  orgs) — a reviewed, operator-triggered rollout with a version pre-check
  is sufficient for now; full automation can follow if cadence demands it.
- Deleting the stale local clones (operator action, noted for safety).
