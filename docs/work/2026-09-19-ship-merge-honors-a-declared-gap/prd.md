---
title: sd-ship merge lands under a declared protection gap
created: 2026-09-19
branch: feat/sd-1110-declared-gap
---

# PRD — ship-merge-honors-a-declared-gap

## Problem

`sd-ship merge` cannot land anything in this repository. It reads the branch
protection object before the pull request's checks and refuses a missing one
(`bin/sd_ship_remote.py`, `protection()`), and `main` here is unprotected by
the owner's recorded decision: `.github/sd-status.json` carries the accepted
gap `unprotected` since 2026-09-12, with the reason and the condition that
ends it. Every merge since then has been `gh pr merge --admin` after a human
read of the checks. The record names that stand-in honestly — "one person and
not a gate" — and names what is lost: the server-side backstop on a red merge.

The tool's own rule is stricter than "protected". `protection()` also requires
`enforce_admins`, a required-reviews object, `strict` status checks and no
bypass allowances. A sole operator cannot satisfy the reviews requirement at
all: GitHub forbids self-approval, so one approving review locks the branch
and zero approving reviews is the gap `sd-status` reports. Re-protecting
`main` narrowly would not make the tool runnable either. As written, `sd-ship
merge` is dead on every single-operator repository, which is every repository
this pack currently ships to.

So the pack has a merge gate that rechecks ownership, exact head, base drift
and per-check CI at the reviewed commit, and none of it runs where the pack is
used. The thing to restore is the machine backstop, not the protection object.

## Requirements

1. `sd-ship merge` proceeds when the protection object is absent **and** the
   repository declares that state accepted. The declaration is the existing
   `accepted_gaps[]` entry in `.github/sd-status.json` whose `id` is
   `unprotected` **and** whose `state` is `{"branch_protection": false}`,
   both, as `source:bin/sd-status::_apply_acknowledgements` matches an entry
   to a gap: the id is necessary and never sufficient, the schema says so,
   and an entry for another gap that happens to pin the same fact is not an
   acceptance of this one. No
   flag, environment variable or database row can stand in for the file: the
   declaration is the checked-in one, or there is none. Checked in means at
   the reviewed commit: `merge` reads the file from `head` (`git show
   <head>:.github/sd-status.json`), never from the working tree, so a
   declaration nobody reviewed cannot let a merge through. `sd-status` keeps
   reading the working tree, which is its job.
