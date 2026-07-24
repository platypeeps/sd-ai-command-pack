# Implementation plan: finish-work bookkeeping validator

## 1. Consolidate rule fixtures

- Inventory current changed-task preflight, archive-description test,
  placeholder, completed-root, topology, journal, and whitespace rules.
- Add pre-archive and final-bundle good/base/failure fixtures, including the
  blank-description failure from the recent main push.

## 2. Implement the canonical validator

- Add strict versioned JSON input/output and concise human rendering.
- Share task/artifact readers and reason codes with existing preflight logic.
- Enforce regular-file, bounds, UTF-8, containment, identity, topology,
  lifecycle, journal/index, commit, placeholder, and whitespace contracts.

## 3. Integrate finish-work and callers

- Run `pre-archive` before delegated Trellis mutation.
- Run `final-bundle` after archive/journal creation and before any push.
- Make pre-publication, `sd-check`, and bookkeeping CI invoke the same rules;
  delete duplicate implementations only after equivalent coverage exists.

## 4. Validate lifecycle behavior

- Prove failures before archive create no bookkeeping commits.
- Prove post-bundle failures preserve local recovery state and prevent push.
- Prove valid finalization retains commit order, one push, and exact-head
  downstream gates.
- Run focused tests, generated parity, `make sync`, and `make check`.
