"""The gate's pinned tools (sd:2936): installed from a pin list, first on an opted-in check's `PATH`, refused when missing.

Every archive here is a `.tar.gz` built in a temporary folder and named by a
`file://` URL, so no test reaches the network or the real gate cache. Each
test names one row of the table in docs/work/2026-10-07-gate-pinned-tools/design.md.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import pathlib
import plistlib
import sys
import tarfile
import tempfile
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))
if str(REPO_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tests"))

import sd_gate_receipts  # noqa: E402
import sd_gate_tools  # noqa: E402
import test_sd_gate_offload_rows as rows  # noqa: E402


def archive(folder: pathlib.Path, files: dict[str, str], name: str = "tool.tar.gz") -> tuple[str, str]:
    """A `.tar.gz` in `folder` holding each executable script in `files`, by path: its `file://` URL and sha256."""
    source = folder / f"{name}.d"
    for path, text in files.items():
        (source / path).parent.mkdir(parents=True, exist_ok=True)
        (source / path).write_text(f"#!/bin/sh\n# {text}\n", encoding="utf-8")
        (source / path).chmod(0o755)
    target = folder / name
    with tarfile.open(target, "w:gz") as tar:
        for path in files:
            tar.add(source / path, arcname=path)
    return target.as_uri(), hashlib.sha256(target.read_bytes()).hexdigest()


def pin(url: str, sha256: str, tool: str = "uv", bin_folder: str = "pkg/bin", provides: tuple[str, ...] = ("uv",),
        platform: str | None = None) -> dict[str, Any]:
    return {"tool": tool, "version": "1.0", "platform": platform or sd_gate_tools.this_platform(), "url": url,
            "sha256": sha256, "bin": bin_folder, "provides": provides}


class Install(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name).resolve()
        self.environment = {"SD_GATE_CACHE_DIR": str(self.tmp / "cache")}
        self.url, self.sha256 = archive(self.tmp, {"pkg/bin/uv": "uv 1.0"})

    def pins(self, *entries: dict[str, Any]) -> None:
        patcher = mock.patch.object(sd_gate_tools, "PINS", entries)
        patcher.start()
        self.addCleanup(patcher.stop)

    def verb(self, *argv: str) -> tuple[int, str, str]:
        parser = argparse.ArgumentParser()
        sd_gate_tools.add_tools_verb(parser.add_subparsers(dest="command_name"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sd_gate_tools.tools_verb(parser.parse_args(["tools", *argv]), self.environment)
        return code, out.getvalue(), err.getvalue()

    def test_a_pin_installs_from_its_archive_into_a_folder_named_by_its_digest(self) -> None:
        self.pins(pin(self.url, self.sha256))
        self.assertEqual(self.verb("install")[0], 0)
        folder = self.tmp / "cache" / "pinned-tools" / f"uv-1.0-{self.sha256[:12]}"
        self.assertEqual(sd_gate_tools.path_entries(self.environment), [str(folder / "pkg" / "bin")])
        self.assertIn("# uv 1.0", (folder / "pkg" / "bin" / "uv").read_text(encoding="utf-8"))
        code, out, _ = self.verb("status", "--json")
        self.assertEqual((code, [row["installed"] for row in json.loads(out)]), (0, [True]))
        self.assertEqual(json.loads(out)[0]["folder"], str(folder))
        self.assertEqual(self.verb("status")[1].splitlines()[-1], f"1 pin(s) for {sd_gate_tools.this_platform()}")

    def test_an_installed_copy_is_left_alone(self) -> None:
        self.pins(pin(self.url, self.sha256))
        sd_gate_tools.install(self.environment)
        mark = pathlib.Path(sd_gate_tools.path_entries(self.environment)[0], "mark")
        mark.write_text("kept", encoding="utf-8")
        self.assertEqual([result["action"] for result in sd_gate_tools.install(self.environment)], ["present"])
        self.assertTrue(mark.is_file())

    def test_a_wrong_digest_installs_nothing(self) -> None:
        self.pins(pin(self.url, "0" * 64))
        code, _, err = self.verb("install")
        self.assertEqual(code, 1)
        self.assertIn("not the pinned " + "0" * 64, err)
        self.assertEqual(list((self.tmp / "cache" / "pinned-tools").iterdir()), [])
        self.assertEqual(self.verb("status")[0], 1)

    def test_an_archive_without_a_provided_name_installs_nothing(self) -> None:
        self.pins(pin(self.url, self.sha256, provides=("uv", "uvx")))
        result = sd_gate_tools.install(self.environment)[0]
        self.assertEqual(result["action"], "failed")
        self.assertIn("holds no executable uvx in pkg/bin", result["error"])
        self.assertEqual(list((self.tmp / "cache" / "pinned-tools").iterdir()), [])

    def test_an_install_another_one_finished_first_keeps_that_copy(self) -> None:
        self.pins(pin(self.url, self.sha256))
        real = pathlib.Path.rename

        def finished_first(source: pathlib.Path, target: Any) -> Any:
            with mock.patch.object(pathlib.Path, "rename", real):
                sd_gate_tools.install(self.environment)  # the other install, which wins the rename
            return real(source, target)

        with mock.patch.object(pathlib.Path, "rename", finished_first):
            self.assertEqual(sd_gate_tools.install(self.environment)[0]["action"], "installed")
        self.assertEqual(len(list((self.tmp / "cache" / "pinned-tools").iterdir())), 1)

    def test_a_rename_that_fails_with_no_copy_in_place_fails_the_install(self) -> None:
        self.pins(pin(self.url, self.sha256))
        with mock.patch.object(pathlib.Path, "rename", side_effect=OSError("disk full")):
            self.assertIn("disk full", sd_gate_tools.install(self.environment)[0]["error"])

    def test_another_platforms_pin_is_ignored(self) -> None:
        self.pins(pin(self.url, self.sha256, platform="plan9-mips"))
        self.assertEqual((sd_gate_tools.install(self.environment), sd_gate_tools.missing(self.environment)), ([], None))

    def test_missing_names_the_tool_its_folder_and_the_install_command(self) -> None:
        self.pins(pin(self.url, self.sha256))
        reason = sd_gate_tools.missing(self.environment)
        self.assertIn(f"pinned uv 1.0 at {self.tmp / 'cache' / 'pinned-tools'}", str(reason))
        self.assertIn("run `sd gate tools install`", str(reason))
        sd_gate_tools.install(self.environment)
        self.assertIsNone(sd_gate_tools.missing(self.environment))

    def test_the_shipped_pins_name_bound_tools_and_full_digests(self) -> None:
        for entry in sd_gate_tools.PINS:
            self.assertEqual(len(entry["sha256"]), 64, entry["tool"])
            self.assertTrue(entry["url"].startswith("https://"), entry["tool"])
            self.assertLessEqual(set(entry["provides"]), set(sd_gate_receipts.OFFLOAD_TOOLS), entry["tool"])


class PinnedGate(rows.SatelliteFixture):
    """An opted-in gate with a pin for `cargo-nextest` and `uv`; the caller's `CARGO_HOME` holds its own `cargo-nextest`."""

    tool, found = staticmethod(rows.CargoSubcommands.tool), staticmethod(rows.CargoSubcommands.found)
    gate, bound = rows.CargoSubcommands.gate, rows.CargoSubcommands.bound

    def setUp(self) -> None:
        super().setUp()
        home = self.root.parent / "home"
        self.scratch = {"HOME": str(home), "SD_GATE_SLOTS": "0", "XDG_CONFIG_HOME": str(home / ".config"),
                        "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".state"),
                        "SD_GATE_CACHE_DIR": str(home / ".cache" / "sd" / "gate")}
        self.cargo = self.root.parent / "cargo-a"
        self.tool(self.cargo / "bin" / "cargo-nextest", "cargo-nextest a")
        self.during: Any = None
        self.seen: dict[str, Any] = {}
        self.url, self.sha256 = archive(self.root.parent, {"pkg/bin/cargo-nextest": "pinned nextest", "pkg/bin/uv": "pinned uv"})
        patcher = mock.patch.object(sd_gate_tools, "PINS", (pin(self.url, self.sha256, provides=("cargo-nextest", "uv")),))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pinned = pathlib.Path(sd_gate_tools.path_entries(self.scratch)[0])

    def stand_in(self, argv, env, tree, timeout):  # type: ignore[no-untyped-def]
        self.path = env["PATH"]
        return rows.CargoSubcommands.stand_in(self, argv, env, tree, timeout)

    def test_a_missing_pinned_copy_refuses_the_gate_with_the_install_command(self) -> None:
        result = self.gate()
        self.assertEqual((result["status"], self.runs), ("failure", 0))
        self.assertIn("run `sd gate tools install`", result["stderr"])
        self.assertNotIn("receipt_revision", result)

    def test_the_check_runs_the_pinned_copy_and_the_row_binds_it(self) -> None:
        sd_gate_tools.install(self.scratch)
        result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertEqual(self.path.split(os.pathsep)[0], str(self.pinned))
        pinned = sd_gate_receipts._content_digest(self.pinned / "cargo-nextest")
        self.assertEqual((self.seen["nextest"], self.bound()), (pinned, pinned))
        self.assertEqual(self.offload_row()["offload_view"]["tools"]["uv"], sd_gate_receipts._content_digest(self.pinned / "uv"))

    def test_a_pinned_name_is_not_copied_from_the_caller(self) -> None:
        sd_gate_tools.install(self.scratch)
        self.gate()
        self.assertEqual(self.seen["listing"], [])

    def test_a_gate_that_did_not_opt_in_gets_no_pinned_path(self) -> None:
        self.opted = "off"
        result = self.gate()
        self.assertEqual((result["status"], self.runs), ("success", 1))
        self.assertNotIn(str(self.pinned), self.path.split(os.pathsep))

    def test_pinning_twice_changes_nothing(self) -> None:
        once = sd_gate_receipts.offload_pins({**self.scratch, "PATH": os.pathsep.join(["/usr/bin", str(self.pinned)])})
        self.assertEqual(once["PATH"].split(os.pathsep), [str(self.pinned), "/usr/bin"])
        self.assertEqual(sd_gate_receipts.offload_pins({**self.scratch, **once})["PATH"], once["PATH"])


