---
title: The contribution row holds a pull request or a branch, and an upstream issue fits neither
created: 2026-09-12
---

# PRD — the-contribution-tracker-cannot-hold-an-issue

## Problem

The 2026-09-10 fleet audit registered six contributions through
`sd task contribution add`: four upstream pull requests and two unfiled
branches. The one open upstream *issue* in the same sweep could not be
registered at all and became a plain task with a followup note — sd:244,
`mindfold-ai/Trellis#531`. Nothing watches it.

The refusal is structural, and all four of its causes were re-measured against
the library at `platypeeps/system@754204d` on 2026-09-12. Each is quoted from
the file rather than from the source issue:

1. The field allow-list rejects the field. `sd_db/contributions.py:30-31`
   defines `FIELDS` as exactly eight names — `local_clone`, `local_branch`,
   `tested_commit`, `pull_url`, `evidence`, `blocked_on`, `depends_on`,
   `blocking_labels`. There is no `issue_url`. `sd_db/contributions.py:186-187`
   raises `unsupported contribution fields` for anything outside it.
2. The URL validator accepts pull requests only. `sd_db/contributions.py:34`
   compiles the pattern
   `https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?\Z`
   and `sd_db/contributions.py:42-44` is the single gate every URL passes
   through.
3. A row with no pull request must have a branch.
   `sd_db/contributions.py:191-192` refuses with
   `unfiled work needs local_clone and local_branch`. An issue you have found
   but not yet filed has neither.
4. Nothing can wait on an issue. `sd_db/contributions.py:160-161` enumerates
   the dependency kinds as exactly `item`, `merge` and `release`.

The consequence is not a missing flag. It is that an upstream issue is invisible
to the four lanes, to the attention events, and to the one-notification-per-event
behaviour the pull-request path already has.

**The source issue reads as a field addition. It is not one, and planning it as
one is how it ships half-done.** Four things make it a model change:

- **The pull request is the model, not a field in it.** The identity rule at
  `sd_db/contributions.py:189-192` is a dichotomy — a `pull_url`, else a clone
  *and* a branch. Uniqueness at `sd_db/contributions.py:219-224` keys on those
  same two things. Observation and attention are pull-request-shaped
  throughout. Requirement 9 enumerates this.
- **Two recited lists, not one.** A contribution field must be named in three
  places across two repositories, and the three already disagree: the enforced
  allow-list holds **8** names at `sd_db/contributions.py:30-31`,
  `bin/sd-status:3248-3250` recites **17**, and `bin/sd_work.py:417-418`
  recites **10**. Both pack-side lists are `for key in (...)` loops guarded by
  `.get()`, so a field the library stores and a reader does not name is dropped
  with no error and no failing test. Adding four fields to the allow-list alone
  would store all four and display none. That tax is filed separately as
  **sd:602**, and requirement 7 sequences it.
- **A five-place enumeration.** The `depends_on` kind is not one list either;
  `design.md` decision D2 names all five and treats them as the same recited-list
  defect rather than as five routine edits.
- **A vocabulary collision.** "Unfiled" is already taken. In the existing model
  it means *a contribution with no `pull_url` yet* — see the refusal text at
  `sd_db/contributions.py:191-192` and the reason strings at
  `sd_db/contributions.py:588-589`. The source issue uses it to mean *an issue
  draft not yet filed anywhere*. These are not the same state, and the existing
  rule actively contradicts the new one: it demands a clone and a branch, which
  an issue draft does not have by definition. Requirement 11 settles the term.

And the whole of it sits on the boundary sd:392 describes, below.

**This work crosses a repository boundary that is itself an open defect.** The
contribution row and its collectors live in `platypeeps/system`, under
`local-sd-db/sd_db/`. Both of this pack's readers live here. sd:392 files that
boundary as a cycle. The boundary verdict, with evidence, is in `design.md`;
the short form is that this item is *sequenced through* that boundary, not
blocked behind it, and the landing order is a hard requirement below.

## Requirements

1. **`issue_url` beside `pull_url`.** A new pattern for
   `https://github.com/OWNER/REPO/issues/N`, validated by its own function.
   The existing URL validator at `sd_db/contributions.py:42` cannot be reused:
   it is also the validator for the `merge` dependency's `url` and the
   `release` dependency's `contains_pull`, so widening it would silently let an
   issue URL satisfy a merge dependency.
