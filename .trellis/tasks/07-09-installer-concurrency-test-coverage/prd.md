# Add concurrent-installer-run test coverage

## Goal

Pin the installer's behavior when two `install.py` runs touch the same target
repo concurrently, so the receipt/provenance last-writer-wins semantics are a
verified contract rather than an unknown.

## Problem

Surfaced by the 2026-07-09 testing review (LOW). The suite is otherwise
strong (361 behavioral tests, 100% line+branch installer coverage), but has
zero coverage of concurrent installer runs against one repo. Unknowns:

- Two overlapping writers to `.sd-ai-command-pack/installed-targets.txt` and
  `provenance.json` — is the final receipt internally consistent, or can it
  record a torn/partial target set?
- Per-file atomic writes (`atomic_write_bytes` → `os.replace`) are individually
  safe, but the receipts are written once at the end from each process's view;
  interleaving is untested.
- Backup-path selection (`next_backup_path`) races: two runs could target the
  same `.bak` name.

This is a test-coverage/contract gap, not a known crash — the task is to
establish the expected behavior and lock it, and only harden code if a test
reveals an inconsistency.

## Requirements

- R1: Add a test that runs two installers against the same fresh target repo
  with overlapping timing (e.g. two subprocesses, or a controlled in-process
  interleaving), then asserts the resulting receipts are internally consistent:
  `provenance.json` parses, every vouched target exists with a matching hash,
  and `installed-targets.txt` agrees with provenance.
- R2: Define and document the intended concurrency contract (last-writer-wins
  with each run leaving a self-consistent receipt is acceptable; a corrupt or
  half-written receipt is not). Record it where installer invariants live.
- R3: If R1 surfaces a real inconsistency (torn receipt, backup collision),
  file/fold a follow-up fix; otherwise the test simply pins current behavior.

## Acceptance Criteria

- [ ] A concurrency test exists and passes deterministically (no flakiness on
      the CI matrix); it fails if made to write a torn receipt.
- [ ] The concurrency contract is documented.
- [ ] 100% line+branch installer coverage maintained; suite runtime not
      materially regressed.

## Non-goals

- Introducing file locking or a lockfile unless R1 proves it necessary —
  prefer to document last-writer-wins if it is already safe.
