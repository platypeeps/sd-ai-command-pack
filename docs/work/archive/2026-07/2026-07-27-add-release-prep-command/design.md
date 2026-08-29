# Canonical release-prep design

## Boundary

Release preparation is repository-maintainer workflow, not consumer behavior.
Expose it as `make release-prep`, backed by a source-only Python orchestrator
under `.github/scripts/`. Do not register or install a new `/sd` command and do
not change the shipped manifest merely to expose maintainer automation.

## Ordered workflow

The orchestrator runs every command from the repository root with the Python
interpreter that launched it:

1. Regenerate command adapters, the command catalog, and `manifest.json` with
   `.github/scripts/generate-command-surfaces.py`.
2. Self-install the exact generated payload with `install.py . --force`.
3. Refresh the generated Trellis knowledge base with
   `scripts/sd-ai-command-pack-update-spec-kb.py`.
4. Run `scripts/sd-ai-command-pack-surface-check.py --json` and validate both
   structural closure and cheap release prerequisites.
5. If and only if the report contains the single expected stale candidate
   ledger finding, run the full-fleet candidate validator once. A clean report
   skips this expensive step.
6. Require strict surface closure after any ledger refresh.
7. Return to the Make target, which invokes `$(MAKE) check` as the final
   repository release-readiness gate. Keeping the recursive Make call in the
   recipe preserves Make's jobserver and fail-fast semantics.

Every Python-owned subprocess is an argv array with `shell=False`, bounded
output capture where parsing is required, and fail-fast behavior. Normal
command output is shown so long-running fleet progress remains visible.

## Pre-candidate gate

The existing surface checker remains strict and unchanged. The orchestrator
consumes its versioned JSON report and permits exactly two states:

- `clean`, with zero findings; or
- `failed`, with one finding whose code is
  `provenance.candidate-stale`, path is
  `docs/fleet/candidate-validation.json`, and relation is
  `requires-release-evidence`.

Invalid reports, truncated findings, inconsistent counts, or additional
findings stop before candidate validation.

The report's resolved `baseRef` and `changedPaths` drive the cheap release
identity check using the same shipped-payload boundary as the existing release
gate: `templates/**`, `docs/SD_AI_COMMAND_PACK.md`, and `manifest.json`. A
payload change requires a resolvable base manifest, a different non-empty
current version, and a top changelog heading matching
`## <version> - YYYY-MM-DD`. This prevents a candidate run against an
unversioned payload that would become stale as soon as the version is fixed.

## Failure behavior

- Generation, install, KB refresh, preflight, candidate validation, strict
  closure, and `make check` are hard gates in order.
- Candidate failures retain the validator's existing behavior: no failing or
  partial result replaces the canonical ledger.
- A clean ledger is reused rather than refreshed, avoiding unnecessary fleet
  clones.
- The orchestrator never commits, tags, pushes, merges, or mutates consumer
  worktrees.

## Alternatives rejected

- A distributed `/sd-release-prep` command would expose source-maintainer
  behavior to consumers and force an unnecessary payload/version change.
- A Make-only recipe cannot safely parse and constrain the structured closure
  report without brittle shell logic.
- Weakening the normal surface checker with a global ignore would let other
  callers accept stale release evidence.
- Always rerunning the candidate validator would waste fleet work when the
  exact ledger is already valid.
