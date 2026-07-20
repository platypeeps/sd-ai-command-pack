# Fleet Rollout

This repository tracks the known sd-ai-command-pack consumer fleet in
`docs/fleet/consumers.json`. The manifest is operator-triggered inventory, not
an unattended rollout system.

The manifest owns rollout order explicitly. The current fast-first order is
rwbp-coordinator, loadsmith, hoa-manager, rwbp-website, mezmo_benchmark,
se-ai-command-pack, then anomaly-metric-creator. The first three are the canary
group; AMC remains last because its CI feedback loop is materially slower.

Use the read-only fleet status report before or after rollout activity:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet
```

The same command can run from an installed consumer after the machine profile
has been created once with `install.py TARGET --configure-fleet`. That profile
only locates this checked-in manifest and applies local checkout path overrides;
it does not replace the versioned fleet policy in this repository.

It preserves the manifest's rollout order and reports checkout availability,
working-tree/upstream state, installed versus target pack versions, GitHub
inventory, Trellis work, and numbered next steps. It does not fetch or modify
consumers, so ref-derived values are labelled `cached`; add `--no-network` for
a local-only snapshot or `--json` for schema-versioned automation output.

## Release Candidate Validation

Before merging/tagging a version that changes shipped payload, validate the
working candidate against disposable clones of every consumer origin:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py
```

The validator does not write to active consumer worktrees. It discovers each
checkout's `origin`, clones the default branch under a temporary directory,
installs the working pack candidate, runs the install audit, and runs the
repo-owned `candidatePrepare` phase followed by the lightweight, read-only
`candidateChecks` declared in the fleet manifest. It continues after failures
so the report covers the whole fleet, then cleans the temporary clones.

Preparation and checks run in declaration order in the same disposable
checkout. Preparation is the only repo-owned phase allowed to mutate generated
artifacts. Every consumer declares `candidatePrepare` explicitly; use an empty
array when the repository owns no preparation step. When a repo owns a tracked
structural map, declare its deterministic refresh command in
`candidatePrepare`, then keep the corresponding preflight in `candidateChecks`
read-only. This keeps candidate validation representative of the real rollout
without weakening or hiding mutation inside the consumer gate.

The current six map-owning consumers run `bash scripts/update_repomix` during
preparation. `se-ai-command-pack` explicitly declares no preparation because
it owns neither that generator nor `docs/repomix-map.md`.
The validator supplies disposable npm, uv, and Python bytecode cache paths to
these commands so local cache permissions cannot make a candidate fail.

A full all-pass run atomically updates
`docs/fleet/candidate-validation.json`. That ledger is bound to the pack
version, installable payload, fleet manifest, declared preparation and checks,
and consumer base commits. Release PR/full-check validation and automatic
tagging reject a missing, stale, partial, or failing ledger. Verify it without
running consumer commands:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger
```

Use `--consumer <name>` for a diagnostic rerun. Partial runs never replace the
canonical full-fleet ledger.

## Preflight

Run the source-owned preflight before opening consumer refresh PRs:

```bash
python3 scripts/sd-ai-command-pack-fleet-preflight.py
```

The target version is read from `manifest.json`. Repos already at that version
are reported as `at-target` and should be skipped, which prevents duplicate
empty refresh PRs.

JSON preflight output includes both `candidatePrepare` and `candidateChecks`,
so orchestration can inspect the complete candidate contract without parsing
the source manifest independently.

For each repo that needs a refresh, the preflight prints the exact install and
audit commands. The audit command passes the fleet manifest's explicit platform
set through `--expected-platform` so missing selected-platform files are caught
even when a faulty install also omitted them from receipts or provenance.

## Refresh Shape

For each `refresh-needed` repo:

1. Create a PR-only branch in that consumer repo.
2. Run the printed `python3 install.py <repo> --force --platform ...` command
   from this pack checkout.
3. Run the printed `python3 scripts/sd-ai-command-pack-install-audit.py --repo
   <repo> --expected-platform ...` command.
4. Commit, push, review, merge, and run housekeeping in the consumer repo.
5. Confirm post-merge provenance reads the target version and the audit passes.

Process consumers in manifest priority order. Do not move to AMC first merely
because it appears in an operator's local list; the fast canaries are intended
to expose cross-repo issues before the longest CI cycle begins.

## Interruption Policy

Stop a rollout for a correctness, security, installation/audit, or
compatibility defect in the released pack. Fix it before tagging when candidate
validation catches it; if it escaped into a tag, use a patch release.

Do not interrupt a healthy rollout for low-risk hardening, style, or an
unrelated consumer finding. Address a small consumer-owned migration in that
consumer PR when appropriate, or record a Trellis follow-up for the next pack
release. This keeps useful review feedback without turning every observation
into another fleet-wide patch cycle.

## Corrective Campaign

When a consumer surfaces a verified pack-owned blocker, pause consumer mutation
before selecting or preparing another release. Retain the original fleet task
so it can resume after the correction; reuse or create one source-owned Trellis
corrective task instead of creating a replacement fleet task for every finding.

Record the campaign findings in the corrective task with this ledger shape:

```text
ID | Contract family | Evidence | Severity | Disposition | Fix | Regression
```

Every verified blocker owns one row. Exact duplicates reuse the owning row.
Before selecting the corrective version, run a bounded contract-surface sweep
around the failure. Cover equivalent producers and consumers, mutation paths,
persisted and dynamically loaded data, normalization and nullability, CLI
exposure, human and JSON output, failure behavior, and generated or template
mirrors where they apply. Record excluded adjacent surfaces so the sweep cannot
expand without a reason.

Iterate with focused source tests and, when useful, partial candidate
diagnostics:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py --consumer <name>
```

Partial runs remain diagnostic and must never replace the canonical candidate
ledger. After the finding ledger and regressions converge, freeze the payload,
select one corrective version, update the release surfaces once, and run one
canonical full-fleet candidate validation with the no-filter command. Only the
no-filter canonical command may update `docs/fleet/candidate-validation.json`.

Merge and tag the corrective release through the source lifecycle, then resume
the original fleet task from a fresh preflight. If an urgent independent
security defect would become riskier while waiting for the bounded sweep, it
may ship immediately with that reason recorded; keep the remaining campaign
open rather than silently discarding it.

## Review Ownership

Pack-owned implementation is reviewed in the sd-ai-command-pack source PR.
Consumer refresh PRs review the installed result: selected-platform wiring,
receipt and provenance integrity, secrets, documentation accuracy, and any
repo-owned migration or integration change. Do not repeat line-level review of
unchanged vendored pack implementation in every consumer.

Do not include stale aliases such as `green-button-manager` or historical
predecessors such as `trellis-review-pr-pack`; they are explicitly excluded in
the fleet manifest.
