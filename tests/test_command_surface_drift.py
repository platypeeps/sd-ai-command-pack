from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from installer import registry

PACK_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PACK_ROOT / ".github/scripts/check-command-surface-drift.py"


def load_linter():
    spec = importlib.util.spec_from_file_location("command_surface_lint", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CommandSurfaceDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.linter = load_linter()

    def make_repo(
        self, root: Path, *, target_families: tuple[str, ...] | None = None
    ) -> registry.CommandInfo:
        command = registry.CommandInfo(
            "sd-one",
            "one",
            "orientation-knowledge",
            target_families=(
                registry.GENERATED_COMMAND_TARGET_FAMILIES
                if target_families is None
                else target_families
            ),
        )
        sources = (
            ".github/command-sources/sd-one.md",
            "templates/.agents/skills/sd-one/SKILL.md",
            "templates/.commands/sd-one.md",
            "templates/.claude/commands/sd/one.md",
            "templates/.gemini/commands/sd/one.toml",
            "templates/.github/prompts/sd-one.prompt.md",
        )
        for relative in sources:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# sd-one\n", encoding="utf-8")
        entries = [
            {
                "platform": "fixture",
                "kind": "command",
                "source": "templates/.commands/sd-one.md",
                "target": target,
            }
            for target in registry.command_installed_targets("sd-one", "one")
        ]
        (root / "manifest.json").write_text(
            json.dumps(
                {"name": "fixture", "version": "1", "files": entries},
                indent=2,
            ),
            encoding="utf-8",
        )
        return command

    def lint(
        self,
        root: Path,
        command: registry.CommandInfo,
        *,
        retirements=(),
        allowances=(),
    ):
        return self.linter.lint_repository(
            root,
            commands=(command,),
            retirements=retirements,
            allowances=allowances,
            source_only=frozenset(),
        )

    def test_live_pack_surface_is_clean(self) -> None:
        report = self.linter.lint_repository(PACK_ROOT)
        self.assertEqual(report.findings, ())
        self.assertGreater(report.files_scanned, 100)
        self.assertGreater(report.suppressed, 0)

    def test_retired_identifier_in_live_spec_reports_exact_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            spec = root / ".trellis/spec/frontend/adapter-guidelines.md"
            spec.parent.mkdir(parents=True)
            spec.write_text("# Adapter\nUse sd-review-local-all here.\n", encoding="utf-8")
            retirement = registry.RetiredCommandSurface(
                id="old-review",
                identifiers=("sd-review-local-all",),
                installed_targets=registry.command_installed_targets(
                    "sd-review-local-all", "review-local-all"
                ),
                removed_version="1.0.0",
                owner_task="fixture",
            )

            report = self.lint(root, command, retirements=(retirement,))

            finding = next(
                item
                for item in report.findings
                if item.category == "retired_identifier_live"
            )
            self.assertEqual(finding.path, spec.relative_to(root).as_posix())
            self.assertEqual(finding.line, 2)
            self.assertEqual(finding.identifier, "sd-review-local-all")

    def test_reasoned_historical_allowance_suppresses_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            (root / "CHANGELOG.md").write_text(
                "Migrated from sd-old in 1.0.0.\n", encoding="utf-8"
            )
            retirement = registry.RetiredCommandSurface(
                id="old-command",
                identifiers=("sd-old",),
                installed_targets=(),
                removed_version="1.0.0",
                owner_task="fixture",
            )
            allowance = registry.CommandSurfaceAllowance(
                identifier="sd-old",
                path_pattern="CHANGELOG.md",
                reason="bounded migration history",
            )

            report = self.lint(
                root,
                command,
                retirements=(retirement,),
                allowances=(allowance,),
            )

            self.assertEqual(report.findings, ())
            self.assertEqual(report.suppressed, 1)

    def test_missing_and_unregistered_targets_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            (root / "templates/.agents/skills/sd-one/SKILL.md").unlink()
            extra = root / ".github/command-sources/sd-extra.md"
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text("# sd-extra\n", encoding="utf-8")

            report = self.lint(root, command)
            categories = {finding.category for finding in report.findings}

            self.assertIn("live_identifier_missing_target", categories)
            self.assertIn("unregistered_public_target", categories)

    def test_unregistered_skill_reference_is_a_public_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            reference = root / ".agents/skills/sd-extra/references/guide.md"
            reference.parent.mkdir(parents=True)
            reference.write_text("# Extra guide\n", encoding="utf-8")

            report = self.lint(root, command)

            finding = next(
                item
                for item in report.findings
                if item.path == reference.relative_to(root).as_posix()
            )
            self.assertEqual(finding.category, "unregistered_public_target")
            self.assertEqual(finding.identifier, "sd-extra")

    def test_registry_command_adapters_are_public_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            adapter_paths = {
                registry.PLATFORM_REGISTRY[platform]
                .command_target_pattern.format(
                    filename="sd-extra.md",
                    name="extra",
                )
                for platform in registry.NEUTRAL_COMMAND_SOURCE_PLATFORMS
            }
            for relative in adapter_paths:
                adapter = root / relative
                adapter.parent.mkdir(parents=True, exist_ok=True)
                adapter.write_text("# sd-extra\n", encoding="utf-8")

            report = self.lint(root, command)

            findings = {
                finding.path
                for finding in report.findings
                if finding.identifier == "sd-extra"
                and finding.category == "unregistered_public_target"
            }
            self.assertEqual(findings, adapter_paths)

    def test_unregistered_manifest_entries_use_unique_target_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            targets = (
                ".cursor/commands/sd-extra.md",
                ".opencode/commands/sd-extra.md",
            )
            manifest["files"].extend(
                {
                    "platform": "fixture",
                    "kind": "command",
                    "source": "templates/.commands/sd-extra.md",
                    "target": target,
                }
                for target in targets
            )
            manifest_text = json.dumps(manifest, indent=2)
            manifest_path.write_text(manifest_text, encoding="utf-8")

            report = self.lint(root, command)

            findings = [
                finding
                for finding in report.findings
                if finding.path == "manifest.json"
                and finding.identifier == "sd-extra"
            ]
            self.assertEqual(
                [finding.line for finding in findings],
                sorted(
                    self.linter._line_for_literal(manifest_text, target)
                    for target in targets
                ),
            )

    def test_stale_help_and_retired_manifest_target_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            catalog = root / "templates/.agents/skills/sd-help/references/catalog.md"
            catalog.parent.mkdir(parents=True)
            catalog.write_text("Use sd-old after setup.\n", encoding="utf-8")
            retirement = registry.RetiredCommandSurface(
                id="old-command",
                identifiers=("sd-old",),
                installed_targets=(".agents/skills/sd-old/SKILL.md",),
                removed_version="1.0.0",
                owner_task="fixture",
            )
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["files"].append(
                {
                    "platform": "shared",
                    "kind": "skill",
                    "source": "templates/.agents/skills/sd-old/SKILL.md",
                    "target": ".agents/skills/sd-old/SKILL.md",
                }
            )
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            report = self.lint(root, command, retirements=(retirement,))

            self.assertTrue(
                any(
                    finding.category == "retired_identifier_live"
                    and finding.path == catalog.relative_to(root).as_posix()
                    for finding in report.findings
                )
            )
            self.assertTrue(
                any(
                    finding.category == "retired_identifier_live"
                    and finding.path == "manifest.json"
                    for finding in report.findings
                )
            )
            manifest_findings = [
                finding
                for finding in report.findings
                if finding.path == "manifest.json"
                and finding.identifier in {"old-command", "sd-old"}
            ]
            self.assertEqual(len(manifest_findings), 1)
            self.assertEqual(
                manifest_findings[0].category, "retired_identifier_live"
            )

    def test_missing_target_family_and_stale_config_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root, target_families=())
            docs = root / "docs/guide.md"
            docs.parent.mkdir(parents=True)
            docs.write_text("Set SD_OLD_REVIEW_KEY.\n", encoding="utf-8")
            retirement = registry.RetiredCommandSurface(
                id="old-config",
                identifiers=(),
                configuration_keys=("SD_OLD_REVIEW_KEY",),
                installed_targets=(),
                removed_version="1.0.0",
                owner_task="fixture",
            )

            report = self.lint(root, command, retirements=(retirement,))
            categories = {finding.category for finding in report.findings}

            self.assertIn("generated_registry_mismatch", categories)
            self.assertIn("stale_configuration_key", categories)

    def test_stale_allowance_and_json_output_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            command = self.make_repo(root)
            retirement = registry.RetiredCommandSurface(
                id="old-command",
                identifiers=("sd-old",),
                installed_targets=(),
                removed_version="1.0.0",
                owner_task="fixture",
            )
            allowance = registry.CommandSurfaceAllowance(
                identifier="sd-old",
                path_pattern="README.md",
                reason="stale migration allowance",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                report = self.linter.lint_repository(
                    root,
                    commands=(command,),
                    retirements=(retirement,),
                    allowances=(allowance,),
                    source_only=frozenset(),
                )
                print(json.dumps(report.as_json()))

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["findingCounts"], {"invalid_allowance": 1})


if __name__ == "__main__":
    unittest.main()
