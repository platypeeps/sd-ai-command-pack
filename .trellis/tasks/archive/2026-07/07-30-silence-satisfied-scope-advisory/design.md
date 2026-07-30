# Design: silence the satisfied scope advisory

## Shape of the change

`check_pr_body_scope` currently interleaves two jobs: resolving the PR body, and
deciding what a missing section means. Advisory mode needs the first without the
second. Split them.

### New helper: `resolve_pr_body_scope_state`

Pure resolution. Writes exactly one state token to stdout and warns nothing,
fails nothing. It is *built* so that it cannot exit nonzero — see "The helper
must not be able to exit" below — but its callers do not assume that, which is
why `unknown:resolver_error` exists:

| Token                   | Meaning                                                     |
| ----------------------- | ----------------------------------------------------------- |
| `satisfied`             | a body was resolved and matches a recognized scope heading    |
| `unsatisfied:provided`  | `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` set, body lacks the section |
| `unsatisfied:resolved`  | body fetched from `gh`, lacks the section                     |
| `unknown:gh_disabled`   | `SD_AI_COMMAND_PACK_SCOPE_CHECK_GH` disabled                  |
| `unknown:gh_missing`    | `gh` not on `PATH`                                            |
| `unknown:no_pr`         | `gh pr view` could not resolve a PR                           |
| `unknown:no_parser`     | neither `python3` nor `jq` available to parse the body        |
| `unknown:parse_error`   | a parser ran on `gh` output and exited nonzero                |
| `unknown:resolver_error`| the resolver produced no token at all                         |

### Resolution order, and the one deliberate reordering

The existing order is: gh-disabled, then the explicit body env, then gh
presence, then `gh pr view`, then parser choice. One step moves — a
`SD_AI_COMMAND_PACK_SCOPE_PR_BODY` that *matches* is evaluated above the
gh-disabled short-circuit:

1. explicit body env set **and** matching → `satisfied`
2. `is_disabled "$GH_MODE"` → `unknown:gh_disabled`
3. explicit body env set (necessarily not matching) → `unsatisfied:provided`
4. …the remaining steps in their existing order.

Without this, `SD_AI_COMMAND_PACK_SCOPE_CHECK_GH=0` plus a satisfying body
resolves to `unknown:gh_disabled`, and the advisory warns while holding positive
evidence in hand — a direct contradiction of the first requirement in prd.md.

The reordering is invisible to enforcing mode, which is why it is safe. Each of
the four input combinations produces the same enforcing outcome as today:

| gh mode  | body env       | today                | after                          |
| -------- | -------------- | -------------------- | ------------------------------ |
| disabled | matches        | return 0 (step 2)    | `satisfied` → return 0         |
| disabled | does not match | return 0 (step 2)    | `unknown:gh_disabled` → return 0 |
| enabled  | matches        | return 0             | `satisfied` → return 0         |
| enabled  | does not match | `fail`               | `unsatisfied:provided` → `fail` |

Only the reporting is otherwise lifted out.

### The helper must not be able to exit

`fail` at `sd-ai-command-pack-review-scope.sh:19-22` calls `exit 1`, and the
script runs under `set -euo pipefail`. Today the advisory branch returns before
any of that machinery; moving resolution into it imports every one of those exit
paths. Three rules keep the helper inert:

- the helper never calls `fail`, and never calls `warn` — it only prints a token;
- every subprocess is guarded (`if ! out="$(cmd)"`), so a crashing `python3`,
  `jq`, or `gh` yields a token rather than a nonzero status;
- *both* callers capture defensively — `state="$(resolve_pr_body_scope_state || true)"`
  — and treat an empty capture as `unknown:resolver_error`. The advisory caller
  warns on it like any other unknown; the mapper fails on it. Writing the `|| true`
  in only one caller would leave the other exposed to the `set -e` abort the rules
  above exist to prevent, and would make the mapper's `resolver_error` arm dead
  code that can never be reached.

Mitigating evidence, not a substitute for the rules above: `checkScopeAdvisory`
in `sd-ai-command-pack-review-preflight.mjs:3479-3488` inspects only
`result.error` (a spawn failure) and never `result.status`, so a nonzero exit
from this script cannot fail the preflight gate. Direct advisory invocations have
no such caller, which is why the helper is built not to exit in the first place.

### `check_pr_body_scope` becomes a mapper

It calls the helper and reproduces today's behavior exactly:

- `satisfied` → return 0
- `unsatisfied:*` → `fail` with the existing message for that variant (the
  provided-body message and the resolved-body message are distinct today and
  stay distinct)
