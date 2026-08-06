# Implementation plan — A-046 state-root consolidation

Branch: `feat/consolidate-state-root-resolution` off `main`.

Migration strategy: **documented one-time move** (see `design.md`). No fallback
code, no legacy read path.

Payload edits land in `templates/scripts/` and reach `scripts/` via `make sync`
— `manifest.json:173-174` makes the template the installed source, so editing
`scripts/` directly is overwritten.

## Ordered checklist

### 1. Lib owner

- [x] **R1**: in `templates/scripts/sd_ai_command_pack_lib.py`, add
      `STATE_HOME_ENV`, `resolve_state_root`, and `ensure_private_directory`
      beside the existing private-path primitives — these become the single
      definitions of each.
- [x] Port the ladder from `sd-ai-command-pack-work-loop.py:329-360`, adding
      `state_home` as step 1. Keep the `PureWindowsPath` separator
      normalization, and **add the `PureWindowsPath` import** — the lib
      currently imports only `Path`.
- [x] `ensure_private_directory` uses the work-loop semantics, raises
      `CommandError`, and **chains the originating `OSError` as `__cause__`** —
      work-loop's wrapper depends on it.
- [x] It takes a `label` so each caller keeps its own wording: work-loop and
      recovery-artifacts pass `"state directory"`, fleet-timing passes
      `"timing state directory"`. The symlink message must keep the literal
      substring `must not be a symlink` — `tests/test_fleet_timing.py:643,667`
      assert it. A `reference` argument carries the caller's path rendering so
      each module keeps its redaction posture byte-for-byte: work-loop the full
      path, recovery-artifacts `path.name` (that module never puts a host
      absolute path in a diagnostic), fleet-timing no path at all.
- [x] Do not reuse the private `_ensure_private_directory` (`:227`); its
      uid/permission checks would change behavior at state call sites.
- [x] `make sync`, then confirm `scripts/sd_ai_command_pack_lib.py` matches.
- [x] Validation: module imports clean; `mypy` clean.

### 2. work-loop (no root movement)

- [x] In `templates/scripts/sd-ai-command-pack-work-loop.py`, replace both local
      definitions with `_state_root` / `_ensure_state_dir` wrappers, binding the
      existing names by assignment so no second `def` exists.
- [x] `_ensure_state_dir` recovers `error.__cause__` and re-raises through
      `_user_state_blocked`, preserving `StatePersistenceError` (an `OSError`
      subclass) and a byte-identical `environment_blocked` fragment.
- [x] Validation: `python3 -m unittest tests.test_work_loop -q` passes with no
      expected-output changes, including the assertion at
      `tests/test_work_loop.py:667`.

### 3. recovery-artifacts (no root movement)

- [x] Same delegation in `templates/scripts/`, wrapping to `RecoveryError`.
      Removes the raw-`OSError` escape (PRD R2).
- [x] Validation: `python3 -m unittest tests.test_recovery_artifacts -q`.

### 4. fleet-timing (source-only; root moves)

- [x] Delegate `resolve_state_root`; it gains the pack variable and the
      corrected Windows branch. No fallback. The wrapper keeps a **positional**
      `state_home` parameter — `:436` calls it positionally.
- [x] **Also delegate `ensure_private_directory` (`:411`)** — it is a third
      definition and AC2 fails if it survives. Its wrapper re-raises
      `FleetTimingError` from `CommandError`, keeping `must not be a symlink`
      and `cannot create timing state directory` in the messages. Both call
      sites (`:470`, `:535`) stay untouched via the assignment binding.
- [x] Leave `timing_store`'s own `state_root.is_symlink()` guard (`:435`) in
      place; it is a separate check on the root, not on the leaf directory.
- [x] Validation: `python3 -m unittest tests.test_fleet_timing -q`.

### 5. fleet-controller (source-only; root moves)

- [x] **R4**: delete `default_state_home`. `CampaignStore` calls
      `resolve_state_root()` and appends `fleet-campaigns` **only on the default
      path**; an injected `state_home` keeps today's `root / repository_digest`
      semantics exactly.
- [x] Keep `CampaignStore`'s absolute/symlink validation.
- [x] Reject a **relative** `XDG_STATE_HOME` explicitly so the existing
      `FleetControllerError` is preserved; the shared ladder would otherwise
      skip it and fall through to the home root (PRD R3 exception (b)).
- [x] Validation: `python3 -m unittest tests.test_fleet_controller -q`.

### 6. Tests

- [x] AC1: all four modules resolve under `SD_AI_COMMAND_PACK_STATE_HOME=/tmp/x`.
- [x] AC2: boundary test asserting exactly one `def resolve_state_root` and one
      `def ensure_private_directory` across `scripts/*.py`, modeled on
      `tests/test_git_invocation_boundary.py`.
- [x] Work-loop `environment_blocked` fragment and `StatePersistenceError`
      subtype unchanged.
- [x] `CampaignStore`: injected `state_home` path unchanged, default path gains
      exactly one `fleet-campaigns` segment — assert exact paths.
- [x] Windows branch via injected `os_name` for both fleet modules.
- [x] Error-type preservation per wrapper, including: fleet-timing still raises
      `FleetTimingError` matching `must not be a symlink`
      (`tests/test_fleet_timing.py:643,667`), recovery-artifacts raw
      `OSError` now becomes `RecoveryError` (R3 exception (a)), and a relative
      `XDG_STATE_HOME` still raises `FleetControllerError` (R3 exception (b)).

### 7. Parity, docs, gate

- [x] Confirm `templates/scripts/` still has no fleet-timing/fleet-controller
      counterpart.
- [x] **R5** (the recorded migration decision) — `CHANGELOG.md`: state-root
      unification, the affected subdirectories
      (`fleet-timing/`, `fleet-campaigns/`), old and new roots, the exact `mv`
      **and its reverse for rollback**, and the requirement that no fleet
      operation be in flight (AC3). Include the Windows case: campaign state
      moves to `LOCALAPPDATA` even with the pack variable unset.
- [x] Update operator docs that become false: `docs/FLEET_ROLLOUT.md:141-148`
      (campaign `<state-home>` resolution) and `README.md:487`
      (`SD_AI_COMMAND_PACK_STATE_HOME` is no longer work-loop-only).
- [x] Bump manifest version; regenerate release-hygiene surfaces.
- [x] Run **`make release-prep` on its own** (AC4). It is the canonical
      post-payload command (`CONTRIBUTING.md:122-142`): `prepare-release.py`
      self-syncs via `install.py . --force` (`:292`) and refreshes the exact
      fleet ledger, then the target ends with `$(MAKE) check` (`Makefile:36-38`).
      Do **not** chain `make sync && make check && make release-prep` — `check`
      enforces the stale ledger that `release-prep` exists to refresh, so `&&`
      can abort before the refresh ever runs.

## Review gates

- After step 1: lib contract reviewed before any caller is touched.
- After step 5: all four callers delegate; `default_state_home` is gone.
- Before commit: AC1–AC4 each mapped to a named passing test.

## Rollback points

- Steps 1–3 are pure refactors: revert individually, no state impact.
- Steps 4–5 are the only root-relocating changes; revert them together.
- Nothing is written to or deleted from a legacy path at any step.

## Validation commands

```bash
# Focused lane (pytest is available system-wide, not in .venv)
pytest tests/ -k "state_root or state_home" -q          # AC1

python3 -m unittest tests.test_work_loop tests.test_recovery_artifacts \
                    tests.test_fleet_timing tests.test_fleet_controller -q

make release-prep                # authoritative gate, AC4 — self-syncs, then check
```
