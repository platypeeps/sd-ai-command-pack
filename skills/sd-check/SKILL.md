---
name: sd-check
description: Run this repository's own check, test and lint entrypoints and report one typed result each.
disable-model-invocation: true
---

# sd-check

`bin/sd-check` owns no checks. It asks `sd_lib.detect_entrypoints` how *this*
repository spells `check`, `test` and `lint`, runs what it found, and reports
one typed result per name. Use it instead of guessing at `make test` or
`npm run lint`.

## Detection order

The `CLAUDE.local.md` marked block first if it names entrypoints, otherwise the
first of `Makefile`, `Taskfile`, `package.json`, `Cargo.toml`, `pyproject.toml`
that yields any. Detection is a library function with its own tests — do not
re-derive it, and do not "helpfully" run a command sd-check reported as
`absent`.

## The four statuses

| Status | Meaning |
|---|---|
| `pass` | ran, exited 0 |
| `fail` | ran and exited non-zero, **or timed out** |
| `skipped` | the entrypoint exists but this run deliberately did not use it |
| `absent` | this repository has no such entrypoint |

Only `fail` is a failure. **`absent` is not `skipped`, and neither is a
failure** — a repository with no lint target is not a repository that failed
lint. Do not report a run as incomplete because something came back `absent`.

The aggregate rule: when the repo defines its own `check`, `test` and `lint`
come back `skipped` with reason `covered by the check entrypoint`. That is
correct, not a gap. `--only lint` still runs one on demand.

## Flags

| Flag | Effect |
|---|---|
| `--json` | one machine-readable object (`schema` 1) |
| `--dry-run` | print what would run, exit 0 without running it |
| `--only NAME` | run exactly one of `check`, `test`, `lint` |
| `--timeout SECONDS` | per-check timeout, default 900; a timeout is a `fail` |
| `--repo PATH` | a directory *inside* the current repo (default: cwd) |

## Exit codes

`0` nothing failed · `1` a check failed · `2` the invocation or the
configuration was wrong (one sentence on stderr, never a traceback).

## Never

- **Never point `--repo` at another checkout.** It exists as a locator for a
  subdirectory of the repo you are standing in; sessions stick to their repos
  (R10-D6). If you need another repo's status, `cd` there in a session that
  belongs there.
- **Never treat sd-check as a gate you can wave through.** `sd-review` runs it
  first, and a failing deterministic gate is a failing review: no model is
  asked to guess at a change that does not build.
- **Never let sd-check write.** It changes no git state, makes no network call,
  and stores nothing. Whatever the repo's own check command does is the repo's
  business — if that command commits or pushes, that is the repo's bug, not
  sd-check's contract.
- **Never substitute a hand-rolled command for a `fail` you did not like.**
  Fix the repo's entrypoint or report the failure.

## Reading the output

Output is captured and attributed per check, never interleaved, and tails at
4,000 characters with a truncation marker. When reporting to the user, quote
the shortest decisive line of that tail rather than the whole block.