- `unknown:gh_disabled` → return 0 silently, as today
- `unknown:gh_missing` → `fail` if `is_required "$GH_MODE"`, else warn and
  return 0
- `unknown:no_pr` → `fail` if required, else warn and return 0
- `unknown:no_parser` → `fail` if required, else warn and return 0
- `unknown:parse_error` → `fail`
- `unknown:resolver_error` → `fail`

The `scoped_count -eq 0` early return stays at the top of `check_pr_body_scope`,
before any resolution, so the zero-scope path still never touches `gh`.

`unknown:parse_error` is the one enforcing-visible delta in the whole change.
The parser assignments at `sd-ai-command-pack-review-scope.sh:212-216` are
unguarded today, so a `gh` call that succeeds but returns malformed JSON aborts
the script through `set -e` with the interpreter's own stderr and no `error:`
line. After the split it becomes a `fail` with a named message. The exit status
is 1 either way, and no other input changes. This is declared rather than
hidden, because prd.md otherwise requires enforcing mode to be byte-identical.

In advisory mode the same token warns like every other `unknown`, which is what
prd.md's "a malformed response must not fail the gate" requires.

`unknown:resolver_error` is deliberately *not* a second declared delta. The three
inertness rules make it unreachable; it exists only so that a future edit which
breaks one of those rules degrades to a named failure instead of an unexplained
`set -e` abort. If a test can construct an input that produces it, one of the
rules has been violated and the bug is there, not in the mapper.

### Advisory branch consumes the same helper

```
satisfied     → return 0, print nothing
unsatisfied:* → warn "<PR exists, body lacks section>" + marker, return 0
unknown:*     → warn "<existing pre-PR wording>" + marker, return 0
```

Advisory never fails, never consults `GH_MODE` requiredness. `is_required` is an
enforcing-mode concept; an advisory that could fail would violate its contract
with `checkScopeAdvisory`, which treats this script as non-fatal.

## Why "unknown warns" is the right default

The advisory is a reminder, and a reminder is only harmful when it is wrong.
Staying silent on `unknown` would mean an offline author, or one without `gh`,
silently loses the reminder they most need — they cannot check the PR body
themselves either. Warning on `unknown` costs one line in a case where the
author genuinely has nothing proving the body is fine.

## Cost

Advisory mode gains one `gh pr view` per invocation on branches that touch a
tooling/generated file. This is the property being traded, and it is bounded:

- branches with no scoped change return at the existing line 277 and never
  reach the helper;
- `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` short-circuits before `gh`;
- a missing or disabled `gh` short-circuits before the subprocess;
- `SD_AI_COMMAND_PACK_SCOPE_CHECK=off` skips the whole script, and
  `checkScopeAdvisory` already honors that env before spawning.

`gh pr view` already runs on the enforcing path in the same situations:
`run_sd_ai_command_pack_scope_check` in
`templates/scripts/sd-ai-command-pack-full-check.sh:457-465` invokes the script
with no `SD_AI_COMMAND_PACK_SCOPE_CHECK` override, so `MODE=auto` reaches
`check_pr_body_scope` on every `make check` already. The worst case is therefore
one additional call per `make check` on a scoped branch, not a new class of
dependency.

### Latency must be bounded, not just non-fatal

Count is not the whole story. Neither call has a timeout today
(`sd-ai-command-pack-review-scope.sh:200`), and the advisory path is fully
synchronous down its whole length: `make check` runs full-check (`Makefile:91`),
full-check runs the preflight with no timeout
(`sd-ai-command-pack-full-check.sh:1000`), and `checkScopeAdvisory` uses
`spawnSync` with no `timeout` option (`sd-ai-command-pack-review-preflight.mjs:3479`).
Tolerating a nonzero exit only helps once the child returns. A stalled `gh`
would therefore stall `make check` indefinitely — a new failure mode, because
today advisory mode never launches `gh` at all.

Fix it at the caller: pass `timeout` (10s) and `killSignal: 'SIGKILL'` to that
`spawnSync`. On expiry, `result.error` is set, the existing guard returns, and
the advisory is simply absent for that run — exactly the degradation the
function already documents for a spawn failure.

The timeout is closed by inspection, not by a regression test, and that is a
decision rather than an omission. A behavioral test needs a stub `gh` that
outlives the bound, which costs the full 10s of suite time; making it fast
requires exposing the bound as an environment variable, which adds a documented
knob to the shipped payload — a larger permanent surface than the guard it would
cover. What is left untested is `spawnSync` setting `result.error` on expiry,
which is Node's documented contract, not this project's logic. The reviewable
artifact is the two options on the call and the existing `result.error` guard
above them.

