# Design: review_preflight in-process install conversion

## Files changed

- `tests/test_review_preflight.py` — only this file. No production code, no test
  support, no CI scripts.

## The twin contract (from `tests/install_test_support.py`)

- `run_install(root, *args, skip_diff_check=True, extra_env=None)` — spawns
  `[sys.executable, INSTALLER, root, *args]` as a subprocess, merged
  stdout/stderr, returns `CompletedProcess`.
- `run_install_inproc(root, *args, skip_diff_check=True)` — calls
  `install.main([str(root), *args])` in-process under
  `redirect_stdout/redirect_stderr`, returns a `CompletedProcess` with the same
  `returncode`/`stdout` shape. No `extra_env` parameter.

Docstring guidance (authoritative): use in-proc "only for tests that install
then inspect the filesystem/return code"; keep subprocess for tests depending on
"argv/CLI parsing, `os.environ` / PATH isolation, `SystemExit` as process exit
status, or the symlink-exec entry."

## Observed call shape in review_preflight

- 54 `self.run_install(...)` call sites, 0 `run_install_inproc`, 0 passing
  `extra_env=`. Two sites run inside `subTest` loops
  (`test_review_preflight.py:1263-1266`, `:3696-3699`), so a non-skipped run
  executes ~56 installer invocations from 54 static sites.
- Dominant form: `self.assertEqual(self.run_install(root).returncode, 0)` or
  `result = self.run_install(root); self.assertEqual(result.returncode, 0, ...)`,
  followed by git config/add/commit and the preflight-under-test. Install is a
  fixture bootstrap; the unit under test is the preflight script, not install.py.

## Conversion rule (per call site)

All 54 sites are expected to CONVERT. Expected post-edit static counts:
**0 `run_install`, 54 `run_install_inproc`.** None passes `extra_env=`, none
asserts installer process semantics — every call is a fixture bootstrap whose
result is used only for `returncode`/`stdout`. This is still a read-each-site
edit (confirm the rule holds per site), not a blind replace, and any genuine
exception found at edit time may stay `run_install` with a one-line reason.

Explicit note (C-4): `test_review_preflight.py:713-715`
(`..._runs_via_symlink...`) is CONVERT. The symlink it creates and executes is
the installed Node preflight script (`:716-729`), NOT the installer symlink-exec
entry that `install_test_support.py:1123-1126` excludes. The test name is not a
signal to keep subprocess.

## Coverage preservation (C3 — resolved: not review_preflight's job)

`install.py` reaches 100% partly via the subprocess entry
(`install.py:873-874` `__main__`->`SystemExit(main())`) and the bad-flag
`SystemExit` at `:703/:705`, which `install.main(argv)` does not itself
exercise. These are already owned by dedicated tests independent of
review_preflight: the `:703` bad-flag `SystemExit` (`--backup requires --force`)
at `test_install_core.py:2358` (`test_backup_requires_force`), the `:705`
bad-flag `SystemExit` (`--skip-trellis-init requires --local-only`) at `:2690`
(`test_skip_trellis_init_requires_local_only`), and the installer symlink-exec
entry at `:2204-2219`. Converting review_preflight therefore cannot drop that
coverage.

Verification stays empirical (run the gate after conversion), but the recovery
path is NOT to un-convert review_preflight fixture calls (that would violate
scope and AC1). If the gate somehow drops below 100%, STOP and re-scope: add a
focused installer-entry test that owns the uncovered line, rather than reverting
in-scope conversions.

## Global-state safety (C5)

`install.main` runs in the test process, and a test module is a single process
running all its methods (`run-tests.sh` shards by module, so cross-shard leakage
is impossible but SAME-module leakage between the 54 in-proc installs is the real
risk). Risks: `install.main` chdir without restore, mutating `os.environ`, or
reading `sys.argv`. `run_install_inproc` passes argv explicitly (no `sys.argv`
reliance), and 21 in-proc uses already exist in `test_install_core`.

Do not treat "the sharded run passed" as proof of isolation (a same-module leak
can pass silently). Validation is an explicit snapshot: capture `Path.cwd()`,
`os.environ`, and `sys.argv` immediately before and after one in-process install
and assert they are unchanged (a throwaway probe during implementation is
enough; it need not ship). If any diverges, that site stays subprocess or the
containment is re-scoped explicitly.

## Alternatives rejected

- Oversubscribe workers — tried, ~6% on 4-core CI (PR #312). Rejected.
- Larger runners — paid even for public repos; ~$40-60/mo to save ~1.5min.
  Rejected.
- Split the module into multiple files for finer sharding — does not reduce
  total work; the sum/cores floor dominates on 4 cores. Deferred.

## Rollback

Single-file, test-only change. Revert `tests/test_review_preflight.py` to
restore every call to `run_install`. No production or CI-config impact.
