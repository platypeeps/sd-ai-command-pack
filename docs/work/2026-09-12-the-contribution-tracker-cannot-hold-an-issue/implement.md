# Implement — the-contribution-tracker-cannot-hold-an-issue

## The landing order is the plan

Six steps across two repositories. Steps 2, 3 and 5 are in `platypeeps/system`
and belong to that repository's own work item (design decision D8); they are
listed because the pack's steps are only correct in this order.

The order exists because of one measured fact: pack CI pins the library at
`ref: 3c4c723a724c5922fb464042a036ded0408a3d51`
(`.github/workflows/tests.yml:84`) and installs a built copy from that pin. A
pack reader naming a field the pinned library does not carry fails in CI and
passes on every developer machine, because every local checkout already has the
newer library. The comment at `.github/workflows/tests.yml:74-79` records that
happening once already.

## Step checklist

- [ ] **1 — sd:602 first (pack).** Replace the two recited field tuples at
      `bin/sd-status:3248-3250` and `bin/sd_work.py:417-418` — both in the
      **text** renderers — with a field-agnostic projection, and add a test
      asserting the *set* of keys the default report renders. Do not touch the
      `--json` paths: `bin/sd_work.py:402-404` and `bin/sd-status:3343-3344`
      never reach either tuple (design decision D4), so a change or a test
      there is a no-op. Independently landable and independently green: it
      changes no library code and no pinned behaviour. If sd:602 is not taken
      first, step 6 grows the field-set assertion instead, and its pull request
      says it paid the tax rather than removed it.

- [ ] **2 — library: the row can hold an issue (system).** `ISSUE`, its own
      validator beside the one at `sd_db/contributions.py:42`, `issue_url` and
      the three `draft` fields in the allow-list at
      `sd_db/contributions.py:30-31`; the identity dichotomy at
      `sd_db/contributions.py:189-192` becomes a three-way choice; mutual
      exclusion of `pull_url` and `issue_url`; a uniqueness guard for
      `issue_url` beside the two at `sd_db/contributions.py:219-224`; the
      `draft_path` digest re-checked on read the way evidence artifacts are at
      `sd_db/contributions.py:126-142`; `_key` at `sd_db/contributions.py:49`
      extended for a filed issue — and *not* for a draft, which is already
      keyed `item:<id>` by `sd_db/contributions.py:615-618`; the projection's
      second pass at `sd_db/contributions.py:622` taught which keys are its
      own. Also in this step, because it changes the same projection:
      requirement 10's lane vocabulary, as decided in `design.md` **D10**: add
      a fourth terminal lane `closed` to `LANES` at
      `sd_db/contributions.py:32`, at an index at or after every non-terminal
      lane, and branch to it at `sd_db/contributions.py:580` instead of falling
      through to `awaiting_them`. Do not settle for the fallback: it is already
      today's behaviour, so that version of the step is a no-op. Assert that
      the sort at `sd_db/contributions.py:630` stays total. In the same edit,
      replace the `"Closed without merge"` reason at
      `sd_db/contributions.py:367` on the issue path with the close reason
      (`completed` or `not_planned`); `merge` is not issue vocabulary in the
      operator-facing text either. Green on
      its own: a row can be registered, listed and filed without any collector
      existing.

- [ ] **3 — library: the collector watches it (system).** `observe_issue`
      beside `sd_db/contributions.py:412`; `_issue_attention` beside
      `sd_db/contributions.py:323`; the two new event kinds added to the
      accepted set at `sd_db/contributions.py:451-452`; a
      `repository.issue(number:)` timeline query beside the pull-request one at
      `sd_db/contribution_github.py:25-37`; the refresh queue at
      `sd_db/contribution_sync.py:97` taught to queue issue keys; the
      `depends_on` kind `issue` in all **nine** places enumerated in `design.md`
      D2 — including the four where omission is silent rather than loud
      (`sd_db/contributions.py:522`, `sd_db/contribution_sync.py:181-182`,
      `sd_db/contribution_sync.py:74`, `sd_db/contributions.py:536-537`); and
      the widened comment trigger on the issue path per `design.md` D3. This is the natural second seam D7 names — if step 2 has shipped,
      sd:244 already has a durable home even if this step slips.

