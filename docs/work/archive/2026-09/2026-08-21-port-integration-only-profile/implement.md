# Implementation plan — Port the fleet integration-only review profile

Ordered. Each step names its own validation. Steps 1-2 are reversible text
moves; step 5 is the only one that changes which skill the fleet actually
calls, and it is deliberately last.

## Review gate before starting

`design.md` leaves exactly one decision open: the finish-work tension
(options A/B/C, recommendation B). **Settle it and record the decision in
`design.md` before step 4.** Steps 1-3 do not depend on it.

## Step 1 — Relocate the recheck procedure

Move `templates/.agents/skills/sd-review-pr/SKILL.md:206-232` (the
`### Fleet Integration-Only Recheck` block) verbatim into
`templates/.agents/skills/sd-fleet-refresh/SKILL.md`. Do not copy — move — but
leave `sd-review-pr` a one-line pointer so it stays coherent until child 2
deletes it.

- Validate: `bash scripts/sd-ai-command-pack-surface-check.py` green;
  `fleet-review-classify.py` reference resolves from `source-root`.
- Validate: `sd-fleet-refresh` still has 0 manifest entries —
  `python3 -c "import json;m=json.load(open('manifest.json'));print(sum('sd-fleet-refresh' in json.dumps(f) for f in m['files']))"` prints `0`.
- Rollback point: single revert, nothing else depends on this yet.

## Step 2 — Add the trusted-caller section to sd-review

Insert `## Trusted caller context` between `## Arguments` (ends `:50`) and
`## Safety and authority` (`:55`). Carry the field list from
`sd-review-pr/SKILL.md:69-77` and the per-profile validation rule from `:81`
verbatim, including the "Accept it only while already executing the resolved
`sd-fleet-refresh` skill" constraint.

- Do **not** add any key to the `key=value` enum at `:45-50`.
- Validate: a `caller=sd-fleet-refresh` argv token is still rejected by the
  existing unknown-key rule. This is the security property; pin it with a test
  now, not later.

## Step 3 — Port exact-head reclassification

Implement the `classified-head` / `LOCAL_HEAD` / `HEAD_SHA` identity
requirement in `sd-review`, matching `sd-review-pr/SKILL.md:81` and `:209`.

- Validate: mismatch on any of the three refuses, proven by test.
- Validate: non-eligible, unavailable, or malformed classifier output fails
  closed and grants no positive confidence.

## Step 4 — Port deferral semantics and return shape

Implement the decision recorded at the review gate above. If option B:
`sd-review` returns a typed deferral disposition inside `review-result` and
does **not** call finish-work, leaving `sd-fleet-refresh` to own it; then
`sd-review/SKILL.md:73` stays absolute and is not edited. If option A: narrow
`:73` explicitly and say why in the same commit.

- Validate: `sd-review/SKILL.md:73` either still reads exactly
  "Do not merge, archive Trellis work, or run housekeeping from this skill."
  (option B/C) or carries the recorded narrowing (option A). No silent edit.

## Step 5 — Repoint sd-fleet-refresh

Change `templates/.agents/skills/sd-fleet-refresh/SKILL.md:310` from
`sd-review-pr` to `sd-review`, keeping `caller: sd-fleet-refresh`,
`return-after: review-result`, `defer-finish-work: true`.

- Validate: `make check` green.
- Validate (manual, cannot run in CI): one real `sd-fleet-refresh`
  integration-only review against a live consumer PR head. Record the
  classifier output and the returned `review-result` in this task directory
  before ticking the acceptance criterion. Do not tick it from a dry run.
- Rollback point: revert this step alone to put the fleet back on
  `sd-review-pr`, which is still fully functional until child 2 lands.

## Step 6 — Regenerate and verify parity

