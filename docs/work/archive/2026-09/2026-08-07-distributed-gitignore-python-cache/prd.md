---
title: Distributed gitignore block omits Python bytecode caches it causes
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-07
---
# Distributed gitignore block omits Python bytecode caches it causes

## Goal

Add Python bytecode-cache patterns to the gitignore block the installer writes
into consumer repositories, so the byproduct of running pack-installed Python
scripts does not surface as untracked noise in every consumer.

## Problem

The installer writes a managed block into each consumer's root `.gitignore`
(`installer/fileops.py:450-469`), assembled from four pattern tuples that are
not contiguous in the source:

| tuple | defined at | covers |
|---|---|---|
| `LOCAL_ENV_GITIGNORE_PATTERNS` | `installer/registry.py:1967` | `.env` and friends |
| `TRELLIS_GITIGNORE_PATTERNS` | `installer/registry.py:1974` | Trellis runtime state |
| `REVIEW_ARTIFACT_GITIGNORE_PATTERNS` | `installer/registry.py:1982` | review/build artifacts |
| `PLATFORM_LOCAL_GITIGNORE_PATTERNS` | `installer/registry.py:1922` | per-platform AI-tool state |

None of the four contains a Python cache pattern.

The pack installs **18** Python scripts into each consumer's `scripts/`
directory (counted from a real consumer's
`.sd-ai-command-pack/installed-targets.txt`). Running any of them writes
`scripts/__pycache__/`, which nothing then ignores.

### The pack already treats this as a byproduct everywhere except the block

Three places show the pack has already made this judgment:

| where | what it says |
|---|---|
| the pack's own `.gitignore:7-8` | `__pycache__/` and `*.py[cod]` |
| `templates/scripts/sd-ai-command-pack-update-spec-kb.py:131` | `__pycache__` in the KB copy skip-list |
| `templates/scripts/sd-ai-command-pack-install-audit.py:264` | `__pycache__` in `REFERENCE_SCAN_EXCLUDED_PARTS` |

So the pack ignores the cache in its own repository, and its shipped scripts
skip it when walking a consumer's tree — but the ignore block it distributes
leaves it visible. The asymmetry is the defect: the pack protects itself from a
byproduct it causes in others.

Trellis, separately, gets this right. `.trellis/.gitignore` — which is
Trellis-owned and **not** a pack-installed target, confirmed against a
consumer's `installed-targets.txt` — carries `**/__pycache__/` and `**/*.pyc`.
Its scope stops at `.trellis/`, so it never reaches `scripts/`.

### Why the sanctioned entry point hides this

`templates/scripts/sd-ai-command-pack-toolchain.sh:176` and `:180` set
`PYTHONDONTWRITEBYTECODE=1`, so `toolchain.sh run-python -- scripts/<name>.py`
leaves nothing behind. Direct `python3 scripts/<name>.py` does not.

That is why this has stayed invisible: every documented invocation in the pack's
own skills routes through the toolchain wrapper. Only ad-hoc direct invocation —
which is exactly what an agent does when analysing a consumer repository —
produces the cache.

### Observed

Hit on 2026-08-07 in `platypeeps/loadsmith` while running
`scripts/sd-ai-command-pack-review-learnings.py` directly to enumerate review
clusters. `scripts/__pycache__/` appeared three separate times across the
session and twice blocked `git worktree remove` without `--force`:

```text
fatal: '<worktree>' contains modified or untracked files, use --force to delete it
```

Forcing there would have discarded an unrelated worktree's contents. The
untracked directory is harmless in itself; what it does is turn a safe cleanup
into one that needs `--force`.

### Why the consumer cannot simply fix this locally

This is the part that makes it the pack's problem rather than each consumer's.

`install_trellis_gitignore` registers `.gitignore` as a generated pack target
(`installer/fileops.py:531-532`), so it appears in the consumer's
`.sd-ai-command-pack/installed-targets.txt`. In `platypeeps/loadsmith` that
listing causes the repo's review gate to classify any `.gitignore` edit as
pack-owned scope and demand that `.sd-ai-command-pack/provenance.json` change in
the same commit. But `.gitignore` is not among provenance's hashed files, so a
project-local edit produces no provenance change to make, and the requirement
cannot be met without touching an unrelated file.

A pull request adding these two patterns to loadsmith's `.gitignore` was opened
and failed CI on exactly that:

```text
error: SD AI command-pack files changed without updating .sd-ai-command-pack/provenance.json
```

It was closed unmerged in favour of this task.

