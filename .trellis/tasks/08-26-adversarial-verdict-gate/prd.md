# Adversarial verdict Check Run as the merge gate, replacing human approval

## Goal

Merges across the fleet stall on human approval and on bot review threads even when CI is green: branch protection asks for a reviewer that a solo organization does not have, and Copilot's COMMENTED reviews never count. Replace that with a machine verdict. A workflow runs the pack's exact-scope local review (sd-ai-command-pack-review-local.py, branch_delta on the PR head, gito via the repository's OpenRouter secret) and publishes a Check Run named adversarial-verdict whose conclusion is success when no outstanding high-severity finding remains after dispositions, failure when one does, and neutral when every lane is unavailable. Branch protection then requires CI Result plus adversarial-verdict, drops the approval count to zero and conversation resolution to off, and sd-create-pr enables auto-merge at PR creation so a green PR lands without an operator. Pilot on sd-ai-command-pack, then roll out with a protection-update script that enumerates the fleet.

## Requirements

- A reusable workflow `adversarial-verdict.yml` runs `sd-ai-command-pack-review-local.py --scope pr` on the PR head with the `gito` lane (OpenRouter key from a repository secret; the codex lane is machine-login only and is not offered in CI).
- The workflow publishes one Check Run named `adversarial-verdict` per head SHA. Conclusion: `success` when the receipt has zero outstanding findings at severity `high`; `failure` when any remain; `neutral` when every selected lane is `unavailable`, so a provider outage never reads as clean.
- Local dispositions recorded in the receipt (`rebutted`, `miscited`, `accepted`) are honored, so a finding a session has already argued down does not re-block the merge.
- A protection-update script takes a repository list, requires `CI Result` and `adversarial-verdict`, sets required approvals to 0 and conversation resolution to off, and reports the before/after state per repository without applying when run with `--dry-run`.
- `sd-create-pr` enables GitHub auto-merge (squash) on the PR it creates; a PR whose verdict fails stays open with the failing check as the only blocker.
- Copilot remains advisory: its reviews are never a required check and its threads never gate the merge.

## Acceptance Criteria

- [ ] On sd-ai-command-pack, a PR with a planted high-severity defect gets `adversarial-verdict: failure` and does not auto-merge; after a `rebutted` disposition is committed, the rerun reports `success` and the PR merges with no human click.
- [ ] A PR touching only gito-excluded paths reports `neutral`, and branch protection blocks it rather than treating it as clean.
- [ ] The protection-update script's `--dry-run` output for the fleet lists every repository whose current rules require approvals or conversation resolution, and applying it removes those from one pilot repository only.
- [ ] Deleting the OpenRouter secret makes the check `neutral`, never `success`.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
