# Design — consolidate duplicated script helpers into the shared library

## Scope boundary

Four independent clusters, four independent commits. Nothing here shares code
with anything else here; the only reason they are one task is that they all land
in `scripts/sd_ai_command_pack_lib.py`. Treat the ordering in the PRD as real and
the coupling as absent.

Not in scope: the secret redactor and `validate_environment_blocked_evidence` —
`07-28-consolidate-secret-redactors` owns those, and the PRD's cross-reference is
right that this task's "preserve existing `environment_blocked` evidence
behavior" constraint should be checked against the *final* redactor.

All four findings are **P2 — unverified citations**. Every line below was
re-derived 2026-07-28. Three of the four enumerations in the PRD are wrong.

## A-085 — atomic write. Smallest, cleanest, land first.

Confirmed exactly three definitions of both functions:

| copy | `atomic_write_text` | `default_text_file_mode` | body |
|---|---|---|---|
| `review-learnings.py` | `:290` | `:276` | **67 lines** |
| `record-session.py` | `:71` | `:61` | 31 lines |
| `update-spec-kb.py` | `:393` | `:383` | 31 lines |

**Correction to the PRD's hardening list.** It names three mechanisms —
cross-device guard, directory fsync, TOCTOU re-check. Measured, the delta is
**two**:

- cross-device guard — `temporary_path.stat().st_dev != destination.parent.stat().st_dev`,
  raising `"atomic update would cross filesystems"`
- directory fsync after `os.replace`, in its own `try/except OSError`

The symlink refusal (`destination.is_symlink()` → `raise OSError("target is a symlink")`)
and the file-level `os.fsync(temporary.fileno())` are present in **all three**
copies, so they are not part of the delta. Naming the symlink check as a
hardening gain would overstate the fix.

This makes A-085 the low-risk one: promoting the 67-line version is strictly
additive for the other two call paths, and the two added mechanisms fail in the
direction of raising rather than silently writing.

## A-080 — cache-env contract. The count is 7, not 3.

The PRD names three key-list sites and two arity assertions. Measured, the key
set is written out **seven** times:

| site | form |
|---|---|
| `sd_ai_command_pack_lib.py:38-45` | `CACHE_ENV_KEYS` tuple — the authority |
| `sd_ai_command_pack_lib.py:47-54` | dict mapping key to subdirectory name |
| `shell-lib.sh:194` | `case` glob alternation |
| `toolchain.sh:425` | `case` glob alternation |
| `toolchain.sh:308` | positional args into the doctor heredoc |
| `toolchain.sh:362` | dict inside that heredoc's Python |
| `toolchain.sh:401-408` | `printf` diagnostic block, one line per key |

Plus the two arity assertions the PRD does name: `shell-lib.sh:210` (`-ne 7`) and
`toolchain.sh:435` (`-eq 7`).

The lib itself carries **two** of the seven. So "emit the key set as data" does
not reach AC2 ("adding an eighth cache variable requires no shell-side edit")
unless the doctor heredoc and the printf block are converted too — and those are
the two that a key-set-as-data change is most likely to skip, because neither
looks like a validation list.

`toolchain.sh:401-408` is the awkward one: it is human-readable diagnostic output,
one `printf` per key with individual labels. Generating it from data is possible
but changes operator-facing text. Decide deliberately rather than leaving it as
the one hand-maintained copy that quietly re-creates the problem.

## A-076 — git invocation. Three adapters, not five.

Exactly three files import the lib helper under the adapter alias:

```
pr-body-scope.py:55      from sd_ai_command_pack_lib import run_git as run_git_command
record-session.py:52     run_git as run_git_command,
review-learnings.py:39   run_git as run_git_command,
```

The PRD says five delegating adapters. There are three:

| adapter | shape |
|---|---|
| `record-session.py:102` | `run_git(*args) -> CompletedProcess` — varargs, no `cwd` |
| `pr-body-scope.py:277` | `_run_git(root, *args) -> tuple[int, str, str]`, flattens `CommandError` to `(124, "", str(exc))` |
| `review-learnings.py:992` | `_run_git(args, repo_root, *, check, accept_one) -> CompletedProcess[str]` |

Three other scripts — `audit-route.py:369`, `fleet-review-classify.py:111`/`:392`,
`recovery-artifacts.py:281`/`:315`/`:379`/`:1043` — call the lib's `run_git`
**directly by its own name, in list form**. They need nothing. Counting them as
adapters is what produced "five".

### The three bypasses, and why one is not like the others

`review-local.py:541` and `surface-check.py:124` are true bypasses — `grep -c
run_git_command` returns **0** for both files. Straightforward migrations.

`work-loop.py:202` is a bypass too, but migrating it is not mechanical:

- It calls `build_tool_environment(repo=repo)` first and converts `CacheSetupError`
  into `WorkLoopError` with appended remediation naming `CACHE_ROOT_ENV` (`:204-214`).
- Its `subprocess.run` at `:216` uses `stderr=subprocess.DEVNULL`,
  `errors="strict"`, `timeout=20`.
