---
title: Review preflight path refs are not ignore-aware
status: done
created: 2026-08-18
---
# Review preflight cannot express a deliberately-absent path

## Status update — 2026-08-20 (mechanism shipped; closing on a naming decision)

Re-verified against the working tree at 2cc1e7fe. Two of this task's three open
criteria are already satisfied by shipped, tested code, and one claim in the
body below is factually wrong.

- **Point-of-use absent declaration: shipped.** `[absent: <reason>]`, pattern at
  `scripts/sd-ai-command-pack-review-preflight.mjs:157`, predicate
  `isAbsentPathMarked` at `:5066`, consumed at `:5084` and `:5111-5115`
  (commit 687f7f8d).
- **Repository-wide declaration: shipped and tested.** `optionalReferencePaths`
  merges from the tracked `.sd-ai-command-pack/review-preflight.json` in
  `loadConfig` (`:448-470`) and is consulted at `:5167`. End-to-end coverage at
  `tests/test_review_preflight.py:4296-4306` fails without the entry and passes
  with it — exactly the mechanism this task's residual scope asked for.
- **The body's claim that "the config path is not covered by an equivalent
  test" is wrong.** `test_review_preflight_reports_malformed_config_as_failure`
  at `tests/test_review_preflight.py:4510-4540` asserts returncode 1 and
  `"could not be parsed as JSON"`. Verified present 2026-08-20. `loadConfig`
  also merges only when `Array.isArray(raw[key])` and filters non-strings, so a
  malformed declaration is dropped and the references stay checked — the path is
  fail-closed by construction, not merely untested.
- **The ignore-aware design this task is named for was already rejected here and
  stays rejected.** No `.gitignore` or allowlist consultation exists anywhere in
  the preflight: `grep -rn "check-ignore"` hits `full-check.sh`,
  `review-local.py`, `install-audit.py`, and `check.py` — never this checker.

### The one residual, and the decision taken

All that remained was schema naming: ship a distinct `absentReferencePaths` key
carrying a required reason, or reuse the existing `optionalReferencePaths`.

**Decision: reuse `optionalReferencePaths`.** It is already tracked, already
merged fail-closed, and already covered by two tests. A second key would add a
parallel code path through `loadConfig` and a second way to express one
intent, for the sole benefit of a reason string that the point-of-use
`[absent: <reason>]` marker already carries where a reason is actually useful.

This decision is cheap to reverse: adding `absentReferencePaths` later is
additive to `loadConfig` and breaks no existing declaration.

Remaining: nothing actionable. Archived 2026-08-20.


## Goal

Give the review preflight's documentation path-reference check a way to accept a
path that is deliberately absent from the checkout, so a planning artifact may
name one in prose without failing `CI scope` — and without weakening the check
that catches an actual typo.

## Origin

Found 2026-08-18 while landing `08-18-opencode-parity-ignores-git`. That task
fixes a test which conflated "exists on disk" with "is tracked payload". Its own
PRD then tripped a related conflation one layer up, in shipped payload:

```
FAIL .trellis/tasks/08-18-opencode-parity-ignores-git/prd.md:16 references missing path .opencode/package.json.
```

The PRD was describing a path `CONTRIBUTING.md:203-211` deliberately keeps out of
the repository. The CI checkout does not contain it, so the reference read as
broken.

## Problem

`templates/scripts/sd-ai-command-pack-review-preflight.mjs:3195-3199` resolves
every documentation path reference with a bare existence probe:

```js
...findMissingDocumentationPathReferences(
  file,
  referenceText,
  (candidate) => exists(candidate),
),
```

`exists` answers "is this in the checkout". The gate means to ask "is this a
real path, or a typo". Those differ for a path the project has decided on
purpose should not be committed — which is a documented, intentional state, not
an error.

The validator already recognises that existence is the wrong test in some cases.
At `:3180-3186` it exempts `design.md` and `implement.md` because they are
forward-looking and reference files the task proposes to create. A
deliberately-absent path is a second such category and has no exemption. The
`pass()` message at `:3211` claims references resolve to "existing repo files or
documented external/local-only paths", but there is no local-only mechanism in
`findMissingDocumentationPathReferences` (`:5002`) — only
`resolveDocumentationReference` declining to resolve non-repo-looking targets.
The message promises a category the code does not implement.

## The obvious fix does not work, and that constrains the design

The first instinct is to make the check ignore-aware: accept any path
`git check-ignore` matches. That fails for the motivating case.

The OpenCode manifest is matched only by line 2 of the per-directory ignore file
in `.opencode/`, and that ignore file **is not tracked** — its own line 5 ignores
`.gitignore`, so it never entered the index. Measured 2026-08-18, with `$M`
standing in for the manifest path this check would reject:

```
$ git ls-files -- .opencode/.gitignore     # no output
$ git check-ignore -v "$M"
.opencode/.gitignore:2:package.json	<manifest>
```

The repository's tracked ignore policy for this directory is `.gitignore:136`,
`.opencode/node_modules/`, and nothing more. In a fresh CI clone nothing ignores
the manifest, so an ignore-aware check would still fail it. Any design that
routes through `git check-ignore` must be rejected on this evidence.

This also surfaces a second, separable gap: a documented policy
(`CONTRIBUTING.md:203-211`, tracked) is enforced by an untracked local file, so a
fresh clone that follows the documented install step gets an untracked manifest
and lockfile with nothing preventing an accidental commit. Recorded here; see
Out of scope.

## Impact