class SystemTools(unittest.TestCase):
    """A tool in macOS's own folders binds and names `system_version`; any other names its resolved file."""

    def setUp(self) -> None:
        sd_gate_receipts.developer_version.cache_clear()
        self.addCleanup(sd_gate_receipts.developer_version.cache_clear)

    def test_a_system_tool_binds_the_system_version(self) -> None:
        with mock.patch.object(sd_gate_receipts, "system_version", return_value="macOS 27.0 (A); CLT 1"):
            one = sd_gate_receipts.view_tool("sh", "/bin", {}, None)
        with mock.patch.object(sd_gate_receipts, "system_version", return_value="macOS 27.0 (A); CLT 2"):
            two = sd_gate_receipts.view_tool("sh", "/bin", {}, None)
        self.assertNotEqual(one[0], two[0])
        self.assertEqual(one[1], "/bin/sh; macOS 27.0 (A); CLT 1")
        self.assertTrue(str(one[0]).startswith(sd_gate_receipts._content_digest("/bin/sh") + " "))

    def test_a_refusal_on_a_system_tool_names_both_versions(self) -> None:
        views = []
        for clt in ("1", "2"):
            with mock.patch.object(sd_gate_receipts, "system_version", return_value=f"macOS 27.0 (A); CLT {clt}"):
                views.append(sd_gate_receipts.offload_view({"HOME": "/nonexistent", "PATH": "/bin"}))
        part = {"scope": {"mode": "full", "command": []}, "detection": {"source": "make", "commands": {}}}
        part = {**dict.fromkeys(sd_gate_receipts.TREE_FIELDS), **part}
        row = {"binding": {"environment_mode": "offload", **part}, "offload_view": views[0]}
        reason = sd_gate_receipts.binding_mismatch(row, part, views[1], "offload")
        self.assertIsNotNone(reason)
        self.assertIn("tools at bash (satellite via /bin/bash; macOS 27.0 (A); CLT 1, hub via /bin/bash; macOS 27.0 (A); CLT 2)",
                      str(reason and reason["reason"]))

    def test_another_tool_names_its_resolved_file_under_home_as_tilde(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp).resolve()
            (home / "bin").mkdir()
            (home / "real").write_text("#!/bin/sh\n", encoding="utf-8")
            (home / "real").chmod(0o755)
            (home / "bin" / "uv").symlink_to(home / "real")
            self.assertEqual(sd_gate_receipts.view_tool("uv", str(home / "bin"), {"HOME": str(home)}, None)[1], "~/real")

    def test_the_command_line_tools_version_comes_from_pkgutil(self) -> None:
        said = {"sw_vers -productVersion": "27.0.1", "sw_vers -buildVersion": "26A434", "xcode-select -p": "/nonexistent/CLT",
                "pkgutil --pkg-info=com.apple.pkg.CLTools_Executables": "package-id: x\nversion: 27.0.0.1\nvolume: /"}
        with mock.patch.object(sd_gate_receipts, "system_answer", lambda argv: said[" ".join(argv)]), \
                mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(sd_gate_receipts.system_version({}), "macOS 27.0.1 (26A434); CLT 27.0.0.1")

    def test_an_xcode_developer_folder_reads_the_apps_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            contents = pathlib.Path(tmp, "Xcode.app", "Contents")
            (contents / "Developer").mkdir(parents=True)
            (contents / "version.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "27.1",
                                                                     "ProductBuildVersion": "27B5"}))
            with mock.patch.object(sd_gate_receipts, "system_answer", lambda argv: "x"), \
                    mock.patch.object(sys, "platform", "darwin"):
                version = sd_gate_receipts.system_version({"DEVELOPER_DIR": str(contents / "Developer")})
        self.assertEqual(version, "macOS x (x); Xcode 27.1 (27B5)")

    def test_another_platform_names_itself(self) -> None:
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(sd_gate_receipts.system_version({}), sd_gate_receipts.platform.platform())

    def test_a_question_that_fails_reads_unknown(self) -> None:
        self.assertEqual(sd_gate_receipts.system_answer(["/nonexistent/sw_vers"]), "unknown")
        self.assertEqual(sd_gate_receipts.system_answer(["/usr/bin/false"]), "unknown")
        self.assertEqual(sd_gate_receipts.system_answer(["/bin/echo", "27"]), "27")


if __name__ == "__main__":
    unittest.main()
