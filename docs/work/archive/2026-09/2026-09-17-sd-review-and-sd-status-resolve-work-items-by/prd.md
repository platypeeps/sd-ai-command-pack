---
title: sd-review and sd-status resolve work items by checkout path, so a runner clone sees no item
created: 2026-09-17
status: done
---

# PRD — sd-review-and-sd-status-resolve-work-items-by

## Problem

The readers that pick a work item key its row by the path of the checkout
they run in, and a runner clone is never at that path.

`sd-review --scope planning` picks the active item through
`source:bin/sd_lib.py::work_items` in `source:bin/sd-review::resolve_subject`
and refuses with "no planning or in_progress work item under docs/work" when
the list is empty, in the same function. `sd-status` enumerates the same way
(`source:bin/sd-status::work_section`). Both reach
`source:bin/sd_lib.py::Rows`, whose base is the checkout's own main worktree
root (`Rows.__init__` sets `self.base` from `main_worktree_root`), so every
row key it builds is `<this checkout>::docs/work/<item>/prd.md`
(`Rows.external_id`). The rows were written under the registered path. A clone at another path builds keys nothing ever wrote, is
told "the database holds no docs/work row" for every item, and reports each
one `unknown`.

The writer does not have this defect. `sd work register` resolves the
checkout it stands in to the registered repository by its origin URL
(`source:bin/sd_work.py::_register` calls `sd_db.repos.registered_for`), so a
clone can register a folder; it cannot then read the row it made.

Measured 2026-09-17 at pack `22183d3c`, with sd:981's own planning run,
which the dashboard dispatched into a clone at
`/Volumes/sd-work/worktrees/981/10-1-44394d0e746a4d369ec0bd7bb24d25be`:

| Reader | From the registered checkout | From the clone |
|---|---|---|
| `sd-status`, `status-unreadable` findings | 7 | 13 |
| `docs/work` folders, active | 13 | 13 |
| `docs/work` rows for the pack | 10 | 10 |

The 7 are folders with no row on either side. The other 6 have rows, and
the clone cannot see them. The row for this item, once registered, is one
of them, which is why this plan's own `sd-review --scope planning` refuses
(see the Log). The 442 run (exec note 709, merged as 2639a7aa) hit the
same refusal and its pages went to the send box unreviewed.

## Requirements

1. A reader that opens the database resolves the checkout it stands in to
   its registered repository the way `sd work register` does: by the path
   when the path is itself registered, otherwise by the origin URL, and to
   itself when neither matches. Readers in scope: `sd-review --scope
   planning`, `sd-status` (including its `status-unreadable` check), and
   `sd-note` / `sd suggest`, which reach a row through
   `source:bin/sd_handoff_rows.py::item_for`.
2. One resolver, in `bin/sd_lib.py`, that `Rows` and `item_for` both call.
   The rule is the library's (`registered_for`); the pack does not restate
   it, and `sd_work.register` keeps calling the library directly.
3. A checkout of some *other* remote, or with no remote, still keys by its
   own path and reads no row that is not its own. The fix widens what a
   clone of the registered remote can read; it does not let any checkout
   speak for any repository.
4. A linked worktree keeps reading its main checkout's row, as today.
5. A library without `registered_for` keeps today's path-keyed behaviour
   rather than raising; the CI pin (system `717b8e32`) carries it, and
   `sd_work.REGISTER_NEEDS` already names it, so this is a guard for an
   older machine and not a second code path anyone runs on purpose.
6. `bin/sd-review` does not change. The pick reads through
   `sd_lib.work_items`, so the fix lands in the shared library and the
   sensitive, owner-merged file is not on the diff.

Assumptions, kept apart from the requirements: the runner clone has an
`origin` remote naming the registered repository's remote (the dashboard's
clone does: `git@github.com:platypeeps/sd-ai-command-pack.git` on both
sides); `same_remote` normalises only a `.git` suffix and a trailing slash,
so an ssh clone of an https-registered repository still resolves to itself,
and that is the library's rule to widen, not this item's.

Out of scope, named so nobody reads their absence as an oversight:
`sd task add --here` and `sd task edit --belongs-to`
(`source:bin/sd_work.py::_task_repo`, `source:bin/sd_work.py::_belongs_to`)
still key by path; they are
writers of other rows and R10-D6 was answered for them separately.
`source:bin/sd_handoff_rows.py::brief_for` keys `note_brief` by path and
briefs nothing in a clone; a follow-up note on sd:981 records both.

## Acceptance criteria

- [ ] `tests/test_status_source.py`: a test clones the fixture repository
      from a bare remote both checkouts share, registers only the original,
      and `sd_lib.Rows(clone).external_id(clone_item)` equals the
      original's identity; `work_items(clone)` reports the item's row
      status, and the `picked()` list from the clone names the item.
- [ ] `tests/test_status_source.py`: from the same clone, `sd-status`'s
      `work_section` renders no `status-unreadable` row for the item.
- [ ] `tests/test_status_source.py`: a clone whose origin names a remote no
      registered repository carries reports the item `unknown` with "holds
      no docs/work row for `<clone path>::...`", the sentence today's
      reader prints; and a checkout with no `origin` does the same.
