---
title: The documentation path-reference check cannot express a deliberately absent path
status: done
created: 2026-08-08
branch: task/08-08-preflight-absent-path-prose
---
# The documentation path-reference check cannot express a deliberately absent path

## Goal

Give a PRD or spec a way to name a path that does not exist — because it is in
another repository, because the prose is explaining that it is missing, or
because it is a hypothetical in a worked example — without failing the review
preflight and without suppressing genuine path rot elsewhere.

`main` failed preflight for exactly this reason on 2026-08-08, so the fix is
not hypothetical. It is green today only because the two offending references
were stripped of their backticks to unblock CI — the degradation requirement 4
reverts. Re-read the first acceptance criterion with that in mind: it passes
today (verified 2026-08-19, `0 failure(s), 0 warning(s)`) and only becomes a
real test once those references are restored.

## Problem

`checkDocumentationPathReferences` resolves every eligible reference in a
documentation file against the filesystem and fails on a miss
(`scripts/sd-ai-command-pack-review-preflight.mjs:3214`):

```js
fail(`${reference.file}:${reference.line} references missing path ${reference.target}.`);
```

The design already recognizes that some references are legitimately unresolvable
and carves out an exclusion for them (`:3191-3195`):

```js
// Design/implement artifacts are forward-looking: they reference files
// the task proposes to CREATE, so a path-existence check is wrong for
// them. PRDs/specs describe current state and keep the check.
((basename === 'design.md' || basename === 'implement.md') &&
  file.startsWith('.trellis/tasks/'))
```

The premise in that comment — "PRDs/specs describe current state" — is where it
breaks. A PRD describing current state routinely needs to name a path that is
currently *absent*, and saying so is the whole point of the sentence.

### `main` was red, and which CI lane you took decided whether you saw it

```
FAIL .trellis/tasks/08-07-distributed-gitignore-python-cache/prd.md:98 references missing path scripts/check_review_readiness.sh.
FAIL .trellis/tasks/08-07-distributed-gitignore-python-cache/prd.md:132 references missing path scripts/__pycache__/y.pyc.
```

Both were fixed on 2026-08-08 by removing the backticks, purely to unblock CI;
requirement 4 below requires replacing that workaround with the real mechanism.

The routing is worth recording. Two pushes of the same branch, same defect:

| Push | Classified | Preflight | Result |
| --- | --- | --- | --- |
| `f3ea4dd6` | `mode=full` | skipped | green |
| `398ae8f0` | `mode=bookkeeping` | ran | red |

Nothing about the offending content differed. `08-07-ci-preflight-full-mode-gap`
owns that routing defect; it is named here because it is why these two failures
survived on `main` at all.

Both are false positives, and the first is self-refuting — the sentence
containing the path says the file is not here:

