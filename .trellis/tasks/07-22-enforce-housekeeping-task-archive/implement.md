# Implementation plan: roll out the housekeeping finish-work gate

## Activation

1. After plan approval, create a source feature branch for this task, record it
   in `task.json`, validate the task, and run `task.py start`.
2. Load the relevant Trellis and fleet specifications in inline mode; do not
   curate the seed JSONL manifests.

## Source Preconditions

3. Run the pack toolchain doctor and the housekeeping hermetic self-test.
4. Refresh and verify the canonical `0.30.2` candidate ledger.
5. Initialize one timing run for all eight manifest consumers, record its run
   ID in the task, and start the fleet preflight timing stage.
6. Fetch the release tag only if required, then run the canonical fleet
   preflight. Stop before consumer inventory or mutation if tag, payload, or
   candidate evidence fails.

## Fleet Execution

7. Maintain the wave-state snapshot and use the source wave planner before
   every consumer start and merge decision.
8. Process consumers conservatively one at a time in manifest order:
   `rwbp-coordinator`, `loadsmith`, `hoa-manager`, `rwbp-website`,
   `mezmo_benchmark`, `se-ai-command-pack`, `sd-github-review`, and
   `anomaly-metric-creator`.
9. For each stale consumer:
   - verify checkout ownership and a clean tree; otherwise record `skipped`;
   - capture the exact default-branch base and create one refresh branch;
   - run the preflight-printed install and expected-platform audit commands;
   - run the consumer's documented full-check;
   - inspect that the diff contains installer-owned paths only;
   - commit, classify the exact head, push, and create one refresh PR;
   - start reviewer and CI timing together, delegate exact-head review, apply
     the finding-severity gate, and settle CI with watch in no-merge mode;
   - run finish-work, push any resulting bookkeeping head, wait for its checks,
     and merge only through housekeeping with that exact head;
   - verify post-merge provenance, audit, clean default branch, and branch
     cleanup before recording `refreshed-merged`.
10. On a verified `0.30.2` reproduction of stranded task bookkeeping, record
    the evidence, classify it as a pack correctness blocker, pause the fleet,
    and create or reuse one source corrective task. Do not add an ad hoc
    consumer repair to this rollout.

## Completion

11. Rerun fleet status and preflight after all selected consumers have a
    terminal outcome; record at-target and remaining-stale consumers.
12. Complete the timing report and add the per-consumer table, finding
    dispositions, PR links, validation evidence, skips, retries, and anomalies
    to this task's PRD.
13. Run `sd-update-spec`; expect no executable spec change unless rollout
    evidence reveals a new contract.
14. Commit only the source task/result bookkeeping, then invoke
    `sd-create-pr` to publish it. Complete deterministic review, finish-work,
    and source housekeeping normally.

## Validation Commands

```bash
bash scripts/sd-ai-command-pack-toolchain.sh doctor
bash scripts/sd-ai-command-pack-housekeeping.sh --self-test
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py --check-ledger
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-preflight.py
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet
```

Per-consumer install, audit, full-check, review, watch, housekeeping, and
post-merge commands come only from preflight, the fleet manifest, and the
installed SD skills.

## Rollback And Stop Points

- Before consumer PR creation: stop on the local refresh branch and report.
- After PR creation: leave the PR open; never bypass review or CI.
- After merge: preserve completed consumers; do not roll them back because a
  later consumer is skipped.
- On pack blocker: pause before another mutation, run one corrective campaign,
  release a patch, then resume this task from a fresh preflight.
