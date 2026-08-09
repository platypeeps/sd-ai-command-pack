"""Machine-scope install engine: ownership, recovery, and refusal behavior.

The engine writes into a user's home directory and later deletes what it
wrote, so the tests are organized around the three ways that goes wrong:

* **Placement** — each destination family lands where the platform actually
  reads it, with the executable bit the family implies, and a rerun is a no-op.
* **Ownership** — a file is ours only when the receipt says so, or when an
  intent journal proves an interrupted run of this exact payload wrote it.
  Byte identity alone must never confer ownership, because `remove` deletes
  what the receipt claims.
* **Trust** — the receipt authorizes overwrites and deletions, so a
  hand-edited one must not be able to direct either outside the family roots.

Every test runs against a scratch home and a scratch state root; nothing
touches the developer's real `~/.agents`, `~/.gemini`, or state directory.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from installer import machinepayload, machinescope
from installer.machinescope import (
    EXIT_CONFLICT,
    EXIT_OK,
    INTENT_FILE,
    RECEIPT_FILE,
    MachineInstallError,
    PlanStatus,
)

PACK_VERSION = "9.9.9"

# One row per destination family, plus the library module that shares the
# scripts family but must not become executable.
PAYLOAD_ROWS: tuple[tuple[str, str, str, bool], ...] = (
    (".agents/skills/sd-check/SKILL.md", "shared", "machine-other", False),
    (".agents/skills/sd-check/references/notes.md", "shared", "machine-other", False),
    ("scripts/sd-ai-command-pack-check.py", "shared", "machine-claude", True),
    ("scripts/sd_ai_command_pack_lib.py", "shared", "machine-claude", True),
    ("docs/SD_AI_COMMAND_PACK.md", "shared", "machine-other", False),
    (".gemini/commands/sd/help.toml", "gemini", "machine-other", False),
    (".opencode/commands/sd-help.md", "opencode", "machine-other", False),
)

EXPECTED_INSTALLED: dict[str, bool] = {
    ".agents/skills/sd-check/SKILL.md": False,
    ".agents/skills/sd-check/references/notes.md": False,
    ".agents/bin/sd-ai-command-pack-check.py": True,
    ".agents/bin/sd_ai_command_pack_lib.py": False,
    ".agents/docs/SD_AI_COMMAND_PACK.md": False,
    ".gemini/commands/sd/help.toml": False,
    ".config/opencode/commands/sd-help.md": False,
}


class MachineInstallerTestCase(unittest.TestCase):
    """Scratch home, scratch state root, and a payload builder."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="sd-machine-"))
        self.addCleanup(self._cleanup)
        self.home = self.base / "home"
        self.state_home = self.base / "state"
        self.home.mkdir()
        self.environ = {"XDG_CONFIG_HOME": str(self.home / ".config")}
        self.payload_root = self.write_payload()

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.base, ignore_errors=True)

    # -- fixtures ---------------------------------------------------------

    def write_payload(
        self,
        *,
        name: str = "payload",
        rows: tuple[tuple[str, str, str, bool], ...] = PAYLOAD_ROWS,
        contents: dict[str, str] | None = None,
        platforms: dict[str, dict[str, object]] | None = None,
    ) -> Path:
        root = self.base / name
        overrides = contents or {}
        for target, _platform, _category, _shared in rows:
            path = root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(overrides.get(target, f"content of {target}\n"), encoding="utf-8")
        partition = {
            "schemaVersion": 1,
            "manifestVersion": PACK_VERSION,
            "platforms": platforms
            or {
                platform: {"scope": "machine", "provisional": False}
                for platform in {row[1] for row in rows}
            },
            "files": [
                {
                    "target": target,
                    "platform": platform,
                    "category": category,
                    "sharedRuntime": shared,
                }
                for target, platform, category, shared in rows
            ],
        }
        (root / "partition.json").write_text(json.dumps(partition, indent=2), encoding="utf-8")
        return root

    # -- helpers ----------------------------------------------------------

    def install(self, **kwargs: object) -> machinescope.InstallOutcome:
        arguments: dict[str, object] = {
            "home": self.home,
            "environ": self.environ,
            "state_home": self.state_home,
        }
        arguments.update(kwargs)
        payload = arguments.pop("payload_root", self.payload_root)
        assert isinstance(payload, Path)
        return machinescope.install(payload, **arguments)  # type: ignore[arg-type]

    def remove(self, **kwargs: object) -> machinescope.RemovalOutcome:
        arguments: dict[str, object] = {
            "home": self.home,
            "environ": self.environ,
            "state_home": self.state_home,
        }
        arguments.update(kwargs)
        return machinescope.remove(**arguments)  # type: ignore[arg-type]

    def status(self, **kwargs: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "home": self.home,
            "environ": self.environ,
            "state_home": self.state_home,
        }
        arguments.update(kwargs)
        return machinescope.status(**arguments)  # type: ignore[arg-type]

    @property
    def state_dir(self) -> Path:
        return self.state_home / machinescope.MACHINE_STATE_DIR

    @property
    def receipt_file(self) -> Path:
        return self.state_dir / RECEIPT_FILE

    @property
    def intent_file(self) -> Path:
        return self.state_dir / INTENT_FILE

    def read_receipt_json(self) -> dict:
        return json.loads(self.receipt_file.read_text(encoding="utf-8"))

    def write_receipt_json(self, payload: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.receipt_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def installed(self, relative: str) -> Path:
        return self.home / relative

    def assert_family_roots_pruned(self, *keep: Path) -> None:
        """Pruning is bounded by the family roots, and reaches all of them.

        `~/.agents` itself is left alone: it is the shared parent of three
        families and other tools' territory, not something this receipt owns.
        A root named in `keep` is expected to survive because something the
        installer did not create still lives in it.
        """

        for root in (
            self.home / ".agents" / "skills",
            self.home / ".agents" / "bin",
            self.home / ".agents" / "docs",
            self.home / ".gemini" / "commands",
            self.home / ".config" / "opencode" / "commands",
        ):
            if root in keep:
                self.assertTrue(root.is_dir(), f"{root} should have survived")
                continue
            self.assertFalse(root.exists(), f"{root} should have been pruned")
        self.assertTrue((self.home / ".agents").is_dir(), "~/.agents is not ours to remove")

    def fail_on_receipt_write(self):
        """Patch the writer so the receipt commit fails after the payload lands.

        This is the interrupted-update shape the PRD names: the files are on
        disk and the intent journal survives, but no receipt was committed.
        """

        original = machinescope._write_bytes

        def writer(destination: Path, content: bytes, *, executable: bool) -> None:
            if destination.name == RECEIPT_FILE:
                raise MachineInstallError("injected receipt-write failure")
            original(destination, content, executable=executable)

        return mock.patch.object(machinescope, "_write_bytes", writer)

    @contextlib.contextmanager
    def unreadable(self, *targets: Path):
        """Make specific paths raise on read, leaving every other read alone."""

        blocked = set(targets)
        original = Path.read_bytes

        def patched(path: Path) -> bytes:
            if path in blocked:
                raise PermissionError(13, "Permission denied")
            return original(path)

        with mock.patch.object(Path, "read_bytes", patched):
            yield

    @contextlib.contextmanager
    def undeletable(self, *targets: Path):
        """Make specific paths raise on unlink, leaving every other one alone."""

        blocked = set(targets)
        original = Path.unlink

        def patched(path: Path, missing_ok: bool = False) -> None:
            if path in blocked:
                raise PermissionError(13, "Permission denied")
            original(path, missing_ok=missing_ok)

        with mock.patch.object(Path, "unlink", patched):
            yield


class PlacementTests(MachineInstallerTestCase):
    def test_fresh_install_places_every_family_with_its_mode(self) -> None:
        outcome = self.install()

        self.assertTrue(outcome.changed)
        for relative, executable in EXPECTED_INSTALLED.items():
            with self.subTest(path=relative):
                path = self.installed(relative)
                self.assertTrue(path.is_file(), f"{relative} was not installed")
                mode_is_executable = bool(path.stat().st_mode & stat.S_IXUSR)
                self.assertEqual(mode_is_executable, executable)

    def test_receipt_records_version_digest_and_every_file(self) -> None:
        outcome = self.install()
        assert outcome.receipt is not None
        receipt = self.read_receipt_json()

        self.assertEqual(receipt["schemaVersion"], machinescope.RECEIPT_SCHEMA_VERSION)
        self.assertEqual(receipt["packVersion"], PACK_VERSION)
        self.assertEqual(receipt["payloadDigest"], outcome.plan.payload.digest)
        self.assertEqual(receipt["sourceRoot"], str(self.payload_root))
        self.assertEqual(len(receipt["files"]), len(PAYLOAD_ROWS))
        self.assertNotIn("backup", receipt["files"][0])

    def test_payload_digest_is_content_addressed(self) -> None:
        first = self.install()
        assert first.receipt is not None
        changed = self.write_payload(
            name="payload-changed",
            contents={".agents/skills/sd-check/SKILL.md": "different\n"},
        )

        second = machinescope.load_payload(changed)
        self.assertNotEqual(second.digest, first.receipt.payload_digest)

    def test_opencode_root_honors_xdg_config_home(self) -> None:
        elsewhere = self.base / "xdg"
        self.install(environ={"XDG_CONFIG_HOME": str(elsewhere)})

        self.assertTrue((elsewhere / "opencode" / "commands" / "sd-help.md").is_file())
        self.assertFalse((self.home / ".config" / "opencode").exists())

    def test_rerun_is_a_no_op(self) -> None:
        self.install()
        before = {
            path: path.read_bytes()
            for path in sorted(self.home.rglob("*"))
            if path.is_file()
        }

        second = self.install()

        self.assertFalse(second.changed)
        self.assertEqual(
            {planned.status for planned in second.plan.files},
            {PlanStatus.OWNED_CURRENT},
        )
        after = {
            path: path.read_bytes()
            for path in sorted(self.home.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_dry_run_writes_nothing(self) -> None:
        outcome = self.install(dry_run=True)

        self.assertTrue(outcome.dry_run)
        self.assertIsNone(outcome.receipt)
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse(self.receipt_file.exists())

    def test_refreshed_payload_replaces_stale_files_and_prunes_removed_rows(self) -> None:
        self.install()
        trimmed = tuple(row for row in PAYLOAD_ROWS if not row[0].startswith(".gemini/"))
        refreshed = self.write_payload(
            name="payload-v2",
            rows=trimmed,
            contents={".agents/skills/sd-check/SKILL.md": "updated skill\n"},
        )

        outcome = self.install(payload_root=refreshed)

        self.assertEqual(
            self.installed(".agents/skills/sd-check/SKILL.md").read_text(encoding="utf-8"),
            "updated skill\n",
        )
        self.assertFalse(self.installed(".gemini/commands/sd/help.toml").exists())
        # The pruned row takes its now-empty directories with it.
        self.assertFalse((self.home / ".gemini" / "commands").exists())
        self.assertEqual(len(outcome.plan.removals), 1)
        self.assertNotIn(
            "sd/help.toml",
            [entry["path"] for entry in self.read_receipt_json()["files"]],
        )

    def test_state_directory_follows_the_shared_state_home_variable(self) -> None:
        elsewhere = self.base / "env-state"
        environ = dict(self.environ)
        environ["SD_AI_COMMAND_PACK_STATE_HOME"] = str(elsewhere)

        self.install(environ=environ, state_home=None)

        self.assertTrue((elsewhere / machinescope.MACHINE_STATE_DIR / RECEIPT_FILE).is_file())
        self.assertFalse(self.receipt_file.exists())

    def test_state_directory_is_private(self) -> None:
        self.install()

        mode = stat.S_IMODE(self.state_dir.stat().st_mode)
        self.assertEqual(mode, 0o700)


class PartitionGateTests(MachineInstallerTestCase):
    def test_provisional_platform_is_refused(self) -> None:
        payload = self.write_payload(
            name="provisional",
            platforms={
                "shared": {"scope": "machine", "provisional": False},
                "gemini": {"scope": "machine", "provisional": True},
                "opencode": {"scope": "machine", "provisional": False},
            },
        )

        with self.assertRaises(MachineInstallError) as caught:
            self.install(payload_root=payload)

        self.assertIn(".gemini/commands/sd/help.toml", str(caught.exception))
        self.assertIn("provisional", str(caught.exception))
        self.assertFalse((self.home / ".agents").exists())

    def test_repo_native_platform_is_refused(self) -> None:
        payload = self.write_payload(
            name="repo-native",
            platforms={
                "shared": {"scope": "machine", "provisional": False},
                "gemini": {"scope": "repo-native", "provisional": False},
                "opencode": {"scope": "machine", "provisional": False},
            },
        )

        with self.assertRaises(MachineInstallError) as caught:
            self.install(payload_root=payload)

        self.assertIn("is repo-native, not machine-scope", str(caught.exception))

    def test_row_outside_every_destination_family_is_refused(self) -> None:
        rows = PAYLOAD_ROWS + ((".agents/agents/reviewer.md", "shared", "machine-other", False),)
        payload = self.write_payload(name="unmapped", rows=rows)

        with self.assertRaises(MachineInstallError) as caught:
            self.install(payload_root=payload)

        self.assertIn("no machine destination family", str(caught.exception))
        self.assertIn(".agents/agents/reviewer.md", str(caught.exception))

    def test_file_without_a_partition_row_is_refused(self) -> None:
        stray = self.payload_root / ".agents" / "skills" / "sd-check" / "stray.md"
        stray.write_text("undeclared\n", encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("no surface-partition row", str(caught.exception))

    def test_payload_symlink_is_refused(self) -> None:
        link = self.payload_root / ".agents" / "skills" / "sd-check" / "link.md"
        link.symlink_to(self.payload_root / ".agents" / "skills" / "sd-check" / "SKILL.md")

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("symlink", str(caught.exception))


class OwnershipTests(MachineInstallerTestCase):
    def test_unowned_file_refuses_the_whole_run_and_names_the_path(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_text("someone else's command\n", encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn(str(collision), str(caught.exception))
        self.assertIn("unowned", str(caught.exception))
        # Refusal is total: no other family was written before the conflict.
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse(self.receipt_file.exists())

    def test_byte_identical_pre_existing_file_is_unowned_without_a_journal(self) -> None:
        """The adoption hole: matching content is not proof of authorship."""

        payload = machinescope.load_payload(self.payload_root)
        entry = next(item for item in payload.entries if item.target.startswith(".gemini/"))
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(entry.content)

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn("unowned", str(caught.exception))
        self.assertIn(str(collision), str(caught.exception))

    def test_locally_modified_owned_file_refuses_as_drifted(self) -> None:
        self.install()
        drifted = self.installed(".agents/skills/sd-check/SKILL.md")
        drifted.write_text("hand edited\n", encoding="utf-8")
        refreshed = self.write_payload(
            name="payload-v2",
            contents={".agents/skills/sd-check/SKILL.md": "new upstream\n"},
        )

        with self.assertRaises(MachineInstallError) as caught:
            self.install(payload_root=refreshed)

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn("drifted", str(caught.exception))
        self.assertIn(str(drifted), str(caught.exception))
        self.assertEqual(drifted.read_text(encoding="utf-8"), "hand edited\n")

    def test_owned_file_deleted_by_the_user_is_restored(self) -> None:
        self.install()
        missing = self.installed(".agents/bin/sd-ai-command-pack-check.py")
        missing.unlink()

        outcome = self.install()

        self.assertTrue(missing.is_file())
        statuses = {planned.status for planned in outcome.plan.files}
        self.assertIn(PlanStatus.ABSENT, statuses)

    def test_symlinked_destination_is_refused_even_with_force(self) -> None:
        other = self.base / "elsewhere.toml"
        other.write_text("elsewhere\n", encoding="utf-8")
        link = self.installed(".gemini/commands/sd/help.toml")
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(other)

        with self.assertRaises(MachineInstallError) as caught:
            self.install(force=True)

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn("symlink", str(caught.exception))
        # --force must not silently rewrite through a link, and must not
        # touch what the link pointed at.
        self.assertTrue(link.is_symlink())
        self.assertEqual(other.read_text(encoding="utf-8"), "elsewhere\n")

    def test_symlinked_parent_directory_is_refused(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        commands = self.home / ".gemini" / "commands"
        commands.parent.mkdir(parents=True, exist_ok=True)
        commands.symlink_to(outside, target_is_directory=True)

        with self.assertRaises(MachineInstallError) as caught:
            self.install(force=True)

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn("symlink", str(caught.exception))
        self.assertEqual(list(outside.iterdir()), [])


class InterruptedRunTests(MachineInstallerTestCase):
    def interrupted_install(self) -> None:
        with self.fail_on_receipt_write():
            with self.assertRaises(MachineInstallError):
                self.install()

    def test_interrupted_run_leaves_the_journal_and_no_receipt(self) -> None:
        self.interrupted_install()

        self.assertTrue(self.intent_file.is_file())
        self.assertFalse(self.receipt_file.exists())
        self.assertTrue(self.installed(".agents/skills/sd-check/SKILL.md").is_file())
        journal = json.loads(self.intent_file.read_text(encoding="utf-8"))
        self.assertEqual(journal["schemaVersion"], machinescope.INTENT_SCHEMA_VERSION)
        self.assertEqual(len(journal["paths"]), len(PAYLOAD_ROWS))

    def test_rerun_after_interruption_converges_via_the_journal(self) -> None:
        self.interrupted_install()

        outcome = self.install()

        self.assertEqual(
            {planned.status for planned in outcome.plan.files},
            {PlanStatus.OWNED_CURRENT},
        )
        self.assertTrue(self.receipt_file.is_file())
        self.assertFalse(self.intent_file.exists())
        report = self.status(payload_root=self.payload_root)
        self.assertEqual(report["comparison"], "current")
        self.assertEqual(
            {entry["state"] for entry in report["files"]},  # type: ignore[union-attr]
            {"current"},
        )

    def test_rerun_without_the_journal_refuses_the_files_it_wrote(self) -> None:
        """Deleting the journal removes the only proof of authorship."""

        self.interrupted_install()
        self.intent_file.unlink()

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn("unowned", str(caught.exception))

    def test_journal_for_a_different_payload_does_not_confer_ownership(self) -> None:
        self.interrupted_install()
        journal = json.loads(self.intent_file.read_text(encoding="utf-8"))
        journal["payloadDigest"] = "sha256:" + "0" * 64
        self.intent_file.write_text(json.dumps(journal), encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("unowned", str(caught.exception))

    def test_stale_journal_is_reported_and_discarded(self) -> None:
        self.install()
        journal = {
            "schemaVersion": machinescope.INTENT_SCHEMA_VERSION,
            "payloadDigest": "sha256:" + "1" * 64,
            "paths": [{"family": "agents-skills", "path": "sd-check/SKILL.md"}],
        }
        self.intent_file.write_text(json.dumps(journal), encoding="utf-8")

        outcome = self.install()

        self.assertTrue(any("different payload" in note for note in outcome.plan.notes))

    def test_malformed_journal_confers_nothing(self) -> None:
        self.interrupted_install()
        self.intent_file.write_text("{ not json", encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("unowned", str(caught.exception))

    def test_journal_is_not_written_when_there_is_nothing_to_do(self) -> None:
        self.install()
        self.assertFalse(self.intent_file.exists())

        self.install()

        self.assertFalse(self.intent_file.exists())


class ForceAndBackupTests(MachineInstallerTestCase):
    def seed_collision(self, relative: str = ".gemini/commands/sd/help.toml") -> Path:
        collision = self.installed(relative)
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_text("the user's own command\n", encoding="utf-8")
        return collision

    def test_force_overwrites_and_records_the_backup_in_the_receipt(self) -> None:
        collision = self.seed_collision()

        self.install(force=True)

        backup = collision.with_name(collision.name + ".bak")
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), "the user's own command\n")
        self.assertNotEqual(collision.read_text(encoding="utf-8"), "the user's own command\n")
        entries = [
            entry for entry in self.read_receipt_json()["files"] if "backup" in entry
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "sd/help.toml")
        self.assertEqual(entries[0]["backup"]["path"], "sd/help.toml.bak")

    def test_remove_restores_the_backed_up_original_and_retires_the_bak(self) -> None:
        collision = self.seed_collision()
        self.install(force=True)
        backup = collision.with_name(collision.name + ".bak")

        outcome = self.remove()

        self.assertEqual(collision.read_text(encoding="utf-8"), "the user's own command\n")
        self.assertFalse(backup.exists())
        self.assertIn(collision, outcome.restored)
        # Everything the installer created is gone; only the restored original
        # survives, which is exactly what "clean machine" claims. Its directory
        # survives with it rather than being pruned out from under it.
        self.assert_family_roots_pruned(self.home / ".gemini" / "commands")
        self.assertEqual(list(collision.parent.iterdir()), [collision])
        self.assertFalse(self.receipt_file.exists())

    def test_backup_record_survives_a_refresh(self) -> None:
        collision = self.seed_collision()
        self.install(force=True)
        refreshed = self.write_payload(
            name="payload-v2",
            contents={".gemini/commands/sd/help.toml": "newer command\n"},
        )

        self.install(payload_root=refreshed)

        entries = [entry for entry in self.read_receipt_json()["files"] if "backup" in entry]
        self.assertEqual(len(entries), 1)
        backup = collision.with_name(collision.name + ".bak")
        self.assertEqual(backup.read_text(encoding="utf-8"), "the user's own command\n")
        # A second backup would have captured our own payload, not the original.
        self.assertFalse(collision.with_name(collision.name + ".bak1").exists())

    def test_dropping_a_forced_row_restores_the_original_instead_of_orphaning_it(self) -> None:
        """The receipt forgets a dropped row, so it must restore before it does."""

        collision = self.seed_collision()
        self.install(force=True)
        backup = collision.with_name(collision.name + ".bak")
        trimmed = tuple(row for row in PAYLOAD_ROWS if not row[0].startswith(".gemini/"))
        refreshed = self.write_payload(name="payload-v2", rows=trimmed)

        self.install(payload_root=refreshed)

        self.assertEqual(collision.read_text(encoding="utf-8"), "the user's own command\n")
        self.assertFalse(backup.exists())
        self.assertEqual(
            [entry for entry in self.read_receipt_json()["files"] if "backup" in entry], []
        )

    def test_dropping_a_row_whose_backup_vanished_still_removes_the_pack_file(self) -> None:
        collision = self.seed_collision()
        self.install(force=True)
        collision.with_name(collision.name + ".bak").unlink()
        trimmed = tuple(row for row in PAYLOAD_ROWS if not row[0].startswith(".gemini/"))
        refreshed = self.write_payload(name="payload-v2", rows=trimmed)

        self.install(payload_root=refreshed)

        self.assertFalse(collision.exists())

    def test_remove_refuses_a_backup_that_no_longer_matches_its_digest(self) -> None:
        collision = self.seed_collision()
        self.install(force=True)
        backup = collision.with_name(collision.name + ".bak")
        backup.write_text("tampered\n", encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            self.remove()

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn(str(backup), str(caught.exception))
        self.assertTrue(collision.is_file())

    def test_forced_remove_leaves_an_unverifiable_backup_in_place(self) -> None:
        collision = self.seed_collision()
        self.install(force=True)
        backup = collision.with_name(collision.name + ".bak")
        backup.write_text("tampered\n", encoding="utf-8")

        outcome = self.remove(force=True)

        self.assertEqual(outcome.restored, ())
        self.assertEqual(backup.read_text(encoding="utf-8"), "tampered\n")
        self.assertFalse(collision.exists())


class RemoveTests(MachineInstallerTestCase):
    def test_remove_deletes_owned_files_and_prunes_directories(self) -> None:
        self.install()

        outcome = self.remove()

        self.assertTrue(outcome.had_receipt)
        self.assertEqual(len(outcome.removed), len(PAYLOAD_ROWS))
        for relative in EXPECTED_INSTALLED:
            self.assertFalse(self.installed(relative).exists(), relative)
        self.assert_family_roots_pruned()
        self.assertFalse(self.receipt_file.exists())

    def test_remove_without_a_receipt_is_a_no_op(self) -> None:
        outcome = self.remove()

        self.assertFalse(outcome.had_receipt)
        self.assertEqual(outcome.removed, ())

    def test_remove_refuses_locally_modified_files(self) -> None:
        self.install()
        modified = self.installed(".agents/skills/sd-check/SKILL.md")
        modified.write_text("hand edited\n", encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            self.remove()

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn(str(modified), str(caught.exception))
        self.assertTrue(modified.is_file())
        self.assertTrue(self.receipt_file.is_file())

    def test_forced_remove_deletes_modified_files(self) -> None:
        self.install()
        modified = self.installed(".agents/skills/sd-check/SKILL.md")
        modified.write_text("hand edited\n", encoding="utf-8")

        self.remove(force=True)

        self.assertFalse(modified.exists())
        self.assertFalse(self.receipt_file.exists())

    def test_remove_dry_run_changes_nothing(self) -> None:
        self.install()

        outcome = self.remove(dry_run=True)

        self.assertTrue(outcome.dry_run)
        self.assertEqual(len(outcome.removed), len(PAYLOAD_ROWS))
        self.assertTrue(self.installed(".agents/skills/sd-check/SKILL.md").is_file())
        self.assertTrue(self.receipt_file.is_file())

    def test_remove_tolerates_a_file_the_user_already_deleted(self) -> None:
        self.install()
        self.installed(".agents/docs/SD_AI_COMMAND_PACK.md").unlink()

        outcome = self.remove()

        self.assertEqual(len(outcome.removed), len(PAYLOAD_ROWS) - 1)
        self.assertFalse(self.receipt_file.exists())


class ReceiptTrustTests(MachineInstallerTestCase):
    """A hand-edited receipt must not be able to direct a write or a delete."""

    def tampered_receipt(self, mutate) -> None:
        self.install()
        payload = self.read_receipt_json()
        mutate(payload)
        self.write_receipt_json(payload)

    def assert_receipt_refused(self, fragment: str) -> None:
        with self.assertRaises(MachineInstallError) as caught:
            self.install()
        self.assertIn(fragment, str(caught.exception))
        with self.assertRaises(MachineInstallError):
            self.remove()

    def test_traversal_path_is_refused(self) -> None:
        def mutate(payload: dict) -> None:
            payload["files"][0]["path"] = "../../../.ssh/authorized_keys"

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("not a safe relative path")

    def test_absolute_path_is_refused(self) -> None:
        def mutate(payload: dict) -> None:
            payload["files"][0]["path"] = "/etc/passwd"

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("not a safe relative path")

    def test_unknown_family_is_refused(self) -> None:
        def mutate(payload: dict) -> None:
            payload["files"][0]["family"] = "root-filesystem"

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("unknown family")

    def test_forged_backup_path_outside_the_family_root_is_refused(self) -> None:
        def mutate(payload: dict) -> None:
            payload["files"][0]["backup"] = {
                "path": "../../../.bashrc",
                "digest": "sha256:" + "0" * 64,
            }

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("backup path is not a safe relative path")

    def test_backup_path_escaping_through_a_symlink_is_refused(self) -> None:
        """Containment is checked after resolution, not on the literal string."""

        self.install()
        (self.base / "outside").mkdir(exist_ok=True)
        escape = self.home / ".agents" / "skills" / "escape"
        escape.symlink_to(self.base / "outside", target_is_directory=True)
        payload = self.read_receipt_json()
        entry = next(row for row in payload["files"] if row["family"] == "agents-skills")
        entry["backup"] = {
            "path": "escape/stolen.md",
            "digest": "sha256:" + "0" * 64,
        }
        self.write_receipt_json(payload)

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("resolves outside", str(caught.exception))

    def test_non_sha256_digest_is_refused(self) -> None:
        def mutate(payload: dict) -> None:
            payload["files"][0]["digest"] = "md5:beef"

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("not a sha256 digest")

    def test_unsupported_schema_version_is_refused(self) -> None:
        def mutate(payload: dict) -> None:
            payload["schemaVersion"] = 99

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("schemaVersion")

    def test_duplicate_entries_are_refused(self) -> None:
        def mutate(payload: dict) -> None:
            payload["files"].append(dict(payload["files"][0]))

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("repeats")

    def test_one_bad_entry_invalidates_the_whole_receipt(self) -> None:
        """No partial trust: the good entries do not survive a bad neighbor."""

        def mutate(payload: dict) -> None:
            payload["files"][-1]["executable"] = "yes"

        self.tampered_receipt(mutate)
        self.assert_receipt_refused("executable is not a boolean")

    def test_symlinked_receipt_is_refused(self) -> None:
        self.install()
        real = self.receipt_file.read_bytes()
        self.receipt_file.unlink()
        elsewhere = self.base / "planted-receipt.json"
        elsewhere.write_bytes(real)
        self.receipt_file.symlink_to(elsewhere)

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("must not be a symlink", str(caught.exception))


class StatusTests(MachineInstallerTestCase):
    def test_status_is_none_before_any_install(self) -> None:
        report = self.status()

        self.assertEqual(report["state"], "none")
        self.assertIsNone(report["packVersion"])
        self.assertEqual(report["files"], [])

    def test_status_reports_installed_state_and_versions(self) -> None:
        outcome = self.install()
        assert outcome.receipt is not None

        report = self.status(payload_root=self.payload_root)

        self.assertEqual(report["state"], "installed")
        self.assertEqual(report["packVersion"], PACK_VERSION)
        self.assertEqual(report["payloadDigest"], outcome.receipt.payload_digest)
        self.assertEqual(report["comparison"], "current")

    def test_status_reports_skew_against_a_newer_payload(self) -> None:
        self.install()
        refreshed = self.write_payload(
            name="payload-v2",
            contents={".agents/skills/sd-check/SKILL.md": "newer\n"},
        )

        report = self.status(payload_root=refreshed)

        self.assertEqual(report["comparison"], "skew")

    def test_status_detects_content_and_mode_drift(self) -> None:
        self.install()
        self.installed(".agents/skills/sd-check/SKILL.md").write_text("edited\n")
        self.installed(".agents/docs/SD_AI_COMMAND_PACK.md").unlink()
        script = self.installed(".agents/bin/sd-ai-command-pack-check.py")
        script.chmod(script.stat().st_mode & ~0o111)

        states = {
            (entry["family"], entry["path"]): entry["state"]
            for entry in self.status()["files"]  # type: ignore[union-attr]
        }

        self.assertEqual(states[("agents-skills", "sd-check/SKILL.md")], "drifted")
        self.assertEqual(states[("agents-docs", "SD_AI_COMMAND_PACK.md")], "missing")
        self.assertEqual(states[("agents-bin", "sd-ai-command-pack-check.py")], "mode-drift")

    def test_malformed_receipt_reports_invalid_not_none(self) -> None:
        self.install()
        self.receipt_file.write_text("{ not json", encoding="utf-8")

        report = self.status()

        self.assertEqual(report["state"], "invalid")
        self.assertIn("detail", report)


class AdvisoryTests(MachineInstallerTestCase):
    """The OpenCode external-skills opt-out is reported, never enforced."""

    def test_no_advisory_when_the_opt_outs_are_unset(self) -> None:
        outcome = self.install()

        self.assertEqual(outcome.advisories, ())

    def test_opt_out_is_reported_but_the_payload_still_installs(self) -> None:
        environ = dict(self.environ)
        environ["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "1"

        outcome = self.install(environ=environ)

        self.assertEqual(len(outcome.advisories), 1)
        self.assertIn("OPENCODE_DISABLE_EXTERNAL_SKILLS", outcome.advisories[0])
        self.assertTrue(self.installed(".agents/skills/sd-check/SKILL.md").is_file())

    def test_both_opt_outs_are_named_in_one_line(self) -> None:
        environ = dict(self.environ)
        environ["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "1"
        environ["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] = "1"

        advisory = machinescope.opencode_skill_advisory(environ)

        assert advisory is not None
        self.assertIn("OPENCODE_DISABLE_EXTERNAL_SKILLS", advisory)
        self.assertIn("OPENCODE_DISABLE_CLAUDE_CODE_SKILLS", advisory)

    def test_a_value_other_than_one_is_not_an_opt_out(self) -> None:
        self.assertIsNone(
            machinescope.opencode_skill_advisory({"OPENCODE_DISABLE_EXTERNAL_SKILLS": "0"})
        )


class CommandLineTests(MachineInstallerTestCase):
    def run_cli(self, *args: str) -> int:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = machinescope.main(
                [
                    *args,
                    "--home",
                    str(self.home),
                    "--state-home",
                    str(self.state_home),
                ]
            )
        self.output = stream.getvalue()
        return code

    def setUp(self) -> None:
        super().setUp()
        # The CLI reads XDG from the process environment rather than an
        # injected mapping, so point it at the scratch home for these tests.
        patcher = mock.patch.dict(os.environ, self.environ, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_install_status_and_remove_round_trip(self) -> None:
        self.assertEqual(self.run_cli("install", "--payload", str(self.payload_root)), EXIT_OK)
        self.assertTrue(self.installed(".agents/skills/sd-check/SKILL.md").is_file())

        self.assertEqual(self.run_cli("status", "--json"), EXIT_OK)
        report = json.loads(self.output)
        self.assertEqual(report["state"], "installed")
        self.assertEqual(report["packVersion"], PACK_VERSION)

        self.assertEqual(self.run_cli("remove"), EXIT_OK)
        self.assert_family_roots_pruned()

    def test_conflict_exits_two(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_text("mine\n", encoding="utf-8")

        code = self.run_cli("install", "--payload", str(self.payload_root))

        self.assertEqual(code, EXIT_CONFLICT)
        self.assertIn(str(collision), self.output)

    def test_missing_payload_exits_one(self) -> None:
        code = self.run_cli("install", "--payload", str(self.base / "absent"))

        self.assertEqual(code, machinescope.EXIT_ERROR)

    def test_dry_run_reports_without_writing(self) -> None:
        code = self.run_cli("install", "--payload", str(self.payload_root), "--dry-run")

        self.assertEqual(code, EXIT_OK)
        self.assertFalse((self.home / ".agents").exists())


class ResolutionTests(MachineInstallerTestCase):
    """Home, state root, and the shared helper library the ladder lives in."""

    @contextlib.contextmanager
    def forgotten_shared_lib(self):
        """Drop the cached helper so a load path can be exercised again."""

        cached = machinescope._shared_lib_cache
        imported = sys.modules.pop(machinescope.SHARED_LIB_MODULE, None)
        machinescope._shared_lib_cache = None
        try:
            yield
        finally:
            machinescope._shared_lib_cache = cached
            if imported is not None:
                sys.modules[machinescope.SHARED_LIB_MODULE] = imported
            else:
                sys.modules.pop(machinescope.SHARED_LIB_MODULE, None)

    def test_helper_already_imported_is_reused(self) -> None:
        self.install()

        self.assertIs(
            machinescope._load_shared_lib(),
            sys.modules[machinescope.SHARED_LIB_MODULE],
        )

    def test_helper_is_found_in_the_second_candidate_directory(self) -> None:
        """A plugin root serves the helper from `bin/`, not `scripts/`."""

        with self.forgotten_shared_lib():
            with mock.patch.object(
                machinescope, "SHARED_LIB_DIRECTORIES", ("no-such-dir", "scripts")
            ):
                module = machinescope._shared_lib()

        self.assertTrue(hasattr(module, "resolve_state_root"))

    def test_missing_helper_is_a_clear_error(self) -> None:
        with self.forgotten_shared_lib():
            with mock.patch.object(machinescope, "SHARED_LIB_DIRECTORIES", ("no-such-dir",)):
                with self.assertRaises(MachineInstallError) as caught:
                    machinescope._shared_lib()

        self.assertIn("not found beside the installer package", str(caught.exception))

    def test_a_failing_helper_import_does_not_leave_a_broken_module(self) -> None:
        class Exploding:
            def create_module(self, spec: object) -> None:
                return None

            def exec_module(self, module: object) -> None:
                raise RuntimeError("boom")

        spec = importlib.machinery.ModuleSpec(machinescope.SHARED_LIB_MODULE, Exploding())
        with self.forgotten_shared_lib():
            with mock.patch.object(
                machinescope.importlib.util, "spec_from_file_location", return_value=spec
            ):
                with self.assertRaises(RuntimeError):
                    machinescope._shared_lib()
            self.assertNotIn(machinescope.SHARED_LIB_MODULE, sys.modules)

    def test_unresolvable_home_is_refused(self) -> None:
        with mock.patch.object(Path, "home", side_effect=RuntimeError("no home")):
            with self.assertRaises(MachineInstallError) as caught:
                machinescope.resolve_home()

        self.assertIn("cannot resolve home directory", str(caught.exception))

    def test_relative_home_is_refused(self) -> None:
        with self.assertRaises(MachineInstallError) as caught:
            machinescope.resolve_home(Path("relative/home"))

        self.assertIn("must be absolute", str(caught.exception))

    def test_default_home_is_the_users_home(self) -> None:
        with mock.patch.object(Path, "home", return_value=Path("/somewhere/else")):
            self.assertEqual(machinescope.resolve_home(), Path("/somewhere/else"))

    def test_relative_state_home_is_refused(self) -> None:
        with self.assertRaises(MachineInstallError) as caught:
            self.install(state_home=Path("relative/state"))

        self.assertIn("cannot resolve state root", str(caught.exception))

    def test_symlinked_state_directory_is_refused(self) -> None:
        self.state_home.mkdir(parents=True)
        (self.state_home / machinescope.MACHINE_STATE_DIR).symlink_to(self.base / "elsewhere")

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("cannot prepare state directory", str(caught.exception))

    def test_receipt_path_reports_the_location_without_creating_it(self) -> None:
        path = machinescope.receipt_path(
            environ=self.environ,
            home=self.home,
            state_home=self.state_home,
        )

        self.assertEqual(path, self.receipt_file)
        self.assertFalse(self.state_home.exists())

    def test_receipt_path_defaults_to_the_process_environment(self) -> None:
        with mock.patch.dict(os.environ, {"SD_AI_COMMAND_PACK_STATE_HOME": str(self.state_home)}):
            self.assertEqual(machinescope.receipt_path(home=self.home), self.receipt_file)

    def test_default_payload_root_sits_beside_the_package(self) -> None:
        default = machinescope.default_payload_root()

        self.assertEqual(default.name, machinescope.DEFAULT_PAYLOAD_DIRNAME)
        self.assertEqual(default.parent.name, Path(machinescope.__file__).parents[1].name)


class PayloadLoadingTests(MachineInstallerTestCase):
    def test_missing_payload_root_is_refused(self) -> None:
        with self.assertRaises(MachineInstallError) as caught:
            machinescope.load_payload(self.base / "absent")

        self.assertIn("payload root not found", str(caught.exception))

    def test_unreadable_partition_is_refused(self) -> None:
        (self.payload_root / "partition.json").write_text("{ not json", encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            machinescope.load_payload(self.payload_root)

        self.assertIn("unreadable", str(caught.exception))

    def test_payload_without_installable_files_is_refused(self) -> None:
        empty = self.base / "empty-payload"
        empty.mkdir()
        (empty / "partition.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "manifestVersion": PACK_VERSION,
                    "platforms": {},
                    "files": [],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(MachineInstallError) as caught:
            machinescope.load_payload(empty)

        self.assertIn("holds no installable files", str(caught.exception))

    def test_unreadable_payload_file_is_refused(self) -> None:
        blocked = self.payload_root / ".agents" / "skills" / "sd-check" / "SKILL.md"

        with self.unreadable(blocked):
            with self.assertRaises(MachineInstallError) as caught:
                machinescope.load_payload(self.payload_root)

        self.assertIn("cannot be read", str(caught.exception))
        self.assertIn(".agents/skills/sd-check/SKILL.md", str(caught.exception))


class WriteFailureTests(MachineInstallerTestCase):
    def test_a_file_where_a_directory_belongs_is_reported(self) -> None:
        blocker = self.home / ".agents" / "skills" / "sd-check"
        blocker.parent.mkdir(parents=True)
        blocker.write_text("in the way\n", encoding="utf-8")

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("cannot create directory", str(caught.exception))

    def test_a_failing_atomic_write_is_reported_without_its_prefix(self) -> None:
        with mock.patch.object(
            machinescope,
            "atomic_write_bytes",
            side_effect=SystemExit("error: cannot write /somewhere: disk full"),
        ):
            with self.assertRaises(MachineInstallError) as caught:
                self.install()

        self.assertEqual(str(caught.exception), "cannot write /somewhere: disk full")

    def test_a_failing_backup_copy_is_reported(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")

        with mock.patch.object(
            machinescope.shutil, "copy2", side_effect=OSError(28, "No space left")
        ):
            with self.assertRaises(MachineInstallError) as caught:
                self.install(force=True)

        self.assertIn("cannot back up", str(caught.exception))

    def test_an_unsafe_backup_path_is_refused(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")

        with mock.patch.object(machinescope, "_safe_relative", return_value=None):
            with self.assertRaises(MachineInstallError) as caught:
                self.install(force=True)

        self.assertIn("unsafe backup path", str(caught.exception))

    def test_backups_do_not_overwrite_an_existing_bak_file(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")
        occupied = collision.with_name(collision.name + ".bak")
        occupied.write_text("an older backup\n", encoding="utf-8")

        self.install(force=True)

        self.assertEqual(occupied.read_text(encoding="utf-8"), "an older backup\n")
        second = collision.with_name(collision.name + ".bak1")
        self.assertEqual(second.read_text(encoding="utf-8"), "mine\n")
        entry = next(
            row for row in self.read_receipt_json()["files"] if row["family"] == "gemini-commands"
        )
        self.assertEqual(entry["backup"]["path"], "sd/help.toml.bak1")

    def test_a_failing_delete_is_reported(self) -> None:
        self.install()
        doomed = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")

        with self.undeletable(doomed):
            with self.assertRaises(MachineInstallError) as caught:
                self.remove()

        self.assertIn("cannot remove", str(caught.exception))

    def test_a_failing_receipt_delete_is_reported(self) -> None:
        self.install()

        with self.undeletable(self.receipt_file):
            with self.assertRaises(MachineInstallError) as caught:
                self.remove()

        self.assertIn("cannot remove", str(caught.exception))

    def test_a_failing_restore_is_reported(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")
        self.install(force=True)

        with mock.patch.object(machinescope.os, "replace", side_effect=OSError(5, "I/O error")):
            with self.assertRaises(MachineInstallError) as caught:
                self.remove()

        self.assertIn("cannot restore", str(caught.exception))

    def test_a_target_resolving_outside_its_family_is_refused(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        nested = self.home / ".gemini" / "commands" / "sd"
        nested.parent.mkdir(parents=True)
        nested.symlink_to(outside, target_is_directory=True)

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("resolves outside gemini-commands", str(caught.exception))
        self.assertEqual(list(outside.iterdir()), [])


class DestinationShapeTests(MachineInstallerTestCase):
    def test_a_directory_at_a_target_path_is_refused(self) -> None:
        blocker = self.installed(".gemini/commands/sd/help.toml")
        blocker.mkdir(parents=True)

        with self.assertRaises(MachineInstallError) as caught:
            self.install(force=True)

        self.assertEqual(caught.exception.exit_code, EXIT_CONFLICT)
        self.assertIn("not-a-file", str(caught.exception))

    def test_an_unreadable_destination_classifies_as_drifted(self) -> None:
        self.install()
        blocked = self.installed(".agents/skills/sd-check/SKILL.md")

        with self.unreadable(blocked):
            with self.assertRaises(MachineInstallError) as caught:
                self.install()

        self.assertIn("cannot be read", str(caught.exception))

    def test_remove_leaves_a_target_replaced_by_a_symlink(self) -> None:
        self.install()
        target = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")
        target.unlink()
        target.symlink_to(self.base / "elsewhere.md")

        outcome = self.remove(force=True)

        self.assertTrue(target.is_symlink())
        self.assertIn((target, "is a symlink"), outcome.skipped)

    def test_remove_leaves_a_target_replaced_by_a_directory(self) -> None:
        self.install()
        target = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")
        target.unlink()
        target.mkdir()

        outcome = self.remove(force=True)

        self.assertTrue(target.is_dir())
        self.assertIn((target, "is not a regular file"), outcome.skipped)

    def relocate_behind_a_symlink(self) -> Path:
        """Turn an installed directory into a link to a sibling inside the root.

        A link pointing *out* of the family root is already refused when the
        receipt is parsed; this shape stays contained, so only the removal
        planner can catch it.
        """

        skills = self.home / ".agents" / "skills"
        relocated = skills / "relocated"
        (skills / "sd-check").rename(relocated)
        (skills / "sd-check").symlink_to(relocated, target_is_directory=True)
        return relocated

    def test_remove_refuses_a_target_behind_a_symlinked_parent(self) -> None:
        self.install()
        relocated = self.relocate_behind_a_symlink()

        with self.assertRaises(MachineInstallError) as caught:
            self.remove()

        self.assertIn("parent directory is a symlink", str(caught.exception))
        self.assertTrue((relocated / "SKILL.md").is_file())

    def test_forced_remove_does_not_delete_through_a_symlinked_parent(self) -> None:
        self.install()
        relocated = self.relocate_behind_a_symlink()

        outcome = self.remove(force=True)

        self.assertTrue((relocated / "SKILL.md").is_file())
        self.assertTrue((relocated / "references" / "notes.md").is_file())
        self.assertNotIn(self.installed(".agents/skills/sd-check/SKILL.md"), outcome.removed)
        # The rest of the receipt still goes.
        self.assertFalse(self.installed(".agents/bin/sd-ai-command-pack-check.py").exists())

    def test_remove_refuses_an_unreadable_target(self) -> None:
        self.install()
        blocked = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")

        with self.unreadable(blocked):
            with self.assertRaises(MachineInstallError) as caught:
                self.remove()

        self.assertIn("cannot be read", str(caught.exception))

    def test_remove_dry_run_reports_a_restorable_backup(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")
        self.install(force=True)

        outcome = self.remove(dry_run=True)

        self.assertEqual(outcome.restored, (collision,))
        self.assertTrue(collision.with_name(collision.name + ".bak").is_file())

    def test_a_deleted_backup_blocks_removal_until_forced(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")
        self.install(force=True)
        collision.with_name(collision.name + ".bak").unlink()

        with self.assertRaises(MachineInstallError) as caught:
            self.remove()
        self.assertIn("recorded backup is missing", str(caught.exception))

        outcome = self.remove(force=True)
        self.assertEqual(outcome.restored, ())


class MalformedReceiptTests(MachineInstallerTestCase):
    """Shapes `parse_receipt` must reject before trusting any entry."""

    def assert_refused(self, payload: object, fragment: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.receipt_file.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(MachineInstallError) as caught:
            self.install()
        self.assertIn(fragment, str(caught.exception))

    def valid_payload(self) -> dict:
        self.install()
        payload = self.read_receipt_json()
        self.remove()
        return payload

    def test_receipt_that_is_not_an_object(self) -> None:
        self.assert_refused([], "receipt is not a JSON object")

    def test_receipt_missing_a_required_string(self) -> None:
        payload = self.valid_payload()
        del payload["packVersion"]
        self.assert_refused(payload, "packVersion is missing")

    def test_receipt_with_a_non_digest_payload_digest(self) -> None:
        payload = self.valid_payload()
        payload["payloadDigest"] = "not-a-digest"
        self.assert_refused(payload, "payloadDigest is not a sha256 digest")

    def test_receipt_whose_files_are_not_an_array(self) -> None:
        payload = self.valid_payload()
        payload["files"] = {}
        self.assert_refused(payload, "files is not an array")

    def test_receipt_entry_that_is_not_an_object(self) -> None:
        payload = self.valid_payload()
        payload["files"] = ["nonsense"]
        self.assert_refused(payload, "entry 0 is not an object")

    def test_receipt_entry_with_a_non_string_path(self) -> None:
        payload = self.valid_payload()
        payload["files"][0]["path"] = 42
        self.assert_refused(payload, "path is not a safe relative path")

    def test_receipt_entry_with_a_denormalized_path(self) -> None:
        payload = self.valid_payload()
        payload["files"][0]["path"] = "sd//help.toml"
        self.assert_refused(payload, "path is not a safe relative path")

    def test_receipt_entry_whose_backup_is_not_an_object(self) -> None:
        payload = self.valid_payload()
        payload["files"][0]["backup"] = "sd/help.toml.bak"
        self.assert_refused(payload, "backup is not an object")

    def test_receipt_entry_with_a_non_digest_backup(self) -> None:
        payload = self.valid_payload()
        payload["files"][0]["backup"] = {"path": "kept.bak", "digest": "nope"}
        self.assert_refused(payload, "backup digest is not a sha256 digest")

    def test_receipt_path_escaping_through_a_symlink_is_refused(self) -> None:
        self.install()
        (self.base / "outside").mkdir(exist_ok=True)
        (self.home / ".agents" / "skills" / "escape").symlink_to(
            self.base / "outside", target_is_directory=True
        )
        payload = self.read_receipt_json()
        entry = next(row for row in payload["files"] if row["family"] == "agents-skills")
        entry["path"] = "escape/stolen.md"
        self.write_receipt_json(payload)

        with self.assertRaises(MachineInstallError) as caught:
            self.install()

        self.assertIn("resolves outside agents-skills", str(caught.exception))

    def test_a_resolution_failure_refuses_rather_than_admits(self) -> None:
        with mock.patch.object(Path, "resolve", side_effect=OSError(40, "Too many levels")):
            self.assertIsNone(machinescope._resolved_within(self.home, "a/b"))


class SharedPayloadModelTests(unittest.TestCase):
    """`installer.machinepayload`, shared with the plugin generator.

    The engine reports these failures in its own error model, so the model
    itself returns reason strings rather than raising; each shape below is one
    way a bundled partition can be wrong.
    """

    def valid_partition(self) -> dict:
        return {
            "schemaVersion": 1,
            "manifestVersion": PACK_VERSION,
            "platforms": {"shared": {"scope": "machine", "provisional": False}},
            "files": [
                {
                    "target": ".agents/skills/sd-check/SKILL.md",
                    "platform": "shared",
                    "category": "machine-other",
                    "sharedRuntime": False,
                }
            ],
        }

    def gate(self) -> machinepayload.PartitionGate:
        gate = machinepayload.parse_partition(self.valid_partition())
        assert isinstance(gate, machinepayload.PartitionGate)
        return gate

    def assert_reason(self, mutate, fragment: str) -> None:
        payload = self.valid_partition()
        mutate(payload)
        reason = machinepayload.parse_partition(payload)
        self.assertIsInstance(reason, str)
        self.assertIn(fragment, str(reason))

    def test_valid_partition_admits_its_row(self) -> None:
        self.assertIsNone(self.gate().reject_reason(".agents/skills/sd-check/SKILL.md"))

    def test_unknown_target_is_rejected(self) -> None:
        self.assertEqual(self.gate().reject_reason("nope.md"), "no surface-partition row")

    def test_repo_native_category_without_shared_runtime_is_rejected(self) -> None:
        payload = self.valid_partition()
        payload["files"][0]["category"] = "repo-native"
        gate = machinepayload.parse_partition(payload)
        assert isinstance(gate, machinepayload.PartitionGate)

        self.assertEqual(
            gate.reject_reason(".agents/skills/sd-check/SKILL.md"),
            "category repo-native is not machine-installable",
        )

    def test_row_naming_a_platform_with_no_disposition_is_rejected(self) -> None:
        payload = self.valid_partition()
        payload["files"][0]["platform"] = "ghost"
        gate = machinepayload.parse_partition(payload)
        assert isinstance(gate, machinepayload.PartitionGate)

        self.assertEqual(
            gate.reject_reason(".agents/skills/sd-check/SKILL.md"),
            "platform ghost has no surface-partition disposition",
        )

    def test_partition_that_is_not_an_object(self) -> None:
        self.assertEqual(
            machinepayload.parse_partition([]), "partition is not a JSON object"
        )

    def test_partition_without_a_manifest_version(self) -> None:
        self.assert_reason(lambda p: p.pop("manifestVersion"), "no manifestVersion")

    def test_partition_without_a_files_array(self) -> None:
        self.assert_reason(lambda p: p.pop("files"), "no files array")

    def test_partition_without_a_platforms_object(self) -> None:
        self.assert_reason(lambda p: p.pop("platforms"), "no platforms object")

    def test_partition_with_a_non_object_file_row(self) -> None:
        self.assert_reason(
            lambda p: p.__setitem__("files", ["nonsense"]), "non-object entry"
        )

    def test_partition_row_without_a_target(self) -> None:
        self.assert_reason(lambda p: p["files"][0].pop("target"), "no target/category")

    def test_partition_row_without_a_platform(self) -> None:
        self.assert_reason(lambda p: p["files"][0].pop("platform"), "has no platform")

    def test_partition_platform_that_is_not_an_object(self) -> None:
        self.assert_reason(
            lambda p: p["platforms"].__setitem__("shared", "machine"),
            "platform shared is not an object",
        )

    def test_partition_platform_without_a_scope(self) -> None:
        self.assert_reason(
            lambda p: p["platforms"]["shared"].pop("scope"), "platform shared has no scope"
        )

    def test_missing_partition_file_is_reported(self) -> None:
        reason = machinepayload.read_partition(Path("/nonexistent/partition.json"))

        self.assertIsInstance(reason, str)
        self.assertIn("bundled partition not found", str(reason))

    def test_opencode_root_falls_back_to_the_home_config_directory(self) -> None:
        roots = machinepayload.family_roots(home=Path("/home/user"), environ={})

        self.assertEqual(
            roots["opencode-commands"], Path("/home/user/.config/opencode/commands")
        )

    def test_a_relative_xdg_config_home_is_ignored(self) -> None:
        roots = machinepayload.family_roots(
            home=Path("/home/user"), environ={"XDG_CONFIG_HOME": "relative/config"}
        )

        self.assertEqual(
            roots["opencode-commands"], Path("/home/user/.config/opencode/commands")
        )


class MalformedIntentTests(unittest.TestCase):
    """A journal that cannot be trusted confers no ownership at all."""

    def valid(self) -> dict:
        return {
            "schemaVersion": machinescope.INTENT_SCHEMA_VERSION,
            "payloadDigest": "sha256:" + "a" * 64,
            "paths": [{"family": "agents-skills", "path": "sd-check/SKILL.md"}],
        }

    def test_valid_journal_parses(self) -> None:
        intent = machinescope.parse_intent(self.valid())

        assert intent is not None
        self.assertIn(("agents-skills", "sd-check/SKILL.md"), intent.paths)

    def test_non_object_is_rejected(self) -> None:
        self.assertIsNone(machinescope.parse_intent(["nope"]))

    def test_wrong_schema_version_is_rejected(self) -> None:
        payload = self.valid()
        payload["schemaVersion"] = 99
        self.assertIsNone(machinescope.parse_intent(payload))

    def test_non_digest_is_rejected(self) -> None:
        payload = self.valid()
        payload["payloadDigest"] = "sha256:short"
        self.assertIsNone(machinescope.parse_intent(payload))

    def test_paths_that_are_not_an_array_are_rejected(self) -> None:
        payload = self.valid()
        payload["paths"] = {}
        self.assertIsNone(machinescope.parse_intent(payload))

    def test_path_entry_that_is_not_an_object_is_rejected(self) -> None:
        payload = self.valid()
        payload["paths"] = ["sd-check/SKILL.md"]
        self.assertIsNone(machinescope.parse_intent(payload))

    def test_unknown_family_is_rejected(self) -> None:
        payload = self.valid()
        payload["paths"] = [{"family": "root-filesystem", "path": "x"}]
        self.assertIsNone(machinescope.parse_intent(payload))

    def test_unsafe_path_is_rejected(self) -> None:
        payload = self.valid()
        payload["paths"] = [{"family": "agents-skills", "path": "../escape"}]
        self.assertIsNone(machinescope.parse_intent(payload))


class StatusFileStateTests(MachineInstallerTestCase):
    def file_states(self) -> dict[tuple[str, str], str]:
        return {
            (entry["family"], entry["path"]): entry["state"]
            for entry in self.status()["files"]  # type: ignore[union-attr]
        }

    def test_symlinked_file_is_reported(self) -> None:
        self.install()
        target = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")
        target.unlink()
        target.symlink_to(self.base / "elsewhere.md")

        self.assertEqual(self.file_states()[("agents-docs", "SD_AI_COMMAND_PACK.md")], "symlink")

    def test_directory_at_a_file_path_is_reported_as_drift(self) -> None:
        self.install()
        target = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")
        target.unlink()
        target.mkdir()

        self.assertEqual(self.file_states()[("agents-docs", "SD_AI_COMMAND_PACK.md")], "drifted")

    def test_unreadable_file_is_reported(self) -> None:
        self.install()
        blocked = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")

        with self.unreadable(blocked):
            states = self.file_states()

        self.assertEqual(states[("agents-docs", "SD_AI_COMMAND_PACK.md")], "unreadable")


class CommandOutputTests(MachineInstallerTestCase):
    """The CLI's own reporting, which is all an operator ever sees."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.dict(os.environ, self.environ, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *args: str) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = machinescope.main(
                [*args, "--home", str(self.home), "--state-home", str(self.state_home)]
            )
        return code, stream.getvalue()

    def test_install_json_reports_counts_and_digest(self) -> None:
        code, output = self.run_cli("install", "--payload", str(self.payload_root), "--json")

        self.assertEqual(code, EXIT_OK)
        report = json.loads(output)
        self.assertTrue(report["changed"])
        self.assertEqual(report["counts"]["absent"], len(PAYLOAD_ROWS))
        self.assertEqual(report["packVersion"], PACK_VERSION)

    def test_install_prints_notes_and_removals(self) -> None:
        self.run_cli("install", "--payload", str(self.payload_root))
        self.intent_file.write_text(
            json.dumps(
                {
                    "schemaVersion": machinescope.INTENT_SCHEMA_VERSION,
                    "payloadDigest": "sha256:" + "1" * 64,
                    "paths": [],
                }
            ),
            encoding="utf-8",
        )
        trimmed = self.write_payload(
            name="payload-v2",
            rows=tuple(row for row in PAYLOAD_ROWS if not row[0].startswith(".gemini/")),
        )

        code, output = self.run_cli("install", "--payload", str(trimmed))

        self.assertEqual(code, EXIT_OK)
        self.assertIn("note: discarding an intent journal", output)
        self.assertIn("removed", output)
        self.assertIn("help.toml", output)

    def test_install_reports_a_dropped_row_restored_from_its_backup(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")
        self.run_cli("install", "--payload", str(self.payload_root), "--force")
        trimmed = self.write_payload(
            name="payload-v2",
            rows=tuple(row for row in PAYLOAD_ROWS if not row[0].startswith(".gemini/")),
        )

        code, output = self.run_cli("install", "--payload", str(trimmed))

        self.assertEqual(code, EXIT_OK)
        self.assertIn(f"restored {collision} from its recorded backup", output)
        self.assertNotIn(f"removed {collision}", output)

    def test_install_json_separates_removed_from_restored(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")
        self.run_cli("install", "--payload", str(self.payload_root), "--force")
        trimmed = self.write_payload(
            name="payload-v2",
            rows=tuple(row for row in PAYLOAD_ROWS if not row[0].startswith(".gemini/")),
        )

        _, output = self.run_cli("install", "--payload", str(trimmed), "--json")

        report = json.loads(output)
        self.assertEqual(report["restored"], [str(collision)])
        self.assertEqual(report["removed"], [])

    def test_install_uses_the_bundled_payload_when_none_is_given(self) -> None:
        with mock.patch.object(
            machinescope, "default_payload_root", return_value=self.payload_root
        ):
            code, _ = self.run_cli("install")

        self.assertEqual(code, EXIT_OK)
        self.assertTrue(self.installed(".agents/skills/sd-check/SKILL.md").is_file())

    def test_install_without_a_payload_or_a_bundle_is_an_error(self) -> None:
        with mock.patch.object(
            machinescope, "default_payload_root", return_value=self.base / "absent"
        ):
            code, output = self.run_cli("install")

        self.assertEqual(code, machinescope.EXIT_ERROR)
        self.assertIn("pass --payload", output)

    def test_remove_json_lists_removed_and_restored_paths(self) -> None:
        collision = self.installed(".gemini/commands/sd/help.toml")
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")
        self.run_cli("install", "--payload", str(self.payload_root), "--force")

        code, output = self.run_cli("remove", "--json")

        self.assertEqual(code, EXIT_OK)
        report = json.loads(output)
        self.assertTrue(report["hadReceipt"])
        self.assertEqual(len(report["removed"]), len(PAYLOAD_ROWS))
        self.assertEqual(report["restored"], [str(collision)])

    def test_remove_without_a_receipt_says_so(self) -> None:
        code, output = self.run_cli("remove")

        self.assertEqual(code, EXIT_OK)
        self.assertIn("no machine receipt found", output)

    def test_remove_prints_what_it_skipped(self) -> None:
        self.run_cli("install", "--payload", str(self.payload_root))
        target = self.installed(".agents/docs/SD_AI_COMMAND_PACK.md")
        target.unlink()
        target.mkdir()

        code, output = self.run_cli("remove", "--force")

        self.assertEqual(code, EXIT_OK)
        self.assertIn("skipped", output)
        self.assertIn(str(target), output)

    def test_status_human_output_covers_every_state(self) -> None:
        _, output = self.run_cli("status")
        self.assertIn("machine install: none", output)

        self.run_cli("install", "--payload", str(self.payload_root))
        _, output = self.run_cli("status", "--payload", str(self.payload_root))
        self.assertIn("machine install: installed", output)
        self.assertIn(f"pack version:   {PACK_VERSION}", output)
        self.assertIn("payload:        current", output)

        _, output = self.run_cli("status")
        self.assertIn("machine install: installed", output)
        self.assertNotIn("payload:", output)

        self.receipt_file.write_text("{ not json", encoding="utf-8")
        _, output = self.run_cli("status")
        self.assertIn("machine install: invalid", output)
        self.assertIn("detail:", output)

    def test_dry_run_install_says_it_would_install(self) -> None:
        code, output = self.run_cli(
            "install", "--payload", str(self.payload_root), "--dry-run"
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("would install", output)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
