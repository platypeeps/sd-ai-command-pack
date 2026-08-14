# Give the append-only journal gate a workspace developer directory migration path

Owns issue #401.

Closure note (2026-08-14): #401 was closed as `not planned` when tracking
moved to the Trellis task tree. The defect is unchanged and this task still
owns it. Reference it as a bare `#401` in the shipping PR — never with a
closing keyword, per `08-14-pack-paper-cuts` item 4. The original line here
read "Closes platypeeps/sd-ai-command-pack#401", which is the phrasing that
caused the accidental close item 4 exists to prevent.

## Problem

A workspace developer directory can be created by accident and never retired.
`.trellis/workspace/<name>/` is append-only history, and no gate accepts a
commit that moves its sessions somewhere else, even when the move preserves
every session verbatim and is diff-verified in the same commit.

Observed in a consumer repo on pack v0.64.32 (issue #401): an init-day orphan
identity `.trellis/workspace/Sven Delmas/` held one 44-line session from
2026-07-17 while `.trellis/.developer` had said `name=sdelmas` since the same
day. A migrate-then-remove commit — content copied verbatim into the active
developer's workspace, directory removed, rename detected by git at 62%
similarity — failed with:

```
.trellis/workspace/Sven Delmas/journal-1.md:10 removes historical Session 1
from origin/main; Trellis journal history is append-only. Restore that session
and edit the intended current session by heading.
```

The consumer shipped the only compliant workaround: retain the directory
byte-identical and annotate its scaffold `index.md`. That leaves a permanently
dead directory that every future hygiene pass has to re-explain.

## Three gates block the migration, not one

The issue reports the first. Enumerating the callers of the history comparison
and the CI classifier finds two more, and a fix that clears only the reported
one still fails on push.

**G1 — `checkTrellisJournalRecords`**
(`scripts/sd-ai-command-pack-review-preflight.mjs:4473-4505`). The comparison
loop is keyed by developer directory: `developerRelatives` is built from the
union of current directories and `dirname(...)` of the baseline journal files,
and `findHistoricalTrellisJournalSessionEdits`
(`scripts/sd-ai-command-pack-review-preflight.mjs:5655-5686`) is invoked once
per directory with only that directory's sessions. Preservation under a
*different* directory is invisible to it by construction, so the removal is
reported as `removed` regardless of where the content went.

**G2 — `validateBookkeepingJournalBundle`**
(`scripts/sd-ai-command-pack-review-preflight.mjs:2565-2571`). Before any
session comparison runs, every workspace entry whose status starts with `D`,
`R`, or `C` is rejected outright:

```js
add(
  'journal_history_mutated',
  entry.oldPath || entry.path,
  'journal and index history is append-or-update only; deletion, rename, and copy are not allowed',
);
```

The same function's path filter
(`scripts/sd-ai-command-pack-review-preflight.mjs:2573-2575`) additionally
emits `journal_scope_invalid` for any workspace path that is not
`journal-N.md` or `index.md`. That is a hard constraint on the solution space:
issue #401's proposal 2 (a `MIGRATED.md` tombstone) cannot be adopted without
widening this filter too, and widening it weakens an unrelated gate.

**G3 — CI**
(`.github/scripts/bookkeeping_ci_scope.py:240-241`). Any pushed delta touching
`.trellis/workspace/` sets `validation_mode = "planning"`, which runs the
planning bundle validator and therefore G2. A local receipt that passes is not
enough; the push is re-validated from the other side.

## Requirements

1. `checkTrellisJournalRecords` must accept the removal of a developer
   directory when every removed baseline session is preserved, in the same
   working tree, under another developer directory — and must keep failing
   when even one removed session has no preserved counterpart.

2. `validateBookkeepingJournalBundle` must accept the same shape over its own
   diff evidence, so the finalization receipt and CI agree with G1. The blanket
   `D`/`R`/`C` rejection may narrow only for a delta that satisfies the same
   preservation proof; every other deletion, rename, and copy still fails.

3. Preservation must be proven from content, never from a path, a git rename
   score, a commit message, or an author-supplied assertion. The proof compares
   the removed session's own bytes against the bytes of a session present in
   the new location.

4. Both gates must fail closed. An unreadable destination, an unparsable
   session, a partial match, or an ambiguous one is a failure, not a pass.

5. The failure diagnostics must name what is missing. A migration that fails
   must say which removed session had no preserved counterpart and where the
   check looked, so the author can fix the commit rather than guess.

6. The direction the gate defends must not widen. Editing a historical session
   in place, dropping one without preserving it, and rewriting an earlier
   session's content all still fail with their current reason codes.

## Constraints the design must resolve

These are known blockers on the obvious implementation, recorded so `design.md`
addresses them rather than rediscovering them.

- **Session numbers collide.** `parseJournalSessionsFromText`
  (`scripts/sd-ai-command-pack-review-preflight.mjs:5597-5616`) slices each
  session's `content` starting at its `## Session N: <title>` heading, so the
  number is inside the compared bytes. A session migrated into a directory that
  already holds sessions `1..N` must be renumbered, which changes `content` and
  defeats a naive verbatim comparison. The design must state exactly what is
  normalized away and why that does not create a hole — `normalizeJournalSessionContent`
  (`scripts/sd-ai-command-pack-review-preflight.mjs:5688-5695`) currently
  normalizes only line endings and trailing whitespace.

- **A provenance header is expected.** The consumer's migration attached one.
  If the design forbids added text, real migrations cannot use the affordance;
  if it allows arbitrary added text, the preservation proof weakens. Pick one
  and justify it.

- **The destination `index.md` must stay consistent.**
  `validateTrellisJournalSessions` compares journal sessions to the sibling
  index for the same directory. A migrated session arrives with commits from
  another identity's history; the design must state what the destination index
  is required to contain.

- **A migration commit still needs its own journal session.** G3 routes the
  push into planning-mode validation, and
  `validateBookkeepingJournalBundle` requires a new completed session
  (`journal_session_missing`). The migration and its record land together; the
  design must confirm the affordance survives that combination rather than
  assuming a lone migration commit.

## Acceptance criteria

- [ ] A fixture where a developer directory is removed and all of its baseline
      sessions are preserved verbatim under another developer directory
      produces a `status: valid` pre-archive result, with no
      `Trellis journal history is append-only` failure.
- [ ] The same fixture produces a `status: valid` final-bundle result, with no
      `journal_history_mutated` and no `journal_scope_invalid` reason code.
- [ ] A fixture that removes a directory while preserving only some of its
      sessions still fails, and the diagnostic names the unpreserved session by
      file and number, asserted against the emitted message rather than by
      reading the code.
- [ ] A fixture that removes a directory and preserves nothing still fails with
      the current reason codes.
- [ ] A fixture that edits a historical session in place still fails. This is
      the direction the check defends and it must not be widened.
- [ ] An unrelated workspace deletion, rename, or copy — one with no
      preservation proof — still fails `validateBookkeepingJournalBundle` with
      `journal_history_mutated`.
- [ ] The consumer-side workaround is retired in documentation:
      `templates/docs/SD_AI_COMMAND_PACK.md:853-856`, the paragraph that
      currently states only "Journal history is append-only", also states the
      sanctioned migration shape, so a future hygiene pass finds it without
      reading the validator.

## Out of scope

- The machine-scope installer's `machine-install.intent.json` backup records.
  That is `.trellis/tasks/08-09-force-backup-journal`, a different subsystem
  that shares only the word "journal".
- Retiring the orphan directory in any consumer repository. This task ships the
  affordance; using it is separate, consumer-owned work.
- Any change to `validateTrellisJournalSessions`' placeholder, completion, or
  commit-list rules beyond what requirement 2's narrowing forces.
- An allowlist input (issue #401's proposal 3). It is the weakest of the three
  and is rejected here: it proves nothing about content and adds a config
  surface that outlives the one-time migration it authorizes.

## Notes

- Complex task. `design.md` and `implement.md` are required before
  `task.py start`; the constraints section above is the input to `design.md`.
- Priority P2. Real gap, but one-off migration friction on a rename, not a
  fleet-wide blocker. It does not gate the thin rollout.
- `08-12-journal-cite-lifecycle-correction`'s PRD refers to this task for the
  migration-path question. Its own criterion about reconciling a historical
  session is not satisfied by this work — that criterion concerns editing a
  committed session in place, which requirement 6 keeps failing.
