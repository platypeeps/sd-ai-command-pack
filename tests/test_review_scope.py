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


def _sh_single_quote(value: str) -> str:
    """Quote a value for a POSIX shell single-quoted context."""
    return "'" + str(value).replace("'", "'\\''") + "'"


class ReviewScopeTests(InstallTestCase):
    """Tests for PR-body scope, Prism/Gito config, and PR review skill behavior."""

    def test_installed_shared_scripts_and_prism_rules_are_valid(self) -> None:
        root = self.make_repo(".gemini")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        script_files = self.shared_manifest_files("script")
        self.assertGreater(len(script_files), 0)
        for file in script_files:
            installed_script = root / file.target
            self.assertTrue(installed_script.is_file(), installed_script)
            self.assertEqual(
                installed_script.read_bytes(),
                file.source.read_bytes(),
                f"{installed_script}: installer should copy script bytes exactly",
            )
            if installed_script.suffix == ".sh":
                self.assert_shell_syntax_valid(installed_script)
            elif installed_script.suffix == ".py":
                self.assert_python_syntax_valid(installed_script)
            elif installed_script.suffix == ".mjs":
                self.assert_node_syntax_valid(installed_script)
            else:
                self.fail(f"unexpected installed script suffix: {installed_script}")
            self.assert_no_secret_markers(installed_script)

        prism_rules = root / ".prism/rules.json"
        self.assertTrue(prism_rules.is_file())
        self.assert_prism_rules_valid(prism_rules)
        self.assert_no_secret_markers(prism_rules)

    def test_install_file_preserves_prism_rules(self) -> None:
        root = self.make_repo()
        file = install.PackFile(
            platform="shared",
            kind="config",
            source=install.ROOT / "templates/.prism/rules.json",
            target=Path(".prism/rules.json"),
            anchor=None,
            install="always",
        )
        destination = root / ".prism/rules.json"
        destination.parent.mkdir(parents=True)
        destination.write_text("{}\n", encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=False
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(destination.read_text(encoding="utf-8"), "{}\n")

    def test_install_file_preserves_gito_config(self) -> None:
        root = self.make_repo()
        file = install.PackFile(
            platform="shared",
            kind="config",
            source=install.ROOT / "templates/.gito/config.toml",
            target=Path(".gito/config.toml"),
            anchor=None,
            install="always",
        )
        destination = root / ".gito/config.toml"
        destination.parent.mkdir(parents=True)
        destination.write_text("retries = 1\n", encoding="utf-8")

        result = install.install_file(
            file, root, force=True, dry_run=False, backup=False
        )

        self.assertEqual(result.status, "preserved")
        self.assertEqual(destination.read_text(encoding="utf-8"), "retries = 1\n")

    def test_force_preserves_existing_prism_rules(self) -> None:
        root = self.make_repo(".gemini")
        target = root / ".agents/skills/sd-review-pr/SKILL.md"
        prism_rules = root / ".prism/rules.json"
        target.parent.mkdir(parents=True)
        prism_rules.parent.mkdir(parents=True)
        target.write_text("local edit\n", encoding="utf-8")
        prism_rules.write_text('{"custom": true}\n', encoding="utf-8")

        result = self.run_install(root, "--force", "--backup")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertIn(".prism/rules.json", result.stdout)
        self.assertIn("SD PR Review Loop", target.read_text(encoding="utf-8"))
        self.assertEqual(
            prism_rules.read_text(encoding="utf-8"),
            '{"custom": true}\n',
        )
        self.assertFalse(prism_rules.with_name("rules.json.bak").exists())

    def test_preserves_existing_prism_rules_without_force(self) -> None:
        root = self.make_repo(".gemini")
        prism_rules = root / ".prism/rules.json"
        prism_rules.parent.mkdir(parents=True)
        prism_rules.write_text('{"custom": true}\n', encoding="utf-8")

        result = self.run_install(root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertIn(".prism/rules.json", result.stdout)
        self.assertNotIn("Conflicts:", result.stdout)
        self.assertNotIn("Re-run with --force", result.stdout)
        self.assertEqual(
            prism_rules.read_text(encoding="utf-8"),
            '{"custom": true}\n',
        )

    def test_force_preserved_prism_rules_are_excluded_from_diff_check(self) -> None:
        root = self.make_repo()
        prism_rules = root / ".prism/rules.json"
        prism_rules.parent.mkdir(parents=True)
        prism_rules.write_text('{"custom": false}\n', encoding="utf-8")
        self.run_git(root, "add", ".prism/rules.json")
        prism_rules.write_text('{"custom": true}   \n', encoding="utf-8")

        result = self.run_install(root, "--force", skip_diff_check=False)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("preserved", result.stdout)
        self.assertEqual(
            prism_rules.read_text(encoding="utf-8"),
            '{"custom": true}   \n',
        )

    def test_pr_body_scope_script_warns_without_body(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            ".cursor/commands/sd-housekeeping.md\n",
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
        self.assertIn("detected Automation scope", result.stdout)
        self.assertIn("PR body not provided", result.stdout)

    def test_review_scope_advisory_names_required_section_without_pr(self) -> None:
        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "repomix-map.md").write_text("# map\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_SCOPE_CHECK": "advisory",
                # Pinned so the advisory resolves to unknown:gh_disabled instead
                # of shelling out to the developer's real gh from a temp repo.
                # Both unknown states emit this same pre-PR wording.
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        # Advisory mode never fails; with no evidence about a PR body it names
        # the section the eventual PR body must carry.
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("the PR body must include", result.stdout)
        self.assertIn("Tooling/generated scope:", result.stdout)
        # Stable machine marker consumed by the preflight; pinned so it cannot
        # drift out from under the mjs matcher.
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)

    def write_gh_pr_body_stub(
        self, root: Path, body: str, state: str = "OPEN"
    ) -> Path:
        """Install a `gh` stub answering `pr view` with a fixed body and state.

        Returns the directory to prepend to PATH. Advisory cases that must
        exercise the shipped resolved-body path cannot use
        SD_AI_COMMAND_PACK_SCOPE_PR_BODY, which short-circuits above gh. `state`
        defaults to OPEN; pass CLOSED/MERGED to exercise the closed-PR-bleed
        guard (finding #6).
        """
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir(exist_ok=True)
        payload = json.dumps(
            {
                "title": "Change",
                "body": body,
                "url": "https://example.test/pr/1",
                "state": state,
            }
        )
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [ "${1:-}" = pr ] && [ "${2:-}" = view ]; then\n'
            f"  printf '%s\\n' {_sh_single_quote(payload)}\n"
            "else\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)
        return stub_bin

    def run_advisory_scope(
        self, root: Path, **env: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={**os.environ, "SD_AI_COMMAND_PACK_SCOPE_CHECK": "advisory", **env},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def commit_installed_repo(self, root: Path) -> None:
        """Commit the install so HEAD resolves.

        `make_repo` only runs `git init`, and the script warns about an
        unresolvable HEAD. Cases that assert the advisory emitted no warning at
        all need that unrelated warning gone, not merely tolerated.
        """
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

    def make_scoped_advisory_repo(self) -> Path:
        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.commit_installed_repo(root)
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "repomix-map.md").write_text(
            "# map\n\nregenerated\n", encoding="utf-8"
        )
        return root

    def test_review_scope_advisory_is_silent_when_provided_body_satisfies(self) -> None:
        root = self.make_scoped_advisory_repo()

        result = self.run_advisory_scope(
            root,
            SD_AI_COMMAND_PACK_SCOPE_PR_BODY=(
                "Tooling/generated scope: regenerated the repository map."
            ),
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertNotIn("warning:", result.stdout)

    def test_review_scope_advisory_warns_pr_exists_when_provided_body_lacks_section(
        self,
    ) -> None:
        root = self.make_scoped_advisory_repo()

        result = self.run_advisory_scope(
            root, SD_AI_COMMAND_PACK_SCOPE_PR_BODY="Unrelated body text."
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        # "Add it before opening the PR" is wrong once a body exists.
        self.assertIn("does not include", result.stdout)
        self.assertNotIn("before opening the PR", result.stdout)

    def test_review_scope_advisory_warns_when_gh_is_disabled(self) -> None:
        root = self.make_scoped_advisory_repo()

        result = self.run_advisory_scope(root, SD_AI_COMMAND_PACK_SCOPE_CHECK_GH="0")

        # Absence of evidence is not evidence the body is fine.
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertIn("the PR body must include", result.stdout)

    def test_claude_hooks_are_scoped_as_copied(self) -> None:
        """`.claude/hooks/*` is a copied/generated platform surface.

        Paired with the JavaScript assertion in
        tests/test_review_preflight.py so the shell review-scope classifier and
        the mjs preflight classifier cannot silently diverge on platform hook
        paths: a change under `.claude/hooks/` must be scoped identically by
        both. A `.claude/hooks/` path can match no other scope category, so the
        advisory firing here proves the copied-path classification.
        """
        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        hook = root / ".claude" / "hooks" / "session-start.py"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("# baseline\n", encoding="utf-8")
        self.commit_installed_repo(root)
        hook.write_text("# baseline\nadjusted\n", encoding="utf-8")

        result = self.run_advisory_scope(root, SD_AI_COMMAND_PACK_SCOPE_CHECK_GH="0")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertIn("the PR body must include", result.stdout)

    def test_gemini_settings_are_scoped_as_copied(self) -> None:
        """`.gemini/settings.json` is a copied/generated platform surface.

        Paired with the JavaScript assertion in
        tests/test_review_preflight.py so the shell review-scope classifier and
        the mjs preflight classifier cannot silently diverge on platform
        settings paths: a change to `.gemini/settings.json` must be scoped
        identically by both. The advisory firing here proves the shell side's
        copied-path classification.
        """
        root = self.make_repo(".gemini")
        self.assertEqual(self.run_install(root).returncode, 0)
        settings = root / ".gemini" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("{}\n", encoding="utf-8")
        self.commit_installed_repo(root)
        settings.write_text('{"adjusted": true}\n', encoding="utf-8")

        result = self.run_advisory_scope(root, SD_AI_COMMAND_PACK_SCOPE_CHECK_GH="0")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertIn("the PR body must include", result.stdout)

    def test_review_scope_advisory_is_silent_when_resolved_body_satisfies(self) -> None:
        """The shipped path: body resolved from gh, not supplied by env."""
        root = self.make_scoped_advisory_repo()
        stub_bin = self.write_gh_pr_body_stub(
            root, "Tooling/generated scope: regenerated the repository map."
        )

        result = self.run_advisory_scope(
            root, PATH=f"{stub_bin}{os.pathsep}{os.environ['PATH']}"
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertNotIn("warning:", result.stdout)

    def test_review_scope_ignores_closed_same_branch_pr_body(self) -> None:
        """Finding #6: a CLOSED same-branch PR's body must not bleed in.

        `gh pr view` resolves the branch's PR and returns a CLOSED one when no
        open PR exists. Its (possibly stale) body is not authoritative: a closed
        body that HAPPENS to carry the scope section must not count as positive
        evidence, and a closed body that lacks it must not be the reason the
        check fails. Pre-publication the intended body is env-provided.
        """
        # A closed PR whose body DOES contain the section must not be trusted as
        # satisfied — the resolver has no open evidence, so advisory still warns.
        root = self.make_scoped_advisory_repo()
        stub_bin = self.write_gh_pr_body_stub(
            root,
            "Tooling/generated scope: regenerated the repository map.",
            state="CLOSED",
        )
        result = self.run_advisory_scope(
            root, PATH=f"{stub_bin}{os.pathsep}{os.environ['PATH']}"
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)

        # With the intended body provided via env, the branch passes without any
        # override reaching for the closed PR body.
        result = self.run_advisory_scope(
            root,
            PATH=f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
            SD_AI_COMMAND_PACK_SCOPE_PR_BODY=(
                "Tooling/generated scope: refreshed copied pack docs."
            ),
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("sd-ai-command-pack-scope-advisory:", result.stdout)

    def test_review_scope_closed_pr_required_mode_fails_distinctly(self) -> None:
        """A required-mode run with only a closed PR fails with a closed-PR
        diagnosis, not the generic resolved-body failure — so the operator is
        told to open the PR / provide the body rather than chasing a phantom
        unsatisfied body."""
        root = self.make_scoped_advisory_repo()
        stub_bin = self.write_gh_pr_body_stub(
            root, "Fixes a product bug.", state="MERGED"
        )
        result = subprocess.run(
            ["bash", "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("closed/merged PR", result.stdout)
        self.assertNotIn(
            "does not include a recognized tooling/generated scope section",
            result.stdout,
        )

    def test_review_scope_advisory_warns_when_resolved_body_lacks_section(self) -> None:
        root = self.make_scoped_advisory_repo()
        stub_bin = self.write_gh_pr_body_stub(root, "Fixes a product bug.")

        result = self.run_advisory_scope(
            root, PATH=f"{stub_bin}{os.pathsep}{os.environ['PATH']}"
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertIn("does not include", result.stdout)
        self.assertNotIn("before opening the PR", result.stdout)

    def test_review_scope_advisory_never_calls_gh_without_a_scoped_change(self) -> None:
        """The zero-scope early return is the whole cost bound of this feature.

        Asserting empty output alone would not catch a helper call hoisted above
        the early return: output stays empty while every branch in the repo
        starts paying a gh round-trip inside `make check`.
        """
        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.commit_installed_repo(root)

        sentinel = root.parent / f"{root.name}-gh-was-called"
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir(exist_ok=True)
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            f"touch {_sh_single_quote(str(sentinel))}\n"
            "exit 1\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

        (root / "product.txt").write_text("not a tooling file\n", encoding="utf-8")

        result = self.run_advisory_scope(
            root, PATH=f"{stub_bin}{os.pathsep}{os.environ['PATH']}"
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertFalse(
            sentinel.exists(),
            "gh was invoked on a branch with no tooling/generated change",
        )

    def test_review_scope_advisory_prefers_satisfying_body_over_disabled_gh(
        self,
    ) -> None:
        """Positive evidence outranks every reason the resolver has to give up.

        Cases 1 and 3 each hold one half of this combination and neither holds
        both, so this is the only proof that a matching supplied body is
        evaluated above the gh-disabled short-circuit.
        """
        root = self.make_scoped_advisory_repo()

        result = self.run_advisory_scope(
            root,
            SD_AI_COMMAND_PACK_SCOPE_CHECK_GH="0",
            SD_AI_COMMAND_PACK_SCOPE_PR_BODY=(
                "Tooling/generated scope: regenerated the repository map."
            ),
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        self.assertNotIn("warning:", result.stdout)

    def write_gh_raw_stub(self, root: Path, payload: str) -> Path:
        """Install a `gh` stub whose `pr view` output is not valid JSON."""
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir(exist_ok=True)
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [ "${1:-}" = pr ] && [ "${2:-}" = view ]; then\n'
            f"  printf '%s\\n' {_sh_single_quote(payload)}\n"
            "else\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)
        return stub_bin

    def test_review_scope_fails_named_when_the_pr_body_cannot_be_parsed(self) -> None:
        """A crashing parser used to abort through `set -e` with no `error:` line.

        This is the one enforcing-mode behavior change in the resolver split, so
        it needs its own case: the exit status is the same 1 it always was, and
        only the presence of a named message distinguishes the new behavior from
        the old.
        """
        root = self.make_scoped_advisory_repo()
        stub_bin = self.write_gh_raw_stub(root, "not json at all")

        result = subprocess.run(
            ["bash", "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "could not parse the PR body returned by gh",
            result.stdout,
        )

    def test_review_scope_advisory_warns_when_the_pr_body_cannot_be_parsed(
        self,
    ) -> None:
        """The same malformed body must never fail the advisory."""
        root = self.make_scoped_advisory_repo()
        stub_bin = self.write_gh_raw_stub(root, "not json at all")

        result = self.run_advisory_scope(
            root, PATH=f"{stub_bin}{os.pathsep}{os.environ['PATH']}"
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("sd-ai-command-pack-scope-advisory:", result.stdout)
        # No body was resolved, so claiming one "does not include" the section
        # would be a statement the script cannot support.
        self.assertIn("the PR body must include", result.stdout)
        self.assertNotIn("could not parse", result.stdout)

    def test_review_scope_off_suppresses_advisory(self) -> None:
        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "repomix-map.md").write_text("# map\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={**os.environ, "SD_AI_COMMAND_PACK_SCOPE_CHECK": "off"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("the PR body must include", result.stdout)

    def test_docs_show_mixed_tooling_and_ci_review_pr_body_scope_example(
        self,
    ) -> None:
        readme = (install.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("review-scope and PR-body", readme)
        self.assertIn(
            "[docs/SD_AI_COMMAND_PACK.md](docs/SD_AI_COMMAND_PACK.md#updating-the-pack)",
            readme,
        )
        self.assertNotIn("Tooling/generated scope:", readme)
        self.assertNotIn("CI/review scope:", readme)

        for doc_path in [
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]:
            content = doc_path.read_text(encoding="utf-8")
            self.assertIn("Tooling/generated scope:", content, doc_path)
            self.assertIn("CI/review scope:", content, doc_path)
            self.assertIn("command invocation", content, doc_path)
            self.assertIn("SD_AI_COMMAND_PACK_SCOPE_PR_BODY", content, doc_path)
            self.assertNotIn("REVIEW_PREFLIGHT_PR_BODY", content, doc_path)

    def test_retired_pr_body_env_is_absent_from_current_shipped_guidance(
        self,
    ) -> None:
        guidance_kinds = {"skill", "command", "prompt", "doc"}
        guidance_sources = sorted(
            {
                file.source
                for file in self._manifest_files
                if file.kind in guidance_kinds
            }
        )
        check_skill = install.ROOT / "templates/.agents/skills/sd-check/SKILL.md"

        self.assertIn(check_skill, guidance_sources)
        self.assertGreater(len(guidance_sources), 1)
        for source in guidance_sources:
            with self.subTest(source=source):
                self.assertNotIn(
                    "REVIEW_PREFLIGHT_PR_BODY",
                    source.read_text(encoding="utf-8"),
                )

    def test_pr_body_scope_default_rule_patterns_match_representatives(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_pr_body_scope_default_rules",
        )

        def representative(pattern: str) -> str:
            if pattern.endswith("/**"):
                base = pattern[:-3].replace("*", "x")
                return f"{base}/nested/file.md"
            return pattern.replace("*", "x")

        checked = 0
        for rule in module.DEFAULT_RULES:
            for pattern in rule.patterns:
                checked += 1
                candidate = representative(pattern)
                self.assertTrue(
                    module._matches_pattern(candidate, pattern),
                    f"{pattern!r} failed to match its representative {candidate!r}",
                )
                self.assertFalse(
                    module._matches_pattern("src/unrelated/module.py", pattern),
                    f"{pattern!r} unexpectedly matched an unrelated path",
                )
        self.assertGreater(checked, 0)

        wildcard_base_pattern = ".claude/skills/sd-*/**"
        self.assertTrue(
            module._matches_pattern(
                ".claude/skills/sd-review-pr/SKILL.md", wildcard_base_pattern
            )
        )
        self.assertTrue(
            module._matches_pattern(".claude/skills/sd-review-pr", wildcard_base_pattern)
        )
        self.assertFalse(
            module._matches_pattern(
                ".claude/skills/other/SKILL.md", wildcard_base_pattern
            )
        )
        self.assertFalse(
            module._matches_pattern(".claude/skillsX/sd-a/file.md", wildcard_base_pattern)
        )

    def test_static_scanner_patterns_cover_manifest_targets_at_subpath_granularity(
        self,
    ) -> None:
        pr_body_scope = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_pr_body_scope_manifest_coverage",
        )
        install_audit = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-install-audit.py",
            "sd_install_audit_manifest_coverage",
        )
        _, files = install.load_manifest()
        targets = sorted(
            file.target.as_posix()
            for file in files
            if file.kind != install.MANAGED_BLOCK_KIND
        )

        pr_body_unmatched = [
            target
            for target in targets
            if not any(
                pr_body_scope._matches_pattern(target, pattern)
                for rule in pr_body_scope.DEFAULT_RULES
                for pattern in rule.patterns
            )
        ]
        audit_unmatched = [
            target
            for target in targets
            if not install_audit.matches_pack_file(target)
        ]

        self.assertEqual(
            pr_body_unmatched,
            [],
            "PR-body scope scanner patterns must cover manifest targets by "
            "full target path so command/config subpath changes cannot drift.",
        )
        self.assertEqual(
            audit_unmatched,
            [],
            "Install-audit pack-file patterns must cover manifest targets by "
            "full target path so command/config subpath changes cannot drift.",
        )

    def test_pr_body_scope_script_detects_wildcard_base_skill_paths(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            ".claude/skills/sd-review-pr/SKILL.md\n"
            ".github/skills/trellis-before-dev/SKILL.md\n",
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
        self.assertIn(".claude/skills/sd-review-pr/SKILL.md", result.stdout)
        self.assertIn(".github/skills/trellis-before-dev/SKILL.md", result.stdout)

    def test_pr_body_scope_script_merges_matching_configured_scope(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        config = root / ".sd-ai-command-pack/pr-body-scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "CI/review scope",
                            "headings": [
                                "CI/review scope:",
                                "CI scope:",
                                "Workflow scope:",
                            ],
                            "patterns": ["scripts/local-review-wrapper.py"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        changed_files = root / "changed-files.txt"
        changed_files.write_text(
            ".github/workflows/test.yml\n"
            "scripts/local-review-wrapper.py\n",
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
        self.assertEqual(result.stdout.count("detected CI/review scope paths:"), 1)
        self.assertIn(".github/workflows/test.yml", result.stdout)
        self.assertIn("scripts/local-review-wrapper.py", result.stdout)

    def test_pr_body_scope_merge_rules_dedupes_patterns_in_order(self) -> None:
        module_path = install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py"
        module = self.load_module_from_path(
            module_path,
            "sd_ai_command_pack_pr_body_scope_test",
        )

        headings = ("CI/review scope:", "CI scope:")
        merged = module._merge_rules(
            (
                module.ScopeRule(
                    label="CI/review scope",
                    headings=headings,
                    patterns=("scripts/a.sh", "scripts/b.sh"),
                ),
                module.ScopeRule(
                    label="CI/review scope",
                    headings=headings,
                    patterns=("scripts/b.sh", "scripts/c.sh"),
                ),
            )
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0].patterns,
            ("scripts/a.sh", "scripts/b.sh", "scripts/c.sh"),
        )

    def test_pr_body_scope_accepts_markdown_heading_without_colon(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_heading_test",
        )

        self.assertTrue(
            module._body_has_heading(
                "## Tooling/generated scope\n- command-pack refresh.",
                ("Tooling/generated scope:",),
            )
        )
        self.assertFalse(
            module._body_has_heading(
                "Summary mentions Tooling/generated scope in prose.",
                ("Tooling/generated scope:",),
            )
        )

    def test_pr_body_scope_double_star_patterns_match_nested_paths(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_match_test",
        )

        self.assertTrue(module._matches_pattern("src", "src/**"))
        self.assertTrue(module._matches_pattern("src/file.py", "src/**"))
        self.assertTrue(module._matches_pattern("src/nested/file.py", "src/**"))
        self.assertTrue(module._matches_pattern("src/file.py", "./src/**"))
        self.assertFalse(module._matches_pattern("other/src/file.py", "src/**"))
        self.assertEqual(module._normalize_path("./src\\file.py"), "src/file.py")

    def test_pr_body_scope_split_changed_files_strips_path_whitespace(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_split_test",
        )

        self.assertEqual(
            module._split_changed_files(
                "  leading.py\ntrailing.py  \n\n./src\\file.py\na path/file name.py\n"
            ),
            ["leading.py", "trailing.py", "src/file.py", "a path/file name.py"],
        )

    def test_pr_body_scope_config_rejects_empty_headings(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_config_shape_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-pr-body-scope-test-")
        self.addCleanup(tempdir.cleanup)
        config = Path(tempdir.name) / "scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "Runtime/server scope",
                            "headings": [],
                            "patterns": ["src/**"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        rules, error = module._load_config_rules(config)

        self.assertEqual(rules, ())
        self.assertIsNotNone(error)
        self.assertIn("non-empty list of non-empty string headings", error)

    def test_pr_body_scope_config_can_include_installed_targets(self) -> None:
        module = self.load_module_from_path(
            install.ROOT / "scripts/sd-ai-command-pack-pr-body-scope.py",
            "sd_ai_command_pack_pr_body_scope_installed_targets_test",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-pr-body-scope-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / ".sd-ai-command-pack").mkdir()
        (root / ".sd-ai-command-pack/installed-targets.txt").write_text(
            "custom/generated.md\n",
            encoding="utf-8",
        )
        config = root / "scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "Custom generated scope",
                            "headings": ["Custom generated scope:"],
                            "patterns": ["docs/custom.md"],
                            "include_installed_targets": True,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        rules, error = module._rules_for_repo(root, config)

        self.assertIsNone(error)
        custom_rule = next(
            rule for rule in rules if rule.label == "Custom generated scope"
        )
        self.assertIn("custom/generated.md", custom_rule.patterns)

    def test_pr_body_scope_script_enforces_configured_runtime_scope(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        config = root / ".sd-ai-command-pack/pr-body-scope.json"
        config.write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "label": "Runtime/server scope",
                            "headings": [
                                "Runtime/server scope:",
                                "Runtime scope:",
                            ],
                            "patterns": ["src/**"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        changed_files = root / "changed-files.txt"
        changed_files.write_text("src/service.py\n", encoding="utf-8")

        missing = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY": "Summary only.",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(missing.returncode, 1, missing.stdout)
        self.assertIn("missing Runtime/server scope", missing.stdout)

        covered = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY": (
                    "Runtime/server scope: updates service behavior."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(covered.returncode, 0, covered.stdout)
        self.assertIn("PR body scope sections cover", covered.stdout)

    def test_pr_body_scope_script_ignores_removed_legacy_body_env(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        changed_files = root / "changed-files.txt"
        changed_files.write_text("scripts/classify_ci_changes.sh\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            env={
                **os.environ,
                "REVIEW_PREFLIGHT_PR_BODY": (
                    "CI/review scope: migrate classifier compatibility."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("detected CI/review scope", result.stdout)
        self.assertIn("PR body not provided", result.stdout)
        self.assertNotIn("PR body scope sections cover", result.stdout)

    def test_pr_body_scope_script_reports_malformed_config_without_traceback(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        config = root / ".sd-ai-command-pack/pr-body-scope.json"
        config.write_text('{"rules": [', encoding="utf-8")
        changed_files = root / "changed-files.txt"
        changed_files.write_text("src/service.py\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-pr-body-scope.py",
                "--changed-files",
                str(changed_files),
            ],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY": (
                    "Runtime/server scope: updates service behavior."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("cannot parse PR body scope config", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_review_scope_script_reports_manifest_driven_pack_changes(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )
        installed_targets = root / install.INSTALLED_TARGETS_FILE
        installed_targets.write_text(
            installed_targets.read_text(encoding="utf-8")
            + "# local note\n",
            encoding="utf-8",
        )
        (root / "docs/repomix-map.md").write_text(
            "# local map\n",
            encoding="utf-8",
        )
        cursor_command = root / ".cursor/commands/trellis-continue.md"
        cursor_command.parent.mkdir(parents=True)
        cursor_command.write_text(
            "# Trellis Continue\n",
            encoding="utf-8",
        )
        workspace_dir = root / ".trellis/workspace/sdelmas"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "journal-1.md").write_text(
            "## Session 1: Test\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "0",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "Tooling/generated review-scope files changed",
            result.stdout,
        )
        self.assertIn("Scope categories:", result.stdout)
        self.assertIn("copied/generated Trellis or sd-ai-command-pack files", result.stdout)
        self.assertIn("known repository-map files", result.stdout)
        self.assertIn("Trellis workspace journal/index files", result.stdout)
        self.assertIn("docs/SD_AI_COMMAND_PACK.md", result.stdout)
        self.assertIn(".cursor/commands/trellis-continue.md", result.stdout)
        self.assertIn("docs/repomix-map.md", result.stdout)
        self.assertIn(".trellis/workspace/sdelmas/journal-1.md", result.stdout)
        self.assertIn(".sd-ai-command-pack/installed-targets.txt", result.stdout)

    def test_review_scope_script_ignores_removed_legacy_pr_body_env(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir()
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            "  printf '%s\\n' "
            "'{\"title\":\"Product fix\",\"body\":\"Updates behavior.\",\"url\":\"https://example.test/pr/1\",\"state\":\"OPEN\"}'\n"
            "else\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
                "REVIEW_PREFLIGHT_PR_BODY": (
                    "Tooling/generated scope: refreshed copied pack docs."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("REVIEW_PREFLIGHT_PR_BODY", result.stdout)
        self.assertIn(
            "does not include a recognized tooling/generated scope section",
            result.stdout,
        )

    def test_review_scope_script_requires_pr_body_scope_when_configured(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir()
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            "  printf '%s\\n' "
            "'{\"title\":\"Product fix\",\"body\":\"Updates behavior.\",\"url\":\"https://example.test/pr/1\",\"state\":\"OPEN\"}'\n"
            "else\n"
            "  printf 'unexpected gh invocation: %s\\n' \"$*\" >&2\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "does not include a recognized tooling/generated scope section",
            result.stdout,
        )

    def test_review_scope_script_accepts_explicit_pr_body_scope_section(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir()
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            "  printf '%s\\n' "
            "'{\"title\":\"Product fix\",\"body\":\"Tooling/generated scope: command-pack refresh.\",\"url\":\"https://example.test/pr/1\",\"state\":\"OPEN\"}'\n"
            "else\n"
            "  printf 'unexpected gh invocation: %s\\n' \"$*\" >&2\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Tooling/generated review-scope files changed", result.stdout)

    def test_review_scope_script_accepts_markdown_scope_heading_without_colon(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        stub_bin = root.parent / f"{root.name}-bin"
        stub_bin.mkdir()
        (stub_bin / "gh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [ \"${1:-}\" = pr ] && [ \"${2:-}\" = view ]; then\n"
            "  printf '%s\\n' "
            "'{\"title\":\"Product fix\",\"body\":\"## Tooling/generated scope\\n- command-pack refresh.\",\"url\":\"https://example.test/pr/1\",\"state\":\"OPEN\"}'\n"
            "else\n"
            "  printf 'unexpected gh invocation: %s\\n' \"$*\" >&2\n"
            "  exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        (stub_bin / "gh").chmod(0o755)

        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}",
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Tooling/generated review-scope files changed", result.stdout)

    def test_review_scope_script_accepts_scope_section_from_explicit_body_env(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": os.environ["PATH"],
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
                "SD_AI_COMMAND_PACK_SCOPE_PR_BODY": (
                    "Tooling/generated scope: command-pack refresh."
                ),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Tooling/generated review-scope files changed", result.stdout)

    def test_review_scope_script_rejects_invalid_explicit_body_env(
        self,
    ) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        root = self.make_repo(".github")
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "install command pack")

        command_pack_doc = root / "docs/SD_AI_COMMAND_PACK.md"
        command_pack_doc.write_text(
            command_pack_doc.read_text(encoding="utf-8")
            + "\nLocal integration note.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [self._bash_path, "scripts/sd-ai-command-pack-review-scope.sh"],
            cwd=root,
            env={
                **os.environ,
                "PATH": os.environ["PATH"],
                "SD_AI_COMMAND_PACK_SCOPE_CHECK_GH": "required",
                "SD_AI_COMMAND_PACK_SCOPE_PR_BODY": "Updates behavior.",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "provided PR body does not include a recognized tooling/generated scope section",
            result.stdout,
        )

    def test_prism_rules_template_has_valid_shape(self) -> None:
        prism_rules_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".prism/rules.json")
        ]

        self.assertEqual(
            len(prism_rules_files),
            1,
            "manifest must contain exactly one shared .prism/rules.json config",
        )
        self.assert_prism_rules_valid(prism_rules_files[0].source)
        self.assert_no_secret_markers(prism_rules_files[0].source)
        self.assertEqual(prism_rules_files[0].install, install.IF_NOT_EXISTS)

    def test_prism_rules_schema_template_is_installed(self) -> None:
        schema_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".prism/rules.schema.json")
        ]

        self.assertEqual(len(schema_files), 1)
        schema = json.loads(schema_files[0].source.read_text(encoding="utf-8"))
        self.assertIn("$schema", schema)
        self.assertIn("severityOverrides", schema["properties"])
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(
            schema["properties"]["required"]["items"]["additionalProperties"]
        )

    # Copied Trellis surfaces plus bulk bookkeeping stay out of local review.
    GITO_TRELLIS_REQUIRED_EXCLUSIONS = (
        ".trellis/.template-hashes.json",
        ".trellis/.version",
        ".trellis/scripts/**",
        ".trellis/agents/**",
        ".trellis/tasks/archive/**",
    )
    # Any of these takes the authored delivery documents back out of scope. A
    # diff confined to them then reaches the provider empty, which reads as a
    # provider failure and blocks the review stage outright.
    #
    # .trellis/workspace/** belongs here rather than above. The journal and its
    # index are the only paths every finalization touches -- a completion bundle
    # is an archive move plus a journal session, a planning bundle is
    # journal-only -- so excluding them leaves exactly the finalization PRs with
    # an empty diff.
    GITO_TRELLIS_FORBIDDEN_EXCLUSIONS = (
        ".trellis/**",
        ".trellis/tasks/**",
        ".trellis/spec/**",
        ".trellis/workspace/**",
    )

    def assert_gito_trellis_exclusion_is_narrow(self, config_text: str) -> None:
        block = re.search(r"exclude_files\s*=\s*\[(.*?)\]", config_text, re.DOTALL)
        self.assertIsNotNone(block, "gito config must declare exclude_files")
        patterns = re.findall(r'"([^"]+)"', block.group(1))

        for pattern in self.GITO_TRELLIS_REQUIRED_EXCLUSIONS:
            self.assertIn(pattern, patterns)
        for pattern in self.GITO_TRELLIS_FORBIDDEN_EXCLUSIONS:
            self.assertNotIn(pattern, patterns)

    def test_gito_config_templates_are_installed(self) -> None:
        config_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".gito/config.toml")
        ]
        env_files = [
            file
            for file in self.shared_manifest_files("config")
            if file.target == Path(".gito/sd-ai-command-pack.env")
        ]

        self.assertEqual(len(config_files), 1)
        self.assertEqual(config_files[0].install, install.IF_NOT_EXISTS)
        config_text = config_files[0].source.read_text(encoding="utf-8")
        self.assertIn("exclude_files = [", config_text)
        self.assertIn("[prompt_vars]", config_text)
        self.assert_gito_trellis_exclusion_is_narrow(config_text)
        self.assert_no_secret_markers(config_files[0].source)

        self.assertEqual(len(env_files), 1)
        self.assertEqual(env_files[0].install, install.ALWAYS_INSTALL)
        env_text = env_files[0].source.read_text(encoding="utf-8")
        self.assertIn("MAX_CONCURRENT_TASKS=4", env_text)
        self.assert_no_secret_markers(env_files[0].source)

    def test_review_pr_skill_allows_reply_and_resolve_for_addressed_threads(self) -> None:
        skill = (
            install.ROOT
            / "templates/.agents/skills/sd-review-pr/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("standing permission to reply", skill)
        self.assertIn("review threads during this loop", skill)
        self.assertIn("fixed, rebutted with evidence", skill)
        self.assertIn("confirmed already addressed", skill)
        self.assertIn("Do not resolve valid unaddressed or ambiguous threads", skill)
        self.assertIn('COMMENT_DATABASE_ID="<review comment database id>"', skill)
        self.assertIn(
            '"repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments/$COMMENT_DATABASE_ID/replies"',
            skill,
        )
        self.assertIn('THREAD_NODE_ID="<review thread node id>"', skill)
        self.assertIn('-F threadId="$THREAD_NODE_ID"', skill)
        self.assertNotIn("{comment_database_id}", skill)
        self.assertNotIn('-F threadId="THREAD_NODE_ID"', skill)

    def test_review_pr_remote_reviewer_is_configurable(self) -> None:
        skill_paths = [
            install.ROOT / ".agents/skills/sd-review-pr/SKILL.md",
            install.ROOT / "templates/.agents/skills/sd-review-pr/SKILL.md",
        ]
        adapter_paths = [
            install.ROOT / ".claude/commands/sd/review-pr.md",
            install.ROOT / ".gemini/commands/sd/review-pr.toml",
            install.ROOT / ".github/prompts/sd-review-pr.prompt.md",
            install.ROOT / ".opencode/commands/sd-review-pr.md",
            install.ROOT / "templates/.claude/commands/sd/review-pr.md",
            install.ROOT / "templates/.commands/sd-review-pr.md",
            install.ROOT / "templates/.gemini/commands/sd/review-pr.toml",
            install.ROOT / "templates/.github/prompts/sd-review-pr.prompt.md",
        ]
        detailed_doc_paths = [
            install.ROOT / "docs/SD_AI_COMMAND_PACK.md",
            install.ROOT / "templates/docs/SD_AI_COMMAND_PACK.md",
        ]

        for skill_path in skill_paths:
            skill = skill_path.read_text(encoding="utf-8")
            self.assertIn("configured remote reviewer", skill)
            self.assertIn("typed deterministic `sd-check`", skill)
            self.assertIn("scripts/sd-ai-command-pack-check.py --json", skill)
            self.assertNotIn("SD_AI_COMMAND_PACK_FULL_CHECK_PRISM", skill)
            self.assertNotIn("SD_AI_COMMAND_PACK_FULL_CHECK_GITO", skill)
            self.assertNotIn(
                "bash scripts/sd-ai-command-pack-review-full-check.sh",
                skill,
            )
            self.assertIn("Do not discover `package.json` scripts", skill)
            self.assertNotIn("any available local review providers", skill)
            self.assertNotIn("optional local review providers", skill)
            self.assertIn(
                'REMOTE_REVIEWER="${SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER:-@copilot}"',
                skill,
            )
            self.assertIn(
                'REMOTE_REVIEWER_LABEL="${SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER_LABEL:-GitHub Copilot}"',
                skill,
            )
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_AUTHOR_MATCH", skill)
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND", skill)
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT", skill)
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_SETTLE_POLLS", skill)
            self.assertIn(
                'REMOTE_REVIEW_AUTHOR_MATCH="copilot-pull-request-reviewer[bot]"',
                skill,
            )
            self.assertIn("after every pushed review-fix commit", skill)
            self.assertIn(
                "before each configured remote-review request",
                skill,
            )
            self.assertIn(
                "fixes for review comments that existed before this command was",
                skill,
            )
            self.assertIn("## Step 2.5: Disposition First-Review Advisories", skill)
            self.assertIn("cover every", skill)
            self.assertIn("applicable boundary", skill)
            self.assertIn("authored-source size", skill)
            self.assertIn("multiple-Trellis-task warnings", skill)
            self.assertIn("## Step 7.5: Capture Review Learnings Once", skill)
            self.assertEqual(
                skill.count("scripts/sd-ai-command-pack-review-learnings.py"),
                1,
            )
            self.assertIn('--github-pr "$PR_NUMBER" --dry-run', skill)
            self.assertLess(skill.index("## Step 7.5"), skill.index("## Step 8"))
            self.assertIn("exactly once per `sd-review-pr` invocation", skill)
            self.assertIn("Do not run it", skill)
            self.assertIn("after individual rounds", skill)
            self.assertIn('-f reviewers[]="$REMOTE_REVIEWER"', skill)
            self.assertIn(
                'gh pr edit "$PR_NUMBER" --add-reviewer "$REMOTE_REVIEWER"',
                skill,
            )
            self.assertIn(
                'gh pr edit "$PR_NUMBER" --add-reviewer @copilot',
                skill,
            )
            self.assertIn("Only **review materialized** completes", skill)
            self.assertIn("cleared reviewer request is a polling", skill)
            self.assertIn("accepted request with no observable activity", skill)
            self.assertNotIn(
                "the review request disappears and remains absent through two polling",
                skill,
            )
            self.assertNotIn("-f reviewers[]=copilot-pull-request-reviewer", skill)
            self.assertNotIn(
                "gh pr edit \"$PR_NUMBER\" --add-reviewer copilot-pull-request-reviewer",
                skill,
            )

        for adapter_path in adapter_paths:
            adapter = adapter_path.read_text(encoding="utf-8")
            self.assertIn("configured remote reviewer", adapter)
            self.assertIn("typed deterministic `sd-check` gate", adapter)
            self.assertIn("automatic re-review after pushed fixes", adapter)
            self.assertIn("configured remote review round limit", adapter)
            self.assertNotIn("any available local review providers", adapter)
            self.assertNotIn("optional local review providers", adapter)

        readme = (install.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("### sd-review-pr", readme)
        self.assertIn("configured remote reviewer", readme)
        self.assertIn("typed deterministic `sd-check` gate", readme)
        self.assertIn("never discovers", readme)
        self.assertIn("re-requests review after each pushed fix", readme)
        self.assertIn(
            "[docs/SD_AI_COMMAND_PACK.md](docs/SD_AI_COMMAND_PACK.md#commands)",
            readme,
        )

        for doc_path in detailed_doc_paths:
            doc = doc_path.read_text(encoding="utf-8")
            self.assertRegex(doc, r"(?i)the\s+default remote review request")
            self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER", doc)
            self.assertIn("review-fix commit made", doc)
            self.assertIn("never invokes full-check, Prism, or Gito", doc)

    def test_scope_guard_classifies_the_caller_repo_when_installed_off_tree(
        self,
    ) -> None:
        """The thin layout, proven rather than asserted from source text.

        A thin install moves this script to the machine, so `$SCRIPT_DIR/..`
        stops being any checkout. Measured on `rwbp-coordinator` converted at
        0.71.16, the old derivation ended the run at
        `fatal: not a git repository` before the first check ran. The script is
        placed outside the repository here for exactly that reason -- running
        it from inside its own checkout cannot tell the two derivations apart.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            consumer = root / "consumer"
            (consumer / ".sd-ai-command-pack").mkdir(parents=True)
            (consumer / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
                "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
            )
            for command in (["init", "-q"], ["add", "-A"]):
                subprocess.run(
                    ["git", *command], cwd=consumer, check=True, capture_output=True
                )

            # Not `scripts/` under any repository: the machine layout this
            # script has to work from once the payload leaves the consumer.
            machine_bin = root / "agents-bin"
            machine_bin.mkdir()
            for name in (
                "sd-ai-command-pack-review-scope.sh",
                "sd-ai-command-pack-shell-lib.sh",
                "sd-ai-command-pack-review-layout.py",
            ):
                shutil.copy2(PACK_ROOT / "templates" / "scripts" / name, machine_bin / name)

            environment = dict(os.environ)
            for name in (
                "SD_AI_COMMAND_PACK_TARGETS_FILE",
                "SD_AI_COMMAND_PACK_REPO_ROOT",
                "SD_AI_COMMAND_PACK_STATE_HOME",
                "XDG_STATE_HOME",
            ):
                environment.pop(name, None)

            result = subprocess.run(
                [
                    "bash",
                    str(machine_bin / "sd-ai-command-pack-review-scope.sh"),
                    "--json",
                    "--path",
                    "scripts/sd-ai-command-pack-full-check.sh",
                    "--path",
                    "src/app.ts",
                ],
                cwd=consumer,
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("not a git repository", result.stderr)
            document = json.loads(result.stdout)
            # The consumer's receipt answered, so the caller's tree is what the
            # script resolved -- an off-tree root would have found no receipt
            # here and reported `unresolved` instead.
            self.assertEqual(document["mode"], "fat")
            self.assertEqual(
                [entry["category"] for entry in document["paths"]],
                ["pack-payload", "authored"],
            )

    def test_scope_guard_prefers_an_explicit_root_over_the_caller_tree(self) -> None:
        """The override rung, which the shared shell library already defines."""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            elsewhere = root / "elsewhere"
            (elsewhere / ".sd-ai-command-pack").mkdir(parents=True)
            (elsewhere / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
                "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
            )
            caller = root / "caller"
            caller.mkdir()
            subprocess.run(
                ["git", "init", "-q"], cwd=caller, check=True, capture_output=True
            )

            machine_bin = root / "agents-bin"
            machine_bin.mkdir()
            for name in (
                "sd-ai-command-pack-review-scope.sh",
                "sd-ai-command-pack-shell-lib.sh",
                "sd-ai-command-pack-review-layout.py",
            ):
                shutil.copy2(PACK_ROOT / "templates" / "scripts" / name, machine_bin / name)

            environment = dict(os.environ)
            for name in (
                "SD_AI_COMMAND_PACK_TARGETS_FILE",
                "SD_AI_COMMAND_PACK_STATE_HOME",
                "XDG_STATE_HOME",
            ):
                environment.pop(name, None)
            environment["SD_AI_COMMAND_PACK_REPO_ROOT"] = str(elsewhere)

            result = subprocess.run(
                [
                    "bash",
                    str(machine_bin / "sd-ai-command-pack-review-scope.sh"),
                    "--json",
                    "--path",
                    "scripts/sd-ai-command-pack-full-check.sh",
                ],
                cwd=caller,
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(result.stdout)
            self.assertEqual(document["mode"], "fat")
            self.assertEqual(
                [entry["category"] for entry in document["paths"]], ["pack-payload"]
            )

    def test_scope_guard_accepts_a_relative_explicit_root(self) -> None:
        """A relative override survives the guard changing directories.

        Only this rung can produce a relative root, and every path derived from
        it -- the targets receipt above all -- is built before `main` enters the
        repository. Left relative, the receipt lookup silently reads nothing and
        the guard reports no tooling/generated scope at all.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            elsewhere = root / "elsewhere"
            (elsewhere / ".sd-ai-command-pack").mkdir(parents=True)
            (elsewhere / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
                "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
            )
            copied = elsewhere / "scripts" / "sd-ai-command-pack-full-check.sh"
            copied.parent.mkdir()
            copied.write_text("old\n", encoding="utf-8")
            for command in (
                ["git", "init", "-q", "."],
                ["git", "config", "user.email", "scope@example.invalid"],
                ["git", "config", "user.name", "scope"],
                ["git", "add", "-A"],
                ["git", "commit", "-qm", "init"],
            ):
                subprocess.run(
                    command, cwd=elsewhere, check=True, capture_output=True
                )
            copied.write_text("old\nchanged\n", encoding="utf-8")

            machine_bin = root / "agents-bin"
            machine_bin.mkdir()
            for name in (
                "sd-ai-command-pack-review-scope.sh",
                "sd-ai-command-pack-shell-lib.sh",
                "sd-ai-command-pack-review-layout.py",
                "sd-ai-command-pack-toolchain.sh",
            ):
                shutil.copy2(PACK_ROOT / "templates" / "scripts" / name, machine_bin / name)

            environment = dict(os.environ)
            for name in (
                "SD_AI_COMMAND_PACK_TARGETS_FILE",
                "SD_AI_COMMAND_PACK_STATE_HOME",
                "XDG_STATE_HOME",
            ):
                environment.pop(name, None)
            environment["SD_AI_COMMAND_PACK_REPO_ROOT"] = "elsewhere"
            environment["SD_AI_COMMAND_PACK_CACHE_ENV_READY"] = "1"

            result = subprocess.run(
                ["bash", str(machine_bin / "sd-ai-command-pack-review-scope.sh")],
                cwd=root,
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "copied/generated Trellis or sd-ai-command-pack files", result.stdout
            )
            self.assertIn(
                "scripts/sd-ai-command-pack-full-check.sh", result.stdout
            )


if __name__ == "__main__":
    unittest.main()
