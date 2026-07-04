# Record pack version and content hashes in the install receipt

## Goal

From loadsmith 07-02-supply-chain-pinning: consumer repos exempt vendored pack files from line review ("reviewed upstream") but nothing in-repo makes that claim checkable. Record the pack version plus per-file content hashes at install time and verify them in the install audit, so tampered refresh PRs hiding command overrides in reviewer-exempted files are detectable.

## Requirements

- R1: `install.py` writes `.sd-ai-command-pack/provenance.json` on every
  non-dry-run install: pack name, version, and a sorted map of installed
  plain-file targets to `sha256:<hex>` of their installed content. Excluded:
  preserved targets (user-tuned, e.g. `.prism/rules.json`), managed-block
  targets (shared ownership), generated files (receipt, provenance itself),
  and conflict results. Dry-run reports the would-be write without writing.
- R2: The provenance file is recorded in the installed-targets receipt and
  is a recognized pack-like file for the audit.
- R3: The install audit verifies provenance when present: a listed file that
  exists with different content is a failure naming the file and the
  recorded pack version; listed-but-absent files defer to the structural
  missing/gitignored handling; unreadable or malformed provenance is a
  failure. Absent provenance file keeps today's behavior (no verification).
- R4: Docs (README + usage guide + twins) describe the provenance file and
  the tamper-evidence it provides; the repo spec records the contract.

## Non-goals

- No signature/attestation chain — content hashes make local tampering
  visible; cryptographic provenance is out of scope.
- No hash coverage for files installed by a different checkout's run (the
  provenance reflects the recorded install).

## Acceptance Criteria

- [ ] Fresh install produces provenance.json listing hashed targets and
      excluding preserved/managed/generated files.
- [ ] Audit passes on an untouched install; editing a hashed file makes the
      audit fail with a drift message; deleting provenance.json returns to
      pre-provenance behavior; malformed provenance fails the audit.
- [ ] Receipt lists provenance.json; twin gate and 100% install.py coverage
      hold; docs and spec updated.
