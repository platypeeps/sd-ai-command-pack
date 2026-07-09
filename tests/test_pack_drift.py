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
        # Every tracked installed twin must match its manifest source so this
        # repo's own footprint can never drift from the shipped templates.
        # (The managed copilot block has its own dedicated full-file test.)
        _, files = install.load_manifest()
        compared = 0
        drifted: list[str] = []
        for file in files:
            if file.kind == install.MANAGED_BLOCK_KIND:
                continue
            installed = install.ROOT / file.target
            if not installed.exists():
                continue
            compared += 1
            if installed.read_bytes() != file.source.read_bytes():
                drifted.append(file.target.as_posix())
        self.assertGreaterEqual(compared, 50)
        self.assertEqual(drifted, [])

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

        result = self.run_pack_source_drift_gates(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "release version gate: shipped payload changed; manifest version",
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
        (stub_bin / "python3").symlink_to(Path(sys.executable))

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
