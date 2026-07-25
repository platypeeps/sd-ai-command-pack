from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
os = _support.os
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
Path = _support.Path
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase


class ReviewStageTests(InstallTestCase):
    """Behavioral coverage for the successor sd-review local stage."""

    SCRIPT = PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-local.py"

    def make_repo(self, *, changed_path: str = "src/app.py") -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="sd-review-stage-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "repo"
        root.mkdir()
        self.run_git(root, "init", "--initial-branch=main")
        self.run_git(root, "config", "user.name", "Review Stage Test")
        self.run_git(root, "config", "user.email", "review@example.com")
        (root / ".gitignore").write_text(".build/\n", encoding="utf-8")
        seed = root / changed_path
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_text("seed\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "seed")
        self.run_git(root, "switch", "-c", "feature")
        seed.write_text("seed\nchanged\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "change")
        return root

    def provider_script(self, root: Path) -> Path:
        del root
        return PACK_ROOT / "tests/fixtures/review_stage_provider.py"

    def write_config(
        self,
        root: Path,
        *,
        modes: tuple[str, str] = ("clean", "clean"),
        timeout: int = 5,
        documentation: str = "cheapest",
        metadata: str = "cheapest",
        required: list[str] | None = None,
    ) -> Path:
        helper = self.provider_script(root)
        log = root.parent / "provider.log"
        providers = []
        for identifier, cost, mode in zip(
            ("prism", "gito"), ("low", "medium"), modes, strict=True
        ):
            providers.append(
                {
                    "id": identifier,
                    "adapter": "argv",
                    "argv": [
                        sys.executable,
                        str(helper),
                        identifier,
                        "{artifact}",
                        str(log),
                        mode,
                    ],
                    "scopes": ["worktree", "branch_delta", "codebase"],
                    "dataHandling": "local",
                    "costTier": cost,
                    "qualityTier": "standard",
                    "timeoutSeconds": timeout,
                    "version": "fixture-v1",
                    "enabled": True,
                    "outcomeByExitCode": {
                        "0": "clean",
                        "1": "findings",
                        "8": "unavailable",
                        "9": "failed",
                        "10": "cancelled",
                    },
                }
            )
        path = root / ".sd-ai-command-pack/review.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "providers": providers,
                    "policy": {
                        "allowedDataHandling": ["local"],
                        "documentation": documentation,
                        "metadata": metadata,
                        "requiredProviders": required or [],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", str(path.relative_to(root)))
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=root, check=False
        )
        if status.returncode != 0:
            self.run_git(root, "commit", "-m", "configure local review")
        return log

    def write_builtin_config(self, root: Path, *, prism_mode: str = "finding") -> Path:
        providers = []
        for identifier, cost in (("prism", "low"), ("gito", "medium")):
            providers.append(
                {
                    "id": identifier,
                    "adapter": identifier,
                    "argv": [],
                    "scopes": ["worktree", "branch_delta", "codebase"],
                    "dataHandling": "local",
                    "costTier": cost,
                    "qualityTier": "standard",
                    "timeoutSeconds": 5,
                    "version": "fixture-v1",
                    "enabled": True,
                    "outcomeByExitCode": {"0": "clean"},
                }
            )
        config = root / ".sd-ai-command-pack/review.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "providers": providers,
                    "policy": {
                        "allowedDataHandling": ["local"],
                        "documentation": "cheapest",
                        "metadata": "cheapest",
                        "requiredProviders": [],
                    },
                }
            ),
            encoding="utf-8",
        )
        self.run_git(root, "add", str(config.relative_to(root)))
        self.run_git(root, "commit", "-m", "configure builtin adapters")

        fake_bin = root.parent / "bin"
        fake_bin.mkdir()
        log = root.parent / "builtin.log"
        prism = fake_bin / "prism"
        prism.write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, sys\n"
            f"log = pathlib.Path({str(log)!r})\n"
            "with log.open('a', encoding='utf-8') as stream: stream.write('prism ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            + (
                "print('human finding that must not become clean')\n"
                if prism_mode == "invalid"
                else "print(json.dumps({'findings': [{'severity': 'medium', 'category': 'correctness', 'title': 'Prism finding', 'locations': [{'path': 'src/app.py', 'lines': {'start': 2, 'end': 2}}]}]}))\n"
            ),
            encoding="utf-8",
        )
        prism.chmod(0o755)
        gito = fake_bin / "gito"
        gito.write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, sys\n"
            f"log = pathlib.Path({str(log)!r})\n"
            "with log.open('a', encoding='utf-8') as stream: stream.write('gito ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1]); out.mkdir(parents=True)\n"
            "report = {'total_issues': 1, 'issues': {'src/app.py': [{'title': 'Gito finding', 'details': 'details', 'severity': 2, 'tags': ['correctness'], 'affected_lines': [{'start_line': 3}]}]}}\n"
            "(out / 'code-review-report.json').write_text(json.dumps(report), encoding='utf-8')\n",
            encoding="utf-8",
        )
        gito.chmod(0o755)
        return log

    def reset_base_then_change(self, root: Path, path: str) -> None:
        self.run_git(root, "branch", "-f", "main", "HEAD")
        target = root / path
        target.write_text(
            target.read_text(encoding="utf-8") + "focused\n", encoding="utf-8"
        )
        self.run_git(root, "add", path)
        self.run_git(root, "commit", "-m", "focused classification change")

    def run_stage(
        self,
        root: Path,
        attempt: str,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        cache = root.parent / "cache"
        cache.mkdir(mode=0o700, exist_ok=True)
        path = os.environ.get("PATH", "")
        fake_bin = root.parent / "bin"
        if fake_bin.is_dir():
            path = f"{fake_bin}{os.pathsep}{path}"
        return subprocess.run(
            [
                sys.executable,
                str(self.SCRIPT),
                "--repo",
                str(root),
                "--base",
                "main",
                "--attempt-id",
                attempt,
                "--json",
                *arguments,
            ],
            cwd=root,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "SD_AI_COMMAND_PACK_CACHE_ROOT": str(cache),
                "PATH": path,
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def report(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"invalid JSON report: {error}\n{result.stdout}")
        self.assertIsInstance(value, dict)
        return value

    def test_substantive_first_head_runs_prism_and_gito_concurrently(self) -> None:
        root = self.make_repo()
        log = self.write_config(root, modes=("barrier", "barrier"))

        result = self.run_stage(root, "parallel-first")
        report = self.report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(report["status"], "clean")
        self.assertEqual(report["receipt"]["plan"]["execution"], "parallel")
        self.assertEqual(
            [row["provider"]["id"] for row in report["receipt"]["attempts"]],
            ["gito", "prism"],
        )
        artifacts = {
            row["provider"]["id"]: row["artifact"]
            for row in report["receipt"]["attempts"]
        }
        self.assertEqual(len(set(artifacts.values())), 2)
        for provider, artifact in artifacts.items():
            self.assertTrue(artifact.endswith(f"/{provider}"), artifact)
        lines = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual([line.split(":")[1] for line in lines[:2]], ["start", "start"])
        timestamps = {
            (parts[0], parts[1]): float(parts[2])
            for line in lines
            for parts in [line.split(":")]
        }
        self.assertLess(
            max(timestamps[(provider, "start")] for provider in ("prism", "gito")),
            min(timestamps[(provider, "end")] for provider in ("prism", "gito")),
            lines,
        )
        self.assertEqual(report["receipt"]["remoteGate"]["state"], "eligible")
        repository = report["remoteSummary"]["repository"]
        self.assertTrue(repository.startswith("local:"), repository)
        self.assertNotIn(str(root), repository)

    def test_case_distinct_paths_are_not_deduplicated(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("case-upper", "case-lower"))

        result = self.run_stage(root, "case-paths")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(
            [finding["path"] for finding in report["receipt"]["findings"]],
            ["SRC/App.py", "src/app.py"],
        )

    def test_nonzero_clean_mapping_cannot_hide_structured_findings(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding-fail", "clean"))
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value["providers"][0]["outcomeByExitCode"]["9"] = "clean"
        config.write_text(json.dumps(value), encoding="utf-8")
        self.run_git(root, "add", str(config.relative_to(root)))
        self.run_git(root, "commit", "-m", "map nonzero finding exit to clean")

        result = self.run_stage(root, "mapped-clean", "--local", "prism")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["status"], "findings")

    def test_provider_cannot_self_disposition_or_escape_finding_path(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("malicious-finding", "clean"))

        result = self.run_stage(root, "unsafe-finding", "--local", "prism")
        report = self.report(result)
        finding = report["receipt"]["findings"][0]

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIsNone(finding["path"])
        self.assertIsNone(finding["line"])
        self.assertEqual(finding["disposition"], "outstanding")
        self.assertEqual(report["receipt"]["remoteGate"]["state"], "blocked")

    def test_builtin_adapters_parse_native_reports_and_avoid_gito_filter(self) -> None:
        root = self.make_repo()
        log = self.write_builtin_config(root)

        result = self.run_stage(root, "native-reports")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["status"], "findings")
        self.assertEqual(
            sorted(finding["summary"] for finding in report["receipt"]["findings"]),
            ["Gito finding", "Prism finding"],
        )
        invocation_log = log.read_text(encoding="utf-8")
        self.assertIn("prism review range", invocation_log)
        self.assertIn("--format json", invocation_log)
        self.assertIn("gito review --vs", invocation_log)
        self.assertNotIn("--filter", invocation_log)

    def test_builtin_adapter_rejects_unstructured_success_output(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, prism_mode="invalid")

        result = self.run_stage(root, "invalid-native", "--local", "prism")
        report = self.report(result)

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertEqual(report["status"], "failed")
        self.assertIn(
            "valid structured review report",
            report["receipt"]["attempts"][0]["diagnostic"],
        )

    def test_prism_worktree_comma_path_fails_before_dispatch(self) -> None:
        root = self.make_repo()
        log = self.write_builtin_config(root)
        comma_path = root / "src/with,comma.py"
        comma_path.write_text("changed\n", encoding="utf-8")

        result = self.run_stage(
            root, "comma-path", "--scope", "changes", "--local", "prism"
        )
        report = self.report(result)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("path containing a comma", report["diagnostic"])
        self.assertFalse(log.exists())

    def test_custom_paths_placeholder_rejects_comma_path_before_dispatch(self) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value["providers"][0]["argv"].append("{paths}")
        config.write_text(json.dumps(value), encoding="utf-8")
        comma_path = root / "src/with,comma.py"
        comma_path.write_text("changed\n", encoding="utf-8")

        result = self.run_stage(
            root, "custom-comma", "--scope", "changes", "--local", "prism"
        )
        report = self.report(result)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("path containing a comma", report["diagnostic"])
        self.assertFalse(log.exists())

    def test_exact_receipt_reuse_avoids_duplicate_provider_calls(self) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        first = self.run_stage(root, "reuse-one")
        second = self.run_stage(root, "reuse-two", "--scope", "pr")

        self.assertEqual(first.returncode, 0, first.stdout)
        report = self.report(second)
        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(report["run"], "reused")
        self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 4)
        self.assertEqual(report["receipt"]["attemptId"], "reuse-one")

    def test_new_head_invalidates_reuse(self) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        first = self.run_stage(root, "head-one")
        self.assertEqual(first.returncode, 0, first.stdout)
        (root / "src/app.py").write_text("seed\nchanged\nagain\n", encoding="utf-8")
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "successor")

        second = self.run_stage(root, "head-two", "--successor", "low-risk")
        report = self.report(second)

        self.assertEqual(second.returncode, 0, second.stdout)
        self.assertEqual(report["run"], "executed")
        self.assertEqual(report["receipt"]["plan"]["policyId"], "low-risk-successor")
        self.assertEqual(len(report["receipt"]["attempts"]), 1)
        self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 6)

    def test_findings_are_deduplicated_with_provider_provenance(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding", "finding-alt"))

        result = self.run_stage(root, "findings")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["status"], "findings")
        findings = report["receipt"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["providers"], ["gito", "prism"])
        self.assertEqual(findings[0]["severity"], "high")
        self.assertEqual(findings[0]["families"], ["boundary-validation", "security"])
        self.assertEqual(report["receipt"]["disposition"]["outstanding"], 1)
        self.assertEqual(report["receipt"]["remoteGate"]["state"], "blocked")

    def test_provider_failure_is_distinct_and_local_policy_controls_gate(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("clean", "fail"))

        optional = self.run_stage(root, "failure-optional")
        optional_report = self.report(optional)
        required = self.run_stage(
            root, "failure-required", "--local-policy", "required"
        )
        required_report = self.report(required)

        self.assertEqual(optional.returncode, 3, optional.stdout)
        self.assertEqual(optional_report["status"], "failed")
        self.assertEqual(
            optional_report["receipt"]["remoteGate"]["state"],
            "eligible-with-limitations",
        )
        self.assertEqual(required.returncode, 3, required.stdout)
        self.assertEqual(required_report["run"], "executed")
        self.assertEqual(required_report["receipt"]["remoteGate"]["state"], "blocked")

    def test_repeated_family_requires_bounded_family_evidence(self) -> None:
        root = self.make_repo()
        self.write_config(root)

        missing = self.run_stage(
            root, "family-missing", "--successor", "repeated-family", "--plan-only"
        )
        missing_report = self.report(missing)
        self.assertEqual(missing.returncode, 2, missing.stdout)
        self.assertIn("--finding-family", missing_report["diagnostic"])

        planned = self.run_stage(
            root,
            "family-planned",
            "--successor",
            "repeated-family",
            "--finding-family",
            "boundary-validation",
            "--plan-only",
        )
        planned_report = self.report(planned)
        self.assertEqual(planned.returncode, 0, planned.stdout)
        self.assertEqual(planned_report["plan"]["policyId"], "repeated-family")
        self.assertEqual(
            planned_report["plan"]["findingFamilies"], ["boundary-validation"]
        )

    def test_documentation_and_ambiguous_plans_are_deterministic(self) -> None:
        docs = self.make_repo(changed_path="docs/guide.md")
        self.write_config(docs)
        self.reset_base_then_change(docs, "docs/guide.md")
        docs_result = self.run_stage(docs, "docs-plan", "--plan-only")
        docs_report = self.report(docs_result)
        self.assertEqual(docs_report["plan"]["policyId"], "documentation-cheapest")
        self.assertEqual(
            [row["id"] for row in docs_report["plan"]["providers"]], ["prism"]
        )

        ambiguous = self.make_repo(changed_path="assets/unknown.bin")
        self.write_config(ambiguous)
        self.reset_base_then_change(ambiguous, "assets/unknown.bin")
        ambiguous_result = self.run_stage(ambiguous, "ambiguous-plan", "--plan-only")
        ambiguous_report = self.report(ambiguous_result)
        self.assertEqual(ambiguous_report["plan"]["policyId"], "substantive-ensemble")
        self.assertEqual(
            [row["id"] for row in ambiguous_report["plan"]["providers"]],
            ["gito", "prism"],
        )

    def test_verified_bookkeeping_successor_skips_without_confidence(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        planned = self.report(self.run_stage(root, "bookkeeping-plan", "--plan-only"))
        target = planned["target"]
        evidence = root.parent / "bookkeeping.json"
        evidence.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "base": target["base"],
                    "head": target["head"],
                    "contentDigest": target["contentDigest"],
                    "classification": "bookkeeping-successor",
                }
            ),
            encoding="utf-8",
        )

        result = self.run_stage(
            root,
            "bookkeeping-run",
            "--successor",
            "bookkeeping",
            "--bookkeeping-evidence",
            str(evidence),
        )
        report = self.report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["receipt"]["attempts"], [])
        self.assertFalse(report["receipt"]["confidence"]["granted"])

    def test_missing_provider_and_timeout_do_not_become_clean(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("clean", "slow"), timeout=1)
        timeout = self.run_stage(root, "timeout", "--local", "gito")
        timeout_report = self.report(timeout)
        self.assertEqual(timeout.returncode, 3, timeout.stdout)
        self.assertEqual(timeout_report["status"], "failed")
        self.assertEqual(timeout_report["receipt"]["attempts"][0]["exitCode"], 124)

        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value["providers"][0]["argv"][0] = "missing-review-provider"
        config.write_text(json.dumps(value), encoding="utf-8")
        self.run_git(root, "add", str(config.relative_to(root)))
        self.run_git(root, "commit", "-m", "make provider unavailable")
        unavailable = self.run_stage(root, "unavailable", "--local", "prism")
        unavailable_report = self.report(unavailable)
        self.assertEqual(unavailable.returncode, 3, unavailable.stdout)
        self.assertEqual(unavailable_report["status"], "unavailable")

    def test_rate_limit_and_cancellation_remain_distinct_from_clean(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("rate-limit", "cancelled"))

        rate_limit = self.run_stage(root, "rate-limit", "--local", "prism")
        rate_limit_report = self.report(rate_limit)
        cancelled = self.run_stage(root, "cancelled", "--local", "gito")
        cancelled_report = self.report(cancelled)

        self.assertEqual(rate_limit.returncode, 3, rate_limit.stdout)
        self.assertEqual(rate_limit_report["status"], "unavailable")
        self.assertIn(
            "rate limited", rate_limit_report["receipt"]["attempts"][0]["diagnostic"]
        )
        self.assertEqual(cancelled.returncode, 3, cancelled.stdout)
        self.assertEqual(cancelled_report["status"], "cancelled")

    def test_remote_repository_identity_excludes_credentials(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        self.run_git(
            root,
            "remote",
            "add",
            "origin",
            "https://review-user:secret-token@example.com/org/repo.git",
        )

        result = self.run_stage(root, "safe-identity", "--plan-only")
        report = self.report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(report["target"]["repository"], "example.com/org/repo")
        self.assertNotIn("review-user", result.stdout)
        self.assertNotIn("secret-token", result.stdout)

    def test_noncanonical_remote_path_uses_opaque_identity(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        self.run_git(
            root,
            "remote",
            "add",
            "origin",
            "https://example.com/org/./repo.git",
        )

        result = self.run_stage(root, "opaque-identity", "--plan-only")
        report = self.report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(str(report["target"]["repository"]).startswith("remote:"))

    def test_option_like_base_is_not_interpreted_as_git_flag(self) -> None:
        root = self.make_repo()
        self.write_config(root)

        result = self.run_stage(root, "option-base", "--base=--octopus", "--plan-only")
        report = self.report(result)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(report["status"], "invalid")

    def test_invalid_config_and_artifact_paths_fail_before_dispatch(self) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value["providers"][0]["argv"] = ["bash", "-c", "echo unsafe"]
        config.write_text(json.dumps(value), encoding="utf-8")

        shell = self.run_stage(root, "bad-shell")
        shell_report = self.report(shell)
        self.assertEqual(shell.returncode, 2, shell.stdout)
        self.assertIn("shell command string", shell_report["diagnostic"])
        self.assertFalse(log.exists())

        self.write_config(root)
        external = self.run_stage(
            root, "bad-root", "--artifact-root", str(root.parent / "outside")
        )
        external_report = self.report(external)
        self.assertEqual(external.returncode, 2, external.stdout)
        self.assertIn("inside the repository", external_report["diagnostic"])

    def test_artifact_root_rejects_lexical_symlink_before_dispatch(self) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        (root / ".gitignore").write_text(
            ".build/\n.build-link\n", encoding="utf-8"
        )
        self.run_git(root, "add", ".gitignore")
        self.run_git(root, "commit", "-m", "ignore artifact symlink")
        try:
            (root / ".build-link").symlink_to(".build", target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

        result = self.run_stage(
            root,
            "symlink-root",
            "--artifact-root",
            ".build-link/reviews",
        )
        report = self.report(result)

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("cannot traverse a symlink", report["diagnostic"])
        self.assertFalse(log.exists())

    def test_branch_scope_rejects_dirty_worktree_and_retry_collision(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        first = self.run_stage(root, "collision", "--local", "none")
        self.assertEqual(first.returncode, 0, first.stdout)
        collision = self.run_stage(root, "collision", "--local", "none", "--no-reuse")
        collision_report = self.report(collision)
        self.assertEqual(collision.returncode, 2, collision.stdout)
        self.assertIn("already exists", collision_report["diagnostic"])

        (root / "src/app.py").write_text("dirty\n", encoding="utf-8")
        dirty = self.run_stage(root, "dirty")
        dirty_report = self.report(dirty)
        self.assertEqual(dirty.returncode, 2, dirty.stdout)
        self.assertIn("clean worktree", dirty_report["diagnostic"])


if __name__ == "__main__":
    unittest.main()
