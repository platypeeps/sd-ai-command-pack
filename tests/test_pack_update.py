"""The one machine update action: plugin update, then machine install.

`sd-ai-command-pack-pack-update.sh` is the only place the two halves of a pack
update meet, so these tests are organized around the seam between them:

* **Fail-closed resolution** — every way `claude` can fail to name exactly one
  updated plugin root stops the run *before* the machine install, because
  installing from the old root would claim an update that did not happen.
* **Skew** — when the plugin half lands and the machine half does not, the
  divergence has to be legible in the run's own output, and a rerun has to
  converge. That pair is the acceptance criterion, so it runs against the real
  plugin root and the real machine installer rather than a stub.

The Claude CLI is stubbed on PATH the way the housekeeping tests stub `gh`; the
plugin root it names is either the committed `plugins/sd` tree or a synthetic
root whose machine installer is a marker-writing stub, depending on whether the
test needs to reach the installer at all.
"""

from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:  # pragma: no cover - import shim
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
os = _support.os
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
Path = _support.Path
install = _support.install
InstallTestCase = _support.InstallTestCase

PLUGIN_ROOT = _support.PACK_ROOT / "plugins" / "sd"
PLUGIN_ID = "sd@sd-ai-command-pack"

STUB_CLAUDE = """#!/usr/bin/env bash
set -u
printf '%s\\n' "$*" >> "$STUB_CLAUDE_LOG"
if [ "${1:-}" = plugin ] && [ "${2:-}" = update ]; then
  exit "${STUB_CLAUDE_UPDATE_EXIT:-0}"
fi
if [ "${1:-}" = plugin ] && [ "${2:-}" = list ]; then
  if [ -f "$STUB_CLAUDE_LIST_FILE" ]; then
    cat "$STUB_CLAUDE_LIST_FILE"
  fi
  exit "${STUB_CLAUDE_LIST_EXIT:-0}"
fi
printf 'unexpected claude invocation: %s\\n' "$*" >&2
exit 9
"""

STUB_MACHINE_INSTALL = """#!/usr/bin/env bash
set -u
printf '%s\\n' "$*" >> "$STUB_INSTALL_LOG"
if [ "${1:-}" = status ]; then
  printf '%s' "${STUB_INSTALL_STATUS_JSON:-}"
fi
exit "${STUB_INSTALL_EXIT:-0}"
"""


