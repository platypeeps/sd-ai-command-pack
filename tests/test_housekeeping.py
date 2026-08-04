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


class HousekeepingTests(InstallTestCase):
    """Tests for housekeeping skill/script behavior and merge cleanup."""

    def finish_work_receipt_args(self, repo: Path, head_oid: str) -> list[str]:
        return [
            "--finish-work-receipt",
            str(self.write_finish_work_receipt(repo, head_oid)),
        ]

    def test_housekeeping_adapters_run_finish_work_before_housekeeping_script(
        self,
    ) -> None:
        adapters = [
            install.ROOT / "templates/.claude/commands/sd/housekeeping.md",
            install.ROOT / "templates/.commands/sd-housekeeping.md",
            install.ROOT / "templates/.gemini/commands/sd/housekeeping.toml",
            install.ROOT / "templates/.github/prompts/sd-housekeeping.prompt.md",
        ]

        for adapter in adapters:
            content = adapter.read_text(encoding="utf-8")
            finish_index = content.index("finish-work")
            script_index = content.index("scripts/sd-ai-command-pack-housekeeping.sh")
            self.assertLess(
                finish_index,
                script_index,
                f"{adapter}: finish-work must run before housekeeping script",
            )
            self.assertIn("--finish-work-receipt", content)
            self.assertNotIn("--finish-work-head", content)

    def test_housekeeping_clean_check_fails_closed_on_git_failure(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        script = str(PACK_ROOT / "scripts/sd-ai-command-pack-housekeeping.sh")
        probe = (
            f'eval "$(awk \'/^working_tree_status\\(\\)/,/^}}/\' {script})";'
            f'eval "$(awk \'/^working_tree_is_clean\\(\\)/,/^}}/\' {script})";'
            'git() { echo boom >&2; return 1; };'
            "if working_tree_is_clean; then echo OPEN; else echo CLOSED; fi"
        )
        result = subprocess.run(
            [self._bash_path, "-c", probe],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertIn("CLOSED", result.stdout)
        self.assertNotIn("OPEN", result.stdout)

    def test_housekeeping_rejects_dash_prefixed_remote(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        result = subprocess.run(
            [
                self._bash_path,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                "--remote",
                "--upload-pack=/bin/true",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('--remote value must not start with "-"', result.stdout)

    def test_housekeeping_rejects_option_like_finish_work_receipt_path(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        result = subprocess.run(
            [
                self._bash_path,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                "--finish-work-receipt",
                "--self-test",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('path must not start with "-"', result.stdout)

    def test_housekeeping_requires_finish_work_receipt_value(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        result = subprocess.run(
            [
                self._bash_path,
                str(PACK_ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                "--finish-work-receipt",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("requires a path", result.stdout)

    def _run_receipt_validator(self, receipt_path: str):
        """Exercise only the extracted validate_finish_work_receipt function.

        Hermetic: no git, gh, network, or KB access — the awk range pulls just
        the function body, so acceptance never proceeds into side-effecting
        housekeeping stages.
        """
        script = str(PACK_ROOT / "scripts/sd-ai-command-pack-housekeeping.sh")
        probe = (
            f'eval "$(awk \'/^validate_finish_work_receipt\\(\\)/,/^}}/\' {script})";'
            'validate_finish_work_receipt "$RECEIPT"'
        )
        return subprocess.run(
            [self._bash_path, "-c", probe],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "RECEIPT": receipt_path},
            check=False,
        )

    def test_finish_work_receipt_accepts_readable_regular_file(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt = Path(temp_dir) / "receipt.json"
            receipt.write_text("{}\n", encoding="utf-8")
            result = self._run_receipt_validator(str(receipt))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout, "")

    def test_finish_work_receipt_rejects_missing_path(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "absent.json"
            result = self._run_receipt_validator(str(missing))
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("path does not exist", result.stdout)
            # Stable diagnostic: the host path is never echoed back.
            self.assertNotIn(str(missing), result.stdout)

    def test_finish_work_receipt_rejects_directory(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self._run_receipt_validator(temp_dir)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("not a directory", result.stdout)
            self.assertNotIn(temp_dir, result.stdout)

    def test_finish_work_receipt_rejects_symlink(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "real.json"
            target.write_text("{}\n", encoding="utf-8")
            link = Path(temp_dir) / "link.json"
            link.symlink_to(target)
            result = self._run_receipt_validator(str(link))
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("not a symlink", result.stdout)

    def test_finish_work_receipt_rejects_broken_symlink_before_existence(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            link = Path(temp_dir) / "dangling.json"
            link.symlink_to(Path(temp_dir) / "nowhere.json")
            result = self._run_receipt_validator(str(link))
            # Symlink rejection precedes the existence check.
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("not a symlink", result.stdout)

    def test_finish_work_receipt_rejects_non_regular_file(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        if not hasattr(os, "mkfifo"):
            self.skipTest("mkfifo is not available on this platform")
        with tempfile.TemporaryDirectory() as temp_dir:
            fifo = Path(temp_dir) / "pipe.json"
            os.mkfifo(fifo)
            result = self._run_receipt_validator(str(fifo))
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("must be a regular file", result.stdout)

    def test_finish_work_receipt_rejects_unreadable_file(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root bypasses filesystem read permissions")
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt = Path(temp_dir) / "secret.json"
            receipt.write_text("{}\n", encoding="utf-8")
            os.chmod(receipt, 0)
            try:
                result = self._run_receipt_validator(str(receipt))
            finally:
                os.chmod(receipt, 0o600)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("is not readable", result.stdout)

    def test_finish_work_receipt_rejected_in_main_before_side_effects(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    self._bash_path,
                    str(PACK_ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                    "--finish-work-receipt",
                    temp_dir,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("not a directory", result.stdout)
            # Fail-fast: never reaches the branch/KB/network phase.
            self.assertNotIn("start branch", result.stdout)

    def test_housekeeping_default_branch_ignores_gh_null(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        script = str(PACK_ROOT / "scripts/sd-ai-command-pack-housekeeping.sh")
        probe = (
            'REMOTE=origin; GITHUB_REPO_SLUG=""; DEFAULT_BRANCH="";'
            "have() { return 0; };"
            "add_anomaly() { :; };"
            "gh() { printf 'null\\n'; };"
            "git() {"
            '  case "$1 $*" in'
            '    "symbolic-ref"*) return 1 ;;'
            '    "show-ref"*"refs/remotes/origin/main") return 0 ;;'
            "  esac; return 1; };"
            f'eval "$(awk \'/^detect_default_branch\\(\\)/,/^}}/\' {script})";'
            'detect_default_branch; printf "branch=%s\\n" "$DEFAULT_BRANCH"'
        )
        result = subprocess.run(
            [self._bash_path, "-c", probe],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertIn("branch=main", result.stdout)
        self.assertNotIn("branch=null", result.stdout)

    def _run_reconcile_recovery(
        self,
        *,
        summary_line: str,
        toolchain_exit: int = 0,
        make_helpers: bool = True,
        dry_run: int = 0,
    ) -> subprocess.CompletedProcess:
        """Drive ``reconcile_recovery_artifacts`` in isolation with a stub toolchain.

        The stub prints ``summary_line`` verbatim (the ``\\x1f``-delimited receipt
        the recovery helper's ``--format shell`` emits) and exits
        ``toolchain_exit``, so the probe exercises only the shell adapter's
        parse-and-classify branches, not the recovery helper or real git.
        """
        script = str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")
        with tempfile.TemporaryDirectory() as script_dir:
            if make_helpers:
                (Path(script_dir) / "sd-ai-command-pack-recovery-artifacts.py").write_text(
                    "# stub helper; the toolchain stub ignores it\n", encoding="utf-8"
                )
                (Path(script_dir) / "sd-ai-command-pack-toolchain.sh").write_text(
                    '#!/usr/bin/env bash\nprintf \'%s\\n\' "$SUMMARY_LINE"\nexit "${TOOLCHAIN_EXIT:-0}"\n',
                    encoding="utf-8",
                )
            probe = (
                "set -uo pipefail;"
                f"SCRIPT_DIR={script_dir!r};"
                f"DRY_RUN={dry_run};"
                "FIELD_SEPARATOR=$'\\x1f';"
                "ACTIONS=(); ACTION_CODES=(); ANOMALIES=(); ANOMALY_CODES=();"
                'add_action() { ACTION_CODES+=("$1"); shift; ACTIONS+=("$*"); };'
                'add_anomaly() { ANOMALY_CODES+=("$1"); shift; ANOMALIES+=("$*"); };'
                f"eval \"$(awk '/^reconcile_recovery_artifacts\\(\\)/,/^}}/' {script})\";"
                "reconcile_recovery_artifacts;"
                'printf "ACTION_CODES=%s\\n" "${ACTION_CODES[*]-}";'
                'printf "ANOMALY_CODES=%s\\n" "${ANOMALY_CODES[*]-}";'
                'printf "ANOMALIES=%s\\n" "${ANOMALIES[*]-}"'
            )
            env = dict(
                os.environ,
                SUMMARY_LINE=summary_line,
                TOOLCHAIN_EXIT=str(toolchain_exit),
            )
            return subprocess.run(
                [self._bash_path, "-c", probe],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                env=env,
            )

    def test_reconcile_recovery_artifacts_maps_summary_to_actions(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        us = "\x1f"

        # Proven-safe retire with no failures: one retired action, no anomaly.
        result = self._run_reconcile_recovery(summary_line=f"1{us}0{us}0{us}")
        self.assertIn("ACTION_CODES=recovery_artifacts_retired", result.stdout)
        self.assertNotIn("recovery_cleanup", result.stdout)
        self.assertNotIn("recovery_helper_missing", result.stdout)

        # Dry-run intent is previewed, never claimed as done.
        result = self._run_reconcile_recovery(summary_line=f"2{us}1{us}0{us}", dry_run=1)
        self.assertIn("ACTION_CODES=recovery_artifacts_retire_previewed", result.stdout)

        # A failed retire surfaces one bounded-detail anomaly; a conservatively
        # preserved artifact never becomes an anomaly and nothing is retired.
        result = self._run_reconcile_recovery(summary_line=f"0{us}1{us}1{us}worktree locked")
        self.assertIn("recovery_cleanup_incomplete", result.stdout)
        self.assertIn("worktree locked", result.stdout)
        self.assertNotIn("recovery_artifacts_retired", result.stdout)

        # Missing helper, malformed receipt, and a non-zero toolchain exit each
        # fail closed with exactly one distinct anomaly and retire nothing.
        result = self._run_reconcile_recovery(summary_line="", make_helpers=False)
        self.assertIn("recovery_helper_missing", result.stdout)
        self.assertNotIn("recovery_artifacts_retired", result.stdout)

        result = self._run_reconcile_recovery(summary_line="garbage-no-separator")
        self.assertIn("recovery_cleanup_incomplete", result.stdout)
        self.assertNotIn("recovery_artifacts_retired", result.stdout)

        result = self._run_reconcile_recovery(summary_line="", toolchain_exit=3)
        self.assertIn("recovery_cleanup_failed", result.stdout)
        self.assertNotIn("recovery_artifacts_retired", result.stdout)

    def test_review_pr_skill_auto_dispatches_housekeeping_after_merge(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")
        adapter_paths = [
            install.ROOT / "templates/.claude/commands/sd/review-pr.md",
            install.ROOT / "templates/.commands/sd-review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
        ]

        self.assertIn("Post-Merge Handoff", skill)
        self.assertIn('PR_STATE" = "MERGED"', skill)
        self.assertIn("bash scripts/sd-ai-command-pack-housekeeping.sh", skill)
        self.assertIn("not a background GitHub webhook", skill)
        for adapter_path in adapter_paths:
            content = adapter_path.read_text(encoding="utf-8")
            self.assertIn("If the PR is merged while this command is running", content)
            self.assertIn("post-merge cleanup workflow", content)

    def test_housekeeping_skill_and_script_describe_expected_clean_state(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/sd-housekeeping/SKILL.md"
        ).read_text(encoding="utf-8")
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")
        result = subprocess.run(
            [
                "bash",
                "-n",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        for text in [
            "Expected clean state",
            "Anomalies",
            "repo-wide open",
            "alone does not block",
            "current-stream cleanup",
            "SD finish-work flow",
            "execute the `sd-finish-work` flow",
            "Housekeeping completed cleanly.",
            "Final state:",
            "PR #<number>: merged at <timestamp>",
            "Insight:",
            "evidence-backed observation",
            "Do not add filler insights",
            "No open or planned Trellis work — backlog is clear.",
            "Always end with the numbered `Next Steps` section",
            "discovered during this session",
            "existing Trellis tasks that are already",
            "high-value Trellis task candidates",
            "The current Trellis task (its id + status, or `none active`).",
            "PR review rounds:",
            "--no-auto-merge",
            "--finish-work-receipt <path>",
            "--dependency-pr <number>",
            "sd-ai-command-pack-pr-eligibility.py",
        ]:
            self.assertIn(text, skill)
        for text in [
            "--no-auto-merge",
            "--finish-work-receipt",
            "--dependency-pr",
            "--merge-strategy",
            "evaluate_pr_eligibility()",
            "evaluate_dependency_pr_eligibility()",
            "sd-ai-command-pack-pr-eligibility.py",
            "PR #$pr_number is open, green, comment-clean",
            "merge_ready_open_pr()",
            "failed to merge PR #$pr_number; resolve branch protection",
            "unable to resolve GitHub PR metadata for $branch",
            "confirmed PR #$pr_number merged",
            'GH_REPO_ARGS=(--repo "$GITHUB_REPO_SLUG")',
            "gh_pr_view()",
            'gh pr view "${GH_REPO_ARGS[@]}" "$@"',
            'gh pr view "$@"',
            'gh_pr_list --state merged --head="$branch"',
            "pruned $REMOTE after remote branch deletion",
            'git remote get-url "$REMOTE"',
            'gh repo view "$GITHUB_REPO_SLUG"',
            "github_repo_from_remote_url()",
            '"${GH_REPO_ARGS[@]}"',
            '-- "$branch"',
            'git rev-parse --verify "refs/heads/$branch^{commit}"',
            'git branch -D -- "$branch"',
            "ls_remote_status",
            'git ls-remote --exit-code "$REMOTE" "refs/heads/$branch"',
            'elif [ "$ls_remote_status" -eq 2 ]; then',
            'git push "$REMOTE" ":refs/heads/$branch"',
            "remote branch $REMOTE/$branch is at $remote_head_oid",
            "left the remote branch untouched",
            "failed to check whether remote branch $REMOTE/$branch exists",
            "would fast-forward $DEFAULT_BRANCH from $REMOTE/$DEFAULT_BRANCH",
            "run_status_report()",
            "sd-ai-command-pack-status.py",
            "sd-ai-command-pack-toolchain.sh",
            "--expect-clean",
            "--refs-refreshed",
            "--prior-anomaly",
            "REFS_REFRESHED=1",
            "refresh_obsidian_kb()",
            "sd-ai-command-pack-update-spec-kb.py",
            "Obsidian KB refresh failed",
        ]:
            self.assertIn(text, script)
        self.assertNotIn("--if-present", script)
        self.assertNotIn("the pack helper is missing;", script)
        self.assertIn("a required pack helper is missing or unreadable;", script)
        self.assertNotIn("resolve the reported conflict", script)
        self.assertIn("resolve the reported issue", script)
        self.assertIn("An absent `.obsidian-kb` is\n   created", skill)

        refresh_index = script.index("if ! refresh_obsidian_kb; then")
        fetch_index = script.index("fetch_and_prune", refresh_index)
        route_index = script.index("route_branch_pr_lifecycle", refresh_index)
        self.assertLess(refresh_index, fetch_index)
        self.assertLess(refresh_index, route_index)

    def test_housekeeping_kb_refresh_contract_covers_creation_success_and_failure(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        script = str(
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        )
        function_source = (
            f'eval "$(awk \'/^refresh_obsidian_kb\\(\\)/,/^}}/\' {script})";'
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir()
            toolchain = scripts_dir / "sd-ai-command-pack-toolchain.sh"
            helper = scripts_dir / "sd-ai-command-pack-update-spec-kb.py"
            helper.write_text("# fixture\n", encoding="utf-8")
            marker = root / "invocation.txt"
            toolchain.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" > \"$KB_MARKER\"\n"
                "exit \"${KB_RESULT:-0}\"\n",
                encoding="utf-8",
            )

            base_probe = (
                "ACTIONS=(); ANOMALIES=(); DRY_RUN=0;"
                f'SCRIPT_DIR={str(scripts_dir)!r};'
                "add_action() { ACTIONS+=(\"$*\"); };"
                "add_anomaly() { ANOMALIES+=(\"$*\"); };"
                f"{function_source}"
                "refresh_obsidian_kb; rc=$?;"
                'printf "rc=%s\\nactions=%s\\nanomalies=%s\\n" '
                '"$rc" "${ACTIONS[*]-}" "${ANOMALIES[*]-}"'
            )

            absent = subprocess.run(
                [self._bash_path, "-c", base_probe],
                cwd=root,
                env={**os.environ, "KB_MARKER": str(marker)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(absent.returncode, 0, absent.stdout)
            self.assertIn("rc=0", absent.stdout)
            self.assertIn("refreshed .obsidian-kb after finish-work", absent.stdout)
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                f"run-python -- {helper}",
            )

            (root / ".obsidian-kb").mkdir()
            marker.unlink()
            success = subprocess.run(
                [self._bash_path, "-c", base_probe],
                cwd=root,
                env={**os.environ, "KB_MARKER": str(marker)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(success.returncode, 0, success.stdout)
            self.assertIn("rc=0", success.stdout)
            self.assertIn("refreshed .obsidian-kb after finish-work", success.stdout)
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                f"run-python -- {helper}",
            )

            failure = subprocess.run(
                [self._bash_path, "-c", base_probe],
                cwd=root,
                env={
                    **os.environ,
                    "KB_MARKER": str(marker),
                    "KB_RESULT": "7",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(failure.returncode, 0, failure.stdout)
            self.assertIn("rc=1", failure.stdout)
            self.assertIn("Obsidian KB refresh failed", failure.stdout)
            self.assertIn(
                "bash scripts/sd-ai-command-pack-toolchain.sh run-python -- "
                "scripts/sd-ai-command-pack-update-spec-kb.py",
                failure.stdout,
            )

    def test_housekeeping_kb_refresh_skips_read_only_target_but_blocks_other_failures(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        script = str(
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        )
        function_source = (
            f'eval "$(awk \'/^refresh_obsidian_kb\\(\\)/,/^}}/\' {script})";'
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scripts_dir = root / "scripts"
            scripts_dir.mkdir()
            toolchain = scripts_dir / "sd-ai-command-pack-toolchain.sh"
            helper = scripts_dir / "sd-ai-command-pack-update-spec-kb.py"
            helper.write_text("# fixture\n", encoding="utf-8")
            # Emit the KB helper's diagnostic text and exit with the KB helper's
            # exit code, so refresh_obsidian_kb can classify the failure.
            toolchain.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "${KB_OUTPUT:-}" >&2\n'
                'exit "${KB_RESULT:-0}"\n',
                encoding="utf-8",
            )
            (root / ".obsidian-kb").mkdir()

            probe = (
                "ACTIONS=(); ANOMALIES=(); DRY_RUN=0;"
                f"SCRIPT_DIR={str(scripts_dir)!r};"
                'add_action() { ACTIONS+=("$*"); };'
                'add_anomaly() { ANOMALIES+=("$*"); };'
                f"{function_source}"
                "refresh_obsidian_kb; rc=$?;"
                'printf "rc=%s\\nactions=%s\\nanomalies=%s\\n" '
                '"$rc" "${ACTIONS[*]-}" "${ANOMALIES[*]-}"'
            )

            # A read-only target (exit 2 with an EACCES diagnostic) is advisory:
            # the merge gate continues instead of blocking (finding #7).
            read_only = subprocess.run(
                [self._bash_path, "-c", probe],
                cwd=root,
                env={
                    **os.environ,
                    "KB_RESULT": "2",
                    "KB_OUTPUT": (
                        "error: failed to refresh .obsidian-kb: "
                        "[Errno 13] Permission denied: '/vault/note.md'"
                    ),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(read_only.returncode, 0, read_only.stdout)
            self.assertIn("rc=0", read_only.stdout)
            self.assertIn("kb_refresh_skipped", read_only.stdout)
            self.assertNotIn("kb_refresh_failed", read_only.stdout)

            # A non-read-only OSError (exit 2, ENOENT) still hard-blocks.
            other = subprocess.run(
                [self._bash_path, "-c", probe],
                cwd=root,
                env={
                    **os.environ,
                    "KB_RESULT": "2",
                    "KB_OUTPUT": (
                        "error: failed to refresh .obsidian-kb: "
                        "[Errno 2] No such file or directory: '/vault'"
                    ),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(other.returncode, 0, other.stdout)
            self.assertIn("rc=1", other.stdout)
            self.assertIn("Obsidian KB refresh failed", other.stdout)
            self.assertNotIn("kb_refresh_skipped", other.stdout)

    def test_housekeeping_dry_run_previews_branch_cleanup_without_final_state_anomaly(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        self.write_housekeeping_gh_stub(stub_bin, head_oid)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--dry-run",
            ],
            cwd=repo,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("would run: git fetch --prune origin", result.stdout)
        self.assertIn("confirmed PR #6 merged", result.stdout)
        self.assertIn("would switch to main", result.stdout)
        self.assertIn("would fast-forward main from origin/main", result.stdout)
        self.assertIn("would delete local branch feature/cleanup", result.stdout)
        self.assertIn("would delete remote branch origin/feature/cleanup", result.stdout)
        self.assertIn("dry-run preview: skipped final git-state verification", result.stdout)
        self.assertNotIn("still on feature/cleanup; skipped branch deletion", result.stdout)
        self.assertNotIn("current branch is feature/cleanup, expected main", result.stdout)
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_json_reserves_stdout_for_typed_result(self) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        self.write_housekeeping_gh_stub(stub_bin, head_oid)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                "--dry-run",
                "--json",
            ],
            cwd=repo,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["kind"], "housekeeping")
        self.assertEqual(payload["outcome"], {"reasonCodes": [], "status": "clean"})
        self.assertEqual(payload["status"]["mode"], "local")
        self.assertIsNone(payload["eligibility"])
        action_codes = {item["code"] for item in payload["actions"]}
        self.assertIn("pull_request_merge_confirmed", action_codes)
        self.assertIn("local_branch_delete_previewed", action_codes)
        self.assertIn("==> SD AI command pack housekeeping", result.stderr)
        self.assertNotIn("==> SD AI command pack housekeeping", result.stdout)

    def test_housekeeping_reports_fetch_failure_without_empty_action_crash(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        self.write_housekeeping_gh_stub(stub_bin, head_oid)
        self.run_git(repo, "switch", "main")
        self.run_git(
            repo,
            "remote",
            "set-url",
            "origin",
            str(repo.parent / "missing.git"),
        )

        result = subprocess.run(
            [
                self._bash_path,
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
            ],
            cwd=repo,
            env={**os.environ, "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "==> Tasks performed\n- refreshed .obsidian-kb after finish-work",
            result.stdout,
        )
        self.assertIn("git fetch --prune origin failed", result.stdout)
        self.assertIn("git pull --ff-only origin main failed", result.stdout)
        self.assertNotIn("unbound variable", result.stdout)

    def test_housekeeping_skips_remote_delete_when_remote_branch_moved(self) -> None:
        repo, remote, stub_bin, merged_head_oid = self.make_housekeeping_repo()
        self.write_housekeeping_gh_stub(stub_bin, merged_head_oid)
        (repo / "remote-only.txt").write_text("new remote commit\n", encoding="utf-8")
        self.run_git(repo, "add", "remote-only.txt")
        self.run_git(repo, "commit", "-m", "remote branch moved")
        moved_head_oid = self.git_output(repo, "rev-parse", "HEAD")
        self.run_git(repo, "push", "origin", "feature/cleanup")
        self.run_git(repo, "reset", "--hard", merged_head_oid)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("deleted local branch feature/cleanup", result.stdout)
        self.assertIn(
            f"remote branch origin/feature/cleanup is at {moved_head_oid}",
            result.stdout,
        )
        self.assertIn(f"merged PR #6 ended at {merged_head_oid}", result.stdout)
        self.assertIn("left the remote branch untouched", result.stdout)
        self.assertNotIn("deleted remote branch origin/feature/cleanup", result.stdout)
        self.assertEqual(
            self.git_output(remote, "rev-parse", "refs/heads/feature/cleanup"),
            moved_head_oid,
        )

    def test_housekeeping_auto_merges_green_comment_clean_pr_then_cleans_up(
        self,
    ) -> None:
        repo, remote, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                *self.finish_work_receipt_args(repo, head_oid),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "PR #6 is open, green, comment-clean, and matches local feature/cleanup",
            result.stdout,
        )
        self.assertIn("merged PR #6 with merge strategy", result.stdout)
        self.assertIn("deleted local branch feature/cleanup", result.stdout)
        self.assertIn("deleted remote branch origin/feature/cleanup", result.stdout)
        self.assertIn("==> Anomalies\nnone", result.stdout)
        self.assertEqual(self.git_output(repo, "branch", "--show-current"), "main")
        remote_branch = subprocess.run(
            [
                "git",
                "ls-remote",
                "--exit-code",
                str(remote),
                "refs/heads/feature/cleanup",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(remote_branch.returncode, 2, remote_branch.stdout)

    def test_housekeeping_json_embeds_the_exact_eligibility_receipt(self) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                *self.finish_work_receipt_args(repo, head_oid),
                "--json",
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outcome"]["status"], "clean")
        self.assertEqual(payload["eligibility"]["status"], "eligible")
        self.assertEqual(payload["eligibility"]["head"]["startOid"], head_oid)
        self.assertEqual(payload["identity"]["finishWork"]["headOid"], head_oid)
        self.assertTrue(payload["identity"]["finishWork"]["verified"])
        self.assertEqual(
            payload["identity"]["finishWork"]["completionSubtype"],
            "post-archive-review-successor",
        )
        self.assertEqual(payload["identity"]["pullRequest"]["number"], 6)
        action_codes = {item["code"] for item in payload["actions"]}
        self.assertIn("pull_request_merged", action_codes)
        self.assertIn("remote_branch_deleted", action_codes)
        self.assertTrue(marker.exists())

    def test_housekeeping_merges_planning_finalization_and_preserves_tasks(
        self,
    ) -> None:
        (
            repo,
            remote,
            stub_bin,
            base_oid,
            head_oid,
        ) = self.make_planning_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)
        receipt = self.write_planning_finish_work_receipt(repo, base_oid, head_oid)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                "--finish-work-receipt",
                str(receipt),
                "--json",
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outcome"]["status"], "clean")
        self.assertEqual(payload["eligibility"]["status"], "eligible")
        self.assertEqual(payload["eligibility"]["head"]["startOid"], head_oid)
        finish_work = payload["identity"]["finishWork"]
        self.assertEqual(finish_work["headOid"], head_oid)
        self.assertTrue(finish_work["verified"])
        self.assertEqual(finish_work["mode"], "planning")
        # A planning receipt never carries completion evidence.
        self.assertIsNone(finish_work["completionSubtype"])
        action_codes = {item["code"] for item in payload["actions"]}
        self.assertIn("pull_request_merged", action_codes)
        self.assertTrue(marker.exists())

        # On synchronized main, every planning task is preserved in planning and
        # nothing was archived by the merge.
        self.assertEqual(self.git_output(repo, "branch", "--show-current"), "main")
        for name in (
            "07-25-planning-preserved",
            "07-25-planning-alpha",
            "07-25-planning-beta",
        ):
            record = json.loads(
                (repo / ".trellis/tasks" / name / "task.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(record["status"], "planning", name)
        self.assertFalse((repo / ".trellis/tasks/archive").exists())

    def test_housekeeping_requires_finish_work_receipt_before_auto_merge(self) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("SD finish-work evidence is missing", result.stdout)
        self.assertIn("pass its retained JSON receipt", result.stdout)
        self.assertNotIn("--finish-work-head", result.stdout)
        self.assertFalse(marker.exists())

    def test_housekeeping_dependency_pr_mode_merges_from_clean_default_branch(
        self,
    ) -> None:
        repo, _, stub_bin, pr_head_oid = self.make_housekeeping_repo()
        self.run_git(repo, "switch", "main")
        self.run_git(repo, "branch", "-D", "feature/cleanup")
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker, pr_head_oid=pr_head_oid)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--dependency-pr",
                "6",
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "dependency PR #6 is green, comment-clean, mergeable, and exact-head current",
            result.stdout,
        )
        self.assertIn("merged PR #6 with merge strategy", result.stdout)
        self.assertIn(
            "skipped post-finish Obsidian KB refresh for dependency PR mode",
            result.stdout,
        )
        self.assertEqual(self.git_output(repo, "branch", "--show-current"), "main")
        self.assertTrue(marker.exists())
        self.assertFalse((repo / ".obsidian-kb").exists())

    def test_housekeeping_rejects_stale_finish_work_receipt_before_auto_merge(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)
        stale_head = "0" * 40
        receipt = self.write_finish_work_receipt(repo, head_oid)
        receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
        receipt_payload["evidence"]["headOid"] = stale_head
        receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--finish-work-receipt",
                str(receipt),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("finish-work receipt does not match", result.stdout)
        self.assertIn("rerun sd-finish-work", result.stdout)
        self.assertFalse(marker.exists())

    def test_housekeeping_prunes_stale_tracking_ref_on_auto_delete_head_branch(
        self,
    ) -> None:
        # Regression: with GitHub auto-delete-head-branch the remote drops the
        # branch at merge time, after housekeeping's initial fetch/prune. The
        # "already absent" cleanup path must prune the stale local tracking ref
        # so the final remote-branch-absent check does not flag a false anomaly.
        repo, remote, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(
            stub_bin, marker, auto_delete_remote_branch=True
        )

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                *self.finish_work_receipt_args(repo, head_oid),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("merged PR #6 with merge strategy", result.stdout)
        self.assertIn(
            "remote branch origin/feature/cleanup is already absent",
            result.stdout,
        )
        self.assertIn(
            "pruned stale origin/feature/cleanup tracking ref",
            result.stdout,
        )
        self.assertIn(
            "remote source branch absent: origin/feature/cleanup", result.stdout
        )
        self.assertNotIn("remote source branch still tracked", result.stdout)
        self.assertIn("==> Anomalies\nnone", result.stdout)
        self.assertEqual(
            subprocess.run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/remotes/origin/feature/cleanup",
                ],
                cwd=repo,
                check=False,
            ).returncode,
            1,
            "stale remote tracking ref should be pruned",
        )

    def test_housekeeping_rejects_undeterminable_check_counts_before_auto_merge(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(
            stub_bin,
            marker,
            blocking_check_count="unknown",
        )

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                *self.finish_work_receipt_args(repo, head_oid),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "could not inspect an open PR for feature/cleanup; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

    def test_housekeeping_auto_merges_with_skipped_and_neutral_checks(self) -> None:
        # Regression: classifier-skipped lanes (SKIPPED/NEUTRAL conclusions)
        # must not block the merge gate when executed checks are green.
        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "NEUTRAL"},'
            ' {"__typename": "StatusContext", "state": "SUCCESS"}]'
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("merged PR #6 with merge strategy", result.stdout)
        self.assertTrue(marker.exists())

    def test_housekeeping_skips_auto_merge_when_all_checks_skipped(self) -> None:
        # An all-skipped run executed nothing, so it must not merge.
        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"}]'
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has no successful executed checks; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

    def test_housekeeping_skips_auto_merge_with_pending_or_failed_checks(self) -> None:
        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},'
            ' {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": null}]'
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has non-green checks; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

        result, marker = self.run_housekeeping_with_rollup(
            '[{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"},'
            ' {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}]'
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has non-green checks; skipped auto-merge",
            result.stdout,
        )
        self.assertFalse(marker.exists())

    def test_housekeeping_self_test_passes_hermetically(self) -> None:
        # The self-test must pass from a non-git directory with no gh on PATH,
        # exercising only the vendored gate logic.
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-selftest-")
        self.addCleanup(tempdir.cleanup)

        result = subprocess.run(
            [
                self._bash_path,
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--self-test",
            ],
            cwd=tempdir.name,
            env={"PATH": tempdir.name, "HOME": tempdir.name},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("self-test: all scenarios passed", result.stdout)
        for scenario in (
            "eligible receipt merges",
            "blocked receipt refuses",
            "indeterminate receipt refuses",
            "incomplete eligible receipt refuses",
            "unknown receipt status refuses",
            "unknown default branch refuses",
        ):
            self.assertIn(f"self-test: {scenario}: ok", result.stdout)

    def test_housekeeping_self_test_detects_a_neutered_gate(self) -> None:
        # Meta-regression: a sabotaged blocking-check gate must fail the
        # self-test, proving it verifies behavior rather than always passing.
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-sabotage-")
        self.addCleanup(tempdir.cleanup)
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")
        needle = 'case "$eligibility_status" in'
        self.assertIn(needle, script)
        sabotaged = Path(tempdir.name) / "sabotaged.sh"
        sabotaged.write_text(
            script.replace(needle, 'case "eligible" in'),
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, str(sabotaged), "--self-test"],
            cwd=tempdir.name,
            env={"PATH": tempdir.name, "HOME": tempdir.name},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("self-test: blocked receipt refuses: FAIL", result.stdout)

    def test_housekeeping_self_test_reports_named_failures_on_stub_errors(
        self,
    ) -> None:
        # A scenario whose collaborators error (unexpected git call) must
        # produce named FAIL lines and a failure summary, never a silent exit.
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-stuberr-")
        self.addCleanup(tempdir.cleanup)
        script = (
            install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"
        ).read_text(encoding="utf-8")
        needle = (
            '[ "$1" != 153 ] || '
            '[ "$2" != 1111111111111111111111111111111111111111 ]'
        )
        self.assertIn(needle, script)
        sabotaged = Path(tempdir.name) / "sabotaged.sh"
        sabotaged.write_text(
            script.replace(needle, '[ "$1" = "$1" ]'), encoding="utf-8"
        )

        result = subprocess.run(
            [self._bash_path, str(sabotaged), "--self-test"],
            cwd=tempdir.name,
            env={"PATH": tempdir.name, "HOME": tempdir.name},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("self-test: eligible receipt merges: FAIL", result.stdout)
        self.assertIn("scenario(s) FAILED", result.stdout)

    def test_housekeeping_no_auto_merge_leaves_open_pr_untouched(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                "--no-auto-merge",
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 for feature/cleanup is open and was not merged; left the branch untouched",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_closed_pr_reports_not_merged_without_cleanup(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        self.write_pr_lifecycle_gh_stub(stub_bin, head_oid, "CLOSED")

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 for feature/cleanup is CLOSED, not MERGED; left the branch untouched",
            result.stdout,
        )
        # A closed PR is never merged or eligibility-evaluated, and nothing is
        # deleted or switched.
        self.assertNotIn("PR #6 is open, green, comment-clean", result.stdout)
        self.assertNotIn("confirmed PR #6 merged", result.stdout)
        self.assertNotIn("deleted local branch feature/cleanup", result.stdout)
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_unresolvable_pr_leaves_branch_untouched(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        # No PR resolves from gh pr view or the merged pr list fallback.
        self.write_pr_lifecycle_gh_stub(stub_bin, head_oid, "")

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "unable to resolve GitHub PR metadata for feature/cleanup",
            result.stdout,
        )
        self.assertNotIn("confirmed PR #6 merged", result.stdout)
        self.assertNotIn("deleted local branch feature/cleanup", result.stdout)
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_json_marks_unknown_pr_state_indeterminate(self) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        # An unexpected lifecycle state must fail closed, not be treated as
        # merged or blocked.
        self.write_pr_lifecycle_gh_stub(stub_bin, head_oid, "QUEUED")

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "scripts/sd-ai-command-pack-housekeeping.sh"),
                "--json",
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outcome"]["status"], "indeterminate")
        self.assertIn(
            "pull_request_state_indeterminate", payload["outcome"]["reasonCodes"]
        )
        self.assertIsNone(payload["eligibility"])
        anomaly_codes = {item["code"] for item in payload["anomalies"]}
        self.assertIn("pull_request_state_indeterminate", anomaly_codes)
        action_codes = {item["code"] for item in payload["actions"]}
        self.assertNotIn("pull_request_merge_confirmed", action_codes)

    def test_housekeeping_counts_unresolved_review_threads_across_pages(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(
            stub_bin,
            marker,
            graphql_body=(
                "  args=\" $* \"\n"
                "  if [[ \"$args\" == *\"cursor=PAGE2\"* ]]; then\n"
                "    printf '%s\\n' '{\"data\":{\"repository\":{\"pullRequest\":{\"reviewThreads\":{\"nodes\":[{\"isResolved\":false}],\"pageInfo\":{\"hasNextPage\":false,\"endCursor\":null}}}}}}'\n"
                "  else\n"
                "    printf '%s\\n' '{\"data\":{\"repository\":{\"pullRequest\":{\"reviewThreads\":{\"nodes\":[],\"pageInfo\":{\"hasNextPage\":true,\"endCursor\":\"PAGE2\"}}}}}}'\n"
                "  fi\n"
            ),
        )

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                *self.finish_work_receipt_args(repo, head_oid),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "PR #6 has 1 unresolved review thread(s); skipped auto-merge",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(
            self.git_output(repo, "branch", "--show-current"),
            "feature/cleanup",
        )

    def test_housekeeping_rejects_invalid_github_repo_override(self) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                *self.finish_work_receipt_args(repo, head_oid),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO must be an owner/repo slug",
            result.stdout,
        )
        self.assertIn(
            "PR #6 for feature/cleanup is open and was not merged",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse(marker.exists())

    def test_housekeeping_rejects_invalid_env_merge_strategy_before_merge(
        self,
    ) -> None:
        repo, _, stub_bin, _ = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(stub_bin, marker)

        result = subprocess.run(
            ["bash", str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh")],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_MERGE_STRATEGY": "fast-forward",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "merge strategy is invalid; expected merge, squash, or rebase; skipped auto-merge",
            result.stdout,
        )
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse((repo / ".trellis/workspace/sdelmas/journal-1.md").exists())
        self.assertFalse(marker.exists())

    def test_housekeeping_reports_review_thread_inspection_failure(
        self,
    ) -> None:
        repo, _, stub_bin, head_oid = self.make_housekeeping_repo()
        marker = repo.parent / "merged-pr"
        self.write_auto_merge_gh_stub(
            stub_bin,
            marker,
            graphql_body="  exit 42\n",
        )

        result = subprocess.run(
            [
                "bash",
                str(install.ROOT / "templates/scripts/sd-ai-command-pack-housekeeping.sh"),
                *self.finish_work_receipt_args(repo, head_oid),
            ],
            cwd=repo,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_HOUSEKEEPING_GITHUB_REPO": "example/repo",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "failed to inspect review threads for PR #6; skipped auto-merge",
            result.stdout,
        )
        self.assertIn("==> Expected clean state", result.stdout)
        self.assertIn("==> Anomalies", result.stdout)
        self.assertNotIn("merged PR #6 with merge strategy", result.stdout)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
