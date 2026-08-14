# Design: housekeeping KB refresh must not block its own merge

## Current behaviour

`sd-housekeeping` runs `refresh_obsidian_kb` first
(`templates/scripts/sd-ai-command-pack-housekeeping.sh:1379`), before
`fetch_and_prune` and before any merge or branch lifecycle. The helper's
`ensure_ignore_file` (`templates/scripts/sd-ai-command-pack-update-spec-kb.py:560`)
rebuilds the managed block from `kb_ignore_block()` and writes whenever the
rebuilt text differs from the file **byte for byte**. Any edit to the block's
comment lines therefore rewrites tracked `.gitignore` on the next run in every
consumer at once.

Three gates then read tree cleanliness, and all three block:

| gate | location | effect |
| --- | --- | --- |
| dependency-PR merge | housekeeping.sh:718 | `working_tree_dirty`, merge skipped |
| merged-branch cleanup | housekeeping.sh:835 | `working_tree_dirty`, no switch/delete |
| auto-merge eligibility | pr-eligibility.py:1145 | `blocked`, `working_tree_dirty` |

The eligibility probe is a separate process, so any "housekeeping forgives its
own writes" scheme would have to be threaded through a second tool. That rules
out the tolerate-my-own-delta direction.

## Decision: remove the write, do not tolerate it

The defect is not the ordering per se; it is that a **cosmetic** change to
generated text produces a **tracked-file** delta on every consumer. Fix it at
the writer: make the ignore block semantically idempotent. The helper writes
only when the block is functionally deficient, never to restyle text it already
owns.

Deficient means exactly one of:

1. no managed block present (markers absent);
2. markers present but the block does not ignore the KB directory;
3. an unmanaged KB ignore entry exists outside the block (the existing prune).

Anything else — including a block whose comment lines were emitted by an older
pack version — is left byte-identical and reported as `present`.

### Why not reorder the refresh

Moving `refresh_obsidian_kb` after the merge is rejected. It contradicts the
documented contract ("Refresh `.obsidian-kb` once before fetch or merge",
`templates/.agents/skills/sd-housekeeping/SKILL.md:70`) which a test pins
(`tests/test_housekeeping.py:497`), and it only defers the problem: the write
still sits in the tree and blocks the **next** run's gates. Semantic idempotence
fixes both runs.

### Why not tolerate the delta at the gate

Rejected: it would have to be duplicated in `pr-eligibility.py`, and it weakens
a failed-closed gate to admit a class of writes identified by content
inspection. The PRD's non-goal ("do not change the gate's failure-closed
posture for deltas the run did not itself write") is easiest to honour by not
creating the delta.

### Escape hatch

A new `--rewrite-ignore-block` flag forces the byte-exact rebuild for the case
where the block text genuinely must be normalized (an installer or conversion
run that will commit the result). Default off. Without it, no run ever rewrites
a functional block.

The flag is orthogonal to the existing mutually exclusive `--dry-run`/`--check`
group, so it combines with either: with `--dry-run` it previews the rebuild,
and with `--check` it restores the old strictness (cosmetic drift reads as
not-current). Every mode routes through the same predicate, so no mode can
promise a write another mode would not perform.

### What stays blocked, on purpose

A run that must **create or repair** the block still writes a tracked file and
still blocks the merge. That is not the #432 defect: the write is necessary,
happens once per repository rather than fleet-wide on a cosmetic change, and
after the anomaly change below it names itself. Tolerating it would mean
teaching a failed-closed gate to forgive writes by content inspection, in two
processes.

## Second change: name the writer when the tree is dirty

Requirement 2 stands even after the write disappears, because a first-ever
install still legitimately adds the block. `refresh_obsidian_kb` parses the
helper's `gitignore: <state>` line and sets a run-scoped flag on any state that
means a write happened — `added`, `updated`, `local-exclude added`, or
`local-exclude updated` (`ignore_change_state`). A symlink conflict wrote
nothing and must not set it. Both `working_tree_dirty` anomalies then report the dirty
paths (bounded list) and, when the flag is set, that this run's KB refresh wrote
the ignore file.

Bounding: at most 10 paths, then `and N more`, so the anomaly stays a diagnostic
rather than a diff dump.

## Third change: written-down ownership of the managed block

Issue #432 records two owners fighting over the same bytes: the KB writer and
whole-file Trellis provenance hashing (`.github/trellis-provenance.json`), whose
drift guidance says revert — which the next refresh undoes. The rule to record:

> The pack owns the bytes between `# sd-ai-command-pack obsidian-kb start` and
> `# sd-ai-command-pack obsidian-kb end`. A provenance mismatch confined to that
> block is reconciled by rehashing `.gitignore`, never by reverting it. Content
> outside the markers stays repo-owned.

Recorded where the pack can record it: the KB ownership reference
(`templates/.agents/skills/sd-update-spec/references/obsidian-kb.md`) and the
writer's module docstring.

The provenance half is consumer-owned and out of reach from here:
`check-trellis-provenance.py` and the guidance that cites it live in each
consumer's own repository, which the pack updates only through its installed
payload — consumer product code and docs are never edited by pack or fleet work.
`se-ai-command-pack` has already solved it: its `CONTRIBUTING.md:257-263` hashes
only the repo-authored remainder and states that revert-don't-rehash applies
exactly when the edit lies outside the markers. The pack ships that wording as a
paste-ready note for consumers whose provenance still hashes the whole file,
rather than pretending it can fix them from here.

## Contracts and compatibility

- Helper exit codes, report fields, and the `gitignore:` state vocabulary are
  unchanged; `present` simply becomes the reported state in the case that used
  to report `updated`.
- `--check` follows: a stale banner reported `updated`, which failed the
  `ignore entry is not current` conflict at
  `templates/scripts/sd-ai-command-pack-update-spec-kb.py:1505` and surfaced as
  the `knowledge.obsidian-kb` row in `sd-check`. It now reports `present` and
  raises no conflict. That is the point — cosmetic drift stops being a finding
  — but it is a visible behaviour change and gets its own test.
- `sd-ai-command-pack-fleet-publish.py` runs the helper so a block rewrite lands
  inside the work commit. Verified it needs no rewrite to occur: the
  `block_written` comparison only shapes a warning on a nonzero helper exit
  (`scripts/sd-ai-command-pack-fleet-publish.py:298-315`), and exit 0 returns
  `refreshed` regardless of whether bytes changed. No change there.
- Dry-run parity: `planned_ignore_file_state` must apply the same predicate, or
  `--dry-run` would promise a write the real run no longer performs.
- No change to KB content generation, copy pruning, symlink handling, or the
  local-exclude path (`.git/info/exclude` is untracked and unaffected either
  way, but it goes through the same function and must behave identically).
- Payload change: `manifest.json` bump plus CHANGELOG entry; `templates/` is the
  source of truth and `scripts/` is regenerated.

## Failure modes considered

- **Incomplete markers** (start without end): unchanged — still `SystemExit`.
- **Symlinked ignore file**: unchanged — still a reported conflict, no write.
- **Block present but entry commented out**: treated as deficient (case 2) and
  repaired, because the ignore is not in effect.
- **Duplicate managed blocks**: `merge_kb_ignore_block` already collapses to the
  first start / first end pair; the predicate reads the same span, so a
  malformed double block still routes to the rebuild path.

## Rollout

Ships in the next pack release and reaches consumers through the normal fleet
refresh. No migration: a consumer carrying an old banner keeps it, and its tree
goes clean the moment this release is installed.