class PackUpdateTests(InstallTestCase):
    """Tests for the machine update entry point."""

    def make_update_fixture(self) -> Path:
        """A scripts/ directory holding the script and the siblings it uses."""

        root = self.make_repo()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir()
        for name in (
            "sd-ai-command-pack-pack-update.sh",
            "sd-ai-command-pack-toolchain.sh",
            "sd_ai_command_pack_lib.py",
        ):
            shutil.copy2(install.ROOT / f"templates/scripts/{name}", scripts_dir / name)
        (root / "bin").mkdir()
        (root / "home").mkdir()
        (root / "state").mkdir()
        return root

    def write_claude_stub(self, root: Path, entries: object) -> Path:
        """Install the CLI stub and the plugin list it answers with."""

        stub = root / "bin" / "claude"
        stub.write_text(STUB_CLAUDE, encoding="utf-8")
        stub.chmod(0o755)
        listing = root / "plugin-list.json"
        if isinstance(entries, str):
            listing.write_text(entries, encoding="utf-8")
        else:
            listing.write_text(json.dumps(entries) + "\n", encoding="utf-8")
        return listing

    def write_stub_plugin_root(self, root: Path, *, version: str = "9.9.9") -> Path:
        """A plugin root whose machine installer only records that it ran."""

        plugin_root = root / "stub-plugin"
        (plugin_root / ".claude-plugin").mkdir(parents=True)
        (plugin_root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "sd", "version": version}) + "\n", encoding="utf-8"
        )
        (plugin_root / "bin").mkdir()
        installer = plugin_root / "bin" / "sd-machine-install"
        installer.write_text(STUB_MACHINE_INSTALL, encoding="utf-8")
        installer.chmod(0o755)
        return plugin_root

    def listing_for(self, install_path: object, *, plugin_id: str = PLUGIN_ID) -> list[dict[str, object]]:
        entry: dict[str, object] = {
            "id": plugin_id,
            "version": "0.0.0",
            "scope": "user",
            "enabled": True,
        }
        if install_path is not None:
            entry["installPath"] = str(install_path)
        return [
            {"id": "other@marketplace", "version": "1.0.0", "installPath": "/nonexistent"},
            entry,
        ]

    def run_pack_update(
        self,
        root: Path,
        *args: str,
        path_entries: tuple[str, ...] | None = None,
        **extra_env: str,
    ) -> subprocess.CompletedProcess[str]:
        # `path_entries` replaces PATH outright rather than prefixing it: a
        # test that needs `claude` to be missing must not fall through to the
        # developer's real CLI, which would run a real plugin update.
        entries = (
            (str(root / "bin"), os.environ.get("PATH", ""))
            if path_entries is None
            else path_entries
        )
        env = {
            **os.environ,
            "PATH": os.pathsep.join(entries),
            "SD_AI_COMMAND_PACK_PYTHON": sys.executable,
            "STUB_CLAUDE_LOG": str(root / "claude.log"),
            "STUB_CLAUDE_LIST_FILE": str(root / "plugin-list.json"),
            "STUB_INSTALL_LOG": str(root / "machine-install.log"),
            **extra_env,
        }
        return subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-pack-update.sh",
                "--home",
                str(root / "home"),
                "--state-home",
                str(root / "state"),
                *args,
            ],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def claude_log(self, root: Path) -> list[str]:
        path = root / "claude.log"
        if not path.is_file():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    # -- the real plugin root: both halves, and the skew between them --------

    def test_update_then_machine_install_reports_current(self) -> None:
        root = self.make_update_fixture()
        self.write_claude_stub(root, self.listing_for(PLUGIN_ROOT))

        result = self.run_pack_update(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"plugin update {PLUGIN_ID}", self.claude_log(root))
        self.assertIn("plugin list --json", self.claude_log(root))
        self.assertIn(f"installing machine surfaces from {PLUGIN_ROOT}", result.stdout)
        self.assertIn("status:  current", result.stdout)
        # The receipt lands under the state root this run was given, and it
        # records the version the resolved plugin root advertises.
        receipt = root / "state" / "machine" / "machine-receipt.json"
        self.assertTrue(receipt.is_file(), result.stdout)
        plugin_version = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        self.assertEqual(
            json.loads(receipt.read_text(encoding="utf-8"))["packVersion"],
            plugin_version,
        )
        self.assertIn(f"plugin:  {PLUGIN_ID} {plugin_version}", result.stdout)

    def test_rerun_after_a_complete_update_is_a_no_op(self) -> None:
        root = self.make_update_fixture()
        self.write_claude_stub(root, self.listing_for(PLUGIN_ROOT))
        first = self.run_pack_update(root)
        self.assertEqual(first.returncode, 0, first.stdout)

        second = self.run_pack_update(root)

        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertIn("owned-current", second.stdout)
        self.assertIn("status:  current", second.stdout)

    def test_failed_machine_install_shows_skew_and_a_rerun_converges(self) -> None:
        root = self.make_update_fixture()
        self.write_claude_stub(root, self.listing_for(PLUGIN_ROOT))
        # A file the receipt does not own at a payload destination: the
        # installer refuses the whole run, which is the "plugin updated,
        # machine install failed" half-state the update has to make legible.
        conflict = root / "home" / ".agents" / "skills" / "sd-check" / "SKILL.md"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("locally authored\n", encoding="utf-8")

        interrupted = self.run_pack_update(root)

        self.assertNotEqual(interrupted.returncode, 0)
        self.assertIn("refusing to install over files this receipt does not own", interrupted.stdout)
        self.assertIn("machine: none unknown", interrupted.stdout)
        self.assertIn("status:  skew", interrupted.stdout)
        self.assertIn("Rerun this script to converge", interrupted.stdout)
        self.assertFalse((root / "state" / "machine" / "machine-receipt.json").exists())
        self.assertEqual(conflict.read_text(encoding="utf-8"), "locally authored\n")

        conflict.unlink()
        converged = self.run_pack_update(root)

        self.assertEqual(converged.returncode, 0, converged.stdout)
        self.assertIn("status:  current", converged.stdout)
        self.assertTrue((root / "state" / "machine" / "machine-receipt.json").is_file())

    # -- fail-closed resolution: nothing installs -----------------------------

    def test_missing_claude_cli_fails_before_anything_runs(self) -> None:
        root = self.make_update_fixture()
        self.write_claude_stub(root, self.listing_for(PLUGIN_ROOT))
        # An empty directory is the whole PATH, so no `claude` can be found
        # here or anywhere the developer happens to have installed one. The
        # script reaches its check with shell builtins and the absolute
        # interpreter paths the runner passes, so it needs nothing else.
        empty_dir = root / "empty-path"
        empty_dir.mkdir()

        result = self.run_pack_update(root, path_entries=(str(empty_dir),))

        self.assertEqual(result.returncode, 127, result.stdout)
        self.assertIn("the Claude Code CLI (claude) is not on PATH", result.stdout)
        self.assertEqual(self.claude_log(root), [])

    def test_plugin_update_failure_skips_the_machine_install(self) -> None:
        root = self.make_update_fixture()
        plugin_root = self.write_stub_plugin_root(root)
        self.write_claude_stub(root, self.listing_for(plugin_root))

        result = self.run_pack_update(root, STUB_CLAUDE_UPDATE_EXIT="3")

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn(f"claude plugin update {PLUGIN_ID} failed (exit 3)", result.stdout)
        self.assertIn("the machine install did not run", result.stdout)
        # The root was never resolved, so the installer was never reached.
        self.assertEqual(self.claude_log(root), [f"plugin update {PLUGIN_ID}"])
        self.assertFalse((root / "machine-install.log").exists())

    def test_plugin_list_failure_skips_the_machine_install(self) -> None:
        root = self.make_update_fixture()
        plugin_root = self.write_stub_plugin_root(root)
        self.write_claude_stub(root, self.listing_for(plugin_root))

        result = self.run_pack_update(root, STUB_CLAUDE_LIST_EXIT="4")

        self.assertEqual(result.returncode, 4, result.stdout)
        self.assertIn("claude plugin list --json failed (exit 4)", result.stdout)
        self.assertFalse((root / "machine-install.log").exists())

    def test_unusable_list_output_is_refused(self) -> None:
        # An array of the wrong shape is a different finding (nothing matches
        # the wanted id), so it belongs with the absent-plugin case below.
        cases: tuple[object, ...] = ("{not json", "", {"plugins": []})
        for entries in cases:
            with self.subTest(entries=entries):
                root = self.make_update_fixture()
                self.write_stub_plugin_root(root)
                self.write_claude_stub(root, entries)

                result = self.run_pack_update(root)

                self.assertEqual(result.returncode, 10, result.stdout)
                self.assertIn(
                    "did not return a JSON array of installed plugins", result.stdout
                )
                self.assertFalse((root / "machine-install.log").exists())

    def test_absent_plugin_is_refused(self) -> None:
        root = self.make_update_fixture()
        plugin_root = self.write_stub_plugin_root(root)
        listings: tuple[object, ...] = (
            self.listing_for(plugin_root, plugin_id="sd@somewhere-else"),
            [],
            ["not an object"],
        )
        for listing in listings:
            with self.subTest(listing=listing):
                self.write_claude_stub(root, listing)

                result = self.run_pack_update(root)

                self.assertEqual(result.returncode, 11, result.stdout)
                self.assertIn(f"plugin {PLUGIN_ID} is not installed", result.stdout)
                self.assertFalse((root / "machine-install.log").exists())

    def test_duplicate_entries_are_refused(self) -> None:
        root = self.make_update_fixture()
        plugin_root = self.write_stub_plugin_root(root)
        listing = self.listing_for(plugin_root)
        self.write_claude_stub(root, [*listing, dict(listing[-1])])

        result = self.run_pack_update(root)

        self.assertEqual(result.returncode, 12, result.stdout)
        self.assertIn(f"reports {PLUGIN_ID} more than once", result.stdout)
        self.assertFalse((root / "machine-install.log").exists())

    def test_entry_without_an_install_path_is_refused(self) -> None:
        root = self.make_update_fixture()
        self.write_stub_plugin_root(root)
        self.write_claude_stub(root, self.listing_for(None))

        result = self.run_pack_update(root)

        self.assertEqual(result.returncode, 13, result.stdout)
        self.assertIn("carries no installPath", result.stdout)
        self.assertFalse((root / "machine-install.log").exists())

    def test_install_path_that_is_not_a_directory_is_refused(self) -> None:
        root = self.make_update_fixture()
        self.write_claude_stub(root, self.listing_for(root / "no-such-root"))

        result = self.run_pack_update(root)

        self.assertEqual(result.returncode, 13, result.stdout)
        self.assertIn("the resolved plugin root does not exist", result.stdout)

    def test_plugin_root_without_a_machine_installer_is_refused(self) -> None:
        root = self.make_update_fixture()
        plugin_root = self.write_stub_plugin_root(root)
        (plugin_root / "bin" / "sd-machine-install").unlink()
        self.write_claude_stub(root, self.listing_for(plugin_root))

        result = self.run_pack_update(root)

        self.assertEqual(result.returncode, 127, result.stdout)
        self.assertIn("no executable machine installer", result.stdout)

    # -- identity, forwarding, and usage --------------------------------------

    def test_plugin_identity_is_overridable(self) -> None:
        root = self.make_update_fixture()
        plugin_root = self.write_stub_plugin_root(root, version="1.2.3")
        self.write_claude_stub(
            root, self.listing_for(plugin_root, plugin_id="pack@internal")
        )

        result = self.run_pack_update(
            root, "--plugin", "pack", "--marketplace", "internal", "--force"
        )

        self.assertIn("plugin update pack@internal", self.claude_log(root))
        self.assertIn("plugin:  pack@internal 1.2.3", result.stdout)
        # --force reaches the installer, and so do the destination overrides.
        forwarded = (root / "machine-install.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            forwarded[0],
            f"install --home {root / 'home'} --state-home {root / 'state'} --force",
        )
        self.assertEqual(
            forwarded[1],
            f"status --json --home {root / 'home'} --state-home {root / 'state'}",
        )

    def test_halves_that_do_not_agree_exit_as_skew(self) -> None:
        # Every shape of "the plugin half landed and the machine half did not"
        # that both halves reporting success can still produce. The real
        # installer only reaches these through a receipt the run did not
        # advance, so the states come from the stub.
        cases = (
            ('{"state": "installed", "packVersion": "1.0.0"}', "plugin 9.9.9, machine 1.0.0"),
            ('{"state": "none"}', "no machine install recorded for plugin 9.9.9"),
            ('{"state": "invalid"}', "machine receipt is invalid"),
        )
        for report, detail in cases:
            with self.subTest(report=report):
                root = self.make_update_fixture()
                plugin_root = self.write_stub_plugin_root(root)
                self.write_claude_stub(root, self.listing_for(plugin_root))

                result = self.run_pack_update(root, STUB_INSTALL_STATUS_JSON=report)

                self.assertEqual(result.returncode, 14, result.stdout)
                self.assertIn(f"status:  skew ({detail})", result.stdout)
                self.assertIn("Rerun this script to converge", result.stdout)

    def test_unreadable_machine_state_is_not_reported_as_current(self) -> None:
        root = self.make_update_fixture()
        plugin_root = self.write_stub_plugin_root(root)
        self.write_claude_stub(root, self.listing_for(plugin_root))

        # The stub installer prints nothing, so `status --json` yields no
        # report to compare against: an unknown verdict, never a passing one.
        result = self.run_pack_update(root)

        self.assertEqual(result.returncode, 15, result.stdout)
        self.assertIn("machine: unreadable unknown", result.stdout)
        self.assertIn("status:  unknown", result.stdout)

    def test_unknown_option_is_a_usage_error(self) -> None:
        root = self.make_update_fixture()
        self.write_claude_stub(root, self.listing_for(PLUGIN_ROOT))

        result = self.run_pack_update(root, "--nonesuch")

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Usage:", result.stdout)
        self.assertEqual(self.claude_log(root), [])


if __name__ == "__main__":
    _support.unittest.main()
