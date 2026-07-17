# Installer status, check, and JSON design

## Boundaries

`install.py` remains the CLI entry point and `manifest.json` remains the source
of truth. Inspection is a read-only planning path over the same manifest,
selection, destination classification, receipt, and retired-target primitives
used by installation. It does not call the normal applying path and does not
write generated receipts merely to discover their expected content.

Add a focused `installer/inspection.py` module rather than expanding the
existing status-enum module or embedding another large concern in `install.py`.
The module owns immutable inspection records, receipt parsing, version
relationship, platform summarization, aggregate state classification, and
human/JSON serialization. `install.py` owns argument validation and exit-code
selection.

The existing standalone install-audit script remains the audit authority.
Inspection invokes it with the current interpreter, `--repo <target>`, and
`--upstream-manifest <pack-root>`, captures stdout/stderr, and records the
result. Inspection performs only the minimum receipt trust checks needed before
planning (shape, safe paths, receipt agreement, and vouched hashes); audit
completeness, expected-platform, structural, legacy-reference, and migration
policy remains solely in the shipped audit script.

## CLI Contract

Inspection introduces two mutually exclusive actions:

```text
install.py [TARGET] --status [--audit] [--json]
install.py [TARGET] --check [--json]
```

`--check` implies audit. Inspection rejects every mutation or platform
selection option. Normal installation remains the default action when neither
inspection flag nor `--remove` is present.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Inspection completed; installation is current and any requested audit passed. |
| `1` | Invalid installation, failed audit, unreadable state, or operational failure. |
| `2` | Invalid CLI usage from argparse. |
| `3` | Inspection completed successfully; install/refresh action is required. |

Human `--status` intentionally exits `0` for both `current` and
`refresh-required`: it is an informational command. Human `--status --audit`
exits `1` only when audit/inspection is invalid. `--check` applies the complete
table, including `3` for refresh-required. JSON does not alter exit semantics.

## Inspection Model

Use a schema-versioned immutable record with these public fields:

```json
{
  "schemaVersion": 1,
  "pack": "sd-ai-command-pack",
  "target": "/absolute/repo",
  "sourceVersion": "0.16.0",
  "installedVersion": "0.15.7",
  "versionRelation": "behind",
  "state": "refresh-required",
  "platforms": {
    "installed": ["claude", "github"],
    "active": ["claude", "github"]
  },
  "counts": {"unchanged": 100, "updated": 2},
  "changeCount": 2,
  "reasons": ["installed version 0.15.7 is behind source 0.16.0"],
  "audit": {
    "requested": true,
    "status": "passed",
    "exitCode": 0,
    "output": "SD AI command pack install audit passed: ..."
  }
}
```

Versions are strict stable `MAJOR.MINOR.PATCH` values. Equal versions produce
`current`; lower installed version is `behind`; higher is `ahead`. Missing
installed receipts produce `not-installed`. Malformed JSON, unsafe receipt
paths, pack-name mismatch, disagreement between installed manifest and
provenance versions, or unsupported data types produce `invalid` with reasons.

Platforms are reported as two sorted observations:

- non-shared platform entries represented by the installed-target receipt and
  installed manifest; and
- active Trellis platform markers detected through the existing platform
  registry, including marker-only platforms such as Codex.

These are reported as observed installation state, not persisted as new
metadata.

## Planning And State Classification

Inspection selects files using the existing default selection rules and
classifies destinations with existing dry-run-safe file functions. It also
computes generated receipt/provenance expectations and retired-target results
without applying writes. Aggregate result statuses are normalized into stable
count keys.

- `current`: versions agree, all selected/generated files are unchanged, no
  removable retired target exists, and receipts are internally valid.
- `refresh-required`: installation is absent, versions differ, or any planned
  target would be created, updated, overwritten, removed, or conflicts with
  source state, provided the currently installed footprint remains audit-clean.
- `invalid`: receipt/provenance/manifest cannot be safely interpreted or its
  integrity audit fails. Audit failure overrides `current`/`refresh-required`
  for the effective check result while preserving pre-audit reasons and counts.

When there is no installed footprint, audit is `not-applicable` and is not
spawned. The state remains `not-installed`; `--status` exits `0` and `--check`
exits `3`.

Every returned reason is deterministic and sorted by stable discovery order.
Human output prints the summary and counts only; JSON contains the same data.

## Read-Only Guarantee

Inspection must not call Trellis initialization, backup creation, atomic write,
managed-block mutation, local exclude mutation, stale-target removal, or final
`git diff --check`. Tests snapshot the complete target tree (file bytes,
symlinks, and modes where practical) before and after every inspection mode.

The audit subprocess is also read-only by contract. Timeouts and launch errors
become audit `error` results and exit `1`, never a silent skip.

## Compatibility And Release

Existing parser defaults and applying code stay intact. New argument validation
runs only when an inspection-specific flag is present. Existing tests remain
the regression suite for install/remove behavior.

This additive public CLI is a minor release. Update `manifest.json`, top
`CHANGELOG.md`, README, distributed guide, and candidate validation ledger.
No new installed file is required, so manifest target entries stay unchanged.

## Rejected Alternatives

- Separate `sd-pack` command: duplicates installer and audit policy.
- Store `sourceRoot` in provenance: leaks machine-local paths into tracked
  consumer state.
- Implement Git pull in `install.py`: couples deterministic installation to
  source-control mutation.
- Parse normal `--dry-run` prose: unstable and unnecessarily expensive for
  automation.
- Duplicate the audit scanner in `installer/inspection.py`: creates two policy
  authorities that will drift.
