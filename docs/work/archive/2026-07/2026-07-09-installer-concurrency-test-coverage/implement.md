# Add Concurrent Installer Run Test Coverage Implementation Plan

## Execution Order

1. Add reusable receipt-consistency assertions if they do not already exist.
2. Build a temp target repo and start two installer subprocesses with
   overlapping arguments.
3. If natural overlap is unreliable, add a test-only synchronization hook in
   the harness, not production behavior.
4. Assert both process results are acceptable and the final receipt/provenance
   pair is internally consistent.
5. Document the last-writer-wins contract.

## Validation Plan

Run the focused concurrency test several times, then the full `tests.test_install_core`
suite and coverage gate.

## Documentation And Spec Updates

Add a short installer invariant note to the installed guide twins or relevant
spec: concurrent installs are not serialized, but completed runs must leave a
self-consistent receipt.

## Review Notes

The review should focus on flake resistance. Avoid sleeps that make the test
pass only on one machine.

## Follow-Ups

If a real race is found, create or fold in a fix task for locking or two-phase
receipt writes.
