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

    def test_a_url_that_is_neither_https_nor_a_file_installs_nothing(self) -> None:
        self.pins(pin("http://example.test/uv.tar.gz", self.sha256))
        self.assertIn("is not an https or file URL", sd_gate_tools.install(self.environment)[0]["error"])

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

    def test_an_archive_that_also_holds_another_bound_name_installs_nothing(self) -> None:
        """A pinned folder leads `PATH`, so a `cargo` beside the pinned `cargo-nextest` would shadow the machine's."""
        url, sha256 = archive(self.tmp, {"cargo-nextest": "nextest", "cargo": "a rustup proxy"}, name="nextest.tar.gz")
        self.pins(pin(url, sha256, tool="cargo-nextest", bin_folder=".", provides=("cargo-nextest",)))
        self.assertIn("also holds cargo in ., which it does not pin", sd_gate_tools.install(self.environment)[0]["error"])
        self.assertEqual(list((self.tmp / "cache" / "pinned-tools").iterdir()), [])

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
        links = sd_gate_tools.clt_links(self.scratch)
        self.assertEqual(once["PATH"].split(os.pathsep), [str(self.pinned), links, "/usr/bin"])
        self.assertEqual(sd_gate_receipts.offload_pins({**self.scratch, **once})["PATH"], once["PATH"])

    def test_git_and_make_bind_the_clt_copy_whatever_path_comes_first(self) -> None:
        """#296 refused at git: one machine's `PATH` led with Homebrew's `git`, the other's with `/usr/bin`."""
        brew = self.root.parent / "brew" / "bin"
        for name in sd_gate_tools.CLT_TOOLS:
            self.tool(brew / name, f"homebrew {name}")
        views = []
        for side, search in (("sat", [str(brew), "/usr/bin", "/bin"]), ("hub", ["/usr/bin", "/bin"])):
            environment = sd_gate_receipts.offload_pins({**self.scratch, "SD_GATE_CACHE_DIR": str(self.root.parent / side),
                                                         "PATH": os.pathsep.join(search)})
            with mock.patch.object(sd_gate_receipts, "developer_tools", return_value="CLT 1"):
                views.append({name: sd_gate_receipts.view_tool(name, environment["PATH"], environment, None)
                              for name in sd_gate_tools.CLT_TOOLS})
        self.assertEqual(views[0], views[1])
        self.assertTrue(views[0]["git"][1].startswith("/usr/bin/git; "), views[0]["git"])

    def test_a_link_to_another_file_is_mended(self) -> None:
        links = pathlib.Path(sd_gate_tools.clt_links(self.scratch))
        (links / "git").unlink()
        (links / "git").symlink_to(self.root.parent / "elsewhere")
        sd_gate_tools.clt_links(self.scratch)
        self.assertEqual(os.readlink(links / "git"), "/usr/bin/git")


class SystemTools(unittest.TestCase):
    """A tool in macOS's own folders binds and names `system_version`; any other names its resolved file."""

    def setUp(self) -> None:
        for cached in (sd_gate_receipts.developer_version, sd_gate_receipts.macos_version):
            cached.cache_clear()
            self.addCleanup(cached.cache_clear)

    def view(self, macos: str, clt: str, name: str = "sh") -> tuple[str | None, str | None]:
        with mock.patch.object(sd_gate_receipts, "macos_version", return_value=macos), \
                mock.patch.object(sd_gate_receipts, "developer_tools", return_value=clt):
            return sd_gate_receipts.view_tool(name, "/bin", {}, None)

    def test_a_system_tool_binds_the_developer_tools(self) -> None:
        one, two = self.view("macOS 27.0 (A)", "CLT 1"), self.view("macOS 27.0 (A)", "CLT 2")
        self.assertNotEqual(one[0], two[0])
        self.assertEqual(one[1], "/bin/sh; macOS 27.0 (A); CLT 1")
        self.assertTrue(str(one[0]).startswith(sd_gate_receipts._content_digest("/bin/sh") + " "))

    def test_a_system_tool_names_the_macos_version_but_does_not_bind_it(self) -> None:
        """The lead's ruling (sd:2936): the hub and a satellite one macOS point release apart still share a gate."""
        one, two = self.view("macOS 27.0 (A)", "CLT 1"), self.view("macOS 27.0.1 (B)", "CLT 1")
        self.assertEqual(one[0], two[0])
        self.assertEqual((one[1], two[1]), ("/bin/sh; macOS 27.0 (A); CLT 1", "/bin/sh; macOS 27.0.1 (B); CLT 1"))

    def test_a_refusal_on_a_system_tool_names_both_versions(self) -> None:
        views = []
        for clt in ("1", "2"):
            with mock.patch.object(sd_gate_receipts, "macos_version", return_value="macOS 27.0 (A)"), \
                    mock.patch.object(sd_gate_receipts, "developer_tools", return_value=f"CLT {clt}"):
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
        """Each question names its absolute path, so a gate's short `PATH` cannot turn `/usr/sbin/pkgutil` into `unknown`."""
        said = {"/usr/bin/sw_vers -productVersion": "27.0.1", "/usr/bin/sw_vers -buildVersion": "26A434",
                "/usr/bin/xcode-select -p": "/nonexistent/CLT",
                "/usr/sbin/pkgutil --pkg-info=com.apple.pkg.CLTools_Executables": "package-id: x\nversion: 27.0.0.1\nvolume: /"}
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

    def test_a_developer_dir_naming_the_app_reads_the_apps_version(self) -> None:
        """`DEVELOPER_DIR=/Applications/Xcode.app` is the app, not its `Contents/Developer`: two Xcodes there differ."""
        with tempfile.TemporaryDirectory() as tmp:
            app = pathlib.Path(tmp, "Xcode.app")
            (app / "Contents").mkdir(parents=True)
            (app / "Contents" / "version.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "27.2",
                                                                             "ProductBuildVersion": "27C1"}))
            with mock.patch.object(sd_gate_receipts, "system_answer", lambda argv: "x"), \
                    mock.patch.object(sys, "platform", "darwin"):
                version = sd_gate_receipts.system_version({"DEVELOPER_DIR": f"{app}/"})
        self.assertEqual(version, "macOS x (x); Xcode 27.2 (27C1)")

    def test_another_platform_names_itself_and_binds_no_developer_tools(self) -> None:
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(sd_gate_receipts.system_version({}), sd_gate_receipts.platform.platform())
            self.assertEqual(sd_gate_receipts.developer_tools({}), "")

    def test_a_question_that_fails_reads_unknown(self) -> None:
        self.assertEqual(sd_gate_receipts.system_answer(["/nonexistent/sw_vers"]), "unknown")
        self.assertEqual(sd_gate_receipts.system_answer(["/usr/bin/false"]), "unknown")
        self.assertEqual(sd_gate_receipts.system_answer(["/bin/echo", "27"]), "27")


if __name__ == "__main__":
    unittest.main()
