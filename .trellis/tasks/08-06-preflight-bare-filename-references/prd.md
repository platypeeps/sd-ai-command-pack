# Preflight does not validate bare-filename path references in documentation

## Goal

Make the review preflight's documentation path-reference check catch a
reference that names a repository file by bare filename but resolves to no
path — the class of reference it currently skips entirely — without turning
ordinary prose that happens to contain a dot into a failure.

## Problem

`scripts/sd-ai-command-pack-review-preflight.mjs:4443`,
`shouldCheckDocumentationPathReference`, decides whether a documentation
reference is eligible for validation. After the exclusion filters, eligibility
comes down to two positive tests:

```js
if (topLevelFiles.has(normalized)) {
  return true;
}

return referencePrefixes.some((prefix) => normalized.startsWith(prefix));
```

A reference is therefore checked only when it is one of eight enumerated
top-level files, or begins with one of the 26 `referencePrefixes` directory
prefixes. Everything else is silently unchecked — including a bare filename
that unambiguously names a tracked file living under a checked prefix.

Observed eligibility, verified by calling the function directly:

| Reference | Eligible | Why |
|---|---|---|
| `scripts/sd-ai-command-pack-review.py` | yes | matches the `scripts/` prefix |
| `review.py` | no | no prefix, not a top-level file |
| `review.py:555` | no | same; the line suffix is irrelevant |
| `manifest.json` | no | not in `topLevelReferenceFiles` |
| `CHANGELOG.md` | no | not in `topLevelReferenceFiles` |

`topLevelReferenceFiles` enumerates eight names — two dotfiles (dockerignore,
gitignore), two agent instruction files (AGENTS, CLAUDE), a Dockerfile, both npm
package manifests, and a README — so two files this repository edits on nearly
every release, `manifest.json` and `CHANGELOG.md`, sit outside the checked set.

That enumeration is also portable across repositories rather than true of any
one: three of its eight names do not exist here. Naming them in code spans in
this very document makes the check fail, which is the same eligibility rule
working correctly from the other direction.

### Why this matters

The check exists so a documentation reference cannot rot into a path that no
longer exists. A bare filename is the reference form most likely to rot: it
carries no directory, so a file move leaves it looking correct. It is also the
form a reviewer most often has to correct by hand.

On PR #339 the PRD referenced `review.py:555` and `review.py:1706`. Preflight
reported 0 failures and 0 warnings. Copilot then flagged both as needing
qualification, and both were corrected to
`scripts/sd-ai-command-pack-review.py` in `a407f75f` — the line numbers were
right, only the paths were unqualified. A paid remote review round did work the
deterministic gate is meant to do for free.

### Why this is not simply "add more prefixes"

Widening `topLevelReferenceFiles` fixes the two named files and nothing else.
The general shape — a bare filename naming a real file under a checked prefix —
needs an eligibility rule that can resolve the name, not a longer enumeration.
And any such rule inherits the reason the enumeration exists in the first
place: prose contains dotted tokens that are not paths at all (`0.64.21`,
`e.g.`, a sentence-ending `foo.` inside a code span), and each one wrongly
declared eligible becomes a false failure in a blocking gate.

## Requirements

### Functional

- R1: a code-span or markdown-link reference that is a bare filename matching a
  tracked file under an existing checked prefix must be validated — passing when
  the file exists, failing when it does not.
- R2: an ambiguous bare filename — one matching tracked files in more than one
  directory — must not be reported as missing. It resolves to something real;
  the check has no basis to pick one.
- R3: the rule must not raise the false-failure rate on existing documentation.
  The current corpus must produce the same failure set before and after, except
  for references that are genuinely broken.
- R4: whatever the rule declines to check must stay declined for a stated
  reason, not by accident. The eligibility decision needs to be inspectable.

### Non-functional

- N1: eligibility is evaluated per reference across all scanned documentation.
  Any repository index the rule needs must be built once per run, not per
  reference.

