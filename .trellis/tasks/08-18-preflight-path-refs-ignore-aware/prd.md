# Review preflight cannot express a deliberately-absent path

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

## Requirements

1. A path the project deliberately keeps out of the checkout resolves as valid.
   The mechanism is a design decision, but it must be **tracked** — an untracked
   file cannot carry it, per the evidence above.
2. A genuinely missing path — neither present nor declared — still fails, and the
   message is byte-identical to today's.
3. The `design.md`/`implement.md` and archive exemptions at `:3180-3186` keep
   their current behavior.
4. The check stays local and deterministic: no network, and no per-reference
   subprocess where one batched query answers the whole file set.
5. An unreadable or malformed declaration fails closed rather than treating every
   reference as valid. This is the lesson from the bash 3.2 gate: an empty result
   must never read as "nothing to check".
6. The `pass()` message at `:3211` describes what the code actually accepts, or
   the code implements what the message already claims.

## Acceptance criteria

- [ ] A planning artifact naming the OpenCode manifest plainly in prose passes
      the preflight in a checkout where that file is absent, proven by running
      the gate with the local install moved aside.
- [ ] A reference to a path that is neither present nor declared still fails, and
      the failure message is byte-identical to today's.
- [ ] A forced-failure or malformation of the declaration makes the check fail
      closed, asserted by a test rather than by inspection.
- [ ] The prose contortions in **both** PRDs — this one and
      `08-18-opencode-parity-ignores-git/prd.md` — are reverted to spell the
      paths plainly, and the preflight still passes.
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
