from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

from installer import registry

contextlib = _support.contextlib
hashlib = _support.hashlib
importlib = _support.importlib
io = _support.io
json = _support.json
os = _support.os
re = _support.re
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
yaml = _support.yaml
install = _support.install
PACK_ROOT = _support.PACK_ROOT
INSTALLER = _support.INSTALLER
SECRET_MARKER_PATTERNS = _support.SECRET_MARKER_PATTERNS
InstallTestCase = _support.InstallTestCase


def dogfood_manifest_files(
    files: list[install.PackFile],
    root: Path = install.ROOT,
) -> list[install.PackFile]:
    dogfood_platforms = {
        platform
        for platform, info in install.PLATFORM_REGISTRY.items()
        if (root / info.directory).is_dir()
    }
    return [
        file
        for file in files
        if file.kind != install.MANAGED_BLOCK_KIND
        and (file.platform == "shared" or file.platform in dogfood_platforms)
    ]


def missing_dogfood_targets(
    files: list[install.PackFile],
    root: Path = install.ROOT,
) -> list[str]:
    return [
        file.target.as_posix()
        for file in files
        if (root / file.target).is_symlink() or not (root / file.target).is_file()
    ]


class PackDriftTests(InstallTestCase):
    """Tests for source/template drift gates, shipped env vars, and release guards."""

    def make_installer_pack_fixture(self, manifest_text: str) -> Path:
        root = self.make_git_repo_without_trellis()
        (root / "templates").mkdir()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            scripts_dir / "sd-ai-command-pack-full-check.sh",
        )
        shutil.copy2(
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
            scripts_dir / "sd-ai-command-pack-shell-lib.sh",
        )
        (root / "install.py").write_text("# installer marker\n", encoding="utf-8")
        (root / "manifest.json").write_text(manifest_text, encoding="utf-8")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        return root

    def test_shipped_shell_cleanup_is_option_safe(self) -> None:
        unsafe_cleanup = re.compile(r'\brm\s+-f\s+"\$')
        violations: list[str] = []

        for script_path in sorted((install.ROOT / "templates/scripts").glob("*.sh")):
            for line_number, line in enumerate(
                script_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if unsafe_cleanup.search(line):
                    violations.append(
                        f"{script_path.relative_to(install.ROOT)}:{line_number}: {line.strip()}"
                    )

        self.assertEqual(violations, [])

    def test_shared_script_templates_are_syntax_valid(self) -> None:
        script_files = self.shared_manifest_files("script")

        self.assertGreater(len(script_files), 0)
        for file in script_files:
            if file.source.suffix == ".sh":
                self.assert_shell_syntax_valid(file.source)
            elif file.source.suffix == ".py":
                self.assert_python_syntax_valid(file.source)
            elif file.source.suffix == ".mjs":
                self.assert_node_syntax_valid(file.source)
            else:
                self.fail(f"unexpected script template suffix: {file.source}")
            self.assert_no_secret_markers(file.source)

    def test_tracked_pack_targets_match_templates(self) -> None:
        # Every dogfood installed twin must exist and match its manifest source
        # so this repo's own footprint can never drift from the shipped
        # templates.
        # (The managed copilot block has its own dedicated full-file test.)
        _, files = install.load_manifest()
        required_files = dogfood_manifest_files(files)
        compared = 0
        missing = missing_dogfood_targets(required_files)
        drifted: list[str] = []
        for file in required_files:
            installed = install.ROOT / file.target
            if not installed.is_file():
                continue
            compared += 1
            if installed.read_bytes() != file.source.read_bytes():
                drifted.append(file.target.as_posix())

        self.assertEqual(missing, [])
        self.assertGreaterEqual(compared, len(required_files))
        self.assertEqual(drifted, [])

    def test_source_only_dev_adapters_match_templates(self) -> None:
        # Source-only commands have no consumer manifest entries, so the
        # manifest-driven twin gate above is structurally blind to them; the
        # registry helper enumerates their dev-tree footprint instead.
        compared = 0
        missing: list[str] = []
        drifted: list[str] = []
        for command in registry.COMMAND_REGISTRY:
            if command.name not in registry.SOURCE_ONLY_COMMAND_NAMES:
                continue
            for source, target in registry.source_only_adapter_twins(
                command.name,
                command.short,
                command.target_families,
                root=install.ROOT,
            ):
                installed = install.ROOT / target
                if not installed.is_file():
                    missing.append(target)
                    continue
                compared += 1
                if installed.read_bytes() != (install.ROOT / source).read_bytes():
                    drifted.append(target)

        self.assertEqual(missing, [])
        self.assertEqual(drifted, [])
        self.assertGreaterEqual(compared, 4)

    def test_dogfood_drift_gate_detects_missing_existing_platform_targets(
        self,
    ) -> None:
        root = self.make_repo()
        (root / ".opencode").mkdir()
        pack_file = install.PackFile(
            platform="opencode",
            kind="command",
            source=install.ROOT / "templates/.commands/sd-review-pr.md",
            target=Path(".opencode/commands/sd-review-pr.md"),
            anchor=Path(".opencode"),
            install="if-anchor-exists",
        )

        required = dogfood_manifest_files([pack_file], root)

        self.assertEqual(required, [pack_file])
        self.assertEqual(
            missing_dogfood_targets(required, root),
            [".opencode/commands/sd-review-pr.md"],
        )

    def test_dogfood_drift_gate_requires_platform_directory(self) -> None:
        root = self.make_repo()
        (root / ".opencode").write_text("not a directory\n", encoding="utf-8")
        pack_file = install.PackFile(
            platform="opencode",
            kind="command",
            source=install.ROOT / "templates/.commands/sd-review-pr.md",
            target=Path(".opencode/commands/sd-review-pr.md"),
            anchor=Path(".opencode"),
            install="if-anchor-exists",
        )

        self.assertEqual(dogfood_manifest_files([pack_file], root), [])

    def test_dogfood_drift_gate_rejects_symlink_targets(self) -> None:
        root = self.make_repo()
        target = root / ".opencode/commands/sd-review-pr.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(install.ROOT / "templates/.commands/sd-review-pr.md")
        pack_file = install.PackFile(
            platform="opencode",
            kind="command",
            source=install.ROOT / "templates/.commands/sd-review-pr.md",
            target=Path(".opencode/commands/sd-review-pr.md"),
            anchor=Path(".opencode"),
            install="if-anchor-exists",
        )

        self.assertEqual(
            missing_dogfood_targets([pack_file], root),
            [".opencode/commands/sd-review-pr.md"],
        )

    def test_tracked_template_sources_match_manifest_sources(self) -> None:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "templates",
            ],
            cwd=install.ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        tracked_template_sources = {
            (install.ROOT / line).resolve()
            for line in result.stdout.splitlines()
            if line
        }
        _, files = install.load_manifest()
        manifest_sources = {file.source.resolve() for file in files}
        source_only_template_sources = set()
        for name in install.SOURCE_ONLY_COMMAND_NAMES:
            short = name.removeprefix("sd-")
            source_only_template_sources.update(
                {
                    (
                        install.ROOT
                        / f"templates/.agents/skills/{name}/SKILL.md"
                    ).resolve(),
                    (install.ROOT / f"templates/.commands/{name}.md").resolve(),
                    (
                        install.ROOT
                        / f"templates/.claude/commands/sd/{short}.md"
                    ).resolve(),
                    (
                        install.ROOT
                        / f"templates/.gemini/commands/sd/{short}.toml"
                    ).resolve(),
                    (
                        install.ROOT
                        / f"templates/.github/prompts/{name}.prompt.md"
                    ).resolve(),
                }
            )
            source_only_template_sources.update(
                (
                    install.ROOT
                    / f"templates/.agents/skills/{name}/{reference}"
                ).resolve()
                for reference in install.SOURCE_ONLY_SKILL_REFERENCES.get(name, ())
            )

        self.assertEqual(
            tracked_template_sources,
            manifest_sources | source_only_template_sources,
        )

    def test_manifest_targets_are_casefold_unique(self) -> None:
        _, files = install.load_manifest()
        seen: dict[str, str] = {}
        collisions: list[str] = []
        for file in files:
            target = file.target.as_posix()
            key = target.casefold()
            if key in seen:
                collisions.append(f"{seen[key]} <-> {target}")
            else:
                seen[key] = target

        self.assertEqual(collisions, [])

    def test_shipped_env_vars_are_documented(self) -> None:
        var_re = re.compile(r"SD_AI_COMMAND_PACK_[A-Z0-9_]+")
        script_vars: set[str] = set()
        for path in (install.ROOT / "scripts").iterdir():
            if path.suffix in {".sh", ".py", ".mjs"}:
                script_vars |= set(var_re.findall(path.read_text(encoding="utf-8")))
        skill_vars: set[str] = set()
        for path in (install.ROOT / "templates/.agents/skills").glob("*/SKILL.md"):
            skill_vars |= set(var_re.findall(path.read_text(encoding="utf-8")))
        documented = set(
            var_re.findall(
                (install.ROOT / "docs/SD_AI_COMMAND_PACK.md").read_text(
                    encoding="utf-8"
                )
            )
        )

        undocumented = sorted(
            (script_vars | skill_vars) - documented - self.ENV_VAR_DOC_EXEMPT
        )
        self.assertEqual(
            undocumented,
            [],
            "env vars read by shipped scripts or skills but missing from the "
            "installed guide",
        )
        stale = sorted(documented - script_vars - skill_vars)
        self.assertEqual(
            stale,
            [],
            "env vars documented in the installed guide but consumed by no "
            "shipped script or skill",
        )

    def test_shipped_script_coverage_gate_lists_every_python_helper(self) -> None:
        gate = install.ROOT / ".github/scripts/check-shipped-script-coverage.sh"
        gate_text = gate.read_text(encoding="utf-8")
        matches = re.findall(
            r"^(scripts/(?:sd-ai-command-pack-[^\s]+|sd_ai_command_pack_(?:fleet_)?lib)\.py)\s+([0-9]+)$",
            gate_text,
            flags=re.MULTILINE,
        )
        configured: dict[str, int] = {}
        duplicates: list[str] = []
        for script, floor in matches:
            if script in configured:
                duplicates.append(script)
            configured[script] = int(floor)
        helpers = {
            path.relative_to(install.ROOT).as_posix()
            for path in (install.ROOT / "scripts").glob("sd-ai-command-pack-*.py")
        }
        helpers.add("scripts/sd_ai_command_pack_lib.py")
        helpers.add("scripts/sd_ai_command_pack_fleet_lib.py")

        self.assertEqual(duplicates, [])
        self.assertEqual(set(configured), helpers)
        self.assertTrue(all(1 <= floor <= 100 for floor in configured.values()))
        self.assertIn(
            '--include="scripts/sd-ai-command-pack-*.py,scripts/sd_ai_command_pack_lib.py,scripts/sd_ai_command_pack_fleet_lib.py"',
            gate_text,
        )
        self.assertIn("--fail-under=76", gate_text)
        self.assertIn(
            'REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"',
            gate_text,
        )
        self.assertIn('cd -- "$REPO_ROOT" || exit 1', gate_text)

    def test_shipped_script_coverage_gate_is_used_by_local_and_ci_runners(
        self,
    ) -> None:
        gate = ".github/scripts/check-shipped-script-coverage.sh"
        makefile = (install.ROOT / "Makefile").read_text(encoding="utf-8")
        workflow = (install.ROOT / ".github/workflows/tests.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(gate, makefile)
        self.assertIn(gate, workflow)

    def test_manifest_sources_do_not_have_trailing_whitespace(self) -> None:
        _, files = install.load_manifest()

        for file in files:
            for line_number, line in enumerate(
                file.source.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                self.assertFalse(
                    line.endswith((" ", "\t")),
                    f"{file.source}:{line_number} has trailing whitespace",
                )


if __name__ == "__main__":
    unittest.main()
