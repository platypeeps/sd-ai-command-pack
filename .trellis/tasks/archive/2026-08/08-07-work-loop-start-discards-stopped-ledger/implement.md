# Implementation: `start` refuses a non-resumable ledger

Design: [`design.md`](design.md). Every source edit lands in
`templates/scripts/sd-ai-command-pack-work-loop.py`; `make sync` mirrors it to
`scripts/`, `make generate` regenerates `plugins/`. The two are byte-identical
today (`diff -q` clean) and must stay that way.

Tests load the module from `templates/scripts/` — confirm with
`grep -n "load_module" -A 6 tests/test_work_loop.py` before assuming, since
`tests/test_housekeeping_result.py` loads the `scripts/` mirror instead and the
asymmetry has cost a false green before.

## Step 0 — red check first

Before editing, write the four tests of Step 5 and run them at HEAD. Record
which fail and which pass. A test that is green before the change proves
nothing about the change; if all four pass at HEAD, the tests are wrong, not
the code.

```bash
.venv/bin/python -m unittest tests.test_work_loop 2>&1 | tail -5
```

## Step 1 — hoist the `--run-id` guard

In the `start` handler, move the mismatch check out of the
`if state["status"] in {"active", "paused"}:` gate so it runs for every
existing ledger, immediately after the repository-identity check.

Acceptance criterion 2's mismatch half is satisfied here.

## Step 2 — add `--resume` and `--reset`

`build_parser()`, the `start` subparser: two `store_true` flags. Reject both
together with `WorkLoopError("conflicting_start_intent: --resume and --reset
are mutually exclusive")` before any file is read.

`--resume` with no existing ledger is an error, not a silent new run: a caller
that says "continue the run" and gets a fresh one is the same class of defect
this task exists to remove.

## Step 3 — the refusal

Replace the fall-through. After the guards, with `E` the loaded ledger:

- `E.status in {"active", "paused"}` and not `--reset` → today's resume path,
  unchanged, including the conflict and focus guards.
- `E.status not in {"active", "paused"}` and neither flag → raise, naming the
  status, the run ID, and both flags. **This is the behavior change.**
- `--resume` on any status → run the same conflict/focus guards, acquire the
  lock, set `status = "active"`, refresh `updatedAt`/`heartbeatAt`, write.
  Leave `iteration`, `counters`, `phase`, `current`, `contextHealth`,
  `stopReason`, and `terminalReconciliation` untouched.
- `--reset` → Step 4, then `new_state`.

## Step 4 — archive on `--reset`

Before writing the new ledger, write the `work-loop-replaced-ledger` wrapper
from the design to `replaced.json` beside `state.json`, through the same
`atomic_write_json` every other write uses. Refuse `--reset --run-id <E.runId>`
— acceptance criterion 2's match half.

Extend `status_snapshot` (`:2530`) with the replaced-ledger row: present/absent,
the replaced run ID, and the timestamp. Absent is the ordinary case, not an
anomaly. Read it the way `_read_status_lock` (`:2506`) reads the lock — status
is read-only and a malformed sibling reports present-but-unreadable rather than
raising.

`--reset` against an `active` ledger still passes through `acquire_lock`
(`:1149`), which refuses a live lock. Order the archive after the lock is held,
so a refused `--reset` writes nothing at all.

## Step 5 — tests (`tests/test_work_loop.py`)

Criterion 3 asks for coverage of *each* persisted status against `start` with
and without `--run-id`. Drive that from `module.STATUSES` rather than a hand
list, so a status added later fails the test instead of slipping past it.

| Test | Asserts |
|---|---|
| `test_start_refuses_every_non_resumable_status` | for each status in `STATUSES - {"active","paused"}`, bare `start` exits nonzero, the message names the status, and `state.json` is byte-identical afterward |
| `test_start_run_id_guards_every_persisted_status` | for each status in `STATUSES`, `start --run-id <other>` raises the already-exists error — the guard is no longer status-conditional |
| `test_reset_archives_the_outgoing_ledger_and_refuses_its_run_id` | `--reset` writes `replaced.json` whose `state` equals the outgoing ledger and whose `kind` is `work-loop-replaced-ledger`; `--reset --run-id <outgoing>` exits nonzero and writes nothing |
| `test_resume_reactivates_a_stopped_run_without_resetting_its_history` | `--resume` on a stopped run yields the same `runId`, `iteration`, and `counters`, `status == "active"`, and a preserved `stopReason` |

Byte-identity of the untouched ledger matters more than field equality: the
incident was a whole-file replacement, so compare the file's bytes.

Criterion 3's matrix has a fourth cell those two tests do not reach: `active`
and `paused` with no `--run-id`, which must still resume. Cover `paused` with
the existing test named below, and add the `active` row to
`test_start_run_id_guards_every_persisted_status`'s loop as a no-flag assertion
so every status is exercised in both columns.

`test_cli_resumes_paused_run_and_does_not_create_repo_state`
(`tests/test_work_loop.py:3124`) must stay green untouched — paused resume is
explicitly out of scope.

## Step 6 — callers, docs, surfaces

Enumerate from the filesystem, not from this list:

```bash
grep -rn "work-loop.py" --include='*.md' templates docs
```

At planning time that returns six files. Two are not callers and must not be
edited: `docs/review-learnings.md` is a historical findings log, and
`templates/.agents/skills/sd-work-backlog/references/terminal-reconciliation.md`
cites `reconcile-terminal`, not `start`. `docs/SD_AI_COMMAND_PACK.md` is the
generated mirror of the `templates/docs/` source. The remaining three:

- `templates/.agents/skills/sd-work-backlog/SKILL.md`: the `start` block gains
  `--reset` for a genuinely new run after a stopped or completed one, and the
  prerequisites paragraph notes that a non-resumable ledger refuses.
- `templates/.agents/skills/sd-work-backlog/references/run-recovery.md`:
  `--resume` beside `reconcile`, with the ordering — reconcile when live state
  may disagree, resume when it does not.
- `templates/docs/SD_AI_COMMAND_PACK.md`: the work-loop section's `start`
  description.

Then `make sync && make generate`, and re-prepare the candidate ledger
(`python3 scripts/sd-ai-command-pack-fleet-candidate-check.py`) since the
payload digest moves. Bump `manifest.json` + `.sd-ai-command-pack/manifest.json`
and add the `CHANGELOG.md` entry.

## Validation

```bash
.venv/bin/python -m unittest tests.test_work_loop
diff -q scripts/sd-ai-command-pack-work-loop.py \
        templates/scripts/sd-ai-command-pack-work-loop.py
grep -rn "work-loop.py start" --include='*.md' templates docs   # every copy current
make generate
make check
```

The live ledger for this very run is `active`, so it exercises none of the
changed paths — but the run's own `start` is the surface being changed, so do
not run `start` against it to try the new behavior. Use a throwaway
`--state-home` under the scratchpad.

## Rollback points

- After Step 1: the guard hoist alone is independently correct and shippable.
- After Step 3: the refusal without `--reset`'s archive still satisfies
  criteria 1 and 2; the archive is additive.
- After Step 6: revert is one `git revert` — no data migration, since
  `replaced.json` is only ever written, never required.

## Out of scope

- `reconcile` semantics, `terminal_reconciliation`, and the checkpoint overlay.
- Lock recovery (`--recover-stale-lock`) behavior.
- Any change to `active`/`paused` resume.
