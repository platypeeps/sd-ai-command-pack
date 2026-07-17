# Fleet candidate validation and priority design

## Boundaries

Fleet policy remains source-owned under `docs/fleet/`; no candidate helper or
fleet command is installed into consumers. `templates/**` remains the source
of truth for shipped documentation and command payloads.

## Fleet Manifest Contract

Raise `docs/fleet/consumers.json` to schema version 2. Each consumer adds:

- `rolloutPriority`: a unique positive integer. Loaders sort by priority, then
  case-insensitive name as a deterministic tie-breaker.
- `candidateTimeoutSeconds`: a bounded positive integer for each declared
  compatibility command.
- `candidateChecks`: a non-empty list of non-empty string argv arrays.

Argument arrays are executed directly with `shell=False`. This permits Bash,
Node, Python, Swift, or any future repo-local tool without teaching the pack
their syntax or introducing a shell-string boundary.

## Candidate Validation Flow

`scripts/sd-ai-command-pack-fleet-candidate-check.py` loads the same fleet
contract as preflight. For each selected consumer it:

1. Resolves the existing path hint only to discover that checkout's `origin`
   URL; it does not inspect or mutate its worktree state.
2. Clones the origin default branch into a temporary directory.
3. Records the clone's HEAD commit.
4. Runs this checkout's `install.py` against the clone with the declared
   platform set.
5. Runs this checkout's install-audit helper with matching
   `--expected-platform` arguments.
6. Runs every declared compatibility argv with the configured timeout.
7. Captures a concise failure detail and continues to the next consumer.

The process inherits the selected Python/toolchain environment and prepends
that Python executable's directory to `PATH`, avoiding accidental Xcode Python
selection in repo-local checks. Temporary clones are always cleaned by
`TemporaryDirectory`.

A `--consumer` run is diagnostic and never writes the canonical ledger. A
full-fleet run writes it atomically only when every consumer passes.

## Validation Ledger

`docs/fleet/candidate-validation.json` records:

- schema version and validation timestamp;
- pack version;
- SHA-256 digest of the canonical manifest plus every unique installable
  source file named by it;
- SHA-256 digest of the fleet manifest bytes;
- each consumer's name, GitHub slug, origin base commit, declared checks, and
  `passed` status.

`scripts/sd_ai_command_pack_fleet_lib.py` owns manifest parsing, fleet schema,
digest calculation, and ledger validation so preflight, candidate validation,
and tag creation share one contract.

The full-check release drift lane runs the candidate helper in
`--check-ledger` mode whenever the manifest version changes. The automatic tag
creator independently validates the committed ledger and payload at the exact
head commit before constructing a tag plan. A stale ledger therefore blocks
the PR gate and remains blocked after merge rather than silently tagging.

## Rollout And Review Policy

The rollout order is:

1. rwbp-coordinator
2. loadsmith
3. hoa-manager
4. rwbp-website
5. mezmo_benchmark
6. anomaly-metric-creator

The first three are fast canaries. A newly discovered correctness, security,
installation/audit, or compatibility problem blocks rollout and may require a
candidate fix before tagging or a patch if somehow found after tagging.
Low-risk hardening, style, and unrelated consumer findings are recorded for a
later release and do not interrupt a healthy rollout.

Consumer PR review verifies the installed result and consumer-owned changes.
Line-level review of pack-owned implementation belongs in this repository;
consumer reviewers still inspect provenance, selected-platform wiring,
secrets, documentation accuracy, and any repo-local migration.

## Failure And Rollback Shape

- Candidate failures leave no consumer mutation and do not replace a previous
  ledger. The version/payload digest makes any previous ledger stale.
- Missing local path hints, missing origins/tools, timeouts, install failures,
  audit failures, and check failures are explicit per-consumer failures.
- A malformed fleet schema fails before any clone or install begins.
- Rollback consists of reverting the source change and regenerating a ledger
  for the resulting candidate; no consumer rollback is needed before release.

## Alternatives Considered

- Ordering the JSON array manually: rejected because priority remains implicit
  and a harmless reformat can change rollout behavior.
- Running full consumer CI locally: rejected as slow and dependency-heavy; the
  goal is a quick compatibility probe before normal consumer PR CI.
- Writing a ledger after partial runs: rejected because it can make incomplete
  evidence look release-ready.
- Validating only in the tag job: rejected because that discovers missing
  evidence after the release PR has already merged.
