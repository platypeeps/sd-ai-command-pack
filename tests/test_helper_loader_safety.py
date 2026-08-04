"""Direct safety/contract tests for the atomic sibling-module loader shared by
status, surface-check, and fleet-controller (the 0.64.3 TOCTOU hardening).

These exercise the inlined ``_read_trusted_sibling_source`` /
``_exec_sibling_module`` helpers against REAL temporary files, never the retired
``spec_from_file_location`` + ``exec_module`` seam.
"""

from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:  # pragma: no cover - import shim
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

import errno
import importlib.util
import os
import socket
import stat  # noqa: F401 - kept for parity with the module under test
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

unittest = _support.unittest
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

SCRIPTS = {
    "status": PACK_ROOT / "templates/scripts/sd-ai-command-pack-status.py",
    "surface": PACK_ROOT / "templates/scripts/sd-ai-command-pack-surface-check.py",
    "controller": PACK_ROOT / "scripts/sd-ai-command-pack-fleet-controller.py",
}


class HelperLoaderSafetyTests(InstallTestCase):
    """Contract and TOCTOU-safety tests for the shared sibling loader."""

    def _load(self, key: str):
        return self.load_module_from_path(SCRIPTS[key], f"loader_safety_{key}")

    def _all(self):
        return [(key, self._load(key)) for key in SCRIPTS]

    def _run_with_timeout(self, fn, *args, timeout: float = 5.0):
        """Run ``fn`` in a daemon thread and fail if it does not return promptly.

        Proves the loader never blocks on a FIFO/socket (advisory ``lstat``
        refuses before any blocking ``os.open``).
        """
        outcome: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                fn(*args)
            except BaseException as error:  # noqa: BLE001 - forwarded to caller
                outcome["error"] = error

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout)
        self.assertFalse(
            thread.is_alive(), "loader blocked on a non-regular node (no O_NONBLOCK?)"
        )
        return outcome.get("error")

    def test_valid_load_returns_module_with_metadata_parity(self) -> None:
        for key, mod in self._all():
            with self.subTest(script=key), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sibling.py"
                path.write_text(
                    "SENTINEL = 41\ndef go():\n    return SENTINEL + 1\n",
                    encoding="utf-8",
                )
                name = f"loader_safety_target_{key}"
                self.addCleanup(sys.modules.pop, name, None)
                source = mod._read_trusted_sibling_source(path)
                loaded = mod._exec_sibling_module(source, path, name, register=False)

                self.assertEqual(loaded.SENTINEL, 41)
                self.assertEqual(loaded.go(), 42)

                # Metadata must match what the real spec_from_file_location +
                # module_from_spec pair produces (R3-2 parity, not None).
                spec = importlib.util.spec_from_file_location(name, path)
                reference = importlib.util.module_from_spec(spec)
                self.assertEqual(loaded.__name__, reference.__name__)
                self.assertEqual(loaded.__file__, reference.__file__)
                self.assertEqual(loaded.__package__, reference.__package__)
                self.assertEqual(loaded.__cached__, reference.__cached__)
                self.assertEqual(
                    loaded.__cached__, importlib.util.cache_from_source(str(path))
                )
                self.assertIsNotNone(loaded.__spec__)
                self.assertEqual(loaded.__spec__.name, name)
                self.assertEqual(
                    type(loaded.__loader__).__name__, "SourceFileLoader"
                )

    def test_symlink_source_is_rejected_without_execution(self) -> None:
        for key, mod in self._all():
            with self.subTest(script=key), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                marker = tmp_path / "pwned.txt"
                attacker = tmp_path / "attacker.py"
                attacker.write_text(
                    f"import pathlib\npathlib.Path({str(marker)!r}).write_text('x')\n",
                    encoding="utf-8",
                )
                link = tmp_path / "sibling.py"
                link.symlink_to(attacker)
                with self.assertRaises(mod._UnsafeSiblingPath):
                    mod._read_trusted_sibling_source(link)
                self.assertFalse(marker.exists())

    def test_non_regular_nodes_rejected_promptly(self) -> None:
        mod = self._load("status")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            directory = tmp_path / "a-dir"
            directory.mkdir()
            with self.assertRaises(mod._UnsafeSiblingPath):
                mod._read_trusted_sibling_source(directory)

            missing = tmp_path / "absent.py"
            with self.assertRaises(mod._UnsafeSiblingPath):
                mod._read_trusted_sibling_source(missing)

            fifo = tmp_path / "a-fifo"
            os.mkfifo(fifo)
            error = self._run_with_timeout(mod._read_trusted_sibling_source, fifo)
            self.assertIsInstance(error, mod._UnsafeSiblingPath)

            sock_path = tmp_path / "a-sock"
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(sock_path))
                error = self._run_with_timeout(
                    mod._read_trusted_sibling_source, sock_path
                )
                self.assertIsInstance(error, mod._UnsafeSiblingPath)
            finally:
                server.close()

    def test_enotdir_parent_maps_to_missing(self) -> None:
        # A non-directory parent component makes the advisory ``lstat`` raise
        # ENOTDIR. That means no regular file is resolvable at the path, so the
        # verdict is ``missing`` ("not found"), not ``non_regular`` ("present but
        # refused"). This exercises the ADVISORY ``lstat`` branch (the open is
        # never reached). status/surface must agree.
        for key in ("status", "surface"):
            mod = self._load(key)
            with self.subTest(script=key), tempfile.TemporaryDirectory() as tmp:
                not_a_dir = Path(tmp) / "file.py"
                not_a_dir.write_text("SENTINEL = 1\n", encoding="utf-8")
                buried = not_a_dir / "sibling.py"
                with self.assertRaises(mod._UnsafeSiblingPath) as ctx:
                    mod._read_trusted_sibling_source(buried)
                self.assertEqual(ctx.exception.reason, "missing")

    def test_enotdir_authoritative_branch_maps_to_missing(self) -> None:
        # The advisory test above never reaches the fd-anchored ``os.open``. Force
        # the AUTHORITATIVE branch: mock ``os.lstat`` to report a regular file so
        # the advisory check passes, but point the real path at a non-directory
        # parent so the actual ``os.open(..., O_NOFOLLOW)`` raises ENOTDIR. Both
        # branches must map ENOTDIR to ``missing`` (advisory/authoritative parity).
        for key in ("status", "surface"):
            mod = self._load(key)
            with self.subTest(script=key), tempfile.TemporaryDirectory() as tmp:
                not_a_dir = Path(tmp) / "file.py"
                not_a_dir.write_text("SENTINEL = 1\n", encoding="utf-8")
                buried = not_a_dir / "sibling.py"
                # A genuine regular-file stat_result so the advisory lstat passes
                # (S_ISLNK false, S_ISREG true) and control reaches os.open.
                regular_stat = os.lstat(not_a_dir)
                with mock.patch.object(mod.os, "lstat", return_value=regular_stat):
                    with self.assertRaises(mod._UnsafeSiblingPath) as ctx:
                        mod._read_trusted_sibling_source(buried)
                self.assertEqual(ctx.exception.reason, "missing")

    def test_seam_differential_old_follows_symlink_new_refuses(self) -> None:
        mod = self._load("status")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "target.py"
            target.write_text("SENTINEL = 7\n", encoding="utf-8")
            link = tmp_path / "sibling.py"
            link.symlink_to(target)

            name = "loader_safety_seam"
            self.addCleanup(sys.modules.pop, name, None)
            # The RETIRED seam follows the symlink and loads the target.
            spec = importlib.util.spec_from_file_location(name, link)
            legacy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(legacy)
            self.assertEqual(legacy.SENTINEL, 7)

            # The new safe-read refuses the exact same input.
            with self.assertRaises(mod._UnsafeSiblingPath):
                mod._read_trusted_sibling_source(link)

    def test_register_true_registers_and_leaves_failed_entry(self) -> None:
        mod = self._load("surface")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            ok_path = tmp_path / "ok.py"
            ok_path.write_text("OK = 1\n", encoding="utf-8")
            name_ok = "loader_safety_register_ok"
            self.addCleanup(sys.modules.pop, name_ok, None)
            mod._exec_sibling_module(
                mod._read_trusted_sibling_source(ok_path),
                ok_path,
                name_ok,
                register=True,
            )
            self.assertIn(name_ok, sys.modules)

            # Compile-time failure: pre-exec registration must remain (parity).
            bad_path = tmp_path / "bad.py"
            bad_path.write_text("def broken(:\n", encoding="utf-8")
            name_syntax = "loader_safety_register_syntax"
            self.addCleanup(sys.modules.pop, name_syntax, None)
            with self.assertRaises(SyntaxError):
                mod._exec_sibling_module(
                    mod._read_trusted_sibling_source(bad_path),
                    bad_path,
                    name_syntax,
                    register=True,
                )
            self.assertIn(name_syntax, sys.modules)

            # Runtime failure: entry likewise remains.
            boom_path = tmp_path / "boom.py"
            boom_path.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            name_runtime = "loader_safety_register_runtime"
            self.addCleanup(sys.modules.pop, name_runtime, None)
            with self.assertRaises(RuntimeError):
                mod._exec_sibling_module(
                    mod._read_trusted_sibling_source(boom_path),
                    boom_path,
                    name_runtime,
                    register=True,
                )
            self.assertIn(name_runtime, sys.modules)

    def test_register_false_never_registers(self) -> None:
        mod = self._load("status")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sibling.py"
            path.write_text("OK = 1\n", encoding="utf-8")
            name = "loader_safety_noregister"
            self.addCleanup(sys.modules.pop, name, None)
            mod._exec_sibling_module(
                mod._read_trusted_sibling_source(path), path, name, register=False
            )
            self.assertNotIn(name, sys.modules)

    def test_missing_spec_raises_sibling_load_error(self) -> None:
        # The spec-None guard (R4): module_from_spec must never receive None.
        mod = self._load("status")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sibling.py"
            path.write_text("OK = 1\n", encoding="utf-8")
            source = mod._read_trusted_sibling_source(path)
            with mock.patch.object(
                mod.importlib.util, "spec_from_file_location", return_value=None
            ):
                with self.assertRaises(mod._SiblingLoadError):
                    mod._exec_sibling_module(source, path, "loader_safety_nospec", register=False)

    def test_raced_symlink_caught_by_authoritative_gate(self) -> None:
        # Advisory lstat is classification-only: mock it to report a regular file
        # while the real path is a symlink, and the fd-anchored O_NOFOLLOW gate
        # must still refuse (ELOOP), never executing the attacker (R4).
        mod = self._load("status")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            marker = tmp_path / "pwned.txt"
            attacker = tmp_path / "attacker.py"
            attacker.write_text(
                f"import pathlib\npathlib.Path({str(marker)!r}).write_text('x')\n",
                encoding="utf-8",
            )
            link = tmp_path / "sibling.py"
            link.symlink_to(attacker)

            regular = os.stat(attacker)
            real_lstat = os.lstat

            def fake_lstat(path, *args, **kwargs):
                if str(path) == str(link):
                    return regular
                return real_lstat(path, *args, **kwargs)

            with mock.patch.object(mod.os, "lstat", fake_lstat):
                with self.assertRaises(mod._UnsafeSiblingPath) as caught:
                    mod._read_trusted_sibling_source(link)
            cause = caught.exception.__cause__
            self.assertEqual(getattr(cause, "errno", None), errno.ELOOP)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
