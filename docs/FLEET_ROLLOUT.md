# Fleet Rollout

This repository tracks the known sd-ai-command-pack consumer fleet in
`docs/fleet/consumers.json`. The manifest is operator-triggered inventory, not
an unattended rollout system.

The manifest owns rollout order explicitly. The current fast-first order is
rwbp-coordinator, loadsmith, hoa-manager, rwbp-website, mezmo_benchmark, then
anomaly-metric-creator. The first three are the canary group; AMC remains last
because its CI feedback loop is materially slower.

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
repo-owned lightweight `candidateChecks` declared in the fleet manifest. It
continues after failures so the report covers the whole fleet, then cleans the
temporary clones.

Candidate checks run in declaration order in the same disposable checkout.
When a repo-owned gate validates generated metadata derived from installed file
structure, declare that repository's deterministic refresh command immediately
before the validating check. This keeps candidate validation representative of
the real rollout without weakening the consumer gate.
The validator supplies disposable npm, uv, and Python bytecode cache paths to
these commands so local cache permissions cannot make a candidate fail.

A full all-pass run atomically updates
`docs/fleet/candidate-validation.json`. That ledger is bound to the pack
version, installable payload, fleet manifest, declared checks, and consumer
base commits. Release PR/full-check validation and automatic tagging reject a
missing, stale, partial, or failing ledger. Verify it without running consumer
commands:

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

## Review Ownership

Pack-owned implementation is reviewed in the sd-ai-command-pack source PR.
Consumer refresh PRs review the installed result: selected-platform wiring,
receipt and provenance integrity, secrets, documentation accuracy, and any
repo-owned migration or integration change. Do not repeat line-level review of
unchanged vendored pack implementation in every consumer.

Do not include stale aliases such as `green-button-manager` or historical
predecessors such as `trellis-review-pr-pack`; they are explicitly excluded in
the fleet manifest.
