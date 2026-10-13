# Repository Copilot Instructions

This repository is the sd-ai-command-pack source. Every file here is authored:
there are no generated mirrors and no vendored payload. `skills/sd-*/SKILL.md` is
the payload and `bin/` is the tooling; `bin/sd_install.py --user` renders the former
onto a machine at install time. Review each file once.

**There is no file here you should decline to review on ownership grounds.**

## Nothing is installed into a consuming repository

The installer is machine-scope: no manifest, no installed-targets receipt, no
provenance file and no install audit to consult. A pack file absent from a
repository is the expected state, not a defect: the only thing this framework
puts in a repository is what somebody deliberately wrote under `docs/work/`.

## Where to spend review budget

- App behavior, data contracts, data/access/security boundaries, migrations and
  rollback behavior, token or invitation fail-closed behavior, tests,
  operator-facing documentation, and repo-owned scripts.
- Group duplicate root causes into one comment. When deterministic local checks
  already cover a repeated issue class, point at the failing check once instead
  of repeating inline findings; if the check is missing or fragile, ask for one
  focused fixture in the local guard suite.
- Separate current, non-outdated unresolved findings from stale or outdated
  review threads.
- Do not comment on cosmetic issues. A finding is cosmetic when fixing it
  changes no behaviour and no action a reader takes: wording, comments,
  docstrings, naming, formatting, or a drifted count or list in prose. Text
  that is a contract is not cosmetic: a doc or help text that gives a wrong
  command or flag, a string a test or tool parses, a config value, or an
  instruction an agent executes.
