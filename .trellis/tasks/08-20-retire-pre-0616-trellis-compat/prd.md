# Retire the pre-0.6.16 vendored Trellis compatibility layer

## Goal

The fleet has converged on Trellis `0.6.16-sd.7`. Declare that as a supported
floor and remove the dual-version machinery the pack carried while the fleet
straddled `0.6.7` and `0.6.14` — but remove only what the floor actually
authorizes, not everything that merely *looks* like a version workaround.

## Measured starting state

Read from each checkout's `.trellis/.version` on 2026-08-20:

| Repo | Trellis |
|---|---|
| sd-ai-command-pack (this repo) | 0.6.16-sd.7 |
| rwbp-coordinator | 0.6.16-sd.7 |
| loadsmith | 0.6.16-sd.7 |
| hoa-manager | 0.6.16-sd.7 |
| rwbp-website | 0.6.16-sd.7 |
| mezmo_benchmark | 0.6.16-sd.7 |
| se-ai-command-pack | 0.6.16-sd.7 |
| sd-github-review | 0.6.16-sd.7 |
| anomaly-metric-creator | 0.6.16-sd.7 |

All nine at the same version. This is what makes a floor statable; it is a
snapshot, and the spec floor — not this table — is what future work reads.

## Problem

`.trellis/spec/tooling/vendored-trellis-compatibility.md` says a pack wrapper
"MUST work against both the current vendored version and <=0.6.7 consumers
until the fleet converges." The fleet converged, so every branch that exists
only to serve `<=0.6.7` is now unreachable code that still has to be read,
maintained, and reasoned about at every future change.

Three surfaces carry that dead weight, and one carries an actively wrong
instruction:

1. **The compatibility spec is stale on three axes.** Its signature table is
   pinned to "vendored task.py, 0.6.14"; its version-spread clause describes a
   condition that no longer holds; and its upgrade procedure prescribes
   `npx @mindfoldhq/trellis@<current>`, which cannot produce the fork builds
   (`0.6.16-sd.N`) the fleet actually runs.

2. **The status collector carries a three-way fallback** for `task.py current
   --json` — parse JSON, else treat stdout as a bare path, else re-run bare
   `current` — where only the first branch is now reachable.

3. **The record-session wrapper re-implements commit-subject rendering** that
   the vendored `add_session.py` now does natively, and does it *worse* (see
   below).

4. **Two surfaces forbid `task.py create --base-branch`** on the grounds that
   the vendored `task_store.py` rejects it as an unrecognized argument. That is
   no longer true, and the prohibition now costs correctness rather than buying
   it: without the flag, `create` falls back to the checked-out branch, which on
   a fleet refresh lane is the refresh branch — the exact defect the workaround
   was written to avoid.

## What this task explicitly does NOT remove

Recorded because the first pass of this review concluded otherwise, and the
code disagreed. Each was checked against the runtime, not against comments:

- **Testing / Next Steps section patching stays.** `add_session.py` renders
  `--test` through `_render_bullet_section(..., bullet_prefix="- [OK] ")`, which
  stamps `- [OK] ` on *every* item unconditionally. Delegating would turn
  `[WARN] flaky lane` into `- [OK] [WARN] flaky lane` and `- already bulleted`
  into `- [OK] - already bulleted`. The wrapper's marker-aware normalization has
  no native equivalent, so `replace_or_insert_section` is load-bearing.
- **Retry de-duplication stays.** `add_session.py --idempotency-key` makes an
  already-*committed* identical record a no-op. The wrapper's
  `existing_session_journals` handles a different case: an *uncommitted* journal
  half-written by a previous run that failed while staging. Complementary, not
  redundant.
- **The explicit `--branch` pass-through stays.** `resolve_session_branch` now
  resolves this correctly on its own, so the pass is redundant — but it is
  explicit, free, and covered by a test. Removing it trades a stated invariant
  for nothing.

## Requirements

- R1: Declare a supported vendored-Trellis floor of `0.6.16-sd.7` — the exact
  fork build recorded in `.trellis/.version` — in the compatibility spec, and
  refresh its signature table, upgrade procedure, and wrong/correct examples
  against the runtime at that floor. The floor must be stated as an identity,
  not as a semver range: `0.6.16-sd.7` carries a prerelease segment, so it
  orders *below* `0.6.16` under semver, and a naive `>=0.6.16` comparison would
  report every repository in the table above as non-compliant.
- R2: Remove the `current --json` fallback chain from the status collector,
  leaving the single documented path.
- R3: Stop the record-session wrapper re-writing commit-table rows. Delegate
  subject rendering to `add_session.py`, which resolves from the same object
  database and escapes the cell strictly better.
- R4: Remove the `create --base-branch` prohibition from the review preflight
  message and the fleet-refresh skill, and use the flag where the two-step
  `create` + `set-base-branch` dance existed to compensate for its absence.
- R5: Retire the tests that exist only to emulate `<=0.6.7`, and cover the
  behavior that replaces them.
- R6: Surface the vendored Trellis version in the human fleet report, which
  prints the pack pin and is silent about Trellis.
- R7: Record the disposition of the two adjacent task records this work
  resolves or re-scopes (`08-17`, `07-09`) rather than leaving them to describe
  a world that no longer exists.

## Acceptance criteria

- [ ] `.trellis/spec/tooling/vendored-trellis-compatibility.md` states the
  `0.6.16-sd.7` floor and the semver caveat, and no longer instructs wrappers to
  support `<=0.6.7`.
- [ ] `git grep -n "0\.6\.7\|0\.6\.14" -- templates/scripts tests scripts`
  returns no occurrence that describes a supported runtime (audit and task prose
  may cite them historically).
- [ ] The record-session wrapper no longer contains a commit-table row regex,
  and a commit subject containing a backslash, a pipe, and collapsed whitespace
  renders correctly in the journal.
- [ ] `make test` is green with no skips, `make lint` and `make audit` clean.
- [ ] The human `sd-status fleet` report prints a Trellis version per row.
- [ ] `python3 ./.trellis/scripts/task.py create --base-branch <b>` is the
  documented path; no shipped surface tells the reader it will be rejected.
- [ ] The four copies of each changed script (`templates/scripts/`, `scripts/`,
  `plugins/sd/bin/`, `plugins/sd/machine-payload/scripts/`) stay byte-identical
  via `make generate` + `make sync`.
- [ ] Shipped payload under `templates/**` changed, so `manifest.json` carries a
  bumped version, `CHANGELOG.md` carries a matching top heading, and
  `docs/fleet/candidate-validation.json` is the all-pass ledger produced by
  `make release-prep` for the exact payload. The `Release payload gate` CI job
  passes.

## Out of scope

- The `npm install -g @mindfoldhq/trellis@latest` instruction in `README.md`,
  `docs/`, `templates/docs/`, and `tests/install_test_support.py`. npm's
  `latest` is `0.6.15`; the fleet runs the unpublished fork `0.6.16-sd.7`, so a
  consumer following the documented instruction installs a CLI *below* this
  task's floor, and `trellis update` from it would downgrade a converged repo.
  That is a real defect with a user-facing decision attached; it belongs to
  parked task `07-09-trellis-version-compatibility` (R5/R6), whose trigger this
  work fires. R7 records the evidence there; the fix is not attempted here.
- Adopting `task.py list --json` in the status collector. Considered and
  declined — see `design.md`.