- [ ] `tests/test_status_source.py`: the existing linked-worktree test
      (`test_a_linked_worktree_reads_the_main_checkout_s_row`) stays green.
- [ ] `tests/test_sd_handoff_rows.py`: `item_for` from a clone of the
      registered remote returns the row `register` made from the original.
- [ ] `sd-status` run from
      `/Volumes/sd-work/worktrees/981/10-1-44394d0e746a4d369ec0bd7bb24d25be`
      reports 7 `status-unreadable` findings: the registered checkout's
      count at `22183d3c`, and 14 from the clone before the change (13
      before this folder had a row, see the Log). Both numbers recorded
      in the Log with the commit they were measured at.
- [ ] `sd-review --scope planning --explain` run from that clone does not
      print "no planning or in_progress work item under docs/work"; its
      explanation names this item.
- [ ] `git diff --stat main -- bin/sd-review` prints nothing.
- [ ] `make check` rc 0, and `bin/sd-docs-lint` ends `sd-docs-lint: clean`.

## References

- sd:981, `sd store item 981`: the row this plan was seeded from, filed by
  the audit-438 run on 2026-09-17 at pack `ea32e76a`, system `a0054d54`.
- The 442 run, exec note 709, merged as `2639a7aa`: the refusal seen from a
  clone, with no row filed for it at the time.
- `sd_db.repos.registered_for` and `sd_db.repos.same_remote`, the system
  library's resolver and comparison, as pinned by
  `.github/workflows/tests.yml` at system `717b8e32`.
- R10-D6: the working directory selects the repository. `registered_for`'s
  docstring says why that is not the same as the working directory *being*
  the repository's recorded path.

## Review

Planning review, 2026-09-17. The point is the development flow's *prd and
design* row of `.claude/rules/sd-planning-adversarial-review.md`, cap 5.

Host review, round 1, against pack `22183d3c`:

- Requirement 3 was added after checking `registered_for`: it resolves an
  unregistered checkout to itself, so a foreign clone cannot adopt the
  pack's rows. Verified by reading `registered_for` in the installed
  library (`same_remote` on a `NULL` remote is false).
- The first draft named the module-level
  `def external_id(root: pathlib.Path | str, item_dir: pathlib.Path)` in
  `bin/sd_lib.py` as a place to change. Rebutted: its only caller is the no-`item_for_artifact` fallback
  in `sd_handoff_rows`, it takes no connection and cannot ask the `repo`
  table; the fix lives where the connection is (`Rows`, `item_for`).
- Whether the row's `repo` column matters for `Rows.item`: it does.
  `item_for_artifact(connection, repo, path)` filters on `repo`, so the
  resolved base must be the registered path exactly as the `repo` table
  spells it, which is what `registered_for` returns.
- The `no marker asks git nothing` guarantee
  (`source:tests/test_status_source.py::test_no_marker_asks_git_nothing`) is
  unaffected: `Rows` is not built
  without a `row` marker, and the one `git remote get-url origin` call
  this adds runs once per enumeration inside `Rows.__init__`.
- Not on a sensitive path: the changed set is `bin/sd_lib.py`,
  `bin/sd_handoff_rows.py`, and tests, none listed under `sensitive` in
  `.github/sd-review.json`. No `C-*` ledger and no cross-artifact sweep
  are owed under the contract; the figures 7, 13, 10 and 6 appear in
  `prd.md` only, and `design.md` cites the table rather than restating it.

Registry lane, `sd-review --scope planning`: **failed**, on this item's
own defect. Run from the clone at pack `22183d3c` after `sd work register`
made row sd:988 for this folder, it printed
`sd-review: error: no planning or in_progress work item under docs/work`
and exited 2. The lane was not skipped; it could not find the item it was
asked to review, which is the finding this plan exists to fix. No approval
is claimed from it. The item stays `planning`; the lane is re-run from the
registered checkout, or from a clone once step 1 of `implement.md` lands.

No blocking finding is open. The item is not promoted, for the reason
above, and `planning → ready` is the first step of the implementation
once the registry lane has run.

## Log

- 2026-09-17 created from sd:981 by an unattended `sd-plan` run in a
  dashboard clone; the checkout choice is recorded as decision note 2702
  on sd:981. The three pages were written together as one edit batch.
- 2026-09-17 measured at `22183d3c`: `sd-status` from the clone, 13
  `status-unreadable`; from `/Users/sven/repos/platypeeps/sd-ai-command-pack`,
  7. After `sd work register` made sd:988 for this folder, the clone
  reports 14: the new row is keyed by the registered path like the other
  six, and this folder exists only on the branch, so the registered
  checkout's 7 is unchanged. `sd-review --scope planning` from the clone
  refused with the sentence quoted under Review, exit 2.
- 2026-09-17 implemented on `feat/sd-981-registered-base` over pack
  `10164281`: the five unit-test criteria above hold in
  `tests/test_status_source.py` and `tests/test_sd_handoff_rows.py`, and
  `bin/sd-review` is not on the diff. The two live criteria, `sd-status`
  and `sd-review --scope planning --explain` from the runner clone, wait
  for the owner's step 4; the counts written there stay unmeasured on this
  branch. The citations of these pages were moved to anchor form first,
  which took `tests.test_doc_citations` from `FAILED (failures=5)` to `OK`.