- **Its contract is `-> str | None` and it never raises on git failure.** Every
  `OSError`, `UnicodeError`, and `TimeoutExpired` becomes `None` (`:227-228`), as
  does any non-zero return code (`:229`).

Callers depend on that. `resolve_repository:237` does
`if not resolved: raise WorkLoopError(f"not a Git repository: {path}")`, and
`:1335`, `:1341`, `:1354`, `:1359`, `:1369`, `:1421`, `:1659`, `:1670` all read
the `None` as "unavailable" rather than "error". Repointing this onto the lib's
`run_git`, which raises, changes control flow at roughly ten sites.

**Design decision:** keep `work-loop.py`'s `-> str | None` swallowing shape as a
local adapter over the lib call. The goal is one git *invocation*, not one git
*error policy*. Rewriting ten call sites' error handling is a separate change
with its own risk and belongs in its own task if it is wanted at all.

The `errors="strict"` difference is not cosmetic either: the lib defaults to
`errors="replace"` (`sd_ai_command_pack_lib.py:376`). Non-UTF-8 git output
currently raises `UnicodeError` in work-loop and is swallowed to `None`; under
`replace` it would return mojibake that then gets parsed. Preserve `strict` at
this call site or the failure mode changes from "unavailable" to "wrong answer".

R2's "two lib shapes with a per-script error adapter passed via `context=`" is
the right target for the three adapters. It is not achievable for `work-loop.py`
without the ten-site rewrite above.

## A-046 — state root. Not a refactor; a state relocation.

The PRD says four copies that "disagree on which env vars they honor". Measured,
it is worse and differently shaped:

| site | function | honors `SD_AI_COMMAND_PACK_STATE_HOME`? |
|---|---|---|
| `work-loop.py:295` | `resolve_state_root` | yes — `STATE_HOME_ENV` at `:38` |
| `recovery-artifacts.py:123` | `resolve_state_root` | yes — `STATE_HOME_ENV` at `:49` |
| `fleet-timing.py:371` | `resolve_state_root` | **no** — `XDG_STATE_HOME`, `LOCALAPPDATA`, `$HOME` only |
| `fleet-controller.py:212` | `default_state_home` | **no** — `XDG_STATE_HOME` or `$HOME`, then appends `/fleet-campaigns` |

So `fleet-controller.py:212` is not a fourth copy of the same function. It is a
differently named function with a different signature, no absolute-path
validation, no Windows branch, and a hardcoded subdirectory baked into the root
rather than supplied by the caller.

**The consequence the PRD does not state:** two of the four sites ignore the
pack's own state-home variable today. Unifying them is a **behavior change**, not
a refactor. For any user with `SD_AI_COMMAND_PACK_STATE_HOME` set, fleet timing
records and campaign state currently live under `XDG_STATE_HOME`/`$HOME` and will
move. Existing state at the old path is not read after the change — it is
orphaned, not migrated.

This is exactly what AC1 asks for ("work-loop and fleet state resolve to the same
root — today they diverge"), so the change is intended. What is missing is the
migration question. Two acceptable answers:

- **Read-through fallback:** resolve to the new root; if it is absent and the
  legacy root exists, read from legacy and write to new. Adds a deprecation
  window and a code path that must eventually be deleted.
- **Documented one-time move:** changelog entry naming the old and new paths and
  the `mv` to run. Cheaper, correct, requires the user to act.

Pick one and record it. Silently relocating live lock and campaign state is the
failure mode this cluster is most likely to ship.

`fleet-controller`'s `/fleet-campaigns` suffix must move to the caller under the
shared contract ("callers keep only their subdirectory name" — R1 already says
this), which is the mechanical part.

## Compatibility

Three of the four clusters are internal refactors with no payload, no key, and no
documented contract crossing a release boundary. A-046 is the exception and is
handled above.

`environment_blocked` evidence behavior must be preserved by all four (PRD R5).
The live risk is A-076: `work-loop.py:204-214` builds `WorkLoopError` text that
names `CACHE_ROOT_ENV`, and `pr-body-scope.py:283` flattens `CommandError` into
`(124, "", str(exc))`. Both are error-shaping the lib does not do. Neither can be
dropped in the name of consolidation.

## Rollout and rollback

Four commits, in the PRD's order — A-085, A-080, A-046, A-076 — smallest and
safest first. Each is independently revertable; none depends on another.

Template parity applies to every lib edit
(`templates/scripts/sd_ai_command_pack_lib.py`), then `make sync`.

A-046 is the only one whose rollback is not clean: if the state relocation ships
and is then reverted, state written under the new root becomes orphaned in the
other direction. That asymmetry is the argument for the read-through fallback.

## Risk

Ranked:

1. **A-046 relocates live state.** Locks and campaign records move. Highest
   consequence, and the PRD does not mention it.
2. **A-076 changes error policy while claiming to change invocation.** The
   `-> str | None` contract and `errors="strict"` at `work-loop.py:202` are
   load-bearing at ~10 call sites. Preserve both.
3. **A-080 declares victory early.** Converting the two `case` globs and leaving
   the doctor heredoc and printf block hand-maintained satisfies the PRD's
   literal wording and fails AC2.
4. **A-085.** Low. Strictly additive hardening in the raising direction.
