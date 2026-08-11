"""Machine payload staging: what a checkout produces, and what refuses.

`install.py --machine` and (from the next step) the plugin generator both build
the machine payload from the same checkout through `installer.machinestage`, so
these tests are organized around what could differ between the two if the build
were not shared:

* **Selection** — the partition decides, so a provisional platform or a
  non-machine category contributes nothing, and a row without a destination
  family fails the build instead of landing somewhere by accident.
* **Rewriting** — the relocated references point at `~/.agents`, verified on
  the real checkout as well as on synthetic roots, because the gates only bind
  if they run against what the pack actually ships.
* **Containment** — `--machine` into a scratch prefix must stay inside it,
  including the XDG-derived OpenCode root (the one family that does not hang
  off the home directory) and the receipt, which an ambient state-root override
  would otherwise park beside the real home while naming the prefix's files.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:  # pragma: no cover - import shim
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

import install
from installer import machinepayload, machinescope, machinestage, references

PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase
contextlib = _support.contextlib
io = _support.io
mock = _support.mock

SCRIPT_BODY = "#!/usr/bin/env bash\nprintf 'probe\\n'\n"
SKILL_BODY = (
    "# Thing\n\n"
    "```bash\n"
    "bash scripts/sd-ai-command-pack-probe.sh --json\n"
    "```\n\n"
    "See `docs/SD_AI_COMMAND_PACK.md` for the toggles.\n"
)


class StageFixtureCase(unittest.TestCase):
    """Synthetic checkouts, small enough to reason about row by row."""

    def baseline_rows(self) -> list[dict[str, object]]:
        return [
            {
                "target": ".agents/skills/sd-thing/SKILL.md",
                "platform": "shared",
                "category": "machine-other",
                "content": SKILL_BODY,
            },
            {
                "target": "docs/SD_AI_COMMAND_PACK.md",
                "platform": "shared",
                "category": "machine-other",
                "content": "# Manual\n",
            },
            {
                "target": "scripts/sd-ai-command-pack-probe.sh",
                "platform": "shared",
                "category": "machine-claude",
                "sharedRuntime": True,
                "content": SCRIPT_BODY,
            },
            {
                "target": "scripts/sd_ai_command_pack_lib.py",
                "platform": "shared",
                "category": "machine-claude",
                "sharedRuntime": True,
                "content": "VALUE = 1\n",
            },
            {
                "target": ".gemini/commands/sd/thing.toml",
                "platform": "gemini",
                "category": "machine-other",
                "content": 'prompt = """\nrun sd-thing\n"""\n',
            },
        ]

    def build_root(
        self,
        rows: list[dict[str, object]] | None = None,
        *,
        version: str = "9.9.9",
        platforms: dict[str, dict[str, object]] | None = None,
    ) -> Path:
        entries = self.baseline_rows() if rows is None else rows
        tempdir = tempfile.TemporaryDirectory(prefix="sd-machine-stage-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)

        manifest_rows: list[dict[str, str]] = []
        partition_rows: list[dict[str, object]] = []
        for row in entries:
            target = str(row["target"])
            source = str(row.get("source") or f"templates/{target}")
            if row.get("manifest", True):
                manifest_rows.append(
                    {
                        "platform": str(row["platform"]),
                        "kind": str(row.get("kind", "skill")),
                        "source": source,
                        "target": target,
                    }
                )
            partition_rows.append(
                {
                    "target": target,
                    "platform": str(row["platform"]),
                    "category": str(row["category"]),
                    "sharedRuntime": bool(row.get("sharedRuntime", False)),
                }
            )
            if row.get("write", True):
                path = root / source
                path.parent.mkdir(parents=True, exist_ok=True)
                content = row.get("content", "# Thing\n")
                if isinstance(content, bytes):
                    path.write_bytes(content)
                else:
                    path.write_text(str(content), encoding="utf-8")

        (root / "manifest.json").write_text(
            json.dumps({"version": version, "files": manifest_rows}, indent=2) + "\n",
            encoding="utf-8",
        )
        artifact = root / machinestage.PARTITION_PATH
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "manifestVersion": version,
                    "platforms": platforms
                    or {
                        platform: {"scope": "machine", "provisional": False}
                        for platform in {str(row["platform"]) for row in entries}
                    },
                    "files": partition_rows,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return root


class SelectionTests(StageFixtureCase):
    """The partition decides what the payload carries."""

    def test_machine_other_and_shared_runtime_rows_are_staged(self) -> None:
        staged = machinestage.build_payload(self.build_root())

        self.assertEqual(
            sorted(staged),
            [
                ".agents/skills/sd-thing/SKILL.md",
                ".gemini/commands/sd/thing.toml",
                "docs/SD_AI_COMMAND_PACK.md",
                machinepayload.PARTITION_FILE,
                "scripts/sd-ai-command-pack-probe.sh",
                "scripts/sd_ai_command_pack_lib.py",
            ],
        )

    def test_only_commands_carry_the_executable_bit(self) -> None:
        staged = machinestage.build_payload(self.build_root())

        self.assertTrue(staged["scripts/sd-ai-command-pack-probe.sh"].executable)
        self.assertFalse(staged["scripts/sd_ai_command_pack_lib.py"].executable)
        self.assertFalse(staged[".agents/skills/sd-thing/SKILL.md"].executable)

    def test_a_provisional_platform_contributes_nothing(self) -> None:
        rows = self.baseline_rows()
        root = self.build_root(
            rows,
            platforms={
                "shared": {"scope": "machine", "provisional": False},
                "gemini": {"scope": "machine", "provisional": True},
            },
        )

        staged = machinestage.build_payload(root)

        self.assertNotIn(".gemini/commands/sd/thing.toml", staged)

    def test_a_repo_native_platform_contributes_nothing(self) -> None:
        rows = self.baseline_rows()
        root = self.build_root(
            rows,
            platforms={
                "shared": {"scope": "machine", "provisional": False},
                "gemini": {"scope": "repo-native", "provisional": False},
            },
        )

        staged = machinestage.build_payload(root)

        self.assertNotIn(".gemini/commands/sd/thing.toml", staged)

    def test_a_partition_admitting_nothing_fails(self) -> None:
        rows = self.baseline_rows()
        root = self.build_root(
            rows,
            platforms={
                "shared": {"scope": "repo-native", "provisional": False},
                "gemini": {"scope": "repo-native", "provisional": False},
            },
        )

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "admits no machine-installable rows"
        ):
            machinestage.build_payload(root)

    def test_a_row_without_a_destination_family_fails(self) -> None:
        rows = self.baseline_rows()
        rows.append(
            {
                "target": ".agents/agents/sd-thing.md",
                "platform": "shared",
                "category": "machine-other",
                "content": "# Agent\n",
            }
        )

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "no destination family: .agents/agents"
        ):
            machinestage.build_payload(self.build_root(rows))

    def test_a_row_without_a_manifest_source_fails(self) -> None:
        rows = self.baseline_rows()
        rows[0]["manifest"] = False

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "no manifest source row"
        ):
            machinestage.build_payload(self.build_root(rows))

    def test_an_unreadable_source_fails(self) -> None:
        rows = self.baseline_rows()
        rows[0]["write"] = False

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "cannot read template source"
        ):
            machinestage.build_payload(self.build_root(rows))

    def test_a_non_utf8_source_fails(self) -> None:
        rows = self.baseline_rows()
        rows[0]["content"] = b"\xff\xfe not text\n"

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "template source is not UTF-8"
        ):
            machinestage.build_payload(self.build_root(rows))

    def test_family_of_reports_an_unmapped_target(self) -> None:
        self.assertIsNone(machinestage.family_of("elsewhere/thing.md"))
        self.assertEqual(
            machinestage.family_of("scripts/sd-ai-command-pack-probe.sh"),
            machinestage.BIN_FAMILY,
        )


class ArtifactReadingTests(StageFixtureCase):
    """Both inputs are untrusted files; each malformed shape has one message."""

    def test_a_missing_manifest_fails(self) -> None:
        root = self.build_root()
        (root / "manifest.json").unlink()

        with self.assertRaisesRegex(machinestage.MachineStageError, "manifest not found"):
            machinestage.build_payload(root)

    def test_invalid_manifest_json_fails(self) -> None:
        root = self.build_root()
        (root / "manifest.json").write_text("{broken", encoding="utf-8")

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "manifest is not valid JSON"
        ):
            machinestage.build_payload(root)

    def test_an_unreadable_manifest_fails(self) -> None:
        root = self.build_root()
        (root / "manifest.json").write_bytes(b"\xff\xfe{}\n")

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "manifest is unreadable"
        ):
            machinestage.build_payload(root)

    def test_a_manifest_that_is_not_an_object_fails(self) -> None:
        root = self.build_root()
        (root / "manifest.json").write_text("[]", encoding="utf-8")

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "manifest is not a JSON object"
        ):
            machinestage.build_payload(root)

    def test_a_manifest_without_files_fails(self) -> None:
        root = self.build_root()
        (root / "manifest.json").write_text('{"version": "9.9.9"}', encoding="utf-8")

        with self.assertRaisesRegex(machinestage.MachineStageError, "has no `files` list"):
            machinestage.build_payload(root)

    def test_a_manifest_row_that_is_not_an_object_fails(self) -> None:
        root = self.build_root()
        (root / "manifest.json").write_text(
            '{"version": "9.9.9", "files": ["row"]}', encoding="utf-8"
        )

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "holds a non-object entry"
        ):
            machinestage.build_payload(root)

    def test_a_manifest_row_without_a_source_is_ignored(self) -> None:
        """Rows the manifest declares but does not author cannot be staged."""

        root = self.build_root()
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"].append(
            {"platform": "shared", "kind": "doc", "source": "", "target": "docs/OTHER.md"}
        )
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        self.assertNotIn("docs/OTHER.md", machinestage.manifest_sources(root))

    def test_an_unusable_partition_fails(self) -> None:
        root = self.build_root()
        (root / machinestage.PARTITION_PATH).write_text('{"files": []}', encoding="utf-8")

        with self.assertRaisesRegex(
            machinestage.MachineStageError, "surface-partition.json is unusable"
        ):
            machinestage.build_payload(root)

    def test_the_partition_travels_into_the_payload_verbatim(self) -> None:
        root = self.build_root()

        staged = machinestage.build_payload(root)

        self.assertEqual(
            json.loads(staged[machinepayload.PARTITION_FILE].content),
            json.loads((root / machinestage.PARTITION_PATH).read_text(encoding="utf-8")),
        )


class RewriteIntegrationTests(StageFixtureCase):
    """The staged bytes are what a non-Claude platform will actually read."""

    def test_staged_text_points_at_the_machine_destinations(self) -> None:
        staged = machinestage.build_payload(self.build_root())

        body = staged[".agents/skills/sd-thing/SKILL.md"].content.decode("utf-8")

        self.assertIn("bash ~/.agents/bin/sd-ai-command-pack-probe.sh --json", body)
        self.assertIn("`~/.agents/docs/SD_AI_COMMAND_PACK.md`", body)
        self.assertNotIn("scripts/sd-ai-command-pack-probe.sh", body)

    def test_executables_travel_verbatim(self) -> None:
        staged = machinestage.build_payload(self.build_root())

        self.assertEqual(
            staged["scripts/sd-ai-command-pack-probe.sh"].content,
            SCRIPT_BODY.encode("utf-8"),
        )

    def test_an_unshipped_reference_fails_the_build(self) -> None:
        rows = self.baseline_rows()
        rows[0]["content"] = "Run sd-ai-command-pack-absent.py to finish.\n"

        with self.assertRaisesRegex(
            references.ReferenceRewriteError, "which the machine payload does not"
        ):
            machinestage.build_payload(self.build_root(rows))

    def test_a_manual_reference_without_the_manual_fails(self) -> None:
        rows = [row for row in self.baseline_rows() if "docs/" not in str(row["target"])]

        with self.assertRaisesRegex(
            references.ReferenceRewriteError, "which the payload does not install"
        ):
            machinestage.build_payload(self.build_root(rows))

    def test_an_unjustified_executable_literal_fails(self) -> None:
        rows = self.baseline_rows()
        rows[2]["content"] = (
            "#!/usr/bin/env bash\n# runs scripts/sd-ai-command-pack-other.sh\n"
        )

        with self.assertRaisesRegex(
            references.ReferenceRewriteError,
            "repository-root pack paths in scripts/sd-ai-command-pack-probe.sh",
        ):
            machinestage.build_payload(self.build_root(rows))


class MaterializeTests(StageFixtureCase):
    """Staging on disk, including the modes the destination families imply."""

    def test_materialize_writes_contents_and_modes(self) -> None:
        staged = machinestage.build_payload(self.build_root())
        destination = Path(tempfile.mkdtemp(prefix="sd-machine-out-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(destination, ignore_errors=True))

        machinestage.materialize(staged, destination)

        script = destination / "scripts/sd-ai-command-pack-probe.sh"
        skill = destination / ".agents/skills/sd-thing/SKILL.md"
        self.assertTrue(script.stat().st_mode & stat.S_IXUSR)
        self.assertFalse(skill.stat().st_mode & stat.S_IXUSR)
        self.assertEqual(script.read_text(encoding="utf-8"), SCRIPT_BODY)

    def test_staged_payload_cleans_up_its_directory(self) -> None:
        with machinestage.staged_payload(self.build_root()) as payload_root:
            self.assertTrue((payload_root / machinepayload.PARTITION_FILE).is_file())
            recorded = payload_root

        self.assertFalse(recorded.exists())

    def test_a_staged_payload_loads_in_the_engine(self) -> None:
        with machinestage.staged_payload(self.build_root()) as payload_root:
            payload = machinescope.load_payload(payload_root)

        self.assertEqual(payload.pack_version, "9.9.9")
        self.assertEqual(len(payload.entries), 5)


class PackCheckoutStagingTests(unittest.TestCase):
    """The gates only bind if they run against what the pack really ships."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.staged = machinestage.build_payload(PACK_ROOT)

    def test_the_real_checkout_stages_every_admitted_row(self) -> None:
        partition = json.loads(
            (PACK_ROOT / machinestage.PARTITION_PATH).read_text(encoding="utf-8")
        )
        admitted = {
            row["target"]
            for row in partition["files"]
            if row["category"] == machinepayload.MACHINE_OTHER
            or row.get("sharedRuntime")
        }

        self.assertEqual(set(self.staged) - {machinepayload.PARTITION_FILE}, admitted)

    def test_no_staged_text_still_names_a_repository_root_resource(self) -> None:
        offenders: dict[str, list[str]] = {}
        for target, entry in sorted(self.staged.items()):
            if machinestage.family_of(target) in (machinestage.BIN_FAMILY, None):
                continue
            body = entry.content.decode("utf-8")
            exempt = references.exempt_names(references.MACHINE_PROFILE, target)
            found = sorted(
                {
                    match.rstrip(".")
                    for match in references.RESIDUE_RE.findall(body)
                    if match.rstrip(".").removeprefix("scripts/") not in exempt
                }
            )
            if found:
                offenders[target] = found

        self.assertEqual(offenders, {})

    def test_the_manual_reference_relocates_to_the_machine_docs_root(self) -> None:
        """No staged file names the manual today, but the rewrite still binds.

        Losing the rule silently would ship a repository-root path that never
        exists on a machine-scope install, so assert it directly rather than
        through whichever surface happens to cite the manual this release.
        """

        rewritten = references.rewrite_text(
            "See `docs/SD_AI_COMMAND_PACK.md` for the contract.\n",
            profile=references.MACHINE_PROFILE,
            key=".agents/skills/sd-check/SKILL.md",
        )

        self.assertIn(f"`{references.AGENTS_DOC_REFERENCE}`", rewritten)
        self.assertNotIn("`docs/SD_AI_COMMAND_PACK.md`", rewritten)

    def test_the_source_only_fleet_references_keep_their_repository_path(self) -> None:
        """Rewriting them would assert a machine location that never exists."""

        manual = self.staged["docs/SD_AI_COMMAND_PACK.md"].content.decode("utf-8")

        self.assertIn("`scripts/sd-ai-command-pack-fleet-controller.py`", manual)
        self.assertIn("bash ~/.agents/bin/sd-ai-command-pack-toolchain.sh", manual)

    def test_every_reference_exemption_still_occurs_in_its_file(self) -> None:
        stale: dict[str, list[str]] = {}
        for target, (_justification, names) in (
            references.MACHINE_REFERENCE_EXEMPTIONS.items()
        ):
            self.assertIn(target, self.staged)
            body = self.staged[target].content.decode("utf-8")
            unused = sorted(name for name in names if name not in body)
            if unused:
                stale[target] = unused

        self.assertEqual(
            stale,
            {},
            "remove resolved names from MACHINE_REFERENCE_EXEMPTIONS: "
            f"{stale}",
        )

    def test_every_closure_allowlist_reference_still_occurs(self) -> None:
        stale: list[str] = []
        for (target, command) in references.MACHINE_CLOSURE_ALLOWLIST:
            self.assertIn(target, self.staged)
            if command not in self.staged[target].content.decode("utf-8"):
                stale.append(f"{target}: {command}")

        self.assertEqual(stale, [])


