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


class ReviewLearningsTests(InstallTestCase):
    """Tests for review-learning detection and managed-block updates."""

    def test_learnings_survive_non_object_graphql_payload(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_payloads",
        )
        responses = ['[{"number": 7, "title": "t", "url": "u"}]', "null"]

        def fake_stdout(args, repo_root):
            return responses.pop(0)

        with mock.patch.object(learnings, "_run_gh_stdout", fake_stdout):
            comments = learnings.fetch_recent_copilot_comments(
                Path("."), days=7, limit=5, github_repo="owner/name"
            )
        self.assertEqual(comments, [])

    def test_learnings_neutralize_embedded_managed_markers(self) -> None:
        learnings = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_markers",
        )
        comment = learnings.PullRequestComment(
            pr_number=1,
            pr_title="t",
            pr_url=f"https://example.invalid/{learnings.MANAGED_START}/1",
            path=f"docs/{learnings.MANAGED_END}.md",
            body=f"evil {learnings.MANAGED_END} splice",
            is_resolved=False,
            is_outdated=False,
        )
        rendered = comment.markdown_item()
        self.assertNotIn(learnings.MANAGED_END, rendered)
        self.assertNotIn(learnings.MANAGED_START, rendered)
        self.assertIn("[managed-end marker removed]", rendered)
        self.assertIn("[managed-start marker removed]", rendered)

        finding = learnings.Finding(
            category="env",
            path=f"docs/{learnings.MANAGED_END}.md",
            lineno=3,
            detail=f"uses {learnings.MANAGED_START} somewhere",
            recommendation=f"drop {learnings.MANAGED_END} now",
        )
        rendered = finding.markdown_item()
        self.assertNotIn(learnings.MANAGED_END, rendered)
        self.assertNotIn(learnings.MANAGED_START, rendered)

    def test_learnings_report_when_no_base_ref_resolves(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="sd-learnings-no-remote-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.run_git(root, "init", "--quiet")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("# base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "seed")

        result = subprocess.run(
            [
                sys.executable,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-review-learnings.py"),
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no base ref could be resolved", result.stderr)
        self.assertIn("no local review-cycle findings detected", result.stdout)

    def test_review_learnings_script_detects_local_patterns(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nscratch=\"$(mktemp)\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+scratch=\"$(mktemp)\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("[sd-review-learnings:portability]", result.stdout)
        self.assertIn("mktemp", result.stdout)

    def test_review_learnings_script_detects_positional_negative_offset(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nlast=\"${@: -1}\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+last=\"${@: -1}\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("[sd-review-learnings:portability]", result.stdout)
        self.assertIn("negative array offsets", result.stdout)

    def test_review_learnings_script_allows_shell_default_expansions(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        tool = root / "scripts/tool.sh"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nmode=\"${TOOL_MODE:-0}\"\n",
            encoding="utf-8",
        )
        diff = root / "diff.patch"
        diff.write_text(
            "diff --git a/scripts/tool.sh b/scripts/tool.sh\n"
            "new file mode 100755\n"
            "index 0000000..1111111\n"
            "--- /dev/null\n"
            "+++ b/scripts/tool.sh\n"
            "@@ -0,0 +1,3 @@\n"
            "+#!/usr/bin/env bash\n"
            "+set -euo pipefail\n"
            "+mode=\"${TOOL_MODE:-0}\"\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("no local review-cycle findings detected", result.stdout)

    def test_review_learnings_script_negative_offset_regex_is_specific(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_regex_test",
        )

        self.assertIsNotNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${@: -1}"))
        self.assertIsNotNone(
            module._NEGATIVE_ARRAY_OFFSET_RE.search("${items[@]: -1}")
        )
        self.assertIsNotNone(
            module._NEGATIVE_ARRAY_OFFSET_RE.search("${items[-1]}")
        )
        self.assertIsNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${VALUE:-1}"))
        self.assertIsNone(module._NEGATIVE_ARRAY_OFFSET_RE.search("${value: -1}"))

    def test_review_learnings_script_extracts_explicit_env_refs_only(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_env_regex_test",
        )

        self.assertEqual(
            module._extract_env_refs(
                'echo "$SD_FOO" "${GH_BAR}" "${SD_DEFAULT:-0}" SD_BARE',
                ("SD", "GH"),
            ),
            {"SD_FOO", "GH_BAR", "SD_DEFAULT"},
        )

    def test_review_learnings_script_updates_managed_block(self) -> None:
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        script_path = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        )
        target = root / "docs/review-learnings.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Review Learnings\n\nHuman notes stay.\n", encoding="utf-8")
        diff = root / "diff.patch"
        diff.write_text("", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(root),
                "--diff-from",
                str(diff),
                "--update",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        content = target.read_text(encoding="utf-8")
        self.assertIn("Human notes stay.", content)
        self.assertIn("<!-- sd-review-learnings:start -->", content)
        self.assertIn("No local review-cycle findings detected", content)

    def test_review_learnings_update_uses_atomic_write(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_atomic_write",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-atomic-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "docs/review-learnings.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        original = "# Review Learnings\n\nHuman notes stay.\n"
        target.write_text(original, encoding="utf-8")
        block = module.render_managed_block([], [])

        with mock.patch.object(module.os, "replace", side_effect=OSError("blocked")):
            with self.assertRaisesRegex(OSError, "blocked"):
                module.update_target(target, block, dry_run=False)

        self.assertEqual(target.read_text(encoding="utf-8"), original)
        self.assertEqual(list(target.parent.glob(".*.tmp")), [])

    def test_review_learnings_script_rejects_malformed_payload_helpers(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_test",
        )

        with self.assertRaisesRegex(TypeError, "expected object"):
            module._as_dict(None)
        with self.assertRaisesRegex(TypeError, "expected list"):
            module._as_list({})

    def test_review_learnings_main_reports_malformed_payload_without_traceback(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_main_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)

        with mock.patch.object(module, "build_local_diff", return_value=""):
            with mock.patch.object(module, "extract_findings", return_value=[]):
                with mock.patch.object(
                    module,
                    "fetch_recent_copilot_comments",
                    side_effect=TypeError("expected list in review learnings payload"),
                ):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        result = module.main(
                            [
                                "--repo-root",
                                tempdir.name,
                                "--github-days",
                                "1",
                            ]
                        )

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:github]", stderr.getvalue())
        self.assertIn("expected list in review learnings payload", stderr.getvalue())

    def test_review_learnings_script_rejects_invalid_managed_marker_order(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_marker_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:end -->\n"
            "old\n"
            "<!-- sd-review-learnings:start -->\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "invalid order"):
            module.update_target(target, "<!-- sd-review-learnings:start -->\nnew\n<!-- sd-review-learnings:end -->\n", dry_run=False)

    def test_review_learnings_main_reports_invalid_managed_marker_order(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_marker_main_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        target = root / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:end -->\n"
            "old\n"
            "<!-- sd-review-learnings:start -->\n",
            encoding="utf-8",
        )

        with mock.patch.object(module, "build_local_diff", return_value=""):
            with mock.patch.object(module, "extract_findings", return_value=[]):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = module.main(
                        [
                            "--repo-root",
                            str(root),
                            "--target",
                            str(target),
                            "--update",
                        ]
                    )

        self.assertEqual(result, 2)
        self.assertIn("[sd-review-learnings:update]", stderr.getvalue())
        self.assertIn("invalid order", stderr.getvalue())

    def test_review_learnings_script_preserves_text_after_managed_block(
        self,
    ) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_layout_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-review-learnings-test-")
        self.addCleanup(tempdir.cleanup)
        target = Path(tempdir.name) / "review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:start -->\n"
            "old\n"
            "<!-- sd-review-learnings:end -->\n"
            "Human notes stay.\n",
            encoding="utf-8",
        )

        module.update_target(
            target,
            "<!-- sd-review-learnings:start -->\n"
            "new\n"
            "<!-- sd-review-learnings:end -->\n",
            dry_run=False,
        )

        content = target.read_text(encoding="utf-8")
        self.assertIn("<!-- sd-review-learnings:end -->\nHuman notes stay.", content)

    def test_review_learnings_script_skips_incomplete_github_payloads(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py",
            "sd_ai_command_pack_review_learnings_github_payload_test",
        )

        def fake_run_gh_json(args: list[str], repo_root: Path):
            if args[:2] == ["pr", "list"]:
                return [{"number": 1, "title": "PR", "url": "https://example.test/pr/1"}]
            return {"errors": [{"message": "rate limited"}]}

        with mock.patch.object(module, "github_repo_slug", return_value=("owner", "repo")):
            with mock.patch.object(module, "_run_gh_json", fake_run_gh_json):
                comments = module.fetch_recent_copilot_comments(
                    Path("."),
                    days=1,
                    limit=1,
                )

        self.assertEqual(comments, [])

    def test_review_learnings_script_resolves_github_repo_generically(self) -> None:
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-review-learnings.py"
        ).read_text(encoding="utf-8")

        self.assertIn("gh", script)
        self.assertIn("repo", script)
        self.assertIn("nameWithOwner", script)
        self.assertNotIn("answerbook", script)
        self.assertNotIn("mezmo_benchmark", script)

    def test_review_learnings_reports_subprocess_timeout_as_setup_failure(
        self,
    ) -> None:
        # Regression: a hung git/gh call must surface the [sd-review-learnings:*]
        # exit-2 contract, not a raw subprocess.TimeoutExpired traceback.
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_timeout_regression",
        )
        root = self.make_repo()

        with mock.patch.object(
            module,
            "build_local_diff",
            side_effect=RuntimeError("git timed out after 120s"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = module.main(["--repo-root", str(root)])
        self.assertEqual(code, 2)
        self.assertIn("[sd-review-learnings:findings]", stderr.getvalue())

        diff_file = root / "empty.diff"
        diff_file.write_text("", encoding="utf-8")
        with mock.patch.object(
            module,
            "fetch_recent_copilot_comments",
            side_effect=RuntimeError("gh timed out after 60s"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = module.main(
                    [
                        "--repo-root",
                        str(root),
                        "--diff-from",
                        str(diff_file),
                        "--github-days",
                        "7",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("[sd-review-learnings:github]", stderr.getvalue())

    def test_review_learnings_untracked_listing_failure_raises_runtime_error(
        self,
    ) -> None:
        # A nonzero `git ls-files` exit must surface as RuntimeError carrying
        # git's stderr, with a stable fallback message when stderr is blank.
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_untracked_failure",
        )
        failed_result = subprocess.CompletedProcess(
            args=["git"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository\n",
        )

        with mock.patch.object(module, "run_git_command", return_value=failed_result):
            with self.assertRaisesRegex(RuntimeError, "not a git repository"):
                module._git_untracked_paths(Path("."))

        blank_result = subprocess.CompletedProcess(
            args=["git"],
            returncode=1,
            stdout="",
            stderr="  \n",
        )

        with mock.patch.object(module, "run_git_command", return_value=blank_result):
            with self.assertRaisesRegex(RuntimeError, "git ls-files failed"):
                module._git_untracked_paths(Path("."))

    def test_review_learnings_working_tree_diff_includes_untracked_files(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-review-learnings.py",
            "sd_review_learnings_untracked_diff",
        )
        root = Path(tempfile.mkdtemp(prefix="sd-learnings-untracked-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.run_git(root, "init", "--quiet")
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "README.md").write_text("# base\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "--quiet", "-m", "seed")

        (root / "README.md").write_text(
            "# base\ntracked-change-line\n", encoding="utf-8"
        )
        untracked = root / "notes" / "untracked.md"
        untracked.parent.mkdir()
        untracked.write_text("untracked-learning-line\n", encoding="utf-8")
        # Untracked-but-not-a-regular-file entries must be skipped, not diffed.
        (root / "dangling-link").symlink_to("missing-target")

        diff_text = module.build_local_diff(root, base=None, include_working_tree=True)

        self.assertIn("+tracked-change-line", diff_text)
        self.assertIn("notes/untracked.md", diff_text)
        self.assertIn("+untracked-learning-line", diff_text)
        self.assertNotIn("dangling-link", diff_text)


if __name__ == "__main__":
    unittest.main()