2. Under the declaration, the substitute rule is every check at the exact
   reviewed head. Every check run reported by `filter=latest` for `head` must
   be `completed` with conclusion `success`, `neutral` or `skipped`. For
   commit statuses, the `/statuses` endpoint returns history newest first, so
   the rule is per context: the **newest** record for each context at `head`
   must be `success`, exactly as `ready()` selects it today
   (`source:bin/sd_ship_remote.py::GitHub.ready`); an older `pending` or
   `failure` behind a newer `success` is history, not a refusal.

   Passing checks are not enough: a commit the Tests workflow never ran on
   would pass on the advisory `route` check alone. So the rule also says
   **which validation must have run**, derived from the repository and not
   from a roster. `merge` reads every `.github/workflows/*.yml` and `*.yaml`
   at `head` (`git ls-tree <head>` on that directory, then `git show`; GitHub
   accepts both extensions), takes every workflow whose `on` includes
   `pull_request`, and requires for each one a workflow run at `head_sha`
   **for the `pull_request` event**
   (`/actions/runs?head_sha=<head>&event=pull_request`) that is `completed`
   with conclusion `success`. The event filter is what makes a run evidence
   of the pull-request validation: a workflow on both `push` and
   `pull_request` can succeed on the push while its pull-request-only steps
   never ran, and a run matched by SHA alone would count it. A workflow that
   did not run for the event — a `paths` filter, a disabled
   workflow, a trigger that never fired — is a refusal naming the workflow,
   never a pass. This is the doctrine of `AGENTS.md` and
   `tests/test_verb_inventory.py`: enumerate from the tree at merge time, so
   a workflow added at `head` is expected at `head` and one deleted at `head`
   is not. App checks that are not repository workflows (Copilot's, for one)
   fall under the check-run rule above and add nothing to the expected set.
3. Every other recheck `merge` performs today stays as it is: `--expected-head`
   equals the current head; the review receipt covers it; merge authority and
   `mode:`; default branch and squash allowed; `mergeable_state == "clean"`;
   `behind_by == 0`; head, base and source repository unchanged since local
   review; the observation repeated immediately before the `PUT`, refusing on
   any difference. The declared gap replaces the protection object in that
   final comparison, nothing else.
4. Fail closed on every way the declaration can be wrong. Only an HTTP 404
   from the protection endpoint counts as "absent"; a 401, 403, 5xx or
   transport failure is the present refusal, and is never read as
   unprotected. A file that is missing at `head`, unreadable, invalid or
   carries an unknown key yields no declaration and the present refusal,
   with the file's faults named. A
   declaration beside a protection object that GitHub *does* return is refused
   as a declaration that does not match the observed state, mirroring
   `sd-status`'s rule; the present `protection()` refusals apply unchanged
   when the object exists.
5. The receipt says which rule governed. The ship receipt and the `--json`
   output carry a `protection` field: the observed object today, or
   `{"declared_gap": "<id>", "until": "<the entry's until>"}` under the
   declaration. The `until` condition is printed in the merge's human output
   as `sd-status` prints it, so the age of the decision stays visible.
6. One reader of `.github/sd-status.json`. `bin/sd-status`'s
   `load_acknowledgements` moves to `bin/sd_lib.py` and both commands import
   it. No second parser of that file exists under `bin/`, and
   `tests/test_cut_symbols.py`'s `ONE_DEFINITION` gains the row.
7. `sd-status`'s protection section does not change. It keeps reporting the
   gap as accepted with its `until`, and keeps reporting a stale entry as a
   bug in the file.
8. `WORKFLOW.md`'s merge section and the `unprotected` entry's `because` are
   updated in the same change: the sentence "`sd-ship merge` is not the
   replacement while this gap stands" stops being true, and the entry says
   what replaces it. `CHANGELOG.md` carries a line.

## Assumptions

- The declaration's owner is the repository, not the operator. A repository
  that lost protection by accident carries no entry and stays refused.
- The GitHub `check-runs` and `statuses` endpoints at an exact SHA are the
  same evidence `ready()` reads today for the required contexts; this widens
  the set from "the named required checks" to "all of them", and requires a
  non-empty set so a commit nothing ran on cannot pass.
- This item is the "user-owned future design" that sd:1021 requirement 4
  deferred, authorized on 2026-09-19.

## Acceptance criteria

- [x] `tests/test_sd_ship.py`: a fixture with a 404 protection object, a
      declaration whose `state` is `{"branch_protection": false}`, and every
      check run at `head` completed `success` reaches the merge `PUT` exactly
      once; the receipt's `protection` field is
      `{"declared_gap": "unprotected", "until": ...}`.
- [x] Same fixture without the declaration: the refusal is the present one
      ("Branch not protected"), and the `PUT` count is 0. The test is run
      red first by removing the declaration check.
- [x] Same fixture with the declaration and one check run at `head` whose
      conclusion is `failure`: refusal with code `ci_not_passing`, `PUT` count
      0. A second variant with the failing run at a *different* SHA and a
      passing rerun at `head` also refuses: the latest run at the head is
      what counts, and a run for another commit is not evidence.
- [x] Status histories at `head`, written as the literal newest-first array
      the `/statuses` endpoint returns for one context:
      `[success, pending]` merges, `PUT` count 1 (CI recovered);
      `[success, failure]` merges, `PUT` count 1 (CI recovered);
      `[failure, success]` refuses, `PUT` count 0 (currently failing);
      `[pending, success]` refuses, `PUT` count 0 (currently pending).
- [x] Same fixture with the declaration and zero check runs and zero statuses
      at `head`: refusal, `PUT` count 0.
- [x] Only the advisory workflow ran: `.github/workflows/` at `head` holds
      `tests.yml` and `sd-review-route.yml`, both on `pull_request`; the only
      check run and the only workflow run at `head` are `route`, `success`.
      Refusal names `Tests`; `PUT` count 0. A second fixture renames the file
      `tests.yaml` and asserts the same refusal, so the `.yaml` spelling is
      enumerated and not skipped.
- [x] A workflow present at `head` but absent from the working tree is still
      expected; one absent at `head` and present in the working tree is not.
      Two fixtures, asked of `expected_workflows` directly: `merge` refuses a
      dirty checkout before it reads anything, so a `PUT` count over a dirty
      tree measures that older guard and not this reader (Log, 2026-09-19).
- [x] A workflow on both `push` and `pull_request` with one run at `head`
      whose `event` is `push`, `success`, and none for `pull_request`:
      refusal names the workflow, `PUT` count 0. The same fixture with a
      second run, `event: pull_request`, `success`: `PUT` count 1.
- [x] A workflow whose `on` is `push` only is not expected; a fixture with a
      third such workflow and no run for it merges, `PUT` count 1.
- [x] An entry with `id: reviews` and `state: {"branch_protection": false}`
      and no `unprotected` entry: refusal, `PUT` count 0 — another gap's
      acceptance does not authorize this one.
- [x] Declaration present and GitHub returns a protection object: refusal
      names the mismatch, `PUT` count 0.
- [x] Declaration file invalid (unknown key, bad JSON, wrong `state` shape):
      refusal names the file's fault, `PUT` count 0.
- [x] The declaration exists only in the working tree and not at `head`:
      `declared_gap` answers `None` and names the missing file at `head`. The
      converse — at `head`, deleted from the working tree — answers the entry,
      because the working tree is not what is landing. Asked of the reader
      directly, for the reason the workflow-set criterion gives.
- [x] The protection endpoint answers 403 and the declaration is present:
      refusal is the present one, not a merge; `PUT` count 0.
- [x] The final pre-`PUT` comparison: a fixture whose protection endpoint
      answers 404 on the first read and returns an object on the second
      refuses with the present "ownership or branch protection changed before
      merge".
- [x] `grep -rn "def load_acknowledgements" bin/` prints exactly one line, in
      `bin/sd_lib.py`; `tests.test_cut_symbols.OneDefinitionEach` holds the
      row and goes red when a copy is pasted into `bin/sd-status`.
- [x] `tests.test_sd_status` passes unchanged in count: the protection
      section's output for this repository is byte-identical before and after.
- [x] `make check`: 0 non-zero shards, `make exit=0`.
- [ ] Live: the next pull request in this repository lands through
      `sd-ship merge --expected-head <sha>` with `ok: True`, and the ship
      receipt in `~/.local/share/sd/sd.db` shows `declared_gap: unprotected`.

## References

- `.github/sd-status.json` `accepted_gaps[0]` — the declaration and its
  reasons (2026-09-11, 2026-09-12).
- `source:bin/sd_ship_remote.py::protection` and
  `source:bin/sd_ship_remote.py::ready` — the rule this substitutes for and
  the evidence reader it reuses.
- `source:bin/sd-status::load_acknowledgements` — the reader that moves.
- sd:1021 requirement 4 — "Merge-authorization redesign belongs to a
  user-owned future design, outside this batch."
- PR #1082 — the merge that prompted this: `sd-ship merge` refused, `gh pr
  merge --admin` after reading four checks by hand.

## Log

- 2026-09-19 created. The owner chose this over doing nothing and over
  re-protecting `main` narrowly; the second would contradict the recorded
  instruction, and would not satisfy `protection()` anyway.

## Review

Development / prd and design point; cap 5 automatic rounds
(`.claude/rules/sd-planning-adversarial-review.md`). `prd.md` is not under a
`sensitive` path of `.github/sd-review.json`, so no stable-id ledger or
cross-artifact sweep is owed; concerns are still listed with dispositions.

### Round 1 — 2026-09-19

Host lane (Claude), against `bin/sd-ship` and `bin/sd_ship_remote.py`:

- **Declaration read from the working tree** — a declaration nobody reviewed
  could let a merge through. *Addressed*: requirement 1 reads the file at
  `head`; two criteria cover the working-tree-only and head-only cases.
- **Any API failure read as "absent"** — a 403 or 5xx must not become
  "unprotected". *Addressed*: requirement 4 admits only HTTP 404; a criterion
  covers 403.
- **`mergeable_state == "clean"` already implies passing checks on an
  unprotected branch** — is requirement 2 redundant? *Rebutted, kept*:
  `mergeable_state` is GitHub's summary and can be `unknown` while it
  recomputes; the pack's own per-run read at the exact SHA is the evidence the
  receipt records. Both stay, as they do today for protected branches.
- **A commit nothing ran on** (`paths-ignore`, a docs-only change) refuses
  under "at least one". *Accepted consequence*: fail closed; the operator
  reruns a workflow or lands by hand, as today.

Codex (independent lane, `sd-review --scope planning --provider codex`),
one `medium` blocking finding, taken as correct:

- **"Every commit status must succeed" cannot recover from pending→success**
  — `/statuses` returns history, and an old `pending` would stand beside the
  new `success`. *Addressed*: requirement 2 now takes the newest record per
  context, as `ready()` does; three history criteria added.

A first Codex run was refused with `input_changed`: the PRD was edited while
the review's `make check` ran. The second run is the one recorded.

### Round 2 — 2026-09-19

Codex, one `medium` blocking finding, verified against
`source:bin/sd-status::_apply_acknowledgements` and taken as correct:

- **Matching on state alone changes the acknowledgement contract** —
  `sd-status` requires id *and* state, so an entry for `reviews` pinning
  `branch_protection: false` would authorize a merge that `sd-status` still
  reports as an unaccepted gap. *Addressed*: requirement 1 requires both; a
  criterion covers the other-gap entry.

Host lane: no new concern from the round-1 changes.

### Round 3 — 2026-09-19

Codex, one `high` blocking finding, taken as correct:

- **A non-empty check set does not prove the validation ran** — with only
  the advisory `route` check present, "at least one" merges a commit the
  Tests workflow never ran on. *Addressed*: requirement 2 now enumerates the
  `pull_request` workflows from `.github/workflows/*.yml` at `head` and
  requires a successful workflow run at `head_sha` for each; a workflow that
  did not run refuses by name. Three criteria cover the advisory-only case,
  the head-versus-working-tree set, and a `push`-only workflow. This is not a
  roster: the set comes from the tree at the reviewed commit.

Host lane: matrix jobs make check-run names unpredictable from the YAML
(`unittest (ubuntu-latest, 3.13)`), which is why the expected set is at
workflow granularity, where a run's conclusion is the conjunction of its
jobs, and the per-check-run rule keeps the finer read.

### Round 4 — 2026-09-19

Codex, two blocking findings, both taken as correct:

- **`*.yml` only** (`high`) — GitHub accepts `.yaml`, so a `tests.yaml`
  would be neither expected nor run and `route` alone would merge.
  *Addressed*: requirement 2 enumerates both spellings by `git ls-tree` at
  `head`; the advisory-only criterion gains a `.yaml` variant.
- **The history criterion read as reversed** (`medium`) — "`pending` then
  `success`" was chronological prose beside "newest first", so a literal
  reading refuses the recovered case and merges the failing one.
  *Addressed*: the criterion now states literal newest-first arrays with
  their `PUT` counts.

Host lane: no new concern.

### Round 5 — 2026-09-19 (the cap)

Codex, one `high` blocking finding, taken as correct:

- **A run matched by SHA alone can be a `push` run** — a workflow on both
  events succeeds on the push while its pull-request validation never fires,
  and the rule as written accepts it. *Addressed*: requirement 2 filters the
  run query by `event=pull_request` (a documented parameter of
  `GET /repos/{owner}/{repo}/actions/runs`); a criterion covers the push-only
  run and its pull-request counterpart.

The cap of five automatic rounds is spent. Every blocking finding is
addressed on the item; none is open. Per the rule, no sixth round starts on
its own, and whether the addressed round-5 finding needs a further
independent read is the owner's call.

### Round 6 — 2026-09-19 (owner-authorized, past the cap)

The owner authorized one round beyond the cap so the round-5 fix would get
an independent read. Codex: `status: clean`, 0 findings; `make check`
passed in the same run (exit 0). No `BLOCKING` line is open; the item is
promoted `planning → ready`.

### 2026-09-19 — implemented on `feat/sd-1110-declared-gap`

- `bin/sd_ship_remote.py`: `api_status` reads the HTTP status through
  `gh api --include`; `gate` returns the validated protection object or the
  declaration read at `head`; `every_check` is the substitute for the
  required-checks list; `expected_workflows` enumerates `pull_request`
  workflows from the tree at `head`. `ready` dispatches to `every_check`
  when the gate is a declaration. `bin/sd-ship`: `merge` calls `gate`,
  records the gate on the receipt, and `still_gated` repeats the read before
  the `PUT`. `Ship.merge` left `tests/test_code_health.py`'s `COMPLEX`
  baseline with that extraction.
- `bin/sd_lib.py`: the YAML reader, `load_acknowledgements`,
  `parse_acknowledgements` and `acknowledgement_problems` moved from
  `bin/sd-status`, which now aliases them. `tests/test_cut_symbols.py`:
  `ONE_DEFINITION` gained the loader and the parser; the
  `load_acknowledgements` row left `HELD_SYMBOLS` (a keep may shrink).
- Two criteria changed shape. `merge` refuses an uncommitted checkout
  before it reads the head, an older guard that stands, so a `PUT` count
  over a dirty working tree cannot observe the readers. Both working-tree
  criteria ask `expected_workflows` and `declared_gap` directly instead; the
  rest of the table is asserted through `merge` and its `PUT` count as
  written. `tests.test_sd_ship.DeclaredGapCase` holds sixteen tests.
- `WORKFLOW.md`, the `unprotected` entry's `because`, and `CHANGELOG.md`
  say what replaces the gate under the declaration. The live criterion is
  ticked when this branch's own pull request lands through
  `sd-ship merge`.

### 2026-09-19 — Codex branch review, two blocking findings, both fixed

- `source:bin/sd_ship_remote.py::expected_workflows` (high): `- pull_request # Validate PRs` is
  valid YAML, and the reader carried the comment as the event name, so the
  Tests workflow silently stopped being expected and an advisory run alone
  merged. Fixed: `sd_lib.yaml_uncommented` strips a trailing comment with
  quotes respected, and `expected_workflows` refuses a trigger that is not
  spelled like an event name (`EVENT_NAME_RE`) instead of dropping the
  file. Two tests.
- `source:bin/sd_ship_remote.py::every_check` (medium): a `pull_request` trigger under
  `paths`, `paths-ignore`, `branches`, `branches-ignore`, or a `types` list
  without `synchronize` runs for some pull requests and not others, so a
  documentation-only change stayed blocked on a source-only workflow GitHub
  never scheduled. First fix: such a workflow was not expected at all.
- Development code review point: one automatic pass spent; the fix gets
  one verification pass (the cap row's "plus one").

### 2026-09-19 — verification pass, two blocking findings

- `source:bin/sd_ship_remote.py::expected_workflows` (high): the first fix
  dropped every filtered workflow, including Tests under
  `branches: [main]` on a merge into main. A second attempt evaluated the
  filters the way GitHub does; the ship lane's review then found two
  divergences from GitHub's cheat sheet in one probe (`docs/**/*.md` against
  `docs/README.md`, `*.jsx?` where `?` repeats the character before it).
  Resolved by returning to requirement 2 as written: a workflow whose `on`
  includes `pull_request` is expected whatever filter sits under the
  trigger, and one that did not run for the event is a refusal naming it.
  The first pass's medium finding — a documentation-only change blocked on
  a source-only workflow — is rebutted on that requirement: the refusal
  names the workflow, the operator sees why, and a merge that guessed the
  filter would be the hole. No workflow in this repository carries a
  `paths` or `branches` filter. The glob matcher is gone; three fixtures
  hold the rule for `paths`, `branches` and `types`.
- `source:bin/sd_lib.py::workflow_triggers` (medium): the single-event
  form `on: pull_request` read as no trigger and refused every merge under
  the declaration. Fixed: an inline scalar is that one event. Two spellings
  and a `workflow_dispatch`-only workflow beside the gate.
- Ship lane, medium, `every_check`: an external check that never enqueues
  is not missed. Rebutted on requirement 2's last sentence: app checks that
  are not repository workflows fall under the check-run rule and add
  nothing to the expected set. A roster of required contexts is what the
  protection object carries, and the owner declined that object
  (`.github/sd-status.json`, `because`); writing the roster into the
  declaration would re-create it under another name, which sd:1021
  requirement 4 leaves to a user-owned design.
- The cap row is spent. A further finding on this branch is the owner's
  call, not an automatic pass.
