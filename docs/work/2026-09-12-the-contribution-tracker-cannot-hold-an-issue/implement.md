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
      `bin/sd-status:3248-3250` and `bin/sd_work.py:417-418` with a
      field-agnostic projection, and add a test asserting the *set* of keys a
      row projects. Independently landable and independently green: it changes
      no library code and no pinned behaviour. If sd:602 is not taken first,
      step 6 grows the field-set assertion instead, and its pull request says
      it paid the tax rather than removed it.

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
      requirement 10's lane vocabulary. `LANES` at
      `sd_db/contributions.py:32` has a terminal lane called `merged`, and it
      is the sort key of the whole projection at
      `sd_db/contributions.py:630`; a closed issue must land in a lane that is
      not a lie. Decide it here — a neutral terminal lane, or an explicit rule
      that a closed issue is `awaiting_them` — and assert that the sort stays
      total either way, because every reader depends on that order. Green on
      its own: a row can be registered, listed and filed without any collector
      existing.

- [ ] **3 — library: the collector watches it (system).** `observe_issue`
      beside `sd_db/contributions.py:412`; `_issue_attention` beside
      `sd_db/contributions.py:323`; the two new event kinds added to the
      accepted set at `sd_db/contributions.py:451-452`; a
      `repository.issue(number:)` timeline query beside the pull-request one at
      `sd_db/contribution_github.py:25-37`; the refresh queue at
      `sd_db/contribution_sync.py:97` taught to queue issue keys; the
      `depends_on` kind `issue` in all five places enumerated in `design.md`
      D2. This is the natural second seam D7 names — if step 2 has shipped,
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
  baseline on this branch at 730d4541 is `53 passed, 21 subtests passed` and
  `11 passed, 2 subtests passed`. Fewer passes, or any failure, is failure.
- `make test` is the authoritative suite. A bare `pytest tests/` is **not** a
  valid check here: it reports 21 collection errors at 730d4541, every one of
  them `ModuleNotFoundError: No module named 'sd_db'`, because this pack cannot
  import the library without the system checkout. That count is the baseline to
  compare against, not a pass.

**Step 1.** A test that registers a contribution carrying a field neither
tuple names today, then asserts that field appears in both
`sd task contribution list --json` and `bin/sd-status --json`. Before the
change that test fails on both; after it, both pass. A test that only checks
the four fields this item adds would pass without removing the tax and is not
the check.

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
a measurement against a named commit: 8 / 17 / 10 field names, 5 dependency
enumerations, 7 accepted event kinds, 21 collection errors, 28 test modules
importing `sd_db`, 4 lanes. Before this item's pull request merges, and again
before the system item's, re-grep each and confirm all three documents agree. A
count corrected in one artifact and left standing in another is the usual way
this fails.
