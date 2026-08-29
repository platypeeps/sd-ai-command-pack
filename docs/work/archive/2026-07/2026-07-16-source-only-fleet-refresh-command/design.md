# Source-Only Fleet Refresh Command Design

## Overview

`sd-fleet-refresh` orchestrates this repository's installer, fleet manifest,
preflight helper, and rollout runbook. Those dependencies intentionally are not
consumer payload, so distributing only the command surfaces creates an
unusable command and dangling documentation references. The fix separates
source command generation from consumer manifest generation.

## Registry Contract

Keep `COMMAND_NAMES` as the complete source command catalog so adapters continue
to be generated and parity-checked. Add a source-only command set owned beside
that catalog. The generator continues producing source/template adapters for
all commands, but `generate_manifest_text()` emits derived manifest entries
only for commands outside the source-only set. Its stale-entry classifier must
still recognize all command shapes so regeneration removes old fleet targets
from an existing manifest.

This keeps one command catalog and one source-only policy declaration. Tests
must reject unknown source-only names and prove every source-only command is
absent from manifest targets.

## Retirement Contract

List the former fleet-refresh target footprint in the existing retired-target
mechanism. Consumer refreshes then remove hash-vouched copies, preserve drifted
copies without force, and include the paths in full-remove recognition.

The pack source checkout is the one exception: its root command surfaces are
source files, not consumer leftovers. `retire_stale_targets()` must skip only
the source-only target group when the destination resolves to the pack root;
other retired targets retain normal cleanup behavior. After one dogfood sync,
receipts and provenance no longer list source-only paths.

## Documentation Contract

The distributed guide may describe `sd-fleet-refresh`, but must state that it is
available only from the canonical pack source checkout and is not installed in
consumers. Remove it from consumer command-completion lists and installed-file
inventories while retaining the operator procedure section.

## Risks

- Filtering too early could stop adapter generation or prevent stale manifest
  rows from being removed.
- A blanket source-repo retirement skip could preserve unrelated retired
  commands; scope the exception to the source-only target set.
- Tests that infer installable commands by scanning templates must switch to
  registry policy rather than treating every template as consumer payload.

## Validation

- Generator `--check` and manifest target assertions.
- Fresh consumer install and old-consumer retirement fixtures.
- Source-root dogfood preservation fixture.
- Installer line/branch coverage and shipped-script coverage.
- `make sync`, KB refresh, and the deterministic full-check.
