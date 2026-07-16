from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

hashlib = _support.hashlib
json = _support.json
subprocess = _support.subprocess
sys = _support.sys
unittest = _support.unittest
Path = _support.Path
install = _support.install
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

STALE_SKILL = ".agents/skills/sd-review-local-all/SKILL.md"
STALE_COMMAND = ".claude/commands/sd/review-local-all.md"
STALE_CONTENT = "# sd-review-local-all\n\nRun the full-codebase review loop.\n"


class RetiredTargetsTests(InstallTestCase):
    """Refresh-time cleanup of retired-command leftovers (sd-review-local-all)."""

    def seed_stale_target(
        self,
        root: Path,
        relative_path: str,
        *,
        content: str = STALE_CONTENT,
        vouch: bool = True,
    ) -> Path:
        """Recreate a retired file the way a prior 0.12.x install left it.

        Installing from a manifest that still lists the old targets is no
        longer possible, so the fixture simulates the stale consumer
        directly: write the file and (unless ``vouch=False``) record its
        content hash in the existing provenance exactly as the prior
        install's receipt writing would have.
        """
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        if vouch:
            provenance_path = root / install.PROVENANCE_FILE
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["files"][relative_path] = (
                "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()
            )
            provenance_path.write_text(
                json.dumps(provenance, indent=2) + "\n",
                encoding="utf-8",
            )
        return destination

    def run_install_audit(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
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

    def test_retired_targets_pin_review_local_all_footprint(self) -> None:
        self.assertEqual(len(install.RETIRED_TARGETS), 25)
        self.assertEqual(
            len(set(install.RETIRED_TARGETS)),
            len(install.RETIRED_TARGETS),
        )
        for target in install.RETIRED_TARGETS:
            with self.subTest(target=target):
                self.assertIn("review-local-all", target)
        # A retired path must never come back as a live manifest target.
        manifest_targets = {file.target.as_posix() for file in self._manifest_files}
        self.assertEqual(
            manifest_targets.intersection(install.RETIRED_TARGETS),
            set(),
        )

    def test_refresh_deletes_vouched_stale_target_and_prunes_parent(self) -> None:
        root = self.make_repo()
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        stale = self.seed_stale_target(root, STALE_SKILL)

        result = self.run_install_inproc(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"{'retired':17} {STALE_SKILL}", result.stdout)
        self.assertFalse(stale.exists())
        self.assertFalse(stale.parent.exists())
        self.assertTrue((root / ".agents/skills/sd-review-local/SKILL.md").is_file())
        receipt = (root / install.INSTALLED_TARGETS_FILE).read_text(encoding="utf-8")
        provenance = (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        self.assertNotIn("review-local-all", receipt)
        self.assertNotIn("review-local-all", provenance)

    def test_refresh_preserves_drifted_stale_target_without_force(self) -> None:
        root = self.make_repo()
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        stale = self.seed_stale_target(root, STALE_COMMAND)
        stale.write_text(
            STALE_CONTENT + "# local customization\n",
            encoding="utf-8",
        )

        result = self.run_install_inproc(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            f"{'retired-preserved':17} {STALE_COMMAND} "
            "(content differs from installed pack version)",
            result.stdout,
        )
        self.assertTrue(stale.is_file())
        self.assertIn("# local customization", stale.read_text(encoding="utf-8"))

    def test_force_refresh_deletes_drifted_stale_target_with_backup(self) -> None:
        root = self.make_repo()
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        stale = self.seed_stale_target(root, STALE_COMMAND, vouch=False)

        result = self.run_install_inproc(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"{'retired':17} {STALE_COMMAND}", result.stdout)
        self.assertIn(f"{'backup':17} {STALE_COMMAND}.bak", result.stdout)
        self.assertFalse(stale.exists())
        backup = root / f"{STALE_COMMAND}.bak"
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), STALE_CONTENT)

    def test_refresh_without_stale_targets_reports_nothing(self) -> None:
        root = self.make_repo()
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("retired", result.stdout)

        result = self.run_install_inproc(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("retired", result.stdout)
        self.assertNotIn("would-retire", result.stdout)

    def test_dry_run_reports_planned_retirement_without_deleting(self) -> None:
        root = self.make_repo()
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        stale = self.seed_stale_target(root, STALE_SKILL)

        result = self.run_install_inproc(root, "--dry-run")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"{'would-retire':17} {STALE_SKILL}", result.stdout)
        self.assertTrue(stale.is_file())
        self.assertEqual(stale.read_text(encoding="utf-8"), STALE_CONTENT)
        # The dry run must not rewrite the receipts either, so the prior
        # provenance still vouches the file for the eventual real refresh.
        provenance = json.loads(
            (root / install.PROVENANCE_FILE).read_text(encoding="utf-8")
        )
        self.assertIn(STALE_SKILL, provenance["files"])

    def test_retire_stale_targets_without_provenance_preserves_files(self) -> None:
        root = self.make_repo()
        stale = root / STALE_SKILL
        stale.parent.mkdir(parents=True)
        stale.write_text(STALE_CONTENT, encoding="utf-8")

        results = install.retire_stale_targets(
            root,
            force=False,
            dry_run=False,
            backup=False,
        )

        self.assertEqual(
            [(result.target.as_posix(), result.status) for result in results],
            [(STALE_SKILL, "retired-preserved")],
        )
        self.assertEqual(
            results[0].detail,
            "content differs from installed pack version",
        )
        self.assertTrue(stale.is_file())

    def test_full_remove_cleans_vouched_stale_target_too(self) -> None:
        root = self.make_repo()
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        stale = self.seed_stale_target(root, STALE_SKILL)
        # A stale consumer's receipt still lists the retired target.
        receipt = root / install.INSTALLED_TARGETS_FILE
        receipt.write_text(
            receipt.read_text(encoding="utf-8") + STALE_SKILL + "\n",
            encoding="utf-8",
        )

        result = self.run_install_inproc(root, "--remove")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn(
            "not a recognized sd-ai-command-pack target",
            result.stdout,
        )
        self.assertFalse(stale.exists())

    def test_refresh_cleanup_restores_clean_install_audit(self) -> None:
        root = self.make_repo()
        result = self.run_install_inproc(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        for target in install.RETIRED_TARGETS:
            self.seed_stale_target(root, target)

        audit = self.run_install_audit(root)
        self.assertEqual(audit.returncode, 1, audit.stdout)
        self.assertIn(
            "pack-like file is not listed in installed targets",
            audit.stdout,
        )

        result = self.run_install_inproc(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_paths_absent(root, install.RETIRED_TARGETS)

        audit = self.run_install_audit(root)
        self.assertEqual(audit.returncode, 0, audit.stdout)
        self.assertIn("install audit passed", audit.stdout)


if __name__ == "__main__":
    unittest.main()
