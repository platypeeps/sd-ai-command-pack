# Implement — satellite gate offload

Two repositories, three pull requests. The design is in [design.md](design.md).
Steps 2 to 7 wait for the operator's answers to Q1 to Q3 there. Each step
names its check and the result that means failure.

## Step checklist

- [ ] 1. Measure, no code. Size S, 1 h.
      - On a fixture, run a hub `sd-ship prepare` at a head that a satellite
        prepare already took to `ready_to_send`. Record whether `sd-review`'s
        gate starts a check.
      - Count `sd-check` runs on the hub per merged item over one day of lane
        logs, as the baseline for step 7.
      - Check: both numbers are written on sd:2704 with the command that
        produced them. A number with no command fails the step.
- [ ] 2. System repository: the opt-in (Q1 = A). Size M, 3–4 h. Own PR.
      - `repo.satellite_gate` column, `off` by default, one migration.
      - `sd-db.sh repo satellite-gate <path> off|accept` and a `repos`
        reader beside `repo_ci`.
      - Check: `sd-db.sh test` passes; a new test shows an unset row reads
        `off` and a set row reads `accept`. On `main` that test fails.
- [ ] 3. Pack: the reader and the offload row, satellite side. Size M, 3–4 h.
      - `sd_lib.repo_satellite_gate`, which answers `off` on every fault,
        as `repo_ci` does.
      - In `bin/sd_gate_receipts.py`: `offload_key`, `pack_bin`,
        `record_offload`, `read_offload`.
      - In `check_in_worktree`: write the row after a recorded pass on a
        satellite, or from a reuse with no row; set `offload_error` on a
        failed write.
      - `sd gate check` refuses before the run when opted in and the hub
        does not answer.
      - Check: tests with `served_by` patched, as `SatellitePrepare` does.
        A pass writes both rows. A hub run writes no offload row. A reuse
        writes the missing row with the original `recorded_at`. Each test
        fails with the write removed.
- [ ] 4. Pack: acceptance on the hub. Size L, 4–5 h.
      - `--satellite-gate` on `sd-ship merge`.
      - The eight clauses of the trust rule in `sd_local_gate.local_gate`,
        through an offload mode of `check_in_worktree` that compares and
        never runs.
      - Codes and the hand-back `next_action` from one definition.
      - No status post on acceptance; `local_gate` saved with `satellite`
        provenance.
      - Check: one test per clause, each asserting its code and that the
        `run` callable was never called. The happy path sends the merge
        `PUT` with no `sd-check` child. Without the flag the existing merge
        suites pass unchanged. Each clause test fails with its clause removed.
- [ ] 5. Pack: the satellite's prepare posts the status. Size S, 1.5–2 h.
      - Post from the offload row through `post_gate_status`, with the
        description `head[:12] inputs <posted_inputs>: sat <hostname>: ...`.
      - Check: a satellite prepare posts one `sd/local-gate` to the GitHub
        double. With no row it posts nothing and reports `offload_error`.
        A hub prepare posts nothing new.
- [ ] 6. Pack: the lane. Size L, 4–5 h.
      - `lane enqueue --satellite --branch B` makes the worktree and the
        entry.
      - `process` skips prepare and passes `--satellite-gate`.
      - A `base_moved` or `satellite_*` refusal marks the entry
        `handed_back` and notes the item.
      - `speculate` skips a following satellite entry.
      - Check: tests in `tests/test_sd_ship_lane.py` with the ship double.
        A satellite entry's argv list holds no `prepare` and no `--catch-up`.
        A moved base ends `handed_back`. No speculative gate starts for it.
        Each fails with its branch removed.
- [ ] 7. Documentation, end to end, and the measurement. Size M, 2–3 h.
      - `WORKFLOW.md`: the satellite flow table.
      - Docstrings of `sd_gate_receipts` and `sd_local_gate`: the widened
        trust boundary and "every merge attempt posts" except an accepted
        offload receipt.
      - `CHANGELOG.md`, plus the satellite section of the system repository's
        `local-sd-db/README.md`.
      - Run acceptance criterion 5 of `prd.md` once, not committed.
      - Check: `sd-docs-lint` passes; the end-to-end run's merge log shows
        `satellite` provenance and no gate run. After a week, the hub's
        `sd-check` count per merged satellite item is 0. A count above 0
        means a path still gates on the hub; name it on sd:2704.

## Estimate

| Step | Hours |
|---|---|
| 1 | 1 |
| 2 | 3–4 |
| 3 | 3–4 |
| 4 | 4–5 |
| 5 | 1.5–2 |
| 6 | 4–5 |
| 7 | 2–3 |
| Total | 18.5–24, before review rounds |

Pull requests: step 2 in the system repository; steps 3 to 5 in one pack PR;
step 6 and step 7 in a second pack PR. Steps 3 to 5 touch the same gate
files, so they share one PR.

## Check

Each pack PR: `sd gate check --base main` passes at its head. Step 2:
`make check` in the system repository through its local gate.
