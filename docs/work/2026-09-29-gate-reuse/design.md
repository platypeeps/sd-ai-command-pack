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
| the gate's whole environment, every variable by name and value | the gate forwards it whole; `MAKEFLAGS` or `PATH` can choose what runs |
| one prepare-to-merge handoff, at most 30 minutes old | bounds what the rest cannot name |

## Trust boundary

Inputs outside the repository are not bound: an external makefile an unchanged
`MAKEFILES` names, a file a tool reads, a tool a Makefile reaches through
another tool, network answers and machine state. Review showed the case: keep
`MAKEFILES=/external/rules.mk`, change that file from a passing recipe to a
failing one, and the binding stays equal. The gate is a self-hosted runner,
not a hermetic build, so it cannot bind them.

The operator's decision (2026-09-29) is to narrow the window, not to widen the
binding. A receipt serves exactly one handoff: prepare records it, and the
merge gate of the same head on this machine reads it within
`REUSE_WINDOW_SECONDS` (30 minutes). Prepare never reads a receipt, and the
merge gate never writes one. A change outside the repository inside that
window is the accepted residual risk. A repository that needs more uses the
explicit dependency contract, `sd-check --record-receipt` with a declared
inventory; sd:1912 stays open for that.

The receipt therefore claims: this machine's gate passed this commit with
these inputs minutes ago.

Conservative choices, flagged for the operator:

- **30-minute window, one handoff.** The first cut allowed 12 hours and any
  later gate. That bounded nothing a reviewer could check, so the window is
  now the prepare-to-merge handoff alone; a merge started later runs the
  check.
- **Only successes are recorded.** A failure always reruns.
- **Every fault means no receipt.** No library, no database, an unreadable
  row, or an unresolvable tool runs the check.
- **The whole environment is bound.** The first cut bound `PATH` only, on
  the view that the whole environment would rarely match between two
  sessions. Review showed the hole: prepare with a `MAKEFLAGS` that made the
  check pass left a receipt a merge without it reused, though the real check
  failed there. Any forwarded variable can choose what runs, so the binding
  is `sd_gate_run.gate_environment`'s whole output. The cost is reuse: a
  prepare and a merge from shells that differ in any variable run twice.

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

## Log

- 2026-10-03, sd:1912: operator ruling D1 (relayed by the lead) drops the agent
  harness's session variables (`CLAUDE*`, `HERDR_*`, `ITERM_*`,
  `TERM_SESSION_ID`, `PWD`, `OLDPWD`, `SHLVL`, `_`) from the gate child's
  environment. The binding is still the whole environment the child sees. With
  D1 a builder's pass and the lead's prepare bind equal, so prepare now reads a
  receipt at the same head and binding. That read is no weaker than the merge
  gate's read of the same receipt. The 30-minute window is unchanged (ruling
  D2), and it counts from the run that passed. "Prepare never reads a receipt"
  above no longer holds. `sd gate check` records a builder's pass; using it is
  optional (ruling D3).
- 2026-10-03, sd:1912 slice A: a repository may key gate receipts by tree
  instead of head, through `.github/sd-gate-reuse.json` (`{"schema_version": 1,
  "key": "tree", "reason": ...}`). The key, the binding and the `gate_inputs`
  digest then name `HEAD^{tree}` and the merge base with the base branch, not
  the head. Opt-in, because two heads with one tree differ in commit metadata,
  and a commit-message lint or a `git describe` stamp can pass at one and fail
  at the other. The merge base is bound because a check may read an old commit
  by name; a run with no base keeps the head key. The receipt row keeps the
  passing head, and a reuse reports it as `reused.head`. Ruling D2': a
  tree-keyed receipt stands for 6 hours (`TREE_REUSE_WINDOW_SECONDS`); the head
  key keeps 30 minutes. Ruling D4: no. The pack does not declare the key. Its
  `make check` reads commit trailers and ranges: `tests/test_sd_review.py` runs
  `sd-review --explain` at the checkout root, which reads the branch range's
  `Authored-with:` trailers; `tests/test_sd_size_report.py` renders "this
  change" and the last 30 days from the log; `tests/test_archive_untouched.py`
  reads the commit that added `docs/work/.status-source`.
- 2026-10-04, sd:2602: the merge gate already read prepare's receipt (sd:2041),
  yet on 2026-10-03 every merge gate ran in full, most beside a prepare receipt
  for the same head made minutes before. Cause: the installed pack sat at
  `929b34cd` from 11:16 to 19:06 MDT and lacked `e2930c27` (ruling D1), so
  `PWD`, `SHLVL`, `_` and `CLAUDE_*` still bound and differed between the
  shells that ran prepare and merge. The first merge after the install of
  `2ca892be` reused. A gate that runs in full now returns `reuse_miss`, the
  reason no receipt stood, beside its result. Operator ruling (2026-10-04,
  "drop it"), an addition to D1: `FNM_MULTISHELL_PATH` is dropped too, and each
  kept `PATH` entry is resolved, so fnm's per-shell folder that leads to the
  same real node binds the same receipt; a different real node still differs.
  Tool paths in the binding were already resolved (`tool_identity`).
