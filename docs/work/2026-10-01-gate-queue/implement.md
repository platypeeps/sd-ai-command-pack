# Implement — gate queue

One pull request. The design is in [design.md](design.md).

## Step checklist

- [x] 1. Queue and admission, in `bin/sd_gate_slots.py`. Size M.
      - `Queue`: the admission lock, tickets, `queue.state`, dead-ticket
        removal.
      - `LoadRule`: limit and settle time, read from the variables, the
        machine settings and the defaults.
      - `wait_for_slot` admits through the queue; `acquire` and the `wait`
        helper keep their signatures.
- [x] 2. `run` and `status`, in `bin/sd_gate_slots.py`, and the `gate` group
      in `bin/sd`. Size S.
      - `run`: process group, signal forwarding, exit codes from `prd.md`.
      - `status`: holders, waiters, load and settings; `--json`.
- [x] 3. Settings, in `bin/sd_lib.py`: `gate_load_max` and
      `gate_settle_seconds` in `CORE_CONFIG`. `sd-check` passes them on.
- [x] 4. Tests, in `tests/test_sd_gate_slots.py` and a new
      `tests/test_sd_gate_queue.py`. Fail-first on `origin/main`:
      - order: waiters queued one by one on 1 slot start in that order;
      - concurrency: 5 `sd gate run` waiters on 2 slots and on 1 slot never
        overlap past the cap;
      - load: a high load1 admits nobody; a low load1 with a high load5
        admits after the settle time; two admissions keep the spacing;
      - recovery: a SIGKILLed holder frees its slot, a dead waiter's ticket
        goes away, and the queue moves on;
      - `run` exit codes and signal forwarding; `status` names holders and
        waiters.
- [x] 5. Documentation: `WORKFLOW.md`, `README.md`, `AGENTS.md` lines on the
      settings, and a `CHANGELOG.md` Unreleased entry.

## Check

`SD_LOCAL_GATE=1 TEST_WORKERS=6 make check` passes. The focused suites pass
first: `python3 -m unittest tests.test_sd_gate_slots tests.test_sd_gate_queue`.