**Scope boundary, stated precisely.** The gate that fires is
`scripts/check_review_readiness.sh` [absent: loadsmith's, not shipped here]
in loadsmith, which is **not** a pack-distributed file — it does not exist
under `templates/` in this repository. So
this task is not responsible for that script's behaviour and must not be read as
a request to change it. What is in scope is the observation it produces: the
block's own closing line invites project-local additions —

```text
# Project-local personal ignores can be added below this managed block.
```

(`installer/fileops.py:467`) — and in at least one real consumer that invitation
cannot be accepted. Whether the invitation should be qualified, or whether the
patterns simply belong in the block, is the question below.

Whether other consumers gate `.gitignore` the same way is **not established**.
One consumer was inspected. The distribution argument does not rest on that
count: a byproduct the pack causes in every consumer belongs in the block the
pack ships, independent of how many consumers find it awkward to patch locally.

## Requirements

- The patterns are added to the managed block's source tuples in
  `installer/registry.py`, not hand-written into any generated artifact. A
  generated `.gitignore` edited directly is overwritten on the next install.
- Placement within the block is decided rather than defaulted. The existing
  groups are env / Trellis-runtime / review-artifact / platform-local, and a
  Python cache is none of those; adding a fifth labelled group is one option and
  extending `REVIEW_ARTIFACT_GITIGNORE_PATTERNS` (`:1982-1993`) is another.
  Record which and why.
- The pattern form is chosen for consistency, not for behaviour. The pack root
  uses unanchored `__pycache__/` (`.gitignore:7`) while `.trellis/.gitignore`
  uses `**/__pycache__/`, and an earlier draft of this PRD asserted the two
  differ in what they match. **They do not.** Tested directly in a scratch
  repository: a root `.gitignore` containing either form ignores both
  `scripts/__pycache__/y.pyc` [absent: scratch-repo hypothetical, never here]
  and `a/b/scripts/__pycache__/x.pyc`, and
  `git status --porcelain --ignored` is byte-identical between them. A pattern
  with no internal slash matches at every depth, so the leading `**/` is
  redundant here. Pick one form, say which existing file it matches, and do not
  justify the choice with a behavioural difference that does not exist.
- Existing consumers converge on the next install without manual intervention,
  since the block is rewritten between its markers
  (`installer/fileops.py:508-515`).
- No currently tracked file in any consumer becomes ignored. `.pyc` files are
  not tracked in the repositories inspected, but the check is run rather than
  assumed.

## Acceptance criteria

- [ ] `trellis_gitignore_block()` emits the chosen Python cache patterns, and
      the generated-parity tests covering the block still pass.
- [ ] A test asserts the patterns are present in the emitted block and fails
      against the current tree. A test that passes today has not captured this
      defect.
- [ ] Installing into a scratch consumer produces a `.gitignore` in which
      `git check-ignore -v scripts/__pycache__/x.pyc` resolves to the managed
      block. The command output is quoted, not described.
- [ ] Re-installing over a consumer that already has the old block replaces it
      in place — the block is rewritten between its markers, no duplicate block
      appears, and content below the end marker survives byte-identical.
- [ ] `git ls-files -i -c --exclude-standard` returns the same set before and
      after in a real consumer checkout, proving no tracked file became ignored.
      Run it both ways rather than reasoning about it; the failure mode is a
      tracked artifact silently dropping out of review scope.
- [ ] The nested case is checked: with the root block in place,
      `git check-ignore -v .trellis/scripts/__pycache__/x.pyc` still resolves to
      `.trellis/.gitignore`, not to the root block. This already holds in a
      scratch reproduction — the deeper file takes precedence — so the criterion
      is a regression guard, not an open question. Quote the output.
- [ ] The repository's own readiness gate and generated-surface parity checks
      pass, and regenerated surfaces are byte-stable for everything except the
      block.

## Notes

Filed from `platypeeps/loadsmith` on 2026-08-07, from a real cleanup that needed
`--force`, not from reading the installer.

A project-local fix was attempted first and is the reason this task exists in
this repository rather than that one: loadsmith PR #213 added the two patterns
below the managed block, passed every local check, and failed CI on the
provenance co-change requirement described above. It was closed unmerged.

The narrower question this task does not answer: whether registering `.gitignore`
as an installed target is right at all, given that the pack manages only a block
inside a file the consumer otherwise owns. Loadsmith's own gate already carves
out one file on precisely that reasoning — `.github/copilot-instructions.md`,
excluded because "the command pack manages a block inside this repo-owned
adapter". `.gitignore` has the same shape and no such carve-out. That is a
consumer-side observation about a consumer-side script, recorded here only so
the reasoning is not lost; it is not in this task's scope.
