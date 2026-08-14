# Implementation plan: discount superseded check runs

Source of truth is `templates/`; `scripts/` and the plugin payload copies are
regenerated. Never hand-edit a generated copy.

## 1. The supersession pass

`templates/scripts/sd-ai-command-pack-pr-eligibility.py`

- [x] Add `parse_check_started_at(raw, index) -> datetime | None`: returns
      `None` when `startedAt` is absent or `null`; raises
      `EligibilityInputError(f"pull request check {index} is invalid")` when it
      is present but not a string or not parseable as ISO-8601. Normalize the
      trailing `Z` GitHub emits with `value.replace("Z", "+00:00")` before
      `datetime.fromisoformat`: the repository floor is Python 3.10
      (`pyproject.toml:5`; CI matrix at `.github/workflows/tests.yml:420`) and
      `fromisoformat` did not accept `Z` until 3.11. Same idiom as
      `sd-ai-command-pack-work-loop.py:236`.
- [x] Add `superseded_check_indexes(rows) -> dict[int, dict[str, Any]]`:
      one pass to bucket `CheckRun` rows by `(workflowName, name)`, then for
      each bucket that contains at least one `CANCELLED` row, compare
      timestamps. Returns a map from the 1-based index of each superseded row
      to `{"index": <1-based index of the superseding row>, "startedAt": <its
      raw string>}`. Buckets with no `CANCELLED` row read no timestamp at all.
- [x] Bucket key normalization: `workflowName` absent → `""`. A row whose
      `name` is absent or not a string is never bucketed — it neither is
      superseded nor supersedes. Do not bucket on the `"unnamed"` display
      placeholder.
- [x] Ordering: strictly later wins; equal timestamps do not supersede. When
      several siblings are later, cite the latest one.
- [x] A row whose own `startedAt` is absent is never superseded. A sibling whose
      `startedAt` is absent can never supersede.
- [x] `parse_checks` runs the pass once before the classification loop, then
      for each `CheckRun`: if its index is in the map, append `"superseded":
      True` and `"supersededBy": {...}` to the observed item and skip the
      `blocking += 1` branch. It must not become `successful`.
- [x] `StatusContext` handling is untouched.

Validation: `python3 -m unittest tests.test_pr_eligibility -v`.

## 2. Tests

`tests/test_pr_eligibility.py`

The module-level `check_run` helper has no `startedAt`; extend it with an
optional `started_at` keyword that is omitted from the dict when `None`, so
every existing call keeps producing today's exact fixture.

- [x] PR #360 shape, verbatim from the PRD table: five names, each `CANCELLED`
      on the earlier run and `SUCCESS`/`SKIPPED` on the later one. Assert
      `blocking == 0` and that the end-to-end verdict is `eligible` with
      `reasonCodes == []`.
- [x] A lone `CANCELLED` row with no sibling still yields `checks_blocking`.
- [x] A rollup whose every row is superseded is refused by `checks_no_success`,
      not by an empty blocking count.
- [x] Observed evidence: the superseded item carries `superseded` and a
      `supersededBy.index` that points at the surviving row. Include a
      `StatusContext` row ahead of the superseded `CheckRun` in that fixture,
      so an off-by-one between input index and `items` position fails the test.
- [x] Two nameless `CheckRun` rows do not bucket together: a `CANCELLED` row
      with no `name` stays blocking even when a later nameless row exists.
- [x] Equal `startedAt` on both rows does not supersede — still blocking.
- [x] A `CANCELLED` row whose `startedAt` is present but malformed raises
      `EligibilityInputError`; one whose `startedAt` is absent does not raise
      and stays blocking.
- [x] Matrix-template rows (`test heavy (py${{ matrix.python-version }})` and
      `test heavy (py3.14)`) are separate identities and do not collapse.
- [x] Same name under two different `workflowName` values does not collapse.
- [x] One query per invocation on the eligible (`CLEAN`) path: assert the `gh`
      invocation count recorded by `FixtureRunner.calls`
      (`tests/test_pr_eligibility.py:123`) is unchanged from the existing
      baseline (R5). The `BLOCKED`-diagnosis path may reach `collect_threads`
      more often by design; see `design.md`.
- [x] Every pre-existing test in this module still passes unmodified except the
      `check_run` signature extension.

## 3. Payload and release plumbing

- [x] `make generate`, then `make sync` after the manifest bump.
- [x] `manifest.json` version bump; `CHANGELOG.md` entry under Fixed naming
      issue #414.
- [x] `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-check.py --json`
      → `passed`.

## 4. Ship

- [ ] Branch `task/eligibility-superseded-runs`, base `main`.
- [ ] PR body: closes #414, states the identity/order decision and why
      `CANCELLED`-only.
- [ ] Review loop with Copilot; merge when green and comment-clean.

## Verification (named before the work)

Falsifiable check, run against the PR #360 rollup shape as a fixture:

1. Build the rollup from the PRD's observed table — five `CANCELLED` rows from
   run `31227464221` and their five replacements.
2. Run the probe against it.
3. It must report `status: eligible` with `reasonCodes: []`.

Failure is any `checks_blocking` reason code, or a `blocking` count above zero.
The negative half of the same check: delete the five replacement rows from that
fixture and the probe must go back to `checks_blocking` — if it does not, the
rule has become a blanket `CANCELLED` allow-list, which R2 forbids.

Scope check for the blast radius — this probe is vendored into every consumer
and read by three commands, so before claiming completion:

- `grep -rn "parse_checks\|blockingCount\|checks_blocking" --include=*.py
  --include=*.md --include=*.sh .` to enumerate every reader of the count and
  every doc that states the old behaviour.
- `python3 -m unittest discover tests` for the whole suite.

## Rollback

Single commit revert; the rule reads and writes no persisted state.