- [ ] **4 — move the pin (pack).** Bump
      `.github/workflows/tests.yml:84` to the system commit that carries steps
      2 and 3. Its own step because it is the one that can be forgotten, and
      forgetting it makes step 6 fail in CI only.

- [ ] **5 — register the rows (system).** Migrate sd:244 to an issue row
      keeping item ID 244, and register
      `mProjectsCode/obsidian-meta-bind-plugin#644`. Last, so the rows are
      created under the finished shape rather than migrated twice.

- [ ] **6 — the pack shows it (pack).** Whatever remains after step 1 —
      documentation in `skills/sd-status/SKILL.md`, and the `key` help string
      at `bin/sd_work.py:483`, which hard-codes both existing key forms in its
      text and will otherwise tell the operator that an issue key does not
      exist.

## Verification

Named before the work, with the result that means failure.

**Gates that must stay green on the pack, every step.**

- `bin/sd-docs-lint` exits 0. Any `FAIL` line is failure.
- `python3 -m pytest tests/test_doc_citations.py tests/test_loc_caps.py` — the
  baseline on this branch at cc93ea85 is `53 passed, 21 subtests passed` and
  `11 passed, 2 subtests passed`. Fewer passes, or any failure, is failure.
- `make test` is the authoritative suite. A bare `pytest tests/` is **not** a
  valid check here: it reports 21 collection errors at cc93ea85, every one of
  them `ModuleNotFoundError: No module named 'sd_db'`, because this pack cannot
  import the library without the system checkout. That count is the baseline to
  compare against, not a pass.

**Step 1.** A test that registers a contribution carrying `blocking_labels` —
allowed at `sd_db/contributions.py:31`, projected at
`sd_db/contributions.py:599`, and named in neither tuple — then asserts the
value appears in the **default, non-`--json`** output of both
`sd task contribution list` and `bin/sd-status`. Before the change that test
fails on both; after it, both pass. Two forms of this check do not work and
were rejected: one written against `--json` passes before and after, because
neither JSON path reaches a tuple; and one checking only the four fields this
item adds would pass without removing the tax.

**Steps 2 and 3.** The library's own suite, run in the system repository. This
lane cannot run it: `sd_db` is not importable in this worktree, and the system
checkout is shared and must not be written to. That is a stated gap, not a
check — whoever takes the system item runs it and reports it there.

**Step 4.** The decisive line is CI's own: after the bump, the
`Install sd_db from that checkout` step must succeed and the suite must report
zero skips, because `.github/workflows/tests.yml:114-119` fails the job on any
skip. A green local run proves nothing about this step — that is precisely the
failure mode being guarded.

**Steps 5 and 6.** `sd task contribution list` shows both seed rows, sd:244
keeping item ID 244. Both issues were re-measured OPEN on 2026-09-12; if either
has closed by the time the step runs, re-measure and record the new state
rather than carrying this document's number forward.

**What cannot be verified here, and by whom.** Whether a maintainer comment on
a real upstream issue reaches needs-you is an end-to-end check against GitHub
with a real event; it needs the operator's credentials and a real comment, and
no fixture substitutes for it. The acceptance criterion stands, and it is the
operator's to close.

**Cross-artifact numeric sweep.** Every count in this item's three documents is
a measurement against a named commit: 8 allow-list names against 17 and 10
recited projection keys, 9 dependency enumerations, 7 accepted event kinds, 21
collection errors, 22 test modules importing `sd_db` by `import`/`from` (28 by
string mention), 4 lanes today and 5 after D10. Before this item's pull request merges, and again
before the system item's, re-grep each and confirm all three documents agree. A
count corrected in one artifact and left standing in another is the usual way
this fails.
