# Adapter + manifest generation from registry

## Problem
Audit A-034: bespoke adapter transform rules live in parity tests with no
producer; manifest command entries (25/command, 534 total) are hand-written
pattern expansions of registry data (A-009/A-012 adjacency).

## Goal
`make generate` produces the claude/gemini/github adapters and all derived
manifest command entries from COMMAND_NAMES + PLATFORM_REGISTRY; a drift
test keeps committed surfaces in sync; adding a command = skill + neutral +
one list entry.

## Requirements
Parent design § 1 is binding: dev-side generator at .github/scripts/,
override list for intentionally-divergent bodies, --check mode, one-time
canonical manifest reorder, byte-identical adapter reproduction.

## Acceptance Criteria
- [ ] --check clean on the committed tree; CI drift test wired.
- [ ] Scratch-adding a dummy command yields complete surfaces.
- [ ] Parity suites stay green; alias-rewrite data single-sourced.
