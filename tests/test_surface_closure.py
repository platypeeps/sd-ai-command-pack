from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from installer import registry

PACK_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PACK_ROOT / "scripts/sd-ai-command-pack-surface-check.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("surface_closure_check", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SurfaceClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load_checker()

    def run_git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def init_repo(self, root: Path) -> None:
        self.run_git(root, "init", "-b", "main")
        self.run_git(root, "config", "user.name", "Surface Test")
        self.run_git(root, "config", "user.email", "surface@example.com")

    def manifest_registry(self):
        return SimpleNamespace(PLATFORM_REGISTRY={"fixture": SimpleNamespace()})

    def write_manifest(self, root: Path, files: object, *, schema: object = 1) -> None:
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "schemaVersion": schema,
                    "name": "sd-ai-command-pack",
                    "version": "1.0.0",
                    "files": files,
                }
            ),
            encoding="utf-8",
        )

    def test_live_surface_is_clean_and_json_is_versioned(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--json", "--base-ref", "HEAD"],
            cwd=PACK_ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["status"], "clean")
        self.assertEqual(payload["findingCount"], 0)
        self.assertGreater(payload["graph"]["nodeCount"], 500)

    def test_manifest_schema_rejects_unknown_wrong_types_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid = {
                "platform": "fixture",
                "kind": "script",
                "source": "templates/scripts/one.py",
                "target": "scripts/one.py",
                "install": "always",
            }
            self.write_manifest(root, [valid], schema=2)
            with self.assertRaisesRegex(
                self.checker.SurfaceInputError, "unsupported manifest schemaVersion"
            ):
                self.checker._manifest_entries(root, self.manifest_registry())

            self.write_manifest(root, [{**valid, "source": ["not", "text"]}])
            with self.assertRaisesRegex(
                self.checker.SurfaceInputError, "source must be non-empty"
            ):
                self.checker._manifest_entries(root, self.manifest_registry())

            duplicate = {**valid, "source": "templates/scripts/two.py"}
            self.write_manifest(root, [valid, duplicate])
            with self.assertRaisesRegex(
                self.checker.SurfaceInputError, "duplicate manifest target"
            ):
                self.checker._manifest_entries(root, self.manifest_registry())

    def test_manifest_rejects_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_manifest(
                root,
                [
                    {
                        "platform": "fixture",
                        "kind": "script",
                        "source": "templates/../outside.py",
                        "target": "scripts/one.py",
                    }
                ],
            )
            with self.assertRaisesRegex(self.checker.SurfaceInputError, "unsafe"):
                self.checker._manifest_entries(root, self.manifest_registry())

    def test_authoritative_files_reject_symlinks_and_oversize(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target"
            target.write_text("safe\n", encoding="utf-8")
            (root / "linked").symlink_to(target)
            with self.assertRaisesRegex(self.checker.SurfaceInputError, "non-symlink"):
                self.checker._regular_text(root, "linked", label="fixture")

            oversized = root / "oversized"
            oversized.write_bytes(b"x" * 9)
            with mock.patch.object(self.checker, "MAX_AUTHORITATIVE_BYTES", 8):
                with self.assertRaisesRegex(self.checker.SurfaceInputError, "exceeds 8"):
                    self.checker._regular_text(root, "oversized", label="fixture")

    def test_changed_paths_include_all_worktree_layers_nul_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.init_repo(root)
            (root / "baseline.txt").write_text("base\n", encoding="utf-8")
            (root / "staged.txt").write_text("old\n", encoding="utf-8")
            self.run_git(root, "add", ".")
            self.run_git(root, "commit", "-m", "baseline")
            (root / "baseline.txt").write_text("worktree\n", encoding="utf-8")
            (root / "staged.txt").write_text("staged\n", encoding="utf-8")
            (root / "space name.txt").write_text("untracked\n", encoding="utf-8")
            self.run_git(root, "add", "staged.txt")

            base, paths = self.checker.collect_changed_paths(root, "HEAD")

            self.assertEqual(base, "HEAD")
            self.assertEqual(
                set(paths), {"baseline.txt", "space name.txt", "staged.txt"}
            )

    def test_changed_paths_reject_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.init_repo(root)
            (root / "base").write_text("base\n", encoding="utf-8")
            self.run_git(root, "add", "base")
            self.run_git(root, "commit", "-m", "baseline")
            (root / "bad\nname").write_text("bad\n", encoding="utf-8")

            with self.assertRaisesRegex(self.checker.SurfaceInputError, "control-free"):
                self.checker.collect_changed_paths(root, "HEAD")

    def test_pr237_unregistered_source_only_reference_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.init_repo(root)
            source = root / "templates/scripts/tool.py"
            source.parent.mkdir(parents=True)
            source.write_text("print('tool')\n", encoding="utf-8")
            skill = root / "templates/.agents/skills/sd-fleet-refresh/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# Fleet\n", encoding="utf-8")
            missing = skill.parent / "references/controller-recovery.md"
            missing.parent.mkdir()
            missing.write_text("# Recovery\n", encoding="utf-8")
            self.write_manifest(
                root,
                [
                    {
                        "platform": "shared",
                        "kind": "script",
                        "source": "templates/scripts/tool.py",
                        "target": "scripts/tool.py",
                        "install": "always",
                    }
                ],
            )
            self.run_git(root, "add", ".")
            self.run_git(root, "commit", "-m", "fixture")
            command = SimpleNamespace(name="sd-fleet-refresh")
            fake_registry = SimpleNamespace(
                COMMAND_REGISTRY=(command,),
                SOURCE_ONLY_COMMAND_NAMES=frozenset({"sd-fleet-refresh"}),
                SOURCE_ONLY_SKILL_REFERENCES={},
                PLATFORM_REGISTRY={},
                RETIRED_COMMAND_SURFACES=(),
            )
            fake_linter = SimpleNamespace(
                _required_source_paths=lambda _command: (
                    "templates/.agents/skills/sd-fleet-refresh/SKILL.md",
                ),
                lint_repository=lambda _root: SimpleNamespace(findings=()),
            )
            with (
                mock.patch.object(self.checker, "_registry_module", return_value=fake_registry),
                mock.patch.object(self.checker, "_load_source_module", return_value=fake_linter),
                mock.patch.object(self.checker, "_caller_findings", return_value=[]),
                mock.patch.object(self.checker, "_generator_finding", return_value=None),
            ):
                report = self.checker._evaluate(root, "HEAD")

            findings = [
                item
                for item in report["findings"]
                if item["code"] == "source.unregistered-template"
            ]
            self.assertEqual(len(findings), 1)
            self.assertEqual(
                findings[0]["path"],
                "templates/.agents/skills/sd-fleet-refresh/references/controller-recovery.md",
            )
            self.assertIn("manifest entry", findings[0]["ownerCommand"])
            self.assertIn("SOURCE_ONLY_SKILL_REFERENCES", findings[0]["ownerCommand"])

    def test_source_only_reference_is_explicit_and_excluded_from_manifest(self) -> None:
        linter = SimpleNamespace(
            _required_source_paths=lambda _command: (
                "templates/.agents/skills/sd-fleet-refresh/SKILL.md",
            )
        )
        paths = self.checker._source_only_paths(registry, linter)

        self.assertIn(
            "templates/.agents/skills/sd-fleet-refresh/references/controller-recovery.md",
            paths,
        )
        manifest_sources = {
            item["source"] for item in json.loads((PACK_ROOT / "manifest.json").read_text())["files"]
        }
        self.assertTrue(paths.isdisjoint(manifest_sources))

    def test_source_only_reference_registry_rejects_invalid_shapes(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "unknown source-only skill"):
            registry.validate_source_only_skill_references(
                frozenset({"sd-fleet-refresh"}),
                {"sd-unknown": ("references/guide.md",)},
            )
        with self.assertRaisesRegex(RuntimeError, "duplicate source-only"):
            registry.validate_source_only_skill_references(
                frozenset({"sd-fleet-refresh"}),
                {
                    "sd-fleet-refresh": (
                        "references/guide.md",
                        "references/guide.md",
                    )
                },
            )
        with self.assertRaisesRegex(RuntimeError, "invalid source-only"):
            registry.validate_source_only_skill_references(
                frozenset({"sd-fleet-refresh"}),
                {"sd-fleet-refresh": ["references/guide.md"]},  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(RuntimeError, "unsafe source-only"):
            registry.validate_source_only_skill_references(
                frozenset({"sd-fleet-refresh"}),
                {"sd-fleet-refresh": ("../outside.md",)},
            )

    def test_graph_represents_every_required_node_kind_and_platform_target(self) -> None:
        linter = SimpleNamespace(
            _required_source_paths=lambda command: (
                f"templates/.agents/skills/{command.name}/SKILL.md",
            )
        )
        _text, entries = self.checker._manifest_entries(PACK_ROOT, registry)
        source_only = self.checker._source_only_paths(registry, linter)
        nodes, _edges = self.checker._graph(registry, entries, source_only)

        self.assertTrue(
            {
                "installable",
                "generated",
                "source-only",
                "documentation-only",
                "check-only",
                "retired",
                "provenance",
                "registry",
            }.issubset({node.kind for node in nodes.values()})
        )
        manifest_targets = {entry["target"] for entry in entries}
        for command in registry.COMMAND_REGISTRY:
            if command.name in registry.SOURCE_ONLY_COMMAND_NAMES:
                continue
            with self.subTest(command=command.name):
                self.assertTrue(
                    set(
                        registry.command_installed_targets(
                            command.name, command.short, command.target_families
                        )
                    ).issubset(manifest_targets)
                )

    def test_local_and_ci_registration_drift_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for relative in (
                self.checker.CHECK_CONFIG,
                self.checker.FULL_CHECK,
                self.checker.CI_WORKFLOW,
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((PACK_ROOT / relative).read_bytes())
            config_path = root / self.checker.CHECK_CONFIG
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["checks"] = []
            config_path.write_text(json.dumps(config), encoding="utf-8")

            findings = self.checker._caller_findings(root)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].path, self.checker.CHECK_CONFIG)
            self.assertEqual(findings[0].code, "checker.registration")

    def test_stale_generator_reports_owner_without_mutation(self) -> None:
        before = (PACK_ROOT / "manifest.json").read_bytes()
        completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="drifted generated surface\n"
        )
        with mock.patch.object(self.checker.subprocess, "run", return_value=completed):
            finding = self.checker._generator_finding(PACK_ROOT)

        self.assertIsNotNone(finding)
        self.assertEqual(finding.owner_command, "make generate")
        self.assertEqual((PACK_ROOT / "manifest.json").read_bytes(), before)

    def test_duplicate_logical_findings_collapse_before_rendering(self) -> None:
        finding = self.checker.Finding(
            "fixture.duplicate", "path", "relation", "message", "make generate"
        )
        self.assertEqual(len({finding, finding}), 1)


if __name__ == "__main__":
    unittest.main()
