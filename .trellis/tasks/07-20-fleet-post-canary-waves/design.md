# Controlled post-canary fleet waves — design

## 1. Scope / Trigger

The fleet refresh contract is currently sequential prose. This task introduces
bounded post-canary overlap without changing any consumer delivery gate. The
change crosses versioned fleet configuration, shared manifest parsing, a
source-only scheduling CLI, the canonical `sd-fleet-refresh` skill, the fleet
runbook, generated mirrors, tests, and release metadata.

The scheduler decides only which independent consumer may start next and which
settled consumer is next in manifest order for merge consideration. It never
installs, reviews, merges, classifies findings, or edits a consumer checkout.

## 2. Signatures

### Fleet manifest schema 4

```json
{
  "schemaVersion": 4,
  "rolloutPolicy": {
    "defaultConcurrency": 2,
    "cohorts": [
      {
        "name": "canary",
        "strategy": "sequential",
        "consumers": ["rwbp-coordinator", "loadsmith", "hoa-manager"]
      },
      {
        "name": "post-canary",
        "strategy": "bounded-parallel",
        "maxConcurrency": 2,
        "consumers": ["rwbp-website", "mezmo_benchmark", "se-ai-command-pack"]
      },
      {
        "name": "final",
        "strategy": "sequential",
        "consumers": ["anomaly-metric-creator"]
      }
    ]
  },
  "consumers": []
}
```

### Shared parser

```python
parse_fleet_rollout_policy(
    manifest: Mapping[str, Any],
    consumers: Sequence[FleetConsumer],
    label: str = "fleet manifest",
) -> FleetRolloutPolicy

load_fleet_rollout_policy(path: Path) -> FleetRolloutPolicy
```

### Scheduling CLI

```text
sd-ai-command-pack-fleet-wave-plan.py
  --fleet <manifest.json>
  --state <safe-state.json>
  [--json]
```

The CLI is source-only. It reads a schema-version-1 observation snapshot and
prints one deterministic plan. No public platform adapter exposes it.

## 3. Contracts

### Configuration

- `defaultConcurrency` is an integer from 1 through 4.
- Cohort names are unique safe identifiers.
- The first cohort is named `canary` and uses `sequential`.
- `sequential` cohorts have effective concurrency 1 and cannot set a different
  `maxConcurrency`.
- `bounded-parallel` cohorts require `maxConcurrency` between 2 and
  `defaultConcurrency`.
- Every manifest consumer appears in exactly one cohort.
- Cohort consumer order concatenates to the canonical
  `(rolloutPriority, name)` order. Configuration can group consumers but cannot
  silently reorder them.
- A one-consumer final cohort encodes the existing AMC-last policy rather than
  hard-coding that repository in orchestration prose or Python.

### Scheduler input

```json
{
  "schemaVersion": 1,
  "consumers": [
    {"name": "rwbp-coordinator", "state": "at-target", "packBlocker": false}
  ]
}
```

Accepted states are `pending`, `in-flight`, `ready`, `at-target`, `merged`,
`pr-open`, `skipped`, `failed`, and `blocked`. Every configured consumer must
appear exactly once. `packBlocker` is a boolean.

### Scheduler output

```json
{
  "schemaVersion": 1,
  "cohort": "post-canary",
  "strategy": "bounded-parallel",
  "maxConcurrency": 2,
  "canStart": ["rwbp-website"],
  "mergeCandidate": null,
  "stopStarting": false,
  "holdMerges": false,
  "complete": false,
  "reason": null
}
```

- Canaries start one at a time. Later cohorts remain locked until every canary
  is `at-target` or `merged`; `pr-open`, `skipped`, `failed`, or `blocked`
  cannot prove canary health.
- A later cohort begins only after the preceding cohort has terminal outcomes.
  Consumer-owned `skipped` or `failed` outcomes remain reportable and do not
  become pack blockers by inference.
