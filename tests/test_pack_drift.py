from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

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
            ["git", "ls-files", "templates"],
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

        self.assertEqual(tracked_template_sources, manifest_sources)

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

    def test_pack_source_drift_gate_rejects_undocumented_skill_env_vars(
        self,
    ) -> None:
        root = self.make_pack_source_fixture()
        skill = root / "templates/.agents/skills/sd-review-pr/SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + "\nFixture: ${SD_AI_COMMAND_PACK_UNDOCUMENTED_SKILL_ONLY}\n",
            encoding="utf-8",
        )

        result = self.run_pack_source_drift_gates(root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "undocumented env var: SD_AI_COMMAND_PACK_UNDOCUMENTED_SKILL_ONLY",
            result.stdout,
        )
        self.assertIn("shipped scripts or skills", result.stdout)

    def test_pack_source_drift_gate_rejects_payload_without_version_bump(
        self,
    ) -> None:
        root = self.make_pack_source_fixture()
        for relative in (
            "templates/scripts/sd-ai-command-pack-housekeeping.sh",
            "scripts/sd-ai-command-pack-housekeeping.sh",
        ):
            path = root / relative
            path.write_text(
                path.read_text(encoding="utf-8") + "\n# release gate fixture\n",
                encoding="utf-8",
            )

        result = self.run_pack_source_drift_gates(root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("release version drift", result.stdout)
        self.assertIn(
            "shipped payload changed without manifest version bump",
            result.stdout,
        )

    def test_shipped_script_coverage_gate_lists_every_python_helper(self) -> None:
        gate = install.ROOT / ".github/scripts/check-shipped-script-coverage.sh"
        gate_text = gate.read_text(encoding="utf-8")
        configured = {
            script: int(floor)
            for script, floor in re.findall(
                r"^(scripts/sd-ai-command-pack-[^\s]+\.py)\s+([0-9]+)$",
                gate_text,
                flags=re.MULTILINE,
            )
        }
        helpers = {
            path.relative_to(install.ROOT).as_posix()
            for path in (install.ROOT / "scripts").glob("sd-ai-command-pack-*.py")
        }

        self.assertEqual(set(configured), helpers)
        self.assertTrue(all(1 <= floor <= 100 for floor in configured.values()))
        self.assertIn('--include="scripts/sd-ai-command-pack-*.py"', gate_text)
        self.assertIn("--fail-under=76", gate_text)

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

    def test_pack_source_drift_gate_accepts_payload_with_version_bump(
        self,
    ) -> None:
        root = self.make_pack_source_fixture()
        for relative in (
            "templates/scripts/sd-ai-command-pack-housekeeping.sh",
            "scripts/sd-ai-command-pack-housekeeping.sh",
        ):
            path = root / relative
            path.write_text(
                path.read_text(encoding="utf-8") + "\n# release gate fixture\n",
                encoding="utf-8",
            )
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "99.0.0"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        changelog_path = root / "CHANGELOG.md"
        changelog_path.write_text(
            changelog_path.read_text(encoding="utf-8").replace(
                "# Changelog\n",
                "# Changelog\n\n## 99.0.0 - 2099-01-01\n\n"
                "- Release gate fixture.\n",
                1,
            ),
            encoding="utf-8",
        )

        result = self.run_pack_source_drift_gates(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "release version gate: shipped payload changed; manifest version",
            result.stdout,
        )
        self.assertIn(
            "release changelog gate: manifest version bump has matching top heading",
            result.stdout,
        )

    def test_pack_source_drift_gate_rejects_version_bump_without_top_changelog_heading(
        self,
    ) -> None:
        root = self.make_pack_source_fixture()
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "99.0.0"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        changelog_path = root / "CHANGELOG.md"
        changelog_path.write_text(
            changelog_path.read_text(encoding="utf-8")
            + "\n## 99.0.0 - 2099-01-01\n\n- Too late in the ledger.\n",
            encoding="utf-8",
        )

        result = self.run_pack_source_drift_gates(root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("release changelog drift", result.stdout)
        self.assertIn(
            "requires the top CHANGELOG.md release heading "
            "'## 99.0.0 - YYYY-MM-DD'",
            result.stdout,
        )

    def test_pack_source_drift_gate_rejects_unresolved_release_base_ref(
        self,
    ) -> None:
        root = self.make_pack_source_fixture()
        path = root / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# release gate fixture\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "payload without release bump")

        result = self.run_pack_source_drift_gates(
            root,
            extra_env={"SD_AI_COMMAND_PACK_FULL_CHECK_RELEASE_BASE_REF": "missing-ref"},
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("release version gate cannot compare", result.stdout)
        self.assertIn("base ref 'missing-ref' does not resolve", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_pack_source_drift_gate_reports_missing_git_without_traceback(
        self,
    ) -> None:
        root = self.make_pack_source_fixture()
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-pack-source-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        try:
            (stub_bin / "python3").symlink_to(Path(sys.executable))
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = self.run_pack_source_drift_gates(
            root,
            extra_env={"SD_AI_COMMAND_PACK_FULL_CHECK_TEST_RUNTIME_PATH": str(stub_bin)},
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("git executable unavailable", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

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