The bound goes in `checkScopeAdvisory` rather than in the shell script on
purpose. A shell-side timeout would need `timeout(1)`, which is absent from
macOS by default, and it would sit on the enforcing path too, where a hard
failure is the intended behavior and where this task must change nothing.
Bounding the Node caller touches only the advisory invocation.

## Which file the documentation edit targets

`templates/docs/SD_AI_COMMAND_PACK.md` is the source; `docs/SD_AI_COMMAND_PACK.md`
is its generated mirror (`diff -q` reports them identical, and `make sync`
rewrites the root copy). `tests/test_review_scope.py:249-257` asserts scope
content in *both* paths, so an edit made only to the root copy is silently
reverted by the `make sync` that follows it.

## Rejected alternatives

- **Downgrade `warning:` to `info:`.** Cheapest, no new failure modes, but it
  only hides the symptom: the reminder still prints after the body is correct,
  and the author still cannot tell a satisfied branch from an unsatisfied one.
- **Have `review-preflight.mjs` resolve the body and pass it in.** Moves the
  cost to the caller and keeps the script offline, but splits the scope policy
  across two languages and leaves every other caller of the script with the old
  unconditional warning. The bash script already owns all heading policy; the
  resolution belongs next to it.

## Compatibility

- No environment variable is added, removed, or repurposed.
- No exit status changes on any enforcing input.
- The advisory marker string is unchanged, so `checkScopeAdvisory` needs no
  parsing change. It is still edited, but only to add the `spawnSync` timeout and
  to correct its now-stale header comment
  (`sd-ai-command-pack-review-preflight.mjs:3467-3470`), which describes the
  advisory as firing "before any PR exists". Nothing in its marker matching, its
  `off` short-circuit at :3471-3474, or its warning emission changes.
- The only observable advisory-mode change is silence in the satisfied case and
  reworded text in the PR-exists-but-unsatisfied case.

## Test strategy

Extend `tests/test_review_scope.py`, whose harness builds a temp repo and runs
the installed script with a controlled environment.

Cases 1-3 drive `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` or `..._GH`, so they never
reach `gh`:

1. advisory + scoped change + body with section → exit 0, no `warning:`, no
   marker.
2. advisory + scoped change + body without section → exit 0, marker present,
   PR-exists wording.
3. advisory + scoped change + `SD_AI_COMMAND_PACK_SCOPE_CHECK_GH=0` → exit 0,
   marker present, pre-PR wording (proves `unknown` still warns).

Cases 4-5 are the ones that matter, and the explicit-body env cannot reach them.
`SD_AI_COMMAND_PACK_SCOPE_PR_BODY` short-circuits above `gh`, so a suite built
only from cases 1-3 would prove `satisfied` works on a path the fix does not
ship: the whole point of the task is a body *resolved from `gh`*. Use the
harness's existing `gh` stub instead — `tests/test_review_scope.py:806-819`
writes an executable `stub_bin/gh` emitting fixed `pr view` JSON and prepends it
to `PATH`:

4. advisory + scoped change + stub `gh` whose JSON body contains
   `Tooling/generated scope:` → exit 0, no `warning:`, no marker. This is the
   task's target case, and the only *script-level* test that exercises the
   shipped resolved-body path. The preflight case below covers the same path one
   layer up; nothing else does.
5. advisory + scoped change + stub `gh` whose JSON body lacks the section →
   exit 0, marker present, PR-exists wording.

Case 6 guards the cost bound rather than the behavior:

6. advisory + **no** scoped change + a stub `gh` that touches a sentinel file
   before printing → exit 0, no output, **and the sentinel does not exist**.

Asserting empty output alone would not catch the regression that matters. If a
later edit hoists the helper call above the `scoped_count -eq 0` early return,
output stays empty on an unscoped branch while every `make check` in the repo
silently starts paying a `gh` round-trip. The sentinel is what makes the first
bullet of the Cost section testable instead of merely asserted.

The existing `test_review_scope_off_suppresses_advisory` does not cover this: it
sets `SD_AI_COMMAND_PACK_SCOPE_CHECK=off`, which skips the script wholesale, and
says nothing about advisory mode on a branch with no scoped change.

Case 7 pins the one reordering this design introduces:

7. advisory + scoped change + `SD_AI_COMMAND_PACK_SCOPE_CHECK_GH=0` + a body
   through `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` that **does** contain the section →
   exit 0, no `warning:`, no marker.

