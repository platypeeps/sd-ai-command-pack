---
title: Journal sessions are silently corrupted by a text merge of two branches
status: planning
created: 2026-08-28
---
# Journal sessions are silently corrupted by a text merge

## Goal

Two branches that each append a journal session must not produce a journal whose
session bodies sit under the wrong headers. The corruption must be prevented, or
failing that, refused at merge time rather than caught downstream.

## Background

`add_session.py` appends a session block to the active journal file and adds a
matching row to `index.md`. Every branch appends at the same place — the end of
the file — so two branches that both finalize produce changes git sees as
adjacent additions in one hunk.

`index.md` conflicts loudly, because the session-history table, the total count,
and the line-count row all change on both sides. The journal file does not. Git
resolves it as a clean auto-merge and interleaves the two session blocks: it can
keep one session's header and drop its tail, leaving the following header
attached to the wrong body.

The result is a journal that reads plausibly and is wrong: a session header
attributed to commits that belong to a different session.

## Evidence

Observed 2026-08-28 merging `origin/main` into
`chore/record-codeql-redos-gate-task` (rwbp-website PR #279). Both branches had
appended a session to `journal-3.md`. Git reported one conflict, in `index.md`
only:

```
Auto-merging .trellis/workspace/sdelmas/index.md
CONFLICT (content): Merge conflict in .trellis/workspace/sdelmas/index.md
Auto-merging .trellis/workspace/sdelmas/journal-3.md
```

`journal-3.md` merged "cleanly" into this:

- line 10 — `## Session 99: Record 08-24-codeql-redos-gate planning artifacts`,
  its Testing and Next Steps sections and its commit list dropped
- line 26 — `## Session 98: Refresh sd-ai-command-pack to 0.71.62`, carrying
  session 99's commit `c453c265...`

Caught only by the final-bundle validator:

```
journal_history_mutated  journal-3.md  Session 98 was modified
journal_index_mismatch   index.md:36   Session 99 commits c453c265... do not match journal-3.md:10 (none).
journal_index_mismatch   index.md:37   Session 98 commits 554d0b02... do not match journal-3.md:26 c453c265...
```

Recovered by restoring both files from `origin/main` and re-running
`add_session.py`. That renumbered the session to 100, leaving a gap at 99.

## Why this matters more than a lane stall

Every other defect found in this rollout stalls a lane. This one writes wrong
history and then merges it. The validator caught it here because a planning
finalization runs the final-bundle gate; a branch that merges main after
finalizing, and does not re-run that gate, has nothing standing between the
corruption and `main`.

## Requirements

- Prevent the interleave. A merge driver registered for the journal path, a
  per-session file layout, or an append format git cannot silently splice would
  all satisfy this; the choice belongs in design.
- If prevention is partial, the corruption must be refused at merge time rather
  than left for a later validator. Note that the existing validator already
  detects it — the gap is that nothing forces it to run on this path.
- Preserve the fingerprint comments (`<!-- trellis-session: v=2 fp=... -->`);
  whatever detects the corruption should be able to use them.
- Session numbering must survive a rebuild without leaving a gap, or the gap
  must be documented as acceptable.

## Non-goals

- Backfilling journals that already lag behind their repository's history for
  unrelated reasons.
- Repairing the session-99 gap left by this incident.

## Acceptance Criteria

- [ ] Two branches each appending a session, then merged, produce a journal
      where every session header retains its own body and commit list — verified
      by constructing that merge in a fixture, not by inspecting a past one.
- [ ] The failure mode, if it can still occur, is reported at merge time and
      names the affected session numbers.
- [ ] `index.md` and the journal agree on every session's commits after the
      merge.
- [ ] A rebuild after a corrupted merge produces contiguous session numbering,
      or the numbering rule is documented.
