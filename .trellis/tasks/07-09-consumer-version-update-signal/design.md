# Give Consumers A Pack-Version Update Signal Design

## Overview

Consumers can audit installed files but cannot tell whether a newer pack
version exists. This task should add a read-only, fail-soft signal that reports
current/behind/ahead against a local pack reference without changing gates.

## Proposal

Extend `scripts/sd-ai-command-pack-install-audit.py` with an optional flag such
as `--upstream-pack <path>` or an environment variable pointing at a pack
checkout. The script reads the consumer's installed provenance version and the
reference checkout's `manifest.json` version, compares normalized semantic
versions, and prints one of: current, behind, ahead, or unknown.

Keep the feature fail-soft. Missing provenance, missing reference checkout,
invalid reference manifest, or unparsable versions should produce a clear note
and preserve the existing audit exit behavior unless the user explicitly asks
for strict update checking in a future task.

This pairs with release-ledger enforcement; tags make the reference meaningful,
but the first implementation can compare local manifest versions only.

## Boundaries And Non-Goals

No network registry calls and no automatic self-update. Installs stay
PR-reviewed and operator-triggered.

## Affected Files

- `templates/scripts/sd-ai-command-pack-install-audit.py`
- `scripts/sd-ai-command-pack-install-audit.py`
- `tests/test_install_audit.py`
- `docs/SD_AI_COMMAND_PACK.md` and template twin
- `README.md` if the maintainer workflow mentions consumer pull-side checks

## Risks And Edge Cases

Version comparison should not mis-handle prereleases or non-semver strings.
When in doubt, report "could not compare" rather than failing an audit.

## Validation

Add tests for behind, current, ahead, missing upstream, missing provenance, and
invalid manifest. Keep shipped-scripts coverage at or above the current floor.
