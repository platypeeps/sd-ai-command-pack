# Copilot ruleset snapshot — 2026-08-21

Pre-change snapshot of every GitHub branch ruleset that carries a
`copilot_code_review` rule across the pack fleet, captured before the planned
removal of automatic Copilot review invocation.

## Why this exists

`sd-review-pr` owns remote-review invocation directly: it requests the
configured reviewer (`@copilot` by default) only after the typed deterministic
`sd-check` passes, readies drafts first, and records a UTC trigger timestamp
against the Step 1 `HEAD_SHA` for each round. A repository ruleset that
requests Copilot automatically duplicates that request, and on the repos with
`review_on_push=true` it defeats the fleet integration-only profile, which
deliberately suppresses a new review request and records `0` remote rounds.

The planned change removes the `copilot_code_review` rule from each
pack-managed repo's active branch ruleset while preserving `deletion` and
`non_fast_forward`, and deletes the dormant duplicate rulesets.
`platypeeps/people-profiles` was initially excluded on the stated grounds that
it is not a pack consumer, so its ruleset was the only Copilot path it had.
That premise was retracted the same day; see below.

## Status: applied 2026-08-21, one repository outstanding

The change has since been applied. Nine of the ten `main` rulesets in scope
were updated and verified by re-reading each from the server: all now report
`active` with rules exactly `deletion, non_fast_forward`. Five of the six
dormant duplicates were deleted. (Scope grew from nine to ten when
people-profiles stopped being an exemption — see below.)

Note for anyone repeating this: the update verb is `PUT`, not `PATCH` — GitHub
answers `PATCH /repos/{owner}/{repo}/rulesets/{id}` with a 404. `PUT` replaces
the whole ruleset object, so the payload must carry `name`, `target`,
`enforcement`, `conditions`, and `bypass_actors` alongside the filtered `rules`
array. Every snapshot below was checked first and carried zero bypass actors
and zero ref excludes, so nothing was dropped in the replacement.

**Outstanding: `answerbook/mezmo_benchmark`.** Both its `main` ruleset
(17617454) and its dormant duplicate (19498731) still carry
`copilot_code_review`. The account running this holds `push` but not `admin` on
that repository, and ruleset writes require admin; GitHub returns 404 rather
than 403. Someone with admin in the `answerbook` organization has to apply the
same two operations there.

**`platypeeps/people-profiles`: exemption retracted, change applied.** The
exemption rested on the repository not being a pack consumer. It was onboarded
to the fleet on 2026-08-21 — refreshed to 0.71.41, converted to a thin install,
and registered at priority 80 in the `final` cohort — so `sd-review-pr` now
owns review invocation there and the ruleset became the same duplicate request
it is everywhere else. Its dormant duplicate was the worse case in the fleet:
alone among the six it was `enforcement=active`, and it carried
`review_on_push=true` and `review_draft_pull_requests=true`, reviewing on every
push and on drafts — exactly what the fleet integration-only profile
suppresses.

The same two operations were applied. Ruleset 19745583 (`main`) was `PUT`
without `copilot_code_review` and re-read from the server: `active`, rules
exactly `deletion, non_fast_forward`. Duplicate 19745586 was deleted, and the
repository now lists one ruleset.

## Scope at capture time

Active `main` ruleset carrying the rule (`deletion, non_fast_forward,
copilot_code_review`):

| Repo | Ruleset ID | `review_on_push` |
| --- | --- | --- |
| platypeeps/anomaly-metric-creator | 16463652 | false |
| platypeeps/hoa-manager | 17715824 | false |
| platypeeps/loadsmith | 18413458 | false |
| platypeeps/rwbp-coordinator | 17617529 | true |
| platypeeps/rwbp-website | 17617253 | true |
| platypeeps/sd-github-review | 19520648 | false |
| platypeeps/se-ai-command-pack | 19131581 | false |
| platypeeps/sd-ai-command-pack | 18446633 | false |
| platypeeps/people-profiles | 19745583 | false |
| answerbook/mezmo_benchmark | 17617454 | true |

Duplicate rulesets named `Code Quality Copilot review for default branch`,
rule set `copilot_code_review` only. All were `enforcement=disabled` except
people-profiles', which was `active`:

All but the last were deleted; `answerbook/mezmo_benchmark`'s survives.

| Repo | Ruleset ID |
| --- | --- |
| platypeeps/anomaly-metric-creator | 19351660 |
| platypeeps/hoa-manager | 19420797 |
| platypeeps/rwbp-coordinator | 19498427 |
| platypeeps/rwbp-website | 19431677 |
| platypeeps/people-profiles | 19745586 |
| answerbook/mezmo_benchmark | 19498731 |

## File naming

`<owner>_<repo>__<ruleset id>.json`, each the verbatim
`GET /repos/{owner}/{repo}/rulesets/{id}` response body.

## Restoring

To put back the `copilot_code_review` rule on a single ruleset, `PUT` the
snapshot's own rule set back. Use `PUT`, not `PATCH`: `PATCH` on a ruleset
answers 404. Because `PUT` replaces the whole object, send the identifying
fields alongside the rules rather than the `rules` array on its own:

```bash
jq -c '{name, target, enforcement, conditions,
        bypass_actors: (.bypass_actors // []), rules}' \
  <owner>_<repo>__<id>.json > payload.json
gh api -X PUT "repos/<owner>/<repo>/rulesets/<id>" --input payload.json
```

Ruleset writes require `admin` on the repository. Without it GitHub answers
404, not 403, so a permissions problem and a wrong verb look identical — check
`gh api repos/<owner>/<repo> --jq .permissions.admin` before concluding which
one you have hit.

To recreate a deleted ruleset, POST the snapshot with the server-owned fields
stripped:

```bash
jq -c 'del(.id, .created_at, .updated_at, .node_id, .source, .source_type, ._links)' \
  <owner>_<repo>__<id>.json > payload.json
gh api -X POST "repos/<owner>/<repo>/rulesets" --input payload.json
```

Recreating assigns a new ruleset ID; the IDs in the tables above will no longer
resolve after a delete-and-recreate cycle.
