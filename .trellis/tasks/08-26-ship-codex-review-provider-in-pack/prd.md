# Ship codex-review-provider inside the pack so the codex review lane works fleet-wide

## Goal

The codex local review lane (.sd-ai-command-pack/review.json provider id codex, argv adapter) invokes codex-review-provider, a wrapper that currently lives only in ~/bin/common on the author's machine. The codex lane itself flagged this on its first run: a clean checkout on another machine classifies the provider as unavailable. Ship the wrapper inside the pack (scripts/sd-ai-command-pack-codex-review-provider.py with a manifest entry and installed target) and point the argv at the installed path, so every fleet consumer gets the subscription-billed codex lane without per-machine setup. Also decide whether the wrapper should honor the repo's gito exclude_files / prism rules so the three lanes review the same scope.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
