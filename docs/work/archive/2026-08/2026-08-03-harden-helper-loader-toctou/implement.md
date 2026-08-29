# Implement — Harden helper-loader TOCTOU (0.64.3)

## Phase A — loader fix (behavior). Edit SOURCE, not mirrors (M6)

Shipped files: edit `templates/scripts/…` only; `make sync`/`make release-prep`
mirror to root `scripts/`. Source-only `fleet-controller.py`: edit `scripts/`.

Shared shape (all three): add the `_UnsafeSiblingPath(OSError)` class,
`_SiblingLoadError(ImportError)` class, `_PATH_POLICY_ERRNOS`, and the two
helpers `_read_trusted_sibling_source(path)` / `_exec_sibling_module(source,
path, module_name, *, register)` per design (advisory `lstat` classification then
O_NOFOLLOW+O_NONBLOCK fd gate, fail-closed; policy-only `_UnsafeSiblingPath` incl.
all non-regular nodes; spec-None → `_SiblingLoadError`; metadata via real
`module_from_spec`; register BEFORE `compile`; opt-in register that LEAVES a
failed entry; exec/non-policy-I/O exceptions propagate). Imports (VERIFIED): add
`errno`, `os`, `stat` to status; add `errno` to surface-check and
fleet-controller; all three already import `importlib.util`/`sys`; `types` NOT
needed (drop the `_exec_sibling_module` return annotation so no `ModuleType`
import is required in status/controller — surface-check keeps its existing
`from types import ModuleType` for other annotations). Wire each site as ONE
`try` with `except _UnsafeSiblingPath` FIRST then the caller's existing handler
tuple (see design "Concrete shape per site").

