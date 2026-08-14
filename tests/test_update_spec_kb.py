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

    def test_update_spec_skill_and_flat_references_cover_extension_gates(self) -> None:
        shared_skill = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        reference_root = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/references"
        )
        repository_map = (reference_root / "repository-map.md").read_text(
            encoding="utf-8"
        )
        architecture = (reference_root / "architecture.md").read_text(
            encoding="utf-8"
        )
        obsidian_kb = (reference_root / "obsidian-kb.md").read_text(
            encoding="utf-8"
        )

        for expected in (
            "Resolve the `trellis-update-spec` skill by name",
            "skill discovery mechanism",
            "Use the Trellis update-spec skill as the primary instructions",
            "references/repository-map.md",
            "references/architecture.md",
            "references/obsidian-kb.md",
            "routine spec-only run loads no optional reference",
            "never follow a reference from another reference",
            "scripts/sd-ai-command-pack-update-spec-kb.py",
            "no infrastructure",
            "not present",
            "not warranted",
            "Obsidian KB",
            "Obsidian vault copy",
        ):
            self.assertIn(expected, shared_skill)

        for expected in (
            "Makefile",
            "package.json",
            "instead of hand-editing generated",
            "Repomix",
            "docs/repomix-map.md",
            "no infrastructure",
        ):
            self.assertIn(expected, repository_map)

        for expected in (
            "ARCHITECTURE.md",
            "docs/ARCHITECTURE.md",
            ".trellis/spec/**/architecture*.md",
            "Do not create an overview unless",
            "architectural signals",
            "package/module",
            "not present",
            "not warranted",
        ):
            self.assertIn(expected, architecture)

        for expected in (
            ".obsidian-kb",
            "exits nonzero",
            ".gitignore",
            "copies",
            ".trellis/workflow.md",
            ".trellis/config.yaml",
            ".trellis/spec/**/*.md",
            ".trellis/tasks/**/*.md",
            ".trellis/workspace/",
            "Dashboard - <repo>.md",
            "Do not rebuild the KB manually",
        ):
            self.assertIn(expected, obsidian_kb)
        self.assertRegex(obsidian_kb, r"visible\s+semantic")

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
            self.assertIn("root `.obsidian-kb` path may itself be a symlink", content)
            self.assertIn("root-anchored `/.obsidian-kb` ignore rule", content)
            self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py", content)
            self.assertIn('cp -R "$(pwd)/.obsidian-kb/."', content)
            self.assertIn("Copy-Item -Recurse -Force", content)
            self.assertNotIn("New-Item -ItemType SymbolicLink", content)
            self.assertNotIn("PowerShell running as Administrator", content)
            self.assertNotIn("Developer Mode enabled", content)

        gitignore = (install.ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/.obsidian-kb", gitignore)
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

    def test_file_ends_with_kb_copy_marker_bounded_tail_read(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_marker_tail",
        )
        root = self.make_repo()
        marker = module.KB_COPY_MARKER_SUFFIX_BYTES

        ends_with = root / "ends-with.md"
        ends_with.write_bytes(b"# Copy\nbody text\n" + marker)
        self.assertTrue(module.file_ends_with_kb_copy_marker(ends_with))

        no_marker = root / "no-marker.md"
        no_marker.write_bytes(b"# Plain user note\nno marker here\n")
        self.assertFalse(module.file_ends_with_kb_copy_marker(no_marker))

        mid_file = root / "mid-file.md"
        mid_file.write_bytes(b"quote " + marker + b" then more trailing text\n")
        self.assertFalse(module.file_ends_with_kb_copy_marker(mid_file))

        shorter = root / "shorter.md"
        shorter.write_bytes(marker[:-1])
        self.assertFalse(module.file_ends_with_kb_copy_marker(shorter))

        empty = root / "empty.md"
        empty.write_bytes(b"")
        self.assertFalse(module.file_ends_with_kb_copy_marker(empty))

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

    def test_update_spec_kb_refresh_block_emits_kb_target_fragment(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_kb_target_block",
        )
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        stdout = io.StringIO()
        with mock.patch.object(
            module, "create_copies", side_effect=OSError("Permission denied: kb copy")
        ):
            with contextlib.redirect_stdout(stdout):
                rc = module.refresh(root, as_json=True)
        self.assertEqual(rc, 2)

        payload = json.loads(stdout.getvalue().strip().splitlines()[-1])
        self.assertEqual(payload["outcome"], "blocked")
        evidence = payload["environmentBlocked"]
        self.assertEqual(evidence["schemaVersion"], 1)
        self.assertEqual(evidence["boundary"], "kb-target")
        self.assertEqual(evidence["mutationState"], "partial-recoverable")
        self.assertTrue(evidence["retryable"])
        self.assertEqual(evidence["checkpoint"], "kb-refresh")
        self.assertEqual(evidence["recoveryAction"]["kind"], "skill")
        self.assertIn("re-run", evidence["recoveryAction"]["instruction"].lower())
        self.assertIn("Permission denied", evidence["diagnostic"])

        # Without --json the stdout envelope must not appear (opt-in only); the
        # human error line rides stderr and the exit code is unchanged.
        plain = io.StringIO()
        with mock.patch.object(
            module, "create_copies", side_effect=OSError("blocked")
        ):
            with contextlib.redirect_stdout(plain):
                rc_plain = module.refresh(root, as_json=False)
        self.assertEqual(rc_plain, 2)
        self.assertNotIn("environmentBlocked", plain.getvalue())

    def test_update_spec_kb_refresh_block_is_retryable_via_idempotent_reconcile(
        self,
    ) -> None:
        # The kb-target block claims retryable=True: the KB copy folder is a
        # regenerable mirror, so re-running the refresh after the block clears
        # reconciles to the same tree without duplicating entries.
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        script = PACK_ROOT / "scripts/sd-ai-command-pack-update-spec-kb.py"

        def _refresh() -> None:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)

        def _tree() -> tuple[tuple[str, str], ...]:
            entries = []
            for path in sorted((root / ".obsidian-kb").rglob("*")):
                if path.is_file():
                    rel = str(path.relative_to(root))
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    entries.append((rel, digest))
            return tuple(entries)

        _refresh()
        first = _tree()
        self.assertTrue(first)
        _refresh()
        second = _tree()
        self.assertEqual(first, second)

    def test_update_spec_kb_inspect_block_emits_none_mutation_fragment(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "sd_ai_command_pack_update_spec_kb_kb_inspect_block",
        )
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        stdout = io.StringIO()
        with mock.patch.object(module, "repo_root", return_value=root):
            with mock.patch.object(
                module, "check_current", side_effect=OSError("Permission denied: kb read")
            ):
                with contextlib.redirect_stdout(stdout):
                    rc = module.main(["--check", "--json"])
        self.assertEqual(rc, 2)

        evidence = json.loads(stdout.getvalue().strip().splitlines()[-1])[
            "environmentBlocked"
        ]
        self.assertEqual(evidence["boundary"], "kb-target")
        self.assertEqual(evidence["mutationState"], "none")
        self.assertTrue(evidence["retryable"])
        self.assertEqual(evidence["checkpoint"], "kb-inspect")

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
        self.assertEqual(gitignore.count("/.obsidian-kb\n"), 1)
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
                (root / relative_path).read_bytes()
                + b"\n<!-- SD-AI-COMMAND-PACK:KB-COPY -->\n",
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
            (root / ".gitignore").read_text(encoding="utf-8").count(
                "/.obsidian-kb\n"
            ),
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
        self.assertEqual(
            copy.read_text(encoding="utf-8"),
            "# Project\n\n<!-- SD-AI-COMMAND-PACK:KB-COPY -->\n",
        )

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
            self.assertEqual(
                copy.read_text(encoding="utf-8"),
                content + "\n<!-- SD-AI-COMMAND-PACK:KB-COPY -->\n",
            )
        self.assertEqual(
            [
                path
                for path in legacy_root.rglob("*")
                if path.is_symlink()
            ],
            [],
        )

    def test_update_spec_kb_preserves_user_file_in_category_folder(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        user_note = root / ".obsidian-kb/Repository Overview/my-notes.md"
        user_note.parent.mkdir(parents=True)
        user_note.write_text("# My private notes\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(
                    install.ROOT
                    / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                ),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            user_note.is_file(),
            "prune deleted a user file the pack never wrote",
        )
        self.assertEqual(
            user_note.read_text(encoding="utf-8"), "# My private notes\n"
        )

    def test_update_spec_kb_preserves_user_file_quoting_copy_marker(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        user_note = root / ".obsidian-kb/Repository Overview/marker-notes.md"
        user_note.parent.mkdir(parents=True)
        # A user note that quotes the marker mid-file must not be treated as
        # pack-owned; only the trailing marker the copier writes proves that.
        note_content = (
            "# Notes\n"
            "The pack marks copies with `<!-- SD-AI-COMMAND-PACK:KB-COPY -->`\n"
            "at the end of each generated file.\n"
        )
        user_note.write_text(note_content, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(
                    install.ROOT
                    / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                ),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            user_note.is_file(),
            "prune deleted a user note that merely quotes the copy marker",
        )
        self.assertEqual(
            user_note.read_text(encoding="utf-8"), note_content
        )

    def test_update_spec_kb_preserves_user_file_behind_root_symlink(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "vault-kb"
            user_note = target / "Architecture and Decisions/notes.md"
            user_note.parent.mkdir(parents=True)
            user_note.write_text("# Vault notes\n", encoding="utf-8")
            kb_root = root / ".obsidian-kb"
            try:
                kb_root.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks are not available: {error}")

            result = subprocess.run(
                [
                    sys.executable,
                    str(
                        install.ROOT
                        / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                    ),
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue(
                user_note.is_file(),
                "prune reached through the root symlink and deleted a vault file",
            )
            self.assertEqual(
                user_note.read_text(encoding="utf-8"), "# Vault notes\n"
            )

    def test_update_spec_kb_prunes_marked_copy_after_source_removed(self) -> None:
        root = self.make_repo()
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
        )
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("# Agent Notes\n", encoding="utf-8")

        first = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(first.returncode, 0, first.stdout)
        orphan = root / ".obsidian-kb/Agent and Platform Guidance/AGENTS.md"
        self.assertTrue(orphan.is_file(), first.stdout)

        (root / "AGENTS.md").unlink()
        second = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertFalse(
            orphan.exists(),
            "orphaned pack copy survived the refresh after its source was removed",
        )
        self.assertTrue(
            (root / ".obsidian-kb/Repository Overview/README.md").is_file()
        )

    def test_update_spec_kb_adopts_pre_marker_copies_and_stays_idempotent(
        self,
    ) -> None:
        root = self.make_repo()
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
        )
        source_content = "# Project\n"
        (root / "README.md").write_text(source_content, encoding="utf-8")
        copy = root / ".obsidian-kb/Repository Overview/README.md"
        copy.parent.mkdir(parents=True)
        # A pre-marker pack copy is byte-identical to its source.
        copy.write_text(source_content, encoding="utf-8")

        first = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(first.returncode, 0, first.stdout)
        adopted = copy.read_text(encoding="utf-8")
        self.assertTrue(adopted.startswith(source_content), adopted)
        self.assertIn("SD-AI-COMMAND-PACK:KB-COPY", adopted)

        before = {
            path: path.stat().st_mtime_ns
            for path in (root / ".obsidian-kb").rglob("*")
            if path.is_file()
        }
        second = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(second.returncode, 0, second.stdout)
        after = {
            path: path.stat().st_mtime_ns
            for path in (root / ".obsidian-kb").rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after, "second refresh rewrote current copies")

        check = subprocess.run(
            [sys.executable, str(script), "--check"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(check.returncode, 0, check.stdout)

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
        self.assertIn("--if-present", result.stdout)
        self.assertFalse((root / ".obsidian-kb").exists())

    def test_update_spec_kb_if_present_skips_absent_kb_without_writes(self) -> None:
        script = install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"

        for mode in ((), ("--dry-run",), ("--check",)):
            with self.subTest(mode=mode or ("refresh",)):
                root = self.make_repo()
                (root / "README.md").write_text("# Project\n", encoding="utf-8")

                result = subprocess.run(
                    [sys.executable, str(script), "--if-present", *mode],
                    cwd=root,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn(
                    "Obsidian KB refresh: skipped (.obsidian-kb is not present)",
                    result.stdout,
                )
                self.assertFalse((root / ".obsidian-kb").exists())
                self.assertFalse((root / ".gitignore").exists())

    def test_update_spec_kb_if_present_refreshes_existing_kb(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".obsidian-kb").mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(
                    install.ROOT
                    / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                ),
                "--if-present",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(
            (root / ".obsidian-kb/Repository Overview/README.md").is_file()
        )
        self.assertIn(
            "# sd-ai-command-pack obsidian-kb start",
            (root / ".gitignore").read_text(encoding="utf-8"),
        )

    def test_update_spec_kb_preserves_root_directory_symlink_and_ignores_it(
        self,
    ) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "vault-kb"
            target.mkdir()
            kb_root = root / ".obsidian-kb"
            try:
                kb_root.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"symlinks are not available: {error}")

            result = subprocess.run(
                [
                    sys.executable,
                    str(
                        install.ROOT
                        / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                    ),
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue(kb_root.is_symlink())
            self.assertTrue((target / "Repository Overview/README.md").is_file())
            ignored = subprocess.run(
                [
                    "git",
                    "-c",
                    f"core.excludesFile={os.devnull}",
                    "check-ignore",
                    "-q",
                    "--",
                    ".obsidian-kb",
                ],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(ignored.returncode, 0, ignored.stdout.decode())
            self.assertIn(
                "/.obsidian-kb\n",
                (root / ".gitignore").read_text(encoding="utf-8"),
            )

    def test_update_spec_kb_root_creation_tolerates_concurrent_directory(
        self,
    ) -> None:
        root = self.make_repo()
        module = self.load_module_from_path(
            install.ROOT
            / "templates/scripts/sd-ai-command-pack-update-spec-kb.py",
            "update_spec_kb_concurrent_root",
        )
        original_mkdir = Path.mkdir

        def concurrent_mkdir(path: Path, *args: object, **kwargs: object) -> None:
            if not path.exists():
                original_mkdir(path, parents=True)
            original_mkdir(path, *args, **kwargs)

        with mock.patch.object(
            Path,
            "mkdir",
            autospec=True,
            side_effect=concurrent_mkdir,
        ):
            kb_root = module.ensure_kb_root(root, create=True)

        self.assertEqual(kb_root, root / ".obsidian-kb")
        self.assertTrue(kb_root.is_dir())

    def test_update_spec_kb_managed_ignore_covers_real_directory(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".obsidian-kb").mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(
                    install.ROOT
                    / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                ),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        ignored = subprocess.run(
            [
                "git",
                "-c",
                f"core.excludesFile={os.devnull}",
                "check-ignore",
                "-q",
                "--",
                ".obsidian-kb",
            ],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0, ignored.stdout.decode())

    def test_update_spec_kb_rejects_invalid_root_paths_before_writes(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
        )
        cases = (
            ("occupied-file", ".obsidian-kb is not a directory"),
            ("broken-symlink", ".obsidian-kb is a broken symlink"),
            (
                "file-symlink",
                ".obsidian-kb symlink target is not a directory",
            ),
        )

        for case, expected in cases:
            for mode in ((), ("--dry-run",), ("--check",)):
                with self.subTest(case=case, mode=mode or ("refresh",)):
                    root = self.make_repo()
                    (root / "README.md").write_text(
                        "# Project\n", encoding="utf-8"
                    )
                    gitignore = root / ".gitignore"
                    gitignore.write_text("dist/\n", encoding="utf-8")
                    kb_root = root / ".obsidian-kb"
                    target = root / "kb-target"

                    if case == "occupied-file":
                        kb_root.write_text("occupied\n", encoding="utf-8")
                    elif case == "broken-symlink":
                        try:
                            kb_root.symlink_to(target, target_is_directory=True)
                        except OSError as error:
                            self.skipTest(f"symlinks are not available: {error}")
                    else:
                        target.write_text("target\n", encoding="utf-8")
                        try:
                            kb_root.symlink_to(target)
                        except OSError as error:
                            self.skipTest(f"symlinks are not available: {error}")

                    result = subprocess.run(
                        [sys.executable, str(script), *mode],
                        cwd=root,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )

                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn(expected, result.stdout)
                    self.assertEqual(
                        gitignore.read_text(encoding="utf-8"), "dist/\n"
                    )
                    if case == "occupied-file":
                        self.assertEqual(
                            kb_root.read_text(encoding="utf-8"), "occupied\n"
                        )
                    elif case == "broken-symlink":
                        self.assertTrue(kb_root.is_symlink())
                        self.assertFalse(target.exists())
                    else:
                        self.assertTrue(kb_root.is_symlink())
                        self.assertEqual(
                            target.read_text(encoding="utf-8"), "target\n"
                        )

    def test_update_spec_kb_if_present_reflects_archive_and_followup_tasks(
        self,
    ) -> None:
        root = self.make_repo()
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
        )
        active_task = root / ".trellis/tasks/07-19-demo"
        active_task.mkdir(parents=True)
        (active_task / "prd.md").write_text("# Demo task\n", encoding="utf-8")
        (root / ".obsidian-kb").mkdir()

        initial = subprocess.run(
            [sys.executable, str(script), "--if-present"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(initial.returncode, 0, initial.stdout)
        active_copy = root / ".obsidian-kb/Task Documentation/07-19-demo-prd.md"
        self.assertTrue(active_copy.is_file())

        archived_task = root / ".trellis/tasks/archive/2026-07/07-19-demo"
        archived_task.parent.mkdir(parents=True)
        shutil.move(active_task, archived_task)
        followup = root / ".trellis/tasks/07-20-follow-up"
        followup.mkdir(parents=True)
        (followup / "prd.md").write_text("# Follow-up task\n", encoding="utf-8")

        refreshed = subprocess.run(
            [sys.executable, str(script), "--if-present"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(refreshed.returncode, 0, refreshed.stdout)
        self.assertFalse(active_copy.exists())
        self.assertTrue(
            (
                root
                / ".obsidian-kb/Task Documentation/"
                "archive-2026-07-07-19-demo-prd.md"
            ).is_file()
        )
        self.assertEqual(
            (
                root
                / ".obsidian-kb/Task Documentation/07-20-follow-up-prd.md"
            ).read_text(encoding="utf-8"),
            "# Follow-up task\n\n<!-- SD-AI-COMMAND-PACK:KB-COPY -->\n",
        )

    def test_update_spec_kb_if_present_does_not_skip_occupied_path(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".obsidian-kb").write_text("occupied\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(
                    install.ROOT
                    / "templates/scripts/sd-ai-command-pack-update-spec-kb.py"
                ),
                "--if-present",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Obsidian KB refresh: skipped", result.stdout)
        self.assertTrue((root / ".obsidian-kb").is_file())

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
        self.assertIn("/.obsidian-kb", exclude_text)
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
        self.assertEqual(gitignore.count("/.obsidian-kb\n"), 1)

    STALE_BANNER_BLOCK = (
        "# sd-ai-command-pack obsidian-kb start\n"
        "# Generated by scripts/sd-ai-command-pack-update-spec-kb.py.\n"
        "# Generated Obsidian KB copy folder; source docs remain in normal "
        "repo paths.\n"
        "/.obsidian-kb\n"
        "# sd-ai-command-pack obsidian-kb end\n"
    )

    def run_kb_helper(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                *args,
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def make_repo_with_stale_ignore_banner(self) -> Path:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        (root / ".gitignore").write_text(
            "dist/\n\n" + self.STALE_BANNER_BLOCK,
            encoding="utf-8",
        )
        return root

    def test_update_spec_kb_leaves_stale_banner_block_untouched(self) -> None:
        """Issue #432: a cosmetic banner change must not dirty a tracked file.

        `sd-housekeeping` refreshes the KB before its merge gates, so rewriting
        a functional block on every consumer at once made the pack's own
        release block its own merge. The block is now rewritten only when it is
        functionally deficient.
        """

        root = self.make_repo_with_stale_ignore_banner()
        before = (root / ".gitignore").read_bytes()

        result = self.run_kb_helper(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: present", result.stdout)
        self.assertEqual((root / ".gitignore").read_bytes(), before)

    def test_update_spec_kb_stale_banner_leaves_git_status_clean(self) -> None:
        """The #432 reproduction, end to end: commit, refresh, status is empty."""

        root = self.make_repo_with_stale_ignore_banner()
        self.run_git(root, "add", ".gitignore")
        self.run_git(root, "commit", "-m", "chore: stale managed ignore block")

        result = self.run_kb_helper(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: present", result.stdout)
        self.assertEqual(
            self.git_output(root, "status", "--porcelain", "--", ".gitignore"),
            "",
        )

    def test_update_spec_kb_repairs_functionally_deficient_block(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        # An entry commented out inside the block does not ignore anything, so
        # the block is deficient even though both markers are present.
        (root / ".gitignore").write_text(
            "dist/\n\n"
            + self.STALE_BANNER_BLOCK.replace(
                "\n/.obsidian-kb\n", "\n#/.obsidian-kb\n"
            ),
            encoding="utf-8",
        )

        result = self.run_kb_helper(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: updated", result.stdout)
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("dist/\n", gitignore)
        self.assertNotIn("#/.obsidian-kb\n", gitignore)
        self.assertEqual(gitignore.count("/.obsidian-kb\n"), 1)

    def test_update_spec_kb_rewrite_flag_restores_byte_exact_block(self) -> None:
        root = self.make_repo_with_stale_ignore_banner()

        result = self.run_kb_helper(root, "--rewrite-ignore-block")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("gitignore: updated", result.stdout)
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("# Generated by sd-ai-command-pack. DO NOT EDIT MANUALLY.\n", gitignore)
        self.assertNotIn(
            "# Generated by scripts/sd-ai-command-pack-update-spec-kb.py.\n",
            gitignore,
        )
        self.assertIn("dist/\n", gitignore)

    def test_update_spec_kb_stale_banner_modes_agree_and_write_nothing(self) -> None:
        """Dry-run, check, and rewrite must promise exactly what a run performs."""

        root = self.make_repo_with_stale_ignore_banner()
        before = (root / ".gitignore").read_bytes()

        dry_run = self.run_kb_helper(root, "--dry-run")
        self.assertEqual(dry_run.returncode, 0, dry_run.stdout)
        self.assertIn("gitignore: would be present", dry_run.stdout)

        # Behaviour change recorded in design.md: cosmetic drift used to fail
        # --check with `ignore entry is not current: updated`, which surfaced as
        # a knowledge.obsidian-kb finding in sd-check. It is no longer a finding.
        check = self.run_kb_helper(root, "--check")
        self.assertIn("gitignore: present", check.stdout)
        self.assertNotIn("ignore entry is not current", check.stdout)

        rewrite_dry_run = self.run_kb_helper(
            root, "--dry-run", "--rewrite-ignore-block"
        )
        self.assertEqual(rewrite_dry_run.returncode, 0, rewrite_dry_run.stdout)
        self.assertIn("gitignore: would be updated", rewrite_dry_run.stdout)

        rewrite_check = self.run_kb_helper(root, "--check", "--rewrite-ignore-block")
        self.assertIn("ignore entry is not current: updated", rewrite_check.stdout)

        self.assertEqual((root / ".gitignore").read_bytes(), before)

    def test_update_spec_kb_deduplicates_entries_around_managed_block(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        managed_block = (
            "# sd-ai-command-pack obsidian-kb start\n"
            "# Generated by sd-ai-command-pack. DO NOT EDIT MANUALLY.\n"
            "# Generated Obsidian KB copy folder; source docs remain in normal "
            "repo paths.\n"
            "/.obsidian-kb\n"
            "# sd-ai-command-pack obsidian-kb end\n"
        )
        (root / ".gitignore").write_text(
            "dist/\n.obsidian-kb/\n\n" + managed_block + "\n/.obsidian-kb/*\nlogs/\n",
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
        self.assertEqual(gitignore.count("/.obsidian-kb\n"), 1)
        self.assertNotIn(".obsidian-kb/\n", gitignore)
        self.assertNotIn("/.obsidian-kb/*\n", gitignore)

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
