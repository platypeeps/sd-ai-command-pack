# Implementation plan: Trellis task metadata integrity preflight

1. Add focused failing fixtures for identity, lifecycle, branch-target, and
   parent/child invariants in `tests/test_review_preflight.py`.
2. Implement bounded changed-task discovery and validation in the template
   preflight source, then synchronize the installed root copy.
3. Reuse existing filesystem and JSON helpers; add small pure validators only
   where they make the error matrix explicit.
4. Preserve the existing scaffold and completed-root checks and verify that
   unchanged historical task records remain non-blocking.
5. Update adapter guidance only if the emitted author-time contract needs a
   durable explanation.
6. Run focused preflight tests, template parity, install audit, and the
   repository full-check.

Do not start this task until the user reviews the planning artifacts.
