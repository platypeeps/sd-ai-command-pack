# Add installer status, check, and JSON modes

## Goal

Make `install.py` the single self-service entry point for inspecting an
sd-ai-command-pack installation. Add concise human status, deterministic
machine-readable status, and an optional integrity audit without introducing a
separate `sd-pack` command or changing normal install/remove behavior.

## Confirmed Facts

- `install.py` already supports `--version`, `--dry-run`, `--remove`,
  `--platform`, `--all`, `--force`, `--backup`, and `--local-only`.
- A normal run refreshes the target; `--dry-run` safely plans that refresh but
  emits hundreds of per-target lines and is not a concise status interface.
- The installed target already carries `.sd-ai-command-pack/manifest.json`,
  `provenance.json`, and `installed-targets.txt` receipts.
- `scripts/sd-ai-command-pack-install-audit.py` owns completeness, structural,
  provenance, legacy, and expected-platform audit policy. It already accepts
  `--upstream-manifest` for advisory version comparison.
- Tracked provenance intentionally contains only pack identity, version, and
  vouched file hashes. Machine-local source checkout paths must not be added.
- Exit code `2` is reserved by argparse for invalid command-line usage. Exit
  code `3` is already used by pack tooling for a successful inspection that
  found operator action is required.
- Git pulling, branch creation, PR publication, and fleet orchestration already
  belong to Git, `sd-create-pr`, and `sd-fleet-refresh`.

## Requirements

- R1. Add `install.py <target> --status`. It must be strictly read-only and
  print a concise report containing source version, installed version,
  version relationship, installation state, detected/recorded adapter
  platforms, and aggregate planned-result counts.
- R2. Status states must distinguish at least `current`, `refresh-required`,
  `not-installed`, and `invalid`. A source/installed version mismatch,
  new source target, source-changed target, removable retired target, or safe
  installer conflict makes an audit-clean installation `refresh-required`.
  Malformed or internally contradictory receipts and failed integrity audit
  make it `invalid`; corruption must not be presented as a routine update.
- R3. Add `install.py <target> --check`. It uses the same inspection model,
  runs the existing install-audit executable, prints the concise report, and
  exits `0` only when current and audit-clean, `3` when a valid refresh is
  required, and `1` for invalid state, audit failure, or operational error.
  Argparse usage errors remain `2`.
- R4. Add `--audit` for `--status`. It runs the same source-owned audit command
  as `--check` and incorporates its result without copying audit rules into
  installer modules. `--check` implies `--audit`. When no installed footprint
  exists, audit is `not-applicable` rather than invoked; `--check` exits `3`.
- R5. Add `--json`, valid with `--status` or `--check`. Output must be one JSON
  document with schema version, pack identity, absolute target, source and
  installed versions, relationship, state, platforms, result counts, change
  total, and audit status/exit/output when requested. No human prose may appear
  on stdout in JSON mode; diagnostics belong in the JSON document.
- R6. Human status output must remain bounded by categories rather than print
  every manifest path. It must say explicitly when no installed footprint or
  no changes are found.
- R7. Inspection must use the current pack checkout as the source and the
  positional argument as the target. It must never discover, persist, fetch,
  pull, clone, or update a source checkout.
- R8. `--status` and `--check` are mutually exclusive action modes and reject
  mutation/selection flags whose meaning would be ambiguous: `--remove`,
  `--dry-run`, `--force`, `--backup`, `--local-only`,
  `--skip-trellis-init`, `--skip-diff-check`, `--platform`, and `--all`.
  `--audit` and `--json` without an inspection mode are usage errors.
- R9. Existing install, refresh, dry-run, local-only, force/backup, and removal
  output and exit behavior must remain compatible.
- R10. Add focused unit and CLI tests for parser combinations, all state and
  exit-code paths, deterministic JSON, audit pass/fail/timeout or launch
  failure, platform reporting, malformed receipts, and proof that inspection
  writes no target files.
- R11. Document the new modes in `README.md` and
  `docs/SD_AI_COMMAND_PACK.md`, including an exit-code table and examples.
  Because the distributed guide and manifest version change, use the next
  minor release, update `CHANGELOG.md`, refresh candidate evidence, and keep
  all release gates green.

## Acceptance Criteria

- [x] A1. `install.py <current-target> --status` reports `current` concisely,
  exits `0`, and leaves the target byte-for-byte unchanged.
- [x] A2. Audit-clean behind, ahead, source-changed, new-target,
  retired-target, and safe-conflict fixtures report `refresh-required`;
  `--check` exits `3` for each valid case.
- [x] A3. Missing installation reports `not-installed`; `--check` exits `3`.
- [x] A4. Missing or drifted vouched targets, malformed or contradictory
  installed manifest/provenance/receipt data, and other integrity failures
  report `invalid`; `--check` exits `1` with an actionable reason.
- [x] A5. `--check` and `--status --audit` invoke the existing audit script;
  audit failure produces state/audit evidence and exit `1` without mutation.
- [x] A6. `--json` output parses as exactly one deterministic schema-versioned
  JSON document and carries the same state, counts, platforms, audit result,
  and effective exit semantics as human output.
- [x] A7. Invalid flag combinations exit `2` with argparse guidance, while all
  pre-existing valid argument combinations retain their behavior.
- [x] A8. Help, README, installed guide, changelog, and tests document the same
  status names and exit codes.
- [x] A9. Installer coverage remains 100 percent line and branch coverage;
  focused tests, `make check`, full-check, candidate ledger validation, and
  generated/source parity gates pass.

## Out Of Scope

- Adding an `sd-pack` skill or platform command.
- Pulling or otherwise changing the pack source checkout.
- Creating branches, commits, pull requests, releases, or fleet refreshes from
  `install.py`.
- Persisting a source checkout path in tracked receipts or provenance.
- Adding JSON output to normal install, remove, or verbose dry-run mode.
- Replacing or weakening `scripts/sd-ai-command-pack-install-audit.py`.
