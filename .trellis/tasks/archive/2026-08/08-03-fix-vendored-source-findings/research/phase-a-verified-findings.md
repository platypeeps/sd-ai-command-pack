# Phase A — findings re-verified against HEAD (b2489a0a base)

All line numbers are in `scripts/` (mirror byte-identically into
`templates/scripts/`). Confirmed by direct read on 2026-08-03.

## recovery-artifacts.py

### Empty pass-only `except` (CodeQL py/empty-except) — 8 sites, CONFIRMED
`L202`, `L207`, `L211` (atomic_write_json: chmod best-effort; os.close +
temporary.unlink in the outer `except Exception:` cleanup), and CleanupLock:
`L964`, `L1002`, `L1012`, `L1019`, `L1033`.
- Fix STRUCTURALLY (comment does NOT clear CodeQL):
  - `except OSError: pass` around a cleanup call → `contextlib.suppress(OSError)`.
  - unlink-and-ignore-missing → `Path.unlink(missing_ok=True)` where the only
    swallowed case is FileNotFoundError.
- Preserve every non-empty sibling handler (e.g. the outer `raise`, the
  OSError→RecoveryError branches). Behavior unchanged.

### read_text UnicodeError gap — CONFIRMED (2 sites)
`read_json` L216 and the CleanupLock read L969 do `path.read_text(encoding=
"utf-8")` but catch only `OSError`, so invalid UTF-8 escapes as `UnicodeError`.
- `encoding="utf-8"` is already explicit → do NOT add `errors="strict"` (no-op).
- Harden: widen to `except (OSError, UnicodeError)` at both sites (matches the
  pattern already used in work-loop L2294 and update-spec-kb L554), raising the
  same RecoveryError / returning the same failure. Add an invalid-UTF-8 test.

### SCHEMA_VERSION
`SCHEMA_VERSION = 1` (L48); `classify_repository` stamps
`{"schemaVersion": SCHEMA_VERSION, ...}` (L737).

## work-loop.py

- Empty except `L1143-1145`: `try: aside.unlink() except FileNotFoundError:
  pass except OSError as error: raise`. Fix: `aside.unlink(missing_ok=True)` and
  drop the FileNotFoundError handler; keep the OSError→WorkLoopError branch.
- read_text `L2293`: ALREADY catches `(OSError, UnicodeError)` (L2294). NO
  CHANGE — the captured "missing errors=" item is a non-issue here.

## update-spec-kb.py

- `file_ends_with_kb_copy_marker` L553: `return path.read_bytes().endswith(
  KB_COPY_MARKER_SUFFIX_BYTES)` with `except OSError: return False`. Fix: bounded
  tail read — open "rb", `seek(-len(marker), SEEK_END)`, read len(marker),
  compare; guard files shorter than the marker (read whole small file / catch
  OSError from seek). Keep `except OSError: return False`. (L559/L567 read_bytes
  are legitimate — leave.)

## status.py

- `collect_recovery`: helper import guard `L1196` (`if not helper.is_file()`)
  follows symlinks; a second identical guard `L800-801` (work-loop helper).
  Harden both to reject symlinks, mirroring this file's idiom at L492-494
  (`X.parent.is_symlink() or X.is_symlink() or not X.is_file()`).
- schemaVersion: after the `isinstance(classified, dict)` check (~L1222-1226),
  add `if classified.get("schemaVersion") != <helper>.SCHEMA_VERSION: return
  {"status":"invalid", ...}` — read SCHEMA_VERSION off the loaded module, do not
  hardcode. schemaVersion IS stamped, so no required-keys fallback.

## Already-resolved / non-issues (NO code change)

- review-scope.sh: provided-body check is at L189-190 (before `gh_disabled`);
  L199 blank. Already correct.
- install-audit.py depth-3 `references/` — rebutted (fnmatch `*` crosses `/`).
- work-loop.py read_text L2293 — already catches UnicodeError.
