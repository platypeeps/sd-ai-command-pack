# Scope the pack-version adoption exemption to managed block boundaries

## Goal

The pack-version adoption exemption in
`scripts/sd-ai-command-pack-review-scope.sh` reasons about whole files. That was
sound while every installer-managed path was wholly installer-owned. Since
0.71.60 the installer manages only a marker-delimited block inside `AGENTS.md`
and leaves the rest of the file to the repository, so a file-level exemption now
covers bytes the installer does not own.

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

## Requirements

- The exemption must reason about the installer's actual ownership boundary for
  a partially managed file, not the whole file.
- Preserve every existing safety property: the granting receipt stays
  scope-checked, an unexpected path still drops the exemption with no second
  rule, and the rule still fails closed.
- Wholly-managed files must keep behaving exactly as they do now. This is a
  narrowing for marker-block files, not a redesign.
- The block boundary must come from the installer's own definition of it —
  `MANAGED_BLOCK_SPECS` in `installer/registry.py` is the table that describes
  every managed-block target — rather than a second copy of the marker syntax
  that can drift.

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
- [ ] The recurring local-review finding no longer reproduces on a fleet refresh
      of a consumer whose `AGENTS.md` is partially managed.
