"""Teardown-race tolerance for the shared install test helpers.

Every temporary tree ``InstallTestCase`` builds hosts a git repository, and
git's automatic garbage collection is a *detached* process: it can create a
file under a directory in the window between ``shutil.rmtree``'s scandir and
its ``rmdir``, so removal fails with ``ENOTEMPTY`` after the test body has
already passed.

The real race is a timing window against a separate process and is not
reproducible on demand (holding a file open does not block ``unlink`` on
POSIX). These tests therefore drive the cleanup path directly with a synthetic
``ENOTEMPTY``, on *both* ``shutil.rmtree`` handler shapes -- ``onexc`` on
Python 3.12+, ``onerror`` on 3.10/3.11.
"""

from __future__ import annotations

import inspect
import warnings

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

errno = _support.errno
os = _support.os
shutil = _support.shutil
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path

InstallTestCase = _support.InstallTestCase
remove_tree_tolerating_teardown_race = _support.remove_tree_tolerating_teardown_race
_rmtree_onerror = _support._rmtree_onerror
_rmtree_onexc = _support._rmtree_onexc
_TEARDOWN_RACE_ERRNOS = _support._TEARDOWN_RACE_ERRNOS


class RmtreeHandlerShapeTest(unittest.TestCase):
    """Both handler shapes, exercised on every interpreter regardless of version."""

    def test_linux_directory_not_empty_is_errno_39(self) -> None:
        # The reported flake is "OSError: [Errno 39] Directory not empty".
        # 39 is ENOTEMPTY on Linux (the CI platform); macOS numbers it 66, so
        # the handler matches on the symbolic constant, not the literal.
        if sys.platform.startswith("linux"):
            self.assertEqual(errno.ENOTEMPTY, 39)
        self.assertIn(errno.ENOTEMPTY, _TEARDOWN_RACE_ERRNOS)

    def test_onexc_swallows_the_race(self) -> None:
        for code in sorted(_TEARDOWN_RACE_ERRNOS):
            with self.subTest(errno=code):
                exc = OSError(code, "Directory not empty")
                self.assertIsNone(_rmtree_onexc(os.rmdir, "/nonexistent", exc))

    def test_onerror_swallows_the_race(self) -> None:
        for code in sorted(_TEARDOWN_RACE_ERRNOS):
            with self.subTest(errno=code):
                exc = OSError(code, "Directory not empty")
                self.assertIsNone(
                    _rmtree_onerror(os.rmdir, "/nonexistent", (OSError, exc, None))
                )

    def test_onexc_reraises_unrelated_oserror(self) -> None:
        exc = PermissionError(errno.EACCES, "Permission denied")
        with self.assertRaises(PermissionError):
            _rmtree_onexc(os.rmdir, "/nonexistent", exc)

    def test_onerror_reraises_unrelated_oserror(self) -> None:
        exc = FileNotFoundError(errno.ENOENT, "No such file or directory")
        with self.assertRaises(FileNotFoundError):
            _rmtree_onerror(os.rmdir, "/nonexistent", (FileNotFoundError, exc, None))

    def test_non_oserror_is_reraised(self) -> None:
        exc = RuntimeError("leaked mock")
        with self.assertRaises(RuntimeError):
            _rmtree_onexc(os.rmdir, "/nonexistent", exc)
        with self.assertRaises(RuntimeError):
            _rmtree_onerror(os.rmdir, "/nonexistent", (RuntimeError, exc, None))


class _RmdirRacer:
    """Stand-in for ``os.rmdir`` that loses one race, then behaves normally."""

    def __init__(self, exc: OSError) -> None:
        self._exc = exc
        self._real = os.rmdir
        self.raised = False

    def __call__(self, *args: object, **kwargs: object) -> None:
        if not self.raised:
            self.raised = True
            raise self._exc
        self._real(*args, **kwargs)  # type: ignore[arg-type]


