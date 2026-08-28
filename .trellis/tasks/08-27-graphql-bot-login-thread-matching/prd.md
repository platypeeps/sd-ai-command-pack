# Normalize bot login when matching review threads

## Goal

The `sd-review` coordinator reported `status: ready` with
`observation.status: "clean"` and `reviewThreads: {total: 0, unresolved: 0}`
for a pull request head that had three unresolved Copilot threads. The same
observation payload listed, by node id, the review that opened those threads.

Filed as [platypeeps/sd-github-review#159][issue]. Observed on
`platypeeps/sd-github-review` PR #157, head `45f892b`.

[issue]: https://github.com/platypeeps/sd-github-review/issues/159

### Cause

GraphQL and REST spell the same bot differently:

```
GraphQL  Bot.login  -> copilot-pull-request-reviewer
REST     user.login -> copilot-pull-request-reviewer[bot]
```

`_collect_observation` builds `authors` from `receipt.backend.reviewAuthors`,
which is written in REST spelling. `_collect_review_threads` fetches threads
over **GraphQL** and keeps a thread only when one of its comments matches that
set:

```python
if matching or not authors:
    threads.append({...})
```

`_matching_author` case-folds both sides (`login.lower() in authors`, and
`authors` is built with `str(item).lower()`) but is otherwise an exact
comparison, so `copilot-pull-request-reviewer` never matches
`copilot-pull-request-reviewer[bot]`. Every thread is dropped, `threads` is
empty, and `"total": len(threads)` reports `0`.

`matching_reviews` is populated from a REST path where the login does carry
`[bot]`, so the review itself survives. One author, two APIs, two spellings,
one matcher — the review comes back, its own comments do not.

`materialized: true` came from a different disjunct — the Copilot check run
matched `checkNames` — so the payload asserted materialized evidence while the
inline-comment channel had been silently emptied.

### Why it matters

`observation.status` is what opens the remote gate. With threads invisible the
coordinator reports no findings to disposition and exits `ready` with
`limitations: []`, giving no signal that anything went unread. On PR #157 the
three dropped findings were all correct and one was a crash: a `null` probe
response dereferenced before any POST. `sd-housekeeping` refused the merge only
because it counts threads without author filtering — the lane's own verdict was
`clean`.

### Blast radius

Not Copilot-specific. Any backend whose `reviewAuthors` are written in REST
spelling loses every GraphQL-sourced inline finding. `github-actions[bot]`, the
`reviewAuthors` entry for both configured PR-Agent backends, has the same
shape. Whether a PR-Agent inline finding has actually been dropped is **not
verified** — PR-Agent declares `findingChannels: ["conversation-comment"]`, and
conversation comments travel a different path.

## Requirements

### R1 — Match a bot author regardless of API spelling

`_matching_author` must treat `copilot-pull-request-reviewer` and
`copilot-pull-request-reviewer[bot]` as the same author. Normalization applies
to both sides of the comparison: the configured `reviewAuthors` and the login
read off the payload. Configuration must not have to know which transport the
collector chose.

The fold is granted to bots only. `name[bot]` and the user account `name` are
different GitHub principals, and both APIs say which is which -- GraphQL
`__typename`, REST `user.type`, and the suffix itself, which only an app can
carry. An exact spelling always matches; the folded spelling matches only a
principal GitHub reports as a bot, so a human registering an app's bare name
never inherits its review authority.

The fold is asymmetric on purpose. `name[bot]` in config never reaches the
human `name`; the bare `name` in config does reach the bot `name[bot]`, because
that is how a repository ordinarily names an App reviewer and GraphQL shows
apps unsuffixed -- demanding the suffix in config would break the transport
independence R1 exists to provide.

**Accepted, recorded during review round 3.** A reviewer flagged the second
direction: a repository that means the human `name` and writes it bare also
authorizes an app of that name. The finding is accurate. It is accepted rather
than fixed because the alternative fails the criterion below -- config without
the suffix must still match a payload carrying it -- and no third spelling
distinguishes the two intents. The bound is documented instead: write
`name[bot]` when you mean the app; there is no spelling that means the human
alone.

Matching stays case-insensitive, as it is today. A login carrying no `[bot]`
suffix on either side is unaffected.

### R2 — Fail closed when the author filter empties a non-empty thread set

When the GraphQL thread query returns rows and **every** row is discarded by
the `reviewAuthors` filter, while REST still holds an inline comment by those
same authors, the observation is internally contradictory: one author matched
on one transport and none matched on the other, on the same channel. The
observation must not report `clean` in that state.

Rows fetched versus rows kept — both already known inside
`_collect_review_threads` — is the pre-filter, not the finding: unrelated human
threads satisfy it while nothing was dropped. The confirming REST page is
fetched only when the pre-filter holds, so the ordinary path costs no extra
call. A matching review is deliberately not one of the pre-filter's terms: it
reads as corroboration but exists only when the `review` channel is configured,
so requiring it would exempt an inline-only backend — the one whose findings
live entirely in the channel this guard protects. The signal is structural, not
textual. Do **not** derive it by
parsing a review body for a phrase like "generated 3 comments": that text is
free English written by the backend, the REST review object carries no comment
count to check it against (`keys` are `_links, author_association, body,
commit_id, html_url, id, node_id, pull_request_url, state, submitted_at,
user`), and a prose matcher would be Copilot-specific and silently rot.

This is deliberately independent of R1. It needs no knowledge of why the count
is wrong, and would have caught this class of defect at first occurrence rather
than leaving it to the merge gate. Keep it after R1 lands: R1 fixes the known
spelling mismatch, R2 catches the next filter that empties the channel for a
reason nobody predicted.

The resulting state must carry a diagnostic naming the contradiction, and must
not be silently downgraded to a limitation the caller can ignore.

## Non-goals

- Changing how `materialized` is computed. Its disjuncts are correct
  individually; the bug is that one channel was emptied upstream.
- Auditing fleet consumers' `reviewAuthors` values. Worth doing, separate task.
- Any change to `sd-github-review`. The defect is entirely pack-side.

## Acceptance Criteria

- [ ] A GraphQL thread payload whose comment author login is
      `copilot-pull-request-reviewer`, matched against `reviewAuthors`
      `["copilot-pull-request-reviewer[bot]"]`, yields
      `reviewThreads.total == 1` and `unresolved == 1`.
- [ ] The reverse spelling — payload carrying `[bot]`, config without it —
      also matches, so neither side is privileged.
- [ ] An observation whose GraphQL thread query returned rows, all of which
      the author filter discarded, while REST holds an inline comment by those
      same authors, does not return `status: "clean"`, and its diagnostic names
      the contradiction.
- [ ] Discarded threads alone do not fire it. A pull request carrying unrelated
      human threads and a body-only review by a configured author -- the shape
      of a clean Copilot review -- still reports `clean`, because REST holds no
      inline comment by those authors to have been dropped.

      **Deviation, recorded during review rather than reworded to pass.** The
      first criterion above originally accepted a matching REST *review* as the
      other-transport evidence. Review round 1 established that this is too
      broad: unrelated human threads plus a body-only review satisfy it while
      nothing was dropped, which would refuse `clean` for the life of the
      branch. The evidence is narrowed to REST inline comments -- the same
      channel the GraphQL thread pass reads -- and the cheap counts become a
      pre-filter that pays for the confirming page only in the suspicious case.
- [ ] A genuinely empty thread set — the query returned no rows at all — still
      reports `clean`. R2 must not fire when there is simply nothing there.
- [ ] Both new tests fail against unmodified source. A test that passes
      pre-fix is not accepted as evidence.
- [ ] The full pack test suite is green, with no existing test's assertions
      weakened to accommodate the change.

      **Deviation, recorded during implementation rather than reworded to
      pass.** The criterion originally read "no existing test modified". One
      existing test had to change:
      `test_dispatch_status_does_not_change_harvested_findings` stubs
      `_collect_review_threads` with `return_value=[]`, and R2 changes that
      function's return to `(threads, fetched)`. The stub was updated to
      `([], 0)` so the mock stays faithful to the real signature; the test's
      assertions are untouched. The absolute wording would have forbidden a
      necessary and honest mock update, so the criterion is narrowed to what it
      was actually protecting -- assertions, not mock plumbing. No other
      existing test was touched.
- [ ] All four copies of the collector are updated in one commit, per the
      convention in `ecbfb0d1`: `scripts/`, `templates/scripts/`,
      `plugins/sd/bin/`, `plugins/sd/machine-payload/scripts/`.

## Verification

Named before implementation. The repository runs `unittest`, not pytest —
`make test` drives `.github/scripts/run-tests.sh` and then asserts on
`unittest-output.log`.

Targeted, for the red/green proof:

```bash
python3 -m unittest tests.test_review_controller -v -k bot_login
python3 -m unittest tests.test_review_controller -v -k author_filter
```

Expected: each new test fails against unmodified source and passes after. A
new test that passes before the fix is rejected, not accepted.

Then the maintainer gate:

```bash
make test
```

Expected: no failures, no skips (the target fails the build on
`skipped=[1-9]`), and no existing test's assertions weakened -- mock plumbing
that must track a changed signature may be updated, and every such update is
recorded as a deviation above. `make test` also enforces 100% coverage on
`install.py`/`installer/*` and runs the shipped-script coverage, docs, and mode
checks, so a new helper added to the collector must satisfy those too.

Failure means any new test passes before the fix, any existing test's
assertions break or are weakened, or `make test` reports a skip.
