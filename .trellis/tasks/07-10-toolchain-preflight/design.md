# Add Distributed Toolchain Preflight Design

## Overview

Add a small Bash 3.2-compatible helper as the executable policy boundary for
pack-owned tool resolution. It reports deterministic choices and can execute a
selected Python exactly once. Skills remain orchestration text; they consume
the helper instead of duplicating platform-specific resolution snippets.

## Command Surface

Ship a helper named `sd-ai-command-pack-toolchain.sh` under the repository's
scripts directory with three subcommands:

```text
sd-ai-command-pack-toolchain.sh doctor [--json]
sd-ai-command-pack-toolchain.sh python [--require-module <name>]...
sd-ai-command-pack-toolchain.sh run-python [--require-module <name>]... -- <args...>
```

- `doctor` reports detected tool versions, selected Python, project-check
  configuration/candidates, and relevant sandbox cache paths. It performs no
  installs or writes.
- `python` writes only the selected executable path to stdout; diagnostics go
  to stderr so command substitution is safe.
- `run-python` validates the interpreter and modules, then `exec`s that
  interpreter once with the supplied arguments.
- Exit `2` means invalid CLI usage, `3` means no supported interpreter, and `4`
  means the selected interpreter lacks required version/modules.

## Python Resolution

Candidate order:

1. `SD_AI_COMMAND_PACK_PYTHON`.
2. `<repo>/.venv/bin/python`.
3. `<repo>/.venv/Scripts/python.exe`.
4. `$VIRTUAL_ENV/bin/python` or `$VIRTUAL_ENV/Scripts/python.exe`.
5. `/opt/homebrew/bin/python3.13` on macOS.
6. `/usr/local/bin/python3.13` on macOS.
7. `python3` from `PATH` when its version meets the pack minimum.

Treat an explicit override or existing repo `.venv` as authoritative. If it
fails validation, report that candidate and stop rather than falling through.
For less-specific system candidates, skip missing executables but never run a
test workload merely to discover whether a candidate works.

The helper's own shell implementation avoids a Python bootstrap dependency.
Version/module probes use short, side-effect-free interpreter commands with
`PYTHONDONTWRITEBYTECODE=1` and temp-backed cache variables when unset.

## Project Check Discovery

`SD_AI_COMMAND_PACK_PROJECT_CHECK_COMMAND` is the only automatically selected
project check. It is repo/user configuration and executes through `bash -c`
from the repository root when a workflow explicitly requests it.

Without the override, `doctor` reports candidates only:

- exact Makefile targets such as `test`, `lint`, `audit`, `check`, and
  `preflight`;
- exact package scripts with those names;
- executable preflight or test helpers already present under `scripts/`.

Discovery uses structured parsing where practical and never parses incidental
README prose. Multiple candidates remain unresolved; the workflow reads repo
instructions and chooses the canonical one. A command whose implementation
invokes `sd-ai-command-pack-full-check.sh` is flagged as recursive and must not
be called from inside that gate.

## Workflow Integration

- `sd-create-pr` and `sd-review-pr` call `doctor` once near their prerequisite
  checks and retain the result for that command run.
- Before an ad hoc Python test, use `run-python --require-module ...` rather
  than trying raw interpreters in sequence.
- Reports list `Project checks`, `Pack full-check`, and `Optional AI review`
  separately so one green lane cannot imply another ran.
- `sd-finish-work` uses the session recorder's `--no-commit` mode when nested
  Git writes are unsuitable, then stages/commits the exact workspace path via
  normal agent Git operations.
- Existing temp-backed cache defaults stay centralized in the shared shell
  library and are reused rather than copied.

Trellis wrappers may recommend the selected interpreter when executing
Trellis scripts, but the pack must not edit or fork Trellis-owned skills.

## Distribution And Ownership

- Source of truth: `sd-ai-command-pack-toolchain.sh` under `templates/scripts/`.
- Root dogfood mirror: the same filename under `scripts/`, synchronized by the
  installer.
- Add the helper to `manifest.json`, installed-target receipts, provenance,
  removal behavior, audit expectations, and docs.
- Update only pack-owned SD skills/adapters whose execution/report contract
  changes.

## Security And Portability

- Keep Bash 3.2 compatibility and quote paths with spaces.
- Do not `eval` helper output or source untrusted repository files.
- Treat `SD_AI_COMMAND_PACK_PROJECT_CHECK_COMMAND` as an explicit trusted local
  command, consistent with existing custom-provider command overrides.
- Never print credentials or environment values unrelated to tool resolution.
- Support Git Bash/WSL-style `.venv/Scripts/python.exe` discovery without
  promising native PowerShell execution for the Bash-based pack gate.

## Testing Strategy

- Shell fixtures provide fake interpreters that record probe/execution counts.
- Assert invalid authoritative candidates stop after one probe and never run
  the requested workload.
- Fixture repositories cover Makefile, package script, executable script,
  ambiguous candidates, recursive full-check candidate, and explicit override.
- Installer/removal tests prove the helper is distributed and audited.
- Skill text tests pin separate reporting for project checks and pack checks.

## Rollback

The helper is additive. If integration causes regressions, revert skill calls
to their prior commands while leaving the helper unused, then remove it in a
follow-up version only after manifest/removal/provenance paths are reconciled.
