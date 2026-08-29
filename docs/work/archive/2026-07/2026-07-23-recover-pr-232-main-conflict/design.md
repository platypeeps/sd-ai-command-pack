# Recover PR 232 After Main Conflict Design

## Overview

Recover the existing PR in place by merging current `origin/main` into its
feature branch, resolving only the overlapping release and append-only journal
surfaces, regenerating derived evidence, and then re-entering the normal
exact-head review and housekeeping lifecycle.

## Proposal

Use a non-rewriting merge commit from `origin/main`. The branch already has a
published and reviewed history, so a merge avoids force-push authority and
makes the incorporated upstream release explicit.

Resolve conflicts by ownership:

- Release version and generated catalogs: retain `0.33.0`, because it is the
  next minor release containing both the merged `0.32.2` fix and the eligibility
  evaluator.
- Changelog: retain both entries, with `0.33.0` before `0.32.2`.
- Review-preflight code/tests/spec: accept upstream malformed-JSONL changes and
  combine their spec paragraphs with the eligibility contract already in the
  branch.
- Journal: preserve upstream Session 199 byte-for-byte; append the branch's
  centralization record as Session 200 and regenerate index totals/order.
- Candidate ledger and installed metadata: discard stale competing receipts and
  regenerate from the combined canonical `0.33.0` payload.

## Boundaries And Non-Goals

The merge does not redesign the evaluator, dependency workflow, review
preflight, or task lifecycle. It does not use rebase, force-push, direct GitHub
merge calls, or manual edits to generated mirrors when a repository generator
owns them.

The recovery task adds a second directly-related Trellis task surface to PR
#232. This is intentional lifecycle evidence, not unrelated product scope, and
must be called out in first-review advisory disposition.

## Affected Files

- Release/generated conflicts: `manifest.json`, `.sd-ai-command-pack/manifest.json`,
  `CHANGELOG.md`, both command catalogs, provenance, and
  `docs/fleet/candidate-validation.json`.
- Combined contract: `.trellis/spec/backend/quality-guidelines.md`.
- Append-only history: `.trellis/workspace/sdelmas/journal-4.md` and sibling
  `index.md`.
- Recovery bookkeeping: this task directory and
  `.trellis/tasks/07-22-streamline-sd-skill-workflows/task.json`.
- Upstream clean merges: review-preflight template/root twins and focused tests.

## Data And Command Contracts

- Git integration: `git merge --no-ff origin/main`; no history rewriting.
- Pack version: one canonical `0.33.0` manifest version.
- Journal numbering after merge: upstream malformed-context session `199`, PR
  eligibility session `200`; recovery finish-work appends the next available
  session.
- Candidate evidence: schema-versioned ledger generated only by the canonical
  no-filter fleet candidate command against the combined working payload.
- Merge mutation: still exclusively
  `scripts/sd-ai-command-pack-housekeeping.sh --finish-work-head <exact-oid>`.

## Risks And Edge Cases

- A new `origin/main` commit can land during recovery. Fetch immediately before
  publication and repeat integration if ancestry is no longer current.
- Hand-resolving generated files can produce internally consistent-looking but
  stale hashes. Always rerun repository generators and candidate validation.
- Keeping either competing Session 199 would silently erase history. Preserve
  upstream numbering and append the unmerged branch session under the next
  number.
- Finish-work creates a newer head than the implementation review. The current
  workflow requires fresh CI for that head and leaves final eligibility to
  housekeeping; router-issued exact-head review receipts remain a separate
  planned task.

## Validation

Run focused review-preflight, eligibility, housekeeping, generated-parity, and
release-gate tests; verify journal/index ordering directly; run `make sync`, the
canonical eight-consumer candidate validator, and `make check`; then require
fresh remote review, green CI, and complete GraphQL review-thread evidence.

## Rollback

Before publishing, abort the merge if resolutions cannot be proven and return
to the pre-merge commit. After publishing, use forward corrective commits only;
do not rewrite the reviewed remote branch.
