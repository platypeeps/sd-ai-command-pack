# Decide the zizmor adhoc-packages disposition before the pin moves

## Goal

Settle, deliberately, what this repository does about zizmor's
`adhoc-packages` finding, before a dependabot bump turns it into a red
`security` job that someone silences under time pressure.

## Context

`requirements-security.txt` pins `zizmor==1.16.3`, installed in CI under
`--require-hashes`. zizmor's `adhoc-packages` audit was introduced in 1.26.0,
so the pinned scanner cannot see it. A local 1.29.0 does:

```
help[adhoc-packages]: ad-hoc installation of packages
   --> .github/workflows/tests.yml:601:14
    |
601 |         run: npm install -g @anthropic-ai/claude-code@2.1.220
    |         ---  ^^^ installs a package outside of a lockfile
    = note: audit confidence -> High
9 findings (8 suppressed): 0 informational, 1 low, 0 medium, 0 high
```

Exit 12. `make audit` does not pass `--no-exit-codes`, and its recipe lines
are not `-`-prefixed, so that finding fails the target. `.github/dependabot.yml`
covers `pip` at `/` monthly, so the pin will cross 1.26.0 on its own schedule
and take the CI `security` job with it.

The step it flags is already deliberate: the CLI is version-pinned at
`@2.1.220` and carries a three-line rationale comment explaining why. zizmor's
objection is not the missing version pin but the missing *lockfile*.

## Requirements

- Pick one disposition and record why, rather than defaulting into whichever
  is easiest at the moment CI turns red:
  1. **Suppress it.** Note that this repository has no suppression mechanism
     today — there is no `zizmor.yml` at any of the paths zizmor reads, and
     zero `# zizmor: ignore[...]` comments anywhere in the tree. Choosing this
     *introduces* the mechanism, and every later suppression will cite it as
     precedent. That is an argument for making the first one exemplary: narrow,
     commented, and tied to this one step.
  2. **Remove the cause.** Install the CLI from a lockfile so the finding does
     not apply. This is the only option that improves supply-chain posture
     rather than recording a decision not to.
  3. **Accept the noise.** Let the audit report it and stop treating a `low`
     as fatal. This weakens the gate for every future finding, not just this
     one, and is the option to argue hardest against.
- Whichever is chosen, do it *before* the pin moves. A decision made while CI
  is green is a decision; the same decision made while CI is red is a
  workaround.
- Bump the pin in the same change, so the repository is actually running the
  scanner version whose behavior was reasoned about.

## Acceptance Criteria

- [ ] `requirements-security.txt` pins a zizmor at or past 1.26.0, hash-pinned, and CI installs it.
- [ ] `make audit` and the CI `security` job both pass at that version.
- [ ] The disposition is recorded where the next reader will find it — beside the workflow step if suppressed, in the config if configured — and says why, not just what.
- [ ] If a suppression mechanism was introduced, it is scoped to this finding and this step, and does not silence the audit repository-wide.
