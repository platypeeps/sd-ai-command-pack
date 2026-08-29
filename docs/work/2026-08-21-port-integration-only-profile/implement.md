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
