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
- **Two recited reader lists, and they already drop a live field.** The write
  allow-list at `sd_db/contributions.py:30-31` holds **8** names. The two
  pack-side renderers each recite their own list of projection keys —
  **17** at `bin/sd-status:3248-3250`, **10** at `bin/sd_work.py:417-418` —
  and both are `for key in (...)` loops guarded by `.get()`. These are three
  lists with three different jobs, not one list copied three times, so the
  counts differing is not itself the defect. **The defect is demonstrable
  today**: `blocking_labels` is in the allow-list at
  `sd_db/contributions.py:31`, is projected at `sd_db/contributions.py:599`,
  and appears in *neither* renderer list. It is silently dropped from both text
  reports right now, with no error and no failing test. Adding four more fields
  to the allow-list alone would do the same thing four more times. That tax is
  filed separately as **sd:602**, and requirement 7 sequences it.

  **Where the drop is not**, because getting this wrong makes the acceptance
  criterion untestable: the `--json` paths do not touch either list.
  `bin/sd_work.py:402-404` returns from `_emit_contributions` before reaching
  its tuple, and `bin/sd-status:3343-3344` dumps the whole result object while
  the tuple lives in `_render_contributions`, reached only through `render()`
  at `bin/sd-status:3206`. `tests/test_sd_work_contributions.py:200` already
  reads a field out of `list --json` and passes. The silent drop is in the
  **text renderers only**.
- **A nine-place enumeration.** The `depends_on` kind is not one list either;
  `design.md` decision D2 names all nine and treats them as the same
  recited-list defect rather than as nine routine edits. Four of the nine are
  the ones where a new kind validates and then never resolves.
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

5. **Attention events for issues — two lists change, not one.** The accepted
   event *vocabulary* at `sd_db/contributions.py:451-452` is seven kinds today
   and gains `closed_completed` and `closed_not_planned`. Separately, the
   *trigger predicates* in `_pull_attention` decide which of those kinds
   actually raises attention, and for issues they must widen — which is a
   deliberate behaviour change, not a port:
   - `sd_db/contributions.py:359` fires on a `comment` only when
     `event.get("maintainer") is True or event.get("mentions_operator") is True`.
     A plain non-author comment raises nothing today. On an upstream issue the
     operator filed, any non-author comment is the signal, so this predicate
     widens for the issue path.
   - `sd_db/contributions.py:361-362` fires `label_added` only for a label that
     is in the row's configured `blocking_labels` *and* currently applied. That
     rule is kept as-is; "label applied" is not by itself an issue event either.
   - Closed is one event today. `sd_db/contributions.py:367` sets
     `reason = "Closed without merge"` for it — see requirement 10.
   In every case the operator's own comments must not fire: the actor-ID guard
   at `sd_db/contributions.py:355-356` is reused, not re-implemented.
6. **`depends_on` kind `issue`**, with a `url` and a resolved predicate
   (closed as `completed`, or a referencing pull request merged). A new
   dependency kind is a **nine**-place change; `design.md` D2 enumerates all
   nine, four of which are places where a new kind validates and then never
   resolves.
7. **The two *text* renderers stop reciting field lists, before the new fields
   are added.** Neither pack text renderer is field-agnostic:
   `bin/sd-status:3248-3250` recites 17 projection keys and
   `bin/sd_work.py:417-418` recites 10, each in a `for key in (...)` loop
   guarded by `.get()`. A projected key absent from a tuple is dropped with no
   error. The scope is exactly these two tuples: the `--json` paths do not
   reach them (`bin/sd_work.py:402-404` returns first;
   `bin/sd-status:3343-3344` dumps the whole result object), so no change to
   either JSON surface is required or sufficient. `blocking_labels` is the
   proof the defect is live: allowed at `sd_db/contributions.py:31`, projected
   at `sd_db/contributions.py:599`, in neither tuple. This is sd:602's subject,
   it taxes every future field equally, and it is cheaper to fix once than to
   pay four times here. **sd:602 lands first**; if it does not, this item's
   field work must carry the field-set assertion of criterion 7 by itself, and
   say in its own PR that it is paying the tax rather than removing it.