`make generate` (or the repo's generator entry point), then confirm the four
mirror trees agree.

- Validate: `make check` green; generated-parity tests pass.
- Validate: `git status --porcelain` shows only intended paths.

## Out of scope reminders

- Delete nothing. `sd-review-pr` must still run its own integration-only path
  when this task ends (child-1 R5).
- Touch no `full-check` script, `Makefile`, or CI gate.

## Definition of done

All seven acceptance criteria in `prd.md` ticked, with criterion 1 backed by
recorded output from the manual step-5 run rather than by inspection.

## Findings, 2026-09-01 — the surface this plan was written against is gone

Recorded, not acted on. This note decides nothing: the item's status, location,
and fate are the maintainer's call. What follows is what a check of the tree and
the remote returns today, so that call is made against facts rather than against
the plan above.

### The branch existed, landed, and was deleted

`prd.md:5` names `branch: feat/port-integration-only-profile` and `prd.md:3`
still reads `status: in_progress`. The branch is not anywhere on this machine
and not on the remote:

- `git branch -a --list '*port-integration*'` — no output.
- `git ls-remote --heads origin | grep -i port-integration` — no output.
- `git worktree list` — three worktrees, all at `75d39c18` on `main` or an
  agent branch; none carries it.
- `find ~/repos -path '*refs/heads/feat/port-integration-only-profile'` and a
  `packed-refs` grep across `~/repos` — no output from either.

It is absent because it merged, not because it was lost.
[PR #535](https://github.com/platypeeps/sd-ai-command-pack/pull/535),
*"feat(review): run the fleet integration-only profile on sd-review"*, head
`feat/port-integration-only-profile` at `372035762b01a5630b1974ca4c0b7c3dfdcf1560`,
merged `2026-08-22T10:58:45Z` as `176d1819`, 32 files, +804/-223. GitHub deleted
the head branch at merge, which is the whole of the mystery. The `31e5950a`
that `prd.md`'s Evidence table names as the verified head still resolves in this
checkout.

### Every path this plan cites has been deleted

Not stale — absent. Checked with `git ls-files`, not with `ls`, so an untracked
leftover could not answer for a tracked file:

| Cited at | Path | State today |
| --- | --- | --- |
| `implement.md:15`, `prd.md:35` | `templates/.agents/skills/sd-review-pr/SKILL.md` | `git ls-files templates` returns nothing; `templates/` does not exist |
| `implement.md:17`, `:63` | `templates/.agents/skills/sd-fleet-refresh/SKILL.md` | same — the whole tree went at step 3e |
| `implement.md:21` | `scripts/sd-ai-command-pack-surface-check.py` | `git ls-files scripts` returns nothing; `scripts/` does not exist |
| `implement.md:24` | `manifest.json` | deleted at step 3e (`CONTRIBUTING.md`, Payload Rules) |
| `implement.md:77` | `make generate` | removed; `CONTRIBUTING.md:36-39` records why |

The named tests are gone with them: `tests/` holds no
`test_review_trusted_context.py` and no `test_sdlc_commands.py`, the two files
`prd.md`'s Evidence table rests on. So six of the seven acceptance criteria are
ticked against evidence that no longer exists in the tree, though it is still
reachable in history and in #535.

### The capability is not in today's `bin/sd-review` under any name

Searched rather than assumed, and the search is the part worth recording:

- `grep -i 'integration-only\|classified-head\|trusted\|caller\|defer-finish-work\|HEAD_SHA\|LOCAL_HEAD' bin/sd-review`
  returns exactly one line, `bin/sd-review:555`, and it is about a subprocess
  environment — *"place, so a caller cannot forget to pass it and inherit the
  parent's."* Nothing about a trusted caller contract.
- `git grep -l -i 'integration-only\|classified-head\|trusted caller'` matches
  no file under `bin/`, `skills/`, `tests/`, `agents/`, or `plugins/` — only
  `CHANGELOG.md`, the known-stale `docs/spec/` and `docs/FLEET_ROLLOUT.md`, this
  item, and archived work.
- `git grep -l 'sd-review-pr\|sd-fleet-refresh' -- bin skills tests agents plugins`
  returns nothing. Neither skill exists in any form.

It is not a rename. Today's `bin/sd-review` is a different shape: its own
docstring says *"Nothing here writes to a network. There is no pull-request
comment, no review submission, no label, no check-run update, and no HTTP client
of any kind"* (`bin/sd-review:16-18`), and *"The repository comes from the
current directory (R10-D6). There is no `--repo` argument and there will not be
one"* (`bin/sd-review:26-28`). A profile whose entire job is to review another
repository's pull-request head on behalf of a trusted fleet caller has no seam
to land on in that design, and R10-D6 forecloses the argument it would need.

### The three siblings were all parked on 2026-09-01; this one was missed

- `docs/work/archive/2026-09/2026-08-09-retire-review-pr-surface/prd.md` —
  parent — `parked: 2026-09-01 bulk-park (D2)`.
- `docs/work/archive/2026-09/2026-08-21-delete-review-pr-surface/prd.md` —
  child 2 — same line.
- `docs/work/archive/2026-09/2026-08-22-verify-ported-integration-only-path/prd.md`
  — the task `prd.md`'s Evidence section hands acceptance criterion 1 to — same
  line.

All three carry `status: planning`. D2's bulk-park moved `status: planning`
items with no branch, so this item was not swept for one reason only: it reads
`in_progress`. It is the sole survivor of its own family, and `sd-status`
counts it as one of the pack's two active items.

### The one open criterion, and what would have to be true to close it

`prd.md`'s criterion 1 — *"`sd-fleet-refresh` completes an integration-only
review through `sd-review` against a real PR head"* — is the only unticked box
and the stated reason the item must stay `in_progress` and must not be archived.
Closing it needs three things that no longer exist: an `sd-fleet-refresh` skill
to run it, a consumer fleet with a live PR head to run it against (the nine
consumers' framework footprint was removed in the step 3-c PRs), and the
verifier task that was assigned to tick it — parked above.
### Disposition, 2026-09-01 — parked as superseded

The findings above are facts; this is the call made against them. The item is
parked, not finished and not abandoned.

**Not finished.** Acceptance criterion 1 — *"`sd-fleet-refresh` completes an
integration-only review through `sd-review` against a real PR head"* — is not
met and cannot be. Closing it needs three subjects that no longer exist: the
`sd-fleet-refresh` skill, a consumer fleet with a live PR head, and the
verifier task assigned to tick it. Ticking a box whose subject is gone is the
vacuous check this rollout keeps finding in its own gates; the box stays
unticked and the item stays out of `done` by declaration.

**Not abandoned.** The work landed. PR #535 merged `2026-08-22T10:58:45Z` as
`176d1819`, 32 files, +804/-223, and GitHub deleted the head branch at merge.
Six of the seven criteria were ticked against evidence that is still reachable
in history even though every path it cites has since been deleted from the
tree.

`status: in_progress` and `branch:` are left exactly as written. Both were true
when written; the `parked:` line and this note supersede them rather than
backdating the record. `sd_lib.status_report` reports any item under
`archive/` as `done` by location, so the `parked:` line is what distinguishes a
parked item from a finished one in `sd-status --parked`.

### Why no automated pass would ever have surfaced this

Worth recording as a class, not as this one instance. `bin/sd_sweep.py` excludes
twice — `item.archived or item.parked` at `:88`, then
`item.status != SWEEPABLE_STATUS or item.branch` at `:91` — and this item trips
the second condition on both halves: it reads `in_progress` and it names a
branch. D2's bulk-park applied the same two exclusions, which is what makes the
two passes comparable (`bin/sd_sweep.py:46-49`), and is why the three siblings went
to `docs/work/archive/2026-09/` on 2026-09-01 and this one did not.

Both exclusions are deliberate and neither should change: `in_progress` is
somebody's open work whatever its age, and a `branch:` field claims a branch
exists. But the two together describe a state nothing checks — **an
`in_progress` item whose branch has already merged**. The branch field outlives
the branch, the status outlives the work, and no sweep will ever nominate it.
That state is closed by a person reading the tree or it is not closed at all.
This item sat in it for ten days.
