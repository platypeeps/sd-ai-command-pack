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


class UpdateSpecKbTests(InstallTestCase):
    """Tests for Obsidian/LLM knowledge-base export behavior."""

    def test_update_spec_wrappers_include_repospec_and_architecture_gates(self) -> None:
        shared_skill = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        for expected in (
            "Resolve the `trellis-update-spec` skill by name",
            "skill discovery mechanism",
            "Use the Trellis update-spec skill as the primary instructions",
            "repospec artifact",
            "Makefile",
            "package.json",
            "instead of hand-editing generated",
            "Repomix",
            "docs/repomix-map.md",
            "no infrastructure",
            "ARCHITECTURE.md",
            "docs/ARCHITECTURE.md",
            ".trellis/spec/**/architecture*.md",
            "Do not create a new overview unless",
            "architecture signals",
            "package/module boundaries",
            "not present",
            "not warranted",
            ".obsidian-kb",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            "exits nonzero",
            "repo root `.gitignore`",
            "copies",
            "visible semantic",
            "file/folder names that start with `.`",
            ".trellis/workflow.md",
            ".trellis/config.yaml",
            ".trellis/spec/**/*.md",
            ".trellis/tasks/**/*.md",
            ".trellis/workspace/",
            ".obsidian-kb/Dashboard - <repo>.md",
            "landing page",
            "Obsidian KB",
            "Obsidian vault copy",
        ):
            self.assertIn(expected, shared_skill)

        adapter_paths = [
            install.ROOT / "templates/.claude/commands/sd/update-spec.md",
            install.ROOT / "templates/.commands/sd-update-spec.md",
            install.ROOT / "templates/.gemini/commands/sd/update-spec.toml",
            install.ROOT / "templates/.github/prompts/sd-update-spec.prompt.md",
        ]
        for adapter_path in adapter_paths:
            content = adapter_path.read_text(encoding="utf-8")
            self.assertIn("Resolve the `sd-update-spec` skill by name", content)
            self.assertIn("source of truth for Trellis update-spec delegation", content)
            self.assertNotIn("Trellis " + "update-spec first", content)
            self.assertNotIn("repospec artifact", content)

    def test_update_spec_docs_explain_obsidian_kb_vault_copying(self) -> None:
        doc_paths = [
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]

        for doc_path in doc_paths:
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn(".obsidian-kb/", content)
            self.assertIn(".obsidian-kb/Dashboard - <repo>.md", content)
            self.assertIn(".obsidian-kb/LLM-KB - <repo>.md", content)
            self.assertIn("Markdown landing page", content)
            self.assertIn("GitHub repository link", content)
            self.assertIn("visible semantic category", content)
            self.assertIn("folder names do not start with `.`", content)
            self.assertIn(".trellis/tasks/**/*.md", content)
            self.assertIn("older symlink-based helper", content)
            self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py", content)
            self.assertIn('cp -R "$(pwd)/.obsidian-kb/."', content)
            self.assertIn("Copy-Item -Recurse -Force", content)
            self.assertNotIn("New-Item -ItemType SymbolicLink", content)
            self.assertNotIn("PowerShell running as Administrator", content)
            self.assertNotIn("Developer Mode enabled", content)

        gitignore = (install.ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".obsidian-kb/", gitignore)
        self.assertIn(".sd-ai-command-pack/installed-targets.txt", gitignore)
        self.assertIn(".sd-ai-command-pack/local-only.txt", gitignore)

    def test_update_spec_kb_ignore_write_uses_atomic_write(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_atomic_write",
        )
        root = self.make_repo()
        gitignore = root / ".gitignore"
        original = "dist/\n"
        gitignore.write_text(original, encoding="utf-8")

        with mock.patch.object(module.os, "replace", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(OSError, "blocked"):
                module.ensure_ignore_file(gitignore, local=False)

        self.assertEqual(gitignore.read_text(encoding="utf-8"), original)
        self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_update_spec_kb_reports_gitignore_symlink_conflict(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        real_gitignore = root / ".gitignore.real"
        real_gitignore.write_text("dist/\n", encoding="utf-8")
        gitignore = root / ".gitignore"
        gitignore.symlink_to(real_gitignore.name)
        script = install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"

        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("gitignore: conflict: .gitignore is a symlink", result.stdout)
        self.assertIn("ignore entry could not be updated", result.stdout)
        self.assertTrue(gitignore.is_symlink())
        self.assertEqual(real_gitignore.read_text(encoding="utf-8"), "dist/\n")

    def test_update_spec_kb_refresh_exits_three_on_conflicts(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-update-spec-kb.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        copy_path = root / ".obsidian-kb/Repository Overview/README.md"
        self.assertTrue(copy_path.is_file(), result.stdout)
        copy_path.unlink()
        copy_path.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-update-spec-kb.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("conflicts:", result.stdout)

    def test_update_spec_kb_script_builds_gitignored_copy_folder(self) -> None:
        root = self.make_repo()
        self.run_git(root, "remote", "add", "origin", "git@github.com:example/project.git")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        files = {
            "README.md": "# Project\n",
            "AGENTS.md": "# Agent Notes\n",
            "docs/SD_AI_COMMAND_PACK.md": "# SD Pack\n",
            "docs/repomix-map.md": "# Repo Map\n",
            "docs/architecture.md": "# Architecture\n",
            ".trellis/workflow.md": "# Workflow\n",
            ".trellis/config.yaml": "project: test\n",
            ".trellis/spec/backend/index.md": "# Backend Spec\n",
            ".trellis/tasks/07-01-demo/prd.md": "# Demo PRD\n",
            ".trellis/tasks/archive/2026-07/07-00-old/design.md": "# Old Design\n",
            "package.json": "{}\n",
            "packages/api/README.md": "# API Package\n",
            "src/main.py": "print('runtime')\n",
            ".trellis/workspace/sdelmas/journal.md": "# private journal\n",
            "node_modules/pkg/README.md": "# dependency docs\n",
        }
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Obsidian KB: .obsidian-kb", result.stdout)
        self.assertIn("gitignore: added", result.stdout)
        self.assertIn("copies:", result.stdout)
        self.assertIn("dashboard: created", result.stdout)
        self.assertIn("llm overview: created", result.stdout)
        self.assertIn("vault copy example:", result.stdout)

        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/\n", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb start", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb end", gitignore)
        self.assertEqual(gitignore.count(".obsidian-kb/"), 1)
        expected_copies = {
            "README.md": "Repository Overview/README.md",
            "AGENTS.md": "Agent and Platform Guidance/AGENTS.md",
            "docs/repomix-map.md": "Repository Maps/repomix-map.md",
            "docs/architecture.md": "Architecture and Decisions/architecture.md",
            ".trellis/workflow.md": "Workflow and Configuration/workflow.md",
            ".trellis/config.yaml": "Workflow and Configuration/config.yaml",
            ".trellis/spec/backend/index.md": "Backend Specs/index.md",
            ".trellis/tasks/07-01-demo/prd.md": (
                "Task Documentation/07-01-demo-prd.md"
            ),
            ".trellis/tasks/archive/2026-07/07-00-old/design.md": (
                "Task Documentation/archive-2026-07-07-00-old-design.md"
            ),
            ".agents/skills/sd-review-pr/SKILL.md": (
                "Agent and Platform Guidance/codex-sd-review-pr.md"
            ),
            "package.json": "Project Manifests/package.json",
            "packages/api/README.md": "Package Documentation/packages-api-README.md",
        }
        for relative_path, kb_relative_path in expected_copies.items():
            copied = root / ".obsidian-kb" / kb_relative_path
            self.assertTrue(copied.is_file(), copied)
            self.assertFalse(copied.is_symlink(), copied)
            self.assertEqual(
                copied.read_bytes(),
                (root / relative_path).read_bytes(),
            )
        for copied_path in (root / ".obsidian-kb").rglob("*"):
            relative = copied_path.relative_to(root / ".obsidian-kb")
            self.assertFalse(
                any(part.startswith(".") for part in relative.parts),
                relative.as_posix(),
            )
            self.assertNotIn("trellis", relative.as_posix().lower())

        dashboard = root / ".obsidian-kb" / f"Dashboard - {root.name}.md"
        self.assertTrue(dashboard.is_file())
        dashboard_text = dashboard.read_text(encoding="utf-8")
        self.assertIn(f"# Dashboard - {root.name}", dashboard_text)
        self.assertIn(
            "GitHub: [example/project](https://github.com/example/project)",
            dashboard_text,
        )
        self.assertIn(
            f"[LLM-KB - {root.name}.md](LLM-KB%20-%20{root.name}.md)",
            dashboard_text,
        )
        self.assertIn("self-contained copy", dashboard_text)
        self.assertIn(
            "[README.md](Repository%20Overview/README.md) - Repository "
            "overview and primary entrypoint.",
            dashboard_text,
        )
        self.assertIn(
            "[AGENTS.md](Agent%20and%20Platform%20Guidance/AGENTS.md) - "
            "Project instructions for AI coding agents.",
            dashboard_text,
        )
        self.assertIn(
            "[codex-sd-review-pr.md]"
            "(Agent%20and%20Platform%20Guidance/codex-sd-review-pr.md)",
            dashboard_text,
        )
        self.assertIn("## Repository Overview", dashboard_text)
        self.assertIn("## Agent and Platform Guidance", dashboard_text)
        self.assertIn("## Pack Documentation", dashboard_text)
        self.assertIn("## Architecture and Decisions", dashboard_text)
        self.assertIn("## Workflow and Configuration", dashboard_text)
        self.assertIn("## Task Documentation", dashboard_text)
        self.assertIn("## Backend Specs", dashboard_text)
        self.assertIn("## Repository Maps", dashboard_text)
        self.assertIn("## Project Manifests", dashboard_text)
        self.assertIn("## Package Documentation", dashboard_text)
        self.assertNotIn("## Repository root", dashboard_text)
        self.assertNotIn("## docs", dashboard_text)
        self.assertNotIn("## .trellis/spec/backend", dashboard_text)
        self.assertNotIn("## Trellis", dashboard_text)
        self.assertNotIn(".trellis", dashboard_text)
        self.assertIn("[README.md](Repository%20Overview/README.md)", dashboard_text)
        self.assertIn(
            "[repomix-map.md](Repository%20Maps/repomix-map.md)",
            dashboard_text,
        )
        self.assertIn(
            "[index.md](Backend%20Specs/index.md)",
            dashboard_text,
        )
        self.assertIn(
            "[07-01-demo-prd.md](Task%20Documentation/07-01-demo-prd.md)",
            dashboard_text,
        )
        self.assertFalse((root / ".obsidian-kb/Dashboard.md").exists())
        self.assertFalse((root / ".obsidian-kb/LLM-KB.md").exists())

        overview = root / ".obsidian-kb" / f"LLM-KB - {root.name}.md"
        self.assertTrue(overview.is_file())
        overview_text = overview.read_text(encoding="utf-8")
        self.assertIn("# LLM Knowledge Base", overview_text)
        self.assertIn(
            "GitHub: [example/project](https://github.com/example/project)",
            overview_text,
        )
        self.assertIn("Copied knowledge files:", overview_text)
        self.assertIn("[README.md](Repository%20Overview/README.md)", overview_text)
        self.assertIn(
            "[SD_AI_COMMAND_PACK.md](Pack%20Documentation/SD_AI_COMMAND_PACK.md)",
            overview_text,
        )
        self.assertIn(
            "[workflow.md](Workflow%20and%20Configuration/workflow.md)",
            overview_text,
        )
        self.assertIn("### Repository Overview", overview_text)
        self.assertIn("### Agent and Platform Guidance", overview_text)
        self.assertIn("### Pack Documentation", overview_text)
        self.assertIn("### Task Documentation", overview_text)
        self.assertIn("### Backend Specs", overview_text)
        self.assertNotIn("### Repository root", overview_text)
        self.assertNotIn("### docs", overview_text)
        self.assertNotIn("### Trellis", overview_text)
        self.assertNotIn("](.trellis", overview_text)

        self.assertFalse((root / ".obsidian-kb/src/main.py").exists())
        self.assertFalse(
            (root / ".obsidian-kb/.trellis/workspace/sdelmas/journal.md").exists()
        )
        self.assertFalse((root / ".obsidian-kb/node_modules/pkg/README.md").exists())

        (root / "docs/repomix-map.md").unlink()
        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: present", result.stdout)
        self.assertIn("stale generated entries removed: 1", result.stdout)
        self.assertIn("dashboard: updated", result.stdout)
        self.assertIn("llm overview: updated", result.stdout)
        self.assertFalse(
            (root / ".obsidian-kb/Repository Maps/repomix-map.md").exists()
        )
        self.assertNotIn(
            "repomix-map.md",
            dashboard.read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            "repomix-map.md",
            overview.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (root / ".gitignore").read_text(encoding="utf-8").count(".obsidian-kb/"),
            1,
        )

    def test_update_spec_kb_excludes_trellis_runtime_and_backup_artifacts(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        files = {
            ".trellis/workflow.md": "# Workflow\n",
            ".trellis/spec/backend/index.md": "# Backend Spec\n",
            ".trellis/tasks/07-01-demo/prd.md": "# Demo PRD\n",
            ".trellis/.backup-2026-07-06T01-42-40/.agents/skills/trellis-meta/"
            "references/platform-files/agents.md": "# stale backup copy\n",
            ".trellis/.runtime/session-notes.md": "# runtime scratch\n",
            ".trellis/worktrees/feature-x/README.md": "# worktree checkout\n",
        }
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

        kb = root / ".obsidian-kb"
        copies = {
            path.relative_to(kb).as_posix(): path.read_text(encoding="utf-8")
            for path in kb.rglob("*")
            if path.is_file()
        }
        self.assertTrue(
            any("# Workflow" in content for content in copies.values()),
            sorted(copies),
        )
        self.assertTrue(
            any("# Backend Spec" in content for content in copies.values()),
            sorted(copies),
        )
        self.assertTrue(
            any("# Demo PRD" in content for content in copies.values()),
            sorted(copies),
        )
        for leaked_marker in (
            "stale backup copy",
            "runtime scratch",
            "worktree checkout",
        ):
            self.assertFalse(
                any(leaked_marker in content for content in copies.values()),
                f"{leaked_marker!r} leaked into the generated KB: {sorted(copies)}",
            )

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--check",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_update_spec_kb_derives_github_repo_url_from_remote(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_remote_test",
        )

        cases = {
            "git@github.com:owner/repo.git": "https://github.com/owner/repo",
            "ssh://git@github.com/owner/repo.git": "https://github.com/owner/repo",
            "https://github.com/owner/repo.git": "https://github.com/owner/repo",
            "http://github.com/owner/repo": "https://github.com/owner/repo",
        }
        for remote, expected in cases.items():
            with self.subTest(remote=remote):
                self.assertEqual(
                    module.github_repository_url_from_remote(remote),
                    expected,
                )

        self.assertIsNone(module.github_repository_url_from_remote(None))
        self.assertIsNone(module.github_repository_url_from_remote(""))
        self.assertIsNone(
            module.github_repository_url_from_remote("git@example.com:owner/repo.git")
        )

    def test_update_spec_kb_normalizes_platform_agents_filenames(self) -> None:
        for script_path, module_name in (
            (
                install.ROOT / "scripts/sd-ai-command-pack-update-spec-kb.py",
                "sd_ai_command_pack_update_spec_kb_source_destination_test",
            ),
            (
                install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
                "sd_ai_command_pack_update_spec_kb_template_destination_test",
            ),
        ):
            module = self.load_module_from_path(script_path, module_name)
            with self.subTest(script=script_path):
                self.assertEqual(
                    module.destination_filename_for_source(Path(".agents/agents.md")),
                    "codex-agents.md",
                )
                self.assertEqual(
                    module.destination_filename_for_source(Path(".agents/AGENTS.md")),
                    "codex-agents.md",
                )
                self.assertEqual(
                    module.destination_filename_for_source(Path("AGENTS.md")),
                    "AGENTS.md",
                )

    def test_update_spec_kb_replaces_legacy_generated_dashboard_name(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        legacy_dashboard = root / ".obsidian-kb/Dashboard.md"
        legacy_dashboard.parent.mkdir(parents=True, exist_ok=True)
        legacy_dashboard.write_text(
            "<!-- SD-AI-COMMAND-PACK:OBSIDIAN-KB-DASHBOARD -->\n"
            "# Obsidian KB Dashboard\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("stale generated entries removed: 1", result.stdout)
        self.assertFalse(legacy_dashboard.exists())
        dashboard = root / ".obsidian-kb" / f"Dashboard - {root.name}.md"
        self.assertTrue(dashboard.is_file())
        self.assertIn(
            f"# Dashboard - {root.name}",
            dashboard.read_text(encoding="utf-8"),
        )

    def test_update_spec_kb_replaces_legacy_generated_overview_name(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        legacy_overview = root / ".obsidian-kb/LLM-KB.md"
        legacy_overview.parent.mkdir(parents=True, exist_ok=True)
        legacy_overview.write_text(
            "<!-- SD-AI-COMMAND-PACK:LLM-KB-OVERVIEW -->\n"
            "# LLM Knowledge Base\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("stale generated entries removed: 1", result.stdout)
        self.assertFalse(legacy_overview.exists())
        overview = root / ".obsidian-kb" / f"LLM-KB - {root.name}.md"
        self.assertTrue(overview.is_file())
        self.assertIn(
            "# LLM Knowledge Base",
            overview.read_text(encoding="utf-8"),
        )

    def test_update_spec_kb_preserves_user_notes_outside_managed_categories(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        initial = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(initial.returncode, 0, initial.stdout)

        custom_note = root / ".obsidian-kb/My Notes.md"
        custom_note.write_text("keep me\n", encoding="utf-8")
        custom_asset = root / ".obsidian-kb/Attachments/diagram.txt"
        custom_asset.parent.mkdir(parents=True)
        custom_asset.write_text("asset\n", encoding="utf-8")
        custom_legacy_name = root / ".obsidian-kb/Dashboard.md"
        custom_legacy_name.write_text("custom dashboard note\n", encoding="utf-8")

        check_result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--check",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(check_result.returncode, 0, check_result.stdout)
        self.assertIn("conflicts: none", check_result.stdout)
        self.assertNotIn("stale generated entries would be removed", check_result.stdout)

        refresh = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(refresh.returncode, 0, refresh.stdout)
        self.assertEqual(custom_note.read_text(encoding="utf-8"), "keep me\n")
        self.assertEqual(custom_asset.read_text(encoding="utf-8"), "asset\n")
        self.assertEqual(
            custom_legacy_name.read_text(encoding="utf-8"),
            "custom dashboard note\n",
        )

    def test_update_spec_kb_quotes_vault_copy_example(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_quote_test",
        )
        root = Path("/tmp/repo with spaces")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.report_kb_state(
                root=root,
                mode=None,
                gitignore_state="present",
                copies=0,
                stale=0,
                dashboard_state="present",
                conflicts=[],
            )

        self.assertIn("cp -R '/tmp/repo with spaces/.obsidian-kb/.'", output.getvalue())

    def test_update_spec_kb_escapes_repo_name_in_overview_link_label(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name) / "repo[docs]"
        root.mkdir()
        (root / ".trellis").mkdir()
        (root / ".trellis/config.yaml").write_text("# test\n", encoding="utf-8")
        self.run_git(root, "init")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        dashboard = root / ".obsidian-kb/Dashboard - repo[docs].md"
        self.assertTrue(dashboard.is_file())
        self.assertIn(
            "[LLM-KB - repo\\[docs\\].md](LLM-KB%20-%20repo%5Bdocs%5D.md)",
            dashboard.read_text(encoding="utf-8"),
        )

    def test_update_spec_kb_replaces_legacy_generated_symlink_with_copy(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        legacy_link = root / ".obsidian-kb/README.md"
        legacy_link.parent.mkdir(parents=True)
        try:
            legacy_link.symlink_to("../README.md")
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("copies:", result.stdout)
        self.assertIn("conflicts: none", result.stdout)
        self.assertFalse(legacy_link.exists())
        copy = root / ".obsidian-kb/Repository Overview/README.md"
        self.assertTrue(copy.is_file())
        self.assertFalse(copy.is_symlink())
        self.assertEqual(copy.read_text(encoding="utf-8"), "# Project\n")

    def test_update_spec_kb_converts_existing_symlink_tree_to_category_copies(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        files = {
            "README.md": "# Project\n",
            "AGENTS.md": "# Agent Notes\n",
            ".trellis/spec/backend/index.md": "# Backend Spec\n",
        }
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        legacy_root = root / ".obsidian-kb"
        legacy_root.mkdir()
        legacy_spec = legacy_root / ".trellis/spec/backend/index.md"
        legacy_spec.parent.mkdir(parents=True)
        try:
            (legacy_root / "README.md").symlink_to("../README.md")
            (legacy_root / "AGENTS.md").symlink_to("../AGENTS.md")
            legacy_spec.symlink_to("../../../../.trellis/spec/backend/index.md")
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("legacy symlinks converted: 3", result.stdout)
        self.assertIn("conflicts: none", result.stdout)
        self.assertFalse((legacy_root / "README.md").exists())
        self.assertFalse((legacy_root / "AGENTS.md").exists())
        self.assertFalse((legacy_root / ".trellis").exists())
        expected_copies = {
            "Repository Overview/README.md": "# Project\n",
            "Agent and Platform Guidance/AGENTS.md": "# Agent Notes\n",
            "Backend Specs/index.md": "# Backend Spec\n",
        }
        for relative_path, content in expected_copies.items():
            copy = legacy_root / relative_path
            self.assertTrue(copy.is_file(), copy)
            self.assertFalse(copy.is_symlink(), copy)
            self.assertEqual(copy.read_text(encoding="utf-8"), content)
        self.assertEqual(
            [
                path
                for path in legacy_root.rglob("*")
                if path.is_symlink()
            ],
            [],
        )

    def test_update_spec_kb_help_is_read_only(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--help",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("usage:", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--check", result.stdout)
        self.assertFalse((root / ".obsidian-kb").exists())

    def test_update_spec_kb_dry_run_does_not_write_files(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--dry-run",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertIn("planned copies:", result.stdout)
        self.assertFalse((root / ".obsidian-kb").exists())
        self.assertEqual((root / ".gitignore").read_text(encoding="utf-8"), "dist/\n")

    def test_update_spec_kb_check_detects_and_accepts_current_state(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        stale = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--check",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(stale.returncode, 1, stale.stdout)
        self.assertIn("mode: check", stale.stdout)
        self.assertIn("Repository Overview/README.md is missing", stale.stdout)

        refresh = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(refresh.returncode, 0, refresh.stdout)

        current = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                "--check",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(current.returncode, 0, current.stdout)
        self.assertIn("conflicts: none", current.stdout)

    def test_update_spec_kb_does_not_overwrite_custom_dashboard(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        dashboard = root / ".obsidian-kb" / f"Dashboard - {root.name}.md"
        dashboard.parent.mkdir(parents=True)
        dashboard.write_text("custom dashboard\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("dashboard: conflict", result.stdout)
        self.assertIn(
            f"Dashboard - {root.name}.md exists and is not generated by this tool",
            result.stdout,
        )
        self.assertEqual(dashboard.read_text(encoding="utf-8"), "custom dashboard\n")
        copy = root / ".obsidian-kb/Repository Overview/README.md"
        self.assertTrue(copy.is_file())
        self.assertFalse(copy.is_symlink())

    def test_update_spec_kb_uses_local_exclude_for_local_only_install(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        marker = root / install.LOCAL_ONLY_MARKER_FILE
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("local only\n", encoding="utf-8")
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: local-exclude added", result.stdout)
        self.assertEqual((root / ".gitignore").read_text(encoding="utf-8"), "dist/\n")
        exclude = Path(self.git_output(root, "rev-parse", "--git-path", "info/exclude"))
        if not exclude.is_absolute():
            exclude = root / exclude
        exclude_text = exclude.read_text(encoding="utf-8")
        self.assertIn("# sd-ai-command-pack obsidian-kb start", exclude_text)
        self.assertIn("# sd-ai-command-pack obsidian-kb end", exclude_text)
        self.assertIn(".obsidian-kb/", exclude_text)
        copy = root / ".obsidian-kb/Repository Overview/README.md"
        self.assertTrue(copy.is_file())
        self.assertFalse(copy.is_symlink())

    def test_update_spec_kb_upgrades_unmarked_gitignore_entry(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_text(
            "dist/\n.obsidian-kb/\nlogs/\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: updated", result.stdout)
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/\n", gitignore)
        self.assertIn("logs/\n", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb start", gitignore)
        self.assertIn("# sd-ai-command-pack obsidian-kb end", gitignore)
        self.assertEqual(gitignore.count(".obsidian-kb/"), 1)

    def test_update_spec_kb_preserves_invalid_existing_gitignore_bytes(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_bytes(b"dist-\xff/\n.obsidian-kb/\n")

        result = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-update-spec-kb.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: updated", result.stdout)
        gitignore = (root / ".gitignore").read_bytes()
        self.assertIn(b"dist-\xff/\n", gitignore)
        self.assertIn(b"# sd-ai-command-pack obsidian-kb start\n", gitignore)


if __name__ == "__main__":
    unittest.main()
