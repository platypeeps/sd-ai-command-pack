# Enforce Adapter Content Parity And Generate Command Fan-Out Design

## Overview

Command adapter drift is currently caught by marker strings and manual
manifest entries. This task should single-source the thin adapter fan-out and
strengthen bespoke adapter parity without forcing every platform into one
template format.

## Proposal

Treat `templates/.commands/sd-*.md` as the neutral command body source. For
OpenCode commands that are byte-identical to the neutral source, point manifest
entries directly at the neutral file and delete the duplicate OpenCode file.
Resolve the one divergent OpenCode command by either adopting neutral wording
or documenting an intentional platform-specific deviation in the test.

For Claude, Gemini, and GitHub, add body-extraction helpers in
`tests/test_generated_parity.py`. Each helper should normalize only the
platform wrapper format, then compare the shared command body to the neutral
source. The goal is structural content parity, not identical frontmatter or
TOML metadata.

For the ten thin platforms, derive expected command manifest entries from
`PLATFORM_REGISTRY` plus the neutral command set. The manifest can remain flat,
but a test should prove the flat entries match what the registry would
generate. This cuts future "add a command" work from many hand-written entries
to one neutral file plus generated/derived coverage.

## Boundaries And Non-Goals

Do not implement a full templating engine for bespoke formats. Do not change
manifest schema sections; that is tracked separately and parked.

## Affected Files

- `manifest.json`
- `templates/.commands/`
- `templates/.opencode/commands/`
- `templates/.claude/commands/sd/`
- `templates/.gemini/commands/sd/`
- `templates/.github/prompts/`
- `installer/registry.py`
- `tests/test_generated_parity.py`

## Risks And Edge Cases

Some platform prompts may need platform-specific command syntax. Keep explicit
deviation records close to parity tests so they are reviewed, not accidental.

## Validation

Run generated parity tests, install selection tests, pack drift tests, and a
full install fixture for `--all` to prove targets remain unchanged where
intended.
