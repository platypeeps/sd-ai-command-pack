# Fleet rollout timing telemetry design

## Boundary

Timing is a source-owned observability sidecar for `sd-fleet-refresh`. It never
decides whether a gate passed, changes consumer state, sends data to a hosted
service, or turns a timing failure into rollout success. The fleet workflow
records stage boundaries around its existing authoritative operations and
reports telemetry anomalies separately from delivery outcomes.

The record lives in the user's local state directory, keyed by a digest of the
source checkout and a safe run ID. It does not dirty the source repository and
never stores an absolute repository path, credentials, command output, review
bodies, or arbitrary environment values.

## Command and state contract

Add `scripts/sd-ai-command-pack-fleet-timing.py` as a source-only command with
these operations:

- `init --run-id ID --target-version VERSION --consumer NAME:PRIORITY ...`
  creates a run or resumes it only when target and ordered consumer identity
  match exactly;
- `stage-start --run-id ID (--fleet | --consumer NAME) --stage STAGE` opens an
  attempt or returns the already-active attempt unchanged;
- `stage-end ... --outcome passed|failed|skipped|interrupted [--reason TEXT]`
  closes the active attempt, or idempotently confirms the last identical end;
- `consumer-end --run-id ID --consumer NAME --outcome OUTCOME [--reason TEXT]`
  records one consumer outcome after its active attempts close; and
- `report --run-id ID [--complete]` renders the current record and summary.
  Completion is allowed only with no active attempts and an outcome for every
  consumer.

All operations accept internal `--repo` and `--state-home` controls. The fleet
skill supplies only `--repo`; `--state-home` exists for deterministic testing
and recovery, not as a public fleet argument or environment tuning surface.

Schema version 1 contains safe run/repository identity, target version,
wall-clock creation/update/completion nanoseconds, fleet stages, and consumers
sorted by rollout priority. Each stage owns sequential attempts with wall and
monotonic start evidence, optional wall end, exact monotonic elapsed
nanoseconds, outcome, and bounded reason. State writes are private, locked,
size-bounded, validated, and atomically replaced.

## Stage and outcome model

The fixed stage vocabulary is:

`preflight`, `checkout-validation`, `install`, `audit`, `local-gate`,
`commit-push`, `pr-creation`, `reviewer-wait`, `ci-wait`, `housekeeping`, and
`post-merge-audit`.

`preflight` is fleet-scoped; the remaining stages are consumer-scoped where
applicable. Reviewer and CI attempts are independent and may overlap. A retry
is another attempt for the same stage after the prior attempt closes. Consumer
retry count is derived from attempts beyond the first rather than maintained
as a second source of truth.

Consumer outcomes are `at-target`, `refreshed-merged`, `pr-open`, `skipped`,
`failed`, or `blocked`. Failure-like stage and consumer outcomes require a
reason; success-like outcomes do not accept one. Skipped stages retain their
reason and zero or positive measured elapsed time rather than disappearing.

## Timing and summary math

Wall-clock nanoseconds preserve auditable UTC boundaries. Elapsed stage time
comes only from monotonic nanoseconds and rejects a backwards monotonic clock.
The summary calculates:

- every stage attempt duration and per-stage aggregate;
- per-consumer earliest-start to latest-end critical-path duration;
- interval-union active wall time so concurrent work is not double-counted;
- reviewer/CI overlap as the intersection of their wall interval unions;
- derived retry counts, slowest consumer, and slowest stage; and
- aggregate fleet critical path across fleet and consumer intervals.

Active partial runs use the current injected clock for a provisional summary.
Completed records freeze all intervals before setting `completedAtWallNs`.
Human output is derived from the same JSON summary and remains manifest ordered.

## Resume and concurrency

Every mutating operation validates the complete stored record before and after
the change. Repeating `init`, an active `stage-start`, an identical `stage-end`,
or an identical `consumer-end` is a no-op with `changed: false`. A new attempt
is created only by `stage-start` after the prior attempt closed.

An exclusive, short-lived operation lock prevents concurrent post-canary
workers from losing updates. A live lock waits only for a bounded interval; a
dead stale lock is recovered only after its owner process is absent. Atomic
replace means an interruption leaves either the prior valid record or the next
valid record, never a partially written JSON file.

## Privacy and failure behavior

IDs, versions, stage names, outcomes, and reasons are strict strings with
bounded lengths. Reasons reject control characters, personal absolute POSIX,
home-relative, Windows drive, and UNC paths plus common credential or private-
key forms. Unknown fields and malformed types fail closed. The record stores a
repository digest, never the repository path or remote URL.

Telemetry command failure is visible in the fleet report and pauses telemetry
mutation for correction, but it does not overwrite or reinterpret the delivery
gate result. Operators resume from the last valid record after correcting the
telemetry input or state.

## Fleet orchestration

`sd-fleet-refresh` initializes one timing run before preflight, brackets every
applicable stage, and records consumer outcomes. Reviewer and CI waits start
and end independently even when they overlap. It emits a partial report on an
interruption and a completed report after all selected consumers settle.

The mandatory final report adds aggregate critical path, slowest consumer,
slowest stage, reviewer/CI overlap, retry count, and telemetry anomalies. It
does not include the local state path. The rollout guide explains how to
compare this sequential baseline with integration-only review and later wave
rollouts.

## Safety and compatibility

- The helper remains outside `manifest.json` and is allowlisted only in the
  source-checkout install audit.
- No public fleet adapter gains timing controls; timing is mandatory internal
  observability for non-dry runs.
- `dry-run` records preflight only and completes without consumer stages.
- Existing release, finding-severity, review, CI, and housekeeping gates remain
  authoritative and unchanged.
- Fake-clock tests exercise all math without sleeping or depending on system
  time.

## Rejected alternatives

- Parse GitHub and journal timestamps after the run: this cannot distinguish
  overlapping waits or retain partial attempts reliably.
- Store telemetry in the repository: an untracked state file would dirty the
  checkout and interfere with release identity and housekeeping.
- Sum stage durations: concurrent reviewer and CI waits would exaggerate the
  critical path.
- Accept arbitrary free-form payloads: paths, credentials, and schema drift
  would enter durable local records.
