# Scanner-manifest reconciliation at subpath granularity

## Problem

Audit finding A-009 (P2·M, architecture), 2026-07-15 @ f6f3932: platform
path layout is re-encoded in 5+ places — `installer/registry.py:27`
(dev-side authority), shipped scanners `install-audit.py:31` + `:173`,
`pr-body-scope.py:97`, `review-scope.sh:80`, plus `manifest.json`'s 384
targets. The only reconciliation guard
(tests/test_install_core.py:1331-1341) checks directory-prefix coverage
only, so refactoring a platform's command subpath silently desyncs the
shipped scanners in every consumer repo.

Related parked tasks: 07-09-upstream-platform-state (root cause: no
machine-readable upstream platform state) and
07-09-platform-registry-manifest-sections; this task is the pack-local
mitigation and does not depend on either trigger.

## Goal

A platform-path refactor that desyncs any shipped scanner fails a pack test
at subpath granularity before it can ship.

## Requirements

- Strengthen the reconciliation test: every non-shared `manifest.json`
  target must be matched (fnmatch) by at least one pattern in each relevant
  shipped scanner table; report unmatched targets by name.
- Evaluate deriving scanner tables from the manifest at build time as the
  stronger alternative; document the choice in the task design notes.
- No consumer-visible behavior change.

## Acceptance Criteria

- [ ] Mutating a manifest command target subpath breaks the new test with
      an actionable message.
- [ ] All current targets pass; no scanner behavior change.