Cases 1 and 3 each hold one half of this and neither holds both: case 1 supplies a
satisfying body with gh mode unpinned, case 3 disables gh with no body. The
"explicit body env set and matching" step that sits above the gh-disabled
short-circuit exists solely for this combination, so without case 7 the
reordering is the one part of the change with no executable proof — a later
"simplification" that restores the original order would pass the whole suite.

### Test isolation is suite-wide, not two tests

The first cut of this plan named two tests that inherit `os.environ` and pin no
gh mode. That undercounted badly. `run_install` writes
`.sd-ai-command-pack/manifest.json` and `.sd-ai-command-pack/installed-targets.txt`,
both classified as scoped by `is_pack_target_path`
(`sd-ai-command-pack-review-scope.sh:115-124`), so **every** preflight test has a
scoped change in its temp repo, and the preflight runs `checkScopeAdvisory` on
every invocation. Today that costs nothing because advisory mode never calls
`gh`. After this change each one would shell out to the developer's real `gh`.

The preflight suite invokes the script from roughly 37 direct `subprocess.run`
sites plus a shared `run_review_preflight` helper with 55 callers, and exactly
one of those sites passes an `env=` at all. Pinning site by site is not a
credible plan — it is 90-odd edits with no mechanism stopping the next test from
reintroducing the leak.

Pin it once instead, in `ReviewPreflightTests.setUp`
(`tests/test_review_preflight.py:32` is the only class in the module):

```python
def setUp(self) -> None:
    super().setUp()
    patcher = mock.patch.dict(os.environ, {"SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "0"})
    patcher.start()
    self.addCleanup(patcher.stop)
```

Sites that pass no `env=` inherit the patched environment; the single site that
builds `{**os.environ, ...}` inherits it too. Tests that need `gh` reachable —
the new stubbed-`gh` preflight case — override the key in their own env dict,
which wins because it is merged last.

Three properties make this safe rather than merely convenient:

- **No assertion changes.** In advisory mode `unknown:gh_disabled` and
  `unknown:no_pr` produce identical wording, and `unknown:no_pr` is what these
  tests get today from a temp repo with no PR. The output is byte-identical.
- **Enforcing mode is unreachable from here.** `checkScopeAdvisory` forces
  `SD_AI_COMMAND_PACK_SCOPE_CHECK: 'advisory'` in the spawn env
  (`sd-ai-command-pack-review-preflight.mjs:3483`), so no preflight test can
  reach an enforcing assertion through this variable.
- **`SCOPE_CHECK=off` would not do.** It suppresses the advisory entirely rather
  than resolving it to a warning, which changes the warning counts existing
  preflight assertions already account for. Disabling `gh` keeps the advisory
  firing with the same text; disabling the check removes it.

`tests/test_review_scope.py` gets the opposite treatment. It holds enforcing-mode
tests whose expected `fail` and `warn` text depends on gh mode, so a suite-wide
default there could silently rewrite an enforcing expectation — precisely what
the compatibility criterion forbids. Pin per test, and only the advisory ones:
`tests/test_review_scope.py:192-215`
`test_review_scope_advisory_names_required_section_without_pr` is the only
existing case that needs it. `test_review_scope_off_suppresses_advisory` at :217
already sets `SD_AI_COMMAND_PACK_SCOPE_CHECK=off` and never reaches resolution.

One case belongs at the preflight level rather than the script level, in
`tests/test_review_preflight.py`: a scoped change plus a stubbed `gh` returning a
satisfying body must produce a preflight run with zero warnings. The script-level
tests prove the marker is absent from the script's output; only this one proves
`checkScopeAdvisory` consequently emits no `warn`, which is the outcome the task
is actually named for.

Enforcing-mode regression is covered by the existing suite; the acceptance
criterion is that no enforcing-mode test changes.

## Rollback

Revert, in this order: `templates/scripts/sd-ai-command-pack-review-scope.sh`,
the `spawnSync` timeout in
`templates/scripts/sd-ai-command-pack-review-preflight.mjs`, the doc paragraph in
`templates/docs/SD_AI_COMMAND_PACK.md`, the new and pinned cases in
`tests/test_review_scope.py` and `tests/test_review_preflight.py`, then
`manifest.json`, the `CHANGELOG.md` heading, and
`docs/fleet/candidate-validation.json`. Re-run `make sync` to restore every root
mirror.

No state and no migration. The version bump is the only artifact that feels
irreversible, and it is not published until the PR merges.
