# Implementation Plan

1. [x] Update installer model and provenance flow:
   - Allow `PackFile.source` to be optional.
   - Make generated pack files source-less.
   - Add source content/digest fields to `InstallResult`.
   - Reuse preflight results in the apply pass.
   - Prefer result-carried source digests in provenance.
2. [x] Add focused regression tests:
   - generated files have no source and are not provenance-vouched;
   - apply can reuse planned source bytes;
   - provenance does not re-read a source when the result has a digest.
3. [x] Resolve docs:
   - correct `CHANGELOG.md` dates for `0.7.1`-`0.7.4`;
   - add `REVIEW_PREFLIGHT_PR_BODY` removal target to README, installed guide,
     and script warning/help surfaces;
   - document shell/GitHub automation coverage exemption and compensating gates.
4. [x] Reconcile `.trellis/audit/ledger.md`:
   - mark local fixed items fixed;
   - keep A-027 open with upstream handoff;
   - park A-027 as `.trellis/tasks/07-16-upstream-trellis-hook-shell-semantics/`;
   - update `last-seen` for all touched findings.
5. [x] Validate:
   - focused unit tests for installer/provenance/review scope;
   - `make lint` if the focused checks pass;
   - update spec KB if docs/spec/task artifacts changed.
