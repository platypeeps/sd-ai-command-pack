# Repository Copilot Instructions

This repository is the sd-ai-command-pack source. There are no generated
mirrors in it: step 3e deleted the per-platform copies and the generator that
produced them, so every file here is authored. `skills/sd-*/SKILL.md` is the
payload and `bin/` is the tooling; `bin/sd_install.py --user` renders the former
onto a machine at install time. Review each file once — there is no second copy
of anything to also comment on.

## There is no vendored payload here any more

Until 2026-08-31 this file carried a long list of copied-in framework and pack
payload families to be treated as vendored and reviewed lightly. Every path in
that list is gone: the predecessor's state directory went at step 2, the per-platform skill and
command trees at step 3a, and the Copilot-facing render — `.github/skills/`,
`.github/agents/`, `.github/copilot/`, `.github/hooks/` —
at step 5b. Nothing in this repository is a copy of anything.

The practical consequence: **there is no file here you should decline to review
on ownership grounds.** The handoff-comment protocol for upstream framework fixes
is retired with the payload it protected, and so is the pack-refresh carve-out —
there is no release train and no version to refresh to.

## Nothing is installed into a consuming repository

Step 3e replaced the fleet installer with a machine-scope renderer, so there is
no manifest, no installed-targets receipt, no provenance file, and no install
audit to consult. A pack file being absent from a repository is the expected
state, not a defect: the only thing this framework puts in a repository is what
somebody deliberately wrote under `docs/work/`.

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