2. **Exactly one identity per row.** A row carries a `pull_url`, an
   `issue_url`, or a clone-plus-branch — never two. A row carrying both
   `pull_url` and `issue_url` is refused.
3. **Unfiled issue metadata.** `target_repo` (`owner/repo`), `draft_title`,
   and `draft_path` — an absolute path to the written-up body, carrying a
   SHA-256 digest that is re-checked on read, the way evidence artifacts are
   at `sd_db/contributions.py:126-142`. Filing the draft preserves the item ID.
4. **A key form for a filed issue, and none for an unfiled draft.** These are
   two different answers and conflating them is the easiest mistake here.
   *Unfiled* work is already keyed `item:<id>` alone: the projection at
   `sd_db/contributions.py:615-618` adds the second, `github:`-prefixed source
   only when the row carries a `pull_url`. An unfiled issue draft therefore
   needs no new key form at all. A *filed* issue does: every `github:` key is
   routed through the pull-request URL validator at
   `sd_db/contributions.py:50-51`, so an issue URL cannot be keyed today. The
   refresh queue at `sd_db/contribution_sync.py:97`, which queues a row only
   when its URL matches the pull-request pattern, must queue it too.

9. **The row's shape changes, not just its field list.** The row is not a bag
   of optional fields with a pull request in one of them; the pull request is
   the model. Four consequences, each a required change rather than a remark:
   - The identity rule at `sd_db/contributions.py:189-192` is a dichotomy —
     a `pull_url`, else a clone *and* a branch. A pure issue draft has neither
     and is refused outright by `unfiled work needs local_clone and local_branch`.
   - The uniqueness guards at `sd_db/contributions.py:219-224` key on
     `pull_url` or on `(local_clone, local_branch)`. An issue row matches
     neither, so without a new guard the same issue can be registered twice.
   - Observation and attention are both pull-request-shaped. `observe_pull` at
     `sd_db/contributions.py:412` validates head and base SHAs, `draft`,
     `mergeable` and CI; `_pull_attention` at `sd_db/contributions.py:323`
     derives from reviews, CI transitions, merge conflicts and draft
     conversion. Issues have none of those. They need sibling functions, not a
     widened branch inside these.
   - The projection picks a row's observation by key *prefix*:
     `sd_db/contributions.py:569-571` takes the first source whose key starts
     with `github:` and treats it as the observation, and the sweep at
     `sd_db/contributions.py:622` scans `contribution:github:%` and feeds every
     hit to that same pull-request-shaped builder. A filed issue must therefore
     take its own key prefix rather than sharing `github:`; sharing it produces
     a malformed row and raises nothing. `design.md` D9 treats this as a
     precondition.

10. **`merged` is pull-request vocabulary.** `LANES` at
    `sd_db/contributions.py:32` is
    `{"newly_unblocked", "awaiting_you", "awaiting_them", "merged"}` and is the
    sort key of the whole projection at `sd_db/contributions.py:630`. Issues
    close; they never merge. The lane set must either gain a neutral terminal
    lane or define explicitly which lane a closed issue occupies — and whatever
    is chosen, the sort must stay total, because every reader depends on that
    order.

11. **A distinct word for an issue that has not been filed.** "Unfiled" already
    means "no `pull_url` yet" in this model, and the rule carrying that meaning
    at `sd_db/contributions.py:191-192` would fire on an issue draft, which has
    no clone and no branch by definition. The new state is named **`draft`**
    throughout — field names, refusal text and documentation — and the existing
    unfiled rule is amended to apply only to rows that are neither a filed
    issue nor a draft. Reusing "unfiled" for both is refused: one word for two
    states in the same validator is how the contradiction above became
    invisible in the source issue in the first place.
5. **Attention events for issues**, classified from the timeline the collector
   already reads. Non-author comment, `@`-mention, label applied, closed as
   `completed` and closed as `not_planned` are five distinct events; the
   operator's own comments must not fire. The accepted event vocabulary at
   `sd_db/contributions.py:451-452` is seven kinds today and is the list that
   grows.