class MachineFlagTests(InstallTestCase):
    """`--machine` has no repository target, so nothing may imply one."""

    def parse_error(self, argv: list[str]) -> str:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                install.parse_args(argv)
        self.assertEqual(raised.exception.code, 2)
        return stderr.getvalue()

    def test_repository_options_are_refused(self) -> None:
        cases = [
            (["--machine", "/tmp/repo"], "a repository target"),
            (["--machine", "--platform", "gemini"], "--platform"),
            (["--machine", "--all"], "--all"),
            (["--machine", "--status"], "--status"),
            (["--machine", "--check"], "--check"),
            (["--machine", "--remove"], "--remove"),
            (["--machine", "--backup"], "--backup"),
            (["--machine", "--local-only"], "--local-only"),
            (["--machine", "--skip-diff-check"], "--skip-diff-check"),
            (["--machine", "--configure-fleet"], "--configure-fleet"),
        ]
        for argv, expected in cases:
            with self.subTest(argv=argv):
                self.assertIn(expected, self.parse_error(argv))

    def test_audit_and_trellis_init_flags_are_refused(self) -> None:
        self.assertIn("--audit", self.parse_error(["--machine", "--status", "--audit"]))
        self.assertIn(
            "--skip-trellis-init",
            self.parse_error(["--machine", "--local-only", "--skip-trellis-init"]),
        )

    def test_home_overrides_require_machine_scope(self) -> None:
        for argv in (["--home", "/tmp/home"], ["--state-home", "/tmp/state"]):
            with self.subTest(argv=argv):
                self.assertIn("require --machine", self.parse_error(argv))

    def test_json_is_accepted_with_machine_scope(self) -> None:
        args = install.parse_args(["--machine", "--json"])

        self.assertTrue(args.machine)
        self.assertTrue(args.json)
        self.assertIsNone(args.target)

    def test_json_still_requires_an_inspection_mode_otherwise(self) -> None:
        self.assertIn("--json requires", self.parse_error(["--json"]))

    def test_a_repository_install_still_defaults_to_the_current_directory(self) -> None:
        self.assertIsNone(install.parse_args([]).target)


