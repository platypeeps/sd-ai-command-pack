# Design — Harden helper-loader TOCTOU (0.64.3)

## Approach: split safe-read (path safety) from exec (module behavior)

Two separate helpers. `_read_trusted_sibling_source` performs **all** path
safety on one descriptor and returns bytes — its `OSError` means "path unsafe or
missing". `_exec_sibling_module` compiles+execs already-read bytes — its
exceptions are ordinary module-execution failures that must propagate to each
caller's existing handler unchanged. Keeping them separate is what prevents the
loader from reclassifying a post-load `OSError` (see C-6).

```python
class _UnsafeSiblingPath(OSError):
    """Path-POLICY rejection: symlink, non-regular, missing, or O_NOFOLLOW
    unavailable. Distinct from an arbitrary open/read OSError (EIO, EACCES…) so
    each caller routes the two cases through its OWN original boundary (R2-B2).
    Subclasses OSError so a caller that only wants the original broad handler
    still catches it, but callers list it FIRST to peel off the policy case."""


# errno values that mean "the path itself violates policy" — missing final
# component, a symlink final component (ELOOP from O_NOFOLLOW), or a path whose
# non-final component is not a directory. Everything else is a real I/O fault.
_PATH_POLICY_ERRNOS = frozenset(
    e for e in (getattr(errno, n, None) for n in ("ENOENT", "ELOOP", "ENOTDIR"))
    if e is not None
)


def _read_trusted_sibling_source(path: Path) -> bytes:
    """Read a sibling module's source with no TOCTOU window.

    Fails CLOSED if O_NOFOLLOW is unavailable. An advisory `lstat` decides ONLY
    which caller branch an unsafe path takes (R3-1) — it is NOT a security gate.
    The authoritative gate is the fd-anchored `O_NOFOLLOW` open + same-descriptor
    `fstat`; the advisory stat never authorizes a read/exec, so it introduces no
    TOCTOU (a swap after the advisory stat is still caught by O_NOFOLLOW/fstat on
    the real descriptor). `O_NONBLOCK` stops a FIFO from blocking the open
    (R2-B1). Executes nothing.

    Raises `_UnsafeSiblingPath` for a path-policy failure (absent O_NOFOLLOW;
    missing / ENOTDIR; a symlink; ANY non-regular node incl. socket/FIFO/dir —
    R3-1 covers ENXIO/EOPNOTSUPP sockets that `os.open` would otherwise surface
    as non-policy). Lets any OTHER open/read OSError (EIO, EACCES, …) propagate
    UNCHANGED so the caller's original boundary classifies it as today (R2-B2).
    """
    if not hasattr(os, "O_NOFOLLOW"):
        raise _UnsafeSiblingPath("O_NOFOLLOW unavailable; refusing sibling load")  # C-7
    # --- advisory classification only (R3-1); not the safety gate ---
    try:
        pre = os.lstat(path)
    except OSError as error:                  # missing / ENOTDIR
        raise _UnsafeSiblingPath(str(error)) from error
    if stat.S_ISLNK(pre.st_mode) or not stat.S_ISREG(pre.st_mode):
        raise _UnsafeSiblingPath(f"{path} is not a regular file")  # symlink/socket/dir/fifo
    # --- authoritative fd-anchored gate ---
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | getattr(
        os, "O_CLOEXEC", 0
    )
    try:
        fd = os.open(path, flags)             # ELOOP if raced to a symlink
    except OSError as error:
        if error.errno in _PATH_POLICY_ERRNOS:
            raise _UnsafeSiblingPath(str(error)) from error   # raced to missing/symlink
        raise                                 # real I/O fault → caller's boundary
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise _UnsafeSiblingPath(f"{path} is not a regular file")  # race defense
        chunks = []
        while True:
            block = os.read(fd, 65536)        # a real read fault propagates raw
            if not block:
                break
            chunks.append(block)
    finally:
        os.close(fd)
    return b"".join(chunks)


class _SiblingLoadError(ImportError):
    """spec/loader could not be CONSTRUCTED for an already-verified sibling path
    (R4-blocker). Preserves each original site's `if spec is None or spec.loader
    is None` guard. Subclasses `ImportError` so status's and surface-check's
    existing handler tuples (both list `ImportError`) catch it exactly as today;
    fleet-controller (no `ImportError` handler) maps it to `FleetControllerError`
    explicitly. This branch is defensively unreachable for a real `.py` path but
    is required for the `make check` mypy gate (`module_from_spec` rejects
    `ModuleSpec | None`)."""


def _exec_sibling_module(source, path, module_name, *, register):  # -> module
    """Compile+exec ALREADY-READ (fd-verified) source into a module namespace.

    Metadata parity (R3-2): the module object is built with the real
    `spec_from_file_location` + `module_from_spec` pair, so `__spec__`,
    `__loader__`, `__cached__`, `__file__`, `__name__`, `__package__` match what
    the retired loader produced EXACTLY. Neither call reads or execs the file —
    `module_from_spec` only constructs the object. Execution runs on the bytes we
    already read from the verified descriptor via `compile`/`exec`; the spec's
    `loader.exec_module` is NEVER invoked, so no post-verification path re-read
    happens (the whole point of the fix).

    Registration parity (R2-4 / R4): when register=True the module is placed in
    sys.modules BEFORE `compile` — so a compile-time `SyntaxError`/`ValueError`
    ALSO leaves the entry registered, matching today's surface-check where the
    pre-exec registration precedes the failing `exec_module`. All execution
    exceptions propagate UNCHANGED; no cleanup, no sentinel ambiguity.
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise _SiblingLoadError(f"cannot construct loader for {path}")  # R4 guard
    module = importlib.util.module_from_spec(spec)   # real metadata; no I/O, no exec
    if register:
        sys.modules[module_name] = module     # BEFORE compile — parity (R4)
    code = compile(source, str(path), "exec")  # SyntaxError here: entry stays if registered
    exec(code, module.__dict__)               # nosec: trusted sibling, verified fd
    return module
```

