# Design — make KB pruning prove ownership before deleting

## Scope boundary

`is_stale_generated_kb_entry` and its callers in
`scripts/sd-ai-command-pack-update-spec-kb.py`, plus the template twin. The root
symlink at `ensure_kb_root:267` is explicitly out of scope (PRD R4) — it is
documented intended behavior at `docs/SD_AI_COMMAND_PACK.md:1065-1071` and
asserted by `tests/test_update_spec_kb.py:138`.

## Three branches, three different standards

```python
def is_stale_generated_kb_entry(candidate, relative_candidate, root, legacy_sources):
    legacy_marker = legacy_generated_marker(relative_candidate)
    if legacy_marker is not None:
        return file_contains_marker(candidate, legacy_marker)          # :247  content proof
    if candidate.is_symlink():
        return (is_tool_owned_symlink(candidate, root)                 # :250  ownership proof
                and (is_managed_kb_category_path(relative_candidate)
                     or relative_candidate in legacy_sources))
    return candidate.is_file() and is_managed_kb_category_path(relative_candidate)  # :256
```

`is_managed_kb_category_path` (`:225`) tests one thing:
`path.parts[0] in KB_CATEGORY_TITLES` — the 13 titles built at `:905` from
`KB_CATEGORIES` at `:834` ("Repository Overview", "Backend Specs", "Thinking
Guides", …). It is a **location** test. The `:256` branch therefore deletes any
plain file whose first path component happens to be one of those titles, with no
evidence the tool created it. The prune loop at `:748` reaches it for every entry
under `kb_root.rglob("*")` and unlinks at `:753`.

## The branch is live, and it mixes tool copies with user files

Corrected 2026-07-28 after adversarial review. An earlier draft of this section
claimed the tool writes only two plain files and that every category document is
a symlink, and concluded the `:256` branch could be deleted outright. **That was
wrong, and acting on it would have deleted the stale-copy pruner.**

The tool has no symlink writer at all — there is no `create_symlinks`. The one
writer is `create_copies` (`:1315`), and it writes a **plain file per source**:

```python
shutil.copy2(source, copy, follow_symlinks=False)     # :1348
```

with `copy = kb_root / kb_destination_for_source(source)` and

```python
def kb_destination_for_source(source: Path) -> Path:              # :1035
    return Path(category_folder_for_source(source)) / destination_filename_for_source(source)
```

So every destination is `<Category Folder>/<name>.md` — precisely the shape
`is_managed_kb_category_path` matches. The `:256` branch's population is
therefore **two overlapping sets**:

1. the tool's own copies whose source was deleted or renamed — genuinely stale,
   and pruning them is the behavior the stale-document and convergence
   acceptance criteria depend on; and
2. any plain file a user drops into a category folder — never written by the
   tool, deleted anyway.

The `:250` symlink branch survives only for KB roots created by older versions,
or links a user made by hand.

That reframes the fix in the opposite direction from the earlier draft. The
branch must **stay**; what it lacks is any way to tell set 1 from set 2. The
`:247` legacy branch already demonstrates the mechanism — content proof through
`file_contains_marker` (`:527`). The `:256` branch is the only one of the three
that deletes on location alone.

**The real cost is the migration.** Copies already on disk carry no marker, so a
marker check applied on its own makes every pre-existing copy unprunable and the
stale-document criterion regresses. Whatever proof mechanism is chosen has to
answer for copies written before it existed. Sizing that is step 1 of
`implement.md`, and it gates everything after it.

## Marker mechanism

The in-file HTML-comment marker is already the house idiom —
`DASHBOARD_MARKER` and `OVERVIEW_MARKER` at `:43-44`, read through
`file_contains_marker:527`. Extending it costs nothing new and keeps the proof
co-located with the artifact, so a file that is copied or renamed carries its own
provenance.

A sidecar manifest (PRD R3's alternative) records paths in one place and can
cover non-text artifacts, but it introduces a second source of truth that can
desynchronize from disk — precisely the failure class this task is fixing.

The marker has one property the manifest does not, and it is decisive here:
`create_copies` **already copies the source byte-for-byte**, so a marker emitted
into the KB copy has to be written by the copier rather than inherited. That is a
change to `create_copies`, not only to the predicate — the copy stops being a
byte-identical `shutil.copy2` of its source and becomes a copy plus a provenance
line. Note the coupling in the changelog; it is the one user-visible difference.

**Recommendation: extend the existing marker idiom; do not add a manifest.**

## Convergence and migration (PRD R2)

Requiring a marker means copies written by earlier versions carry none, so they
stop being pruned and the tool stops converging — leftovers accumulate silently.
The earlier draft listed "delete the branch" as option A; with the branch now
known to be the live stale-copy pruner, that option is withdrawn. Two remain:

- **A — one-time reconciliation, not a blind sweep.** On a run where the marker
  is newly present, an unmarked plain file under a category folder is prunable
  **only if its path is a current or former `kb_destination_for_source` value** —
  that is, only if the tool could have written it. A user's `my-notes.md` is not
  a destination the generator ever emits, so it is never touched. This converges
  without ever deleting on location alone. Recommended.
- **B — leave unmarked files alone forever.** Safe, non-converging: every
  pre-marker copy becomes permanent litter, and the stale-document criterion is
  satisfied only for copies written after the change. Acceptable fallback if A's
  destination reconstruction proves unreliable, but it must be stated as a known
  regression rather than discovered later.

A blind version-keyed sweep of unmarked category files is **rejected**: it is the
same delete-on-location bug, scheduled once.

### Migration sizing and decision (recorded 2026-07-31, implement.md step 1)

Measured against the pre-change KB generated by the current `main` code:

- total plain files under category folders: **853**
- files a marker check would strand: **853** (one grep hit was this task's own
  `implement.md` copy, which quotes the marker string — no real marker exists yet)

**Decision: option B, with adoption-by-rewrite.** Option A's reconciliation
requires the set of *former* `kb_destination_for_source` values, and former
sources are not recorded anywhere — the tool cannot compute destinations for
sources that no longer exist. Reconstructing them from filename shape is the
same delete-on-location heuristic this design already rejects. So A's
destination reconstruction is unreliable by construction, which is exactly B's
documented trigger.

B's regression is far smaller than the raw 853 suggests: on the first refresh
after the change, every copy whose source still exists fails the new
marker-aware currency check (old copies are byte-identical to their sources)
and is rewritten with the marker — natural adoption, no special pass. The
permanent-litter residue is only copies orphaned *before* the upgrade, which in
a converged KB is zero. The changelog states the regression: files orphaned
before this version are no longer pruned automatically; delete them manually or
regenerate the KB from scratch.

## Rollout and rollback

`.obsidian-kb` is gitignored (`.gitignore:172`) and per-checkout, so there is no
consumer-visible artifact to migrate and no cross-repo coordination. Rollback is
revert plus normal pack release. The irreversible part is any file already
deleted by the current behavior — this change stops future loss, it does not
recover past loss.

## Test strategy

The decisive test is a **user file that must survive**: place
`Repository Overview/my-notes.md` (no marker, not a symlink, not in `wanted` or
`generated`) under a KB root, run the prune, assert the file still exists. That
test fails against today's code. A test that only checks marked files are pruned
passes today and proves nothing.
