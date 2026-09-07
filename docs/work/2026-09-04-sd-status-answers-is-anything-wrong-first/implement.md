# Implement — sd-status answers "is anything wrong" first

## Budget

The whole change lands in `bin/sd-status`, `skills/sd-status/SKILL.md` and
`tests/test_sd_status.py`. `bin/` measured **12,416** lines on `8cf99431`
against the 14,000 ceiling in `tests/test_loc_caps.py`, so there are 1,584
lines of headroom; this item claims at most **600** of them and the ceiling is
what checks it, not this sentence. `dashboard/` is not touched at all, so
neither `DASHBOARD_CAP` nor `DASHBOARD_CODE_CAP` moves.

## Step checklist

- [ ] **1. The inventory producer.** Add `CLASSES`, `EXCLUDED`, `action_id()`
      and `actionable_inventory()` to `bin/sd-status`, plus the per-class
      producers. Landable and green on its own: nothing renders it yet, and
      `python3 -m unittest tests.test_sd_status` still passes.
- [ ] **2. The merged-branch derivation, two-tier.** `branch_landed(root,
      branch, default, pulls)` — ancestor test, then the `--no-renames`
      path-equality test, then a pull request matched by `headRefName` whose
      `mergedAt` is set, whose `baseRefName` is the default branch, and whose
      `headRefOid` equals the branch tip. Returns `landed` / `not landed` /
      `unknown`, never a bare boolean. Regression cases, both from C-19: a
      branch extended after its PR merged must not report landed, and a PR
      merged into a non-default base must not count.
      Verified against this checkout's five squash-merged branches:
      tier 1 resolves three, tier 2 resolves the remaining two, ancestry
      resolves none.
- [ ] **2b. The three-state banner.** `clear` / `n finding(s)` /
      `unchecked: reason` per class, with unchecked counted separately from
      clear in the summary line.
- [ ] **3. The concern-ledger scanner, by row shape.** One
      `git grep -n -E '^\s*(\|\s*|[-*]\s*)?(\*\*)?C-[0-9]+\b' -- docs/work` over
      the index, archived items included. Classify each row against the
      five-vocabulary `DISPOSITIONS` table; an open token beats a closing one on
      the same row; a row with no recognised token becomes an
      `unreadable-concern-row` finding rather than being dropped. Headings are
      not read at all — 75 distinct `##` headings match /review|concern/ and
      only a handful are ledgers. Four rules the prototype earned, all four
      required: dedupe by `(full item path, C-id)`; absorb continuation lines to
      the next blank or next candidate; shape precedence table > bold > prose;
      and never truncate the item path (keying on `split("/")[2]` collapses 487
      archived items into one bucket and loses `C-19` entirely). Expected on
      today's corpus: 245 concerns, 206 closed, 23 open, 16 unclassifiable.
      Note: `[[:space:]]` in the `git grep -E` pattern matches nothing; use ` *`.
- [ ] **3b. `accepted-gap-standing`.** Each `.github/sd-status.json`
      `accepted_gaps[]` entry becomes an inventory row carrying `since` and
      `until`, rank 45, not abnormal.
- [ ] **4. The three new sections and the fixed skeleton.** `_render_banner`,
      `_render_pending`, `_render_next`, `_render_threads`, and an empty-state
      sentence for each of the eight existing sections that could vanish.
- [ ] **5. `--actions`, and the `--json` keys.** `abnormalities`, `actions` and
      `next` added to `collect()`; `SCHEMA_VERSION` bumped to 3, because
      consumers gain keys and the report gains a section order they may depend
      on.
- [ ] **6. `skills/sd-status/SKILL.md`.** The twelve-section order, the ranking
      table, the id scheme, and the `AskUserQuestion` contract with its
      4-option/4-question limit and the resolution.
- [ ] **7. Tests.** Every new behaviour in `tests/test_sd_status.py` — no new
      module, so `make check`'s `OK` count stays at 40. Named cases, in order of
      what they protect: **(a)** two checks firing on one pull request produce
      two rows with two different ids — C-11's regression, which fails under the
      rejected letter-keyed formula; **(b)** a squash-merged branch is detected
      as landed and an unmerged one is not; **(c)** the `## Review` scanner
      reads both ledger shapes and defaults an unrecognised disposition to
      `unreadable-concern-row`; **(c2)** a class whose data could not be fetched
      prints `unchecked` and is not counted clear; **(c3)** an item that is
      `in_progress` *and* `parked:` *and* under `archive/` at once — the real
      case is `archive/2026-09/2026-08-21-port-integration-only-profile` —
      resolves to exactly one row per firing check and no crash; **(d)** the
      section skeleton is identical for a repository
      with content and one with none; **(e)** the pending cap prints at most 10
      rows and states the suppressed count.

## Verification

Named before the work, and each names its own result.

1. `python3 -m unittest tests.test_sd_status -v` → `OK`, 0 failures, 0 errors.
2. `make -C <worktree> VENV=<shared venv> check` → the tail prints no `FAILED`;
   `grep -cE '^OK' unittest-output.log` prints `40` and
   `grep -c FAILED unittest-output.log` prints `0`. Baseline on `8cf99431` was
   measured, not assumed: 40 and 0.
3. `python3 -m unittest tests.test_loc_caps` → `OK`. This is the check that
   enforces the 600-line budget above; the budget is not separately asserted.
4. `./bin/sd-status --json | python3 -c "..."` counting
   `check == 'branch-already-merged'` findings → `1`, naming
   `the-plan-interview-is-one-sentence`. This is the criterion that would have
   failed under the rejected `--is-ancestor` derivation, so it is the one that
   proves C-1 was actually fixed rather than described.
5. Id stability: `./bin/sd-status --json` run twice, the `id` fields diffed →
   no output.
6. Read-only: `python3 -m unittest tests.test_sd_status.ReadOnlyTests` → `OK`.
   The existing digest test brackets a full run; if any new code path writes,
   this is what says so.
7. Run time: `time ./bin/sd-status >/dev/null` → recorded here after the fact,
   as the evidence rebutting C-4. A wall time over 5 seconds means the concern
   was right and the scanners need narrowing.

**Not verifiable here.** That the report *reads* as a report — that a person
opening it sees the abnormality before anything else — is the user's eyes on the
first real run. And that a calling agent renders four `multiSelect` options from
the pending list is a property of the agent; the skill states the contract and no
test in this repository can assert conformance to it.

## Verification results

Filled in as each check runs, so a claim here is a transcript and not a plan.

- 2026-09-04 baseline, before any code change: `make check` →
  `grep -cE '^OK' unittest-output.log` = `40`, `grep -c FAILED` = `0`.
