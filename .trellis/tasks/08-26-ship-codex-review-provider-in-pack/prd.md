# Ship codex-review-provider inside the pack so the codex review lane works fleet-wide

## Goal

The codex local review lane (.sd-ai-command-pack/review.json provider id codex, argv adapter) invokes codex-review-provider, a wrapper that currently lives only in ~/bin/common on the author's machine. The codex lane itself flagged this on its first run: a clean checkout on another machine classifies the provider as unavailable. Ship the wrapper inside the pack (a new pack-prefixed script under scripts/ with a manifest entry and installed target) and point the argv at the installed path, so every fleet consumer gets the subscription-billed codex lane without per-machine setup. Also decide whether the wrapper should honor the repo's gito exclude_files / prism rules so the three lanes review the same scope.

## Requirements

- The wrapper ships as a pack-prefixed script under `scripts/` with a manifest entry and an installed target, so a consumer install places it on every fleet checkout.
- The `codex` provider argv in the shipped `review.json` template points at the installed path, not at `~/bin/common`.
- When `codex` is not installed or not logged in, the wrapper exits 3 (`unavailable`) with a reason, so the coordinator degrades to the remaining lanes instead of failing the run.
- The wrapper honors the repository's gito `exclude_files` so the codex lane reviews the same scope as gito; a decision on prism rules is recorded in `design.md`.

## Acceptance Criteria

- [ ] A fresh consumer install lists the wrapper in `installed-targets.txt` and `sd-ai-command-pack-review-local.py --scope changes --local codex` produces a receipt on that checkout.
- [ ] With `codex` absent from PATH, the same command records the provider as `unavailable` and the run still completes on the other lanes.
- [ ] A diff touching only paths in gito's `exclude_files` yields `status: clean` from the codex lane with no model call.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
