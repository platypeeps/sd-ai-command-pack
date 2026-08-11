# Make release-prep reach a changed candidate validator

Child 2 of `08-09-thin-migration`, contract C-F. Pack-internal.

> **Scope narrowed 2026-08-11, after planning review.** This task originally
> carried both halves of contract C-F: making release-prep *reach* the
> validator, and rescoping the validator to the *thin shape*. Three review
> rounds (host ×2, this repository's Codex lane ×1) found four blocking
> concerns against the thin-shape half — it mutates the pack's own fleet
> registry, defeats its own clean-tree precondition, breaks on already-thin
> checkouts, and needs a release-gate policy decision. Operator decision:
> ship the mechanism, hand the shape to a new child. The full concern ledger
> is in `design.md` D7a; the deferred half is
> `08-11-thin-candidate-loop-shape`.
>
> The directory slug still says `candidate-loop-rescope` because it predates
> the split and `task.py` has no rename.

## Problem

The full-fleet candidate validator installs a payload into disposable consumer
checkouts and runs each consumer's repo-owned `candidateChecks`. It is
`validate_consumer` in
`scripts/sd-ai-command-pack-fleet-candidate-check.py`, invoked as
`CANDIDATE_CHECK` from `.github/scripts/prepare-release.py:342`.
(`scripts/sd-ai-command-pack-fleet-preflight.py` only reports local refresh
status and is **not** this loop.)

**`prepare-release.py:338` skips the validator entirely** when the candidate
ledger is already current, so a green `make release-prep` does not by itself
prove the loop ran. That is worse than a timing hazard, because the ledger's
currency cannot see the validator:
`scripts/sd-ai-command-pack-fleet-candidate-check.py` has **no `manifest.json`
row and no `templates/` twin** — measured 2026-08-11, zero manifest rows match
it — and the payload digest hashes only manifest-declared *sources*
(`fleet_lib.py:717`, reading each row's `source` field, collected at
`fleet_lib.py:723`). So rewriting the
validator moves neither the payload digest nor the fleet digest, the ledger
stays current, and release-prep returns without ever running the new code.
`tests/test_release_prep.py:90` tests that skip explicitly.

Every future change to this validator — including the thin-shape rescope this
task was split away from — is unverifiable until that is fixed. Knowing about
the skip is not a fix; this task ships a mechanism.

### What is *not* uncovered

`scripts/sd_ai_command_pack_fleet_lib.py` looks like a second blind spot and is
not one. Its manifest row is
`source: templates/scripts/sd_ai_command_pack_fleet_lib.py`,
`target: scripts/sd_ai_command_pack_fleet_lib.py`, so the authoritative
template *is* payload-declared and editing it already moves `payloadDigest`.
The root copy is a mirror (`CONTRIBUTING.md:143`) that `make sync` rewrites
from the template. Planning review got this backwards in both directions before
settling it; it is recorded here so the next reader does not repeat the trip.

## Requirements

1. **Ship a mechanism that makes a changed validator run.** Bind a
   candidate-validator digest into the candidate ledger, so editing the
   validator invalidates it. `design.md` D1 records why this was chosen over a
   force-validation flag.
2. The mechanism must be correct at every call site that validates a ledger,
   including the one that validates a ledger **at a historical commit**.
3. The documented skip survives for a genuinely unchanged candidate. A no-op
   release-prep that stops being fast is a release-prep somebody disables.

## Acceptance criteria

- [x] **Current ledger plus a changed validator source still executes
      validation.** Edit the validator, leave the ledger current, run
      `make release-prep`, and observe the validator run. Failing this means
      the mechanism shipped code that release-prep never reaches.

      Measured. From a converged tree, appending one comment line to
      `scripts/sd-ai-command-pack-fleet-candidate-check.py` moved exactly one
      ledger field — `validatorDigest is 'sha256:16be194d…'; expected
      'sha256:9cc47732…'` — with `packVersion`, `payloadDigest`, and
      `fleetManifestDigest` all unchanged, which is precisely why schema 2 read
      such a ledger as current. Release-prep then printed
      `release prep: validate exact candidate across the full fleet` and ran all
      eight consumers, rather than the skip message. The probe was reverted and
      the revert verified twice: the line is gone, and the expected digest
      returned bit-identically to `sha256:16be194d…`.
- [x] The skip still holds when nothing changed: a second consecutive
      `make release-prep` on an unchanged clean tree reports the ledger current
      and does not rerun the fleet validation.

      Measured: `release prep: candidate ledger is current; skipping fleet
      validation`, exit 0, with no fleet lines in the output.
- [x] Every `validate_candidate_ledger` call site supplies a digest computed
      from the same tree as the ledger it is checking — working tree for the
      two working-tree sites, commit-scoped blobs for
      `verify_candidate_ledger_at_commit`. Proven by a test that fails when the
      historical site is fed the working tree.

      `test_commit_digest_reads_the_commit_not_the_working_tree` commits a
      validator, edits it in the working tree, and asserts the commit-scoped
      digest equals the committed value and differs from the working tree's.
- [x] A missing validator source at a historical commit fails closed with a
      named error, never a fallback to the working tree.

      `test_commit_digest_fails_closed_on_a_source_absent_at_the_commit`. The
      loader is wrapped so the diagnostic names the validator; reusing the
      payload loader unwrapped reported a missing *manifest* source, sending a
      reader to look for a row that has never existed.
- [x] Mutation testing over the digest comparison shows the assertion has
      teeth: a mutant that accepts differing digests is killed.
      (`PYTHONDONTWRITEBYTECODE=1`.)

      Three mutants, all killed: the `validatorDigest` comparison row removed
      (7 failures), the digest computed over `b""` instead of source content
      (7 failures), and `CANDIDATE_LEDGER_SCHEMA_VERSION` reverted to 2
      (5 failures). The mirror was restored byte-identical afterward.
- [x] `make check` passes. `make check exit=0`; `Review preflight: 0
      failure(s), 3 warning(s)`.

      The first run failed on two real defects — `08-11-thin-candidate-loop-shape`
      and `08-11-codex-lane-removal-citations` both carried an empty
      `task.json` description, which `task.py create` leaves blank. Both now
      describe their scope.

      The three surviving warnings are dispositioned, not suppressed:
      (1) the diff adds **path-filesystem** and **normalization-evidence**
      boundary risk. Covered: in-root reads, a missing source, a
      traversal/symlink escape, a symlinked root (the matrix's "equivalent raw
      and normalized values" row, `/var` vs `/private/var`), and
      absent-at-commit evidence. Not covered: oversized-file and TOCTOU
      replacement — `filesystem_payload_digest`, which this mirrors, guards
      neither, and the source is a repo-tracked file in the pack's own
      checkout; guarding one loader and not its sibling would be the
      inconsistency, not the fix.
      (2) four Trellis task directories change — this task, the split-out
      child, the parent's map, and an iteration-1 follow-up. They are the one
      outcome of the split decision.
      (3) the PR body needs a tooling/generated scope section.

## Non-goals

- The thin-shape rescope of `validate_consumer`, in any part. It is
  `08-11-thin-candidate-loop-shape` and owns concerns C-1 through C-4.
- Any consumer repository mutation. Children 3–5 own that and are blocked on
  explicit per-cohort user authorization (`08-09-thin-migration/prd.md:91`).