8. **Landing order is part of the requirement.** The pack's CI pins the
   library at a commit — `.github/workflows/tests.yml:84` reads
   `ref: 3c4c723a724c5922fb464042a036ded0408a3d51` — and installs a built copy
   from it. A pack reader that names a field the pinned library does not carry
   fails CI in a way no local run reproduces, because every local checkout
   already has the newer library. The comment at
   `.github/workflows/tests.yml:74-79` records that exact failure happening
   once already, for `record_check`.

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

10. **`merged` is pull-request vocabulary, and the fallback lane is not a free
    answer.** `LANES` at `sd_db/contributions.py:32` is
    `{"newly_unblocked": 0, "awaiting_you": 1, "awaiting_them": 2, "merged": 3}`
    and is the sort key of the whole projection at
    `sd_db/contributions.py:630`. Issues close; they never merge. The
    assignment at `sd_db/contributions.py:580` already sends anything not
    `merged` to `awaiting_them`, so "a closed issue is `awaiting_them`" is
    today's behaviour and **is refused as the answer**: at index 2 a terminal,
    closed issue would sort permanently among live awaiting-them work and ahead
    of merged pull requests. The requirement is a *terminal* lane for a closed
    issue that sorts at or after every non-terminal lane, with the sort still
    total. The reason string travels with it: `sd_db/contributions.py:367`
    reads `"Closed without merge"`, which is the same pull-request vocabulary
    in the operator-facing text and is replaced on the issue path. `design.md`
    D10 records the choice.

11. **A distinct word for an issue that has not been filed.** "Unfiled" already
    means "no `pull_url` yet" in this model, and the rule carrying that meaning
    at `sd_db/contributions.py:191-192` would fire on an issue draft, which has
    no clone and no branch by definition. The new state is named **`draft`**
    throughout — field names, refusal text and documentation — and the existing
    unfiled rule is amended to apply only to rows that are neither a filed
    issue nor a draft. Reusing "unfiled" for both is refused: one word for two
    states in the same validator is how the contradiction above became
    invisible in the source issue in the first place.

## Acceptance criteria

- [ ] `sd task contribution add` accepts `{"issue_url": "https://github.com/OWNER/REPO/issues/N"}`
      and exits non-zero for a payload carrying both `pull_url` and `issue_url`.
- [ ] An unfiled issue registers with `target_repo`, `draft_title` and a hashed
      `draft_path`; editing the row to add `issue_url` keeps the same item ID,
      matching the existing filed-a-branch behaviour asserted at
      `tests/test_sd_work_contributions.py:205`.
- [ ] A non-author comment on an issue produces one attention event — including
      a comment from someone who is neither a maintainer nor `@`-mentioning the
      operator, which raises nothing on the pull-request path today
      (`sd_db/contributions.py:359`). A comment whose actor ID is the operator
      produces none.
- [ ] An issue closed as `not_planned` and one closed as `completed` produce
      two distinguishable events, not one `closed`.
- [ ] A contribution that `depends_on` an `issue` moves to the
      `newly_unblocked` lane when that issue resolves, and a dependency cycle
      through an issue is still refused.
- [ ] Re-collecting an unchanged issue produces no second notification.
- [ ] A closed issue occupies a lane that is neither `merged` nor
      `awaiting_them`, whose index in `LANES` is greater than or equal to every
      non-terminal lane's, and the projection's sort is still total over the
      lane set. Asserted by a test that sorts a mixed set of pull-request and
      issue rows and checks the closed issue lands after every open row, not by
      inspection. `awaiting_them` is excluded deliberately: it is the existing
      fallback at `sd_db/contributions.py:580`, so a criterion permitting it
      would pass with no code change at all.
- [ ] No operator-facing string on the issue path reads `"Closed without
      merge"` (`sd_db/contributions.py:367`).
- [ ] The **default, non-`--json`** output of `bin/sd-status` and of
      `sd task contribution list` both show `issue_url`, `target_repo`,
      `draft_title` and `draft_path` for an issue row. The `--json` surfaces are
      not the check: they bypass both recited tuples
      (`bin/sd_work.py:402-404`, `bin/sd-status:3343-3344`) and would pass
      unchanged. The regression test is the tax's own: a row carrying
      `blocking_labels` — allowed at `sd_db/contributions.py:31` and projected
      at `sd_db/contributions.py:599`, yet in neither tuple — must appear in
      both text reports. That test fails on `origin/main` today and is the
      evidence sd:602 actually landed.
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
