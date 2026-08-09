# Fix PR evidence (PR #386, run 31291158452)

Head `41a6c06d4c283a3194ba685aab6d16477a1ec1d4`, event `pull_request`,
action `opened` (initial head — the guaranteed-full case).

## Full mode, event head validated

CI scope job 93188459919, conclusion `success`, step conclusions read
from the Actions API:

- `Classify exact-head CI scope`: success
- `Install review preflight coverage tooling`: success (unconditional)
- `Validate event head`: **success** — ran on a full-mode head
- `Validate bookkeeping head`: **skipped** (mode is full — final-bundle
  half correctly stays bookkeeping-only)
- `Report review preflight JavaScript coverage`: success

Full mode further confirmed by job conclusions on the same run: the
unittest matrix (3 lanes), lint, security, and release-payload-gate all
RAN (a bookkeeping head would have skipped them) and passed.

## Base correctness (from the run log, job 93188459919)

```
EVENT_BASE_SHA: 3c247269abfc47b7b135eee7a9b8d044c2371bc9
SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF="$EVENT_BASE_SHA" \
```

`3c247269` is the pull request's base (`main` tip at PR creation), not
the PR's previous head — on an `opened` head there IS no previous head,
which is exactly why the old `BEFORE_SHA` design could never run here.

## Preflight outcome on this head

```
Review preflight: 0 failure(s), 2 warning(s).
```

(The two warnings: multi-task-directory advisory — this task's artifacts
plus the spec page — and the tooling/generated scope advisory, both
dispositioned in the PR body's scope section.)

## c8 coverage measured in full mode (first time)

```
review-preflight.mjs coverage: 40.36% (2193/5433 lines)
```

Non-zero measured lines in a full-mode run — the coverage plumbing and
zero-line guard now cover both lanes. The guard's ability to fire is
proven separately in `local-replays.md` (replay 4).

## Aggregate

`CI Result` conclusion: success (9/9 required-lane states permitted).
Copilot review: 8/8 files, zero comments (review 4890382518).

Note: the `Shell coverage` lane (not in `ci-result.needs`, pre-existing)
failed once on `test_completion_successor_finds_recent_anchor_in_long_history`
under kcov instrumentation with concurrent `gh timed out after 60s`
noise in the same run; the test passes locally (2.4s) and in all three
unittest lanes. Rerun of the job passed (`Shell coverage: pass, 6m20s`,
job 93189519262) — one-off infrastructure flake, not a regression.
