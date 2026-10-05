# Implement — satellite gate offload

Two repositories, four pull requests. The design is in [design.md](design.md).
The operator ruled Q1 to Q3 on 2026-10-05 (design.md, "Decisions"). Each step
names its check and the result that means failure.

## Step checklist

- [ ] 1. Measure, no code. Size S, 1 h.
      - On a fixture, run a hub `sd-ship prepare` at a head that a satellite
        prepare already took to `ready_to_send`. Record whether `sd-review`'s
        gate starts a check.
      - Count `sd-check` runs on the hub per merged item over one day of lane
        logs, as the baseline for step 8.
      - Check: both numbers are written on sd:2704 with the command that
        produced them. A number with no command fails the step.
- [ ] 2. System repository: the opt-in (Q1). Size M, 3–4 h. Own PR.
      - `repo.satellite_gate` column, `off` by default, one migration.
      - `sd-db.sh repo satellite-gate <path> off|accept` and a `repos`
        reader beside `repo_ci`.
      - Check: `sd-db.sh test` passes; a new test shows an unset row reads
        `off` and a set row reads `accept`. On `main` that test fails.
- [ ] 3. Pack: the reader and the offload row, satellite side. Size M, 4–5 h.
      - `sd_lib.repo_satellite_gate`, which answers `off` on every fault,
        as `repo_ci` does.
      - In `bin/sd_gate_receipts.py`: `offload_key`, `pack_bin`,
        `record_offload`, `read_offload`.
      - In `check_in_worktree`: write the row after a recorded pass on a
        satellite, or from a reuse with no row; set `offload_error` on a
        failed write, and keep the pass.
      - The pre-gate warning against `sd-lane-pack:v1:<slug>`.
      - Check: tests with `served_by` patched, as `SatellitePrepare` does.
        A pass writes both rows. A hub run writes no offload row. A reuse
        writes the missing row with the original `recorded_at`. An
        unreachable hub still runs the check and reports `offload_error`.
        A differing published digest prints the warning. Each test fails
        with its branch removed.
- [ ] 4. Pack: acceptance on the hub. Size L, 5–6 h.
      - Split `gate_binding` into a tree part and a machine part; its output
        is unchanged.
      - `--satellite-gate` on `sd-ship merge`.
      - The eight clauses of the trust rule in `sd_local_gate.local_gate`,
        through an offload mode of `check_in_worktree` that compares and
        never runs.
      - `base_moved` on `ready`'s behind refusal.
      - Codes and the hand-back `next_action` from one definition.
      - No status post on acceptance; `local_gate` saved with `satellite`
        provenance.
      - Check: one test per clause, each asserting its code and that the
        `run` callable was never called. A hub whose `PATH` lacks the
        repository's tool still compares and accepts. The happy path sends
        the merge `PUT` with no `sd-check` child. Without the flag the
        existing merge suites pass unchanged. Each clause test fails with its
        clause removed.
- [ ] 5. Pack: the satellite's prepare posts the status. Size S, 1.5–2 h.
      - Post from the offload row through `post_gate_status`, with the
        description `head[:12] inputs <gate_inputs(root, head)>: sat <hostname>: ...`.
      - Check: a satellite prepare posts one `sd/local-gate` to the GitHub
        double. With no row it posts nothing and reports `offload_error`.
        A hub prepare posts nothing new.
- [ ] 6. Pack: the request row and intake (Q2). Size L, 6–7 h.
      - `sd-ship lane request --item N [--manual]`: refuses on the hub and on
        an item not `ready_to_send` at the pushed head; writes
        `lane-request:v1:<slug>:<item>`.
      - `intake` in `bin/sd_lane.py`, called by `run_lane` before each
        claim: the six steps of design.md, "Intake".
      - Outcome write-back from `finish`; the item note for `handed_back`
        and `failed`.
      - `lane run` publishes `sd-lane-pack:v1:<slug>` at start and after a
        pack fast-forward.
      - Check: tests in a new `tests/test_sd_lane_requests.py`. One per
        intake refusal: no queue entry, reason on the row. A second request
        supersedes a pending entry. A running entry leaves the request
        `requested`. A crash injected between the queue write and the row
        write takes the request in once. A revision conflict on the row is
        retried at the next intake. Each fails with its step removed.
- [ ] 7. Pack: processing a satellite entry. Size M, 3–4 h.
      - `process` for `gate: satellite`: fetch, head check, base check, merge
        with `--branch` and `--satellite-gate`; no prepare.
      - A `head_moved`, `base_moved` or `satellite_*` outcome marks the entry
        `handed_back`.
      - `speculate` skips a following satellite entry.
      - `clean_up` deletes `origin/B` with a lease on the merged head.
      - Check: tests in `tests/test_sd_ship_lane.py` with the ship double.
        A satellite entry's argv list holds no `prepare` and no `--catch-up`.
        A moved base ends `handed_back` with no merge call. No speculative
        gate starts for it. The remote branch is deleted only at the merged
        head. Each fails with its branch removed.
- [ ] 8. Documentation, scheduling, end to end, and the measurement. Size M, 2.5–3.5 h.
      - `WORKFLOW.md`: the satellite flow table.
      - Docstrings of `sd_gate_receipts`, `sd_local_gate` and `sd_lane`:
        the widened trust boundary, "every merge attempt posts" except an
        accepted offload receipt, and intake.
      - `CHANGELOG.md`, plus the satellite section of the system repository's
        `local-sd-db/README.md` and a `local-cron-jobs` example for the
        scheduled `lane run`.
      - Run acceptance criterion 6 of `prd.md` once, not committed.
      - Check: `sd-docs-lint` passes; the end-to-end run's merge log shows
        `satellite` provenance and no gate run. After a week, the hub's
        `sd-check` count per merged satellite item is 0. A count above 0
        means a path still gates on the hub; name it on sd:2704.

## Estimate

| Step | Hours |
|---|---|
| 1 | 1 |
| 2 | 3–4 |
| 3 | 4–5 |
| 4 | 5–6 |
| 5 | 1.5–2 |
| 6 | 6–7 |
| 7 | 3–4 |
| 8 | 2.5–3.5 |
| Total | 26–32.5, before review rounds |

The first draft estimated 18.5–24 h with SSH enqueue. The request row (Q2)
adds the request verb, intake and its crash recovery, outcome write-back and
the scheduled job. The planning review added the binding split, the pre-gate
warning and the base check.

Pull requests:

1. Step 2, in the system repository. It lands first; the pack reads `off`
   until it does.
2. Steps 3 to 5, in one pack PR. They touch the same gate files.
3. Steps 6 and 7, in a second pack PR. They touch the lane.
4. Step 8's `local-cron-jobs` example, in the system repository. The pack's
   documentation goes with PR 3.

## Check

Each pack PR: `sd gate check --base main` passes at its head. Each system PR:
`make check` through its local gate.
