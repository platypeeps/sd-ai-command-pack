# Taskless fleet refresh finish-work implementation plan

## Contract and state

- [x] Add the blocked campaign, lane, receipt, and corrective task evidence to the source task artifacts.
- [x] Extend controller state validation and reports with bounded corrective recovery evidence while remaining compatible with existing schema-version-1 campaigns.
- [x] Add `resume --recover-consumer <name> --corrective-release <version>` with mutually exclusive argument parsing and strict terminal-pack-blocker preconditions.
- [x] Reset an eligible lane to a new `pr-publication` attempt without changing or replaying historical receipts.

## Fleet workflow

- [x] Require a dedicated active Trellis task during checkout validation for every new refresh lane that lacks one.
- [x] Define the substantive consumer task PRD fields and ownership stop when an unrelated active task or dirty Trellis state is present.
- [x] Document the append-only recovery sequence for an already-published taskless PR, including final-bundle validation before push and retained receipt handoff.
- [x] Keep finding severity, review, exact-head eligibility, serialized merge, and post-merge gates unchanged.

## Tests and release

- [x] Add focused controller tests for successful recovery and invalid consumer, release, stage, result, blocker, head, PR, and conflicting resume modes.
- [x] Add/adjust command-surface and skill-contract tests.
- [x] Run focused controller and bookkeeping tests.
- [x] Run a partial `rwbp-coordinator` candidate diagnostic and one canonical full-fleet candidate validation.
- [x] Run installer/audit parity checks and `make check`.
- [ ] Publish one corrective source release, then recover the original controller campaign and PR without replaying the failed merge action.

## Recovery validation command

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-controller.py resume \
  --repo . \
  --campaign fleet-0-54-0-20260726T143936Z \
  --recover-consumer rwbp-coordinator \
  --corrective-release <new-version> --json
```
