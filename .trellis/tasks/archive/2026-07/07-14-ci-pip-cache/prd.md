# Cache pip deps in CI

## Goal

Add cache: pip to the 3 setup-python steps (unittest/lint/security) to stop cold pip installs on every run. Keep pinned SHAs; keep zizmor + parity test green.

## Problem

All four CI jobs (unittest matrix ×3, lint, security) run `python3 -m pip
install -r requirements-*.txt` with no cache, so every run re-downloads and
re-installs the dependency set from scratch — wasted wall-clock on every push.

## Requirements

- R1: Add `cache: pip` to each of the three `actions/setup-python` steps in
  `.github/workflows/tests.yml`, with `cache-dependency-path` pointing at the
  requirements file that lane installs — `requirements-dev.txt` for the unittest
  matrix and lint lanes, `requirements-security.txt` for the security lane.
- R2: Purely additive. Do not change the pinned `actions/setup-python` SHA
  (the parity test asserts the SHA count) and introduce no unpinned `@vN` tag.
- R3: The security lane stays clean — `zizmor` reports no new findings from the
  cache configuration.

## Constraints

- CI tooling only, not shipped payload, so no `manifest.json` version bump.
- `test_generated_parity` (pins the setup-python SHA count and the main-push
  guards), `make audit` (zizmor), and `make full-check` stay green.

## Acceptance Criteria

- [x] `cache: pip` + `cache-dependency-path` on all three setup-python blocks;
      YAML valid.
- [x] Pinned SHAs unchanged; no unpinned action tags; `zizmor` no findings.
- [x] `test_generated_parity` and `make full-check` green; no version bump.

## Non-goals

- SHA-pinning is already done; bumping action versions is left to Dependabot
  (open PRs #98/#99).
