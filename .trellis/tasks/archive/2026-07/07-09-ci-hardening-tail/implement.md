# CI Hardening Tail Implementation Plan

## Execution Order

1. Resolve current action SHAs and replace tag pins with SHA pins plus version
   comments.
2. Add dependabot configuration for `pip` and `github-actions`.
3. Fix the ignored-path required-context deadlock.
4. Add mypy dependency/config and a CI + Makefile lane over `installer/`.
5. Record and apply the ruff scope decision for vendored hook Python.

## Validation Plan

Run `zizmor --offline .github/workflows/`, ruff, mypy, and the generated parity
tests. Use GitHub's workflow view or a test PR to reason through ignored-only
PR behavior.

## Documentation And Spec Updates

Document action pinning maintenance and ruff scope if not obvious from comments
in the workflow.

## Review Notes

Reviewers should verify official action SHAs map to the intended versions and
that dependabot can update them.

## Follow-Ups

If mypy generates broad type cleanup, split that cleanup rather than burying it
inside CI hardening.