6. **`depends_on` kind `issue`**, with a `url` and a resolved predicate
   (closed as `completed`, or a referencing pull request merged). A new
   dependency kind is a five-place change; `design.md` enumerates all five.
7. **The recited field lists stop being recited, before the new fields are
   added.** Neither pack reader is field-agnostic: `bin/sd-status:3248-3250`
   recites 17 names and `bin/sd_work.py:417-418` recites 10, against an
   enforced 8 in the library. A field absent from a list is dropped silently.
   This is sd:602's subject, it taxes every future field equally, and it is
   cheaper to fix once than to pay four times here. **sd:602 lands first**; if
   it does not, this item's field work must carry the field-set assertion of
   criterion 7 by itself, and say in its own PR that it is paying the tax
   rather than removing it.
8. **Landing order is part of the requirement.** The pack's CI pins the
   library at a commit — `.github/workflows/tests.yml:84` reads
   `ref: 3c4c723a724c5922fb464042a036ded0408a3d51` — and installs a built copy
   from it. A pack reader that names a field the pinned library does not carry
   fails CI in a way no local run reproduces, because every local checkout
   already has the newer library. The comment at
   `.github/workflows/tests.yml:74-79` records that exact failure happening
   once already, for `record_check`.

## Acceptance criteria

- [ ] `sd task contribution add` accepts `{"issue_url": "https://github.com/OWNER/REPO/issues/N"}`
      and exits non-zero for a payload carrying both `pull_url` and `issue_url`.
- [ ] An unfiled issue registers with `target_repo`, `draft_title` and a hashed
      `draft_path`; editing the row to add `issue_url` keeps the same item ID,
      matching the existing filed-a-branch behaviour asserted at
      `tests/test_sd_work_contributions.py:205`.
- [ ] A non-author comment on an issue produces one attention event; a comment
      whose actor ID is the operator produces none.
- [ ] An issue closed as `not_planned` and one closed as `completed` produce
      two distinguishable events, not one `closed`.
- [ ] A contribution that `depends_on` an `issue` moves to the
      `newly_unblocked` lane when that issue resolves, and a dependency cycle
      through an issue is still refused.
- [ ] Re-collecting an unchanged issue produces no second notification.
- [ ] A closed issue occupies a lane that is not `merged`, and the projection's
      sort is still total over the lane set — asserted by a test that sorts a
      mixed set of pull-request and issue rows, not by inspection.
- [ ] `bin/sd-status --json` and `sd task contribution list --json` both emit
      `issue_url`, `target_repo`, `draft_title` and `draft_path` for an issue
      row. A test asserts the field list, not a sample row, so a future field
      cannot be dropped silently.
- [ ] `bin/sd-docs-lint` exits 0 and
      `python3 -m pytest tests/test_doc_citations.py tests/test_loc_caps.py`
      passes. Measured green on this branch at 730d4541 before any change.
- [ ] sd:244 is migrated to an issue row keeping item ID 244, and
      `mProjectsCode/obsidian-meta-bind-plugin#644` is registered, before the
      item closes. Both were re-measured open on 2026-09-12 (see References).

## References

- GitHub issue: <https://github.com/platypeeps/sd-ai-command-pack/issues/804>
- sd:244 — the plain task that exists because this gap does.
- sd:392 — the cross-repository cycle this work crosses. Verdict in `design.md`.
- Seed rows, re-measured 2026-09-12 with `gh issue view`:
  - `mindfold-ai/Trellis#531` — OPEN, **0 comments**, last updated
    2026-08-07T03:48:15Z. Unchanged from the 2026-09-10 reading.
  - `mProjectsCode/obsidian-meta-bind-plugin#644` — OPEN, **1 comment**
    (repository owner, 2026-01-07), last updated 2026-06-21T16:17:35Z.
    Unchanged from the 2026-09-10 reading.
- Unfiled issue drafts, re-checked 2026-09-12: still **none**. Grepping the
  library for `issue_url`, `target_repo`, `draft_title` and `draft_path`
  returns zero hits, and the database holds no row of that shape because no
  shape exists to hold one.

## Log

- 2026-09-12 created. Library facts measured against `platypeeps/system@754204d`;
  pack facts against this pack at 730d4541.
