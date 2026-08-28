# review-preflight treats a branch name as a repository path when its prefix collides

## Goal

The documentation path-reference gate should not fail a document for naming a Git branch. A
branch name is not a path claim, and today whether the gate fires on one depends entirely on
whether the branch's first segment happens to match a configured reference prefix.

## Origin

Found on 2026-08-28 filing a task record. The gate failed:

```text
FAIL .trellis/tasks/08-28-status-remote-branch-detection/prd.md:13 references missing path
docs/file-review-and-kb-defects.
```

The PRD was describing a Git branch, not citing a file. The same document referred to a second
branch in the same way, and that one passed:

```text
origin/feat/codex-local-review-lane
```

Both are branch names in code spans. The only difference between them is the leading segment.

## The mechanism

`shouldCheckDocumentationPathReference` decides eligibility from the target's shape, and one of
its accept branches is an unconditional prefix match
(`scripts/sd-ai-command-pack-review-preflight.mjs:5368`):

```js
if (referencePrefixes.some((prefix) => normalized.startsWith(prefix))) {
  return true;
}
```

`referencePrefixes` (`:375-401`) contains `docs/`, and also `apps/` and `scripts/`. `origin/` is
not in it. So the failing branch above is admitted as a path reference and then required to
exist, while `origin/feat/codex-local-review-lane` is never considered at all.

`docs/`, `apps/`, and `scripts/` are all ordinary Git branch-name prefixes; `docs/<slug>` is a
common convention and is the one this repository actually used.

## Why the existing escape hatches do not cover it

The extractor already supports an explicit marker, `[absent: ...]`
(`ABSENT_PATH_MARKER_PATTERN` at `:157-158`, tested by `isAbsentPathMarked` at `:5236-5238`
and applied at `:5254` and `:5285-5286`). It is the wrong
tool here: it asserts that a *path* is intentionally absent. A branch name is not an absent
path, so marking one would put a false claim in the document to silence a check that should
never have fired.

The gate's own design already draws the distinction this case needs, but only on the other
branch of the decision. The bare-filename rule at `:5372-5386` declines a target that carries
no line/range suffix, on the explicit reasoning that

> Prose uses a filename as a noun far more often than as a path, and that class carries the
> names of things that deliberately do not exist.

That is exactly the noun-versus-location distinction a branch name needs. The prefix branch
never applies it: a prefix match is accepted unconditionally, with no shape test behind it.

## The PRD cannot state its own example

This document originally named the offending branch in prose twice, and the gate failed it
both times — the same failure it exists to describe. The two mentions were rewritten to refer
to the failure message rather than repeat the token, because the one available escape hatch,
`[absent: ...]`, would have asserted that a branch is a missing path. That is direct evidence
for the requirement below that an author be able to name a branch without asserting something
untrue about it.

## Requirements

- A document may name a Git branch without the path-reference gate failing, and without the
  author having to assert something untrue about it.
- The fix does not depend on the branch's leading segment. Whatever the resolution, it treats
  `docs/<branch>` and `origin/<branch>` alike.
- Real missing-path references keep failing. In particular a genuine `docs/...` file citation
  that does not exist must still be reported; narrowing the prefix list is therefore not a
  sufficient fix on its own.
- Whatever distinguishes a branch from a path is decided from the shape of the reference or its
  immediate context, consistent with the existing rule that eligibility is pure shape and
  existence is answered later by `resolveDocumentationReference`.
- The chosen mechanism is documented where an author will meet it — a failing message that
  names a branch should say how to express one.

## Directions worth weighing

Not a decision this PRD makes; each has a real cost.

1. **A branch marker**, sibling to `[absent: ...]` — explicit and truthful, but it is another
   piece of notation for authors to know, and the failure message must teach it.
2. **Context-sensitive suppression** — skip a reference whose surrounding prose says "branch".
   Requires no notation, but couples a deterministic shape gate to prose parsing, which the
   current design deliberately avoids.
3. **Require a path-ish tail** for prefix matches — a branch name rarely ends in a file
   extension, and the branch in the failure above does not. This reuses the existing
   noun-versus-location instinct, but would stop checking directory references that are
   legitimately extensionless.

## Non-goals

- Changing how the bare-filename branch of the rule works; it already makes this distinction.
- Removing `docs/`, `apps/`, or `scripts/` from `referencePrefixes` as the whole fix, which
  would silence real missing-path findings under those trees.
- Any change to `[absent: ...]` semantics for genuine paths.

## Acceptance criteria

- [ ] A document naming a branch whose first segment is a configured reference prefix passes
      the gate, and the same document on today's code fails it.
- [ ] A genuine reference to a non-existent file under `docs/` still fails, pinned by a test so
      the fix cannot over-reach into silencing real findings.
- [ ] `docs/<branch>` and `origin/<branch>` are treated identically by the gate.
- [ ] A test covers at least one additional colliding prefix from the configured list, so the
      fix is not special-cased to `docs/`.
- [ ] If the resolution introduces notation, the failure message names it, and a test asserts
      the message does.
- [ ] All four copies of `sd-ai-command-pack-review-preflight.mjs` stay byte-identical and
      `make generate` reports `shipped-surface closure: clean`.

## Related

- `.trellis/tasks/08-28-status-remote-branch-detection` — the task record whose PRD triggered
  this, filed in the same session.