1. `templates/scripts/sd-ai-command-pack-status.py` — add missing of `errno`/
   `os`/`stat`:
   - `collect_work_loop` (L800): one `try` running
     `source=_read_trusted_sibling_source(helper)`, then **inside
     `with suppress_bytecode_writes():`** `module=_exec_sibling_module(source,
     helper, "sd_ai_command_pack_status_work_loop", register=False)`, then
     `module.status_snapshot(...)` OUTSIDE the `with` (today's L810 scope, R3-3);
     `except _UnsafeSiblingPath: return {"status":"unavailable","error":"work-loop
     helper is not installed"}`; then the existing `except (Attr,Import,Key,
     OSError,Runtime,Syntax,Type,Value) → {"status":"invalid",…}` untouched.
   - recovery classify (L1192): same shape incl. the `suppress_bytecode_writes()`
     wrap (today's L1208) → unavailable msg `"recovery-artifacts helper is not
     installed"`, register=False, existing invalid-classifier untouched.
2. `templates/scripts/sd-ai-command-pack-surface-check.py` `_load_source_module`
   (L212): one `try` running `source=_read_trusted_sibling_source(path)` then
   `module=_exec_sibling_module(path…, register=True)` (no bytecode-suppress —
   none today); `except _UnsafeSiblingPath: raise SurfaceInputError("missing
   source validator module: {relative}")`; then the existing `except (Import,
   Runtime,SystemExit,Type,Value)` → `SurfaceInputError("cannot load …")`. A
   non-policy read/exec `OSError` is caught by neither and propagates raw, as
   today. Add `import errno` only if missing (already has os/stat/importlib.util).
3. `scripts/sd-ai-command-pack-fleet-controller.py` `_wave_planner` (L127): add
   `errno` if missing; one `try` running
   `source=_read_trusted_sibling_source(path)` then `_exec_sibling_module(…,
   "sd_ai_command_pack_fleet_wave_plan_for_controller", register=False)`; `except
   (_UnsafeSiblingPath, _SiblingLoadError): raise FleetControllerError("fleet
   wave planner cannot be loaded")` (preserves today's spec-None →
   FleetControllerError); non-policy read/exec errors propagate raw as today.
   Note `WAVE_PLANNER = _wave_planner()` runs at module import (L139) — unchanged.

Validation A:
- `grep -n "spec_from_file_location\|exec_module" templates/scripts/…status.py
  templates/scripts/…surface-check.py scripts/…fleet-controller.py` → gone at the
  four sites.
- `.venv/bin/python -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" <files>` → parses.
- Root mirrors reconciled by `make sync` in Phase C (do not hand-edit them).

## Phase B — tests (R4) per corrected design

4. Add `tests/test_helper_loader_safety.py` covering, for status /
   surface-check / fleet-controller inlined helpers: (1) valid load returns
   module with sentinel AND **byte-identical metadata** to a real
   `spec_from_file_location`+`module_from_spec` (`__spec__` a `ModuleSpec`,
   `__loader__` a `SourceFileLoader`, `__cached__`==`cache_from_source(str(p))`,
   `__file__`/`__name__`/`__package__` — assert real values, not `None`); (2)
   symlink `p` → `_read_trusted_sibling_source` raises `_UnsafeSiblingPath` and
   attacker marker never written; (3) directory / FIFO / **Unix socket** →
   `_UnsafeSiblingPath`, FIFO+socket return promptly (short-timeout guard proves
   non-blocking via advisory `lstat`); (4) **seam differential** —
   `spec_from_file_location(name,p)+exec_module` loads the symlink target while
   the safe-read refuses (same input, opposite outcome); (5) register-True sets
   `sys.modules[name]` and LEAVES it on a failing exec — test BOTH a compile-time
   `SyntaxError` and a runtime exception (register-before-compile parity, R4);
   register-False never sets it; (6) **raced-symlink** — mock `os.lstat` →
   regular while the real path is a symlink; assert `_UnsafeSiblingPath` with
   `__cause__.errno == errno.ELOOP` and attacker not executed (exercises the
   authoritative `O_NOFOLLOW` branch, R4).
5. Rewrite old-seam mocks in `tests/test_status.py`:
   - `test_collect_work_loop_handles_helper_contract_and_syntax_failures` (L963):
     replace `spec_from_file_location`/`exec_module.side_effect` mocks with a
     **real** temp helper (syntax error / non-dict return) → assert `"invalid"`.
   - Audit L1433 + neighbors for the same retired seam; convert to real temp
     helpers. Keep static-symlink tests L1487/L1504 (still valid).
   - Adapt the bytecode-suppression test at L1345 to the new load path, asserting
     all THREE (R4): helper execution observes `dont_write_bytecode=True`; the
     post-`with` helper callable observes the prior value; prior value restored
     after both success and failure (a restore-only assert would pass even if
     suppression were deleted). Add a socket→`unavailable` case (R3-1).
6. Run: `.venv/bin/python -m unittest tests.test_helper_loader_safety tests.test_status -v`
   → all pass. The symlink-reject in the new module is a true assertion of the
   new loader; the seam-differential (4) is the honest regression demonstration
   (do NOT claim a static-symlink fixture "fails pre-fix" — it does not).

## Phase C — release 0.64.3 (canonical order, M6)

7. `manifest.json`: version 0.64.2 → 0.64.3.
8. `CHANGELOG.md`: add `## 0.64.3 - <date>` heading + entry (security-hardening:
   atomic O_NOFOLLOW helper loader, removes islink-then-load TOCTOU at 4 sites;
   loader-safety tests) — **before** release-prep (payload gate checks it).
9. `make release-prep` → runs generate → `install.py . --force` (mirrors root
   `scripts/` from templates) → update-spec-kb → payload/version+CHANGELOG gate →
   conditional full-fleet candidate-ledger refresh → `make check`. Do NOT
   hand-run `make generate`, hand-edit root mirrors, or hand-regenerate the
   ledger.

Validation C:
- `grep '"version"' manifest.json` == 0.64.3.
- Root mirrors reconciled: `diff scripts/…status.py templates/scripts/…status.py`
  → empty (proves `make sync` mirrored the template edit); same for surface-check.
- Re-run `make release-prep` (or `make generate`) → 0 residual drift.
- `make release-prep` → EXIT 0, 0 FAIL.

## Phase D — planning adversarial review gate

Already run at planning convergence (this task creates prd/design/implement).
Re-run the host lane (+ optional Codex lane) if Phase A–C materially changed the
plan. Do not proceed past an unresolved blocking concern.

## Phase E — ship pack 0.64.3

12. Single logical commit on `fix/harden-helper-loader-toctou`.
13. `trellis:finish-work` (archive task + journal).
14. Push, open PR to `main`, request Copilot, drive review+CI green, squash-merge.
15. Confirm `v0.64.3` tag on merged main; sync local main.

## Phase F — fresh fleet campaign at 0.64.3

16. New campaign `refresh-0.64.3-<utc>`; run preflight → all 8 consumers
    refresh-needed 0.64.0→0.64.3.
17. Drive canaries sequential → post-canary waves ≤2 → final, per the
    fleet-refresh procedure. Each consumer's `local-checks` must now pass the
    Prism gate (the flagged pattern is gone).
18. **Execution correction from the blocked run:** create each consumer's
    dedicated Trellis task by running the consumer's `task.py` with **cwd set to
    that consumer** (the blocked run created it in the pack repo by running from
    the pack cwd). Verify `task.py current` resolves inside the consumer before
    recording checkout-validation.

## Rollback points

- After Phase A/B: revert loader edits, keep 0.64.2. No release moved.
- After Phase C but pre-merge: drop the branch.
- Post-merge: 0.64.3 is additive; a 0.64.4 would supersede. No consumer moved
  until Phase F.
