from __future__ import annotations

import signal
import time

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
        ceiling: str | None = None,
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
                        # Written only when asked for. Emitting it as an
                        # explicit null would change the policy digest of every
                        # test that does not use it.
                        **(
                            {"localAdvisorySeverityCeiling": ceiling}
                            if ceiling is not None
                            else {}
                        ),
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

    def write_builtin_config(
        self,
        root: Path,
        *,
        prism_mode: str = "finding",
        gito_count: int = 1,
        gito_severity: object = 2,
    ) -> Path:
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
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", str(config.relative_to(root)))
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=root, check=False
        )
        if status.returncode != 0:
            self.run_git(root, "commit", "-m", "configure builtin adapters")

        fake_bin = root.parent / "bin"
        fake_bin.mkdir(exist_ok=True)
        log = root.parent / "builtin.log"
        fixture = PACK_ROOT / "tests/fixtures/review_stage_builtin_provider.py"
        (fake_bin / "provider-config.json").write_text(
            json.dumps(
                {
                    "log": str(log),
                    "prismMode": prism_mode,
                    "gitoCount": gito_count,
                    "gitoSeverity": gito_severity,
                }
            ),
            encoding="utf-8",
        )
        payload = fixture.read_bytes()
        for provider in ("prism", "gito"):
            executable = fake_bin / provider
            executable.write_bytes(payload)
            executable.chmod(0o755)
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

    def write_family_evidence(
        self,
        root: Path,
        *,
        current_round: int,
        findings: list[dict[str, object]],
        audits: list[dict[str, object]] | None = None,
        extensions: list[dict[str, object]] | None = None,
        blocked_redispatches: int = 0,
    ) -> Path:
        path = root.parent / "family-evidence.json"
        path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "lifecycleId": "pr-123",
                    "currentRound": current_round,
                    "currentHead": self.git_output(root, "rev-parse", "HEAD"),
                    "blockedRedispatches": blocked_redispatches,
                    "findings": findings,
                    "audits": audits or [],
                    "extensions": extensions or [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def family_finding(
        self,
        root: Path,
        identifier: str,
        round_number: int,
        family: str,
    ) -> dict[str, object]:
        return {
            "id": identifier,
            "provider": "copilot",
            "round": round_number,
            "head": self.git_output(root, "rev-parse", "HEAD"),
            "family": family,
            "actionable": True,
            "disposition": "outstanding",
            "fixCommit": None,
            "siblingAuditId": None,
        }

    def completed_family_audit(
        self,
        root: Path,
        *,
        family: str = "boundary-validation",
        round_number: int = 2,
        outcome: str = "clean",
        limitations: list[str] | None = None,
    ) -> dict[str, object]:
        dimensions = {
            "boundary-validation": (
                "strict-types",
                "normalization",
                "persistence-invariants",
                "state-transitions",
                "replay-idempotency",
                "attempts-receipts",
                "exact-identity-head",
                "subprocess-failures",
                "permissions",
                "paths-symlinks-toctou",
                "controlled-diagnostics",
            )
        }
        head = self.git_output(root, "rev-parse", "HEAD")
        return {
            "id": f"audit-{family}-{round_number}",
            "family": family,
            "round": round_number,
            "head": head,
            "localReceiptId": "a" * 64,
            "localHead": head,
            "localOutcome": outcome,
            "localLimitations": limitations or [],
            "checkHead": head,
            "checkStatus": "passed",
            "batchSize": 2,
            "fixCommits": [head],
            "siblingFindingIds": ["sibling-one", "sibling-two"],
            "dimensions": [
                {"id": identifier, "status": "covered"}
                for identifier in dimensions[family]
            ],
        }

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

    def test_rebutted_local_finding_clears_the_gate_but_stays_visible(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))

        first = self.run_stage(root, "rebuttal", "--local", "prism")
        blocked = self.report(first)
        self.assertEqual(first.returncode, 1, first.stdout)
        self.assertEqual(blocked["receipt"]["remoteGate"]["state"], "blocked")
        self.assertEqual(
            blocked["receipt"]["remoteGate"]["reason"], "actionable-local-findings"
        )
        identifier = blocked["receipt"]["findings"][0]["id"]

        second = self.run_stage(
            root,
            "rebuttal",
            "--local",
            "prism",
            "--local-disposition",
            f"{identifier}=rebutted",
        )
        cleared = self.report(second)
        receipt = cleared["receipt"]

        self.assertNotEqual(receipt["remoteGate"]["state"], "blocked")
        self.assertEqual(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(
            receipt["disposition"]["localDispositions"], {identifier: "rebutted"}
        )
        # The finding is dispositioned, never deleted: the evidence a reviewer
        # would need to audit the rebuttal has to survive it.
        self.assertEqual(len(receipt["findings"]), 1)
        self.assertEqual(receipt["findings"][0]["id"], identifier)
        self.assertEqual(receipt["findings"][0]["disposition"], "rebutted")

    def test_local_disposition_rejects_an_id_matching_no_finding(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))
        self.run_stage(root, "unknown-id", "--local", "prism")

        result = self.run_stage(
            root,
            "unknown-id",
            "--local",
            "prism",
            "--local-disposition",
            "0000000000000000=rebutted",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("match no finding", result.stdout)

    def test_local_disposition_rejects_unsupported_grammar(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))

        for index, token in enumerate(("abc=dismissed", "abc", "=rebutted")):
            with self.subTest(token=token):
                result = self.run_stage(
                    root,
                    f"grammar-{index}",
                    "--local",
                    "prism",
                    "--local-disposition",
                    token,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("<stable-id>=rebutted", result.stdout)

    def test_duplicate_local_disposition_ids_are_rejected(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))

        result = self.run_stage(
            root,
            "duplicate-id",
            "--local",
            "prism",
            "--local-disposition",
            "abc=rebutted",
            "--local-disposition",
            "abc=rebutted",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unique", result.stdout)

    def test_rebuttal_does_not_carry_to_a_different_head(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))
        first = self.report(self.run_stage(root, "head-one", "--local", "prism"))
        identifier = first["receipt"]["findings"][0]["id"]

        moved = root / "src/app.py"
        moved.write_text("seed\nchanged after the rebuttal\n", encoding="utf-8")
        self.run_git(root, "add", "src/app.py")
        self.run_git(root, "commit", "-m", "move the head")

        # Finding ids are stable by construction (path, line, summary), because
        # the family-audit machinery matches findings across rounds by id. So
        # the protection against a stale rebuttal is not that the id changes:
        # it is that the receipt is keyed per target, and the disposition is a
        # per-invocation argument never stored against a later head.
        moved_result = self.run_stage(root, "head-two", "--local", "prism")
        moved_receipt = self.report(moved_result)["receipt"]

        self.assertEqual(moved_result.returncode, 1, moved_result.stdout)
        self.assertEqual(moved_receipt["disposition"]["outstanding"], 1)
        self.assertEqual(moved_receipt["disposition"].get("localDispositions"), {})
        self.assertEqual(moved_receipt["findings"][0]["disposition"], "outstanding")
        self.assertEqual(moved_receipt["remoteGate"]["state"], "blocked")

        # Re-supplying it on the new head is allowed, but it takes a deliberate
        # act by the caller rather than inheritance from the previous head.
        again = self.report(
            self.run_stage(
                root,
                "head-two",
                "--local",
                "prism",
                "--local-disposition",
                f"{identifier}=rebutted",
            )
        )["receipt"]
        self.assertEqual(again["disposition"]["outstanding"], 0)

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

    # --- .prism/rules.json handling -------------------------------------

    def write_prism_rules(self, root, payload) -> None:
        """Write .prism/rules.json and commit it, or write raw bytes verbatim."""
        rules = root / ".prism/rules.json"
        rules.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            rules.write_text(payload, encoding="utf-8")
        else:
            rules.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        self.run_git(root, "add", ".prism/rules.json")
        self.run_git(root, "commit", "-m", "add prism rules")

    def prism_rules_record(self, report):
        for row in report["receipt"]["attempts"]:
            if row["provider"]["id"] == "prism":
                return row["rules"]
        self.fail("no prism attempt in receipt")

    def test_prism_rules_are_passed_when_the_file_exists(self) -> None:
        root = self.make_repo()
        log = self.write_builtin_config(root)
        self.write_prism_rules(root, {"focus": ["bug"], "required": []})

        report = self.report(self.run_stage(root, "rules-applied"))

        self.assertIn("--rules .prism/rules.json", log.read_text(encoding="utf-8"))
        self.assertEqual(
            self.prism_rules_record(report),
            {"status": "applied", "path": ".prism/rules.json"},
        )

    def test_prism_argv_is_unchanged_when_no_rules_file_exists(self) -> None:
        root = self.make_repo()
        log = self.write_builtin_config(root)

        report = self.report(self.run_stage(root, "rules-absent"))

        invocation_log = log.read_text(encoding="utf-8")
        self.assertNotIn("--rules", invocation_log)
        self.assertIn("prism review range", invocation_log)
        self.assertEqual(
            self.prism_rules_record(report),
            {"status": "absent", "path": ".prism/rules.json"},
        )

    def test_prism_rules_carrying_severity_overrides_are_refused(self) -> None:
        root = self.make_repo()
        log = self.write_builtin_config(root)
        self.write_prism_rules(
            root,
            {
                "focus": ["bug"],
                "required": [],
                "severityOverrides": {"bug": "high"},
            },
        )

        result = self.run_stage(root, "rules-refused")
        report = self.report(result)

        # Refusing the rules file must not fail the review: running without
        # rules is the behaviour that shipped before the flag existed.
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["status"], "findings")
        self.assertNotIn("--rules", log.read_text(encoding="utf-8"))
        record = self.prism_rules_record(report)
        self.assertEqual(record["status"], "refused")
        self.assertEqual(record["path"], ".prism/rules.json")
        self.assertIn("severityOverrides", record["reason"])

    def test_unreadable_prism_rules_degrade_rather_than_raise(self) -> None:
        for label, payload in (
            ("not-json", "{ this is not json"),
            ("not-an-object", "[1, 2, 3]\n"),
        ):
            with self.subTest(label):
                root = self.make_repo()
                log = self.write_builtin_config(root)
                self.write_prism_rules(root, payload)

                result = self.run_stage(root, f"rules-{label}")
                report = self.report(result)

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertNotIn("--rules", log.read_text(encoding="utf-8"))
                record = self.prism_rules_record(report)
                self.assertEqual(record["status"], "unreadable")
                self.assertTrue(record["reason"])

    def test_gito_argv_is_untouched_by_the_rules_decision(self) -> None:
        root = self.make_repo()
        log = self.write_builtin_config(root)
        self.write_prism_rules(root, {"focus": ["bug"], "required": []})

        report = self.report(self.run_stage(root, "rules-gito"))

        gito_lines = [
            line
            for line in log.read_text(encoding="utf-8").splitlines()
            if line.startswith("gito ")
        ]
        self.assertTrue(gito_lines)
        for line in gito_lines:
            self.assertNotIn("--rules", line)
        gito = [
            row
            for row in report["receipt"]["attempts"]
            if row["provider"]["id"] == "gito"
        ]
        self.assertEqual(
            gito[0]["rules"], {"status": "not-applicable", "adapter": "gito"}
        )

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

    def test_gito_native_report_limit_is_inclusive(self) -> None:
        exact_root = self.make_repo()
        self.write_builtin_config(exact_root, gito_count=1_000)
        exact = self.run_stage(exact_root, "gito-limit", "--local", "gito")
        exact_report = self.report(exact)

        self.assertEqual(exact.returncode, 1, exact.stdout)
        self.assertEqual(len(exact_report["receipt"]["findings"]), 1_000)

    def test_gito_oversized_native_report_fails_closed(self) -> None:
        oversized_root = self.make_repo()
        self.write_builtin_config(oversized_root, gito_count=1_001)
        oversized = self.run_stage(oversized_root, "gito-oversized", "--local", "gito")
        oversized_report = self.report(oversized)

        self.assertEqual(oversized.returncode, 3, oversized.stdout)
        self.assertEqual(oversized_report["status"], "failed")
        self.assertIn(
            "valid structured review report",
            oversized_report["receipt"]["attempts"][0]["diagnostic"],
        )

    def test_gito_out_of_schema_severity_fails_closed(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, gito_severity=4)

        result = self.run_stage(root, "gito-severity", "--local", "gito")
        report = self.report(result)

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertEqual(report["status"], "failed")
        self.assertIn(
            "valid structured review report",
            report["receipt"]["attempts"][0]["diagnostic"],
        )

    def test_gito_string_severity_is_normalized(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, gito_severity="High")

        result = self.run_stage(root, "gito-string-severity", "--local", "gito")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["receipt"]["findings"][0]["severity"], "high")

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
        self.assertEqual(findings[0]["families"], ["boundary-validation", "other"])
        self.assertEqual(
            findings[0]["sourceFamilies"], ["boundary-validation", "security"]
        )
        self.assertEqual(report["receipt"]["disposition"]["outstanding"], 1)
        self.assertEqual(report["receipt"]["remoteGate"]["state"], "blocked")

    def test_whitespace_provider_family_normalizes_to_other_provenance(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("finding-whitespace", "clean"))

        result = self.run_stage(root, "finding-whitespace")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        findings = report["receipt"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["families"], ["other"])
        self.assertEqual(findings[0]["sourceFamilies"], ["other"])

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

        unknown = self.run_stage(
            root,
            "family-unknown",
            "--successor",
            "repeated-family",
            "--finding-family",
            "security",
            "--plan-only",
        )
        unknown_report = self.report(unknown)
        self.assertEqual(unknown.returncode, 2, unknown.stdout)
        self.assertIn("bounded vocabulary", unknown_report["diagnostic"])

    def test_second_same_family_round_requires_one_sibling_audit(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        evidence = self.write_family_evidence(
            root,
            current_round=2,
            blocked_redispatches=1,
            findings=[
                self.family_finding(root, "remote-one", 1, "boundary-validation"),
                self.family_finding(root, "remote-two", 2, "boundary-validation"),
            ],
        )

        planned = self.run_stage(
            root,
            "family-second-round-plan",
            "--family-evidence",
            str(evidence),
            "--plan-only",
        )
        planned_report = self.report(planned)

        self.assertEqual(planned.returncode, 0, planned.stdout)
        plan = planned_report["plan"]
        gate = plan["familyGate"]
        self.assertEqual(plan["policyId"], "repeated-family")
        self.assertEqual(
            [row["id"] for row in plan["providers"]], ["gito", "prism"]
        )
        self.assertEqual(gate["state"], "sibling-audit-required")
        self.assertEqual(gate["roundsAvoided"], 1)
        row = gate["families"][0]
        self.assertEqual(row["rounds"], [1, 2])
        self.assertEqual(
            [item["id"] for item in row["checklist"]],
            [
                "strict-types",
                "normalization",
                "persistence-invariants",
                "state-transitions",
                "replay-idempotency",
                "attempts-receipts",
                "exact-identity-head",
                "subprocess-failures",
                "permissions",
                "paths-symlinks-toctou",
                "controlled-diagnostics",
            ],
        )

        executed = self.run_stage(
            root,
            "family-second-round-run",
            "--family-evidence",
            str(evidence),
        )
        executed_report = self.report(executed)
        self.assertEqual(executed.returncode, 0, executed.stdout)
        self.assertEqual(
            executed_report["receipt"]["remoteGate"],
            {"state": "blocked", "reason": "sibling-audit-required"},
        )

    def test_unrelated_families_do_not_trigger_recurrence(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        evidence = self.write_family_evidence(
            root,
            current_round=2,
            findings=[
                self.family_finding(root, "boundary-one", 1, "boundary-validation"),
                self.family_finding(root, "generated-two", 2, "generated-surfaces"),
            ],
        )

        result = self.run_stage(
            root, "unrelated-families", "--family-evidence", str(evidence)
        )
        report = self.report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(report["receipt"]["plan"]["familyGate"]["state"], "observed")
        self.assertEqual(report["receipt"]["remoteGate"]["state"], "eligible")

    def test_complete_audit_allows_redispatch_and_reports_batch(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        evidence = self.write_family_evidence(
            root,
            current_round=2,
            findings=[
                self.family_finding(root, "remote-one", 1, "boundary-validation"),
                self.family_finding(root, "remote-two", 2, "boundary-validation"),
            ],
            audits=[self.completed_family_audit(root)],
        )

        result = self.run_stage(
            root,
            "family-audit-complete",
            "--family-evidence",
            str(evidence),
            "--plan-only",
        )
        report = self.report(result)
        gate = report["plan"]["familyGate"]

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(gate["state"], "redispatch-eligible")
        self.assertEqual(gate["siblingFindings"], 2)
        self.assertEqual(gate["batchSize"], 2)
        self.assertTrue(gate["families"][0]["auditComplete"])

    def test_empty_or_mismatched_sibling_batch_cannot_complete_audit(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        findings = [
            self.family_finding(root, "remote-one", 1, "boundary-validation"),
            self.family_finding(root, "remote-two", 2, "boundary-validation"),
        ]

        for batch_size, sibling_ids in (
            (0, []),
            (1, ["sibling-one", "sibling-two"]),
        ):
            with self.subTest(batch_size=batch_size, sibling_ids=sibling_ids):
                audit = self.completed_family_audit(root)
                audit["batchSize"] = batch_size
                audit["siblingFindingIds"] = sibling_ids
                evidence = self.write_family_evidence(
                    root,
                    current_round=2,
                    findings=findings,
                    audits=[audit],
                )

                result = self.run_stage(
                    root,
                    f"family-audit-incomplete-{batch_size}",
                    "--family-evidence",
                    str(evidence),
                    "--plan-only",
                )
                report = self.report(result)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertEqual(
                    report["plan"]["familyGate"]["state"],
                    "sibling-audit-required",
                )
                self.assertFalse(
                    report["plan"]["familyGate"]["families"][0]["auditComplete"]
                )

    def test_failed_local_audit_cannot_complete_sibling_gate(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        evidence = self.write_family_evidence(
            root,
            current_round=2,
            findings=[
                self.family_finding(root, "remote-one", 1, "boundary-validation"),
                self.family_finding(root, "remote-two", 2, "boundary-validation"),
            ],
            audits=[
                self.completed_family_audit(
                    root, outcome="failed", limitations=["prism:failed"]
                )
            ],
        )

        result = self.run_stage(
            root,
            "family-audit-failed",
            "--family-evidence",
            str(evidence),
            "--plan-only",
        )
        report = self.report(result)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            report["plan"]["familyGate"]["state"], "sibling-audit-required"
        )
        self.assertFalse(
            report["plan"]["familyGate"]["families"][0]["auditComplete"]
        )

    def test_post_audit_recurrence_requires_explicit_extension(self) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        findings = [
            self.family_finding(root, f"remote-{round_number}", round_number, "boundary-validation")
            for round_number in (1, 2, 3)
        ]
        evidence = self.write_family_evidence(
            root,
            current_round=3,
            findings=findings,
            audits=[self.completed_family_audit(root)],
        )

        blocked = self.run_stage(
            root, "family-extension-blocked", "--family-evidence", str(evidence)
        )
        blocked_report = self.report(blocked)

        self.assertEqual(blocked.returncode, 1, blocked.stdout)
        self.assertEqual(blocked_report["status"], "blocked")
        self.assertEqual(
            blocked_report["familyGate"]["state"], "round-extension-required"
        )
        self.assertFalse(log.exists())

        extended = self.write_family_evidence(
            root,
            current_round=3,
            findings=findings,
            audits=[self.completed_family_audit(root)],
            extensions=[
                {
                    "family": "boundary-validation",
                    "afterRound": 3,
                    "decisionId": "review.round-extension",
                    "approved": True,
                }
            ],
        )
        planned = self.run_stage(
            root,
            "family-extension-approved",
            "--family-evidence",
            str(extended),
            "--plan-only",
        )
        planned_report = self.report(planned)
        self.assertEqual(planned.returncode, 0, planned.stdout)
        self.assertEqual(
            planned_report["plan"]["familyGate"]["state"], "redispatch-eligible"
        )

    def test_family_evidence_rejects_wrong_head_and_multiple_fix_commits(self) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        findings = [
            self.family_finding(root, "remote-one", 1, "boundary-validation"),
            self.family_finding(root, "remote-two", 2, "boundary-validation"),
        ]
        evidence = self.write_family_evidence(
            root, current_round=2, findings=findings
        )
        value = json.loads(evidence.read_text(encoding="utf-8"))
        value["currentHead"] = "0" * 40
        evidence.write_text(json.dumps(value), encoding="utf-8")

        wrong_head = self.run_stage(
            root, "family-wrong-head", "--family-evidence", str(evidence)
        )
        self.assertEqual(wrong_head.returncode, 2, wrong_head.stdout)
        self.assertIn("exact review head", self.report(wrong_head)["diagnostic"])

        audit = self.completed_family_audit(root)
        audit["fixCommits"] = [
            self.git_output(root, "rev-parse", "HEAD"),
            "1" * 40,
        ]
        evidence = self.write_family_evidence(
            root, current_round=2, findings=findings, audits=[audit]
        )
        too_many = self.run_stage(
            root, "family-too-many-fixes", "--family-evidence", str(evidence)
        )
        self.assertEqual(too_many.returncode, 2, too_many.stdout)
        self.assertIn("at most one fix commit", self.report(too_many)["diagnostic"])
        self.assertFalse(log.exists())

    def test_family_evidence_rejects_symlink_and_oversized_file_before_dispatch(
        self,
    ) -> None:
        root = self.make_repo()
        log = self.write_config(root)
        evidence = self.write_family_evidence(
            root,
            current_round=1,
            findings=[
                self.family_finding(root, "remote-one", 1, "boundary-validation")
            ],
        )
        target = evidence.with_name("family-evidence-target.json")
        evidence.replace(target)
        try:
            evidence.symlink_to(target)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")

        symlinked = self.run_stage(
            root, "family-symlink", "--family-evidence", str(evidence)
        )
        self.assertEqual(symlinked.returncode, 2, symlinked.stdout)
        self.assertIn(
            "regular non-symlink file", self.report(symlinked)["diagnostic"]
        )
        self.assertFalse(log.exists())

        evidence.unlink()
        evidence.write_bytes(b"{" + b" " * (512 * 1024))
        oversized = self.run_stage(
            root, "family-oversized", "--family-evidence", str(evidence)
        )
        self.assertEqual(oversized.returncode, 2, oversized.stdout)
        self.assertIn("exceeds 524288 bytes", self.report(oversized)["diagnostic"])
        self.assertFalse(log.exists())

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

    def test_provider_timeout_does_not_become_clean(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("clean", "slow"), timeout=1)
        timeout = self.run_stage(root, "timeout", "--local", "gito")
        timeout_report = self.report(timeout)
        self.assertEqual(timeout.returncode, 3, timeout.stdout)
        self.assertEqual(timeout_report["status"], "failed")
        self.assertEqual(timeout_report["receipt"]["attempts"][0]["exitCode"], 124)

    def test_missing_provider_is_reported_as_unavailable(self) -> None:
        root = self.make_repo()
        self.write_config(root)
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

    def test_provider_output_is_bounded_before_parsing(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("large-output", "clean"))

        result = self.run_stage(root, "large-output", "--local", "prism")
        report = self.report(result)

        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertEqual(report["status"], "failed")
        output = root / ".build/sd-review/runs/large-output/prism/stdout.txt"
        self.assertEqual(output.stat().st_size, 4 * 1024 * 1024)

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

    @unittest.skipUnless(os.name == "posix", "POSIX signal behavior required")
    def test_signal_cancellation_emits_terminal_report_and_attempt(self) -> None:
        root = self.make_repo()
        log = self.write_config(root, modes=("slow", "clean"), timeout=5)
        cache = root.parent / "cache"
        cache.mkdir(mode=0o700, exist_ok=True)
        process = subprocess.Popen(
            [
                sys.executable,
                str(self.SCRIPT),
                "--repo",
                str(root),
                "--base",
                "main",
                "--attempt-id",
                "signal-cancelled",
                "--local",
                "prism",
                "--json",
            ],
            cwd=root,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "SD_AI_COMMAND_PACK_CACHE_ROOT": str(cache),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.addCleanup(
            lambda: process.kill() if process.poll() is None else None
        )
        deadline = time.monotonic() + 5
        while not log.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(log.exists(), "provider did not start before signal deadline")
        process.send_signal(signal.SIGTERM)
        stdout, _ = process.communicate(timeout=15)
        report = json.loads(stdout)

        self.assertEqual(process.returncode, 3, stdout)
        self.assertEqual(report["status"], "cancelled")
        attempt = report["receipt"]["attempts"][0]
        self.assertEqual(attempt["status"], "cancelled")
        attempt_path = (
            root / ".build/sd-review/runs/signal-cancelled/prism/attempt.json"
        )
        self.assertEqual(json.loads(attempt_path.read_text())["status"], "cancelled")

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

    def test_codebase_scope_requires_clean_exact_head(self) -> None:
        root = self.make_repo()
        self.write_config(root)

        clean = self.run_stage(
            root, "clean-codebase", "--scope", "codebase", "--plan-only"
        )
        self.assertEqual(clean.returncode, 0, clean.stdout)

        (root / "src/app.py").write_text("uncommitted\n", encoding="utf-8")
        dirty = self.run_stage(
            root, "dirty-codebase", "--scope", "codebase", "--plan-only"
        )
        dirty_report = self.report(dirty)

        self.assertEqual(dirty.returncode, 2, dirty.stdout)
        self.assertIn("clean worktree", dirty_report["diagnostic"])

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
        (root / ".gitignore").write_text(".build/\n.build-link\n", encoding="utf-8")
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

    def test_branch_scope_rejects_retry_collision(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        first = self.run_stage(root, "collision", "--local", "none")
        self.assertEqual(first.returncode, 0, first.stdout)
        collision = self.run_stage(root, "collision", "--local", "none", "--no-reuse")
        collision_report = self.report(collision)
        self.assertEqual(collision.returncode, 2, collision.stdout)
        self.assertIn("already exists", collision_report["diagnostic"])

    def test_branch_scope_rejects_dirty_worktree(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        (root / "src/app.py").write_text("dirty\n", encoding="utf-8")
        dirty = self.run_stage(root, "dirty")
        dirty_report = self.report(dirty)
        self.assertEqual(dirty.returncode, 2, dirty.stdout)
        self.assertIn("clean worktree", dirty_report["diagnostic"])


    # --- advisory severity ceiling and the miscited disposition ---------------

    def test_advisory_ceiling_reaches_the_plan_and_changes_the_policy_digest(
        self,
    ) -> None:
        """T1: the ceiling is carried on the plan, so it is inside policyDigest.

        Asserting only that the digest changed would prove nothing -- the
        configuration file changed too, and configurationDigest is already in
        the plan. What is checked instead is that the ceiling is the *only*
        added plan key, which fails if the value never reaches the plan.
        """

        strict_root = self.make_repo()
        self.write_config(strict_root)
        strict_plan = self.report(
            self.run_stage(strict_root, "digest-strict", "--local", "prism")
        )["receipt"]["plan"]

        ceiling_root = self.make_repo()
        self.write_config(ceiling_root, ceiling="medium")
        ceiling_plan = self.report(
            self.run_stage(ceiling_root, "digest-ceiling", "--local", "prism")
        )["receipt"]["plan"]

        self.assertNotIn("localAdvisorySeverityCeiling", strict_plan)
        self.assertEqual(ceiling_plan["localAdvisorySeverityCeiling"], "medium")
        self.assertEqual(
            set(ceiling_plan) ^ set(strict_plan), {"localAdvisorySeverityCeiling"}
        )
        self.assertNotEqual(ceiling_plan["policyDigest"], strict_plan["policyDigest"])

    def test_advisory_ceiling_rejects_high_and_unspecified_and_nonsense(self) -> None:
        """T2, T3: the two vocabulary members that are still refused, plus junk.

        ``high`` is refused because accepting it would let a policy author lower
        the blocking floor to nothing; ``unspecified`` because rank 0 means the
        provider classified nothing, which is the last thing a ceiling should
        release.
        """

        for index, value in enumerate(("high", "unspecified", "nonsense", "")):
            with self.subTest(ceiling=value):
                root = self.make_repo()
                self.write_config(root, ceiling=value)
                result = self.run_stage(root, f"bad-ceiling-{index}", "--local", "prism")

                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn(
                    "localAdvisorySeverityCeiling", self.report(result)["diagnostic"]
                )

    def test_advisory_ceiling_does_not_release_a_high_finding(self) -> None:
        """T4: the floor is not lowerable by the highest permitted ceiling."""

        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"), ceiling="medium")

        result = self.run_stage(root, "high-blocked", "--local", "prism")
        receipt = self.report(result)["receipt"]

        self.assertEqual(receipt["findings"][0]["severity"], "high")
        self.assertEqual(receipt["remoteGate"]["state"], "blocked")
        self.assertEqual(receipt["remoteGate"]["reason"], "actionable-local-findings")
        self.assertEqual(receipt["disposition"]["outstanding"], 1)
        self.assertEqual(receipt["disposition"]["advisory"], 0)

    def test_advisory_predicate_keeps_a_floor_a_wider_vocabulary_cannot_lower(
        self,
    ) -> None:
        """T4b: pins the `rank >= high` floor, which T4 cannot reach.

        The floor is redundant while the accepted ceilings are `low`/`medium` --
        `3 <= 2` already refuses a high finding. So the end-to-end test above
        passes with the floor deleted, and only a direct call with a ceiling the
        config layer refuses can pin it. It exists for whoever widens
        ``ADVISORY_CEILING_VALUES`` later; delete it and that change silently
        opens the gate on every high-severity defect.
        """

        module = self.load_module_from_path(self.SCRIPT, "sd_review_local_predicate")

        self.assertFalse(module._is_advisory({"severity": "high"}, "high"))
        self.assertTrue(module._is_advisory({"severity": "medium"}, "high"))
        self.assertFalse(module._is_advisory({"severity": "high"}, "medium"))
        self.assertFalse(module._is_advisory({"severity": "low"}, None))

    def test_advisory_ceiling_releases_a_finding_at_or_below_it(self) -> None:
        """T5: the case the whole task exists for."""

        root = self.make_repo()
        self.write_config(root, modes=("severity-low", "clean"), ceiling="medium")

        receipt = self.report(
            self.run_stage(root, "low-released", "--local", "prism")
        )["receipt"]

        self.assertEqual(receipt["findings"][0]["severity"], "low")
        self.assertEqual(receipt["remoteGate"]["state"], "eligible")
        self.assertEqual(receipt["remoteGate"]["reason"], "local-advisory-released")
        self.assertEqual(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(receipt["disposition"]["advisory"], 1)
        # Released, not deleted and not silently dispositioned: the finding is
        # still outstanding, and the receipt still says so.
        self.assertEqual(receipt["findings"][0]["disposition"], "outstanding")

    def test_advisory_ceiling_never_releases_an_unclassified_finding(self) -> None:
        """T6, T7: rank 0 blocks, whether it is the sentinel or an unknown word.

        A provider that omits ``severity`` -- or invents one -- must not get a
        cheaper gate than one that classifies honestly, or omission becomes the
        escape.
        """

        for mode, expected in (
            ("severity-unspecified", "unspecified"),
            ("severity-bizarre", "bizarre"),
        ):
            with self.subTest(mode=mode):
                root = self.make_repo()
                self.write_config(root, modes=(mode, "clean"), ceiling="medium")
                receipt = self.report(
                    self.run_stage(root, "rank-zero", "--local", "prism")
                )["receipt"]

                self.assertEqual(receipt["findings"][0]["severity"], expected)
                self.assertEqual(receipt["remoteGate"]["state"], "blocked")
                self.assertEqual(receipt["disposition"]["outstanding"], 1)
                self.assertEqual(receipt["disposition"]["advisory"], 0)

    def test_no_ceiling_blocks_on_a_low_finding(self) -> None:
        """T8: omission is strict -- exactly today's behaviour."""

        root = self.make_repo()
        self.write_config(root, modes=("severity-low", "clean"))

        receipt = self.report(
            self.run_stage(root, "strict-low", "--local", "prism")
        )["receipt"]

        self.assertEqual(receipt["remoteGate"]["state"], "blocked")
        self.assertEqual(receipt["remoteGate"]["reason"], "actionable-local-findings")
        self.assertEqual(receipt["disposition"]["outstanding"], 1)
        self.assertEqual(receipt["disposition"]["advisory"], 0)

    def test_miscited_is_recorded_with_its_citation_and_not_as_rebutted(self) -> None:
        """T9: the ground is distinct, and the caller's evidence is stored."""

        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))
        blocked = self.report(self.run_stage(root, "miscite", "--local", "prism"))
        identifier = blocked["receipt"]["findings"][0]["id"]

        receipt = self.report(
            self.run_stage(
                root,
                "miscite",
                "--local",
                "prism",
                "--local-disposition",
                f"{identifier}=miscited@src/other.py:41",
            )
        )["receipt"]
        finding = receipt["findings"][0]

        self.assertEqual(finding["disposition"], "miscited")
        self.assertEqual(
            finding["dispositionCitation"], {"path": "src/other.py", "line": 41}
        )
        # Both locations survive: what the provider claimed, and what the caller
        # checked. That is what makes the assertion auditable rather than a
        # blanket suppression.
        self.assertEqual(finding["path"], "src/app.py")
        self.assertEqual(finding["line"], 2)
        self.assertEqual(
            receipt["disposition"]["localDispositions"], {identifier: "miscited"}
        )

    def test_miscited_releases_a_high_finding_that_otherwise_blocks(self) -> None:
        """T10: one test, both halves -- the ground works and the gate is real."""

        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))

        blocked = self.report(self.run_stage(root, "high-miscite", "--local", "prism"))
        self.assertEqual(blocked["receipt"]["remoteGate"]["state"], "blocked")
        identifier = blocked["receipt"]["findings"][0]["id"]

        cleared = self.report(
            self.run_stage(
                root,
                "high-miscite",
                "--local",
                "prism",
                "--local-disposition",
                f"{identifier}=miscited@src/app.py:99",
            )
        )["receipt"]

        self.assertEqual(cleared["remoteGate"]["state"], "eligible")
        self.assertEqual(
            cleared["remoteGate"]["reason"], "local-findings-dispositioned"
        )
        self.assertEqual(cleared["disposition"]["outstanding"], 0)
        self.assertEqual(cleared["disposition"]["dispositioned"], 1)

    def test_miscited_grammar_requires_a_usable_citation(self) -> None:
        """T11, plus the `=`-in-path trap that rpartition would misreport."""

        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))
        self.run_stage(root, "miscite-grammar", "--local", "prism")

        cases = (
            ("abc=miscited", "<path>:<line>"),
            ("abc=miscited@", "<path>:<line>"),
            ("abc=miscited@src/app.py", "<path>:<line>"),
            ("abc=miscited@src/app.py:", "<path>:<line>"),
            ("abc=miscited@src/app.py:zero", "<path>:<line>"),
            # str.isdigit accepts characters int() refuses: superscript two
            # escaped as an uncaught ValueError, and the fullwidth digits
            # parsed silently to a line the caller never wrote.
            ("abc=miscited@src/app.py:\u00b2", "<path>:<line>"),
            ("abc=miscited@src/app.py:\uff11\uff12\uff13", "<path>:<line>"),
            ("abc=miscited@src/app.py:" + "9" * 5000, "<path>:<line>"),
            ("abc=miscited@:3", "<path>:<line>"),
            ("abc=miscited@src/app.py:0", "line is out of range"),
            ("abc=miscited@../secret.py:3", "unsafe or unbounded"),
            ("abc=miscited@/etc/passwd:3", "unsafe or unbounded"),
            ("abc=miscited@a=b.py:3", "cannot contain '='"),
            ("abc=rebutted@src/app.py:3", "only miscited accepts a citation"),
        )
        for index, (token, expected) in enumerate(cases):
            with self.subTest(token=token):
                result = self.run_stage(
                    root,
                    f"miscite-bad-{index}",
                    "--local",
                    "prism",
                    "--local-disposition",
                    token,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout)
                # The contract is a bounded input error, not merely a non-zero
                # exit: a traceback is a different failure wearing the same
                # code. run_stage merges stderr into stdout, so this sees it.
                self.assertNotIn("Traceback", result.stdout)

    def test_one_advisory_finding_does_not_release_a_blocking_sibling(self) -> None:
        """T12: the counts are per-finding, not a whole-receipt verdict."""

        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"), ceiling="medium")

        receipt = self.report(
            self.run_stage(root, "mixed", "--local", "prism")
        )["receipt"]

        self.assertEqual(len(receipt["findings"]), 2)
        self.assertEqual(receipt["remoteGate"]["state"], "blocked")
        self.assertEqual(receipt["disposition"]["outstanding"], 1)
        self.assertEqual(receipt["disposition"]["advisory"], 1)

    def test_disposition_reason_outranks_advisory_release(self) -> None:
        """T13: report the strongest claim the receipt supports."""

        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"), ceiling="medium")
        blocked = self.report(self.run_stage(root, "precedence", "--local", "prism"))
        high = next(
            item
            for item in blocked["receipt"]["findings"]
            if item["severity"] == "high"
        )

        receipt = self.report(
            self.run_stage(
                root,
                "precedence",
                "--local",
                "prism",
                "--local-disposition",
                f"{high['id']}=rebutted",
            )
        )["receipt"]

        self.assertEqual(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(receipt["disposition"]["advisory"], 1)
        self.assertEqual(receipt["disposition"]["dispositioned"], 1)
        self.assertEqual(receipt["remoteGate"]["state"], "eligible")
        self.assertEqual(
            receipt["remoteGate"]["reason"], "local-findings-dispositioned"
        )



    # --- PR #353: a Markdown-only diff whose fences quote source -------------

    def test_markdown_only_diff_misread_as_source_is_clearable_by_rebuttal(
        self,
    ) -> None:
        """The originating case for the local rebuttal channel, as a regression.

        PR #353 added four `.trellis/tasks/` artifacts and no code file at all.
        The provider returned three findings, at the three fenced blocks where
        the PRD *quoted* source as evidence of the defects it was filing -- it
        read the quotations as the diff's own code and re-reported the documented
        defects as new ones. That generalizes: every defect-filing PRD quotes the
        defect it documents, so the whole task-filing workflow is a
        false-positive generator under that reader.

        What is pinned here is the pack's half of the problem, which is the half
        the pack owns: findings on a diff with no source file in it are
        rebuttable per finding, the gate opens once every one is dispositioned,
        and each rebuttal stays in the receipt to be audited. Making the provider
        stop misreading a fence is not something this repository can assert.
        """

        root = self.make_repo(changed_path="docs/prd.md")
        self.write_config(root, modes=("markdown-fenced-quotes", "clean"))

        blocked = self.report(self.run_stage(root, "fenced", "--local", "prism"))
        receipt = blocked["receipt"]

        # The scenario's premise: no source file is under review at all.
        self.assertNotIn(
            ".py", {Path(row["path"]).suffix for row in receipt["target"]["paths"]}
        )
        self.assertEqual(len(receipt["findings"]), 3)
        self.assertEqual(
            {item["path"] for item in receipt["findings"]}, {"docs/prd.md"}
        )
        self.assertEqual(receipt["remoteGate"]["state"], "blocked")
        self.assertEqual(receipt["disposition"]["outstanding"], 3)

        identifiers = [item["id"] for item in receipt["findings"]]
        cleared = self.report(
            self.run_stage(
                root,
                "fenced",
                "--local",
                "prism",
                *[
                    token
                    for identifier in identifiers
                    for token in ("--local-disposition", f"{identifier}=rebutted")
                ],
            )
        )["receipt"]

        self.assertEqual(cleared["remoteGate"]["state"], "eligible")
        self.assertEqual(
            cleared["remoteGate"]["reason"], "local-findings-dispositioned"
        )
        self.assertEqual(cleared["disposition"]["outstanding"], 0)
        self.assertEqual(cleared["disposition"]["dispositioned"], 3)
        # All three survive *as evidence*, which is more than surviving as
        # three entries: a channel that kept the ids and dropped the location
        # and summary would clear the gate and leave the next reader nothing to
        # audit. Compare the full evidence rows, not the count.
        def evidence(receipt):
            return sorted(
                (item["id"], item["path"], item["line"], item["summary"])
                for item in receipt["findings"]
            )

        self.assertEqual(evidence(cleared), evidence(receipt))
        self.assertEqual(
            {item["disposition"] for item in cleared["findings"]}, {"rebutted"}
        )
        self.assertEqual(
            cleared["disposition"]["localDispositions"],
            {identifier: "rebutted" for identifier in identifiers},
        )

    def test_the_hallucinated_typo_from_pr_353_takes_the_miscited_ground(
        self,
    ) -> None:
        """The fourth finding, and the ground that fits it better than rebuttal.

        Retagging the fences to `text` cleared the three above and produced a
        new one: *"Typographical error: 'descision' should be 'decision'"* at
        `prd.md:140`. Line 140 read `decision`, spelled correctly, and `grep -rn
        descision` returned nothing in the file, the PR, or the repository.

        `rebutted` would clear it, but it asserts the wrong thing -- the claim is
        not merely false, it names a location whose text does not contain what it
        describes. That is what `miscited` is for, and the citation the caller
        supplies is exactly the line they checked.
        """

        root = self.make_repo(changed_path="docs/prd.md")
        self.write_config(root, modes=("markdown-hallucinated-typo", "clean"))

        blocked = self.report(self.run_stage(root, "typo", "--local", "prism"))
        finding = blocked["receipt"]["findings"][0]
        self.assertEqual(blocked["receipt"]["remoteGate"]["state"], "blocked")
        self.assertEqual(finding["line"], 140)

        cleared = self.report(
            self.run_stage(
                root,
                "typo",
                "--local",
                "prism",
                "--local-disposition",
                f"{finding['id']}=miscited@docs/prd.md:140",
            )
        )["receipt"]
        dispositioned = cleared["findings"][0]

        self.assertEqual(cleared["remoteGate"]["state"], "eligible")
        self.assertEqual(dispositioned["disposition"], "miscited")
        # Provider's cited location and the caller's agree here, which is the
        # point: the caller read that exact line and the described text is not
        # on it. Both are recorded either way, so a reader can check.
        self.assertEqual(
            dispositioned["dispositionCitation"], {"path": "docs/prd.md", "line": 140}
        )
        self.assertEqual(dispositioned["line"], 140)



if __name__ == "__main__":
    unittest.main()
