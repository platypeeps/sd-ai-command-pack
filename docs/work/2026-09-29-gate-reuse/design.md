# Design — gate reuse

## One gate, run the same way in both places

Prepare's check ran `sd-check` in the operator's checkout with the operator's
environment. The merge gate ran it in a clean detached worktree with a
scrubbed environment (`bin/sd_local_gate.py`). A pass in the first place is
weaker evidence than a pass in the second, so it could not stand in for it.

Under `repo.ci = local`, prepare now asks `sd-review --gate-check <base>`,
which runs `sd_gate_run.check_in_worktree` through `sd-review`'s own
process-group runner (sd:1482). Both lanes now produce the same evidence. A
repository under `repo.ci = github` runs prepare's check as before.

The run moved out of `sd_local_gate` into `bin/sd_gate_run.py`, and the
status post stayed behind. So `sd-review`, which must never post, imports the
run and not the post. The review lane's line cap rises by the moved module;
`tests/test_sd_review_boundary.py` records the measurement.

## Decision: what binds a reusable gate receipt

The existing `--reuse-check` receipts claim hermeticity: a tracked
declaration asserts every input and no network. The pack cannot make that
claim for its own gate (sd:1296), and most repositories cannot either. Gate
receipts claim less, and say so:

| Bound | Why |
|---|---|
| head and tree | the exact commit the worktree held |
| `gate_inputs` digest | every pack `bin/` file and an untracked `CLAUDE.local.md`; a pack upgrade reruns |
| scope and its merge base | a docs-only pass is not a full pass |
| detected commands and source | a changed entrypoint is a different check |
| each command's executable, by path and bytes | a new `make` or `cargo` is a different check |
| interpreter path, version and bytes | `sd-check` itself runs on it |
| the gate's `PATH` value | a different tool set on `PATH` |
| age of at most 12 hours | bounds what the rest cannot name |

Not bound: a tool a Makefile reaches through another tool, network answers,
other environment variables, and machine load. The gate is a self-hosted
runner, not a hermetic build, and its docstring already says so. The receipt
therefore claims: this machine's gate passed this commit with these inputs,
recently. That is the claim a CI system makes when it reads a green check on
a head.

Conservative choices, flagged for the operator:

- **12-hour age limit.** A prepare and its merge are minutes to hours apart.
  A longer limit saves nothing observed; a shorter one may rerun a slow merge.
- **Only successes are recorded.** A failure always reruns.
- **Every fault means no receipt.** No library, no database, an unreadable
  row, or an unresolvable tool runs the check.
- **Other environment variables are not bound.** Binding the whole
  environment would never match between two sessions. `PATH` is bound because
  it chooses the tools.

## Decision: prepare's gate bound

`sd-review --timeout` bounded both the gate and each reviewer. With no
`--timeout`, the gate now gets `sd_lib.GATE_CHECK_SECONDS` (3600, the merge
gate's own) and each reviewer keeps 1800. An explicit `--timeout`, forwarded
from `--review-timeout`, still bounds both, as sd:1475 designed. The timing
plan gains `check_seconds`, and the watchdog total is setup plus the gate
plus one phase per candidate. `sd-ship` still accepts a plan without the key.

## Decision: the gate slot

`sd-check` has taken the sd:1996 slot since that change, so a gate prepare
starts is capped wherever `sd-check` runs. This change adds no slot of its
own. A reused receipt runs no check and takes no slot. A test shows prepare's
gate taking a slot from the shared directory.

## Docs-only scope

The declaration is `.github/sd-check-scope.json` in the reviewed tree, so a
change to it is itself reviewed. It holds `docs_paths` globs and a
`docs_command` argv. `sd-check --base REF` diffs merge-base to HEAD with
`--no-renames`, so a rename shows both sides. The full check runs when:

- no declaration, no `--base`, no merge base, or an empty range;
- any path is not a docs path;
- any path decides what the check is: the declaration, a Makefile or `*.mk`,
  the entrypoint's source file, `CLAUDE.local.md`, or a file a check command
  or the docs command names in its argv.

"Check scripts" is read as the last item. A script a Makefile calls
indirectly is not detected; a repository whose docs globs could match such a
script must keep its globs narrow. The pack does not declare a scope in this
change: its `skills/**` Markdown is tested payload, and a narrow enough glob
set saves little.