Module-level imports (VERIFIED against current files):
- `status.py` has `importlib.util`, `sys` → **add `errno`, `os`, `stat`**.
  `suppress_bytecode_writes` is a local function (L105), already available.
- `surface-check.py` has `importlib.util`, `os`, `stat`, `sys`,
  `from types import ModuleType` → **add `errno`** only.
- `fleet-controller.py` has `importlib.util`, `os`, `stat`, `sys` → **add
  `errno`** only.

`types`/`ModuleType` is NOT required by the helpers (metadata comes from
`module_from_spec`; the `_exec_sibling_module` return annotation is dropped so
the inline copy needs no `ModuleType` import in status/fleet-controller). `Path`
is already imported in all three. Do not duplicate existing imports.

Key properties:
- The safety check (`O_NOFOLLOW` open + `fstat`) and the read share one
  descriptor. There is no window where the path can be swapped for a symlink
  between check and read (C-6 closes the TOCTOU).
- **Fail closed (C-7):** absent `O_NOFOLLOW` raises `_UnsafeSiblingPath` rather
  than silently loading with no symlink protection.
- **No FIFO hang (R2-B1):** `O_NONBLOCK` is in the open flags, so a FIFO returns
  a valid fd immediately; the advisory `lstat` already refuses it as non-regular
  first. On a regular file `O_NONBLOCK` is a no-op for reads.
- **All non-regular nodes classified as policy (R3-1):** the advisory `lstat`
  rejects symlink / socket / FIFO / directory as `_UnsafeSiblingPath` *before*
  `os.open`, so a Unix socket (which `os.open` would surface as `ENXIO`/Linux or
  `EOPNOTSUPP`/macOS — non-policy errnos) still routes to `unavailable` (status)
  / `SurfaceInputError` (surface-check), matching today's `is_file()` precheck.
  The advisory stat is classification-only; the fd `O_NOFOLLOW`+`fstat` remains
  the sole security authority, so no TOCTOU is introduced.
- **Exact failure classification (R2-B2):** only path-policy failures raise
  `_UnsafeSiblingPath`; a genuine open/read I/O `OSError` (EIO, EACCES…)
  propagates to the caller's original boundary — status `invalid`,
  surface-check/fleet-controller raw — identical to today.
- **True metadata parity (R3-2):** `_exec_sibling_module` builds the module via
  the real `spec_from_file_location`+`module_from_spec`, so `__spec__` /
  `__loader__` / `__cached__` / `__file__` / `__name__` / `__package__` are
  byte-identical to the retired loader's. Only execution differs: `compile`/
  `exec` of the fd-read bytes, never `loader.exec_module`. No false "None ==
  equivalent" claim.
