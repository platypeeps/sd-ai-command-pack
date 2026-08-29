# CI Hardening Tail Design

## Overview

The workflow is already reasonably hardened, but this task should close the
remaining supply-chain, mergeability, typing, dependency-update, and lint-scope
gaps without duplicating shell/hook work.

## Proposal

SHA-pin all GitHub Actions while retaining version comments, then add
dependabot coverage for both `pip` and `github-actions` so pinned SHAs are
maintainable. Resolve the `paths-ignore`/required-context deadlock by ensuring
`CI Result` still reports for ignored-only PRs, either by removing the ignore
for PRs or adding a tiny always-run aggregate-compatible workflow.

Add a pragmatic mypy lane over `installer/` first. Keep strictness modest and
baseline only if needed; the goal is type-signal, not a large rewrite. Wire the
lane into both CI and `make check`.

Finally document the ruff scope decision for vendored hook Python. The current
security workflow comments already exclude Trellis-vendored hooks; make the
lint scope match the intended policy.

## Boundaries And Non-Goals

Do not add actionlint here. Do not add Python 3.11/3.12 lanes; that belongs to
the review-nits matrix decision.

## Affected Files

- `.github/workflows/tests.yml`
- a new Dependabot configuration file under the GitHub configuration directory
- `Makefile`
- `requirements-dev.txt` if mypy is added
- `pyproject.toml` for mypy config if needed
- `README.md` or `CONTRIBUTING.md` for lint-scope rationale

## Risks And Edge Cases

SHA pinning can make workflow updates tedious unless dependabot is configured
correctly. The ignored-path fix must preserve the intentional chore lane while
keeping fork PRs mergeable.

## Validation

Run workflow security checks, generated parity tests if workflow text is
pinned, and local `make check` after adding mypy.
