---
title: Harden helper-loader TOCTOU and ship corrective 0.64.3
status: done
created: 2026-08-03
---
# PRD — Harden helper-loader TOCTOU and ship corrective 0.64.3

## Origin

Fleet campaign `refresh-0.64.2-20260803T222602Z` blocked at canary
`rwbp-coordinator` `local-checks`. The consumer's documented full gate
(`npm run check:full`) ran a Prism/gemini-2.5-pro review over the 0.64.0→0.64.2
install diff and produced three findings against the **vendored, shipped**
`sd-ai-command-pack-status.py`. The fleet finding-severity gate
(`sd-ai-command-pack-fleet-finding-classify.py`) returned
`pause-corrective-release`: two `security`-family findings classified
`block-corrective-release`. Pack-blocker recorded; campaign is superseded and a
corrective release is required before any consumer can move.

## Problem

Two shipped helper loaders in `sd-ai-command-pack-status.py` use the classic
check-then-use anti-pattern:

```python
helper = Path(__file__).resolve().with_name("<sibling>.py")
if helper.parent.is_symlink() or helper.is_symlink() or not helper.is_file():
    return {"status": "unavailable", ...}
spec = importlib.util.spec_from_file_location(name, helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)   # loads by PATH, re-resolved after the check
```

The `is_symlink()` guard and the `exec_module` load are two separate path
resolutions with a window between them (TOCTOU). A contract sweep found the same
class at two more sites:

- `sd-ai-command-pack-surface-check.py` `_load_source_module` (L214) — **shipped**.
- `sd-ai-command-pack-fleet-controller.py` `_wave_planner` (L129) — source-only,
  and currently has **no** symlink guard at all.

## Threat-model note (honest scope)

Every loader targets a **sibling of the already-running trusted script**
(`Path(__file__)` / `SCRIPT_DIR`). Winning the race requires pre-existing write
access to the pack's own `scripts/` directory, where an attacker could instead
just overwrite the regular exec'd helper directly — no symlink, no race, no new
privilege. So real-world exploitability beyond existing access is negligible.
**But** the fleet security gate is deterministic: `security`-family findings are
released-pack blockers by default, and the fleet contract forbids inferring an
override from prose. The racy pattern is also a genuine anti-pattern worth
removing. We fix it structurally rather than override.

## Requirements

- R1: Eliminate the TOCTOU at every islink-precheck-then-`exec_module` site by
  performing the safety check and the source read on **one** file descriptor
  (`O_NOFOLLOW`), with no path re-resolution between check and load.
- R2: Preserve existing behavior on valid inputs: a present, regular, non-symlink
  sibling module loads with **byte-identical module metadata** to the retired
  loader (`__spec__`/`__loader__`/`__cached__`/`__file__`/`__name__`/`__package__`
  from the real `spec_from_file_location`+`module_from_spec`; only execution
  switches to `compile`/`exec` of the fd-verified bytes). A missing / symlinked /
  **any non-regular** (socket / FIFO / dir) sibling yields the existing
  "unavailable" (status) or raised-error (surface-check/controller) outcome — the
  advisory `lstat` classifies all non-regular nodes as policy so a socket does
  not drift to `invalid`/raw. A genuine, non-policy open/read `OSError` (EIO,
  EACCES) routes through each caller's **original** boundary (status→`invalid`,
  surface-check/controller→raw), unchanged. Status keeps its
  `suppress_bytecode_writes()` boundary around the load. Registration stays
  surface-check-only and, on a failing exec, leaves the `sys.modules` entry as
  today. No behavior change for callers on the happy path.
- R3: Apply the fix to shipped files in **both twins** (`scripts/` and
  `templates/scripts/`), byte-identical.
- R4: Add direct tests covering symlink-rejection and valid-load for the new
  loader (clears the MEDIUM test-gap finding).
- R5: Ship as corrective version **0.64.3**: bump `manifest.json`, refresh
  version-bearing surfaces, dogfood manifest, provenance, CHANGELOG, and the
  full-fleet candidate ledger; `make release-prep` must pass.
- R6: No unrelated behavior or product changes. Loader-safety + release
  plumbing only.

## Out of scope

- The 40+ `is_symlink()` file-I/O guards that are NOT followed by dynamic code
  execution (they gate reads/writes, not `exec_module`) — not this finding's
  class.
- Fleet campaign resume mechanics — handled after 0.64.3 is merged and tagged
  (a fresh campaign targets 0.64.3).

## Acceptance criteria

- AC1: No shipped or source loader performs `spec_from_file_location` /
  `exec_module` on a path that was symlink-checked via a **separate** stat.
  Verify: the four sites route through the atomic loader.
- AC2: New tests assert the fixed loader's contract — valid module loads and
  carries **byte-identical metadata** to a real `spec_from_file_location`+
  `module_from_spec` (`__spec__` is a `ModuleSpec`, `__loader__` a
  `SourceFileLoader`, `__cached__`/`__file__`/`__name__`/`__package__` matching —
  not `None`); a symlink is refused raising `_UnsafeSiblingPath` with the
  attacker module never executed; a directory / FIFO / **Unix socket** is refused
  promptly (advisory `lstat` + `O_NONBLOCK`, no block, no socket drift). A status
  site keeps `sys.dont_write_bytecode` restored across a load. Plus a **seam
  differential** test: the old `spec_from_file_location`+`exec_module` follows
  the symlink while `_read_trusted_sibling_source` refuses (same input, opposite
  outcome). A static symlink alone is NOT a valid pre/post differential (the old
  `is_symlink()` guard already rejected it) and must not be claimed as one.
- AC3: the root `scripts/` mirrors and their `templates/scripts/` sources are
  byte-identical for every changed shipped file (status and surface-check).
  Verify: `diff` per file returns empty.
- AC4: `manifest.json` version == `0.64.3`; `make generate` reports 0 drift;
  `make release-prep` exits 0.
- AC5: The loaders no longer match the flagged pattern (confirmed by AC1 + AC2),
  not by suppressing the finding.