> The gate that fires is `scripts/check_review_readiness.sh` [absent: loadsmith's, not shipped here]
> in loadsmith, which is **not** a pack-distributed file — it does not exist
> under `templates/` in this repository.

The second is a hypothetical path from a scratch-repo experiment documented in
the PRD, never a real repository file.

This landed on `main` because full-mode CI does not run the preflight at all —
the separate defect tracked by `08-07-ci-preflight-full-mode-gap`. That gap is
why nobody saw it; this task is why it was wrong in the first place.

### The only escape hatch is repo-global

`shouldCheckDocumentationPathReference` (`:5134`) consults
`optionalCandidatePaths` (`:5138`, `:5168`), built from `optionalReferencePaths`
— a flat array of paths defaulted at `:401-422` and extendable through
`.sd-ai-command-pack/review-preflight.json` (`:436-460`).

That list is repository-wide with no file or line scope. Silencing one path for
one sentence in one PRD also silences it everywhere, including a future document
that names it because it genuinely rotted. The mechanism that exists trades a
false positive for a permanent blind spot.

There is no inline suppression: nothing in the preflight recognizes a
`preflight-ignore` comment, an attribute, or any per-reference marker.

### This document demonstrates the defect, and the only workaround is worse

The first draft of this PRD wrapped the offending path in a code span twice —
in the blockquote above and in the sentence explaining the allow-list. Both
failed, in the document whose subject is that they should not:

```
FAIL .trellis/tasks/08-08-preflight-absent-path-prose/prd.md:48 references missing path <path elided here>.
FAIL .trellis/tasks/08-08-preflight-absent-path-prose/prd.md:67 references missing path <path elided here>.
```

The workaround was to remove the backticks. Only two reference kinds are
collected — `markdown-link` (`:5087-5095`) and `code-span` (`:5120-5128`) — so
plain text inside a fenced block or a blockquote is never examined. That is why
the failure output quoted under "`main` was red" contains the same path
in full and passes, while the blockquote beneath it did not until its code span
was removed.

So the check keys on markdown formatting rather than on intent: to write about a
path that is deliberately absent, you must stop formatting it as a path. The
document gets less readable, the reference stops being clickable, and nothing
records that the un-formatting was deliberate — the next author reformats it and
the failure returns. That degradation should be reverted as part of the fix.

### Interaction with `08-06-preflight-bare-filename-references`

That task widens eligibility so bare-filename references stop being skipped.
This task is its mirror image: widening eligibility without a way to mark an
intentional absence grows the false-positive class this task is about, and this
document's own workaround depends on the current narrowness. The two must land
coherently, and whichever lands second must not re-open what the first closed.

## Requirements

1. A documentation reference can be marked as intentionally unresolvable at the
   point of use, scoped to that file — and ideally that line — rather than
   repository-wide.
2. The marker is visible in the rendered prose or adjacent to it. A reader
   should be able to tell that a path is deliberately absent without consulting
   a config file. A silent suppression that only the preflight understands is
   not acceptable.
3. `optionalReferencePaths` keeps working unchanged for what it is actually for:
   paths that are optional everywhere, such as generated artifacts.
4. The two references in `08-07-distributed-gitignore-python-cache/prd.md` are
   converted from the current backtick-stripping workaround to the new marker.
   That workaround was applied on 2026-08-08 to unblock CI (see below) and is the
   same degradation this document applies to itself; both must be reverted
   together.
5. Genuine rot still fails. Marking one reference must not weaken the check for
   any other reference to the same path in the same file or elsewhere.
6. The change lands in `templates/scripts/sd-ai-command-pack-review-preflight.mjs`
   first with the root mirror synchronized (`AGENTS.md:36`).

## Acceptance criteria

- `node scripts/sd-ai-command-pack-review-preflight.mjs` on `main` reports zero
  failures.
- A test asserts a marked reference passes and an unmarked reference to the same
  path in the same file still fails, proving requirement 5 rather than assuming
  it.
- A test asserts the marker does not leak across files.
- The two `main` references are fixed with the new marker, not by adding either
  path to `optionalReferencePaths`. Verified by asserting the config array is
  byte-identical to its pre-change value (requirement 4).
- The marker is visible where the path is, and the path still displays as a
  path. Satisfied by a static syntax check, not by a passing preflight: assert
  that no marker occurrence is followed by `(` or `[` and that no matching link
  reference definition exists, so the marker cannot be absorbed into link
  syntax and renders as literal text. A suppressed reference is a code span or
  a Markdown link by construction, so its path formatting needs no separate
  assertion. This criterion deliberately does not execute a Markdown renderer:
  the repository has no Markdown dependency and the preflight is
  dependency-free, so adding one buys less than it costs. Amended 2026-08-19
  during planning review; the original asked for a rendered-Markdown check.
- `optionalReferencePaths` behaviour is unchanged for both sources: its existing
  tests pass unmodified, *and* a new test loads a path through
  `.sd-ai-command-pack/review-preflight.json` and asserts it is still skipped.
  The existing tests cover only the built-in defaults, so they do not prove the
  config-extension half of requirement 3.
- `make check` passes, including template/root mirror verification.

## Verification evidence, 2026-08-19

- `node scripts/sd-ai-command-pack-review-preflight.mjs`: `0 failure(s), 2
  warning(s)` -- the multi-task-directory and tooling/generated-scope warnings,
  both dispositioned in the pull request body. Run after the two code spans were
  restored, so it certifies the fix rather than the workaround.
- Node harness: 15 marker cases pass, covering the marked/unmarked pair in one
  fixture, an 11-entry fail-closed array, direct `isAbsentPathMarked`
  assertions, and both code-formatted-link cases.
- Python integration: the marker does not leak across files -- a temp repo marks
  the same missing path in `docs/a.md` [absent: test fixture, never in this repository]
  and leaves it unmarked in `docs/b.md` [absent: test fixture, never in this repository],
  and the run exits 1 naming only that second file's first line;
  `optionalReferencePaths` still skips a path loaded through
  `.sd-ai-command-pack/review-preflight.json`; every `[absent: ...]` in tracked
  documentation is literal text, not link syntax.
- `optionalReferencePaths` is byte-identical to `origin/main`: `shasum` reports
  `ac9ce046f877d39af221cd4efea207981649b46d` on both sides.
- `make test`: exit 0, 81 test lanes `OK`, zero `FAILED`/`ERROR`.
- `make release-prep`: exit 0; `docs/fleet/candidate-validation.json` reports
  packVersion `0.71.34`, payload digest `sha256:e2ff6258...`, 8 consumers
  `passed`.

## Out of scope

- Changing which references are *eligible* for checking. That is
  `08-06-preflight-bare-filename-references`; this task only adds a way to opt a
  known-absent path out of a check it is correctly eligible for.
- Making CI run the preflight in full mode. That is
  `08-07-ci-preflight-full-mode-gap`.
- Auditing every existing PRD for other false positives beyond the two on `main`.
  Fix those two; file anything else the fix surfaces.

## Absorbed: 08-06-preflight-bare-filename-references (2026-08-08 consolidation)

That task covered the eligibility half of the same documentation
path-reference check: `shouldCheckDocumentationPathReference`
(`scripts/sd-ai-command-pack-review-preflight.mjs:5134`) validates a reference
only when it is one of eight enumerated top-level files or begins with one of
26 directory prefixes — a bare filename naming a tracked file (`review.py:555`,
`manifest.json`, `CHANGELOG.md`) is silently unchecked. On PR #339 preflight
passed while Copilot flagged two unqualified `review.py` references — a paid
remote round doing work the deterministic gate should do free.

Carried as an explicit **phase-2 requirement, sequenced strictly after this
task's absent-path escape hatch lands**. Sequencing puts it outside this
task's change: none of the acceptance criteria above mentions bare filenames,
and the Out of scope section already excludes eligibility. R1-R4 below moved to
`08-19-preflight-bare-filename-references`, created on 2026-08-19 once this
task's work was complete; that task carries them verbatim and names this one as
its predecessor. They stay below as the record of what was absorbed and where it
went. Recorded here rather than dropped (the tasks are complementary: escape
hatch first, widening second — widening eligibility before the escape hatch
exists would raise the false-failure rate the source's own R3 forbids):

- R1: a code-span/markdown-link bare filename matching a tracked file under an
  existing checked prefix must be validated — passing when the file exists,
  failing when it does not.
- R2: an ambiguous bare filename (matching tracked files in more than one
  directory) must not be reported as missing.
- R3: the current corpus must produce the same failure set before and after,
  except genuinely broken references.
- R4: whatever the rule declines to check stays declined for a stated,
  inspectable reason. Foreign-repository references stay out of scope
  (operator decision 2026-08-07; name the owning repository in prose instead).
