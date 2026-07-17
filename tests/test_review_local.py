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


class ReviewLocalTests(InstallTestCase):
    """Tests for local Prism/Gito review command behavior."""

    # Per-class cache of the template dir holding a git repo with the pack
    # installed. Set lazily on the concrete class and read via ``__dict__`` so a
    # subclass never reuses a parent's template (mirrors ``_housekeeping_template``).
    _installed_repo_template: Path | None

    def _build_installed_repo_template(self, root: Path) -> None:
        """Populate ``root`` as a git repo with the full pack installed.

        Mirrors ``make_repo()`` + ``run_install(root)`` but into a class-scoped
        template dir. ``run_install`` writes ~80 files via an installer
        subprocess; running it once per class instead of once per test is the
        dominant saving here (``make_repo`` alone is cheap).
        """
        (root / ".trellis").mkdir()
        (root / ".trellis" / "config.yaml").write_text("# test\n", encoding="utf-8")
        self.run_git(root, "init")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def make_installed_review_repo(self) -> Path:
        """Return an isolated copy of a repo with the pack already installed.

        The canonical installed repo is built once per test class into a
        template dir; each call ``copytree``-clones it. Every clone is a fully
        independent tree (its own working files and ``.git``), so tests that run
        review-local.sh -- writing outputs, creating commits or branches -- never
        observe each other's state. ``make_repo`` creates no remote, so unlike
        ``make_housekeeping_repo`` no remote repointing is needed.
        """
        cls = type(self)
        template_root = cls.__dict__.get("_installed_repo_template")
        if template_root is None:
            template_root = Path(
                tempfile.mkdtemp(prefix="sd-ai-command-pack-review-local-template-")
            )
            self._build_installed_repo_template(template_root)
            cls.addClassCleanup(shutil.rmtree, template_root, ignore_errors=True)
            cls._installed_repo_template = template_root

        tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-review-local-test-"
        )
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo"
        shutil.copytree(template_root, root)
        return root

    def _make_committed_review_repo(self) -> Path:
        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        return root

    def _make_review_stub_bin(self) -> tuple[Path, Path]:
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        return stub_bin, Path(tools_tempdir.name) / "tool.log"

    def test_review_local_script_runs_gito_after_prism_findings(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name, exit_code in (("prism", 1), ("gito", 0)):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                f"exit {exit_code}\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review unstaged", log)
        self.assertIn(
            "gito review --vs HEAD --filter app.txt --out .build/review/gito",
            log,
        )
        self.assertTrue((root / ".build/review/gito").is_dir())

    def test_review_local_script_preserves_configuration_error_exit_code(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'prism %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 1\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "not-configured",
                "prism",
            ],
            cwd=root,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("No command configured for local review tool 'not-configured'", result.stdout)
        self.assertIn("prism review unstaged", log_path.read_text(encoding="utf-8"))

    def test_review_local_script_reviews_branch_when_no_local_changes(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("branch\n", encoding="utf-8")
        self.run_git(root, "add", "app.txt")
        self.run_git(root, "commit", "-m", "branch change")
        merge_base = self.git_output(root, "rev-parse", "HEAD~1")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name in ("prism", "gito"):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_BASE_REF": "HEAD~1",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD~1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(f"prism review range {merge_base}..HEAD", log)
        self.assertIn(
            "gito review --vs HEAD~1 --filter app.txt --out .build/review/gito",
            log,
        )

    def test_review_local_script_prefers_local_changes_over_branch_diff(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "branch.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "branch.txt").write_text("branch\n", encoding="utf-8")
        self.run_git(root, "add", "branch.txt")
        self.run_git(root, "commit", "-m", "branch change")
        (root / "local.txt").write_text("untracked\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name in ("prism", "gito"):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_BASE_REF": "HEAD~1",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD~1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review codebase --paths local.txt", log)
        self.assertNotIn("prism review range", log)
        self.assertIn(
            "gito review --vs HEAD~1 --filter local.txt --out .build/review/gito",
            log,
        )
        self.assertNotIn("branch.txt", log)

    def test_review_local_script_all_scope_runs_codebase_providers(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        for name, exit_code in (("prism", 1), ("gito", 0)):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} %s\\n' \"$*\" >> {str(log_path)!r}\n"
                f"exit {exit_code}\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Local review scope: full codebase", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review codebase", log)
        self.assertIn("--exclude .agent,.agent/**", log)
        self.assertIn(".github,.github/**", log)
        self.assertIn(
            f"gito review --all --path {root.resolve()} --filter ",
            log,
        )
        self.assertIn("--out .build/review/gito-all", log)
        gito_line = next(line for line in log.splitlines() if line.startswith("gito "))
        gito_filter = gito_line.split(" --filter ", 1)[1].split(" --out ", 1)[0]
        gito_filter_paths = set(gito_filter.split(","))
        for excluded in (
            ".agent",
            ".agents",
            ".claude",
            ".codex",
            ".codebuddy",
            ".cursor",
            ".devin",
            ".factory",
            ".gemini",
            ".github",
            ".kiro",
            ".kilocode",
            ".opencode",
            ".pi",
            ".qoder",
            ".reasonix",
            ".trae",
            ".zcode",
            ".build",
            ".git",
            ".pytest_cache",
            ".obsidian-kb",
            ".trellis",
            ".ruff_cache",
            ".venv",
            ".sd-ai-command-pack",
            "node_modules",
        ):
            self.assertNotIn(excluded, gito_filter_paths)
        self.assertTrue((root / ".build/review/gito-all").is_dir())

    def test_review_local_script_all_scope_keeps_gito_all_when_tracked_files_deleted(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").unlink()

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Tracked or branch-diff deletions are present", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(f"gito review --all --path {root.resolve()} --filter ", log)
        gito_line = next(line for line in log.splitlines() if line.startswith("gito "))
        gito_filter = gito_line.split(" --filter ", 1)[1].split(" --out ", 1)[0]
        self.assertNotIn("app.txt", set(gito_filter.split(",")))

    def test_review_local_script_all_scope_keeps_gito_all_when_branch_diff_deletes_files(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "keep.txt").write_text("keep\n", encoding="utf-8")
        (root / "removed.txt").write_text("remove\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "removed.txt").unlink()
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "delete removed file")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD~1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Tracked or branch-diff deletions are present", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn(f"gito review --all --path {root.resolve()} --filter ", log)
        gito_line = next(line for line in log.splitlines() if line.startswith("gito "))
        gito_filter = gito_line.split(" --filter ", 1)[1].split(" --out ", 1)[0]
        gito_filter_paths = set(gito_filter.split(","))
        self.assertIn("keep.txt", gito_filter_paths)
        self.assertNotIn("removed.txt", gito_filter_paths)

    def test_review_local_script_retries_gito_rate_limit(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        state_path = Path(tools_tempdir.name) / "gito-attempts.txt"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"state={str(state_path)!r}\n"
            "count=\"$(cat \"$state\" 2>/dev/null || printf 0)\"\n"
            "count=$((count + 1))\n"
            "printf '%s\\n' \"$count\" > \"$state\"\n"
            f"printf 'gito attempt %s %s\\n' \"$count\" \"$*\" >> {str(log_path)!r}\n"
            "if [ \"$count\" -eq 1 ]; then\n"
            "  printf 'ClientError: 429 Slow down\\n'\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertIn("Gito appears rate-limited", result.stdout)
        self.assertIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 2, log)
        self.assertIn("gito attempt 2 review --vs HEAD --filter app.txt", log)

    def test_review_local_script_does_not_retry_gito_when_latest_status_is_not_429(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito attempt %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "printf 'ClientError: 429 Slow down\\n'\n"
            "printf 'Exception: provider summary 500\\n'\n"
            "exit 1\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertNotIn("Gito appears rate-limited", result.stdout)
        self.assertNotIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 1, log)

    def test_review_local_script_does_not_retry_gito_non_rate_limit_trace(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'gito attempt %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "printf 'A traceback mentioned provider rate limiting docs.\\n'\n"
            "printf 'Docs mention `ClientError: 429` or `Slow down`.\\n'\n"
            "printf 'ClientError: 404 Not Found\\n'\n"
            "exit 1\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertNotIn("Gito appears rate-limited", result.stdout)
        self.assertNotIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 1, log)

    def test_review_local_script_prism_codebase_empty_chunk_falls_back_to_batches(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'prism %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "paths_arg=''\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"${1:-}\" = --paths ]; then\n"
            "    shift\n"
            "    paths_arg=\"${1:-}\"\n"
            "    break\n"
            "  fi\n"
            "  shift\n"
            "done\n"
            "if [ -z \"$paths_arg\" ] || [[ \"$paths_arg\" == *,* ]]; then\n"
            "  printf 'Error: chunked review: chunk 0: no content in response\\n'\n"
            "  exit 4\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "prism"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE": "2",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("empty chunk response", result.stdout)
        self.assertIn("full codebase batch", result.stdout)
        self.assertIn("retrying each path individually", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism review codebase --fail-on high", log)
        self.assertIn("prism review codebase --paths", log)
        for line in log.splitlines():
            if " --paths " in line:
                self.assertNotIn("--paths .agents/", line)
                self.assertNotIn("--paths .github/", line)
                self.assertNotIn("--paths .trellis/", line)

    def test_review_local_script_prism_empty_chunk_after_split_is_not_auth(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'Error: chunked review: chunk 0: no content in response\\n'\n"
            "exit 4\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "prism"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE": "1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("empty chunk response after fallback splitting", result.stdout)
        self.assertNotIn("authentication or configuration", result.stdout)

    def test_review_local_script_prism_api_error_does_not_trigger_empty_chunk_fallback(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self._make_committed_review_repo()
        stub_bin, log_path = self._make_review_stub_bin()
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'prism %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "printf 'Error: chunked review: chunk 0: API error (status 400): billing unavailable\\n'\n"
            "exit 4\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "prism"],
            cwd=root,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("retrying in tracked-file batches", result.stdout)
        self.assertEqual(log_path.read_text(encoding="utf-8").count("prism "), 1)

    def test_review_local_script_labels_diff_empty_response_without_auth_claim(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self._make_committed_review_repo()
        (root / "app.txt").write_text("changed\n", encoding="utf-8")
        stub_bin, _ = self._make_review_stub_bin()
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            "printf 'Error: provider review: no content in response\\n'\n"
            "exit 4\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "prism"],
            cwd=root,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("empty or malformed provider response", result.stdout)
        self.assertNotIn("authentication or configuration", result.stdout)

    def test_review_local_script_caps_prism_empty_chunk_leaf_failures(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self._make_committed_review_repo()
        stub_bin, log_path = self._make_review_stub_bin()
        prism = stub_bin / "prism"
        prism.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'prism %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "printf 'Error: chunked review: chunk 0: no content in response\\n'\n"
            "exit 4\n",
            encoding="utf-8",
        )
        prism.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "prism"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_BATCH_SIZE": "1",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_CODEBASE_MAX_EMPTY_CHUNK_FAILURES": "2",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("reached 2 empty-response failures", result.stdout)
        self.assertEqual(log_path.read_text(encoding="utf-8").count("prism "), 3)

    def test_review_local_script_times_out_prism_and_gito_process_groups(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self._make_committed_review_repo()
        stub_bin, log_path = self._make_review_stub_bin()
        for name in ("prism", "gito"):
            tool = stub_bin / name
            tool.write_text(
                "#!/usr/bin/env bash\n"
                f"printf '{name} started\\n' >> {str(log_path)!r}\n"
                "sleep 10\n",
                encoding="utf-8",
            )
            tool.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_TIMEOUT_SECONDS": "1",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_TIMEOUT_SECONDS": "1",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=8,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout.count("command timed out after 1s"), 2)
        self.assertIn("Prism review: full codebase exited with status 124", result.stdout)
        self.assertIn("Gito review: full codebase timed out after 1s", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("prism started", log)
        self.assertIn("gito started", log)
        self.assertEqual(log.count("gito started"), 1)
        self.assertNotIn("Gito appears rate-limited", result.stdout)

    def test_review_local_script_sets_writable_uv_dirs_for_gito(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("codebase\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'UV_CACHE_DIR=%s\\n' \"$UV_CACHE_DIR\" >> {str(log_path)!r}\n"
            f"printf 'UV_TOOL_DIR=%s\\n' \"$UV_TOOL_DIR\" >> {str(log_path)!r}\n"
            f"printf 'gito %s\\n' \"$*\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)
        temp_root = root / "tmp"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "TMPDIR": str(temp_root),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(log_path.is_file(), result.stdout)
        log = log_path.read_text(encoding="utf-8")
        user_root = temp_root / f"sd-ai-command-pack-{os.getuid()}"
        self.assertIn(f"UV_CACHE_DIR={user_root}/uv-cache", log)
        self.assertIn(f"UV_TOOL_DIR={user_root}/uv-tools", log)
        self.assertTrue((user_root / "uv-cache").is_dir())
        self.assertTrue((user_root / "uv-tools").is_dir())
        self.assertIn("gito review --all", log)
        self.assertIn("--filter ", log)

    def test_review_local_scripts_register_temp_file_cleanup(self) -> None:
        script_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh",
        ]

        for script_path in script_paths:
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("cleanup_review_local_temp_files()", content, script_path)
            self.assertIn("trap cleanup_review_local_temp_files EXIT", content, script_path)
            self.assertEqual(
                content.count("$(mktemp "),
                content.count('REVIEW_LOCAL_TEMP_FILES+=("$'),
                script_path,
            )

        shell_lib_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-shell-lib.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
        ]
        for shell_lib_path in shell_lib_paths:
            content = shell_lib_path.read_text(encoding="utf-8")
            self.assertIn("register_sd_ai_command_pack_temp_file()", content, shell_lib_path)
            self.assertIn('REVIEW_LOCAL_TEMP_FILES+=("$file")', content, shell_lib_path)
            self.assertIn(
                'register_sd_ai_command_pack_temp_file "$output_file"',
                content,
                shell_lib_path,
            )

    def test_review_local_script_loads_gito_concurrency_env(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.write_gito_pack_env(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'MAX_CONCURRENT_TASKS=%s\\n' \"${{MAX_CONCURRENT_TASKS:-}}\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("MAX_CONCURRENT_TASKS=4", log_path.read_text(encoding="utf-8"))

    def test_review_local_script_preserves_explicit_gito_concurrency_env(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-review-local-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"printf 'MAX_CONCURRENT_TASKS=%s\\n' \"${{MAX_CONCURRENT_TASKS:-}}\" >> {str(log_path)!r}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all", "gito"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "MAX_CONCURRENT_TASKS": "2",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("MAX_CONCURRENT_TASKS=2", log_path.read_text(encoding="utf-8"))

    def test_review_local_script_disabled_provider_smoke(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_PRISM_MODE": "0",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_GITO_MODE": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Skipping Prism review", result.stdout)
        self.assertIn("Skipping Gito review", result.stdout)
        self.assertIn("Local review providers completed", result.stdout)

    def test_review_local_script_runs_configured_custom_tool(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "printf 'custom-ok\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("==> Local review: custom", result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "custom-ok\n")

    def test_review_local_script_runs_custom_tool_without_login_shell(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh"],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "case \"$-\" in *l*) printf 'login\\n' ;; *) printf 'non-login\\n' ;; esac > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "non-login\n")

    def test_review_local_all_scope_prefers_configured_all_custom_tool(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--all"],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "printf 'diff-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_CUSTOM_COMMAND": (
                    "printf 'all-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Local review scope: full codebase", result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "all-command\n")

    def test_review_local_full_codebase_alias_uses_all_custom_tool(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        tool_log = root / "custom-tool.log"

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "--full-codebase",
            ],
            cwd=root,
            env={
                **os.environ,
                "CUSTOM_TOOL_LOG": str(tool_log),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS": "custom",
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_CUSTOM_COMMAND": (
                    "printf 'diff-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
                "SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_CUSTOM_COMMAND": (
                    "printf 'full-command\\n' > \"$CUSTOM_TOOL_LOG\""
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Local review scope: full codebase", result.stdout)
        self.assertEqual(tool_log.read_text(encoding="utf-8"), "full-command\n")

    def test_review_local_script_lists_supported_tools(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "--list-tools",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.splitlines(), ["prism", "gito", "all", "default"])

    def test_review_local_script_help_describes_full_codebase_alias(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "--help"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--full-codebase", result.stdout)
        self.assertIn("--list-tools", result.stdout)
        self.assertIn("Tool names must use only", result.stdout)

    def test_review_local_script_reports_unknown_tool(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-local.sh", "unknown"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("No command configured for local review tool 'unknown'", result.stdout)

    def test_review_local_script_rejects_unsafe_tool_name(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()

        result = subprocess.run(
            [
                self._bash_path,
                "scripts/sd-ai-command-pack-review-local.sh",
                "../unknown",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Unsupported local review tool name '../unknown'", result.stdout)

    def test_full_check_script_retries_gito_rate_limit(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_installed_review_repo()
        self.write_gito_pack_env(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "app.txt").write_text("before\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "baseline")
        (root / "app.txt").write_text("after\n", encoding="utf-8")

        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-full-check-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        stub_bin = Path(tools_tempdir.name) / "bin"
        stub_bin.mkdir()
        log_path = Path(tools_tempdir.name) / "tool.log"
        state_path = Path(tools_tempdir.name) / "gito-attempts.txt"
        gito = stub_bin / "gito"
        gito.write_text(
            "#!/usr/bin/env bash\n"
            f"state={str(state_path)!r}\n"
            "count=\"$(cat \"$state\" 2>/dev/null || printf 0)\"\n"
            "count=$((count + 1))\n"
            "printf '%s\\n' \"$count\" > \"$state\"\n"
            f"printf 'gito attempt %s %s\\n' \"$count\" \"$*\" >> {str(log_path)!r}\n"
            "if [ \"$count\" -eq 1 ]; then\n"
            "  printf 'ClientError: 429 Slow down\\n'\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-full-check.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT": "0",
                "SD_AI_COMMAND_PACK_INSTALL_AUDIT": "0",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_PRISM": "0",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO": "1",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF": "HEAD",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_MAX_ATTEMPTS": "2",
                "SD_AI_COMMAND_PACK_FULL_CHECK_GITO_RETRY_DELAY_SECONDS": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Gito attempt 1/2", result.stdout)
        self.assertIn("Gito appears rate-limited", result.stdout)
        self.assertIn("Gito attempt 2/2", result.stdout)
        log = log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("gito attempt"), 2, log)
        self.assertIn("gito attempt 2 review --vs HEAD --filter app.txt", log)

    def test_pr_body_scope_script_classifies_review_local_as_ci_review(self) -> None:
        root = self.make_installed_review_repo()
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            "scripts/sd-ai-command-pack-review-local.sh\n"
            "scripts/sd-ai-command-pack-review-learnings.py\n"
            ".qoder/commands/sd-review-local.md\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("detected Tooling/generated scope", result.stdout)
        self.assertIn("detected CI/review scope", result.stdout)
        self.assertIn(".qoder/commands/sd-review-local.md", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-review-local.sh", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", result.stdout)


if __name__ == "__main__":
    unittest.main()
