# Rescope the release-prep candidate loop to the thin shape

Child 2 of `08-09-thin-migration`, contract C-F. Pack-internal.

## Problem

The full-fleet candidate validator installs the **fat** payload into
disposable consumer checkouts and then runs each consumer's repo-owned
`candidateChecks`. It is `validate_consumer` in
`scripts/sd-ai-command-pack-fleet-candidate-check.py`, invoked as
`CANDIDATE_CHECK` from `.github/scripts/prepare-release.py:342`.
(`scripts/sd-ai-command-pack-fleet-preflight.py` only reports local
refresh status and is **not** this loop.)

Two properties make a naive rescope vacuous:

- **`prepare-release.py:338` skips the validator entirely** when the
  candidate ledger is already current, so a green `make release-prep`
  does not by itself prove the loop ran. This is worse than a timing
  hazard: `scripts/sd-ai-command-pack-fleet-candidate-check.py` has
  **no `manifest.json` payload row**, and the payload digest hashes only
  manifest-declared sources
  (`scripts/sd_ai_command_pack_fleet_lib.py:744`). So rewriting the
  validator itself moves neither the payload digest nor the fleet
  digest, the ledger stays current, and release-prep returns without
  ever running the new code. `tests/test_release_prep.py:90` tests that
  skip explicitly. Knowing about it is not a fix — this task must ship a
  mechanism.
- **All eight registry entries omit `mode` and therefore default to
  `fat`** (`scripts/sd_ai_command_pack_fleet_lib.py:26`). Before child 3
  there is no thin consumer to exercise, so "run each consumer in its
  declared mode" would validate nothing new while appearing to pass.

Once consumers convert, that gate validates a shape no consumer runs. If
it is rescoped *after* the first conversion, there is a window where the
only pre-release full-fleet gate is testing the wrong thing. Rescoping
before conversion closes that window; the parent design orders this
child ahead of every conversion for exactly that reason.

## Requirements

0. This task depends on child 1: converting a disposable checkout to the
   thin shape is `install.py --thin`.
1. `validate_consumer` exercises the thin shape: build the plugin,
   `claude plugin validate --strict`, load it with `claude
   --plugin-dir` in smoke mode, and run the machine installer into a
   scratch prefix.
2. Each consumer's repo-owned `candidatePrepare` / `candidateChecks`
   still run, against a checkout in the shape that consumer will
   actually be in.
3. **The thin shape is exercised regardless of declared modes.** A
   shadow-thin run against disposable checkouts happens even while all
   eight entries are `fat`, so the gate is real before the first
   conversion. Once modes diverge, the loop additionally exercises each
   consumer in its declared mode and silently skips neither kind.
4. The gate still blocks. A failing thin-shape step fails
   `make release-prep`, and that is proven by a deliberate break, not
   asserted.
5. If `claude` is unavailable in the environment, the loop reports the
   step as unavailable and fails — it never degrades an unrunnable
   validation into a pass.
6. **Ship a mechanism that makes a changed validator run.** Either a
   supported force-validation option, or bind a candidate-validator
   digest/version into the candidate ledger so editing the validator
   invalidates it. Decide which in this task's `design.md`; awareness of
   the skip is not a remedy for it.

## Acceptance criteria

- [ ] **Current ledger plus a changed validator source still executes
      validation.** Edit the validator, leave the ledger current, run
      `make release-prep`, and observe the validator run. Failing this
      means the rescope shipped code that release-prep never reaches.
- [ ] `make release-prep` exercises the thin shape end to end and
      passes on a clean tree, with evidence in its output that the
      validator actually ran.
- [ ] The shadow-thin run happens with all eight registry entries still
      `fat`, proven by the loop's output naming the thin steps it
      executed.
- [ ] A deliberately broken plugin build makes `make release-prep` exit
      nonzero; the break is reverted afterward and the revert verified.
- [ ] A registry with one `fat` and one `thin` consumer exercises both,
      proven by the loop's own output naming each consumer and the mode
      it ran.
- [ ] An absent `claude` binary produces an explicit unavailable
      diagnostic and a nonzero exit, never a silent pass.
- [ ] `make check` passes.