## Constraints

- The `scripts/` and `templates/scripts/` copies of the preflight must stay
  byte-identical; both change together.
- Do not weaken any existing eligible-reference failure into a warning to make
  room for the new class.
- The gate is blocking. A rule that cannot hold R3 is not shippable, however
  correct it is in principle.
- The rule must not try to resolve a reference that names a file in a *different*
  repository. Recorded as an operator decision on 2026-08-07: CI does not require
  cross-repository plumbing or checks. A reference of that kind cannot be
  validated from this checkout, and acquiring the ability to validate it would
  mean fetching or trusting a foreign tree from a blocking gate — a much larger
  change than this task's eligibility rule, and one nobody has asked for.
- Because the rule declines that class, the author-side convention is the whole
  remedy and belongs in R4's "stated reason" rather than in code: name the owning
  repository in prose and do not write the foreign path as a bare
  repository-relative code span. The check has no way to distinguish such a span
  from a local path that has rotted, and it is right to fail it.

## Open questions (resolve in design)

- What is the resolution source — `git ls-files`, an existing preflight file
  index, or a filesystem walk? The preflight already reads the repository for
  other checks; reusing that surface is preferable to adding a second one.
- Should a bare filename resolving to a file *outside* every checked prefix be
  eligible? R1 as written says no, but the prefix list exists for scope control
  rather than correctness, so this is worth revisiting once resolution exists.
- Does the same gap apply to the markdown-link branch at
  `scripts/sd-ai-command-pack-review-preflight.mjs:4417`, or does the
  `./`/`../` early return at
  `scripts/sd-ai-command-pack-review-preflight.mjs:4481` already cover links?
- Are `manifest.json` and `CHANGELOG.md` best served by the general rule, or
  should they also join `topLevelReferenceFiles` as a cheap independent
  improvement?
- What does R4's "inspectable" mean concretely — a debug mode, a reason field on
  the skipped reference, or documentation alone?

## Acceptance Criteria

- [ ] A documentation code span naming a bare filename that matches no tracked
      file anywhere fails the check, with the offending reference and its
      containing file and line in the diagnostic.
- [ ] A documentation code span naming a bare filename that matches exactly one
      tracked file under a checked prefix passes.
- [ ] A bare filename matching tracked files in two or more directories passes
      and is not reported.
- [ ] Running the check over the repository's current documentation before and
      after the change produces the same set of failures.
- [ ] Unit tests cover each row of the table above, plus at least three
      non-path dotted prose tokens that must remain ineligible.
- [ ] The `scripts/` and `templates/scripts/` copies of the preflight are
      identical, proven by `diff`.

## Notes

- Source: audit on 2026-08-06 following PR #339 and PR #340. The gap was
  confirmed by calling `shouldCheckDocumentationPathReference` directly against
  each reference in the table.
- Related but separate: `.trellis/tasks/08-06-review-check-receipt-pinning` and
  `.trellis/tasks/08-06-local-provider-empty-scope` also came out of that audit.
  Neither touches this function.
- The foreign-repository class above was found the hard way on 2026-08-07. PR #358
  described a test class living in the consumer repository `se-ai-command-pack`
  and wrote its location as a bare code span under this repository's `tests/`
  prefix. That made the reference eligible, it resolved to nothing here, and the
  gate failed — correctly. It was fixed in `765c0f74` by naming the owning
  repository in prose instead, which is the convention the new constraint
  records. The eligibility rule behaved exactly as designed; only the reference
  was wrong.
- Adjacent but distinct: `.trellis/tasks/08-07-ci-preflight-full-mode-gap` covers
  *when* this check runs in CI — it currently runs in one classifier mode only.
  That task does not change eligibility, and this one does not change scheduling.
- Complex enough to need `design.md` and `implement.md` before `task.py start`:
  R1 and R3 pull against each other, and the resolution source is a real choice
  with a per-run cost (N1).