class MachineInstallEntryTests(InstallTestCase):
    """`install.py --machine` end to end, contained in a scratch prefix."""

    def setUp(self) -> None:
        super().setUp()
        self.base = Path(tempfile.mkdtemp(prefix="sd-machine-entry-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.base, ignore_errors=True))
        self.home = self.base / "home"
        self.state_home = self.base / "state"

    def run_machine(self, *extra: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = install.main(
                [
                    "--machine",
                    "--home",
                    str(self.home),
                    "--state-home",
                    str(self.state_home),
                    *extra,
                ]
            )
        return code, stdout.getvalue()

    def receipt(self) -> dict[str, object]:
        path = self.state_home / machinescope.MACHINE_STATE_DIR / machinescope.RECEIPT_FILE
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        return loaded

    def test_dry_run_writes_nothing(self) -> None:
        code, output = self.run_machine("--dry-run")

        self.assertEqual(code, 0, output)
        self.assertIn("would install", output)
        self.assertFalse(self.home.exists())
        self.assertFalse(self.state_home.exists())

    def test_install_lands_in_the_family_roots_and_records_a_receipt(self) -> None:
        code, output = self.run_machine()

        self.assertEqual(code, 0, output)
        skills = self.home / ".agents/skills"
        self.assertTrue((skills / "sd-check/SKILL.md").is_file())
        toolchain = self.home / ".agents/bin/sd-ai-command-pack-toolchain.sh"
        self.assertTrue(toolchain.stat().st_mode & stat.S_IXUSR)
        self.assertTrue(
            (self.home / ".agents/docs/SD_AI_COMMAND_PACK.md").is_file()
        )
        self.assertTrue((self.home / ".gemini/commands/sd/help.toml").is_file())

        receipt = self.receipt()
        manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["packVersion"], manifest["version"])
        staged = machinestage.build_payload(PACK_ROOT)
        self.assertEqual(len(receipt["files"]), len(staged) - 1)

    def test_the_opencode_root_stays_inside_the_scratch_prefix(self) -> None:
        """The XDG family is the one that does not hang off the home directory."""

        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.base / "real")}):
            code, output = self.run_machine()

        self.assertEqual(code, 0, output)
        self.assertTrue(
            (self.home / ".config/opencode/commands/sd-help.md").is_file()
        )
        self.assertFalse((self.base / "real").exists())

    def test_an_xdg_root_inside_the_prefix_is_honored(self) -> None:
        inside = self.home / "xdg"
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(inside)}):
            code, output = self.run_machine()

        self.assertEqual(code, 0, output)
        self.assertTrue((inside / "opencode/commands/sd-help.md").is_file())

    def test_a_rerun_is_a_no_op(self) -> None:
        self.run_machine()
        first = self.receipt()

        code, output = self.run_machine("--json")

        self.assertEqual(code, 0, output)
        report = json.loads(output)
        self.assertFalse(report["changed"])
        self.assertEqual(report["counts"], {"owned-current": len(first["files"])})
        self.assertEqual(self.receipt()["payloadDigest"], first["payloadDigest"])

    def test_an_unowned_collision_refuses_with_the_conflict_code(self) -> None:
        collision = self.home / ".agents/skills/sd-check/SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code, _output = self.run_machine()

        self.assertEqual(code, machinescope.EXIT_CONFLICT)
        self.assertIn(str(collision), stderr.getvalue())
        self.assertEqual(collision.read_text(encoding="utf-8"), "mine\n")

    def test_force_overwrites_the_collision_and_records_a_backup(self) -> None:
        collision = self.home / ".agents/skills/sd-check/SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("mine\n", encoding="utf-8")

        code, output = self.run_machine("--force")

        self.assertEqual(code, 0, output)
        backups = [
            entry for entry in self.receipt()["files"] if isinstance(entry, dict) and entry.get("backup")
        ]
        self.assertEqual(len(backups), 1)
        self.assertEqual(
            (collision.parent / "SKILL.md.bak").read_text(encoding="utf-8"), "mine\n"
        )

    def test_a_staging_failure_is_reported_without_a_traceback(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            install.machinestage,
            "build_payload",
            side_effect=machinestage.MachineStageError("no rows"),
        ):
            with contextlib.redirect_stderr(stderr):
                code, _output = self.run_machine()

        self.assertEqual(code, 1)
        self.assertIn("error: no rows", stderr.getvalue())

    def test_a_gate_failure_is_reported_without_a_traceback(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(
            install.machinestage,
            "build_payload",
            side_effect=references.ReferenceRewriteError("rewrite residue in x"),
        ):
            with contextlib.redirect_stderr(stderr):
                code, _output = self.run_machine()

        self.assertEqual(code, 1)
        self.assertIn("rewrite residue in x", stderr.getvalue())

    def test_the_engine_argv_mirrors_the_installer_flags(self) -> None:
        """Without a home override the engine gets none, and installs for real."""

        seen: list[list[str]] = []

        @contextlib.contextmanager
        def fake_payload(root: Path) -> object:
            yield Path("/payload")

        cases = [
            (["--machine"], []),
            (
                ["--machine", "--force", "--dry-run", "--json"],
                ["--force", "--dry-run", "--json"],
            ),
            (
                ["--machine", "--home", "/scratch", "--state-home", "/state"],
                ["--home", "/scratch", "--state-home", "/state"],
            ),
        ]
        for argv, expected in cases:
            with self.subTest(argv=argv):
                seen.clear()
                with (
                    mock.patch.object(
                        install.machinestage, "staged_payload", fake_payload
                    ),
                    mock.patch.object(
                        install.machinescope,
                        "main",
                        side_effect=lambda passed: (seen.append(list(passed)), 0)[1],
                    ),
                ):
                    code = install.main(argv)

                self.assertEqual(code, 0)
                self.assertEqual(
                    seen[0], ["install", *expected, "--payload", "/payload"]
                )

    def test_the_installer_entry_point_runs_machine_scope(self) -> None:
        """The documented invocation, through the real entry point."""

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "install.py"),
                "--machine",
                "--dry-run",
                "--home",
                str(self.home),
                "--state-home",
                str(self.state_home),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would install", result.stdout)


