# Design: read-only `sd-check`

## Summary

Add one installed Python coordinator, `scripts/sd-ai-command-pack-check.py`,
and one generated `sd-check` command family. The coordinator owns deterministic
verification and emits the same schema-version-1 result for human, skill, local
pre-publication, and CI callers. It does not call the legacy full-check script,
provider runners, GitHub review dispatch, or any refresh command.

The predecessor remains installed only until
`07-24-remove-retired-review-surfaces` removes its complete footprint. It is not
an alias, implementation fallback, configuration reader, or dependency of the
new command.

## Public Interface

The stable executable interface is:

```text
python3 scripts/sd-ai-command-pack-check.py [--json]
    [--repo PATH] [--config PATH]
```

- `--repo` is an internal/testing convenience and must resolve to a Git
  worktree. The default is the current worktree root.
- `--config` defaults to `.sd-ai-command-pack/check.json` below that root. An
  explicit path must resolve to that same canonical default; it cannot select
  an external or alternate policy file.
- Human output is a concise rendering of the JSON result. `--json` emits
  exactly one JSON document.
- Exit `0` means every executed required check passed. Exit `1` means a check
  failed or the final state guard found mutation. Exit `2` means configuration
  or repository state is invalid. Exit `3` means the result is unavailable or
  indeterminate without a deterministic failure verdict.

The shared skill runs the coordinator through the installed sibling toolchain
and consumes JSON. Generated platform adapters only resolve that skill and
state the no-mutation boundary.

## Configuration Contract

`.sd-ai-command-pack/check.json` is strict schema version 1:

```json
{
  "schemaVersion": 1,
  "prerequisites": [
    {
      "id": "tooling",
      "argv": ["python3", "scripts/check-tooling.py"],
      "cwd": ".",
      "timeoutSeconds": 120
    }
  ],
  "checks": [
    {
      "id": "unit",
      "argv": ["python3", "-m", "unittest", "discover", "-s", "tests"],
      "cwd": ".",
      "timeoutSeconds": 900
    }
  ]
}
```

The object is closed. IDs are unique safe identifiers. `argv` is a non-empty,
bounded array of bounded strings with no NUL/control characters; shell strings
are never accepted or evaluated. `cwd` is a bounded repository-relative path
that resolves to a real directory inside the worktree without a symlink escape.
Timeouts are positive integers with a documented upper bound. Unknown schema
versions, fields, invalid UTF-8, oversized files, escaped paths, duplicate IDs,
malformed argv, or unbounded timeouts fail before any configured command runs.

Prerequisites use the same executable contract as checks. A failed,
unavailable, or indeterminate prerequisite skips later configured checks with
an explicit blocking reason. Declared checks are required; missing executables
are `unavailable`, not successful skips.

## Built-In Checks

The coordinator has a small closed built-in inventory:

1. unstaged and staged `git diff --check`;
2. deterministic review preflight through its required shipped helper;
3. installed-payload audit through its required shipped helper;
4. Obsidian KB freshness through the helper's existing `--check` mode only
   when `.obsidian-kb` exists;
5. tooling/generated and PR-body scope checks through their required shipped
   helpers; and
6. configured prerequisites and checks.

Additional repository-specific gates, including source-pack drift, generated
surface, map, CI-classification, and finish-work validation, are argv entries
or separately registered read-only helpers. The coordinator never infers
package scripts, executes `package.json` `check:full`, accepts environment
command strings, or discovers commands by filename convention.

The child task `07-24-validate-shipped-surface-closure` adds the authoritative
registry-derived surface helper to this same typed inventory. Until then,
existing orthogonal parity tests remain authoritative and are not duplicated
inside the coordinator.

## Result Contract

Schema version 1 contains:

- command/schema identity and repository-relative configuration identity;
- full HEAD OID when available and clean/dirty observation;
- ordered result rows with stable ID, kind, status, exit code, bounded command
  identity, duration, diagnostic, and remediation;
- `passed`, `failed`, `skipped`, `unavailable`, `invalid`, and
`indeterminate` counts;
- before/after state-guard identity and mutation findings; and
- one aggregate status and exit code derived from fixed precedence.

Rows are ordered by built-in inventory, then configuration order. JSON keys and
finding lists are stable and diagnostics are size/control bounded. The report
does not include credentials, inherited environment values, command output
beyond bounded diagnostics, or absolute cache paths.

Aggregate precedence is `invalid`, `failed`, `indeterminate`, `unavailable`,
then `passed`. `skipped` is never a clean substitute for a declared required
check or missing shipped helper. Optional built-ins that are not applicable,
such as an absent KB, may report `skipped` without blocking an otherwise
passing aggregate.

## Read-Only And Cache Boundary

Every subprocess receives the shared sandbox-safe tool environment from
`sd_ai_command_pack_lib.py`; authentication-related variables remain inherited
and cache variables point to validated private locations outside the worktree.
No command is launched when cache setup cannot satisfy that boundary.

Before execution, the coordinator records:

- HEAD, symbolic HEAD, refs, and index identity;
- tracked and non-ignored untracked content identity; and
- ignored pack-owned/generated knowledge identities for `.obsidian-kb/`,
  `.sd-ai-command-pack/`, and known repository-map outputs.

It records the same state after execution. Any delta becomes a failing
`state-guard` row naming the changed class; the coordinator never repairs,
reverts, stages, deletes, or refreshes the changed path. Built-in and fixture
tests prove all pack-owned lanes preserve the snapshot. Config documentation
requires project commands to be read-only; the guard detects violations but is
not authority to undo user or tool output.

## Caller And Migration Boundary

- `sd-review-pr` uses the JSON coordinator instead of the legacy
  review-full-check selector while that command still exists.
- `sd-create-pr`, `sd-ship`, and `sd-work-backlog` continue to compose their
  owning workflow but refer to the typed `sd-check` result instead of prose
  reconstruction or `check:full` discovery.
- The upcoming unified `sd-review` task consumes this result contract directly.
- CI/local-prepublication share the same executable; the surface-closure child
  removes remaining parallel checker inventories.

## Failure And Rollback

Malformed configuration, unsafe paths, cache setup failure, missing required
tools, timeout, signal/launch failure, or mutation evidence is explicit and
never normalized to pass. Raw outputs stay bounded in memory and are not
written under the repository.

Rollback removes the new registry row, script, skill, generated adapters, and
manifest entries before release. It does not reactivate a hidden alias. After
release, rollback reinstalls the last pre-cut pack version as defined by the
parent program.
