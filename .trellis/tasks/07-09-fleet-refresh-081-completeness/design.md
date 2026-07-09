# Fleet Refresh To 0.8.1 With Install Completeness Verification Design

## Overview

This task should make fleet refreshes self-checking before opening consumer
PRs and after installation. The design keeps refreshes operator-triggered, but
turns the fleet inventory, target-version check, and expected installed target
set into checked pack-owned data instead of session memory.

## Proposal

Add a checked-in fleet manifest that records each consumer repository slug,
local path hint, and enabled platform set. Build a rollout preflight that reads
each consumer's `.sd-ai-command-pack/provenance.json` and skips repos already
at the requested manifest version before creating branches or commits.

Extend the install/audit surface with a provenance-independent completeness
check: derive the expected target set from `manifest.json`, the selected
platforms, generated receipt files, and managed blocks, then compare that
against the target repo's disk, receipt, and provenance state. This check must
fail when a selected target such as `.claude/commands/sd/work-backlog.md` is
missing even if provenance omitted it.

Reproduce the broken 0.7.0 install pattern in installer tests by constructing a
repo whose `.claude/` state matches the failing consumers. If the installer is
silently skipping selected targets, fix the skip path; if the reproduction is
negative, keep the completeness check as the compensating control and record
the negative result.

## Boundaries And Non-Goals

This does not create unattended scheduled rollouts. It also does not delete
stale local clones; it only keeps them out of the fleet manifest.

## Affected Files

- New fleet manifest/runbook location, likely under `docs/`, `scripts/`, or a
  pack-owned config file.
- `install.py`, `installer/fileops.py`, `installer/provenance.py`, and
  `scripts/sd-ai-command-pack-install-audit.py` for expected-target logic.
- `tests/test_install_audit.py`, `tests/test_install_core.py`, and
  `tests/test_generated_parity.py` for completeness and platform assertions.
- `docs/SD_AI_COMMAND_PACK.md`, `templates/docs/SD_AI_COMMAND_PACK.md`, and
  `README.md` for operator workflow.

## Risks And Edge Cases

The biggest risk is deriving a target set differently from the installer. Reuse
`selected_files()` and registry data rather than duplicating platform logic.
Local-only installs and `--platform` filters must remain valid inputs. The
fleet manifest must not treat stale aliases such as `green-button-manager` as
separate consumers.

## Validation

Add fixture tests for at-target skip, missing selected target failure, and a
complete install pass. Run the installer coverage gate, shipped-scripts
coverage gate, `git diff --check`, and the pack full-check with Prism/Gito
disabled. Validate at least one dry-run rollout skips an already-current repo.