class RemoveTreeTest(unittest.TestCase):
    def _tree(self) -> Path:
        base = Path(tempfile.mkdtemp(prefix="sd-ai-command-pack-rmtree-test-"))
        self.addCleanup(shutil.rmtree, base, True)
        (base / "nested" / "deeper").mkdir(parents=True)
        (base / "nested" / "deeper" / "file.txt").write_text("x", encoding="utf-8")
        return base

    def test_installs_the_handler_kwarg_for_this_interpreter(self) -> None:
        expected = "onexc" if sys.version_info >= (3, 12) else "onerror"
        with mock.patch.object(shutil, "rmtree") as rmtree:
            remove_tree_tolerating_teardown_race("/nonexistent")
        self.assertEqual(list(rmtree.call_args.kwargs), [expected])

    def test_selects_the_handler_shape_per_python_version(self) -> None:
        # Only one branch is reachable on the interpreter running this suite,
        # so the other is forced. The CI matrix spans both (3.10 and 3.13).
        cases = (
            ((3, 10, 0), "onerror", _rmtree_onerror),
            ((3, 11, 0), "onerror", _rmtree_onerror),
            ((3, 12, 0), "onexc", _rmtree_onexc),
            ((3, 13, 0), "onexc", _rmtree_onexc),
        )
        for version, kwarg, handler in cases:
            with self.subTest(version=version):
                with mock.patch.object(sys, "version_info", version):
                    with mock.patch.object(shutil, "rmtree") as rmtree:
                        remove_tree_tolerating_teardown_race("/nonexistent")
                self.assertEqual(list(rmtree.call_args.kwargs), [kwarg])
                self.assertIs(rmtree.call_args.kwargs[kwarg], handler)

    @unittest.skipUnless(
        "onerror" in inspect.signature(shutil.rmtree).parameters,
        "shutil.rmtree no longer accepts the 3.10/3.11 onerror handler",
    )
    def test_real_rmtree_returns_via_the_onerror_shape(self) -> None:
        # The 3.10/3.11 wiring, driven through the real rmtree on whatever
        # interpreter is running: rmtree still accepts onerror after 3.12.
        base = self._tree()
        racer = _RmdirRacer(OSError(errno.ENOTEMPTY, "Directory not empty"))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with mock.patch.object(os, "rmdir", new=racer):
                shutil.rmtree(base, onerror=_rmtree_onerror)
        self.assertTrue(racer.raised)

    def test_real_rmtree_returns_when_the_race_fires(self) -> None:
        base = self._tree()
        racer = _RmdirRacer(OSError(errno.ENOTEMPTY, "Directory not empty"))
        with mock.patch.object(os, "rmdir", new=racer):
            remove_tree_tolerating_teardown_race(base)
        self.assertTrue(racer.raised)

    def test_real_rmtree_propagates_an_unrelated_error(self) -> None:
        base = self._tree()
        racer = _RmdirRacer(PermissionError(errno.EACCES, "Permission denied"))
        with mock.patch.object(os, "rmdir", new=racer):
            with self.assertRaises(PermissionError):
                remove_tree_tolerating_teardown_race(base)

    def test_clean_tree_is_fully_removed(self) -> None:
        base = self._tree()
        remove_tree_tolerating_teardown_race(base)
        self.assertFalse(base.exists())


class HelperTempTreeRaceTest(InstallTestCase):
    """Acceptance: a tree from the shared helpers survives a racing writer.

    ``addCleanup`` is LIFO, so the registration order below yields the run
    order: helper tree removal (with ``os.rmdir`` racing), then unpatch, then a
    best-effort sweep of whatever the lost race left behind.
    """

    def test_helper_tree_teardown_survives_concurrent_writer(self) -> None:
        leftovers: dict[str, Path] = {}
        def sweep_leftovers() -> None:
            root = leftovers.get("root")
            if root is not None:
                shutil.rmtree(root, ignore_errors=True)

        self.addCleanup(sweep_leftovers)
        racer = _RmdirRacer(OSError(errno.ENOTEMPTY, "Directory not empty"))
        patcher = mock.patch.object(os, "rmdir", new=racer)
        self.addCleanup(patcher.stop)

        root = self.make_git_repo_without_trellis()
        leftovers["root"] = root
        self.assertTrue((root / ".git").is_dir())

        # From here on the only remaining work is teardown; if the helper's
        # cleanup cannot absorb the race this test errors after passing.
        patcher.start()


if __name__ == "__main__":
    unittest.main()
