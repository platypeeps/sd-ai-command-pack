# Implement — lane host per repository

The design is in [design.md](design.md). Four pull requests and one system pin bump (step 9): system first, pack second, retirements last.
Each step leaves the hub and every satellite working. Each step's check names the criteria of [prd.md](prd.md) it covers.

## PR 1 — system: the setting, the dashboard control, the lock

- [ ] 1. Migration `024_repo_lane_host.sql`: `repo.lane_host TEXT`, default `NULL`, with a `CHECK` on the name shape.
      Check: `sd-db.sh test`; a migrated copy reads `NULL` on every row (criterion 5).
- [ ] 2. `sd_db/repos.py`: `set_lane_host`, `repo_lane_host`; `sd-db.sh repo lane-host PATH HOST|hub`; the column in `repo list`.
      Check: the verb tests fail first, then pass (criteria 1, 2).
- [ ] 3. `sd_db/ship.py`: `hosts_lane`, `LaneElsewhere`, and `repository_lock` calls it; local lock directory on a satellite host.
      Check: lock tests for hub, non-host and satellite host fail first, then pass (criteria 6, 7).
- [ ] 4. Dashboard: `lane_host` in `management_screen._repos`, `lane-host` in `SETTERS` and the `/api/repos/` route,
      the field and the Move lane action in `management.js`. Invoke the `hallmark` skill before the page change.
      Check: `dashboard.sh test`; the route tests fail first, then pass (criteria 2, 3, 4).
- [ ] 5. `local-sd-db/README.md`: a "Lane host" section; mark "Satellite gate offload" as retiring under sd:3003.
      Check: `make check` passes.

All rows stay `NULL`, so behaviour is unchanged after PR 1.

## PR 2 — pack: the host check and the hosted lane job

- [ ] 6. `bin/sd_lib.py`: `hosts_lane`, fail-closed on an older `sd_db`. Check: unit tests for each fallback.
- [ ] 7. `bin/sd-ship`: `dispatch` routes `prepare` on a non-host to the lock-free path; the lock's `lane_elsewhere` reaches the JSON answer.
      Check: the merge and prepare tests fail first, then pass (criteria 8, 9).
- [ ] 8. `bin/sd_lane.py`: the queue verbs refuse on a non-host; `lane run --hosted`; the runner reads the setting before each claim.
      Check: the lane tests fail first, then pass (criteria 9, 10, 11).
- [ ] 9. In system, one small pull request: `.sd-pack-rev` to this pack revision, and `local-cron-jobs/examples/lane-run.job`.
      Check: system `make check`.

## Rollout (no pull request)

- [ ] 10. Install the `lane-run.job` example on every machine; remove each hub `satellite-lane-<repo>.job`.
- [ ] 11. Check that no `lane-request:v1:` row is `requested` or `queued`. Then move each satellite repository with the dashboard control.
      Record each move in `sd task note 3003`.

## PR 3 — pack: retire the satellite hand-off

- [ ] 12. Delete design.md "What retires" rows 1, 2, 3 and 5, their tests, and the `WORKFLOW.md` steps.
      Check: grep `lane-request\|satellite-gate\|publish_pack` under `bin/` and `tests/` finds nothing (criterion 12).
- [ ] 13. Delete row 4: offload receipts and the offload environment. Grep for other callers of `sd_gate_tools` first.
      Check: the gate suites pass; grep `offload_` under `bin/` finds nothing.
- [ ] 14. Archive `docs/work/2026-10-05-satellite-gate-offload/` as superseded. Check: `sd-docs-lint` passes.

## PR 4 — system: retire the opt-in column

- [ ] 15. Migration drops `repo.satellite_gate`; delete `set_satellite_gate`, `repo_satellite_gate`, the verb and the README section.
      Delete `local-cron-jobs/examples/satellite-lane-run.job`. Check: `make check`; criterion 13.
