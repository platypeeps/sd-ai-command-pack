# Design — Tolerate temp-dir teardown races in the install test helpers

## Scope decision: shared helpers only

The fix covers the four temp-tree call sites in `tests/install_test_support.py`
(`make_repo`, `make_git_repo_without_trellis`, `make_planning_housekeeping_repo`,
`make_housekeeping_repo`). The remaining `tempfile.TemporaryDirectory(` call
sites under `tests/` are left alone.

### Why the rest are excluded

The hazard needs a *second process* writing into the tree while `shutil.rmtree`
walks it. In this repository the only such writer is git's detached auto-gc, and
it exists only where a test hosts a git repository. All four helper sites do
(`git init`, `git init --bare`, or a `copytree`-cloned template whose `.git`
comes with it). Extending the change to every call site would rewrite hundreds
of lines across ~84 modules to buy tolerance for trees that no background
process ever touches, and would spread errno suppression across code where an
`ENOTEMPTY` would be a real bug rather than a race.

### Residual risk of the excluded set

A per-test `TemporaryDirectory` that is *not* covered here can still hit the race
if a future test starts a git repository (or any other background writer, e.g. a
spawned installer subprocess that outlives its assertion) inside its own temp
tree instead of going through the shared helpers. That is not currently the case.
The cheap mitigation if it ever appears is to route the new site through
`InstallTestCase.make_temp_root`, which is why the tolerance lives in a named,
reusable helper rather than inline in each of the four call sites.

## Mechanism

`tempfile.TemporaryDirectory` gives no way to pass a custom `shutil.rmtree`
error handler; its only knob is `ignore_cleanup_errors=True`, which installs an
ignore-everything handler and would violate the PRD constraint that unrelated
teardown errors stay visible. So the helpers switch from
`TemporaryDirectory` + `addCleanup(tempdir.cleanup)` to
`tempfile.mkdtemp` + `addCleanup(remove_tree_tolerating_teardown_race, root)`.
Callers keep receiving a plain `Path`, so nothing downstream changes — the same
`mkdtemp` + `addClassCleanup(shutil.rmtree, template_root, ignore_errors=True)`
pattern was already in use for the cached housekeeping template.

`remove_tree_tolerating_teardown_race` suppresses exactly `OSError` with
`errno.ENOTEMPTY` (39 on Linux, 66 on macOS) or `errno.EEXIST` (the same `rmdir`
refusal on platforms that report it that way), and re-raises everything else.
The handler is installed per call, so nothing outside that one removal is
affected.

Both `shutil.rmtree` handler shapes are covered: `onexc(func, path, exc)` on
Python 3.12+, `onerror(func, path, exc_info)` on 3.10/3.11, dispatched on
`sys.version_info` and sharing one predicate.

## Reproduction

Reproducing the real race is explicitly not an acceptance criterion, and it is
not attempted. Confidence rests on the mechanism plus direct tests of the
cleanup path: `tests/test_install_test_support_cleanup.py` drives both handler
shapes with a synthetic `ENOTEMPTY`, drives the real `shutil.rmtree` with
`os.rmdir` raising `ENOTEMPTY` once, forces both version branches, asserts
unrelated errors still propagate, and asserts a tree from
`make_git_repo_without_trellis` tears down cleanly while `os.rmdir` loses one
race.
