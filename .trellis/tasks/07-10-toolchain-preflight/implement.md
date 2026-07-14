# Add Distributed Toolchain Preflight Implementation Plan

## Execution Order

1. Add shell-level fixture tests for the proposed `doctor`, `python`, and
   `run-python` contracts before adding the helper.
2. Implement the template helper using Bash 3.2-compatible functions and the
   existing shared shell-library conventions. Keep diagnostics on stderr and
   machine-readable/path output on stdout.
3. Add Python candidate fixtures for explicit override, repo `.venv`, Windows
   `.venv`, active virtualenv, both Homebrew prefixes, PATH fallback,
   unsupported versions, and missing required modules.
4. Add project-check discovery fixtures for explicit override, Make targets,
   package scripts, executable scripts, ambiguity, and recursive full-check
   detection. Do not execute discovered candidates in these tests.
5. Add the helper to `manifest.json`, installer/removal/audit expectations,
   provenance, generated parity, and target completeness tests.
6. Update template SD skills first: `sd-create-pr`, `sd-review-pr`,
   `sd-full-check`, and `sd-finish-work` only where their resolution or final
   report contract changes. Keep adapters thin.
7. Update README, contributing guidance, distributed docs, configuration and
   troubleshooting tables. Align macOS examples on versioned Homebrew Python
   3.13 and `.venv`.
8. Add the required changelog entry and bump the manifest version for shipped
   payload changes.
9. Self-install with the supported repo interpreter, refresh provenance and
   KB, then run focused and full validation.

## Validation Commands

```bash
make setup                         # only when .venv is absent or stale
.venv/bin/python -m unittest tests.test_toolchain_preflight
.venv/bin/python -m unittest tests.test_install_core tests.test_install_audit
make test
make lint
make audit
python3 scripts/sd-ai-command-pack-update-spec-kb.py
SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 \
SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 \
bash scripts/sd-ai-command-pack-full-check.sh
```

Run ShellCheck when available and explicitly test with macOS Bash 3.2.

## Review Focus

- No workload executes while merely resolving an interpreter.
- An invalid authoritative `.venv` fails once instead of falling through.
- Paths and module names are quoted/validated safely.
- Project-check discovery reports candidates without guessing or recursion.
- Full-check output does not imply that target project tests ran.
- No Trellis-owned files are changed.
- Installer, removal, receipt, provenance, and docs move together.

## Rollback Points

- After helper tests, before manifest integration: discard the additive helper
  if the command surface cannot remain portable and deterministic.
- After manifest integration, before skill adoption: keep the helper shipped
  but unused while correcting installer/audit behavior.
- After skill adoption: revert the skill calls as a unit; do not remove a
  manifest target without its removal/provenance/test updates.

## Completion Checklist

- [x] All resolution and single-execution fixtures pass.
- [x] Project-check discovery is conservative and non-mutating.
- [x] Pack-owned skills use/report the helper consistently.
- [x] Docs use Homebrew Python 3.13 and explain `.venv` precedence.
- [x] Root/template helper and skill mirrors match.
- [x] Version, changelog, manifest, provenance, and receipt are synchronized.
- [x] Coverage, Ruff, ShellCheck, install audit, KB freshness, and deterministic
      full-check pass.
