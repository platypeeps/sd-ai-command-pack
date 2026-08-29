# Design — Consolidate state-root resolution into the shared library (A-046)

## Migration decision (the blocking gate — recorded here per PRD AC3)

**Decision: documented one-time move.** Chosen by the user on 2026-08-06 after
adversarial review round 1 reopened the initial read-through-fallback choice.

Only two of the four sites relocate at all:

| site | honors pack var today | root moves? |
|---|---|---|
| `sd-ai-command-pack-work-loop.py` | yes | no |
| `sd-ai-command-pack-recovery-artifacts.py` | yes | no |
| `sd-ai-command-pack-fleet-timing.py` | no | **yes** |
| `sd-ai-command-pack-fleet-controller.py` | no | **yes** |

Work-loop and recovery-artifacts already resolve through
`SD_AI_COMMAND_PACK_STATE_HOME`, so adopting the lib ladder is a pure refactor
for them and no live state moves.

Why the one-time move rather than a read-through fallback: `timing_store`
(`sd-ai-command-pack-fleet-timing.py:433-444`) and `CampaignStore`
(`sd-ai-command-pack-fleet-controller.py:339-351`) each derive `state_path` and
`lock_path` from a single `directory`. A fallback has no seam to attach to —
selecting legacy would also write legacy, and a legacy/canonical split would put
old and new processes on different lock files, destroying the mutual exclusion
that was the whole reason to protect live locks. The one-time move eliminates
that class of failure by construction: there is exactly one root in effect at
any moment.

Bounding evidence:

- On POSIX, `SD_AI_COMMAND_PACK_STATE_HOME` unset ⇒ canonical and legacy roots
  are identical and nothing moves. Only a user who sets it is affected.
- **Windows is affected even with the variable unset**, for fleet campaigns
  only: `default_state_home` (`sd-ai-command-pack-fleet-controller.py:332-336`)
  has no Windows branch, so adopting the shared ladder moves campaign state from
  `~/.local/state/...` to `LOCALAPPDATA/sd-ai-command-pack/state/...`. The
  migration note must name those users. `fleet-timing` already has a Windows
  branch, so it is unaffected by this specific change.
- Neither fleet script ships in `templates/scripts/`, so relocation can only
  affect a maintainer checkout, never an installed consumer.
- `~/.local/state/sd-ai-command-pack/` already holds `work-loops/`,
  `fleet-timing/`, and `fleet-campaigns/` side by side — the unified layout is
  already the de-facto shape when the variable is unset.

Operator contract, to be recorded in `CHANGELOG.md` (AC3):

- Name the old root (`$XDG_STATE_HOME/sd-ai-command-pack` or
  `~/.local/state/sd-ai-command-pack`) and the new root
  (`$SD_AI_COMMAND_PACK_STATE_HOME`).
- Give the exact move for the two affected subdirectories, `fleet-timing/` and
  `fleet-campaigns/`.
- State that it must be run with no fleet operation in flight, because a move
  while a lock is held would strand that lock.
- No code reads the legacy root after this change. Nothing is auto-migrated,
  auto-deleted, or copied.

## Lib contract

Added to `scripts/sd_ai_command_pack_lib.py`, beside the existing private-path
primitives (`_path_from_environment`, `_validate_external_path`,
`_ensure_private_directory`):

```python
STATE_HOME_ENV = "SD_AI_COMMAND_PACK_STATE_HOME"

def resolve_state_root(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    os_name: str | None = None,
    state_home: Path | None = None,
) -> Path: ...

def ensure_private_directory(path: Path, *, label: str) -> Path: ...
```

`resolve_state_root` carries the canonical ladder, taken from the work-loop
implementation (`sd-ai-command-pack-work-loop.py:329-360`), which is the most
complete of the four:

1. explicit `state_home` argument (absolute, else raise) — preserves the
   `fleet-timing` and `CampaignStore` injection points;
