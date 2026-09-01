---
title: Scope the pack-version adoption exemption to managed block boundaries
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-28
---
# Scope the pack-version adoption exemption to managed block boundaries

## Goal

The pack-version adoption exemption states one rule on two surfaces — the gate
that enforces it and the reviewer instructions that describe it — and both
reason about whole files. That was
sound while every installer-managed path was wholly installer-owned. Since
0.71.60 the installer manages only a marker-delimited block inside `AGENTS.md`
and leaves the rest of the file to the repository, so a file-level exemption now
covers bytes the installer does not own. Fix both surfaces together; a gate and
a reviewer instruction that disagree about the same rule is worse than either
error alone.

## Context

Raised by local review on multiple consumers during the 0.71.62 rollout, under
the titles "Version-adoption exemption too broad for managed-block files",
"Version-adoption exemption excludes required task bookkeeping", and
"Version-adoption exemption ignores managed-block boundaries" — severity low to
medium. Accepted as a pack-internal concern on each lane rather than fixed,
because the lane's job was the refresh.

The exemption's own comments state the safety case it must not lose
(`scripts/sd-ai-command-pack-review-scope.sh:129-190`):

- the receipt granting the exemption must itself be scope-checked, because
  "under an exemption the sign flips and a diff could exempt itself";
- an unexpected extra path must drop the exemption "with no second rule";
- failing open is explicitly rejected — "requirement 2 is the whole safety case
  for this exemption".

A file-level rule applied to a partially managed file fails open in exactly the
shape those comments forbid: edits to the unmanaged remainder of `AGENTS.md`
ride along inside an exemption granted for the managed block.

### Second surface: the reviewer-facing statement of the rule

Filed as issue #575 after this task was created, found by prism (medium /
correctness) during the local review of rwbp-website PR #280 — the
0.71.51 → 0.71.62 refresh, whose diff is exactly the implicated shape:
`AGENTS.md` managed block, `.github/copilot-instructions.md`, and the three
`.sd-ai-command-pack/` receipts. Classified `contractFamily: documentation` →
`defer-follow-up`, campaign decision `continue-with-follow-ups`, waived on the
consumer PR as `accepted` because the sentence is rendered pack payload that the
consumer PR did not author.

The sentence tells the reviewer:

> Do not request one when every changed file is a file the pack installs — that
> is a version adoption, and the gate exempts it.

`AGENTS.md` is edited by the pack and *installed* by nothing. So a
version-adoption PR carrying that block edit does not satisfy "every changed
file is a file the pack installs", and the instruction excludes precisely the
diff shape carried by the adoption PR of every consumer that has an `AGENTS.md`.

The 0.71.62 refresh PR bodies state that the installer never creates the file
and skips a repository without one, which is why the exclusion is conditional on
the consumer already having it. That claim comes from the release description,
not from a read of installer source; confirm it before relying on it as the
boundary condition.

Two files carry the sentence, and they are **not** copies of each other — they
hash differently and the sentence sits at different lines:

```
templates/.github/copilot-instructions.sd-ai-command-pack.md:66
.github/copilot-instructions.md:77
```

`installer/conversion.py:173` states their fates differ and calls
`.github/copilot-instructions.md` repo-native; `installer/thin.py:679` treats it
as consumer-owned. Establish which is authored and which is derived before
editing; do not hand-edit both.

## Requirements

- The exemption must reason about the installer's actual ownership boundary for
  a partially managed file, not the whole file.
- Preserve every existing safety property: the granting receipt stays
  scope-checked, an unexpected path still drops the exemption with no second
  rule, and the rule still fails closed.
- Wholly-managed files must keep behaving exactly as they do now. This is a
  narrowing for marker-block files, not a redesign.
- The block boundary must come from the installer's own definition of it —
  `MANAGED_BLOCK_SPECS` at `installer/registry.py:2365` is the table that
  describes every managed-block target — rather than a second copy of the marker syntax
  that can drift.
- The reviewer instruction must state the rule in terms of what the pack
  installs **or manages**, so that a managed block in a file the pack does not
  own is covered. It must describe the same boundary the gate enforces; the two
  are one rule with two statements of it.

## Non-goals

- Changing which files the installer manages, or the marker syntax itself.
- Touching the actor-based exemption in
  `scripts/sd-ai-command-pack-pr-body-scope.py`. Different mechanism, different
  file, not implicated.

## Acceptance Criteria

- [ ] A diff that edits `AGENTS.md` outside the installer-managed block does not
      receive the pack-version adoption exemption.
- [ ] A diff that edits only the managed block, plus the ordinary receipts, still
      receives it.
- [ ] A wholly installer-managed file's exemption behavior is unchanged, proven
      by a test that would fail if it regressed.
- [ ] The marker boundary is read from the installer's managed-block definition,
      with no second copy of the marker syntax.
- [ ] The reviewer instruction covers a managed block in a file the pack does
      not install, and the wording matches the boundary the gate enforces.
- [ ] The instruction is changed at its authored source, with the derived copy
      regenerated rather than hand-edited, and the two are consistent afterwards.
- [ ] The recurring local-review finding no longer reproduces on a fleet refresh
      of a consumer whose `AGENTS.md` is partially managed.
- [ ] Issue #575 is closed by the change.
