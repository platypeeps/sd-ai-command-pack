---
title: Harden audit read-only methods and path handling
status: done
created: 2026-07-24
---
# Harden audit read-only methods and path handling

## Goal

Resolve review findings `1.4.1.1` and `1.4.1.2` by removing checkout-code
execution from read-only audit charters and making tracked-file analysis safe
for every valid tracked filename.

## Confirmed Evidence

- `templates/.agents/skills/sd-audit-repo/charters/tooling.md:48-63`
  promises read-only probes but recommends `make -n` and arbitrary `--help`
  execution. Make expansion, recursive make, and script help handlers can have
  side effects before the audit can stop.
- `templates/.agents/skills/sd-audit-repo/charters/architecture.md:50-59`
  uses a newline/whitespace-delimited `git ls-files | xargs wc -l` pipeline that
  misparses spaces, newlines, option-like names, and empty input.
- The generated checkout-trust preflight prevents untrusted-fork execution, but
  trust is not authorization for mutation during a read-only audit.

## Dependencies And Boundaries

- Parent: `07-24-correct-sd-skill-contract-drift`.
- Preserve the formal audit's architecture and tooling coverage, severity
  schema, charter routing, and finding output contract.
- Change canonical templates first and synchronize generated/dogfood mirrors.
- No upstream Trellis change is required.

## Requirements

- R1: A read-only audit method may statically inspect command definitions,
  Makefiles, workflow steps, scripts, and documentation but must not execute a
  repository target or script merely to see whether it resolves or prints help.
- R2: Remove `make -n`, arbitrary `--help`, and equivalent checkout-code probes
  from the tooling charter. Do not replace them with another execution-shaped
  command presented as read-only.
- R3: Replace the architecture filename pipeline with a portable deterministic
  method that preserves spaces, tabs, newlines, leading option characters, and
  an empty tracked-file set. Prefer an existing safe helper or a small tested
  pack-owned helper over fragile shell quoting.
- R4: Keep externally controlled paths bounded and never interpret a filename as
  a command option, response-file reference, or path outside the repository.
- R5: Add behavioral fixtures for side-effecting Make expansion/help handlers
  and hostile valid filenames. Tests must prove the dangerous code was not run,
  not merely that the audit eventually reported failure.
- R6: Keep source templates, root mirrors, manifest/provenance data, audit tests,
  and documentation synchronized.

## Acceptance Criteria

- [ ] No live audit charter instructs a read-only reviewer to execute
  checkout-owned targets, scripts, hooks, package tasks, or help handlers.
- [ ] A fixture containing side-effecting `$(shell ...)`, recursive make, and a
  writing `--help` handler completes the audit-method test with zero marker files
  and zero network/provider invocation.
- [ ] Architecture inventory tests handle filenames with spaces, tabs, newlines,
  leading dashes, and an empty repository without splitting or option parsing.
- [ ] The replacement still identifies the largest tracked components and
  preserves the existing finding schema.
- [ ] Focused audit tests, template/root parity, `make sync`, and `make check`
  pass.

## Out Of Scope

- Running repository code in a sandbox as a default substitute for static
  inspection.
- Weakening the generated untrusted-checkout preflight.
- Changing which audit dimensions are selected.

## Notes

- This task removes unsafe methods; it does not preserve them behind a legacy
  flag or compatibility mode.
