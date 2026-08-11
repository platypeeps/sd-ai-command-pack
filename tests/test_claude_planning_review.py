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
    # Deliberately not an install target: the Codex lane is a practice of this
    # repository, carried outside `templates/` and outside `manifest.json`.
    APPENDIX = "docs/planning-adversarial-review-codex.md"

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
        # Assert existence before reading. The appendix is the one file here
        # with no manifest row and no template twin, so nothing else in the
        # suite would catch it being moved or renamed -- and a bare
        # `read_text` would report that as a FileNotFoundError inside a
        # contract-wording test rather than as a missing file.
        appendix_path = install.ROOT / self.APPENDIX
        self.assertTrue(appendix_path.is_file(), f"missing {self.APPENDIX}")
        appendix = appendix_path.read_text(encoding="utf-8")

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
            "`addressed`, `rebutted`, `parked`, or `unresolved`",
            "prevents `task.py start`",
            "three automatic rounds total",
            "start a fourth automatic round",
        ):
            self.assertIn(expected, reference)

        # The operational detail for the Codex lane lives in the appendix, and
        # these assertions moved with it rather than being dropped. `<
        # /dev/null` is checked explicitly: a background run without it hangs
        # at near-zero CPU with no output, which reads as a slow review rather
        # than a stuck one.
        for expected in (
            "command -v codex",
            "codex exec --help",
            "separate background Bash task",
            "`BashOutput`",
            "`--sandbox read-only`",
            "`--ephemeral`",
            "`< /dev/null`",
            "Codex: skipped",
            "Codex: failed",
        ):
            self.assertIn(expected, appendix)

        for forbidden in (
            "codex-companion.mjs",
            "CLAUDE_PLUGIN_ROOT",
            ".claude/plugins/cache",
        ):
            self.assertNotIn(forbidden, rule)
            self.assertNotIn(forbidden, reference)
            self.assertNotIn(forbidden, appendix)

    def test_host_contract_carries_no_codex_invocation(self) -> None:
        # The point of the split. A surviving pack-shipped file telling an
        # agent to run `codex exec` in a repository that never declared codex
        # is what the thin resweep reports as `undeclared codex usage`, and it
        # blocked every consumer's conversion. Assert on the invocation, not
        # on the word: the contract still *names* the lane, and must, or the
        # capability would be undiscoverable.
        reference = (install.ROOT / f"templates/{self.REFERENCE}").read_text(
            encoding="utf-8"
        )

        for forbidden in ("codex exec", "command -v codex", "--platform codex"):
            self.assertNotIn(forbidden, reference)

        # No dangling promise either. The contract must not point a consumer at
        # a lane it can never obtain, so it names no second-lane file at all --
        # only the standard the single lane is held to instead.
        self.assertNotIn("planning-adversarial-review-codex", reference)
        self.assertIn("the pack ships none", reference)
        self.assertIn("hold it to the standard that two lanes", reference)

    def test_appendix_is_absent_from_the_shipped_payload(self) -> None:
        # The resolution this task shipped. The Codex lane really does invoke
        # the CLI, and no wording makes that acceptable inside a file that
        # reaches a repository which never declared the platform -- so it
        # reaches none. Two independent facts, because either alone is
        # bypassable: no manifest row, and no copy under `templates/`.
        appendix = install.ROOT / self.APPENDIX
        self.assertTrue(appendix.is_file(), f"{self.APPENDIX} must exist in the repo")
        self.assertIn("codex exec", appendix.read_text(encoding="utf-8"))

        _, files = install.load_manifest()
        for file in files:
            self.assertNotIn(
                "planning-adversarial-review-codex",
                file.target.as_posix(),
                "the Codex lane must carry no manifest row",
            )

        stray = sorted(
            path.relative_to(install.ROOT).as_posix()
            for path in (install.ROOT / "templates").rglob(
                "*planning-adversarial-review-codex*"
            )
        )
        self.assertEqual(stray, [])


if __name__ == "__main__":
    _support.unittest.main()