class CliEnvironTests(unittest.TestCase):
    """`--home` scopes the XDG-derived family too, or a scratch prefix leaks."""

    def test_no_home_override_uses_the_real_environment(self) -> None:
        self.assertIs(machinescope.cli_environ(None), os.environ)

    def test_an_absent_xdg_root_is_left_alone(self) -> None:
        environ = {"PATH": "/bin"}

        self.assertIs(machinescope.cli_environ(Path("/scratch"), environ), environ)

    def test_an_outside_xdg_root_is_dropped(self) -> None:
        scoped = machinescope.cli_environ(
            Path("/scratch/home"), {"XDG_CONFIG_HOME": "/real/config"}
        )

        self.assertNotIn("XDG_CONFIG_HOME", scoped)

    def test_an_inside_xdg_root_is_kept(self) -> None:
        scoped = machinescope.cli_environ(
            Path("/scratch/home"), {"XDG_CONFIG_HOME": "/scratch/home/.config"}
        )

        self.assertEqual(scoped["XDG_CONFIG_HOME"], "/scratch/home/.config")

    def test_an_outside_state_root_is_dropped(self) -> None:
        """A receipt beside the real home would claim the scratch prefix's files."""

        for name in ("XDG_STATE_HOME", "SD_AI_COMMAND_PACK_STATE_HOME", "LOCALAPPDATA"):
            with self.subTest(variable=name):
                scoped = machinescope.cli_environ(
                    Path("/scratch/home"), {name: "/real/state"}
                )

                self.assertNotIn(name, scoped)

    def test_an_inside_state_root_is_kept(self) -> None:
        scoped = machinescope.cli_environ(
            Path("/scratch/home"), {"XDG_STATE_HOME": "/scratch/home/.local/state"}
        )

        self.assertEqual(scoped["XDG_STATE_HOME"], "/scratch/home/.local/state")

    def test_the_receipt_follows_the_named_home(self) -> None:
        """The whole ladder is scoped, so a scratch install stays self-contained."""

        home = Path(tempfile.mkdtemp(prefix="sd-machine-scoped-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(home, ignore_errors=True))
        elsewhere = Path(tempfile.mkdtemp(prefix="sd-machine-real-state-"))
        self.addCleanup(
            lambda: __import__("shutil").rmtree(elsewhere, ignore_errors=True)
        )

        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(elsewhere)}):
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = install.main(["--machine", "--home", str(home)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(list(elsewhere.iterdir()), [])
        self.assertTrue(
            (
                home
                / ".local/state/sd-ai-command-pack"
                / machinescope.MACHINE_STATE_DIR
                / machinescope.RECEIPT_FILE
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
