# Fleet candidate preparation design

## Boundaries

`docs/fleet/consumers.json` remains the source of truth for the fleet. The
shared `sd_ai_command_pack_fleet_lib.py` parser owns its schema and produces an
immutable `FleetConsumer`; the candidate validator owns execution in disposable
clones. Consumer preflight scripts remain read-only policy checks.

The manifest schema advances from version 2 to version 3. Every consumer gains
a required `candidatePrepare` list alongside its required non-empty
`candidateChecks` list. Both fields use the same safe direct-argv shape, but
preparation may be empty because not every repository owns generated structural
metadata.

The candidate-ledger schema advances from version 1 to version 2. Each consumer
row records `prepares` and `checks`, and ledger validation compares both against
the parsed fleet contract. The fleet-manifest digest already binds the complete
manifest; recording preparations also keeps evidence human-auditable and
prevents consumers of the ledger from having to reconstruct execution shape.

## Execution Contract

For each consumer, the candidate validator performs:

1. Discover the active checkout's origin and clone its default branch into the
   temporary work root.
2. Install the working pack candidate into that clone.
3. Run the source-owned installation audit.
4. Run each `candidatePrepare` command in declaration order.
5. Run each `candidateChecks` command in declaration order.

Preparation uses the consumer's existing `candidateTimeoutSeconds` and the
same isolated npm, uv, Python-bytecode, and coverage-clean environment as its
checks. Commands are passed directly to `subprocess.run`; no shell parsing is
introduced. The first failed preparation returns a failed consumer result with
the label `candidate preparation N`; no checks run for that consumer. The outer
fleet loop continues unchanged.

Successful detail output reports preparation and check counts. JSON ledger
rows expose exact argv arrays under `prepares` and `checks`.

## Fleet Configuration

The following consumers run their repository-local Repomix refresh during
preparation because their current default branches own both the generator and
tracked artifact:

- `rwbp-coordinator`
- `loadsmith`
- `hoa-manager`
- `rwbp-website`
- `mezmo_benchmark`
- `anomaly-metric-creator`

`se-ai-command-pack` declares `candidatePrepare: []`. Adding a map there would
be a consumer-owned feature, not a prerequisite for consistent orchestration.

HOA's existing update command moves from `candidateChecks` to
`candidatePrepare`; its read-only preflight remains the check. The other
repositories keep their current checks and gain only the explicit preparation
phase.

## Compatibility And Migration

Fleet schema version 3 intentionally rejects old manifests that omit
`candidatePrepare`; this prevents silent reintroduction of the inconsistent
behavior. All in-repo fixtures migrate together.

Ledger schema version 2 intentionally invalidates prior evidence. A complete
candidate run must regenerate `docs/fleet/candidate-validation.json` after the
implementation and fleet manifest stabilize. Partial diagnostics remain unable
to overwrite the ledger.

The pack install manifest version remains unchanged because fleet candidate
orchestration is source-only and no installed payload under `templates/**`,
`docs/SD_AI_COMMAND_PACK.md`, or `manifest.json` changes.

## Operational Considerations

Preparation may download Repomix through a consumer wrapper and may modify the
temporary checkout. Existing disposable cache roots and per-consumer timeouts
bound those effects. The temporary clone is deleted after validation, and the
developer's active checkout is never mutated.

Regenerating maps can surface a changed artifact in the clone; that is expected
and lets the following preflight inspect the prepared state. Candidate
validation does not commit generated output or attempt to prove that the
consumer's default branch already contains the same bytes.

## Rejected Alternatives

- Run `update_repomix` inside every preflight: violates the read-only validator
  boundary and surprises developers by mutating active worktrees.
- Keep refresh commands in `candidateChecks`: obscures which steps mutate state
  and led directly to inconsistent fleet declarations.
- Auto-detect a consumer's Repomix refresh command: makes source-owned release
  behavior depend on checkout contents and silently changes when files appear
  or vanish.
- Add a structural map to SE in this task: expands a fleet-orchestration fix
  into an unrelated consumer feature.
