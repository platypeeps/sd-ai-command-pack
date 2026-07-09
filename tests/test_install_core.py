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


class InstallCoreTests(InstallTestCase):
    """Tests for installer CLI, manifest validation, platform selection, and file install behavior."""

    def test_install_adds_trellis_gitignore_block(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text("dist/\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = gitignore.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("dist/\n"))
        self.assert_trellis_gitignore_block(content)
        self.assertIn("updated", result.stdout)
        self.assertIn(".gitignore", result.stdout)

    def test_install_replaces_managed_trellis_gitignore_block(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text(
            "dist/\n\n"
            f"{install.TRELLIS_GITIGNORE_START}\n"
            "stale trellis ignore rule\n"
            f"{install.TRELLIS_GITIGNORE_END}\n\n"
            "logs/\n",
            encoding="utf-8",
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = gitignore.read_text(encoding="utf-8")
        self.assertIn("dist/\n", content)
        self.assertIn("logs/\n", content)
        self.assertNotIn("stale trellis ignore rule", content)
        self.assertEqual(content.count(install.TRELLIS_GITIGNORE_START), 1)
        self.assertEqual(content.count(install.TRELLIS_GITIGNORE_END), 1)
        self.assert_trellis_gitignore_block(content)

    def test_install_replaces_blanket_trellis_gitignore_entry(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        gitignore.write_text("dist/\n.trellis/\nlogs/\n", encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = gitignore.read_text(encoding="utf-8")
        self.assertIn("dist/\n", content)
        self.assertIn("logs/\n", content)
        self.assert_trellis_gitignore_block(content)

    def test_trellis_gitignore_dry_run_does_not_write_file(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("created", result.stdout)
        self.assertIn(".gitignore", result.stdout)
        self.assertFalse((root / ".gitignore").exists())

    def test_trellis_gitignore_rejects_incomplete_marker_block(self) -> None:
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_trellis_gitignore_block(
                f"{install.TRELLIS_GITIGNORE_START}\nold\n"
            )

    def test_trellis_gitignore_inserts_after_no_newline_prefix(self) -> None:
        merged = install.merge_trellis_gitignore_block("dist/")

        self.assertTrue(merged.startswith("dist/\n\n"))
        self.assert_trellis_gitignore_block(merged)

    def test_trellis_gitignore_blanket_removal_preserves_blank_only_content(self) -> None:
        self.assertEqual(
            install.remove_unmanaged_trellis_blanket_entries("\n\n"),
            ("\n\n", False),
        )
        self.assertEqual(
            install.remove_unmanaged_trellis_blanket_entries("dist/\n\n.trellis/\n\nlogs/\n"),
            ("dist/\n\n\nlogs/\n", True),
        )

    def test_trellis_gitignore_rejects_existing_directory_target(self) -> None:
        root = self.make_repo()
        (root / ".gitignore").mkdir()

        with self.assertRaisesRegex(SystemExit, "target exists and is not a file"):
            install.install_trellis_gitignore(root, dry_run=False)

    def test_default_install_skips_plain_framework_dirs_without_trellis_markers(
        self,
    ) -> None:
        root = self.make_repo()
        for platform_dir in (
            ".claude",
            ".cursor",
            ".gemini",
            ".github",
            ".opencode",
        ):
            (root / platform_dir).mkdir()

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_installed_targets_snapshot_matches_selection(root)
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-continue.md").exists())
        self.assertFalse((root / ".gemini/commands/sd/continue.toml").exists())
        self.assertFalse((root / ".github/prompts/sd-review-pr.prompt.md").exists())
        self.assertFalse((root / ".github/copilot-instructions.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertIn(
            "active Trellis claude install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis cursor install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis gemini install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis github install not detected",
            result.stdout,
        )
        self.assertIn(
            "active Trellis opencode install not detected",
            result.stdout,
        )

    def test_platform_filter_still_installs_shared_assets(self) -> None:
        root = self.make_repo(".claude", ".cursor", ".gemini", ".github", ".opencode")

        result = self.run_install(root, "--platform", "gemini")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-start/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-backlog/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-designs/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-local-all/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-learnings/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-full-check/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-housekeeping/SKILL.md").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-full-check.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-shell-lib.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-housekeeping.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-scope.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-preflight.mjs").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-local.sh").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-review-learnings.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-pr-body-scope.py").is_file())
        self.assertTrue((root / "scripts/sd-ai-command-pack-update-spec-kb.py").is_file())
        self.assertTrue((root / ".prism/rules.json").is_file())
        self.assertTrue((root / "docs/SD_AI_COMMAND_PACK.md").is_file())
        self.assert_installed_targets_snapshot_matches_selection(
            root,
            platforms=["gemini"],
        )
        self.assertTrue((root / ".gemini/commands/sd/continue.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/start.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/finish-work.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/create-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/work-backlog.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/work-designs.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-pr.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-local-all.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/review-learnings.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/full-check.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/housekeeping.toml").is_file())
        self.assertTrue((root / ".gemini/commands/sd/update-spec.toml").is_file())
        self.assertFalse((root / ".claude/commands/sd/continue.md").exists())
        self.assertFalse((root / ".claude/commands/sd/start.md").exists())
        self.assertFalse((root / ".claude/commands/sd/finish-work.md").exists())
        self.assertFalse((root / ".claude/commands/sd/create-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/work-backlog.md").exists())
        self.assertFalse((root / ".claude/commands/sd/work-designs.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-pr.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-local-all.md").exists())
        self.assertFalse((root / ".claude/commands/sd/review-learnings.md").exists())
        self.assertFalse((root / ".claude/commands/sd/full-check.md").exists())
        self.assertFalse((root / ".claude/commands/sd/housekeeping.md").exists())
        self.assertFalse((root / ".claude/commands/sd/update-spec.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-continue.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-start.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-create-pr.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-work-backlog.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-work-designs.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-local.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-local-all.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".cursor/commands/sd-update-spec.md").exists())
        self.assertFalse((root / ".github/prompts/sd-continue.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-start.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-finish-work.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-create-pr.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-work-backlog.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-work-designs.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-pr.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-local.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-local-all.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-review-learnings.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-full-check.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-housekeeping.prompt.md").exists())
        self.assertFalse((root / ".github/prompts/sd-update-spec.prompt.md").exists())
        self.assertFalse((root / ".github/copilot-instructions.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-continue.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-start.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-finish-work.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-create-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-work-backlog.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-work-designs.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-local-all.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-review-learnings.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-update-spec.md").exists())

    def test_install_merges_copilot_guidance_preserving_existing_instructions(
        self,
    ) -> None:
        root = self.make_repo(".github")
        copilot_instructions = root / ".github/copilot-instructions.md"
        copilot_instructions.write_text(
            "# Repo Copilot Instructions\n\nKeep the product voice sharp.",
            encoding="utf-8",
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = copilot_instructions.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("# Repo Copilot Instructions"))
        self.assertIn("Keep the product voice sharp.", content)
        self.assert_copilot_guidance_block(content)
        self.assertIn("updated", result.stdout)
        self.assertIn(".github/copilot-instructions.md", result.stdout)

    def test_install_updates_existing_managed_copilot_guidance_block(self) -> None:
        root = self.make_repo(".github")
        copilot_instructions = root / ".github/copilot-instructions.md"
        copilot_instructions.write_text(
            "# Repo Copilot Instructions\n\n"
            f"{install.COPILOT_GUIDANCE_START}\n"
            "stale copied-file guidance\n"
            f"{install.COPILOT_GUIDANCE_END}\n\n"
            "Keep this repo-specific footer.\n",
            encoding="utf-8",
        )

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = copilot_instructions.read_text(encoding="utf-8")
        self.assertIn("# Repo Copilot Instructions", content)
        self.assertIn("Keep this repo-specific footer.", content)
        self.assertNotIn("stale copied-file guidance", content)
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_START), 1)
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_END), 1)
        self.assert_copilot_guidance_block(content)

    def test_install_adopts_unmarked_copilot_guidance_into_managed_block(self) -> None:
        # Pre-marker guidance (key phrases present, no managed markers) must be
        # adopted into a marked, upgradable block rather than left stranded as a
        # block that can never be refreshed by future installs.
        root = self.make_repo(".github")
        copilot_instructions = root / ".github/copilot-instructions.md"
        existing = (
            "# Repo Copilot Instructions\n\n"
            "- Ignore copied-in Trellis runtime/platform files unless this "
            "PR changes Trellis integration.\n"
            "- Ignore files copied in from `sd-ai-command-pack` unless this "
            "PR changes the SD review-pack integration.\n"
        )
        copilot_instructions.write_text(existing, encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        content = copilot_instructions.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("# Repo Copilot Instructions"))
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_START), 1)
        self.assertEqual(content.count(install.COPILOT_GUIDANCE_END), 1)
        self.assert_copilot_guidance_block(content)
        self.assertIn("updated", result.stdout)
        self.assertIn(".github/copilot-instructions.md", result.stdout)

        # A second run is now idempotent because the block is marker-tracked.
        second = self.run_install(root)
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(copilot_instructions.read_text(encoding="utf-8"), content)
        self.assertIn("unchanged", second.stdout)

    def test_copilot_guidance_dry_run_does_not_write_instructions(self) -> None:
        root = self.make_repo(".github")

        result = self.run_install(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("created", result.stdout)
        self.assertIn(".github/copilot-instructions.md", result.stdout)
        self.assertFalse((root / ".github/copilot-instructions.md").exists())

    def test_tracked_copilot_guidance_matches_template(self) -> None:
        # The tracked file may carry a repo-specific section outside the
        # managed markers (for example the templates-mirror review guidance),
        # but the managed block itself must match the shipped template exactly.
        installed = (install.ROOT / ".github/copilot-instructions.md").read_text(
            encoding="utf-8"
        )
        template = (
            install.ROOT / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(installed.count(install.COPILOT_GUIDANCE_START), 1)
        self.assertEqual(installed.count(install.COPILOT_GUIDANCE_END), 1)
        self.assertIn(template.strip("\n"), installed)
        self.assertIn("byte-verified mirrors of `templates/**`", installed)
        self.assertRegex(
            installed,
            r"do not repeat\s+the same finding on both copies",
        )

    def test_copilot_block_keeps_scanner_phrases_contiguous(self) -> None:
        # The review-learnings scanner and the guidance-block assertions match
        # these phrases as contiguous substrings; a line-wrap inside one silently
        # breaks both, so pin that they survive as single-line substrings.
        template = (
            install.ROOT / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "current, non-outdated unresolved",
            "stale or outdated review threads",
            "copied or generated",
            "data/access/security boundaries",
        ):
            self.assertIn(phrase, template, f"phrase wrapped or missing: {phrase!r}")

    def test_tracked_full_check_skill_matches_template_and_documents_audit(self) -> None:
        installed = (install.ROOT / ".agents/skills/sd-full-check/SKILL.md").read_text(
            encoding="utf-8"
        )
        template = (
            install.ROOT / "templates/.agents/skills/sd-full-check/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(installed, template)
        for expected in (
            "Structural post-install audit",
            "scripts/sd-ai-command-pack-install-audit.py",
            "SD_AI_COMMAND_PACK_INSTALL_AUDIT=0",
            "SD_AI_COMMAND_PACK_INSTALL_AUDIT=required",
            "post-install audit ran, skipped, or failed",
        ):
            self.assertIn(expected, installed)

    def test_rejects_copilot_instruction_symlink_resolved_outside_repo(
        self,
    ) -> None:
        root = self.make_repo(".github")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "copilot-instructions.md"
        outside_target.write_text("outside\n", encoding="utf-8")
        target = root / ".github/copilot-instructions.md"
        target.symlink_to(outside_target)

        result = self.run_install(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertEqual(outside_target.read_text(encoding="utf-8"), "outside\n")

    def test_backup_path_skips_existing_numbered_backups(self) -> None:
        root = self.make_repo()
        destination = root / ".agents/skills/sd-review-pr/SKILL.md"
        destination.parent.mkdir(parents=True)
        destination.write_text("current\n", encoding="utf-8")
        destination.with_name("SKILL.md.bak").write_text("backup\n", encoding="utf-8")
        destination.with_name("SKILL.md.bak1").write_text(
            "backup 1\n",
            encoding="utf-8",
        )

        backup = install.next_backup_path(root, destination)

        self.assertEqual(backup, destination.with_name("SKILL.md.bak2"))

    def test_managed_block_helpers_reject_invalid_inputs(self) -> None:
        root = self.make_repo(".github")
        invalid_source = root / "invalid-block.md"
        invalid_source.write_text("missing markers\n", encoding="utf-8")
        invalid_file = self.valid_pack_file(
            source=invalid_source,
            target=Path(".github/copilot-instructions.md"),
        )
        managed_source = (
            install.ROOT / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
        )
        unsupported_target = install.PackFile(
            platform="github",
            kind=install.MANAGED_BLOCK_KIND,
            source=managed_source,
            target=Path(".github/unsupported.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )
        directory_target = install.PackFile(
            platform="github",
            kind=install.MANAGED_BLOCK_KIND,
            source=managed_source,
            target=Path(".github/copilot-instructions.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )

        with self.assertRaisesRegex(SystemExit, "missing markers"):
            install.normalize_managed_block_template(invalid_file)
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_managed_block(
                f"{install.COPILOT_GUIDANCE_START}\npartial\n",
                "replacement\n",
            )
        with self.assertRaisesRegex(SystemExit, "unsupported managed block target"):
            install.install_managed_block(
                unsupported_target,
                root,
                dry_run=False,
            )

        destination = root / ".github/copilot-instructions.md"
        destination.mkdir()
        with self.assertRaisesRegex(SystemExit, "target exists and is not a file"):
            install.install_managed_block(directory_target, root, dry_run=False)

    def test_merge_managed_block_inserts_for_empty_and_newline_variants(self) -> None:
        block = (
            f"{install.COPILOT_GUIDANCE_START}\n"
            "managed\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )

        self.assertEqual(install.merge_managed_block("", block), block)
        self.assertEqual(
            install.merge_managed_block("Repo\n", block),
            f"Repo\n\n{block}",
        )
        self.assertEqual(
            install.merge_managed_block("Repo\n\n", block),
            f"Repo\n\n{block}",
        )

    def test_merge_managed_block_rejects_reversed_markers(self) -> None:
        reversed_markers = (
            f"{install.COPILOT_GUIDANCE_END}\nbody\n{install.COPILOT_GUIDANCE_START}\n"
        )
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_managed_block(reversed_markers, "replacement\n")

    def test_managed_block_update_preserves_invalid_existing_bytes(self) -> None:
        root = self.make_repo(".github")
        managed_file = install.PackFile(
            platform="github",
            kind=install.MANAGED_BLOCK_KIND,
            source=(
                install.ROOT
                / "templates/.github/copilot-instructions.sd-ai-command-pack.md"
            ),
            target=Path(".github/copilot-instructions.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )
        destination = root / managed_file.target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"Repo-specific bytes: \xff\n")

        result = install.install_managed_block(managed_file, root, dry_run=False)

        self.assertEqual(result.status, "updated")
        content = destination.read_bytes()
        self.assertIn(b"Repo-specific bytes: \xff\n", content)
        self.assertIn(install.COPILOT_GUIDANCE_START.encode("utf-8"), content)

    def test_install_file_unit_covers_core_status_branches(self) -> None:
        # Exercise the write/conflict/overwrite engine directly so its coverage
        # does not depend solely on the subprocess-coverage mechanism.
        root = self.make_repo()
        source = root / "source.md"
        source.write_text("pack template\n", encoding="utf-8")
        file = self.valid_pack_file(source=source, target=Path("docs/example.md"))
        destination = root / "docs/example.md"

        created = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(created.status, "created")
        self.assertEqual(destination.read_text(encoding="utf-8"), "pack template\n")

        unchanged = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(unchanged.status, "unchanged")

        destination.write_text("local edit\n", encoding="utf-8")
        conflict = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(conflict.status, "conflict")
        self.assertEqual(destination.read_text(encoding="utf-8"), "local edit\n")

        overwritten = install.install_file(
            file, root, force=True, dry_run=False, backup=True
        )
        self.assertEqual(overwritten.status, "overwritten")
        self.assertIsNotNone(overwritten.backup)
        self.assertEqual(destination.read_text(encoding="utf-8"), "pack template\n")
        self.assertEqual(
            overwritten.backup.read_text(encoding="utf-8"), "local edit\n"
        )

    def test_branch_edges_in_block_merges(self) -> None:
        start = install.COPILOT_GUIDANCE_START
        end = install.COPILOT_GUIDANCE_END
        block = f"{start}\nnew body\n{end}\n"
        # Managed block whose END marker sits at EOF without a newline.
        merged = install.merge_managed_block(f"{start}\nold\n{end}", block)
        self.assertEqual(merged, block)

        gi_start = install.TRELLIS_GITIGNORE_START
        gi_end = install.TRELLIS_GITIGNORE_END
        merged = install.merge_trellis_gitignore_block(f"{gi_start}\nold\n{gi_end}")
        self.assertIn(gi_end, merged)
        self.assertNotIn("\nold\n", merged)
        self.assertTrue(merged.startswith(gi_start))
        # Existing gitignore content without a trailing newline.
        merged = install.merge_trellis_gitignore_block("dist/")
        self.assertTrue(merged.startswith("dist/\n\n"))
        merged = install.merge_trellis_gitignore_block("dist/\n\n")
        self.assertTrue(merged.startswith("dist/\n\n"))
        self.assertNotIn("dist/\n\n\n", merged)

        lo_start = install.LOCAL_ONLY_EXCLUDE_START
        lo_end = install.LOCAL_ONLY_EXCLUDE_END
        lo_block = f"{lo_start}\npattern\n{lo_end}\n"
        merged = install.merge_local_only_exclude_block(
            f"{lo_start}\nold\n{lo_end}", lo_block
        )
        self.assertEqual(merged, lo_block)
        merged = install.merge_local_only_exclude_block("existing", lo_block)
        self.assertTrue(merged.startswith("existing\n\n"))
        merged = install.merge_local_only_exclude_block("existing\n\n", lo_block)
        self.assertTrue(merged.startswith("existing\n\n"))
        self.assertNotIn("existing\n\n\n", merged)

        removed = install.remove_marked_block(
            f"keep\n{gi_start}\nold\n{gi_end}",
            start_marker=gi_start,
            end_marker=gi_end,
            label=".gitignore",
        )
        self.assertEqual(removed, "keep\n")

    def test_branch_edges_in_dry_run_updated_paths(self) -> None:
        root = self.make_repo()
        copilot_file = next(
            file
            for file in self._manifest_files
            if file.kind == install.MANAGED_BLOCK_KIND
        )
        destination = root / str(install.COPILOT_INSTRUCTIONS_TARGET)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            f"{install.COPILOT_GUIDANCE_START}\nstale\n"
            f"{install.COPILOT_GUIDANCE_END}\n",
            encoding="utf-8",
        )
        result = install.install_managed_block(copilot_file, root, dry_run=True)
        self.assertEqual(result.status, "updated")
        self.assertIn("stale", destination.read_text(encoding="utf-8"))

        provenance_path = root / str(install.PROVENANCE_FILE)
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text("{}\n", encoding="utf-8")
        result = install.install_provenance_file(
            {"name": "sd-ai-command-pack", "version": "0.0.1"},
            [],
            root,
            receipt_targets=set(),
            never_vouched=set(),
            dry_run=True,
        )
        self.assertEqual(result.status, "updated")
        self.assertEqual(provenance_path.read_text(encoding="utf-8"), "{}\n")

        receipt_path = root / str(install.INSTALLED_TARGETS_FILE)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text("stale-entry\n", encoding="utf-8")
        result = install.install_installed_targets_file([], root, dry_run=True)
        self.assertEqual(result.status, "updated")
        self.assertEqual(receipt_path.read_text(encoding="utf-8"), "stale-entry\n")

    def test_branch_edges_in_misc_helpers(self) -> None:
        self.assertEqual(install.system_exit_detail(SystemExit("boom")), "boom")

        root = self.make_repo()
        receipt_path = root / str(install.INSTALLED_TARGETS_FILE)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text("# comment\n\nreal-entry\n", encoding="utf-8")
        self.assertEqual(
            install.read_existing_installed_targets(root), {"real-entry"}
        )

        absolute_exclude = root / ".git/info/exclude"
        with mock.patch.object(
            install.localonly, "git_output", return_value=str(absolute_exclude)
        ):
            self.assertEqual(install.git_info_exclude_path(root), absolute_exclude)

        self.assertEqual(install.run_diff_check(root), 0)

        drifted = root / "docs/example.md"
        drifted.parent.mkdir(parents=True, exist_ok=True)
        drifted.write_text("drifted\n", encoding="utf-8")
        allowed, detail = install.may_remove_pack_file(
            drifted,
            file=None,
            recorded_hash="sha256:0000",
            force=False,
        )
        self.assertFalse(allowed)
        self.assertEqual(detail, "content differs from installed pack version")

    def test_local_only_init_failure_without_output(self) -> None:
        root = self.make_git_repo_without_trellis()
        failed = subprocess.CompletedProcess(["trellis", "init"], 2, stdout="")
        with mock.patch.object(shutil, "which", return_value="/bin/trellis"):
            with mock.patch.object(subprocess, "run", return_value=failed):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(SystemExit, "trellis init failed"):
                        install.ensure_trellis_for_local_only(
                            root,
                            platforms=[],
                            install_all=False,
                            dry_run=False,
                            skip_trellis_init=False,
                        )
        self.assertEqual(output.getvalue(), "")

    def test_install_applies_umask_derived_modes_and_source_exec_bits(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        current_umask = os.umask(0)
        os.umask(current_umask)
        expected_file_mode = 0o666 & ~current_umask
        expected_exec_mode = 0o777 & ~current_umask

        doc = root / "docs/SD_AI_COMMAND_PACK.md"
        self.assertEqual(doc.stat().st_mode & 0o777, expected_file_mode)

        recorder = root / "scripts/sd-ai-command-pack-record-session.py"
        self.assertEqual(recorder.stat().st_mode & 0o777, expected_exec_mode)
        self.assertTrue(os.access(recorder, os.X_OK))

        receipt = root / ".sd-ai-command-pack/installed-targets.txt"
        self.assertEqual(receipt.stat().st_mode & 0o777, expected_file_mode)

    def test_force_refresh_normalizes_downgraded_file_modes(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        doc = root / "docs/SD_AI_COMMAND_PACK.md"
        original = doc.read_text(encoding="utf-8")
        doc.write_text("tampered\n", encoding="utf-8")
        os.chmod(doc, 0o600)

        result = self.run_install(root, "--force")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(doc.read_text(encoding="utf-8"), original)

        current_umask = os.umask(0)
        os.umask(current_umask)
        self.assertEqual(doc.stat().st_mode & 0o777, 0o666 & ~current_umask)

    def test_install_file_unit_covers_symlink_branches(self) -> None:
        root = self.make_repo()
        source = root / "source.md"
        source.write_text("pack template\n", encoding="utf-8")
        file = self.valid_pack_file(source=source, target=Path("docs/example.md"))
        destination = root / "docs/example.md"

        created = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(created.status, "created")

        # Byte-identical content behind a symlink must not report unchanged:
        # provenance and the audit vouch plain regular files only.
        real_copy = root / "docs/example.real.md"
        destination.rename(real_copy)
        destination.symlink_to("example.real.md")
        self.assertEqual(
            destination.read_bytes(), source.read_bytes(), "fixture must be identical"
        )

        conflict = install.install_file(
            file, root, force=False, dry_run=False, backup=False
        )
        self.assertEqual(conflict.status, "symlink-conflict")
        self.assertTrue(destination.is_symlink())

        dry = install.install_file(file, root, force=True, dry_run=True, backup=False)
        self.assertEqual(dry.status, "overwritten")
        self.assertTrue(
            destination.is_symlink(), "dry-run must not replace the symlink"
        )

        forced = install.install_file(
            file, root, force=True, dry_run=False, backup=True
        )
        self.assertEqual(forced.status, "overwritten")
        self.assertFalse(destination.is_symlink())
        self.assertEqual(destination.read_text(encoding="utf-8"), "pack template\n")

        # Force-preserved targets stay untouched even when symlinked.
        preserved_target = root / ".prism/rules.json"
        preserved_source = root / "preserved-source.json"
        preserved_source.write_text("{}\n", encoding="utf-8")
        preserved_target.parent.mkdir(parents=True, exist_ok=True)
        preserved_real = root / ".prism/rules.real.json"
        preserved_real.write_text("{}\n", encoding="utf-8")
        preserved_target.symlink_to("rules.real.json")
        preserved_file = self.valid_pack_file(
            source=preserved_source, target=Path(".prism/rules.json")
        )
        preserved = install.install_file(
            preserved_file, root, force=True, dry_run=False, backup=False
        )
        self.assertEqual(preserved.status, "preserved")
        self.assertTrue(preserved_target.is_symlink())

    def test_install_symlinked_target_conflicts_then_force_repairs_and_audits(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        doc = root / "docs/SD_AI_COMMAND_PACK.md"
        aside = root / "docs/SD_AI_COMMAND_PACK.real.md"
        doc.rename(aside)
        doc.symlink_to("SD_AI_COMMAND_PACK.real.md")

        result = self.run_install(root)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("symlink-conflict docs/SD_AI_COMMAND_PACK.md", result.stdout)
        self.assertIn(
            "docs/SD_AI_COMMAND_PACK.md "
            "(target is a symlink; the pack installs regular files only)",
            result.stdout,
        )

        result = self.run_install(root, "--force", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overwritten docs/SD_AI_COMMAND_PACK.md", result.stdout)
        self.assertTrue(doc.is_symlink(), "dry-run must not modify the target")

        result = self.run_install(root, "--force")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(doc.is_symlink())
        self.assertEqual(
            doc.read_bytes(),
            (install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md").read_bytes(),
        )

        audit = subprocess.run(
            [sys.executable, "scripts/sd-ai-command-pack-install-audit.py"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(audit.returncode, 0, audit.stdout)

    def test_install_file_preserves_existing_pull_request_template(self) -> None:
        root = self.make_repo(".github")
        file = install.PackFile(
            platform="github",
            kind="doc",
            source=install.ROOT / "templates/.github/PULL_REQUEST_TEMPLATE.md",
            target=Path(".github/PULL_REQUEST_TEMPLATE.md"),
            anchor=Path(".github"),
            install="if-anchor-exists",
        )
        destination = root / ".github/PULL_REQUEST_TEMPLATE.md"
        destination.write_text("## My custom template\n", encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=False
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(
            destination.read_text(encoding="utf-8"), "## My custom template\n"
        )

    def test_pull_request_template_prompts_for_scope_sections(self) -> None:
        template = (
            install.ROOT / "templates/.github/PULL_REQUEST_TEMPLATE.md"
        ).read_text(encoding="utf-8")

        self.assertIn("## Summary", template)
        self.assertIn("## Test plan", template)
        self.assertIn("## Pre-PR checklist", template)
        self.assertIn("Tooling/generated scope:", template)
        self.assertIn("Automation scope:", template)
        self.assertIn("CI/review scope:", template)
        self.assertIn("sd-ai-command-pack-full-check.sh", template)
        self.assertIn("no mutate-before-success", template)
        self.assertIn("push once", template)
        # An unedited template body must NOT satisfy the pr-body scope check, or
        # every PR would auto-pass. Assert against the real matcher rather than a
        # hand-rolled line check, so this cannot drift from _body_has_heading()
        # (which also matches headings behind Markdown markers like "- "/"> ").
        scope_check = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_pr_body_scope_template_guard",
        )
        for heading in (
            "Tooling/generated scope:",
            "Automation scope:",
            "CI/review scope:",
        ):
            self.assertFalse(
                scope_check._body_has_heading(template, (heading,)),
                f"template body must not satisfy the scope check for {heading!r}",
            )

    def test_install_file_preserves_if_not_exists_targets(self) -> None:
        root = self.make_repo()
        source = root / "source.json"
        source.write_text('{"pack": true}\n', encoding="utf-8")
        file = self.valid_pack_file(
            source=source,
            target=Path(".custom/config.json"),
        )
        file = install.PackFile(
            platform=file.platform,
            kind=file.kind,
            source=file.source,
            target=file.target,
            anchor=file.anchor,
            install=install.IF_NOT_EXISTS,
        )
        destination = root / ".custom/config.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"local": true}\n', encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=True
        )

        self.assertEqual(result.status, "preserved")
        self.assertIsNone(result.backup)
        self.assertEqual(destination.read_text(encoding="utf-8"), '{"local": true}\n')

    def test_load_manifest_reports_missing_manifest_cleanly(self) -> None:
        with mock.patch.object(install.manifest, "MANIFEST_PATH", PACK_ROOT / "missing-manifest.json"):
            with self.assertRaisesRegex(SystemExit, "manifest not found"):
                install.load_manifest()

    def test_installer_help_and_version_exit_cleanly(self) -> None:
        manifest, _ = install.load_manifest()
        cases = [
            (
                ["--help"],
                [
                    "usage:",
                    "--version",
                    "--remove",
                    "--platform",
                    "--local-only",
                ],
            ),
            (
                ["--version"],
                [f"{manifest['name']} {manifest['version']}"],
            ),
        ]

        for args, expected_texts in cases:
            with self.subTest(args=args):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                    stderr
                ):
                    with self.assertRaises(SystemExit) as raised:
                        install.parse_args(args)

                self.assertEqual(raised.exception.code, 0)
                output = stdout.getvalue() + stderr.getvalue()
                for expected in expected_texts:
                    self.assertIn(expected, output)
                if args == ["--version"]:
                    self.assertIn(
                        f"{manifest['name']} {manifest['version']}",
                        stdout.getvalue(),
                    )
                    self.assertEqual(stderr.getvalue(), "")

    def test_load_manifest_rejects_malformed_manifests(self) -> None:
        fixtures = Path(tempfile.mkdtemp(prefix="sd-manifest-fixtures-"))
        self.addCleanup(shutil.rmtree, fixtures, True)
        cases = [
            ("{not json", "manifest is not valid JSON"),
            ('{"schemaVersion": 2, "files": []}', "schemaVersion 2 is newer"),
            (
                '{"schemaVersion": "1", "files": []}',
                "schemaVersion must be an integer",
            ),
            (
                '{"schemaVersion": true, "files": []}',
                "schemaVersion must be an integer",
            ),
            (
                '{"files": [{"kind": "doc", "source": "docs/x.md",'
                ' "target": "docs/x.md"}]}',
                "missing required field 'platform'",
            ),
            ('{"files": ["not-an-object"]}', r"files\[0\] must be an object"),
            ("[]", "manifest must be a JSON object"),
            (
                '{"requiresTrellis": "yes", "files": []}',
                "requiresTrellis must be a boolean",
            ),
            ('{"files": null}', "'files' must be an array"),
        ]
        for index, (content, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                manifest_path = fixtures / f"manifest-{index}.json"
                manifest_path.write_text(content, encoding="utf-8")
                with mock.patch.object(
                    install.manifest, "MANIFEST_PATH", manifest_path
                ):
                    with self.assertRaisesRegex(SystemExit, expected):
                        install.load_manifest()

    def test_validate_manifest_rejects_unknown_kind(self) -> None:
        file = install.PackFile(
            platform="shared",
            kind="managed_block",
            source=install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
            target=Path("docs/example.md"),
            anchor=None,
            install="always",
        )
        with self.assertRaisesRegex(
            SystemExit, "unknown kind 'managed_block' in manifest"
        ):
            install.validate_manifest([file])

    def test_install_skips_trellis_requirement_when_manifest_opts_out(self) -> None:
        fixtures = Path(tempfile.mkdtemp(prefix="sd-manifest-opt-out-"))
        self.addCleanup(shutil.rmtree, fixtures, True)
        manifest_path = fixtures / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "name": "sd-ai-command-pack",
                    "version": "0.0.1",
                    "requiresTrellis": False,
                    "files": [],
                }
            ),
            encoding="utf-8",
        )
        plain_dir = Path(tempfile.mkdtemp(prefix="sd-plain-target-"))
        self.addCleanup(shutil.rmtree, plain_dir, True)

        output = io.StringIO()
        with mock.patch.object(install.manifest, "MANIFEST_PATH", manifest_path):
            with contextlib.redirect_stdout(output):
                result = install.main([str(plain_dir), "--skip-diff-check"])

        self.assertEqual(result, 0, output.getvalue())
        self.assertFalse((plain_dir / ".trellis").exists())

    def test_manifest_cli_identity_reports_malformed_identity(self) -> None:
        root = self.make_repo()
        manifest_path = root / "manifest.json"
        cases = [
            ("not json\n", "manifest is not valid JSON"),
            (json.dumps({"version": "1.2.3"}) + "\n", "manifest name is missing"),
            (json.dumps({"name": "pack"}) + "\n", "manifest version is missing"),
        ]

        for content, expected in cases:
            with self.subTest(expected=expected):
                manifest_path.write_text(content, encoding="utf-8")
                with mock.patch.object(install.manifest, "MANIFEST_PATH", manifest_path):
                    with self.assertRaisesRegex(SystemExit, expected):
                        install.manifest_cli_identity()

    def test_require_target_directory_reports_missing_target(self) -> None:
        root = self.make_repo()

        with self.assertRaisesRegex(SystemExit, "target repo not found"):
            install.require_target_directory(root / "missing")

    def test_install_gitignore_rejects_invalid_utf8(self) -> None:
        root = self.make_repo()
        (root / ".gitignore").write_bytes(b"dist-\xff/\n")

        with self.assertRaisesRegex(SystemExit, "not valid UTF-8"):
            install.install_trellis_gitignore(root, dry_run=False)

    def test_read_text_helpers_report_decode_and_os_errors(self) -> None:
        root = self.make_repo()
        invalid = root / "invalid.txt"
        invalid.write_bytes(b"not utf-8: \xff\n")

        with self.assertRaisesRegex(SystemExit, "strict label is not valid UTF-8"):
            install.read_text_strict(invalid, "strict label")
        with mock.patch.object(Path, "read_text", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(SystemExit, "cannot read strict label"):
                install.read_text_strict(root / "blocked.txt", "strict label")
            with self.assertRaisesRegex(SystemExit, "cannot read optional label"):
                install.read_text_if_exists(root / "blocked.txt", "optional label")

    def test_atomic_write_failure_reports_and_cleans_temp_file(self) -> None:
        root = self.make_repo()
        destination = root / "out.txt"

        with mock.patch.object(install.os, "replace", side_effect=OSError("blocked")):
            with mock.patch.object(Path, "unlink", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(SystemExit, "cannot write"):
                    install.atomic_write_bytes(destination, b"content\n")

    def test_managed_block_rejects_duplicate_markers(self) -> None:
        block = (
            f"{install.COPILOT_GUIDANCE_START}\n"
            "pack block\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )
        current = (
            f"{install.COPILOT_GUIDANCE_START}\nold\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
            f"{install.COPILOT_GUIDANCE_START}\nolder\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )

        with self.assertRaisesRegex(SystemExit, "duplicate"):
            install.merge_managed_block(current, block)

        duplicate_end = (
            f"{install.COPILOT_GUIDANCE_START}\nold\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
            f"{install.COPILOT_GUIDANCE_END}\n"
        )

        with self.assertRaisesRegex(SystemExit, "duplicate sd-ai-command-pack end"):
            install.merge_managed_block(duplicate_end, block)

    def test_subprocess_coverage_bootstrap_is_wired(self) -> None:
        # The 100% coverage gate depends on this bootstrap being present and on
        # parallel/fail-under settings; assert them so a silent break is caught.
        sitecustomize = PACK_ROOT / "tests/coverage_sitecustomize/sitecustomize.py"
        self.assertTrue(sitecustomize.is_file())
        self.assertIn(
            'getattr(coverage, "process_startup", None)',
            sitecustomize.read_text(encoding="utf-8"),
        )
        coveragerc = (PACK_ROOT / ".coveragerc").read_text(encoding="utf-8")
        self.assertIn("parallel = True", coveragerc)
        self.assertIn("fail_under = 100", coveragerc)

    def test_main_diff_check_excludes_preserved_targets(self) -> None:
        root = self.make_repo()
        prism = root / ".prism/rules.json"
        prism.parent.mkdir(parents=True)
        prism.write_text('{"local": true}\n', encoding="utf-8")
        captured: dict[str, object] = {}

        def fake_diff_check(target: Path, paths: list[Path] | None = None) -> int:
            captured["paths"] = paths
            return 0

        with mock.patch.object(install, "run_diff_check", fake_diff_check):
            code = install.main([str(root)])

        self.assertEqual(code, 0)
        paths = captured.get("paths")
        self.assertIsInstance(paths, list)
        self.assertNotIn(Path(".prism/rules.json"), paths)
        self.assertIn(install.INSTALLED_TARGETS_FILE, paths)

    def test_manifest_declares_trellis_requirement(self) -> None:
        raw, _ = install.load_manifest()

        self.assertIs(raw.get("requiresTrellis"), True)
        self.assertIn("Trellis", raw["description"])

    def test_platform_registry_derives_consistent_tables(self) -> None:
        registry = install.PLATFORM_REGISTRY
        self.assertEqual(install.PLATFORMS, tuple(sorted(registry)))

        _, files = install.load_manifest()
        platforms_with_files = {
            file.platform for file in files if file.platform != "shared"
        }
        for platform in sorted(platforms_with_files):
            info = registry[platform]
            self.assertTrue(
                info.markers, f"{platform} has manifest files but no markers"
            )
            self.assertTrue(
                info.init_flag, f"{platform} has manifest files but no init flag"
            )
        # Markers must be owned by the platform's own directory so an
        # unrelated platform's install can never activate this one (the
        # zcode-via-codex regression).
        for platform, info in registry.items():
            for marker in info.markers:
                self.assertTrue(
                    marker.startswith(f"{info.directory}/"),
                    f"{platform} marker {marker} is outside {info.directory}/",
                )

        derived_checks = install.LOCAL_ONLY_TRACKED_CHECK_PATHS
        self.assertEqual(derived_checks[0], "AGENTS.md")
        self.assertEqual(derived_checks[1], ".trellis")
        self.assertFalse(
            [path for path in derived_checks if path.endswith("/")],
            "tracked-check paths must not keep exclude-form trailing slashes",
        )

        gitignore = install.PLATFORM_LOCAL_GITIGNORE_PATTERNS
        self.assertEqual(gitignore[-1], "node_modules/")
        claude_ignore = gitignore.index(".claude/**")
        self.assertEqual(gitignore[claude_ignore + 1], "!.claude/commands/")

        # A registry row's entries must actually reach the derived tables:
        # any platform carrying gitignore or local-only data has to hold a
        # slot in the byte-stability order tuples.
        for platform, info in registry.items():
            if info.local_gitignore_patterns:
                self.assertIn(
                    platform,
                    install._LOCAL_GITIGNORE_GROUP_ORDER,
                    f"{platform} gitignore group missing from group order",
                )
            if info.trellis_local_only:
                self.assertIn(
                    platform,
                    install._LOCAL_ONLY_GROUP_ORDER,
                    f"{platform} local-only group missing from group order",
                )

    def test_platform_registry_dirs_covered_by_shipped_scanners(self) -> None:
        audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_registry_coverage",
        )
        scope_script = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_pr_body_scope_registry_coverage",
        )
        review_scope_text = (
            install.ROOT / "scripts/sd-ai-command-pack-review-scope.sh"
        ).read_text(encoding="utf-8")
        scope_patterns = {
            pattern
            for rule in scope_script.DEFAULT_RULES
            for pattern in rule.patterns
        }
        _, files = install.load_manifest()
        platforms_with_files = {
            file.platform for file in files if file.platform != "shared"
        }

        for platform, info in sorted(install.PLATFORM_REGISTRY.items()):
            directory = info.directory
            self.assertIn(
                directory,
                audit.REFERENCE_SCAN_BASES,
                f"{directory} missing from audit REFERENCE_SCAN_BASES",
            )
            # Every Trellis-owned local-only path must be classified as
            # Trellis runtime by review-scope — including platforms with no
            # pack adapter files (e.g. codex config/hook paths).
            for entry in info.trellis_local_only:
                expected = entry + "*" if entry.endswith("/") else entry
                self.assertIn(
                    expected,
                    review_scope_text,
                    f"{platform} runtime path {entry} missing from "
                    "review-scope is_trellis_runtime_path",
                )
            if platform not in platforms_with_files:
                continue
            self.assertTrue(
                any(
                    pattern.startswith(f"{directory}/")
                    for pattern in audit.PACK_FILE_PATTERNS
                ),
                f"{directory} has adapter files but no audit PACK_FILE_PATTERNS",
            )
            self.assertTrue(
                any(pattern.startswith(f"{directory}/") for pattern in scope_patterns),
                f"{directory} missing from pr-body-scope DEFAULT_RULES",
            )

    def test_zcode_requires_zcode_owned_markers(self) -> None:
        root = self.make_repo()
        (root / ".zcode").mkdir()
        codex_marker = root / ".agents/skills/trellis-before-dev/SKILL.md"
        codex_marker.parent.mkdir(parents=True, exist_ok=True)
        codex_marker.write_text("# codex install artifact\n", encoding="utf-8")

        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((root / ".zcode/commands/sd/start.md").exists())
        self.assertIn(
            "hint: .zcode/ exists but no active Trellis zcode install was "
            "detected; pass --platform zcode or update Trellis",
            result.stdout,
        )

        zcode_marker = root / ".zcode/cli/agents/trellis-check.md"
        zcode_marker.parent.mkdir(parents=True, exist_ok=True)
        zcode_marker.write_text("# zcode trellis agent\n", encoding="utf-8")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".zcode/commands/sd/start.md").is_file())

    def test_entry_script_runs_via_symlink(self) -> None:
        link_dir = Path(tempfile.mkdtemp(prefix="sd-install-symlink-"))
        self.addCleanup(shutil.rmtree, link_dir, True)
        link = link_dir / "install.py"
        link.symlink_to(INSTALLER)

        result = subprocess.run(
            [sys.executable, str(link), "--version"],
            env=self.installer_subprocess_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack", result.stdout)

    def test_install_prints_platform_note_for_manifest_less_platform(self) -> None:
        root = self.make_repo()
        result = self.run_install(root, "--platform", "codex")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "note: platform codex has no dedicated manifest files; "
            "its commands are provided by the shared .agents skills",
            result.stdout,
        )

    def test_conflict_requires_force(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflict", result.stdout)
        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")

        forced = self.run_install(root, "--force")
        self.assertEqual(forced.returncode, 0, forced.stdout)
        self.assertIn("SD PR Review Loop", target.read_text(encoding="utf-8"))

    def test_force_backup_preserves_overwritten_file(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("backup", result.stdout)
        self.assertEqual(
            (root / ".agents/skills/sd-review-pr/SKILL.md.bak").read_text(
                encoding="utf-8"
            ),
            "local edit\n",
        )
        self.assertIn("SD PR Review Loop", target.read_text(encoding="utf-8"))

    def test_install_file_reports_backup_copy_failures_cleanly(self) -> None:
        root = self.make_repo(".gemini")
        file = self.valid_pack_file()
        target = root / file.target
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        with mock.patch.object(
            install.shutil,
            "copyfile",
            side_effect=OSError("blocked backup"),
        ):
            with self.assertRaisesRegex(
                SystemExit,
                "cannot create backup.*blocked backup",
            ):
                install.install_file(
                    file,
                    root,
                    force=True,
                    dry_run=False,
                    backup=True,
                )

        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")
        self.assertFalse(target.with_name("SKILL.md.bak").exists())

    def test_dry_run_force_backup_does_not_report_or_write_backup(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")

        result = self.run_install(root, "--dry-run", "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overwritten", result.stdout)
        self.assertNotIn("backup", result.stdout)
        self.assertFalse(
            (root / ".agents/skills/sd-review-pr/SKILL.md.bak").exists()
        )
        self.assertEqual(target.read_text(encoding="utf-8"), "local edit\n")

    def test_force_backup_does_not_write_through_existing_backup_symlink(self) -> None:
        root = self.make_repo(".gemini")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_backup = Path(outside_tempdir.name) / "outside-backup"
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")
        target.with_name("SKILL.md.bak").symlink_to(outside_backup)

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("SKILL.md.bak1", result.stdout)
        self.assertEqual(
            target.with_name("SKILL.md.bak1").read_text(encoding="utf-8"),
            "local edit\n",
        )
        self.assertFalse(outside_backup.exists())

    def test_backup_requires_force(self) -> None:
        root = self.make_repo(".gemini")

        result = self.run_install(root, "--backup")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "--backup requires --force unless --remove is set",
            result.stdout,
        )
        self.assertNotIn("Traceback", result.stdout)

    def test_dry_run_does_not_write_files(self) -> None:
        root = self.make_repo(".opencode")

        result = self.run_install(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertFalse((root / ".agents/skills/sd-review-pr/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-create-pr/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-work-backlog/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-work-designs/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-full-check/SKILL.md").exists())
        self.assertFalse((root / ".agents/skills/sd-housekeeping/SKILL.md").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-full-check.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-housekeeping.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-review-scope.sh").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-review-preflight.mjs").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-pr-body-scope.py").exists())
        self.assertFalse((root / "scripts/sd-ai-command-pack-update-spec-kb.py").exists())
        self.assertFalse((root / ".prism/rules.json").exists())
        self.assertFalse((root / "docs/SD_AI_COMMAND_PACK.md").exists())
        self.assertFalse((root / install.INSTALLED_TARGETS_FILE).exists())
        self.assertIn(".sd-ai-command-pack/installed-targets.txt", result.stdout)
        self.assertFalse((root / ".opencode/commands/sd-review-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-create-pr.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-work-backlog.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-work-designs.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-full-check.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-housekeeping.md").exists())
        self.assertFalse((root / ".opencode/commands/sd-update-spec.md").exists())
        self.assertFalse((root / ".github/copilot-instructions.md").exists())

    def test_rejects_non_trellis_repo(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name)

        result = self.run_install(target)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".trellis/config.yaml not found", result.stdout)
        self.assertIn("trellis init", result.stdout)
        self.assertIn(install.TRELLIS_INSTALL_DOCS_URL, result.stdout)
        for unexpected in (
            ".agents",
            ".sd-ai-command-pack",
            ".prism",
            "docs",
            "scripts",
            ".github",
            ".claude",
            ".cursor",
            ".gemini",
            ".opencode",
        ):
            self.assertFalse((target / unexpected).exists(), unexpected)

    def test_local_only_bootstraps_trellis_and_excludes_generated_files(self) -> None:
        root = self.make_git_repo_without_trellis()
        (root / ".gitignore").write_text("dist/\n", encoding="utf-8")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".gitignore")
        self.run_git(root, "commit", "-m", "baseline")
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        bin_dir = Path(tools_tempdir.name) / "bin"
        trellis_log = Path(tools_tempdir.name) / "trellis-args.log"
        self.write_trellis_stub(bin_dir, trellis_log)

        result = self.run_install(
            root,
            "--local-only",
            "--platform",
            "cursor",
            extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: local-only", result.stdout)
        self.assertIn("initialized-trellis-local", result.stdout)
        self.assertIn("local-exclude", result.stdout)
        self.assertIn("local-only-marker-written", result.stdout)
        self.assertTrue((root / ".trellis/config.yaml").is_file())
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-create-pr/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-backlog/SKILL.md").is_file())
        self.assertTrue((root / ".agents/skills/sd-work-designs/SKILL.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-review-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-create-pr.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-work-backlog.md").is_file())
        self.assertTrue((root / ".cursor/commands/sd-work-designs.md").is_file())
        self.assertEqual(
            trellis_log.read_text(encoding="utf-8").strip(),
            "init --yes --skip-existing --codex --cursor",
        )

        exclude = Path(
            self.git_output(root, "rev-parse", "--git-path", "info/exclude")
        )
        if not exclude.is_absolute():
            exclude = root / exclude
        exclude_text = exclude.read_text(encoding="utf-8")
        for expected in (
            install.LOCAL_ONLY_EXCLUDE_START,
            "AGENTS.md",
            ".trellis/",
            ".agents/skills/sd-review-pr/SKILL.md",
            ".agents/skills/sd-create-pr/SKILL.md",
            ".agents/skills/sd-work-backlog/SKILL.md",
            ".agents/skills/sd-work-designs/SKILL.md",
            ".codex/config.toml",
            ".codex/hooks/",
            ".cursor/agents/trellis-*.md",
            ".cursor/commands/sd-review-pr.md",
            ".cursor/commands/sd-create-pr.md",
            ".cursor/commands/sd-work-backlog.md",
            ".cursor/commands/sd-work-designs.md",
            "scripts/sd-ai-command-pack-full-check.sh",
            ".sd-ai-command-pack/",
            ".obsidian-kb/",
            install.LOCAL_ONLY_EXCLUDE_END,
        ):
            self.assertIn(expected, exclude_text)
        self.assertEqual((root / ".gitignore").read_text(encoding="utf-8"), "dist/\n")
        self.assertTrue((root / install.LOCAL_ONLY_MARKER_FILE).is_file())
        self.assertEqual(self.git_output(root, "status", "--short"), "")

    def test_local_only_dry_run_does_not_init_trellis_or_write_exclude(self) -> None:
        root = self.make_git_repo_without_trellis()
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        bin_dir = Path(tools_tempdir.name) / "bin"
        trellis_log = Path(tools_tempdir.name) / "trellis-args.log"
        self.write_trellis_stub(bin_dir, trellis_log)

        result = self.run_install(
            root,
            "--local-only",
            "--dry-run",
            "--platform",
            "gemini",
            extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("mode: dry-run", result.stdout)
        self.assertIn("mode: local-only", result.stdout)
        self.assertIn("would-init-trellis-local", result.stdout)
        self.assertIn("would-update-local-exclude", result.stdout)
        self.assertIn("would-write-local-only-marker", result.stdout)
        self.assertFalse((root / ".trellis/config.yaml").exists())
        self.assertFalse(trellis_log.exists())
        self.assertFalse((root / install.LOCAL_ONLY_MARKER_FILE).exists())

    def test_local_only_reports_existing_trellis_without_bootstrap(self) -> None:
        root = self.make_repo()

        result = install.ensure_trellis_for_local_only(
            root,
            platforms=None,
            install_all=False,
            dry_run=False,
            skip_trellis_init=False,
        )

        self.assertEqual(result.status, "trellis-present")
        self.assertEqual(result.target, Path(".trellis/config.yaml"))

    def test_local_only_rejects_tracked_framework_paths(self) -> None:
        root = self.make_repo()
        (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
        codex_config = root / ".codex/config.toml"
        codex_config.parent.mkdir(parents=True, exist_ok=True)
        codex_config.write_text("hooks = true\n", encoding="utf-8")
        self.run_git(
            root,
            "add",
            ".trellis/config.yaml",
            "AGENTS.md",
            ".codex/config.toml",
        )

        result = self.run_install(root, "--local-only")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("already tracked", result.stdout)
        self.assertIn(".trellis/config.yaml", result.stdout)
        self.assertIn("AGENTS.md", result.stdout)
        self.assertIn(".codex/config.toml", result.stdout)

    def test_local_only_rejects_tracked_paths_before_bootstrap(self) -> None:
        root = self.make_git_repo_without_trellis()
        (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
        pack_script = root / "scripts/sd-ai-command-pack-full-check.sh"
        pack_script.parent.mkdir(parents=True)
        pack_script.write_text("#!/bin/sh\n", encoding="utf-8")
        self.run_git(root, "add", "AGENTS.md", "scripts/sd-ai-command-pack-full-check.sh")
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        bin_dir = Path(tools_tempdir.name) / "bin"
        trellis_log = Path(tools_tempdir.name) / "trellis-args.log"
        self.write_trellis_stub(bin_dir, trellis_log)

        result = self.run_install(
            root,
            "--local-only",
            "--platform",
            "cursor",
            extra_env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("already tracked", result.stdout)
        self.assertIn("AGENTS.md", result.stdout)
        self.assertIn("scripts/sd-ai-command-pack-full-check.sh", result.stdout)
        self.assertFalse(trellis_log.exists())
        for unexpected in (
            ".trellis",
            ".agents",
            ".codex",
            ".cursor",
            ".sd-ai-command-pack",
        ):
            self.assertFalse((root / unexpected).exists(), unexpected)

    def test_local_only_requires_git_repo(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name)

        result = self.run_install(target, "--local-only")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "failed to verify --local-only target Git repository",
            result.stdout,
        )
        self.assertIn("not a git repository", result.stdout)

    def test_local_only_skip_trellis_init_requires_existing_trellis(self) -> None:
        root = self.make_git_repo_without_trellis()

        result = self.run_install(root, "--local-only", "--skip-trellis-init")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(".trellis/config.yaml not found", result.stdout)

    def test_local_only_reports_missing_trellis_command(self) -> None:
        root = self.make_git_repo_without_trellis()
        tools_tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-tools-")
        self.addCleanup(tools_tempdir.cleanup)
        bin_dir = Path(tools_tempdir.name) / "bin"
        bin_dir.mkdir()
        git_path = shutil.which("git")
        self.assertIsNotNone(git_path)
        (bin_dir / "git").write_text(
            "#!/bin/sh\n"
            f"exec {git_path!r} \"$@\"\n",
            encoding="utf-8",
        )
        (bin_dir / "git").chmod(0o755)

        result = self.run_install(
            root,
            "--local-only",
            extra_env={"PATH": str(bin_dir)},
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("needs `trellis` on PATH", result.stdout)

    def test_skip_trellis_init_requires_local_only(self) -> None:
        root = self.make_repo()

        result = self.run_install(root, "--skip-trellis-init")

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("--skip-trellis-init requires --local-only", result.stdout)

    def test_local_only_git_helpers_handle_errors(self) -> None:
        root = self.make_git_repo_without_trellis()
        subdir = root / "nested"
        subdir.mkdir()

        with self.assertRaisesRegex(SystemExit, "Git repo root"):
            install.require_git_repo_for_local_only(subdir)

        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError):
            self.assertIsNone(install.git_output(root, "status"))
            with self.assertRaisesRegex(SystemExit, "git is required"):
                install.git_output(
                    root,
                    "status",
                    required=True,
                    context="check status",
                )
            with self.assertRaisesRegex(SystemExit, "git is required"):
                install.tracked_paths(root, ["anything"])

        failed_git = subprocess.CompletedProcess(
            ["git", "status"],
            1,
            stdout="fatal: nope\n",
        )
        with mock.patch.object(subprocess, "run", return_value=failed_git):
            self.assertIsNone(install.git_output(root, "status"))

        with mock.patch.object(install.localonly, "git_output", return_value=None):
            with self.assertRaisesRegex(SystemExit, "requires the target to be a Git repo"):
                install.require_git_repo_for_local_only(root)

        with mock.patch.object(install.localonly, "git_output", return_value=str(root)):
            with mock.patch.object(Path, "resolve", side_effect=OSError("boom")):
                with self.assertRaisesRegex(SystemExit, "cannot resolve target repo"):
                    install.require_git_repo_for_local_only(root)

        with mock.patch.object(install.localonly, "git_output", return_value=None):
            with self.assertRaisesRegex(SystemExit, "cannot find .git/info/exclude"):
                install.git_info_exclude_path(root)

        self.assertEqual(install.tracked_paths(root, []), [])
        failed = subprocess.CompletedProcess(
            ["git", "ls-files"],
            1,
            stdout="fatal: bad pathspec\n",
        )
        with mock.patch.object(subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(SystemExit, "git ls-files failed"):
                install.tracked_paths(root, ["bad"])

    def test_local_only_trellis_init_error_paths(self) -> None:
        root = self.make_git_repo_without_trellis()

        self.assertEqual(
            install.trellis_init_platforms(["cursor"], install_all=True),
            sorted(install.TRELLIS_INIT_PLATFORM_FLAGS),
        )

        failed = subprocess.CompletedProcess(
            ["trellis", "init"],
            2,
            stdout="trellis exploded\n",
        )
        with mock.patch.object(shutil, "which", return_value="/bin/trellis"):
            with mock.patch.object(subprocess, "run", return_value=failed):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(SystemExit, "trellis init failed"):
                        install.ensure_trellis_for_local_only(
                            root,
                            platforms=[],
                            install_all=False,
                            dry_run=False,
                            skip_trellis_init=False,
                        )
                self.assertEqual(output.getvalue(), "trellis exploded\n")

        succeeded_without_config = subprocess.CompletedProcess(
            ["trellis", "init"],
            0,
            stdout="",
        )
        with mock.patch.object(shutil, "which", return_value="/bin/trellis"):
            with mock.patch.object(
                subprocess,
                "run",
                return_value=succeeded_without_config,
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "trellis init completed",
                ):
                    install.ensure_trellis_for_local_only(
                        root,
                        platforms=[],
                        install_all=False,
                        dry_run=False,
                        skip_trellis_init=False,
                    )

    def test_local_only_tracking_rejection_reports_overflow(self) -> None:
        root = self.make_git_repo_without_trellis()
        tracked = [f"path-{index}.txt" for index in range(22)]

        with mock.patch.object(install.localonly, "tracked_paths", return_value=tracked):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(SystemExit, "Remove these paths"):
                    install.reject_tracked_local_only_paths(root, [])

        self.assertIn("path-0.txt", output.getvalue())
        self.assertIn("2 more", output.getvalue())

    def test_local_only_exclude_block_edge_cases(self) -> None:
        block = install.local_only_exclude_block(["one/"])

        with self.assertRaisesRegex(SystemExit, "incomplete"):
            install.merge_local_only_exclude_block(
                f"{install.LOCAL_ONLY_EXCLUDE_START}\none/\n",
                block,
            )

        current = (
            "before\n"
            f"{install.LOCAL_ONLY_EXCLUDE_START}\n"
            "old/\n"
            f"{install.LOCAL_ONLY_EXCLUDE_END}\n"
            "after\n"
        )
        self.assertEqual(
            install.merge_local_only_exclude_block(current, block),
            f"before\n{block}after\n",
        )
        self.assertEqual(install.merge_local_only_exclude_block("", block), block)
        self.assertEqual(
            install.merge_local_only_exclude_block("manual", block),
            f"manual\n\n{block}",
        )

    def test_local_only_exclude_and_marker_are_idempotent(self) -> None:
        root = self.make_git_repo_without_trellis()

        install.ensure_local_only_exclude(root, [], dry_run=False)
        exclude_result = install.ensure_local_only_exclude(root, [], dry_run=False)
        self.assertEqual(exclude_result.status, "local-exclude-unchanged")

        install.write_local_only_marker(root, dry_run=False)
        marker_result = install.write_local_only_marker(root, dry_run=False)
        self.assertEqual(marker_result.status, "local-only-marker-unchanged")

    def test_rejects_target_path_resolved_outside_repo(self) -> None:
        root = self.make_repo()
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside = Path(outside_tempdir.name)
        (root / ".agents").symlink_to(outside, target_is_directory=True)

        result = self.run_install(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertFalse((outside / "skills/sd-review-pr/SKILL.md").exists())

    def test_rejects_existing_target_symlink_resolved_outside_repo(self) -> None:
        root = self.make_repo(".gemini")
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(outside_tempdir.cleanup)
        outside_target = Path(outside_tempdir.name) / "outside-target"
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        target.symlink_to(outside_target)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target path resolves outside target repo", result.stdout)
        self.assertFalse(outside_target.exists())

    def test_rejects_existing_target_directory(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.mkdir(parents=True)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target exists and is not a file", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_rejects_existing_broken_target_symlink(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        target.parent.mkdir(parents=True)
        missing_target = root / ".agents/skills/sd-review-pr/missing.md"
        target.symlink_to(missing_target)

        result = self.run_install(root, "--force")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target exists and is not a file", result.stdout)
        self.assertNotIn("Traceback", result.stdout)
        self.assertFalse(missing_target.exists())

    def test_diff_check_is_limited_to_installed_paths(self) -> None:
        root = self.make_repo(".gemini")
        unrelated = root / "unrelated.txt"
        unrelated.write_text("clean\n", encoding="utf-8")
        self.run_git(root, "add", "unrelated.txt")
        unrelated.write_text("bad   \n", encoding="utf-8")

        result = self.run_install(root, skip_diff_check=False)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((root / ".agents/skills/sd-review-pr/SKILL.md").is_file())

    def test_scoped_diff_check_reports_selected_path_failures(self) -> None:
        root = self.make_repo()
        bad = root / "bad.txt"
        bad.write_text("clean\n", encoding="utf-8")
        self.run_git(root, "add", "bad.txt")
        bad.write_text("bad   \n", encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            bad_result = install.run_diff_check(root, [Path("bad.txt")])
            missing_result = install.run_diff_check(root, [Path("missing.txt")])

        self.assertNotEqual(bad_result, 0)
        self.assertEqual(missing_result, 0)

    def test_empty_scoped_diff_check_does_not_run_repo_wide(self) -> None:
        root = self.make_repo()
        bad = root / "bad.txt"
        bad.write_text("clean\n", encoding="utf-8")
        self.run_git(root, "add", "bad.txt")
        bad.write_text("bad   \n", encoding="utf-8")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = install.run_diff_check(root, [])

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), "")

    def test_manifest_rejects_unknown_duplicate_and_missing_entries(self) -> None:
        source = install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        unknown_platform = install.PackFile(
            platform="mystery",
            kind="skill",
            source=source,
            target=Path(".agents/skills/sd-review-pr/SKILL.md"),
            anchor=None,
            install="always",
        )
        duplicate_a = self.valid_pack_file()
        duplicate_b = self.valid_pack_file()
        missing_source = self.valid_pack_file(source=install.ROOT / "missing.md")

        with self.assertRaisesRegex(SystemExit, "unknown platform"):
            install.validate_manifest([unknown_platform])
        with self.assertRaisesRegex(SystemExit, "duplicate target"):
            install.validate_manifest([duplicate_a, duplicate_b])
        with self.assertRaisesRegex(SystemExit, "missing pack template"):
            install.validate_manifest([missing_source])

    def test_path_resolution_errors_are_reported_without_tracebacks(self) -> None:
        with mock.patch.object(Path, "resolve", side_effect=OSError("boom")):
            with self.assertRaisesRegex(SystemExit, "cannot resolve source path"):
                install.validate_pack_source(
                    install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
                )

        with mock.patch.object(Path, "resolve", side_effect=OSError("boom")):
            with self.assertRaisesRegex(SystemExit, "cannot resolve target path"):
                install.validate_resolved_target_path(
                    Path("/tmp/repo"),
                    Path("/tmp/repo/file"),
                    "target path",
                )

    def test_manifest_rejects_unsafe_target_paths(self) -> None:
        for target in [
            Path("/tmp/pwn"),
            Path("../outside"),
            Path(".agents/../x"),
            Path(r"C:tmp\pwn"),
            Path("C:/tmp/pwn"),
            Path(r"\\server\share\pwn"),
            Path(r".agents\..\x"),
        ]:
            with self.subTest(target=target):
                with self.assertRaisesRegex(SystemExit, "unsafe target path"):
                    install.validate_manifest([self.valid_pack_file(target=target)])

    def test_manifest_rejects_unsafe_anchor_paths(self) -> None:
        for anchor in [
            Path("/tmp"),
            Path("../.github"),
            Path(".github/../x"),
            Path(r"C:.github"),
            Path(r"\.github"),
            Path(r".github\..\x"),
        ]:
            with self.subTest(anchor=anchor):
                with self.assertRaisesRegex(SystemExit, "unsafe anchor path"):
                    install.validate_manifest([self.valid_pack_file(anchor=anchor)])

    def test_manifest_rejects_unsafe_source_paths(self) -> None:
        for source in [
            Path("/tmp/pwn"),
            install.ROOT / ".." / "outside",
            install.ROOT / r"C:tmp\pwn",
            install.ROOT / r"templates\..\install.py",
        ]:
            with self.subTest(source=source):
                with self.assertRaisesRegex(SystemExit, "unsafe source path"):
                    install.validate_manifest([self.valid_pack_file(source=source)])

    def test_manifest_rejects_source_symlink_resolved_outside_pack_root(self) -> None:
        pack_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-root-"
        )
        outside_tempdir = tempfile.TemporaryDirectory(
            prefix="sd-ai-command-pack-outside-"
        )
        self.addCleanup(pack_tempdir.cleanup)
        self.addCleanup(outside_tempdir.cleanup)
        pack_root = Path(pack_tempdir.name)
        outside_source = Path(outside_tempdir.name) / "secret.md"
        outside_source.write_text("outside\n", encoding="utf-8")
        source = pack_root / "templates/source.md"
        source.parent.mkdir(parents=True)
        source.symlink_to(outside_source)

        with mock.patch.object(install.manifest, "ROOT", pack_root):
            with self.assertRaisesRegex(SystemExit, "unsafe source path"):
                install.validate_manifest([self.valid_pack_file(source=source)])

    def test_git_diff_check_missing_git_is_nonfatal(self) -> None:
        root = self.make_repo()
        output = io.StringIO()

        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            with contextlib.redirect_stdout(output):
                result = install.run_diff_check(root, [Path("README.md")])

        self.assertEqual(result, 0)
        self.assertIn("git not found", output.getvalue())

    def test_main_returns_failed_diff_check_status(self) -> None:
        root = self.make_repo()
        output = io.StringIO()

        with mock.patch.object(install, "run_diff_check", return_value=7):
            with contextlib.redirect_stdout(output):
                result = install.main([str(root)])

        self.assertEqual(result, 7)

    def test_codex_visible_sd_skill_wrappers_reference_workflows(self) -> None:
        expected = {
            "sd-start": "Resolve the `trellis-start` skill by name",
            "sd-continue": "Resolve the `trellis-continue` skill by name",
            "sd-finish-work": "Resolve the `trellis-finish-work` skill by name",
            "sd-update-spec": "Resolve the `trellis-update-spec` skill by name",
        }

        for skill_name, target in expected.items():
            skill_path = (
                install.ROOT / f"templates/.agents/skills/{skill_name}/SKILL.md"
            )
            content = skill_path.read_text(encoding="utf-8")
            self.assertIn(f"name: {skill_name}", content)
            self.assertIn(target, content)

        review_pr = (
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-pr", review_pr)
        self.assertIn("# SD PR Review Loop", review_pr)
        self.assertIn("standing permission to reply", review_pr)
        self.assertIn("bash scripts/sd-ai-command-pack-full-check.sh", review_pr)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0", review_pr)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0", review_pr)

        create_pr = (
            install.ROOT / "templates/.agents/skills/sd-create-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-create-pr", create_pr)
        self.assertIn("# SD Create Pull Request", create_pr)
        self.assertIn("Resolve both `sd-update-spec` and `sd-review-pr`", create_pr)
        self.assertIn("Do not create a duplicate PR", create_pr)
        self.assertIn("Do not assume the base branch is `main`", create_pr)
        self.assertIn("SD_AI_COMMAND_PACK_CREATE_PR_BRANCH", create_pr)
        self.assertIn("SD_AI_COMMAND_PACK_CREATE_PR_BRANCH_SLUG", create_pr)
        self.assertIn("git switch -c", create_pr)
        self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR", create_pr)
        self.assertIn("Do not run Prism, Gito", create_pr)

        work_backlog = (
            install.ROOT / "templates/.agents/skills/sd-work-backlog/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-work-backlog", work_backlog)
        self.assertIn("# SD Work Backlog", work_backlog)
        self.assertIn("one implementation-ready task", work_backlog)
        self.assertIn("Work exactly one backlog task per iteration", work_backlog)
        self.assertIn("sd-create-pr", work_backlog)
        self.assertIn("sd-housekeeping", work_backlog)
        self.assertIn("Parked by sd-work-backlog", work_backlog)
        self.assertIn("follow-ups or learnings", work_backlog)
        self.assertIn("Do not create pull requests in the upstream `Trellis`", work_backlog)

        work_designs = (
            install.ROOT / "templates/.agents/skills/sd-work-designs/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-work-designs", work_designs)
        self.assertIn("# SD Work Designs", work_designs)
        self.assertIn("design.md", work_designs)
        self.assertIn("implement.md", work_designs)
        self.assertIn("Do not run `task.py start`", work_designs)
        self.assertIn("Parked by sd-work-designs", work_designs)
        self.assertIn("numbered list", work_designs)

        review_local = (
            install.ROOT / "templates/.agents/skills/sd-review-local/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-local", review_local)
        self.assertIn("# SD Local Review Loop", review_local)
        self.assertIn("bash scripts/sd-ai-command-pack-review-local.sh", review_local)
        self.assertIn("SD_AI_COMMAND_PACK_REVIEW_LOCAL_TOOLS", review_local)
        self.assertIn("asks the user which findings to fix", review_local)
        self.assertIn("Do not substitute `sd-full-check`", review_local)

        review_local_all = (
            install.ROOT / "templates/.agents/skills/sd-review-local-all/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-local-all", review_local_all)
        self.assertIn("# SD Full-Codebase Local Review Loop", review_local_all)
        self.assertIn(
            "bash scripts/sd-ai-command-pack-review-local.sh --full-codebase",
            review_local_all,
        )
        self.assertIn("prism review codebase", review_local_all)
        self.assertIn("empty chunk response", review_local_all)
        self.assertIn("gito review --all --path <repo-root>", review_local_all)
        self.assertIn("replacing `<repo-root>` with the absolute repository root", review_local_all)
        self.assertIn("branch-diff deletions", review_local_all)
        self.assertIn("continue stacking fixes", review_local_all)
        self.assertIn("UV_CACHE_DIR", review_local_all)
        self.assertIn(
            "SD_AI_COMMAND_PACK_REVIEW_LOCAL_ALL_<TOOL>_COMMAND",
            review_local_all,
        )

        review_learnings = (
            install.ROOT / "templates/.agents/skills/sd-review-learnings/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-review-learnings", review_learnings)
        self.assertIn("# SD Review Learnings", review_learnings)
        self.assertIn("scripts/sd-ai-command-pack-review-learnings.py", review_learnings)

        full_check = (
            install.ROOT / "templates/.agents/skills/sd-full-check/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-full-check", full_check)
        self.assertIn("# SD Full Check", full_check)
        self.assertIn("bash scripts/sd-ai-command-pack-full-check.sh", full_check)
        self.assertIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO", full_check)
        # The skill lists common toggles and points at the canonical docs for
        # the full env-var set (deprecated fallbacks included).
        self.assertIn("docs/SD_AI_COMMAND_PACK.md", full_check)
        self.assertIn("Configuration", full_check)
        self.assertIn("sandboxed agent sessions", full_check)
        self.assertIn("PYTHONPYCACHEPREFIX", full_check)
        self.assertIn("UV_TOOL_DIR", full_check)
        self.assertIn("RUFF_CACHE_DIR", full_check)

        housekeeping = (
            install.ROOT / "templates/.agents/skills/sd-housekeeping/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("name: sd-housekeeping", housekeeping)
        self.assertIn("# SD Housekeeping", housekeeping)
        self.assertIn("bash scripts/sd-ai-command-pack-housekeeping.sh", housekeeping)
        self.assertIn("Expected clean state", housekeeping)
        self.assertIn("general\nrepo maintenance", housekeeping)
        self.assertIn("branch: <default>", housekeeping)

        update_spec = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("do not rebuild", update_spec)
        self.assertIn("`.obsidian-kb/` manually", update_spec)
        self.assertIn("helper as the source of truth for `.obsidian-kb/`", update_spec)
        self.assertNotIn("Ensure `.obsidian-kb/`", update_spec)
        self.assertNotIn("Link every relevant existing repo-knowledge file", update_spec)
        self.assertNotIn("perform the remaining bullets manually", update_spec)

        update_spec = (
            install.ROOT / "templates/.agents/skills/sd-update-spec/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("repospec artifact", update_spec)
        self.assertIn("docs/repomix-map.md", update_spec)
        self.assertIn("Architectural overview", update_spec)
        self.assertIn(".obsidian-kb", update_spec)
        self.assertIn("scripts/sd-ai-command-pack-update-spec-kb.py", update_spec)
        self.assertIn(".obsidian-kb/Dashboard - <repo>.md", update_spec)
        self.assertIn("Obsidian vault copy", update_spec)

    def test_generic_markdown_platforms_share_neutral_command_sources(self) -> None:
        _, files = install.load_manifest()
        generic_platforms = {
            "antigravity",
            "codebuddy",
            "cursor",
            "devin",
            "droid",
            "kilo",
            "opencode",
            "pi",
            "qoder",
            "trae",
            "zcode",
        }
        command_sources_by_platform: dict[str, dict[str, Path]] = {
            platform: {} for platform in generic_platforms
        }

        for file in files:
            if file.platform not in generic_platforms:
                continue
            if file.source.relative_to(install.ROOT).parts[:2] != ("templates", ".commands"):
                continue
            command_sources_by_platform[file.platform][file.source.name] = file.source

        expected_sources = {
            f"sd-{command}.md"
            for command in [
                "start",
                "continue",
                "finish-work",
                "create-pr",
                "work-backlog",
                "work-designs",
                "review-pr",
                "review-local",
                "review-local-all",
                "review-learnings",
                "full-check",
                "housekeeping",
                "update-spec",
            ]
        }
        for platform, command_sources in command_sources_by_platform.items():
            self.assertEqual(set(command_sources), expected_sources, platform)
            for source_name, source_path in command_sources.items():
                self.assertEqual(
                    source_path.relative_to(install.ROOT),
                    Path("templates") / ".commands" / source_name,
                    platform,
                )

    def test_review_provider_scan_excludes_are_managed_in_scripts(self) -> None:
        lib_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-shell-lib.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
        ]
        runner_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh",
        ]
        expected_dirs = (
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
        )

        for script_path in lib_paths:
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("# sd-ai-command-pack review-scan-excludes start", content)
            self.assertIn("# sd-ai-command-pack review-scan-excludes end", content)
            for dirname in expected_dirs:
                self.assertIn(f'  "{dirname}"', content, script_path)

        for script_path in runner_paths:
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("source_sd_ai_command_pack_shell_lib", content)
            self.assertIn("--exclude \"$excludes\"", content)
            self.assertIn("--filter \"$filters\"", content)

    def test_shell_scripts_source_shared_helper_library(self) -> None:
        helper_functions = (
            "positive_int_or_default",
            "nonnegative_int_or_default",
            "load_gito_pack_env",
            "prepare_gito_uv_env",
            "gito_output_indicates_rate_limit",
            "run_gito_command",
            "has_ref",
            "default_review_base_ref",
            "configured_review_base_ref",
            "path_is_standard_review_scan_excluded",
            "review_scan_exclude_globs_csv",
            "join_by_comma",
        )
        lib_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-shell-lib.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
        ]
        runner_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-scope.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-scope.sh",
        ]

        for lib_path in lib_paths:
            content = lib_path.read_text(encoding="utf-8")
            for function_name in helper_functions:
                self.assertIn(f"{function_name}()", content, lib_path)

        for runner_path in runner_paths:
            content = runner_path.read_text(encoding="utf-8")
            self.assertIn("sd-ai-command-pack-shell-lib.sh", content, runner_path)
            for function_name in helper_functions:
                self.assertNotIn(f"{function_name}()", content, runner_path)

    def test_review_scripts_avoid_hardcoded_default_branch_and_regex_scope_paths(
        self,
    ) -> None:
        script_paths = [
            install.ROOT / "scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "scripts/sd-ai-command-pack-shell-lib.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-scope.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            install.ROOT / "templates/scripts/sd-ai-command-pack-full-check.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-scope.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-preflight.mjs",
        ]

        for script_path in script_paths:
            content = script_path.read_text(encoding="utf-8")
            self.assertNotIn("origin/main", content, script_path)

        for script_path in (
            install.ROOT / "scripts/sd-ai-command-pack-shell-lib.sh",
            install.ROOT / "templates/scripts/sd-ai-command-pack-shell-lib.sh",
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-preflight.mjs",
        ):
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("origin/HEAD", content, script_path)

        scope_script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-scope.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("normalize_repo_path()", scope_script)
        self.assertNotIn("[[ \"$path\" =~", scope_script)

    def test_install_drops_gitignored_anchor_entries_without_git(self) -> None:
        root = self.make_repo(".claude")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        shutil.rmtree(root / ".claude")
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8") + ".claude/\n",
            encoding="utf-8",
        )

        # Without git the ignore status cannot be confirmed, so preservation
        # fails closed and the entries drop.
        result = self.run_install(root, extra_env={"PATH": ""})

        self.assertEqual(result.returncode, 0, result.stdout)
        receipt_text = (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8")
        self.assertNotIn(".claude/commands/sd/start.md", receipt_text)
        self.assertNotIn("kept-in-receipt", result.stdout)

    def test_force_overwrite_revouches_drifted_target(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        # Drift a vouched script, then force-refresh: the overwrite must be
        # re-vouched with the template hash (single-pass fleet refreshes
        # produce exactly this "overwritten" status for changed files).
        script = root / "scripts/sd-ai-command-pack-review-local.sh"
        script.write_text(
            script.read_text(encoding="utf-8") + "\n# drift\n",
            encoding="utf-8",
        )

        result = self.run_install(root, "--force")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overwritten", result.stdout)

        template_digest = "sha256:" + hashlib.sha256(
            (PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-local.sh").read_bytes()
        ).hexdigest()
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        self.assertEqual(
            provenance["files"]["scripts/sd-ai-command-pack-review-local.sh"],
            template_digest,
        )

        audit = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-install-audit.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(audit.returncode, 0, audit.stdout)
        self.assertNotIn("drifted from pack", audit.stdout)

    def test_fresh_gitignore_reports_created_status(self) -> None:
        root = self.make_repo()
        gitignore = root / ".gitignore"
        if gitignore.exists():
            gitignore.unlink()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("created     .gitignore", result.stdout)

        result = self.run_install(root)
        self.assertIn("unchanged   .gitignore", result.stdout)

    def test_run_diff_check_skips_cleanly_outside_git_repo(self) -> None:
        plain_dir = Path(tempfile.mkdtemp(prefix="sd-non-git-"))
        self.addCleanup(shutil.rmtree, plain_dir, True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = install.run_diff_check(plain_dir, [Path("README.md")])
        self.assertEqual(status, 0)
        self.assertIn("git diff --check could not run", output.getvalue())


if __name__ == "__main__":
    unittest.main()