2. `SD_AI_COMMAND_PACK_STATE_HOME` (absolute, else raise);
3. `XDG_STATE_HOME` + `sd-ai-command-pack` when absolute;
4. Windows `LOCALAPPDATA` + `sd-ai-command-pack/state`, using the existing
   `PureWindowsPath` + separator-normalization branch so `os_name`-injected
   portability tests stay deterministic;
5. `~/.local/state/sd-ai-command-pack` (absolute, else raise).

No `legacy_state_root` is introduced: the one-time move means no code ever reads
the old root.

The lib function is named `ensure_private_directory` — **not**
`ensure_state_directory` — so PRD AC2 ("exactly one `def resolve_state_root` and
one `def ensure_private_directory` across `scripts/*.py`, both in the lib") is
literally satisfiable. It is distinct from the existing private
`_ensure_private_directory` (`sd_ai_command_pack_lib.py:227`), which enforces
uid-ownership and a strict group/other permission check appropriate to cache
namespaces; applying those at state call sites would be a behavior change.
Folding the two together is a separate cleanup, not this task.

`ensure_private_directory` adopts the **evidence-raising** form (PRD R2): reject
symlinks before and after `mkdir`, `mode=0o700`, best-effort `chmod`, and never
let a raw `OSError` escape. It raises `CommandError`, and — critically — chains
the originating `OSError` as `__cause__` so callers can re-wrap without losing
it.

## Error-type preservation (PRD R3)

No call site changes its observable error type. Each script keeps a thin local
wrapper, named so that no second `def resolve_state_root` or
`def ensure_private_directory` exists outside the lib:

```python
def _state_root(...) -> Path:
    try:
        return lib.resolve_state_root(...)
    except lib.CommandError as error:
        raise WorkLoopError(str(error)) from error
```

The module-level names the existing call sites use stay bound by assignment
(`resolve_state_root = _state_root`), not by a second `def`, so 7 of the 8
`resolve_state_root`/`default_state_home` call sites and all 8
`ensure_private_directory` call sites are untouched. The exception is
`sd-ai-command-pack-fleet-controller.py:344`, which necessarily changes because
`default_state_home` is deleted outright (PRD R4).

All three `ensure_private_directory` definitions
(`work-loop.py:368`, `recovery-artifacts.py:156`, `fleet-timing.py:411`) are
structurally identical — symlink pre-check, `mkdir(mode=0o700, parents=True,
exist_ok=True)`, post-check, best-effort `chmod` — and differ only in error type
and message wording. `label` carries that wording: `"state directory"` for
work-loop and recovery-artifacts, `"timing state directory"` for fleet-timing.
Only the symlink substring is test-asserted
(`tests/test_fleet_timing.py:643,667`).

Three mechanical constraints the wrappers must respect:

- `sd_ai_command_pack_lib.py` imports `Path` but **not** `PureWindowsPath`; the
  Windows branch requires adding that import.
- `sd-ai-command-pack-fleet-timing.py:436` calls `resolve_state_root(state_home)`
  **positionally**, so its wrapper keeps a positional `state_home` parameter even
  though the lib function is keyword-only.
- `timing_store` keeps its own `state_root.is_symlink()` guard (`:435`). That
  checks the *root*, not the leaf directory `ensure_private_directory` creates,
  so delegation does not subsume it.

**Work-loop is the exception that matters.** Its directory-create failure raises
`StatePersistenceError` (`sd-ai-command-pack-work-loop.py:173-187`), which
subclasses `OSError` *deliberately* — the docstring states it exists "so the
atomic-write contract and every existing OSError handler keep working
unchanged", and it carries the structured `environment_blocked` evidence that
`sd-work-backlog` and `sd-status` read. `tests/test_work_loop.py:667` asserts
both the subtype and the evidence. Its wrapper therefore must **not** convert to
`WorkLoopError`:

```python
def _ensure_state_dir(path: Path) -> None:
    try:
        lib.ensure_private_directory(path, label="state directory")
    except lib.CommandError as error:
        cause = error.__cause__
        if isinstance(cause, OSError):
            raise _user_state_blocked(
                "prepare the work-loop state directory", "state-directory", cause
            ) from cause
        raise WorkLoopError(str(error)) from error
```

This is why the lib chains the original `OSError`: `_user_state_blocked` needs
the real errno to reproduce a byte-identical fragment.

## Per-caller changes

- **work-loop**: delete both local definitions; delegate via the wrappers above.
  `state_paths` unchanged. Preserves `StatePersistenceError` and the
  `environment_blocked` fragment exactly.
- **recovery-artifacts**: same delegation, wrapping to `RecoveryError`. Its
  current `ensure_private_directory` lets a raw `OSError` escape — that is the
  R2 defect, and delegation fixes it.
- **fleet-timing**: delegate; gains the pack variable and the corrected Windows
  branch (its current `Path(local_app_data)` skips separator normalization).
  No fallback logic.
- **fleet-controller**: delete `default_state_home`. `CampaignStore` calls
  `resolve_state_root()` and appends `fleet-campaigns` itself (PRD R4) **only on
  the default path**. An injected `state_home` keeps today's exact semantics —
  `root / repository_digest`, with no `fleet-campaigns` segment — because
  `CampaignStore(state_home=X)` currently means "campaigns live directly under
  X" (`sd-ai-command-pack-fleet-controller.py:340-350`), and the CLI tests that
  inject a root do not assert its exact path, so a silent change would not be
  caught. `CampaignStore` keeps its absolute/symlink validation.

  One observable-behavior trap (PRD R3): a **relative** `XDG_STATE_HOME`
  currently flows through `default_state_home` unvalidated and then raises
  `FleetControllerError("state home must be an absolute path")` at
  `sd-ai-command-pack-fleet-controller.py:345-346`. The shared ladder instead
  skips a non-absolute `XDG_STATE_HOME` and falls through to the home root,
  which would silently succeed where it used to fail. The controller wrapper
  must therefore reject a relative `XDG_STATE_HOME` explicitly to preserve the
  existing error.

## Test plan

- AC1: `SD_AI_COMMAND_PACK_STATE_HOME=/tmp/x` resolves all four modules under
  `/tmp/x`.
- AC2: boundary test grepping `scripts/*.py` for exactly one
  `def resolve_state_root` and one `def ensure_private_directory`, modeled on
  `tests/test_git_invocation_boundary.py`.
- Error-type preservation per wrapper, plus a dedicated test that the work-loop
  `environment_blocked` fragment and `StatePersistenceError` subtype are
  unchanged (guards `tests/test_work_loop.py:667`).
- `CampaignStore` injected-`state_home` path is unchanged, and the default path
  gains exactly one `fleet-campaigns` segment — asserted on exact paths, closing
  the gap at `tests/test_fleet_controller.py:1592`.
- Windows branch via injected `os_name` for both fleet modules.
- Template parity, including the library itself (see below).

## Packaging and parity

`manifest.json:173-174` makes `templates/scripts/sd_ai_command_pack_lib.py` the
**installed source** for `scripts/sd_ai_command_pack_lib.py`, and `make sync`
force-refreshes the dogfood install from `templates/`. Editing only `scripts/`
would therefore be overwritten by the next sync. Every payload edit must land in
`templates/scripts/` and be synced down:

- `templates/scripts/sd_ai_command_pack_lib.py`
- `templates/scripts/sd-ai-command-pack-work-loop.py`
- `templates/scripts/sd-ai-command-pack-recovery-artifacts.py`

The fleet timing and fleet controller scripts are source-only and have no
template counterpart — confirm they are still absent from `templates/scripts/`
rather than assuming it.

## Rollback

Single commit, no automatic data mutation: revert restores the four local
implementations. Rollback is symmetric because nothing is ever written to a
legacy path and nothing is deleted — the only asymmetry is that a user who
performed the documented `mv` must move the two directories back, which the
CHANGELOG entry states explicitly.

## Follow-up

- Consider folding `ensure_private_directory` into `_ensure_private_directory`
  once the ownership/permission difference is reconciled.

## Adversarial review ledger

### Round 1 (2026-08-06)

Host lane: completed. Codex lane: completed (`codex exec`, read-only,
ephemeral). Both lanes independently found the AC2 defect (C-4). Every concern
was re-verified against repository code before disposition.

| ID | Severity | Blocks | Concern | Evidence | Disposition |
|---|---|---|---|---|---|
| C-1 | Critical | yes | Read-through fallback has no seam: `timing_store` derives `state_path` and `lock_path` from one `directory`; `CampaignStore` does the same. | `fleet-timing.py:433-444`, `fleet-controller.py:339-351` | **addressed** — migration switched to a documented one-time move; no fallback exists |
| C-2 | High | yes | "Clean rollback both directions" was false: reverted fleet code ignores the pack variable, and old/new processes would lock different roots. | `fleet-timing.py:390`, `fleet-controller.py:332` | **addressed** — one root in effect at a time; rollback section corrected |
| C-3 | High | yes | `CampaignStore.state_home` semantics would silently change from `root/<digest>` to `root/fleet-campaigns/<digest>`; CLI tests inject a root but never assert its exact path. | `fleet-controller.py:340-350`, `tests/test_fleet_controller.py:1592` | **addressed** — suffix applied only on the default path; exact-path test added |
| C-4 | High | yes | AC2 unsatisfiable: lib function was named `ensure_state_directory`, leaving zero `def ensure_private_directory`. | `prd.md:76-77` | **addressed** — lib function named `ensure_private_directory` |
| C-5 | High | yes | Template parity omitted the library itself; `make sync` force-installs from templates and would overwrite it. | `manifest.json:173-174`, `Makefile` sync target | **addressed** — parity section now names all three template files |
| C-6 | High | yes | Fallback tests omitted partial migration and lock coexistence across sibling records. | `fleet-timing.py:439`, `fleet-controller.py:349` | **addressed** — moot; no fallback, so no partial-migration state exists |
| C-7 | Medium | yes | `StatePersistenceError` is an `OSError` subclass carrying `environment_blocked` evidence; a `CommandError → WorkLoopError` wrapper would change the type and break the asserted evidence. | `work-loop.py:170-178`, `tests/test_work_loop.py:667` | **addressed** — lib chains the original `OSError`; work-loop wrapper re-raises via `_user_state_blocked` |
| C-8 | Low | no | Stale figures: `prd.md` cited `work-loop.py:330` (actual 329), `fleet-timing.py:377` (actual 390), `fleet-controller.py:331` (actual 332), `ensure_private_directory` at `369/156/398` (actual `368/156/411`), "~6 call sites" (actual 8 resolve/default and 8 ensure). | `grep` over `scripts/*.py` | **addressed** — `prd.md` corrected; `design.md` no longer cites "~9" |
| C-9 | Low | no | `implement.md` validated with `pytest` while the repo gate is unittest via `make test`. | `Makefile:41-43` | **addressed** — pytest is the focused lane only; `make check` is authoritative |

Round 1 outcome: implementation blocked. C-1, C-2, and C-6 turned on one
reopened strategy decision, escalated to the user per contract §4.

User judgment (2026-08-06): **documented one-time move**.

### Round 2 (2026-08-06)

Host lane: completed, 2 concerns. Codex lane: completed, 4 blocking + 2 low.
All re-verified against repository code.

| ID | Severity | Blocks | Concern | Evidence | Disposition |
|---|---|---|---|---|---|
| C-10 | Low | no | Lib imports `Path` but not `PureWindowsPath`, which the Windows branch needs. | `sd_ai_command_pack_lib.py:16` | **addressed** — import added to step 1 |
| C-11 | Medium | yes | `fleet-timing` calls `resolve_state_root(state_home)` positionally; a keyword-only wrapper would break it. | `fleet-timing.py:436` | **addressed** — wrapper keeps a positional parameter |
| C-12 | High | yes | `prd.md` still called the read-through fallback "recommended" and framed old state as "orphaned, not migrated", contradicting the selected decision. | `prd.md:38-53` | **addressed** — decision section rewritten as RESOLVED |
| C-13 | High | yes | With the pack variable unset **on Windows**, campaign state still moves: `default_state_home` has no Windows branch, so the shared ladder relocates it to `LOCALAPPDATA`. The "unset ⇒ nothing moves" claim was false. | `fleet-controller.py:332-336` | **addressed** — claim scoped to POSIX; Windows case added to design and the CHANGELOG contract |
| C-14 | High | yes | A relative `XDG_STATE_HOME` currently reaches `CampaignStore` and raises `FleetControllerError`; the shared ladder would skip it and silently succeed, violating R3. | `fleet-controller.py:332-346` | **addressed** — controller wrapper rejects relative `XDG_STATE_HOME`; recorded as PRD R3 exception (b) |
| C-15 | High | yes | PRD R2 and R3 are mutually inconsistent for recovery-artifacts: R2 requires removing the raw `OSError` leak, R3 forbids changing observable behavior at any ensure call site. | `prd.md:32-36,61-69`, `recovery-artifacts.py:156-160` | **addressed** — R3 now carries two explicit exceptions |
| C-16 | High | yes | Shipped template changes require `make release-prep`, not just `make sync && make check`; and `docs/FLEET_ROLLOUT.md:141-148` plus `README.md:487` document the old resolution and would become false. Design promised a reverse `mv` the checklist never requested. | `CONTRIBUTING.md:122-142`, `docs/FLEET_ROLLOUT.md:141-148`, `README.md:487` | **addressed** — release-prep, both doc updates, and the reverse `mv` added to step 7 |
| C-17 | Low | no | Design claimed all 8 resolve/default call sites stay untouched, but deleting `default_state_home` necessarily changes `fleet-controller.py:344`. | `fleet-controller.py:344` | **addressed** — corrected to "7 of 8" with the exception named |
| C-18 | Low | no | Stale details: `StatePersistenceError` is at 173-187 (not 170-178); pinned pytest version was wrong. | `work-loop.py:173` | **addressed** — line range corrected; version number dropped |

Round 2 outcome: all concerns addressed in `prd.md`, `design.md`, and
`implement.md`. Proceeding to the third and final permitted review round
(contract §4 allows three automatic rounds total).

### Round 3 (2026-08-06) — final

Host lane: completed, 0 new concerns; all six round-2 fixes verified present.
Codex lane: completed, verdict `BLOCKED:` with 2 concerns. Both re-verified
against repository code before acceptance; both are checklist-completeness
defects in `implement.md`, not design or strategy reversals.

| ID | Severity | Blocks | Concern | Evidence | Disposition |
|---|---|---|---|---|---|
| C-19 | High | yes | `implement.md` step 4 delegated only fleet-timing's `resolve_state_root`, never its `ensure_private_directory`. Following the plan literally would leave two `def ensure_private_directory` in `scripts/*.py` and fail AC2. | `fleet-timing.py:411`; `grep '^def ensure_private_directory' scripts/*.py` returns 3 (`fleet-timing:411`, `recovery-artifacts:156`, `work-loop:368`) | **addressed** — step 4 now delegates it, names both call sites (`:470`, `:535`), and pins the `FleetTimingError` / `must not be a symlink` preservation |
| C-20 | High | yes | The gate `make sync && make check && make release-prep` is ordered wrong: `check` enforces the stale fleet ledger that `release-prep` exists to refresh, so `&&` can abort before the refresh runs. | `Makefile:36-38` (`release-prep` = `prepare-release.py` then `$(MAKE) check`); `prepare-release.py:292` runs `install.py . --force` | **addressed** — step 7 and the validation block now call `make release-prep` alone, with the self-sync/check chain documented |

Host verification of the round-3 fixes (post-edit greps over `implement.md`):
`make sync && make check` now appears exactly once, as an explicit prohibition,
and never as a prescribed command; step 4 names `ensure_private_directory`;
requirement traceability is `R1:1 R2:1 R3:3 R4:1 R5:1` and
`AC1:3 AC2:2 AC3:1 AC4:3`.

Round 3 outcome: both concerns addressed. No fourth automatic round is
permitted, and none is required — neither fix reopened a design decision.
Implementation is unblocked.
