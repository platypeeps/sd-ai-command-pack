# Dropped Claude Work-Backlog Install Root Cause Implementation Plan

1. Inspect installer selection, anchor detection, force overwrite, receipt, and
   provenance code paths for conditions that can skip one selected Claude
   command while installing siblings.
2. Add a focused test fixture with `.claude/` gitignore/local-state behavior and
   explicit Claude platform selection.
3. Attempt to reproduce the historical symptom by forcing or simulating the
   suspected skip condition.
4. If reproduced, fix the generic skip/recording path and assert the target
   appears on disk, in receipt, and in provenance.
5. If not reproduced, add a short negative-result note to the PRD and verify the
   manifest completeness audit fails when the target is removed from disk and
   receipt.
6. Run focused tests, `make test`, and the pack full-check with Prism/Gito
   disabled.
