# Name the contract when `--bookkeeping-evidence` input is unusable

## Origin

Issue #490, filed 2026-08-16 from `platypeeps/sd-github-review` while shipping
its PR #93, against pack 0.71.26.

## Premise correction — verify before acting

The issue reports two symptoms. Reading the current source on 2026-08-25 at
`main`, **one of them no longer reproduces as quoted**:

- Quoted: a Markdown file yields a bare `Expecting value: line 1 column 1
  (char 0)`. Today `_read_json`
  (`scripts/sd-ai-command-pack-review-local.py:388-401`) already attributes it:
  `cannot read bookkeeping evidence <path>: Expecting value: ...`. That
  attribution has been present since the lane was introduced
  (`4c872c34`, 2026-07-24), i.e. *before* the observed 0.71.26 — so the bare
  form the issue quotes most likely reached the operator through a relaying
  surface that printed only the exception text, not from this function.
  **Re-verify which surface produced the quoted string before changing it**;
  if it is a relay, the fix belongs there and this task should say so.
- Quoted: `[Errno 2] No such file or directory: ''`. This still reproduces.
  `main` resolves the flag with `Path(args.bookkeeping_evidence).resolve(strict=True)`
  (`:2646-2649`); the `OSError` is caught by the blanket
  `except (OSError, ReviewInputError)` and stringified verbatim, so the message
  names neither the flag nor the fact that a path was expected.

What survives both corrections is the issue's actual complaint, unaffected by
either: **no failure on this flag names the shape it wants.** The required
receipt is discoverable only by reading `_validate_bookkeeping_evidence`
(`:833-847`) — a JSON object with exactly `schemaVersion: 1`, `base`, `head`,
`contentDigest`, `classification: "bookkeeping-successor"`, whose `base`/`head`/
`contentDigest` equal the target under review.

## Why it matters

The current messages are silent about the one thing an operator needs, and their
shape invites the wrong fix. An agent that reverse-engineers the schema from the
source is one step from hand-authoring a receipt to satisfy the check — which is
manufacturing verification evidence, precisely what the classification exists to
prevent. A message that names the contract pushes toward the honest path; in the
filed case `--successor low-risk` was the accurate classification and was the one
finally used.

## Requirements

- R1: The missing-file case is attributed to the flag: name `--bookkeeping-evidence`,
  the path as given, and that a JSON receipt file is expected. Do not widen the
  blanket `except` — resolve the flag inside the attributed path instead.
- R2: Every rejection from `_validate_bookkeeping_evidence` names the required
  shape: the five keys, the exact `schemaVersion` and `classification` values,
  and that `base`/`head`/`contentDigest` must match the reviewed target. The
  mismatch case additionally says *which* field disagreed, without echoing
  attacker-controlled content unbounded (`safe_text` limits already used in this
  file apply).
- R3: The message states how a receipt is legitimately produced, or points at
  the document that does. Closing that loop is the part that redirects an
  operator away from hand-authoring one.
- R4: No message text change alters an outcome classification, an exit code, or
  the receipt schema itself. This task is diagnostics only.

## Acceptance Criteria

- [ ] A test passing a nonexistent path asserts the message contains the flag
      name and the path; it fails on current `main`.
- [ ] A test passing a non-JSON file asserts the message names the flag and the
      required keys.
- [ ] A test per rejection branch in `_validate_bookkeeping_evidence` (bad
      `schemaVersion`, missing/extra keys, wrong `classification`, target
      mismatch) asserts the shape is named and, for mismatch, the disagreeing
      field.
- [ ] Exit codes and JSON report structure for each branch are unchanged,
      proven by asserting them in the same tests.
- [ ] The relay question in *Premise correction* is answered in writing — either
      "no relay, the quoted bare form is stale" or the relaying surface is named
      and fixed.
- [ ] Changelog + version; fleet rollout via normal refresh.

## Field evidence from PR #551 (2026-08-25)

Hit while driving PR #551 through `sd-ship until=merge` at 0.71.52. Two things
this task should absorb, both about the *same* validator.

**The unnamed-fields message is worse than it reads.** Passing the wrong
artifact yields exactly:

```
bookkeeping evidence has unsupported or missing fields
```

No field names, no indication of which side was wrong. The caller cannot tell
a missing key from an extra one, and `set(value) != required | {"schemaVersion"}`
treats both identically. The acceptance criterion above already covers naming
the shape; this is a live instance of why it matters.

**The wrong artifact is the one the docs hand you.** `sd-ship` Stage 2b says
to retain the finish-work flow's "exact-head schema-version-1 bookkeeping
receipt" and pass it on. That receipt is `final-bundle --mode completion`
output, `kind: "trellis-bookkeeping-validation"`. The flag wants something
else entirely:

```json
{"schemaVersion": 1, "classification": "bookkeeping-successor",
 "base": "<merge-base OID>", "head": "<OID>", "contentDigest": "<sha256>"}
```

Two names collide on the word "bookkeeping" and the docs point at the wrong
one. Worth deciding whether the fix is a clearer message, a renamed flag, or
a corrected `sd-ship` instruction — likely the doc, since the descriptor is
the narrower and more checkable of the two.

**`contentDigest` is not obtainable from documentation.** `base` is the
resolved merge-base OID, not the PR base, and `contentDigest` is a sha256 over
a canonicalized diff. The only way found to obtain either was an undocumented
probe:

```bash
sd-ai-command-pack-review-local.py --repo . --scope pr \
  --base origin/main --head <head> --local auto --successor first \
  --attempt-id probe --plan-only --no-reuse --json
```

A required input reachable only through an unadvertised flag is a contract
that cannot be satisfied from the docs. Consider deriving the descriptor
inside the review script, which already computes the target it must match.

## Notes

- Lightweight; PRD-only is appropriate. Diagnostics text plus tests, no contract
  change.
