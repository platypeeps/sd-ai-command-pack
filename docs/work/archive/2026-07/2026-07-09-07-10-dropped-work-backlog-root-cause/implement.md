# Dropped Claude Work-Backlog Install Root Cause Implementation Plan

1. Add a focused two-version fixture: install with the Claude work-backlog
   manifest entry removed, retain the old receipt, remove all active Trellis
   Claude markers while keeping the `.claude/` anchor, then refresh with the
   current manifest.
2. Assert the refresh reports `active Trellis claude install not detected`,
   preserves old Claude receipt entries, and omits the newly introduced target
   from disk, receipt, and provenance.
3. Assert the current ordinary audit catches the missing target through
   receipt-inferred manifest completeness, while `--expected-platform claude`
   catches it without relying on receipt inference.
4. Keep production installer selection unchanged. The historical run reported
   the skip correctly; fleet preflight now prevents recurrence by supplying
   explicit install and audit platform sets.
5. Update task acceptance evidence and run focused tests, `make test`, and the
   pack full-check with Prism/Gito disabled.
