# fleet-publish: pack self-publish trips completion_archive_move_missing

## Goal

fleet-publish.py commits the active task at H1 and archives it at H2 in a single push. On consumer repos this is fine, but the pack's OWN bookkeeping CI (.github/scripts/bookkeeping_ci_scope.py + tests.yml 'Validate bookkeeping head') validates each incremental push (github.event.before..head) and, in completion mode, requires the live task to PRE-EXIST the finish-work push. So self-publishing 0.64.4 via the helper failed completion_archive_move_missing on the folded head (PR #318), forcing an un-fold + post-merge archival instead. Fix options: (a) make the helper commit/push the live task in an earlier push so it pre-exists finish-work, (b) add a pack-repo-aware mode that skips the fold when the target repo carries this bookkeeping gate, or (c) document that fleet-publish is consumer-only and must not be used to self-publish the pack. Repro: run fleet-publish on a task never previously committed-live on the branch, then check completion --base <prev-head> --head <folded-head>.

## Requirements

Child C of `08-04-0-64-5-followup-hardening`. **Decision: approach (c)** — guard +
doc, consumer-only. Full design in the parent `design.md` §C and `implement.md`
Phase C.

- `fleet-publish.py check_preconditions` must refuse to run against the pack's own
  repo, detected by the presence of `.github/scripts/bookkeeping_ci_scope.py`,
  raising `PublishError(..., code=3)` that points self-publish to `sd-finish-work`.
- Consumer checkouts (no such gate) are unaffected.
- Document fleet-publish as consumer-only in `docs/FLEET_ROLLOUT.md` and the
  module docstring.

## Acceptance Criteria

- [ ] Guard raises code 3 with a sd-finish-work pointer on a pack-shaped tree (test).
- [ ] Consumer-shaped tree passes the guard (test).
- [ ] `docs/FLEET_ROLLOUT.md` + docstring state consumer-only.
- [ ] `.venv/bin/python -m unittest tests.test_fleet_publish` green.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