- `canStart` contains the earliest pending consumers that fit the cohort's
  remaining concurrency slots.
- `mergeCandidate` is at most one consumer: the first non-terminal consumer in
  canonical manifest order, and only when its state is `ready`. A later ready
  PR waits behind an earlier unsettled consumer.
- Any `packBlocker: true` sets both `stopStarting` and `holdMerges`, returns no
  starts or merge candidate, and identifies the blocker state without echoing
  review bodies, paths, credentials, or command output.
- `at-target`, `merged`, and `pr-open` consumers are never restarted. This is
  the idempotent resume boundary; live GitHub/preflight evidence remains the
  authority for assigning those observations.

### Orchestration ownership

- The main fleet controller owns scheduling, timing, finding classification,
  deterministic merge order, final reporting, and interruption state.
- At most the scheduler-provided consumer set may run concurrently.
- Each consumer worker owns one existing checkout, one branch, and one PR until
  it reports a settled observation. No two workers may share a repository.
- Workers may overlap checkout validation, installation, audit, local gate,
  commit/push, PR creation, review wait, and CI wait.
- The controller serializes merge decisions through the scheduler and invokes
  each consumer's existing housekeeping gate exactly once.
- A blocker signal interrupts new dispatch immediately. Already running
  workers may finish read-only validation but may not merge until the finding
  severity gate clears the hold.

## 4. Validation & Error Matrix

- Manifest schema other than 4 -> controlled fleet configuration error.
- Missing/empty policy or cohorts -> controlled configuration error.
- Missing, repeated, unknown, or reordered cohort consumer -> reject.
- Invalid strategy/concurrency combination -> reject.
- State schema other than 1, duplicate/unknown/missing consumer, invalid state,
  or non-boolean blocker -> exit 2 with a bounded diagnostic.
- Active consumers exceeding configured concurrency -> invalid-pause; never
  start another consumer.
- Canary non-success terminal outcome -> no starts/merges and a controlled
  canary-health reason.
- Pack blocker in any cohort -> no starts/merges, even if another PR is ready.
- Scheduler import, manifest, state-file, or serialization failure -> exit 2
  without traceback or mutation.

## 5. Good / Base / Bad Cases

- Good: three canaries complete sequentially; two post-canary consumers start;
  a third starts after one slot frees; ready PRs merge in manifest order; the
  solo final cohort starts last.
- Base: resumed state reports canaries at target, one post-canary PR merged,
  one in flight, and one pending; only the remaining pending consumer is
  eligible when capacity exists.
- Bad: a later PR becomes ready first and is merged out of order, or a blocker
  is treated as a worker-local condition while another consumer starts.

## 6. Tests Required

- Manifest parser: valid policy, schema mismatch, empty cohorts, concurrency
  bounds, duplicate/unknown/missing consumers, order drift, and strategy rules.
- Scheduler unit tests: sequential canary, canary failure, bounded start slots,
  manifest-ordered merge hold, partial non-blocking failure, pack-blocker stop,
  all-terminal completion, and resume without duplicate starts.
- CLI tests: JSON and human output, malformed state, missing files, controlled
  exit codes, no traceback, and no absolute-path echo.
- Skill/runbook tests: controller/worker ownership, bounded wave dispatch,
  merge serialization, blocker interruption, timing integration, resume, and
  final manifest-ordered report.
- Generated parity, source-only coverage, `make check`, and canonical
  full-fleet candidate validation for the release payload.

## 7. Wrong vs Correct

Wrong: spawn one worker per stale consumer and let whichever CI finishes first
merge first.

Correct: ask the scheduler for at most the configured starts, keep each worker
checkout isolated, and merge only the returned manifest-order candidate through
that consumer's housekeeping gate.

Wrong: infer that a consumer test failure is pack-owned and freeze the wave, or
infer it is consumer-owned and continue.

Correct: preserve the observed failure, run the existing finding severity gate,
and set `packBlocker` only from its verified blocker disposition.