- **Bytecode-write suppression retained (R3-3):** the two status sites keep
  wrapping the module-load (`_exec_sibling_module`) — but not the subsequent
  helper-callable invocation — in `suppress_bytecode_writes()`, exactly as today
  (status.py L810/L1208). surface-check/fleet-controller had no such wrapper and
  gain none.
- **Registration is opt-in and parity-exact (C-5/M5, R2-4):** only surface-check
  passes `register=True`, registering `sys.modules[name]` BEFORE exec and — like
  today — LEAVING that entry on a failing exec (no cleanup, no `dict.get`/`None`
  sentinel ambiguity). status.py and fleet-controller pass `register=False`,
  never registering, as today.
- `O_NOFOLLOW` refuses a symlinked **final** component race-free. The old guard
  also had a `helper.parent.is_symlink()` branch, but the parent is derived from
  a **canonical** path — `Path(__file__).resolve().with_name(...)` in status.py
  (verified L800/L1192) and `SCRIPT_DIR = Path(__file__).resolve().parent`
  (verified fleet-controller L24). `.resolve()` collapses every symlink in the
  parent chain, so the parent is a real directory and its `is_symlink()` branch
  could never fire. Dropping it is therefore not a coverage regression; the
  fd-anchored `O_NOFOLLOW`+`fstat` on the final component is the whole residual
  risk.
- `surface-check.py._load_source_module` builds `root / relative` where the old
  guard was only `not path.is_file() or path.is_symlink()` — it never checked
  intermediate parents of a multi-segment `relative` either. So O_NOFOLLOW is at
  least as strong as the prior guard there (final-component symlink, now
  race-free) and introduces no regression; intermediate-dir following is
  unchanged from current behavior and out of scope for this finding.

## Placement — inline per file

`status.py` already imports `sd_ai_command_pack_lib` (L24), so a shared-lib
loader would add no new dependency *there* — but `surface-check.py` and
`fleet-controller.py` do **not** import that lib, so routing them through it
would add a runtime import to two installed/standalone scripts. Rather than make
the placement asymmetric, inline the two private helpers
(`_read_trusted_sibling_source`, `_exec_sibling_module`) in each of the three
files. ~25 lines; uniform self-containment across all three is cheaper and
lower-risk than one shared import that only one of them already has.

## Sites and their exact per-caller wiring

