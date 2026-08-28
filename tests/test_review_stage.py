from __future__ import annotations

import shutil
import signal
import time
from unittest import mock

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

    def runner_refused_rules_keys(self) -> dict:
        """Read ``REFUSED_RULES_KEYS`` out of the script without importing it.

        The stage is exercised as a subprocess everywhere else in this module,
        and importing it here to read one constant would run its module body
        under the test process. Parsing the source is the cheaper honesty: it
        reads what ships, and it fails loudly if the constant is renamed or
        stops being a literal rather than silently reporting an empty set.
        """
        import ast

        tree = ast.parse(self.SCRIPT.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "REFUSED_RULES_KEYS" in names:
                return ast.literal_eval(node.value)
        raise AssertionError(
            "REFUSED_RULES_KEYS is not a module-level literal in "
            f"{self.SCRIPT.name}; the schema/runner binding test cannot read it"
        )

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
        codex_mode: str | None = None,
        codex_executable: bool = True,
        gito_move_head: bool = False,
    ) -> Path:
        """Configure builtin adapters backed by the fixture executable.

        ``codex_mode`` adds a codex provider; ``codex_executable=False`` keeps
        that provider configured but leaves no ``codex`` on PATH.
        """
        providers = []
        if codex_mode is not None:
            providers.append(
                {
                    "id": "codex",
                    "adapter": "codex",
                    "argv": [],
                    "scopes": ["worktree", "branch_delta"],
                    "dataHandling": "local",
                    "costTier": "none",
                    "qualityTier": "deep",
                    "timeoutSeconds": 5,
                    "version": "fixture-v1",
                    "enabled": True,
                    "outcomeByExitCode": {"0": "clean", "1": "unavailable"},
                }
            )
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
                    "codexMode": codex_mode or "finding",
                    "gitoMoveHead": gito_move_head,
                }
            ),
            encoding="utf-8",
        )
        payload = fixture.read_bytes()
        executables = ["prism", "gito"]
        if codex_mode is not None and codex_executable:
            executables.append("codex")
        for provider in executables:
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
        self.assertIn("gito review --what", invocation_log)
        self.assertNotIn("--filter", invocation_log)

    # --- codex adapter ---------------------------------------------------

    def attempt(self, report, identifier):
        for row in report["receipt"]["attempts"]:
            if row["provider"]["id"] == identifier:
                return row
        self.fail(f"no {identifier} attempt in receipt")

    def codex_attempt(self, report):
        return self.attempt(report, "codex")

    def test_codex_adapter_seeds_schema_and_reads_the_answer_file(self) -> None:
        root = self.make_repo()
        log = self.write_builtin_config(root, codex_mode="finding")

        result = self.run_stage(root, "codex-native")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["status"], "findings")
        self.assertIn(
            "Codex finding",
            [finding["summary"] for finding in report["receipt"]["findings"]],
        )
        codex = self.codex_attempt(report)
        self.assertEqual(codex["status"], "findings")
        invocation = log.read_text(encoding="utf-8")
        self.assertIn(
            "codex exec --sandbox read-only --ignore-user-config "
            "--ignore-rules --ephemeral -C",
            invocation,
        )
        # execpolicy .rules load on their own path, not through config.toml.
        self.assertIn("--ignore-rules", invocation)
        # No session transcript of the reviewed diff outside the run's own
        # bounded artifact directory.
        self.assertIn("--ephemeral", invocation)
        self.assertIn("--output-schema", invocation)
        self.assertIn("--output-last-message", invocation)
        self.assertIn("-c project_doc_max_bytes=0", invocation)
        # read-only bounds the shell, not the MCP servers the user's
        # config.toml would otherwise hand a model that is reading untrusted
        # diff text. The lane refuses that file outright.
        self.assertIn("--ignore-user-config", invocation)
        # Codex receives the exact refs the coordinator resolved, not a
        # branch name it would have to resolve itself.
        target = report["receipt"]["target"]
        self.assertIn(f"git diff {target['base']}..{target['head']}", invocation)

    def test_codex_adapter_clean_answer_does_not_block(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(
            root, codex_mode="clean", prism_mode="clean", gito_count=0
        )

        report = self.report(self.run_stage(root, "codex-clean", "--local", "codex"))

        self.assertEqual(self.codex_attempt(report)["status"], "clean")
        self.assertEqual(report["receipt"]["findings"], [])

    def test_codex_adapter_unavailable_when_binary_is_missing(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, codex_mode="finding", codex_executable=False)
        # The adapter always resolves the bare name ``codex``, so a real
        # install on the developer machine must be hidden from this run.
        # Rebuilding the path from git's own directory hid codex only on a
        # machine that keeps the two apart, and dropping every directory
        # that holds a codex takes the rest of that directory down with it --
        # a Homebrew prefix, /usr/local/bin, or a Nix profile carries git and
        # python3 beside codex, and the fixtures are `#!/usr/bin/env python3`
        # scripts that still need an interpreter. Replace such a directory in
        # place with a shim exposing everything it offered except codex, so
        # the entry keeps its position and only the one name disappears.
        fake_bin = root.parent / "bin"
        entries = []
        for index, entry in enumerate(os.environ.get("PATH", "").split(os.pathsep)):
            if not entry:
                continue
            if not os.path.exists(os.path.join(entry, "codex")):
                entries.append(entry)
                continue
            shim = root.parent / f"codex-free-{index}"
            shim.mkdir(parents=True, exist_ok=True)
            for item in os.listdir(entry):
                if item == "codex":
                    continue
                link = shim / item
                if link.is_symlink() or link.exists():
                    continue
                link.symlink_to(os.path.join(entry, item))
            entries.append(str(shim))
        isolated = {"PATH": os.pathsep.join([str(fake_bin), *entries])}

        with mock.patch.dict(os.environ, isolated):
            self.assertIsNone(
                shutil.which("codex"),
                "a real codex is reachable on the isolated PATH",
            )
            report = self.report(self.run_stage(root, "codex-missing"))

        self.assertEqual(self.codex_attempt(report)["status"], "unavailable")
        # The other lanes still ran and their findings survive.
        self.assertEqual(
            sorted(finding["summary"] for finding in report["receipt"]["findings"]),
            ["Gito finding", "Prism finding"],
        )

    def test_codex_adapter_logged_out_maps_to_unavailable(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, codex_mode="logged-out")

        report = self.report(self.run_stage(root, "codex-logged-out"))

        self.assertEqual(self.codex_attempt(report)["status"], "unavailable")
        self.assertEqual(report["status"], "findings")

    def test_codex_adapter_invalid_answer_is_a_failure_not_clean(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, codex_mode="invalid")

        report = self.report(self.run_stage(root, "codex-invalid", "--local", "codex"))

        self.assertEqual(self.codex_attempt(report)["status"], "failed")

    def test_cheapest_policy_falls_back_past_an_unavailable_codex(self) -> None:
        root = self.make_repo(changed_path="docs/guide.md")
        self.write_builtin_config(
            root, codex_mode="logged-out", prism_mode="finding", gito_count=0
        )
        # Uncommitted, documentation-only, so the worktree target takes the
        # documentation-cheapest policy rather than the substantive ensemble.
        (root / "docs/guide.md").write_text("seed\nchanged\nagain\n", encoding="utf-8")

        result = self.run_stage(root, "codex-fallback", "--scope", "changes")
        report = self.report(result)

        self.assertEqual(report["receipt"]["plan"]["policyId"], "documentation-cheapest")
        self.assertEqual(
            [row["id"] for row in report["receipt"]["plan"]["providers"]], ["codex"]
        )
        self.assertEqual(
            [(row["provider"]["id"], row["status"]) for row in report["receipt"]["attempts"]],
            [("codex", "unavailable"), ("prism", "findings")],
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(report["status"], "findings")

    def test_a_clean_fallback_reviews_the_change_instead_of_failing(self) -> None:
        """The PRD's requirement: a logged-out codex degrades to the other
        lanes rather than failing the run. The fallback tests above only ever
        watched a fallback that *found* something, where the aggregate is
        ``findings`` either way -- so nothing covered the case where the
        fallback comes back clean and the primary's ``unavailable`` is the
        only failing status left to outrank it."""
        root = self.make_repo(changed_path="docs/guide.md")
        self.write_builtin_config(
            root, codex_mode="logged-out", prism_mode="clean", gito_count=0
        )
        (root / "docs/guide.md").write_text("seed\nchanged\nagain\n", encoding="utf-8")

        result = self.run_stage(root, "codex-fallback-clean", "--scope", "changes")
        report = self.report(result)

        self.assertEqual(
            [(row["provider"]["id"], row["status"]) for row in report["receipt"]["attempts"]],
            [("codex", "unavailable"), ("prism", "clean")],
        )
        # The unavailable primary keeps its own status in the receipt -- which
        # lane was asked and what it answered stays readable -- but records
        # the fallback that covered it and stops deciding the aggregate.
        self.assertEqual(self.codex_attempt(report)["supersededBy"], "prism")
        self.assertEqual(report["receipt"]["outcome"], "clean")
        self.assertEqual(
            report["receipt"]["confidence"], {"granted": True, "limitations": []}
        )
        self.assertEqual(report["receipt"]["remoteGate"]["state"], "eligible")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_an_absent_optional_lane_does_not_fail_a_run_the_others_reviewed(
        self,
    ) -> None:
        """A substantive review selects codex as a lane rather than a
        fallback, so nothing supersedes it and its absence used to decide the
        outcome -- every repository without codex installed failed every
        substantive review. Absence is a smaller ensemble, not a wrong
        answer."""
        root = self.make_repo()
        self.write_builtin_config(
            root, codex_mode="logged-out", prism_mode="clean", gito_count=0
        )

        result = self.run_stage(root, "codex-absent-ensemble", "--local", "all")
        report = self.report(result)
        receipt = report["receipt"]

        self.assertEqual(
            [(row["provider"]["id"], row["status"]) for row in receipt["attempts"]],
            [("codex", "unavailable"), ("gito", "clean"), ("prism", "clean")],
        )
        self.assertEqual(receipt["outcome"], "clean")
        self.assertEqual(result.returncode, 0, result.stdout)
        # Reduced, and the receipt says so: the lane is still a limitation and
        # confidence is still withheld. It just does not fail the run.
        self.assertIn("codex:unavailable", receipt["confidence"]["limitations"])
        self.assertFalse(receipt["confidence"]["granted"])

    def test_a_declined_lane_still_lets_a_fallback_review_the_change(self) -> None:
        """A decline leaves the ensemble as short as an unavailable does, and
        the fallback is a different tool the reviewed change does not taint --
        so the fallback that exists to cover that gap has to run."""
        root = self.make_repo(changed_path=".agents/skills/probe/SKILL.md")
        self.write_builtin_config(
            root, codex_mode="finding", prism_mode="clean", gito_count=0
        )
        # The decline is decided from the reviewed paths, so the skill has to
        # be in this scope's diff rather than merely present in the checkout.
        (root / ".agents/skills/probe/SKILL.md").write_text(
            "seed\nchanged\nagain\n", encoding="utf-8"
        )

        result = self.run_stage(root, "codex-declined-fallback", "--scope", "changes")
        report = self.report(result)

        attempts = [
            (row["provider"]["id"], row["status"])
            for row in report["receipt"]["attempts"]
        ]
        self.assertEqual(attempts, [("codex", "skipped"), ("prism", "clean")])
        # Covered by a lane that actually read the change, so the decline
        # stops deciding the aggregate and stops being a limitation.
        self.assertEqual(self.codex_attempt(report)["supersededBy"], "prism")
        self.assertEqual(report["receipt"]["outcome"], "clean")
        self.assertEqual(
            report["receipt"]["confidence"], {"granted": True, "limitations": []}
        )

    def test_a_required_lane_that_declines_still_degrades_the_gate(self) -> None:
        """``requiredProviders`` says that lane must actually run. A lane
        declining to is not an answer to that, any more than a fallback
        standing in for it is."""
        root = self.make_repo(changed_path=".agents/skills/probe/SKILL.md")
        # Every other lane clean, so the gate's verdict turns on the
        # required lane's absence rather than on somebody's findings.
        self.write_builtin_config(
            root, codex_mode="finding", prism_mode="clean", gito_count=0
        )
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value.setdefault("policy", {})["requiredProviders"] = ["codex"]
        config.write_text(json.dumps(value) + "\n", encoding="utf-8")
        self.run_git(root, "add", ".sd-ai-command-pack/review.json")
        self.run_git(root, "commit", "-m", "require the codex lane")

        report = self.report(self.run_stage(root, "codex-required-decline"))

        codex = self.codex_attempt(report)
        self.assertEqual(codex["status"], "skipped")
        self.assertNotIn("supersededBy", codex)
        self.assertIn("codex:skipped", report["receipt"]["confidence"]["limitations"])
        self.assertNotEqual(report["receipt"]["remoteGate"]["state"], "eligible")

    def test_a_lane_mapped_to_skipped_still_lets_a_fallback_review(self) -> None:
        """Absence of any shape lets the fallback run. A lane whose exit a
        repository maps to ``skipped`` reviewed nothing, exactly like a
        missing one, so treating it as "somebody reported" left the change
        unreviewed with nothing saying so."""
        root = self.make_repo(changed_path="docs/guide.md")
        self.write_builtin_config(
            root, codex_mode="logged-out", prism_mode="clean", gito_count=0
        )
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        for provider in value["providers"]:
            if provider["id"] == "codex":
                provider["outcomeByExitCode"] = {"0": "clean", "1": "skipped"}
        config.write_text(json.dumps(value) + "\n", encoding="utf-8")
        self.run_git(root, "add", ".sd-ai-command-pack/review.json")
        self.run_git(root, "commit", "-m", "map the codex lane to skipped")
        (root / "docs/guide.md").write_text("seed\nchanged\nagain\n", encoding="utf-8")

        report = self.report(
            self.run_stage(root, "codex-skipped-fallback", "--scope", "changes")
        )

        self.assertEqual(
            [(row["provider"]["id"], row["status"]) for row in report["receipt"]["attempts"]],
            [("codex", "skipped"), ("prism", "clean")],
        )
        self.assertEqual(report["receipt"]["outcome"], "clean")

    def test_a_required_lane_mapped_to_skipped_still_degrades_the_gate(self) -> None:
        """The third way out of running. ``skipped`` is neither a terminal
        failure nor a decline, so a repository that maps an exit code to it
        could have its required lane read nothing and still be told the
        review was clean, ungraded, and confident."""
        root = self.make_repo()
        # A valid provider payload overrides the exit-code mapping, so
        # ``skipped`` is only reachable through an exit that produced no
        # report at all -- here the rate-limit mode, remapped.
        self.write_config(root, modes=("clean", "rate-limit"), required=["gito"])
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        for provider in value["providers"]:
            if provider["id"] == "gito":
                provider["outcomeByExitCode"]["8"] = "skipped"
        config.write_text(json.dumps(value) + "\n", encoding="utf-8")
        self.run_git(root, "add", ".sd-ai-command-pack/review.json")
        self.run_git(root, "commit", "-m", "require a lane that maps to skipped")

        report = self.report(self.run_stage(root, "required-skipped", "--local", "all"))
        receipt = report["receipt"]

        self.assertEqual(self.attempt(report, "gito")["status"], "skipped")
        self.assertIn("gito:skipped", receipt["confidence"]["limitations"])
        self.assertFalse(receipt["confidence"]["granted"])
        self.assertNotEqual(receipt["remoteGate"]["state"], "eligible")

    def test_a_fallback_does_not_cover_a_required_provider(self) -> None:
        """``requiredProviders`` says that lane must actually run. A cheaper
        substitute clearing its limitation would let the fallback list
        override a policy the repository wrote."""
        root = self.make_repo(changed_path="docs/guide.md")
        self.write_builtin_config(
            root, codex_mode="logged-out", prism_mode="clean", gito_count=0
        )
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value.setdefault("policy", {})["requiredProviders"] = ["codex"]
        config.write_text(json.dumps(value) + "\n", encoding="utf-8")
        self.run_git(root, "add", ".sd-ai-command-pack/review.json")
        self.run_git(root, "commit", "-m", "require the codex lane")
        (root / "docs/guide.md").write_text("seed\nchanged\nagain\n", encoding="utf-8")

        report = self.report(
            self.run_stage(root, "codex-required", "--scope", "changes")
        )

        codex = self.codex_attempt(report)
        self.assertEqual(codex["status"], "unavailable")
        self.assertNotIn("supersededBy", codex)
        self.assertIn(
            "codex:unavailable", report["receipt"]["confidence"]["limitations"]
        )

    def test_an_unavailable_lane_beside_a_running_one_still_limits_the_run(
        self,
    ) -> None:
        """Supersession is not "ignore every unavailable provider". No
        fallback runs while some selected provider is still working, so the
        ensemble is genuinely reduced and the receipt has to say so."""
        # A genuinely broken lane, not one that declined: a lane that steps
        # aside for independence reports ``skipped`` and is covered by
        # test_a_lane_that_declined_does_not_block_a_clean_review.
        root = self.make_repo()
        self.write_builtin_config(root, codex_mode="logged-out")

        report = self.report(self.run_stage(root, "codex-reduced-ensemble"))

        codex = self.codex_attempt(report)
        self.assertEqual(codex["status"], "unavailable")
        self.assertNotIn("supersededBy", codex)
        self.assertIn("codex:unavailable", report["receipt"]["confidence"]["limitations"])
        self.assertFalse(report["receipt"]["confidence"]["granted"])

    def test_worktree_review_rejects_a_tree_that_moved_during_the_run(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, codex_mode="mutate")
        (root / "src/app.py").write_text("seed\nchanged\nmore\n", encoding="utf-8")

        result = self.run_stage(
            root, "codex-drift", "--scope", "changes", "--local", "codex"
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("working tree changed while the local review ran", result.stdout)

    def test_low_risk_successor_falls_back_past_an_unavailable_codex(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(
            root, codex_mode="logged-out", prism_mode="finding", gito_count=0
        )

        result = self.run_stage(
            root, "codex-successor", "--successor", "low-risk"
        )
        report = self.report(result)

        self.assertEqual(report["receipt"]["plan"]["policyId"], "low-risk-successor")
        self.assertEqual(
            [(row["provider"]["id"], row["status"]) for row in report["receipt"]["attempts"]],
            [("codex", "unavailable"), ("prism", "findings")],
        )

    def test_branch_review_rejects_a_tree_that_became_dirty_during_the_run(
        self,
    ) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, codex_mode="mutate")

        result = self.run_stage(root, "codex-branch-drift", "--local", "codex")

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("became dirty while provider(s) codex", result.stdout)

    def test_codebase_review_rejects_a_head_that_moved_during_the_run(
        self,
    ) -> None:
        # The dirtiness re-check cannot see this: an empty commit moves HEAD
        # and leaves the tree clean, so before the codebase branch of
        # _reconfirm_tree_binding existed the receipt named a commit the
        # provider never read.
        root = self.make_repo()
        self.write_builtin_config(root, gito_move_head=True)

        result = self.run_stage(
            root, "gito-codebase-drift", "--scope", "codebase", "--local", "gito"
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("HEAD moved while the local review ran", result.stdout)

    def test_codex_lane_steps_aside_when_the_change_edits_its_own_skills(
        self,
    ) -> None:
        root = self.make_repo(changed_path=".agents/skills/probe/SKILL.md")
        self.write_builtin_config(root, codex_mode="finding")

        report = self.report(self.run_stage(root, "codex-tainted"))

        codex = self.codex_attempt(report)
        # Declining for independence is not a failure. Recording it as one
        # made every change to these paths permanently unreviewable, because
        # the guard fires on exactly the paths this pack ships.
        self.assertEqual(codex["status"], "skipped")
        self.assertTrue(codex["declined"])
        self.assertIn("instruction surfaces codex loads", codex["diagnostic"])
        # The lane steps aside; the others still review the change.
        self.assertEqual(
            sorted(finding["summary"] for finding in report["receipt"]["findings"]),
            ["Gito finding", "Prism finding"],
        )
        # Visible in the receipt, but it does not degrade the gate.
        self.assertIn("codex:skipped", report["receipt"]["confidence"]["limitations"])

    def test_a_lane_that_declined_does_not_block_a_clean_review(self) -> None:
        # The whole point of the status change: a change editing codex's own
        # instruction surfaces must still be able to reach a clean review on
        # the strength of the lanes that can read it.
        root = self.make_repo(changed_path=".agents/skills/probe/SKILL.md")
        self.write_builtin_config(
            root, codex_mode="finding", prism_mode="clean", gito_count=0
        )

        report = self.report(self.run_stage(root, "codex-declined-clean"))

        receipt = report["receipt"]
        self.assertEqual(self.codex_attempt(report)["status"], "skipped")
        self.assertEqual(receipt["outcome"], "clean")
        self.assertTrue(receipt["confidence"]["granted"])
        self.assertIn("codex:skipped", receipt["confidence"]["limitations"])
        self.assertNotEqual(receipt["remoteGate"]["reason"], "local-review-limited")

    def test_deleting_a_skill_does_not_make_the_codex_lane_step_aside(self) -> None:
        """Nothing is left at the path for codex to load, so the change
        cannot write into its own reviewer's context."""
        root = self.make_repo(changed_path=".agents/skills/probe/SKILL.md")
        self.write_builtin_config(root, codex_mode="clean")
        (root / ".agents/skills/probe/SKILL.md").unlink()

        report = self.report(
            self.run_stage(root, "codex-deleted-skill", "--scope", "changes")
        )

        codex = self.codex_attempt(report)
        self.assertEqual(codex["status"], "clean")

    def test_codex_adapter_refuses_codebase_scope(self) -> None:
        root = self.make_repo()
        self.write_builtin_config(root, codex_mode="finding")
        config = root / ".sd-ai-command-pack/review.json"
        value = json.loads(config.read_text(encoding="utf-8"))
        value["providers"][0]["scopes"] = ["worktree", "branch_delta", "codebase"]
        config.write_text(json.dumps(value) + "\n", encoding="utf-8")
        self.run_git(root, "add", ".sd-ai-command-pack/review.json")
        self.run_git(root, "commit", "-m", "offer codebase scope to codex")

        result = self.run_stage(
            root, "codex-codebase", "--scope", "codebase", "--local", "codex"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not support codebase scope", result.stdout)

        # The refusal belongs to reading the configuration, not to expanding
        # the argv of a lane that was already selected: a codex provider
        # offering a scope its adapter can never run is rejected on any run,
        # including one that never asks for that scope.
        other = self.run_stage(
            root, "codex-codebase-declared", "--scope", "changes", "--local", "codex"
        )
        self.assertNotEqual(other.returncode, 0)
        self.assertIn("does not support codebase scope", other.stdout)

    # --- .prism/rules.json handling -------------------------------------

    def write_prism_rules(self, root, payload) -> None:
        """Write .prism/rules.json and commit it.

        A ``str`` payload is written verbatim, which is how the malformed-JSON
        cases are built; anything else is serialized as JSON.
        """
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

    def test_the_shipped_schema_admits_no_key_the_runner_refuses(self) -> None:
        """The schema and the refusal list must describe the same file.

        A key the schema admits and the runner refuses is the worst of both:
        the author's file passes every check available to them and then fails
        at review time, with nothing in between to catch it. Asserting the
        intersection is empty binds the two sides, so neither can be edited
        alone -- which is how they drifted apart in the first place, when
        0.71.48 retired ``severityOverrides`` from the runner and left it
        standing in the schema.

        Read from the shipped schema and from the script's own constant rather
        than from a literal, so the test tracks whatever those files say.
        """
        schema = json.loads(
            (PACK_ROOT / "templates/.prism/rules.schema.json").read_text(
                encoding="utf-8"
            )
        )
        refused = set(self.runner_refused_rules_keys())

        self.assertTrue(refused, "the runner refuses nothing; the test is vacuous")
        admitted = set(schema["properties"])
        self.assertEqual(
            admitted & refused,
            set(),
            "the schema admits a key the runner refuses",
        )
        # additionalProperties is what turns "not listed" into "forbidden".
        # Without it the deletion above would leave the key merely undescribed.
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema.get("required", [])) & refused, set())

    def test_every_refused_key_carries_its_own_receipt_reason(self) -> None:
        """A shared reason string would misdescribe the second key added.

        The reason is published in the receipt and is the only thing telling an
        author what to remove, so it has to name the key that was actually
        found.
        """
        for key, reason in self.runner_refused_rules_keys().items():
            with self.subTest(key):
                self.assertIn(key, reason)
                self.assertNotIn("/", reason)
                self.assertNotIn("\\", reason)

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
                # The receipt is published; it must not carry host paths. Both
                # separators, so the assertion still bites if the suite is ever
                # run on Windows.
                self.assertNotIn("/", record["reason"])
                self.assertNotIn("\\", record["reason"])
                self.assertEqual(record["path"], ".prism/rules.json")

    def test_a_dangling_prism_rules_symlink_is_unreadable_not_absent(self) -> None:
        """A broken link is a broken checkout, and the receipt must say so.

        ``Path.is_file()`` follows symlinks, so a dangling link reads as False
        exactly like a missing file. Reporting `absent` would tell a reader the
        repository ships no rules when it ships a link to nothing.
        """

        root = self.make_repo()
        log = self.write_builtin_config(root)
        rules = root / ".prism/rules.json"
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.symlink_to("nowhere.json")
        self.run_git(root, "add", ".prism/rules.json")
        self.run_git(root, "commit", "-m", "add a dangling prism rules link")

        result = self.run_stage(root, "rules-dangling")
        report = self.report(result)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn("--rules", log.read_text(encoding="utf-8"))
        record = self.prism_rules_record(report)
        self.assertEqual(record["status"], "unreadable")
        self.assertEqual(record["path"], ".prism/rules.json")
        self.assertNotIn("/", record["reason"])
        self.assertNotIn("\\", record["reason"])

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

    def gito_argv(self, log: Path) -> list[str]:
        """The single gito invocation recorded in the fixture log, as a token list.

        Fails rather than returning an empty list when gito never ran: an argv
        assertion that silently passes on no invocations is worse than no test.
        """
        lines = [
            line
            for line in log.read_text(encoding="utf-8").splitlines()
            if line.startswith("gito ")
        ]
        self.assertEqual(len(lines), 1, f"expected one gito invocation, got {lines}")
        return lines[0].split()

    def test_gito_branch_delta_argv_carries_head_and_base_in_order(self) -> None:
        """--what <head> --vs <base>, both values pinned, in that order.

        The order matters as much as the presence: gito reviews ``--vs..--what``,
        so a fix that transposes them reviews ``head..base`` and would still
        satisfy an assertion that only counted arguments or checked membership.
        """
        root = self.make_repo()
        log = self.write_builtin_config(root)
        head = self.git_output(root, "rev-parse", "HEAD")
        base = self.git_output(root, "rev-parse", "main")
        self.assertNotEqual(base, head, "branch_delta needs a base distinct from head")

        self.run_stage(root, "gito-branch-delta", "--scope", "pr", "--local", "gito")

        argv = self.gito_argv(log)
        self.assertIn("--what", argv)
        self.assertEqual(argv[argv.index("--what") + 1], head)
        self.assertEqual(argv[argv.index("--vs") + 1], base)
        self.assertLess(
            argv.index("--what"),
            argv.index("--vs"),
            f"--what must precede --vs, got {argv}",
        )

    def test_gito_worktree_argv_has_no_head(self) -> None:
        """worktree review is of the tree itself, so there is no head ref to send."""
        root = self.make_repo()
        log = self.write_builtin_config(root)
        (root / "src/app.py").write_text("seed\nchanged\ndirty\n", encoding="utf-8")
        head = self.git_output(root, "rev-parse", "HEAD")

        self.run_stage(root, "gito-worktree", "--scope", "changes", "--local", "gito")

        argv = self.gito_argv(log)
        self.assertNotIn("--what", argv)
        self.assertEqual(argv[argv.index("--vs") + 1], head)

    def test_gito_codebase_argv_is_unchanged(self) -> None:
        """The --all path is not what this defect is about and must not move."""
        root = self.make_repo()
        log = self.write_builtin_config(root)

        self.run_stage(root, "gito-codebase", "--scope", "codebase", "--local", "gito")

        argv = self.gito_argv(log)
        self.assertIn("--all", argv)
        self.assertEqual(
            Path(argv[argv.index("--path") + 1]).resolve(), root.resolve()
        )
        self.assertNotIn("--what", argv)
        self.assertNotIn("--vs", argv)

    def detach_head_from(self, root: Path) -> str:
        """Advance the branch one commit and return the now-historical head oid.

        Leaves the working tree clean and bound to the *new* commit, so a run
        asking for the returned oid is asking for a head the tree does not hold —
        the exact situation gito cannot honour.
        """
        historical = self.git_output(root, "rev-parse", "HEAD")
        target = root / "src/app.py"
        target.write_text(
            target.read_text(encoding="utf-8") + "later\n", encoding="utf-8"
        )
        self.run_git(root, "add", "src/app.py")
        self.run_git(root, "commit", "-m", "a commit the requested head predates")
        self.assertNotEqual(self.git_output(root, "rev-parse", "HEAD"), historical)
        return historical

    def test_gito_refuses_a_head_the_working_tree_does_not_hold(self) -> None:
        """gito reads content from the tree, so an unheld head silently misreviews.

        Asserts on the message naming both oids rather than on the exception type:
        the dirty-worktree guard raises the same type, and a type-only assertion
        could not tell a head mismatch from dirtiness.
        """
        root = self.make_repo()
        self.write_builtin_config(root)
        historical = self.detach_head_from(root)
        actual = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_stage(
            root,
            "gito-unheld-head",
            "--scope",
            "pr",
            "--head",
            historical,
            "--local",
            "gito",
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(historical, result.stdout)
        self.assertIn(actual, result.stdout)

    def test_a_symbolic_head_that_resolves_to_the_tree_is_not_refused(self) -> None:
        """The comparison is between two canonical oids, not two spellings.

        ``--head feature`` and ``--head <oid>`` name the same commit; refusing
        the first because it is not literally equal to the resolved head would
        make the guard fire on the common case it is supposed to allow.
        """
        root = self.make_repo()
        log = self.write_builtin_config(root)
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_stage(
            root,
            "gito-symbolic-head",
            "--scope",
            "pr",
            "--head",
            "feature",
            "--local",
            "gito",
        )

        self.assertNotIn("does not hold", result.stdout)
        argv = self.gito_argv(log)
        self.assertEqual(argv[argv.index("--what") + 1], head)

    def test_prism_still_reviews_a_head_the_working_tree_does_not_hold(self) -> None:
        """The refusal is provider-scoped; prism reads content from refs.

        Without this, a later simplification that moves the check into
        resolve_target — refusing for every provider — passes its own tests.
        """
        root = self.make_repo()
        self.write_builtin_config(root)
        historical = self.detach_head_from(root)

        result = self.run_stage(
            root,
            "prism-unheld-head",
            "--scope",
            "pr",
            "--head",
            historical,
            "--local",
            "prism",
        )

        self.assertNotIn("does not hold", result.stdout)
        report = self.report(result)
        self.assertIn(report["status"], {"clean", "findings"})

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

    def bookkeeping_target(self, root: Path) -> dict:
        """The exact target a bookkeeping evidence file has to agree with."""

        planned = self.report(self.run_stage(root, "bookkeeping-target", "--plan-only"))
        return planned["target"]

    def bookkeeping_evidence(
        self, root: Path, name: str, value: object
    ) -> Path:
        path = root.parent / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def assert_evidence_rejected(
        self, root: Path, attempt: str, *arguments: str
    ) -> str:
        """Run a rejected bookkeeping attempt and return its diagnostic.

        Every branch is asserted through the same helper so the exit code and
        the report envelope are re-checked on each one: the point of this work
        was to change the prose, and a message improvement that quietly moved
        an exit code or dropped a report key would break every caller that
        parses the JSON.
        """

        result = self.run_stage(
            root, attempt, "--successor", "bookkeeping", *arguments
        )
        self.assertEqual(result.returncode, 2, result.stdout)
        report = self.report(result)
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["command"], "sd-review-local-stage")
        self.assertEqual(report["status"], "invalid")
        self.assertEqual(report["outcome"], "invalid")
        diagnostic = report["diagnostic"]
        self.assertIsInstance(diagnostic, str)
        # The shared contract sentence: which flag, what shape, and the
        # disambiguation from the similarly named finish-work receipt. Asserted
        # on every branch because the original defect was branch-specific --
        # one message happened to be informative and the rest were not.
        self.assertIn("--bookkeeping-evidence", diagnostic)
        for key in ("schemaVersion", "classification", "base", "head", "contentDigest"):
            self.assertIn(key, diagnostic)
        self.assertIn("bookkeeping-successor", diagnostic)
        self.assertIn("final-bundle", diagnostic)
        return diagnostic

    def test_absent_bookkeeping_evidence_path_names_the_flag(self) -> None:
        """A path that does not exist used to surface as a bare OS error.

        `Path(...).resolve(strict=True)` ran in `main()` under a blanket
        `except (OSError, ReviewInputError)`, so the operator saw
        `[Errno 2] No such file or directory: '<path>'` with no mention of the
        flag that carried the path or of the receipt that was wanted. This
        fails before the fix on the flag-name assertion.
        """

        root = self.make_repo()
        self.write_config(root)
        missing = root.parent / "not-written-yet.json"
        self.assertFalse(missing.exists())

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-absent", "--bookkeeping-evidence", str(missing)
        )

        self.assertIn(str(missing), diagnostic)
        self.assertIn("No such file or directory", diagnostic)
        self.assertNotIn("Errno", diagnostic)

    def test_non_json_bookkeeping_evidence_names_the_flag_and_shape(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        notes = root.parent / "notes.md"
        notes.write_text("# not a receipt\n", encoding="utf-8")

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-not-json", "--bookkeeping-evidence", str(notes)
        )

        self.assertIn(str(notes), diagnostic)
        self.assertIn("Expecting value", diagnostic)

    def test_missing_bookkeeping_evidence_flag_states_the_shape(self) -> None:
        root = self.make_repo()
        self.write_config(root)

        diagnostic = self.assert_evidence_rejected(root, "evidence-omitted")

        self.assertIn("requires --bookkeeping-evidence", diagnostic)

    def test_finish_work_receipt_rejection_names_the_offending_fields(self) -> None:
        """The confusion this task came from: the wrong artifact, by name.

        A `final-bundle --mode completion` receipt is JSON, has
        `"schemaVersion": 1`, and shares the word bookkeeping, so it is the
        artifact an operator reaches for first. The rejection now names which
        keys were missing and which were not recognized, rather than saying
        only that some unspecified field was wrong.
        """

        root = self.make_repo()
        self.write_config(root)
        receipt = self.bookkeeping_evidence(
            root,
            "final-bundle.json",
            {"schemaVersion": 1, "kind": "final-bundle", "status": "valid"},
        )

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-wrong-artifact", "--bookkeeping-evidence", str(receipt)
        )

        self.assertIn("missing base, classification, contentDigest, head", diagnostic)
        self.assertIn("unsupported kind, status", diagnostic)

    def test_bookkeeping_evidence_guidance_names_the_stage_script(self) -> None:
        """The guidance has to survive being forwarded by the controller.

        `--bookkeeping-evidence` is also accepted by
        `sd-ai-command-pack-review.py`, which forwards it here and relays this
        rejection back verbatim. That controller has no `--plan-only`, so a
        message that said "this command's own --plan-only report" sent such a
        caller to a flag the command they invoked rejects. Naming the stage
        script reads correctly from either entry point.
        """

        root = self.make_repo()
        self.write_config(root)

        diagnostic = self.assert_evidence_rejected(root, "evidence-omitted")

        self.assertIn("--plan-only", diagnostic)
        self.assertIn("sd-ai-command-pack-review-local.py --plan-only", diagnostic)
        self.assertNotIn("this command's own", diagnostic)

    def test_bookkeeping_evidence_schema_version_rejection_is_specific(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        target = self.bookkeeping_target(root)
        evidence = self.bookkeeping_evidence(
            root,
            "bad-version.json",
            {
                "schemaVersion": 2,
                "classification": "bookkeeping-successor",
                "base": target["base"],
                "head": target["head"],
                "contentDigest": target["contentDigest"],
            },
        )

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-bad-version", "--bookkeeping-evidence", str(evidence)
        )

        self.assertIn("schemaVersion must be 1", diagnostic)

    def test_bookkeeping_evidence_classification_rejection_is_specific(self) -> None:
        root = self.make_repo()
        self.write_config(root)
        target = self.bookkeeping_target(root)
        evidence = self.bookkeeping_evidence(
            root,
            "bad-classification.json",
            {
                "schemaVersion": 1,
                "classification": "planning-successor",
                "base": target["base"],
                "head": target["head"],
                "contentDigest": target["contentDigest"],
            },
        )

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-bad-class", "--bookkeeping-evidence", str(evidence)
        )

        self.assertIn("classification must be", diagnostic)

    def test_target_mismatch_names_the_field_without_leaking_the_answer(self) -> None:
        """Name which field disagreed; never hand over the value it wanted.

        Reporting the target's own `head` and `contentDigest` would turn the
        rejection into a template for hand-authoring a passing evidence file,
        which is manufacturing the verification the classification exists to
        require. Only the caller-supplied half is echoed back.
        """

        root = self.make_repo()
        self.write_config(root)
        target = self.bookkeeping_target(root)
        forged = "0" * 40
        evidence = self.bookkeeping_evidence(
            root,
            "mismatched.json",
            {
                "schemaVersion": 1,
                "classification": "bookkeeping-successor",
                "base": target["base"],
                "head": forged,
                "contentDigest": "sha256:not-the-digest",
            },
        )

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-mismatch", "--bookkeeping-evidence", str(evidence)
        )

        self.assertIn("does not match the exact target", diagnostic)
        self.assertIn("head", diagnostic)
        self.assertIn("contentDigest", diagnostic)
        self.assertIn(forged, diagnostic)
        self.assertNotIn(target["head"], diagnostic)
        self.assertNotIn(target["contentDigest"], diagnostic)

    def test_oversized_bookkeeping_evidence_is_attributed_to_the_flag(self) -> None:
        """The size guard fires before the file is read, and still names it."""

        root = self.make_repo()
        self.write_config(root)
        oversized = root.parent / "oversized-evidence.json"
        oversized.write_bytes(b"{" + b" " * (65 * 1024))

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-oversized", "--bookkeeping-evidence", str(oversized)
        )

        self.assertIn("exceeds 65536 bytes", diagnostic)
        self.assertIn(str(oversized), diagnostic)

    def test_symlinked_bookkeeping_evidence_is_gated_on_content(self) -> None:
        """A symlink is followed, and the descriptor check is the real gate.

        `_read_json` refuses a symlink outright, but it never sees one here:
        the flag is resolved with `Path(...).resolve(strict=True)`, which
        follows the link before the reader runs. That is unchanged from before
        this change, and it is sound because the path shape is not what
        authorizes anything -- the descriptor has to equal the reviewed
        target's `base`, `head`, and `contentDigest`, so pointing at a file
        through a link buys the caller exactly nothing. Asserted rather than
        assumed, since the two guards look like they contradict.
        """

        root = self.make_repo()
        self.write_config(root)
        real = self.bookkeeping_evidence(
            root,
            "linked-target.json",
            {"schemaVersion": 1, "kind": "final-bundle", "status": "valid"},
        )
        link = root.parent / "evidence-link.json"
        link.symlink_to(real)

        diagnostic = self.assert_evidence_rejected(
            root, "evidence-symlink", "--bookkeeping-evidence", str(link)
        )

        # The link was followed: this is the content rejection, not the
        # regular-file one that a refused symlink would have produced.
        self.assertIn("unsupported or missing fields", diagnostic)
        self.assertNotIn("regular non-symlink file", diagnostic)

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
        the plan. What is checked instead is *exactly* which plan keys the
        ceiling adds, which fails if the value never reaches the plan.

        That set is two keys, not one: ``localAdvisoryRecordVersion`` rides the
        same condition so that adopting the per-finding record moves the
        receipt identity. It is spelled out rather than relaxed to a subset
        check -- the assertion's whole value is that it fails when a key
        nobody intended reaches the plan and changes every digest with it.
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
            set(ceiling_plan) ^ set(strict_plan),
            {"localAdvisorySeverityCeiling", "localAdvisoryRecordVersion"},
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
            # 0.71.51 gave `accepted` an @ payload too, so the old
            # "only miscited accepts a citation" wording became false.
            ("abc=rebutted@src/app.py:3", "only miscited and accepted accept"),
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

    # --- the classification recorded on each finding -------------------------

    def assert_counts_match_records(self, receipt: dict[str, object]) -> None:
        """Recompute the disposition block from ``findings[]`` and compare.

        Reads only ``disposition`` and ``advisory``, never ``severity``. A
        helper that re-applied the ceiling here would be re-implementing
        ``_is_advisory`` in the test suite, which is the duplication the
        recorded field exists to remove -- and it would agree with the runner
        by construction, which is the one thing this must not do.
        """

        counts = {"outstanding": 0, "advisory": 0, "dispositioned": 0, "accepted": 0}
        for finding in receipt["findings"]:
            disposition = finding["disposition"]
            if disposition == "accepted":
                counts["accepted"] += 1
            elif disposition != "outstanding":
                counts["dispositioned"] += 1
            elif finding.get("advisory"):
                counts["advisory"] += 1
            else:
                counts["outstanding"] += 1
        recorded = receipt["disposition"]
        for key, value in counts.items():
            self.assertEqual(recorded[key], value, f"{key}: {receipt['findings']}")

    def test_a_released_finding_says_so_on_its_own_record(self) -> None:
        """T14: partition the findings reading nothing but their own records."""

        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"), ceiling="medium")

        receipt = self.report(
            self.run_stage(root, "recorded", "--local", "prism")
        )["receipt"]

        outstanding = [
            item for item in receipt["findings"] if item["disposition"] == "outstanding"
        ]
        released = [item["summary"] for item in outstanding if item["advisory"]]
        blocking = [item["summary"] for item in outstanding if not item["advisory"]]

        self.assertEqual(released, ["mixed advisory observation"])
        self.assertEqual(blocking, ["mixed real defect"])
        self.assert_counts_match_records(receipt)

    def test_a_rebutted_finding_does_not_keep_its_advisory_flag(self) -> None:
        """T15: the record follows the disposition, or this task's own defect
        comes back one disposition later.

        The second run reuses the stored receipt, so it is ``_redispose_receipt``
        that recomputes -- the path where a stale ``advisory: true`` would
        survive. It rebuts the *released* finding deliberately: rebutting the
        blocking one passes even with the removal unimplemented.
        """

        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"), ceiling="medium")
        first = self.report(
            self.run_stage(root, "cleared", "--local", "prism")
        )["receipt"]
        released = next(item for item in first["findings"] if item["advisory"])

        receipt = self.report(
            self.run_stage(
                root,
                "cleared",
                "--local",
                "prism",
                "--local-disposition",
                f"{released['id']}=rebutted",
            )
        )["receipt"]
        stored = next(
            item for item in receipt["findings"] if item["id"] == released["id"]
        )

        self.assertEqual(stored["disposition"], "rebutted")
        self.assertNotIn("advisory", stored)
        self.assert_counts_match_records(receipt)

    def test_no_ceiling_leaves_every_finding_record_unchanged(self) -> None:
        """T16: a strict repository's receipt gains nothing at all."""

        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"))

        receipt = self.report(
            self.run_stage(root, "strict-records", "--local", "prism")
        )["receipt"]

        self.assertNotIn("localAdvisoryRecordVersion", receipt["plan"])
        for finding in receipt["findings"]:
            self.assertNotIn("advisory", finding)
        self.assertEqual(receipt["disposition"]["outstanding"], 2)
        self.assertEqual(receipt["disposition"]["advisory"], 0)
        self.assert_counts_match_records(receipt)

    def test_adopting_the_record_changes_the_receipt_identity(self) -> None:
        """T17: recording the classification is a policy change, so it moves
        the digest that names the receipt.

        Asserting only that the marker is on the plan would leave the point
        unproven: what requirement 3 asks is that a repository already running
        with a ceiling cannot serve a cached pre-change receipt, and that is a
        statement about ``policyDigest``, which ``_receipt_identity`` digests.
        """

        module = self.load_module_from_path(self.SCRIPT, "sd_review_local_identity")
        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"), ceiling="medium")

        plan = self.report(
            self.run_stage(root, "identity", "--local", "prism")
        )["receipt"]["plan"]

        self.assertEqual(plan["localAdvisoryRecordVersion"], 1)

        legacy = {key: value for key, value in plan.items() if key != "policyDigest"}
        del legacy["localAdvisoryRecordVersion"]
        legacy["policyDigest"] = module._digest(legacy)
        target = {"scope": "branch_delta"}

        self.assertNotEqual(
            module._receipt_identity(target, plan),
            module._receipt_identity(target, legacy),
        )

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



    # --- accepted: the ground for a finding that is true and stands ---------

    def test_accepted_releases_a_high_finding_that_otherwise_blocks(self) -> None:
        """T14: one test, both halves -- the ground works and the gate is real.

        Paired deliberately. A release asserted on its own cannot tell a
        working disposition from a gate that never blocked.
        """

        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))

        blocked = self.report(self.run_stage(root, "high-accept", "--local", "prism"))
        self.assertEqual(blocked["receipt"]["remoteGate"]["state"], "blocked")
        self.assertEqual(
            blocked["receipt"]["remoteGate"]["reason"], "actionable-local-findings"
        )
        identifier = blocked["receipt"]["findings"][0]["id"]
        # A high finding is never advisory -- _is_advisory refuses rank >= high
        # regardless of ceiling -- so nothing but the disposition can open this.
        self.assertEqual(blocked["receipt"]["findings"][0]["severity"], "high")

        cleared = self.report(
            self.run_stage(
                root,
                "high-accept",
                "--local",
                "prism",
                "--local-disposition",
                f"{identifier}=accepted@deliberate: the grant is narrowed on purpose",
            )
        )["receipt"]

        self.assertEqual(cleared["remoteGate"]["state"], "eligible")
        self.assertEqual(cleared["disposition"]["outstanding"], 0)
        self.assertEqual(cleared["disposition"]["accepted"], 1)

    def test_accepted_is_not_an_alias_of_rebutted_or_miscited(self) -> None:
        """T15: fails if `accepted` were wired as either existing ground.

        The whole point of the ground is that a reader can tell a waived
        finding from a refuted one. Every assertion here is one way that
        distinction could be lost.
        """

        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))
        blocked = self.report(self.run_stage(root, "accept-alias", "--local", "prism"))
        identifier = blocked["receipt"]["findings"][0]["id"]
        reason = "trivial impact, understood, not worth a change"

        receipt = self.report(
            self.run_stage(
                root,
                "accept-alias",
                "--local",
                "prism",
                "--local-disposition",
                f"{identifier}=accepted@{reason}",
            )
        )["receipt"]
        finding = receipt["findings"][0]

        self.assertEqual(finding["disposition"], "accepted")
        self.assertEqual(finding["dispositionReason"], reason)
        # Not miscited: an acceptance concedes the citation is correct, so
        # borrowing the citation field would erase that distinction.
        self.assertNotIn("dispositionCitation", finding)
        # Not rebutted: the counts are separate integers precisely so a reader
        # cannot mistake a waiver for a refutation.
        self.assertEqual(receipt["disposition"]["accepted"], 1)
        self.assertEqual(receipt["disposition"]["dispositioned"], 0)
        # The per-finding ground survives here too, which is what lets a reader
        # attribute the waiver without walking the findings array.
        self.assertEqual(
            receipt["disposition"]["localDispositions"], {identifier: "accepted"}
        )
        # The provider's own claim is untouched. An acceptance never edits the
        # finding it accepts.
        self.assertEqual(finding["path"], "src/app.py")
        self.assertEqual(finding["line"], 2)

    def test_accepted_outranks_every_other_eligible_claim(self) -> None:
        """T16: the weakest release ground is the one a reader must be told.

        A rebuttal says the finding was not real; an advisory release says
        policy did not care; an acceptance says it is real, it stands, and
        someone signed for it. If the ladder reported the better news, a reader
        consulting `remoteGate.reason` alone would never learn a waiver
        happened -- which is the silent acceptance this ground exists to avoid.
        """

        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"), ceiling="medium")
        blocked = self.report(self.run_stage(root, "accept-rank", "--local", "prism"))
        high = next(
            item
            for item in blocked["receipt"]["findings"]
            if item["severity"] == "high"
        )

        receipt = self.report(
            self.run_stage(
                root,
                "accept-rank",
                "--local",
                "prism",
                "--local-disposition",
                f"{high['id']}=accepted@known and accepted",
            )
        )["receipt"]

        # An advisory finding is present and released, and it must not be the
        # claim the gate reports.
        self.assertEqual(receipt["disposition"]["advisory"], 1)
        self.assertEqual(receipt["disposition"]["accepted"], 1)
        self.assertEqual(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(receipt["remoteGate"]["state"], "eligible")
        self.assertEqual(
            receipt["remoteGate"]["reason"], "local-findings-accepted"
        )

    def test_accepted_outranks_a_dispositioned_sibling(self) -> None:
        """T17: an acceptance is not masked by a rebuttal in the same receipt.

        This is the shape the motivating replay actually has -- four findings
        dispositioned and three accepted -- so the masking case is the real one,
        not a contrived one.
        """

        root = self.make_repo()
        self.write_config(root, modes=("mixed-severity", "clean"))
        blocked = self.report(self.run_stage(root, "accept-mask", "--local", "prism"))
        findings = blocked["receipt"]["findings"]
        high = next(item for item in findings if item["severity"] == "high")
        other = next(item for item in findings if item["id"] != high["id"])

        receipt = self.report(
            self.run_stage(
                root,
                "accept-mask",
                "--local",
                "prism",
                "--local-disposition",
                f"{high['id']}=accepted@real, and it stands",
                "--local-disposition",
                f"{other['id']}=rebutted",
            )
        )["receipt"]

        self.assertEqual(receipt["disposition"]["accepted"], 1)
        self.assertEqual(receipt["disposition"]["dispositioned"], 1)
        self.assertEqual(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(
            receipt["remoteGate"]["reason"], "local-findings-accepted"
        )

    def test_family_evidence_still_rejects_an_accepted_disposition(self) -> None:
        """T19: the family-evidence grammar stays closed to the new ground.

        `accepted` is a LOCAL_DISPOSITION_VALUES member and deliberately not a
        FINDING_DISPOSITIONS one. That set has exactly one consumer --
        `_parse_family_finding` -- and a waiver has no defined meaning on that
        path: `--family-evidence` drives the family gate, and an accepted
        finding carrying `actionable: true` would validate and reach it with
        nothing deciding what it means.

        Pinned rather than left implicit, because the two sets look like they
        ought to agree and the obvious tidying edit is to add the member to
        both.
        """

        root = self.make_repo()
        self.write_config(root, modes=("clean", "clean"))
        finding = self.family_finding(root, "remote-one", 1, "boundary-validation")
        finding["disposition"] = "accepted"
        evidence = self.write_family_evidence(
            root, current_round=1, findings=[finding]
        )

        result = self.run_stage(
            root,
            "family-accepted",
            "--family-evidence",
            str(evidence),
            "--plan-only",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("family finding disposition is unsupported", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_accepted_grammar_requires_a_bounded_reason(self) -> None:
        """T18: the bound is enforced, not documented.

        `accepted` is the one ground whose claim cannot be checked against the
        checkout -- the finding is true by admission -- so the required reason
        is the whole of what makes it attributable. An optional reason is not a
        bound, and a reason that arrives mangled is worse than one refused.
        """

        root = self.make_repo()
        self.write_config(root, modes=("finding", "clean"))
        self.run_stage(root, "accept-grammar", "--local", "prism")

        cases = (
            ("abc=accepted", "accepted requires a reason"),
            ("abc=accepted@", "accepted requires a reason"),
            ("abc=accepted@" + "x" * 501, "reason is unsafe or unbounded"),
            ("abc=accepted@why\tnot", "reason is unsafe or unbounded"),
            ("abc=accepted@why\nnot", "reason is unsafe or unbounded"),
            # rpartition splits on the LAST "=", so a reason containing one
            # moves the split point and the id silently absorbs
            # "...=accepted@<prefix>". Without its own diagnostic this surfaces
            # as an unrelated complaint about a mangled id, which is what a
            # plain typo would produce.
            ("abc=accepted@a=b", "an accepted reason cannot contain '='"),
        )
        for index, (token, expected) in enumerate(cases):
            with self.subTest(token=token):
                result = self.run_stage(
                    root,
                    f"accept-bad-{index}",
                    "--local",
                    "prism",
                    "--local-disposition",
                    token,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout)
                # A bounded input error, not merely a non-zero exit: a
                # traceback is a different failure wearing the same code.
                self.assertNotIn("Traceback", result.stdout)


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



    # ------------------------------------------------------------------
    # A dead provider reaches the gate
    # (08-25-aggregate-outcome-masks-provider-failure)
    #
    # `outcome` answers "what did the providers find". It is not a verdict.
    # `_aggregate_outcome` ranks `findings` ahead of `failed`, so a run where one
    # provider found something and another died reported `outcome: "findings"`,
    # the terminal-failure branch never ran, and the gate said plain `eligible`
    # about a receipt that names a dead lane in `confidence.limitations`.
    # ------------------------------------------------------------------

    def test_a_failed_provider_limits_the_gate_even_when_another_found_things(
        self,
    ) -> None:
        """The case the task exists for: findings AND a dead lane."""
        root = self.make_repo()
        self.write_config(root, modes=("severity-low", "fail"), ceiling="medium")

        receipt = self.report(self.run_stage(root, "degraded-findings"))["receipt"]

        self.assertEqual(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(receipt["remoteGate"]["state"], "eligible-with-limitations")
        self.assertEqual(receipt["remoteGate"]["reason"], "local-review-limited")
        self.assertTrue(
            any("gito" in entry for entry in receipt["confidence"]["limitations"]),
            receipt["confidence"]["limitations"],
        )

    def test_aggregate_outcome_still_reports_findings_over_failure(self) -> None:
        """Precedence asserted, not read off the tuple.

        Reordering the tuple was the rejected fix: it makes `failed` dominate
        `findings`, so a run that found real problems reports `failed` and the
        findings vanish from the summary. This fails if someone later "fixes"
        the defect that way.
        """
        root = self.make_repo()
        self.write_config(root, modes=("severity-low", "fail"), ceiling="medium")

        receipt = self.report(self.run_stage(root, "outcome-precedence"))["receipt"]

        self.assertEqual(receipt["outcome"], "findings")

    def test_a_findings_run_with_no_failure_is_unchanged(self) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("severity-low", "clean"), ceiling="medium")

        receipt = self.report(self.run_stage(root, "no-failure"))["receipt"]

        self.assertEqual(receipt["remoteGate"]["state"], "eligible")
        self.assertEqual(receipt["remoteGate"]["reason"], "local-advisory-released")
        self.assertEqual(receipt["confidence"]["limitations"], [])

    def test_a_required_policy_blocks_when_a_provider_dies_alongside_findings(
        self,
    ) -> None:
        root = self.make_repo()
        self.write_config(root, modes=("severity-low", "fail"), ceiling="medium")

        receipt = self.report(
            self.run_stage(root, "degraded-required", "--local-policy", "required")
        )["receipt"]

        self.assertEqual(receipt["remoteGate"]["state"], "blocked")
        self.assertEqual(receipt["remoteGate"]["reason"], "required-local-review-failed")

    def test_outstanding_findings_outrank_a_degraded_lane(self) -> None:
        """Blocked is blocked; the stronger claim wins.

        A degraded run that still has outstanding findings reports
        `actionable-local-findings`, not `local-review-limited`. The limitation
        is still in the receipt either way.
        """
        root = self.make_repo()
        self.write_config(root, modes=("finding", "fail"))

        receipt = self.report(self.run_stage(root, "degraded-outstanding"))["receipt"]

        self.assertGreater(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(receipt["remoteGate"]["state"], "blocked")
        self.assertEqual(receipt["remoteGate"]["reason"], "actionable-local-findings")
        self.assertNotEqual(receipt["confidence"]["limitations"], [])

    def test_regating_a_stored_degraded_receipt_keeps_the_limitation(self) -> None:
        """The second call site, which re-gates a receipt rather than building one.

        `attempts` and the local `limitations` list are not in scope there; the
        persisted `confidence.limitations` is. The two sites are easy to fix
        asymmetrically and nothing else would catch it.
        """
        root = self.make_repo()
        self.write_config(root, modes=("finding", "fail"))

        blocked = self.report(self.run_stage(root, "regate"))["receipt"]
        self.assertEqual(blocked["remoteGate"]["state"], "blocked")
        identifier = blocked["findings"][0]["id"]

        receipt = self.report(
            self.run_stage(
                root, "regate", "--local-disposition", f"{identifier}=rebutted"
            )
        )["receipt"]

        self.assertEqual(receipt["disposition"]["outstanding"], 0)
        self.assertEqual(receipt["remoteGate"]["state"], "eligible-with-limitations")
        self.assertEqual(receipt["remoteGate"]["reason"], "local-review-limited")


if __name__ == "__main__":
    unittest.main()
