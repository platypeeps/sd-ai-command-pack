# Bare-filename documentation references are silently unchecked

## Goal

Widen the documentation path-reference check so a bare filename naming a
tracked file is validated, rather than skipped because it carries no directory
prefix.

## Background

This is phase 2 of the documentation path-reference work. It was originally
task `08-06-preflight-bare-filename-references`, absorbed into
`08-08-preflight-absent-path-prose` on 2026-08-08 as a phase-2 requirement
sequenced strictly after that task's absent-path escape hatch, and restored
here as its own task when 08-08's work completed (that task's `implement.md`
step 6 owns this creation). The requirements below are carried verbatim from
the absorbed task.

Predecessor: `08-08-preflight-absent-path-prose`, which shipped the
`[absent: <reason>]` marker. The sequencing is the point: widening eligibility
without a way to mark an intentional absence grows the false-positive class,
which the source task's own R3 forbids. That marker now exists, so this task is
unblocked.

`shouldCheckDocumentationPathReference`
(`scripts/sd-ai-command-pack-review-preflight.mjs:5134`) validates a reference
only when it is one of eight enumerated top-level files or begins with one of
26 directory prefixes -- a bare filename naming a tracked file (`review.py:555`,
`manifest.json`, `CHANGELOG.md`) is silently unchecked. On PR #339 preflight
passed while Copilot flagged two unqualified `review.py` references -- a paid
remote round doing work the deterministic gate should do free.

## Requirements

- R1: a code-span/markdown-link bare filename matching a tracked file under an
  existing checked prefix must be validated -- passing when the file exists,
  failing when it does not.
- R2: an ambiguous bare filename (matching tracked files in more than one
  directory) must not be reported as missing.
- R3: the current corpus must produce the same failure set before and after,
  except genuinely broken references.
- R4: whatever the rule declines to check stays declined for a stated,
  inspectable reason. Foreign-repository references stay out of scope
  (operator decision 2026-08-07; name the owning repository in prose instead).

## Acceptance Criteria

- [ ] A test asserts an existing bare filename under a checked prefix passes
      and a non-existent one fails (R1).
- [ ] A test asserts an ambiguous bare filename is not reported as missing
      (R2).
- [ ] `node scripts/sd-ai-command-pack-review-preflight.mjs` over this
      repository produces the same failure set as before the change, except
      references that are genuinely broken. Any newly failing reference is
      either fixed or marked with `[absent: <reason>]` (R3).
- [ ] The declined classes are enumerated in the code with a stated reason,
      and foreign-repository references remain declined (R4).
- [ ] `make check` passes, including template/root mirror verification.

## Out of scope

- The absent-path marker itself, which `08-08-preflight-absent-path-prose`
  delivered.
- Making CI run the preflight in full mode; that is
  `08-07-ci-preflight-full-mode-gap`.
