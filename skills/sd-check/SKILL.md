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

## Exit codes

`0` nothing failed · `1` a check failed · `2` the invocation or the
configuration was wrong (one sentence on stderr, never a traceback).

## Never

- **Never try to point sd-check at another checkout.** There is no `--repo` and
  there will not be one (R10-D6): the repository is resolved from the working
  directory and nowhere else, and `tests/test_verb_inventory.py` enumerates
  `bin/` to keep it that way. If you need another repo's result, `cd` there in a
  session that belongs there.
- **Never treat sd-check as a gate you can wave through.** `sd-review` runs it
  first, and a failing deterministic gate is a failing review: no model is
  asked to guess at a change that does not build.
- **Never let sd-check write.** It changes no git state, makes no network call,
  and stores nothing. Whatever the repo's own check command does is the repo's
  business — if that command commits or pushes, that is the repo's bug, not
  sd-check's contract.
- **Never substitute a hand-rolled command for a `fail` you did not like.**
  Fix the repo's entrypoint or report the failure.

## Code health

The registry's code rules are enforced by the tests their rows name, not by
sd-check; sd-check meets them as one more red result from the repository's
own `test` entrypoint. They are cited here because this is the skill an author
has open when that result arrives. Four are `tests/test_code_health.py`'s —
three per-function ceilings and a rule over pairs, each with a baseline that
may shrink and may not grow — and one is about where a file may live:

- R12-D1 — complexity, `COMPLEXITY_CEILING`, on the cyclomatic score.
- R12-D2 — length, `LENGTH_CEILING`, in unparsed statements.
- R12-D3 — depth, `DEPTH_CEILING`, in indented blocks.
- R12-D4 — duplication: two functions of one shape, once each is at least
  `CLONE_FLOOR` AST nodes.
- R11-D6 — shell placement: where a file with a shell suffix or shebang may
  live, held by `tests/test_no_shipped_shell.py`.

The rows in `bin/sd_rules.py` state each number and the one directory; none
is restated here.
`bin/sd-rules --for <path>` prints the rows in scope for the file being
written.

## Prose rules

The registry's prose rules are enforced by the suites their rows name, not by
sd-check; as with the code rules above, an author meets them as a red result
from the repository's own `test` entrypoint. Each is a per-document baseline
that may shrink and may not grow, so the first run swept nothing and every
new violation is red on the day it is written:

- R13-D1 — a citation into code names the symbol, `source:<path>::<symbol>`,
  where the line it would name sits inside one.
- R13-D2 — a count of something the tree enumerates is derived, or carries
  the commit, pull request number or date it was measured at.
- R13-D3 — a claim about what a pack tool or a test does cites a rule id on
  the same line.

The rows in `bin/sd_rules.py` state what each rule exempts; it is not
restated here. `bin/sd-rules --for <path>` prints the rows in scope for the
page being written.

## Reading the output

Output is captured and attributed per check, never interleaved, and tails at
4,000 characters with a truncation marker. When reporting to the user, quote
the shortest decisive line of that tail rather than the whole block.