Only a **path-policy** failure (`_UnsafeSiblingPath`: missing / symlink /
non-regular / no-O_NOFOLLOW) takes the "unavailable/raise" branch. A
non-policy open/read `OSError` (EIO, EACCES…) and every **exec** exception run
under the caller's **existing** handler, so post-load classification is
byte-for-byte preserved (C-6, R2-B2). Each site is one `try` with the policy
`except` listed **first** (it's an `OSError` subclass, so ordering matters):

| File / function | register | `_UnsafeSiblingPath` → | everything else (read-I/O + exec), unchanged from today → |
|---|---|---|---|
| `status.py` `collect_work_loop` (L800) | False | return `{"status":"unavailable","error":"work-loop helper is not installed"}` | existing `except (Attr,Import,Key,OSError,Runtime,Syntax,Type,Value)` → `{"status":"invalid",…}` |
| `status.py` recovery classify (L1192) | False | return `{"status":"unavailable","error":"recovery-artifacts helper is not installed"}` | same existing invalid-classifier |
| `surface-check.py` `_load_source_module` (L212) | True | raise `SurfaceInputError("missing source validator module: …")` | existing `except (Import,Runtime,SystemExit,Type,Value)` → `SurfaceInputError("cannot load …")`; a non-policy `OSError` during read **or** exec still propagates raw, as today |
| `fleet-controller.py` `_wave_planner` (L127) | False | `except (_UnsafeSiblingPath, _SiblingLoadError)` → raise `FleetControllerError("fleet wave planner cannot be loaded")` (preserves today's spec-None → FleetControllerError) | non-policy read/exec errors propagate raw, as today (it had no guard) |

Concrete shape per site — read, exec, and use share ONE try so a non-policy
read fault lands in the same handler that a non-policy exec fault does today:

```python
try:
    source = _read_trusted_sibling_source(p)
    module = _exec_sibling_module(source, p, name, register=…)
    <use module>                       # e.g. module.status_snapshot(repo)
except _UnsafeSiblingPath:             # FIRST — peel off path policy
    <unavailable / raise policy error>
except (<original handler tuple>):     # UNCHANGED — reclassifies exactly as today
    <original invalid/raise handler>
```

**Status sites additionally wrap the load in `suppress_bytecode_writes()`
(R3-3)** — preserving today's boundary, which covers the module load but NOT the
subsequent helper-callable call:

```python
try:
    source = _read_trusted_sibling_source(helper)
    with suppress_bytecode_writes():                 # today's L810/L1208 scope
        module = _exec_sibling_module(source, helper, name, register=False)
    result = module.status_snapshot(repo)            # outside the with, as today
except _UnsafeSiblingPath:
    return {"status": "unavailable", …}
except (Attr, Import, Key, OSError, Runtime, Syntax, Type, Value):
    return {"status": "invalid", …}
```

surface-check and fleet-controller have no such wrapper today and add none; their
original handlers do **not** list `OSError`, so a non-policy read/exec `OSError`
isn't caught by either `except` and propagates raw — matching today, where the
retired `exec_module` `OSError` also propagated raw.

**Spec-construction guard (R4).** `_exec_sibling_module` raises
`_SiblingLoadError(ImportError)` if `spec`/`spec.loader` is `None`, preserving
each site's existing guard: status's tuple lists `ImportError` → `invalid`;
surface-check's tuple lists `ImportError` → `SurfaceInputError`; fleet-controller
lists it explicitly (`except (_UnsafeSiblingPath, _SiblingLoadError)`) →
`FleetControllerError`. Defensively unreachable for a real `.py` path, but
required so `module_from_spec` never receives `ModuleSpec | None` (the `make
check` mypy gate). (surface-check's spec-None message shifts from "cannot load
source validator module" to the "cannot load {relative}: …" branch — same
`SurfaceInputError` type, an accepted nuance on an unreachable path.)

**Metadata note (R3-2).** `_exec_sibling_module` builds the module with the real
`spec_from_file_location`+`module_from_spec`, so its metadata
(`__spec__`/`__loader__`/`__cached__`/`__file__`/`__name__`/`__package__`) is
byte-identical to the retired loader's; only execution differs (`compile`/`exec`
of fd-read bytes, never `loader.exec_module`). The valid-load test asserts the
real spec/loader/cached values, not `None`s.

## Twin discipline (canonical)

`templates/**` is the **source of truth** for shipped files; root `scripts/`
copies are **mirrors** refreshed by `make sync` (CONTRIBUTING.md:120-122).
Therefore: edit `templates/scripts/sd-ai-command-pack-status.py` and
`templates/scripts/sd-ai-command-pack-surface-check.py` (source), then let `make
sync` / `make release-prep` mirror them to root `scripts/`. Do **not** hand-edit
the root mirrors. `fleet-controller.py` has **no** `templates/scripts/` copy
(verified) — it is a source-only file living directly in `scripts/`, so it is
edited in `scripts/` directly.

## Tests (R4)

### Honest framing of what is testable (C-5)

A **static** symlink is already rejected by the pre-fix `is_symlink()` guard, so
a static-symlink fixture passes on both old and new code and proves nothing about
the TOCTOU (the existing `test_collect_recovery_rejects_symlinked_helper` /
`…work_loop…` at test_status.py:1487/1504 are exactly this — they stay valid but
are not the regression test). The race itself cannot be triggered deterministically
without a swap hook. So the tests assert the **new loader's contract** plus a
**seam differential**, not a false "fails on pre-fix" claim.

### New module `tests/test_helper_loader_safety.py`

Load each shipped/source file as a module (ordinary `spec_from_file_location`
under the existing `install_test_support` harness — this is trusted test-time
loading, not a security seam) and exercise its inlined helpers:

1. **valid load + metadata parity (R3-2)** — real sibling `.py` with
   `SENTINEL = 1`; assert the loaded module has `SENTINEL == 1` **and** that its
   metadata equals what a real `spec_from_file_location`+`module_from_spec` on
   the same path yields: `__name__ == module_name`, `__file__ == str(p)`,
   `__package__ == ""`, `__spec__` is a `ModuleSpec` for that path, `__loader__`
   is a `SourceFileLoader`, `__cached__` equals `importlib.util.cache_from_source
   (str(p))`. (Assert the real values — NOT `None`.)
2. **symlink rejected** — `p` is a symlink → attacker file that writes a marker
   on import; assert `_read_trusted_sibling_source(p)` raises `_UnsafeSiblingPath`
   **and** the marker was never written (attacker code not executed).
3. **non-regular rejected** — `p` is a directory / FIFO / **Unix socket** (R3-1)
   → `_UnsafeSiblingPath`. The FIFO/socket cases must return promptly (the
   advisory `lstat` refuses before any blocking `os.open`; also proves
   `O_NONBLOCK`, R2-B1), not block.
4. **seam differential (documents the closed hazard)** — same symlink `p`:
   assert the old pattern would have followed it —
   `importlib.util.spec_from_file_location(name, p)` + `exec_module` loads the
   attacker sentinel — while `_read_trusted_sibling_source(p)` refuses. Same
   input, opposite outcome: the fix's value, deterministically.
5. **register semantics (M5, R2-4)** — `register=True` sets `sys.modules[name]`
   and, on a **failing** exec, LEAVES that entry (matches today's surface-check —
   no cleanup); `register=False` never sets it.
6. **fleet-controller coverage (M4)** — repeat 1–2 against its inlined helpers.
7. **status classification (R3-1/R3-3)** — for a status site: a socket path →
   `unavailable`. Bytecode-suppression must assert all THREE properties (R4), not
   just restoration (a restore-only test passes even if suppression were removed):
   (a) during the load the executing helper observes `sys.dont_write_bytecode ==
   True`; (b) the helper CALLABLE invoked after the `with` observes the prior
   value; (c) the prior value is restored after BOTH a successful and a failing
   load. Adapt the existing test at test_status.py:1345.
8. **raced-symlink authoritative branch (R4)** — the static symlink tests all
   exit via the advisory `lstat`, never reaching the fd gate. Add one test that
   mocks `os.lstat` to return regular-file metadata while the real path is a
   symlink, then assert `_read_trusted_sibling_source` raises `_UnsafeSiblingPath`
   with `ELOOP` as the cause (`error.__cause__.errno == errno.ELOOP`) and the
   attacker code never executed — exercising the `O_NOFOLLOW`+`_PATH_POLICY_ERRNOS`
   path, the actual TOCTOU-closing branch.

### Rewrite existing old-seam tests (M4)

`test_status.py` mocks the retired importlib seam and must be reworked to the new
one:
- `test_collect_work_loop_handles_helper_contract_and_syntax_failures`
  (L963) — currently patches `spec_from_file_location` /
  `spec.loader.exec_module.side_effect`. Replace the mock with a **real** temp
  helper whose source has a `SyntaxError` / returns a non-dict, and assert
  `status == "invalid"` (post-load classification path, now reached via the real
  `exec`).
- Audit L1433 and neighbors for the same mocked seam; convert to real temp
  helpers. Keep the static-symlink tests (1487/1504) — still valid.

Run: `.venv/bin/python -m unittest tests.test_helper_loader_safety tests.test_status -v` → all pass.

## Release plumbing (R5) — canonical order (M6)

`make release-prep` (`prepare_release()`) itself runs, in order,
generate-command-surfaces → `install.py . --force` (mirror/self-sync) →
update-spec-kb → the version+CHANGELOG payload gate → the conditional full-fleet
candidate-ledger refresh → `make check`. So the manual steps are only:

1. Edit `templates/scripts/…` sources (status, surface-check) + `scripts/…`
   fleet-controller; add tests.
2. Bump `manifest.json` 0.64.2 → 0.64.3.
3. Add the `## 0.64.3 - <date>` heading to `CHANGELOG.md` (the payload gate
   requires it to match the manifest version) **before** running release-prep.
4. `make release-prep` — it performs generation, root-mirror sync, ledger
   refresh, and the full check. Do **not** hand-run `make generate`, hand-edit
   root mirrors, or hand-regenerate the ledger.

## Alternatives considered

- **Operator override, keep 0.64.2**: rejected — bypasses the deterministic
  security gate on prose rationale, which the fleet contract forbids, and leaves
  the racy pattern shipped.
- **Shared-lib loader**: rejected — `surface-check.py`/`fleet-controller.py` do
  not import `sd_ai_command_pack_lib`, so it would add a runtime import to two
  standalone scripts; inline keeps all three self-contained.
- **`resolve()` + re-check**: rejected — still a check-then-use with a window;
  only an fd-anchored check removes the race.
- **Always-register in sys.modules**: rejected (M5) — changes status/controller
  behavior; registration is opt-in per caller.

## Rollback

Single squashable commit on `fix/harden-helper-loader-toctou`. Revert = drop the
branch; 0.64.2 remains the tagged release. No consumer has moved (campaign
blocked before any push/PR; rwbp-coordinator reset to clean main).
