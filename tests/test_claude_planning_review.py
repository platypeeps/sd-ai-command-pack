from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

install = _support.install
InstallTestCase = _support.InstallTestCase


class ClaudePlanningReviewTests(InstallTestCase):
    RULE = ".claude/rules/sd-planning-adversarial-review.md"
    REFERENCE = ".claude/sd-ai-command-pack/planning-adversarial-review.md"

    def test_manifest_scopes_planning_review_files_to_claude(self) -> None:
        _, files = install.load_manifest()
        entries = {
            file.target.as_posix(): file
            for file in files
            if file.target.as_posix() in {self.RULE, self.REFERENCE}
        }

        self.assertEqual(set(entries), {self.RULE, self.REFERENCE})
        for entry in entries.values():
            self.assertEqual(entry.platform, "claude")
            self.assertEqual(entry.anchor.as_posix(), ".claude")
            self.assertEqual(entry.install, "if-anchor-exists")

    def test_claude_install_includes_rule_and_reference(self) -> None:
        root = self.make_repo(".claude")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_paths_are_files(root, [self.RULE, self.REFERENCE])
        self.assertEqual(
            (root / self.RULE).read_bytes(),
            (install.ROOT / f"templates/{self.RULE}").read_bytes(),
        )
        self.assertEqual(
            (root / self.REFERENCE).read_bytes(),
            (install.ROOT / f"templates/{self.REFERENCE}").read_bytes(),
        )
        self.assert_installed_targets_snapshot_matches_selection(root)

        ignored = self._run_git_process(root, "check-ignore", self.RULE, self.REFERENCE)
        self.assertEqual(ignored.returncode, 1, ignored.stdout)

    def test_non_claude_install_does_not_include_planning_review_files(self) -> None:
        root = self.make_repo(".gemini")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_paths_absent(root, [self.RULE, self.REFERENCE])
        self.assert_installed_targets_snapshot_matches_selection(root)

    def test_planning_review_contract_is_bounded_and_fail_safe(self) -> None:
        rule = (install.ROOT / f"templates/{self.RULE}").read_text(encoding="utf-8")
        reference = (install.ROOT / f"templates/{self.REFERENCE}").read_text(
            encoding="utf-8"
        )

        for expected in (
            "`prd.md`",
            "`design.md`",
            "`implement.md`",
            "content hashes",
            "planning convergence boundary",
            "task.py start",
        ):
            self.assertIn(expected, rule)

        for expected in (
            "whitespace, formatting",
            "once",
            "command -v codex",
            "codex exec --help",
            "separate background Bash task",
            "`BashOutput`",
            "`--sandbox read-only`",
            "`--ephemeral`",
            "`addressed`, `rebutted`, `parked`, or `unresolved`",
            "prevents `task.py start`",
            "Do not start a third automatic round",
            "Codex: skipped",
            "Codex: failed",
        ):
            self.assertIn(expected, reference)

        for forbidden in (
            "codex-companion.mjs",
            "CLAUDE_PLUGIN_ROOT",
            ".claude/plugins/cache",
        ):
            self.assertNotIn(forbidden, rule)
            self.assertNotIn(forbidden, reference)


if __name__ == "__main__":
    _support.unittest.main()
