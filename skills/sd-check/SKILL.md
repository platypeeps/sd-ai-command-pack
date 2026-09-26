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
| `--record-receipt` | Explicitly record eligible full-check evidence in the shared database. |
| `--database PATH` | Select the receipt database; valid only with `--record-receipt`. |

## Optional check receipts

Default invocations store nothing.
Use `--record-receipt` only for a proven complete, local-only check in a clean committed checkout.
The dependency declaration must be tracked at `.github/sd-check-reuse.json`.
Before recording or reusing evidence, read `skills/sd-check/references/check-receipts.md` in the sd-ai-command-pack checkout.
It defines the declaration, controlled environment, identity bindings, and refusal conditions.
Do not combine receipt recording with `--only` or `--dry-run`.
Recording a receipt does not enable reuse automatically.

The declaration is an operator assertion, not proof of arbitrary command hermeticity or filesystem isolation.
Do not enable reuse when the check depends on undeclared ignored files, network access, environment, or external dependencies.
Unknown dependencies mean run the check normally.

## Exit codes

`0` nothing failed; `1` a check or receipt-storage operation failed; `2` invocation or configuration was invalid.
Receipt-storage failure reports `receipt_error` and provides no reusable receipt, even when the underlying checks passed.

## Never

- **Never try to point sd-check at another checkout.** There is no `--repo` and
  there will not be one (R10-D6): the repository is resolved from the working
  directory and nowhere else, and `tests/test_verb_inventory.py` enumerates
  `bin/` to keep it that way. If you need another repo's result, `cd` there in a
  session that belongs there.
- **Never treat sd-check as a gate you can wave through.** `sd-review` runs it
  first, and a failing deterministic gate is a failing review: no model is
  asked to guess at a change that does not build.
- Keep wrapper effects separate from repository check effects.
  The wrapper changes no Git state and makes no network calls itself.
  Default execution stores nothing; explicit receipt recording permits only its shared-database checkpoint writes.
  Repository commands can have their own effects; receipt recording does not authorize unrelated writes or transmission.
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
`sd-rules --for <path>` prints the rows in scope for the file being
written.

## Prose rules

The suites named by each registry row enforce the prose rules.
The full suite makes each new violation red.
The changed-file selector currently omits `tests.test_prose_counts` for
the pack's `.claude/rules/sd-planning-adversarial-review.md`.
Each rule uses a per-document baseline that can shrink but cannot grow:

- R13-D1 — a citation into code names the symbol, `source:<path>::<symbol>`,
  or the file alone; every `path:line` into code counts.
- R13-D2 — a count of something the tree enumerates is derived, or carries
  the commit, pull request number or date it was measured at.
- R13-D3 — a claim about what a pack tool or a test does cites a rule id on
  the same line.

The rows in `bin/sd_rules.py` state what each rule exempts; it is not
restated here. `sd-rules --for <path>` prints the rows in scope for the
page being written.

## Reading the output

Output is captured and attributed per check, never interleaved, and tails at
4,000 characters with a truncation marker. When reporting to the user, quote
the shortest decisive line of that tail rather than the whole block.
