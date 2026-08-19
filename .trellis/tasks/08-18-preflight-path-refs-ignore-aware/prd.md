# Review preflight path refs are not ignore-aware

## Goal

Make the review preflight's documentation path-reference check distinguish a
path that is *missing* from one the repository deliberately *ignores*, so a
planning artifact may name a git-ignored path without failing `CI scope`.

## Origin

Found 2026-08-18 while landing `08-18-opencode-parity-ignores-git`. That task
fixes a test which conflated "exists on disk" with "is tracked payload". Its own
PRD then tripped the identical conflation one layer up, in shipped payload:

```
FAIL .trellis/tasks/08-18-opencode-parity-ignores-git/prd.md:16 references missing path .opencode/package.json.
```

The PRD was describing a path the repository ignores on purpose. The CI checkout
does not contain it, so the reference read as broken.

## Problem

`templates/scripts/sd-ai-command-pack-review-preflight.mjs:3198` resolves every
documentation path reference with a bare existence probe:

```js
...findMissingDocumentationPathReferences(
  file,
  referenceText,
  (candidate) => exists(candidate),
),
```

`exists` answers "is this in the checkout". The question the gate means to ask is
"is this a real, intentional path". Those differ for exactly the paths a
repository ignores on purpose — the OpenCode manifest, its lockfiles, and its
dependency tree — which `.opencode/.gitignore` names explicitly so developers
can install the plugins locally.

The validator already recognises that existence is the wrong test in some cases.
Immediately above, at `:3180-3186`, it exempts `design.md` and `implement.md`
because they are forward-looking and reference files the task proposes to create.
An ignored-but-intentional path is a third legitimate category, and it has no
exemption.

## Impact

Any planning artifact that discusses an intentionally-ignored path fails
`CI scope`, and the failure names a "missing path" that is not missing — it is
ignored by design. The current workaround, used in
`08-18-opencode-parity-ignores-git`, is to avoid spelling such a path outside a
fenced code block. That is a prose contortion driven by a validator defect, and
it silently teaches authors to write around the gate instead of fixing it.

This PRD demonstrated the defect on itself. Its first draft named the paths
plainly, and the gate rejected the document describing the bug, for the bug:

```
FAIL .trellis/tasks/08-18-preflight-path-refs-ignore-aware/prd.md:37 references missing path .opencode/package.json.
FAIL .trellis/tasks/08-18-preflight-path-refs-ignore-aware/prd.md:37 references missing path .opencode/node_modules.
FAIL .trellis/tasks/08-18-preflight-path-refs-ignore-aware/prd.md:72 references missing path .opencode/package.json.
```

The prose above was then contorted the same way, which is why acceptance
criterion 4 requires both artifacts be restored to plain wording once the
validator is fixed.

## Requirements

1. A path matched by the repository's ignore rules resolves as valid, whether or
   not it is present in the checkout. `git check-ignore` is the authority; do not
   reimplement ignore matching.
2. A genuinely missing path — neither present nor ignored — still fails, with the
   message unchanged.
3. The existing `design.md`/`implement.md` and archive exemptions at `:3180-3186`
   keep their current behavior.
4. The check must not become network- or state-dependent, and must not shell out
   once per reference when one batched query answers the whole file set.
5. A repository with no ignore rules, or a checkout where the ignore query fails,
   fails closed rather than treating every reference as valid.

## Acceptance criteria

- [ ] A planning artifact naming the OpenCode manifest plainly in prose passes
      the preflight in a checkout where that file is absent, proven by running
      the gate with the local install moved aside.
- [ ] A reference to a path that is neither present nor ignored still fails, and
      the failure message is byte-identical to today's.
- [ ] A forced-failure of the ignore query makes the check fail closed, asserted
      by a test rather than by inspection.
- [ ] The prose contortions in **both** PRDs — this one and
      `08-18-opencode-parity-ignores-git/prd.md` — are reverted to spell the
      paths plainly, and the preflight still passes.
- [ ] `manifest.json` is bumped, `make sync` and `make generate` are clean, and
      `docs/fleet/candidate-validation.json` is refreshed — this changes shipped
      payload under `templates/**`.
- [ ] `make check` passes.

## Out of scope

- The parity-test fix itself (`08-18-opencode-parity-ignores-git`).
- Any other preflight lane, and the personal-absolute-path and stale-map checks
  that run beside this one.
- Broadening the `design.md`/`implement.md` exemption, or adding new exemption
  categories beyond the ignore rule above.
