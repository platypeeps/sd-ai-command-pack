# Add Concurrent Installer Run Test Coverage Design

## Overview

The installer uses atomic per-file replacement, but receipt/provenance writes
are produced at the end of each run. This task should define and test the
expected behavior when two installer processes target the same repo.

## Proposal

Start with a deterministic test rather than adding locks. Use two subprocess
installer invocations against one temp repo, with controlled timing if needed
through environment hooks or monkeypatchable slow paths. After both finish,
assert the final receipt state is self-consistent: provenance parses, every
vouched file exists and matches its recorded hash, `installed-targets.txt`
agrees with provenance, and no partial JSON or torn receipt remains.

Document the intended contract as "last writer wins, but every completed run
must leave self-consistent receipts." If the test exposes backup-name or
receipt interleaving bugs, fold in the smallest code fix or split a follow-up.

## Boundaries And Non-Goals

Do not introduce lock files unless the test proves the current contract cannot
hold. This is coverage first, hardening second.

## Affected Files

- `tests/test_install_core.py` or a new installer concurrency test file
- `tests/install_test_support.py` for shared receipt assertions if useful
- `docs/SD_AI_COMMAND_PACK.md` and template twin for the concurrency contract

## Risks And Edge Cases

Concurrency tests can be flaky. Prefer deterministic synchronization over
sleep-only timing, and keep runtime acceptable for macOS and Ubuntu CI.

## Validation

Run the new test repeatedly locally, then the full installer coverage gate.
Mutation testing can be simulated by writing a torn provenance fixture and
asserting the consistency check catches it.
