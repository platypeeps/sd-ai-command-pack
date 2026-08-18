# Design: close the local bash 3.2 syntax gap

## Decision

Add one dedicated gate, `.github/scripts/check-bash32-syntax.sh`, and run it as
the last step of the `lint` target. `make check` is `test lint audit
full-check` (`Makefile:106`), so the gate runs in the standard local gate
without a new target and without a new CI leg.

## Why not the three options the PRD listed

The PRD's open question offered three homes and asked design to pick one. All
three are rejected, and the reasons are the same class of defect the task
exists to close.

**Pinning the interpreter inside `tests/test_review_scope.py`.** That test walks
*installed* shared scripts — the payload copied into a temporary install root —
not the tracked source set. Pinning its interpreter would validate the shipped
subset with bash 3.2 and leave everything outside the payload (`Makefile`
helpers, `.github/scripts/*.sh`, `.githooks/pre-push`, `installer` shell) still
validated by whatever bash sits on `PATH`. It also buries a platform gate inside
an unrelated assertion, where its output is a test name rather than a named
lane.

**A `.sd-ai-command-pack/check.json` row.** This repository does track its own
`check.json` — one row, `pack.shipped-surface-closure` — so a row here would
run against this source tree. The disqualifier is *when*. `check.json` is read
only by `scripts/sd-ai-command-pack-check.py:29`, the `sd-check` coordinator
invoked by the review and ship flows; `make check` is `test lint audit
full-check` and `scripts/sd-ai-command-pack-full-check.sh` never reads that
file. The incident is precisely a developer running the local gate, seeing exit
0, and pushing. A row that only fires once review has already started does not
close that window, and `make check` is the lane `.githooks/pre-push` points a
failing developer back at (`.githooks/pre-push:117`).

**The review preflight.** Preflight is diff-scoped and advisory by design. A
syntax gate has to be repository-scoped (requirement 2: enumerate from the
filesystem, so an unlisted file cannot hide) and blocking. Advisory findings do
not fail a build, which is the exact complaint the PRD makes about the
documented rule already living in the quality guidelines.

The fourth option — a standalone script in `lint` — is repository-scoped,
blocking, visible as its own line in gate output, and costs no CI leg.

## Interpreter resolution

Candidates come from `SD_AI_COMMAND_PACK_BASH32` when set (space-separated
paths), otherwise from `/bin/bash`, `/usr/bin/bash`, `/usr/local/bin/bash`,
`/opt/homebrew/bin/bash`, and `command -v bash`. Every candidate is
version-probed with `--version` and accepted only when the first line contains
`version 3.2`, so a candidate that happens to sit at a probed path but is bash 5
is skipped rather than silently trusted. This is what makes the gate honest on a
Homebrew machine, where `/opt/homebrew/bin/bash` is 5.x and `/bin/bash` is 3.2.

The environment override exists for the tests: they need to force both the
"interpreter present" and "interpreter absent" branches on a platform that has
only one of them.

Accepted limitation: the candidate list is space-separated and word-split, so an
interpreter path containing a space cannot be passed through
`SD_AI_COMMAND_PACK_BASH32`. Every real candidate path is space-free, and the
alternative (an array, or a delimiter other than whitespace) buys nothing for a
list of absolute interpreter paths.

## Enumeration

`git ls-files -z -- '*.sh' .githooks` at run time, filtered by `is_shell_file`:
a `*.sh` suffix, or a first line matching a `sh` shebang for the extensionless
tracked hooks. Measured on this branch, that is 37 tracked `*.sh` plus
`.githooks/pre-push`, and the gate reports `38 tracked shell scripts accepted`.
A repository-wide shebang scan finds no other tracked shell file outside those
two patterns, so the enumeration is currently complete and stays complete as
scripts are added, because nothing is listed inside the gate.

`is_shell_file` reads the first line into a variable rather than piping `head`
into a matcher: under `set -o pipefail` a reader that exits after one line
turns the pipeline into a failure, which would misclassify large scripts.

## No-bash-3.2 platforms

Linux carries no bash 3.2. The gate prints
`warning: no bash 3.2 interpreter found; skipping bash 3.2 syntax checks (the
macOS CI leg still enforces them).` on stdout and exits 0 — visible, not silent,
satisfying requirement 3. `STRICT=1` turns that same state into an error and
exit 1, matching the existing `STRICT=1 make lint` convention CONTRIBUTING
already documents for missing optional tools.

The residual risk is stated rather than engineered away: a Linux-only developer
gets no local bash 3.2 coverage. The macOS CI leg still fails the push, which is
the status quo for that developer and no worse than before. Requirement 4
forbids buying more than that with a new CI job.

## Validation

`tests/test_generated_parity.py::test_bash32_syntax_gate_rejects_bash32_only_shell`
executes the gate rather than asserting the command was wired in:

1. runs the real gate against this repository and requires exit 0;
2. builds a throwaway git repository containing a fixture with the exact
   construct that caused the incident — an apostrophe in a comment inside a
   `"$( ... )"` substitution;
3. forces the absent-interpreter branch through the environment override and
   requires the visible warning plus exit 0, then the same state under
   `STRICT=1` and requires exit 1 with `STRICT=1` named in stderr;
4. where a real bash 3.2 exists, first proves the gap — the `PATH` bash accepts
   the fixture with exit 0 — then requires the gate to exit 1 naming
   `pack-broken.sh`.

On a platform with no bash 3.2 the rejection half returns early instead of
calling `skipTest`, because CI enforces a no-new-skips rule; the macOS unittest
leg owns that half.

## Rollout and rollback

Additive: one new script, one appended `lint` line, docs. Rollback is removing
the `lint` line; nothing else depends on the gate, and no generated payload or
`manifest.json` version changes, so the fleet ledger is untouched.
