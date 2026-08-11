# Rescope the candidate validator loop to the thin shape

Child of `08-09-thin-migration`, contract C-F. Pack-internal. Split out of
`08-10-thin-candidate-loop-rescope` on 2026-08-11 by operator decision, after
three planning-review rounds found four blocking concerns against this half.

## Why this is a separate task

Contract C-F had two defects behind one title. The *reachability* defect —
`make release-prep` skipping the validator when the ledger is current — is
mechanical, independently correct, and is being shipped by
`08-10-thin-candidate-loop-rescope`. This half, rescoping `validate_consumer`
to the thin install shape, turned out to need a different design shape than the
first attempt assumed, plus one policy decision. Shipping the mechanism first
also means this task's work becomes verifiable for the first time: until the
digest binding lands, an edited validator is not reached by release-prep at
all.

**Depends on `08-10-thin-candidate-loop-rescope`.** Not for correctness — for
observability. Do not start this before that lands, or the acceptance criteria
below cannot be measured.

## Problem

Once consumers convert, the full-fleet candidate gate validates a shape no
consumer runs. All eight registry entries currently omit `mode` and default to
`fat` (`fleet_lib.py:26`), so "run each consumer in its declared mode" would
validate nothing new while appearing to pass. Rescoping *after* the first
conversion leaves a window where the only pre-release full-fleet gate tests the
wrong thing; the parent design orders this child ahead of every conversion for
that reason.

## The four concerns this task owns

Each was measured during the prior task's planning review. They are inputs, not
speculation, and a design that does not answer all four is not ready.

1. **C-1 — the conversion mutates the pack's own registry.**
   `install.py --thin` without `--consumer` is rejected; *with* it, a
   successful conversion calls `flip_registry_mode`
   (`installer/thin.py:967-976`) and flips that consumer to `thin` in this
   repository's fleet registry. A validator that mutates the source checkout is
   not a validator, and it would destroy the "all eight entries still `fat`"
   property the shadow-thin proof depends on. Needs an isolated registry
   mechanism or a conversion entry point that does not write the registry.

2. **C-2 — the clean-tree precondition defeats the obvious ordering.** The
   conversion needs a prior install to have placed a machine-scope payload, but
   installing the candidate dirties the clone;
   `sd-ai-command-pack-thin-resweep.py:1723` turns a dirty worktree into a
   blocked verdict, and `install.py:898` re-runs the resweep fresh and refuses
   on any blocker. Needs a pre-cleaned conversion fixture, a commit or
   normalization step, or a different sequence entirely.

3. **C-3 — already-thin checkouts reject `--platform`.** A fat-install-first
   lane passes `--platform`, but an already-thin checkout enters the
   thin-refresh branch (`install.py:1474`) where `--platform` is explicitly
   rejected (`install.py:1268`). Once modes diverge in production, an
   unconditional lane breaks. Needs branching on checkout state or separately
   prepared per-lane checkouts.

4. **C-4 — `blocked` has no representation in the current gate, and needs a
   policy decision.** A non-`clear` resweep verdict is a real outcome, but
   `fleet-candidate-check.py:502` fails validation for every consumer whose
   status is not `passed` and suppresses the ledger, and `fleet_lib.py:829`
   rejects a non-`passed` consumer during ledger validation. **The policy
   question — does a consumer the pack cannot convert fail `make release-prep`?
   — is deferred to this task and is not answered.** Treating a blocked lane as
   top-level `passed` would make the ledger certify a thin validation that
   never completed, so "just report it" is not free either.

## Requirements

1. `validate_consumer` exercises the thin shape: build the plugin,
   `claude plugin validate --strict`, load it with `claude --plugin-dir` in
   smoke mode, and run the machine installer into a scratch prefix.
2. Each consumer's repo-owned `candidatePrepare` / `candidateChecks` still run,
   against a checkout in the shape that consumer will actually be in.
3. **The thin shape is exercised regardless of declared modes.** A
   shadow-thin run against disposable checkouts happens even while all eight
   entries are `fat`, so the gate is real before the first conversion. Once
   modes diverge, the loop additionally exercises each consumer in its declared
   mode and silently skips neither kind.
4. The gate still blocks: a failing thin-shape step fails `make release-prep`,
   proven by a deliberate break rather than asserted.
5. If `claude` is unavailable, the loop reports the step as unavailable and
   fails — it never degrades an unrunnable validation into a pass.
6. Answer C-4 explicitly in `design.md`, and make the ledger contract agree
   with the answer.

## Acceptance criteria

- [ ] `make release-prep` exercises the thin shape end to end and passes on a
      clean tree, with evidence in its output that the validator actually ran.
- [ ] The shadow-thin run happens with all eight registry entries still `fat`,
      proven by the loop's output naming the thin steps it executed, **and** by
      the registry still reading eight `fat` entries afterward — the C-1 check.
- [ ] A deliberately broken plugin build makes `make release-prep` exit
      nonzero; the break is reverted afterward and the revert verified.
- [ ] A registry with one `fat` and one `thin` consumer exercises both, proven
      by the loop's own output naming each consumer and the mode it ran.
- [ ] An absent `claude` binary produces an explicit unavailable diagnostic and
      a nonzero exit, never a silent pass.
- [ ] A consumer whose resweep verdict is not `clear` produces the behavior
      C-4's answer specifies, and the ledger contract agrees with it — proven
      by a test, not by reading the code.
- [ ] `make check` passes.

## Non-goals

- The reachability mechanism — `08-10-thin-candidate-loop-rescope`.
- Converting any consumer. Children 3–5 own that and are blocked on explicit
  per-cohort user authorization (`08-09-thin-migration/prd.md:91`).