Any planning artifact that discusses a deliberately-absent path fails
`CI scope`, and the failure calls it a "missing path" when it is a documented
one. The workaround in `08-18-opencode-parity-ignores-git` is to avoid spelling
such a path outside a fenced code block, which teaches authors to write around
the gate rather than fix it.

This PRD demonstrated the defect on itself, twice. Its first draft named the
paths plainly:

```
FAIL .../08-18-preflight-path-refs-ignore-aware/prd.md:37 references missing path .opencode/package.json.
FAIL .../08-18-preflight-path-refs-ignore-aware/prd.md:37 references missing path .opencode/node_modules.
FAIL .../08-18-preflight-path-refs-ignore-aware/prd.md:72 references missing path .opencode/package.json.
```

and the second draft, after contorting the prose, was rejected for citing the
ignore file itself:

```
FAIL .../08-18-preflight-path-refs-ignore-aware/prd.md:38 references missing path .opencode/.gitignore.
```

The gate rejected the document describing the bug, for the bug, on two
consecutive attempts.

## What `08-08-preflight-absent-path-prose` delivered, 2026-08-19

That task shipped the point-of-use marker: a documentation reference followed
on the same line by `[absent: <reason>]` is exempt from the existence probe.
The reason is required, every malformed or misplaced form leaves the reference
checked, and the exemption covers only the one reference it follows. It also
rewrote the `pass()` message to name all three accepted outcomes -- resolved,
optional by configuration, or marked absent at the point of use -- which is
requirement 6 below, closed in full.

The marker closes the motivating case: a planning artifact may now spell the
OpenCode manifest path plainly in prose and mark it, and the gate accepts it in
a checkout where the file is absent. Requirements 2, 3, and 4 were never at
risk and remain satisfied -- the marker is a per-match regex test with no
subprocess and no network, and it changes no other exemption.

### What a tracked declaration would still buy

The marker is per-reference by design, so it is the wrong tool for a path that
several documents legitimately name. That is the residual scope here:

- A **tracked, repository-wide declaration** of deliberately-absent paths.
  `optionalReferencePaths` extended through `.sd-ai-command-pack/review-preflight.json`
  is already exactly that mechanism and that file would be tracked, so the
  remaining question is not whether one exists but whether the pack should ship
  a distinct *absent* declaration -- carrying a required reason, the way the
  marker does -- rather than reusing an array named for optional generated
  artifacts. Answer that before designing anything.
- **Fail-closed behavior on a malformed declaration** (requirement 5). The
  marker fails closed by construction and is asserted so. The config path is
  not covered by an equivalent test; that gap is real and independent of which
  declaration shape wins.

Reduced scope, 2026-08-19. Do not re-litigate the ignore-aware design: the
untracked-ignore-file evidence above still rules `git check-ignore` out.

Also note: `08-18-opencode-parity-ignores-git` was archived on 2026-08-18, so
the acceptance criterion below asking to revert prose contortions in *that*
PRD now targets an archived record. Archived tasks are immutable; treat that
half of the criterion as closed by the marker's availability for future
documents, not as an edit to make.

## Requirements

1. ~~A path the project deliberately keeps out of the checkout resolves as
   valid.~~ Delivered 2026-08-19 by the `[absent: <reason>]` marker. What
   remains is the repository-wide form: a **tracked** declaration for a path
   several documents name, since an untracked file cannot carry it per the
   evidence above.
2. A genuinely missing path — neither present nor declared — still fails, and the
   message is byte-identical to today's.
3. The `design.md`/`implement.md` and archive exemptions at `:3180-3186` keep
   their current behavior.
4. The check stays local and deterministic: no network, and no per-reference
   subprocess where one batched query answers the whole file set.
5. An unreadable or malformed declaration fails closed rather than treating every
   reference as valid. This is the lesson from the bash 3.2 gate: an empty result
   must never read as "nothing to check".
6. ~~The `pass()` message describes what the code actually accepts.~~ Closed
   2026-08-19: it now names resolved, optional-by-configuration, and
   marked-absent-at-the-point-of-use. The `:3211` citation predates that
   change and is not refreshed here, because the line no longer carries the
   defect.

## Acceptance criteria

- [x] A planning artifact naming the OpenCode manifest plainly in prose passes
      the preflight in a checkout where that file is absent. Delivered by the
      `[absent: <reason>]` marker on 2026-08-19; a repository-wide declaration
      would still need its own proof.
- [ ] A reference to a path that is neither present nor declared still fails, and
      the failure message is byte-identical to today's.
- [ ] A forced-failure or malformation of the declaration makes the check fail
      closed, asserted by a test rather than by inspection.
- [ ] The prose contortions in this PRD are reverted to spell the paths
      plainly, and the preflight still passes. The
      `08-18-opencode-parity-ignores-git` half is dropped: that task archived on
      2026-08-18 and its record is immutable.
- [ ] No design in the accepted plan resolves validity through `git check-ignore`,
      or it carries a written rebuttal of the untracked-ignore-file evidence
      above.
- [ ] `manifest.json` is bumped, `make sync` and `make generate` are clean, and
      `docs/fleet/candidate-validation.json` is refreshed — this changes shipped
      payload under `templates/**`.
- [ ] `make check` passes.

## Out of scope

- The parity-test fix itself (`08-18-opencode-parity-ignores-git`).
- Tracking the `.opencode` ignore rules so a fresh clone enforces the documented
  policy. That is the separable gap recorded above and needs its own task; this
  one changes a validator, not the repository's ignore policy.
- Any other preflight lane, including the personal-absolute-path and stale-map
  checks that run beside this one.
- Broadening the `design.md`/`implement.md` exemption.
