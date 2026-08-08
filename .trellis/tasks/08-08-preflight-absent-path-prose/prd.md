# The documentation path-reference check cannot express a deliberately absent path

## Goal

Give a PRD or spec a way to name a path that does not exist — because it is in
another repository, because the prose is explaining that it is missing, or
because it is a hypothetical in a worked example — without failing the review
preflight and without suppressing genuine path rot elsewhere.

`main` fails preflight today for exactly this reason, so the fix is not
hypothetical.

## Problem

`checkDocumentationPathReferences` resolves every eligible reference in a
documentation file against the filesystem and fails on a miss
(`scripts/sd-ai-command-pack-review-preflight.mjs:2929-2930`):

```js
fail(`${reference.file}:${reference.line} references missing path ${reference.target}.`);
```

The design already recognizes that some references are legitimately unresolvable
and carves out an exclusion for them (`:2905-2911`):

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

### `main` is red right now

```
FAIL .trellis/tasks/08-07-distributed-gitignore-python-cache/prd.md:98 references missing path scripts/check_review_readiness.sh.
FAIL .trellis/tasks/08-07-distributed-gitignore-python-cache/prd.md:132 references missing path scripts/__pycache__/y.pyc.
```

Both are false positives, and the first is self-refuting — the sentence
containing the path says the file is not here:

> The gate that fires is scripts/check_review_readiness.sh in loadsmith, which
> is **not** a pack-distributed file — it does not exist under `templates/` in
> this repository.

(The original wraps that path in a code span. This quotation deliberately does
not — see below.)

The second is a hypothetical path from a scratch-repo experiment documented in
the PRD, never a real repository file.

This landed on `main` because full-mode CI does not run the preflight at all —
the separate defect tracked by `08-07-ci-preflight-full-mode-gap`. That gap is
why nobody saw it; this task is why it was wrong in the first place.

### The only escape hatch is repo-global

`shouldCheckDocumentationPathReference` (`:4443`) consults
`optionalCandidatePaths` (`:4447`, `:4477`), built from `optionalReferencePaths`
— a flat array of paths defaulted at `:313-334` and extendable through
`.sd-ai-command-pack/review-preflight.json` (`:365-375`).

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
collected — `markdown-link` (`:4417-4421`) and `code-span` (`:4430-4434`) — so
plain text inside a fenced block or a blockquote is never examined. That is why
the failure output quoted under "`main` is red right now" contains the same path
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
4. The two live `main` failures are fixed using the new mechanism, and `main`
   returns to a clean preflight.
5. Genuine rot still fails. Marking one reference must not weaken the check for
   any other reference to the same path in the same file or elsewhere.
6. The change lands in `templates/scripts/sd-ai-command-pack-review-preflight.mjs`
   first with the root mirror synchronized (`AGENTS.md:29-33`).

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
- A rendered-Markdown check: the marked reference still displays the path as a
  path. A marker that only the preflight can see fails requirement 2, so this
  criterion is not satisfied by a passing preflight alone.
- `optionalReferencePaths` behaviour is unchanged for both sources: its existing
  tests pass unmodified, *and* a new test loads a path through
  `.sd-ai-command-pack/review-preflight.json` and asserts it is still skipped.
  The existing tests cover only the built-in defaults, so they do not prove the
  config-extension half of requirement 3.
- `make check` passes, including template/root mirror verification.

## Out of scope

- Changing which references are *eligible* for checking. That is
  `08-06-preflight-bare-filename-references`; this task only adds a way to opt a
  known-absent path out of a check it is correctly eligible for.
- Making CI run the preflight in full mode. That is
  `08-07-ci-preflight-full-mode-gap`.
- Auditing every existing PRD for other false positives beyond the two on `main`.
  Fix those two; file anything else the fix surfaces.
