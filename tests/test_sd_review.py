"""Fixtures for bin/sd-review: policy, routing, the runner seam, and disposition.

Every provider here is a fake runner. The point of the seam is that no test in
this file starts a real codex, prism, gito or kimi process, and none of them
reaches a network: a test that needed one would be a test proving the seam is
not a seam.
"""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Mapping, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD_REVIEW = REPO_ROOT / "bin" / "sd-review"
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))


def load_module() -> Any:
    """Import `bin/sd-review` as a module.

    It ships without a `.py` suffix, so the loader has to be named: the default
    finder recognises files by extension and returns no spec for this one.
    """

    loader = importlib.machinery.SourceFileLoader("sd_review_under_test", str(SD_REVIEW))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


sd_review = load_module()


class FakeRunner:
    """A runner that answers from a script and records what it was handed.

    It records the environment it received, not the environment the caller
    intended to build: the credential-scrub assertions in
    `test_sd_review_codex.py` read `calls[i]["env"]` for exactly that reason.
    """

    def __init__(self, answers: Mapping[str, Any] | None = None, default: Any = None) -> None:
        self.answers = dict(answers or {})
        self.default = default or sd_review.Completed(0, '{"findings": []}', "")
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        cwd: pathlib.Path,
        timeout: int,
    ) -> Any:
        self.calls.append(
            {"argv": list(argv), "env": dict(env), "cwd": pathlib.Path(cwd), "timeout": timeout}
        )
        program = pathlib.Path(argv[0]).name
        if program.startswith("python") or argv[-1] == "--json" and "sd-check" in " ".join(argv):
            program = "sd-check"
        answer = self.answers.get(program, self.default)
        if callable(answer):
            return answer(argv, env, cwd, timeout)
        return answer


def namespace(**overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "scope": "worktree",
        "challenge": False,
        "explain": False,
        "dry_run": False,
        "json": False,
        "draft": False,
        "timeout": 60,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ReviewFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()

    def make_repo(self, name: str = "repo") -> pathlib.Path:
        root = self.tmp / name
        root.mkdir(parents=True)
        for args in (
            ["init", "--quiet", "--initial-branch", "main"],
            ["config", "user.email", "fixture@example.invalid"],
            ["config", "user.name", "Fixture"],
        ):
            subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)
        (root / "README.md").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "seed"], cwd=str(root), check=True, capture_output=True
        )
        return root

    def chatgpt_home(self, key: Any = None, mode: str = "chatgpt") -> pathlib.Path:
        home = self.tmp / f"codex-home-{len(list(self.tmp.iterdir()))}"
        home.mkdir(parents=True)
        payload: dict[str, Any] = {"auth_mode": mode, "OPENAI_API_KEY": key}
        (home / "auth.json").write_text(json.dumps(payload), encoding="utf-8")
        return home


class PolicyTests(ReviewFixture):
    def test_absent_file_uses_the_documented_default(self) -> None:
        root = self.make_repo()
        policy, source = sd_review.load_policy(root)
        self.assertEqual(source, "built-in default")
        self.assertEqual(policy, sd_review.DEFAULT_POLICY)

    def test_present_file_is_merged_over_the_default(self) -> None:
        root = self.make_repo()
        (root / ".github").mkdir()
        (root / ".github" / "sd-review.json").write_text(
            json.dumps({"severity_floor": "high"}), encoding="utf-8"
        )
        policy, source = sd_review.load_policy(root)
        self.assertEqual(policy["severity_floor"], "high")
        self.assertEqual(policy["large_change_lines"], 800)
        self.assertTrue(source.endswith("sd-review.json"))

    def test_this_repository_ships_a_policy_that_validates(self) -> None:
        policy, source = sd_review.load_policy(REPO_ROOT)
        self.assertTrue(source.endswith(".github/sd-review.json"), source)
        self.assertIn("authors", policy)

    def test_shipped_schema_covers_every_policy_key(self) -> None:
        schema = json.loads((REPO_ROOT / ".github" / "sd-review.schema.json").read_text())
        self.assertEqual(set(schema["properties"]), set(sd_review.POLICY_KEYS))

    def assert_rejects(self, payload: Any, fragment: str) -> None:
        self._rejections = getattr(self, "_rejections", 0) + 1
        root = self.make_repo(f"reject-{self._rejections}")
        (root / ".github").mkdir()
        (root / ".github" / "sd-review.json").write_text(
            payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
        )
        with self.assertRaises(sd_review.PolicyError) as caught:
            sd_review.load_policy(root)
        self.assertIn(fragment, str(caught.exception))

    def test_malformed_policies_name_what_is_wrong(self) -> None:
        self.assert_rejects("{not json", "not valid JSON")
        self.assert_rejects([], "must be a JSON object")
        self.assert_rejects({"nonsense": 1}, "unknown key(s) nonsense")
        self.assert_rejects({"tiers": {"nope": []}}, "tiers.nope is not in tier_order")
        self.assert_rejects({"tiers": {"cheap": ["nosuch"]}}, "unknown backend 'nosuch'")
        self.assert_rejects({"default_tier": "gold"}, "default_tier must be one of")
        self.assert_rejects({"categories": [{"paths": ["a"]}]}, "name must be a non-empty string")
        self.assert_rejects({"categories": [{"name": "x", "paths": []}]}, "must name at least one glob")
        self.assert_rejects({"large_change_lines": -1}, "non-negative integer")
        self.assert_rejects({"large_change_lines": True}, "non-negative integer")
        self.assert_rejects({"severity_floor": "urgent"}, "severity_floor must be one of")
        self.assert_rejects({"authors": [3]}, "authors[0] must be a string")
        self.assert_rejects({"tier_order": ["a", "a"]}, "must not repeat a tier")
        self.assert_rejects({"challenge_providers": ["ghost"]}, "names unknown backend 'ghost'")

    def test_a_broken_policy_never_falls_back_to_the_default(self) -> None:
        root = self.make_repo()
        (root / ".github").mkdir()
        (root / ".github" / "sd-review.json").write_text("{", encoding="utf-8")
        with self.assertRaises(sd_review.PolicyError):
            sd_review.load_policy(root)


class BackendTableTests(unittest.TestCase):
    def test_probe_gated_backends_are_declared_disabled_with_a_reason(self) -> None:
        for name in ("antigravity", "exo", "baseten"):
            row = sd_review.BACKENDS_BY_NAME[name]
            self.assertFalse(row.enabled, name)
            self.assertEqual(row.strategy, "none", name)
            self.assertTrue(row.disabled_reason.strip(), f"{name} is disabled without a reason")

    def test_github_backends_are_declared_but_never_local(self) -> None:
        for name in ("copilot", "greptile"):
            row = sd_review.BACKENDS_BY_NAME[name]
            self.assertEqual(row.lane, "github", name)
            self.assertFalse(row.enabled, name)

    def test_codex_heads_every_tier_that_reviews_anything(self) -> None:
        for tier, chain in sd_review.DEFAULT_POLICY["tiers"].items():
            if chain:
                self.assertEqual(chain[0], "codex", tier)

    def test_a_disabled_backend_reports_its_reason_instead_of_running(self) -> None:
        runner = FakeRunner()
        outcome = sd_review.run_backend(
            sd_review.BACKENDS_BY_NAME["baseten"],
            pathlib.Path("/nonexistent"),
            sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""),
            "prompt",
            runner,
            {},
            60,
        )
        self.assertEqual(outcome.status, sd_review.DISABLED)
        self.assertIn("gap gate", outcome.detail)
        self.assertEqual(runner.calls, [])


class SubjectTests(ReviewFixture):
    def test_worktree_scope_sees_modified_and_untracked_files(self) -> None:
        root = self.make_repo()
        (root / "README.md").write_text("seed\nchanged\n", encoding="utf-8")
        (root / "new.py").write_text("x = 1\n", encoding="utf-8")
        subject = sd_review.resolve_subject(root, "worktree")
        self.assertEqual(subject.base, "HEAD")
        self.assertEqual(subject.paths, ("README.md", "new.py"))
        self.assertGreater(subject.lines, 0)

    def test_branch_scope_is_the_committed_delta_from_the_merge_base(self) -> None:
        root = self.make_repo()
        subprocess.run(["git", "checkout", "--quiet", "-b", "topic"], cwd=str(root), check=True)
        (root / "feature.py").write_text("y = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "feature"], cwd=str(root), check=True, capture_output=True
        )
        subject = sd_review.resolve_subject(root, "branch")
        self.assertEqual(subject.paths, ("feature.py",))
        self.assertNotEqual(subject.base, subject.head)

    def test_worktree_scope_ignores_committed_history(self) -> None:
        root = self.make_repo()
        subprocess.run(["git", "checkout", "--quiet", "-b", "topic"], cwd=str(root), check=True)
        (root / "committed.py").write_text("y = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "c"], cwd=str(root), check=True, capture_output=True
        )
        self.assertEqual(sd_review.resolve_subject(root, "worktree").paths, ())

    def test_planning_scope_reads_the_active_work_item(self) -> None:
        root = self.make_repo()
        item = root / "docs" / "work" / "2026-01-01-thing"
        item.mkdir(parents=True)
        (item / "prd.md").write_text(
            "---\nstatus: in_progress\nbranch: topic\n---\n\n- [ ] one\n", encoding="utf-8"
        )
        (item / "design.md").write_text("design\n", encoding="utf-8")
        subject = sd_review.resolve_subject(root, "planning")
        self.assertEqual(
            subject.paths,
            ("docs/work/2026-01-01-thing/design.md", "docs/work/2026-01-01-thing/prd.md"),
        )

    def test_planning_scope_without_an_active_item_is_a_usage_error(self) -> None:
        root = self.make_repo()
        with self.assertRaises(sd_review.UsageError):
            sd_review.resolve_subject(root, "planning")


class DispositionTests(unittest.TestCase):
    def test_the_floor_decides_blocking_from_advisory(self) -> None:
        findings = [
            {"severity": "high", "summary": "a"},
            {"severity": "medium", "summary": "b"},
            {"severity": "low", "summary": "c"},
            {"severity": "unspecified", "summary": "d"},
        ]
        disposed = sd_review.dispose(findings, "medium")
        self.assertEqual(
            [record["disposition"] for record in disposed],
            ["blocking", "blocking", "advisory", "advisory"],
        )
        raised = sd_review.dispose(findings, "high")
        self.assertEqual([record["disposition"] for record in raised][:2], ["blocking", "advisory"])

    def test_unspecified_never_blocks_even_at_the_lowest_floor(self) -> None:
        disposed = sd_review.dispose([{"severity": "unspecified", "summary": "d"}], "unspecified")
        self.assertEqual(disposed[0]["disposition"], "advisory")


class ParseTests(unittest.TestCase):
    def test_the_codex_shape_and_the_prism_shape_both_normalise(self) -> None:
        flat = sd_review.parse_findings(
            json.dumps(
                {"findings": [{"path": "a.py", "line": 3, "severity": "high", "summary": "s", "family": "f"}]}
            )
        )
        assert flat is not None
        self.assertEqual(flat[0]["path"], "a.py")
        nested = sd_review.parse_findings(
            json.dumps(
                {
                    "findings": [
                        {
                            "locations": [{"path": "b.py", "lines": {"start": 9}}],
                            "severity": "low",
                            "title": "t",
                            "category": "testing",
                        }
                    ]
                }
            )
        )
        assert nested is not None
        self.assertEqual(nested[0], {"path": "b.py", "line": 9, "severity": "low", "summary": "t", "family": "testing"})

    def test_non_json_and_wrong_shapes_are_not_findings(self) -> None:
        self.assertIsNone(sd_review.parse_findings("boom"))
        self.assertIsNone(sd_review.parse_findings(""))
        self.assertIsNone(sd_review.parse_findings(json.dumps({"issues": []})))

    def test_a_finding_missing_its_path_is_dropped_not_invented(self) -> None:
        parsed = sd_review.parse_findings(json.dumps({"findings": [{"summary": "s"}]}))
        self.assertEqual(parsed, [])

    def test_findings_are_capped(self) -> None:
        many = [
            {"path": "a", "line": None, "severity": "low", "summary": str(index), "family": "f"}
            for index in range(sd_review.MAX_FINDINGS + 10)
        ]
        parsed = sd_review.parse_findings(json.dumps({"findings": many}))
        assert parsed is not None
        self.assertEqual(len(parsed), sd_review.MAX_FINDINGS)


class ClassifyTests(unittest.TestCase):
    def test_rate_limited_is_not_unavailable(self) -> None:
        limited = sd_review.Completed(1, "", "You have hit your usage limit. Try again at 3pm.")
        self.assertEqual(sd_review.classify_failure(limited), sd_review.RATE_LIMITED)
        broken = sd_review.Completed(1, "", "panic: bad flag")
        self.assertEqual(sd_review.classify_failure(broken), sd_review.UNAVAILABLE)

    def test_a_process_that_never_launched_is_unavailable(self) -> None:
        missing = sd_review.Completed(127, "", "codex: not found on PATH", launched=False)
        self.assertEqual(sd_review.classify_failure(missing), sd_review.UNAVAILABLE)

    def test_the_word_rate_limit_in_findings_text_still_reads_as_a_quota_stop(self) -> None:
        # Deliberate: the classifier only runs on a FAILED invocation, so a
        # successful run whose findings discuss rate limits never reaches it.
        ok = sd_review.Completed(0, '{"findings": [{"path": "a", "line": 1, "severity": "low", "summary": "rate limit handling", "family": "x"}]}', "")
        self.assertIsNotNone(sd_review.parse_findings(ok.stdout))


class PipelineTests(ReviewFixture):
    def prepare(self, root: pathlib.Path) -> None:
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")

    def run_review(
        self,
        root: pathlib.Path,
        runner: FakeRunner,
        env: Mapping[str, str] | None = None,
        **overrides: Any,
    ) -> dict[str, Any]:
        return sd_review.review(
            root,
            namespace(**overrides),
            runner,
            dict(env or {}),
            self.chatgpt_home(),
        )

    def test_a_clean_codex_run_is_clean_and_posts_nothing(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", ""), "codex": sd_review.Completed(0, '{"findings": []}', "")})
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "clean")
        self.assertFalse(result["posted"])
        self.assertEqual(result["findings"], [])

    def test_a_failing_gate_stops_before_any_provider(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner({"sd-check": sd_review.Completed(1, "{}", "lint failed")})
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "gate_failed")
        self.assertEqual([call["argv"][0] for call in runner.calls[1:]], [])

    def test_a_blocking_finding_blocks(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        payload = json.dumps(
            {"findings": [{"path": "src.py", "line": 1, "severity": "high", "summary": "bad", "family": "correctness"}]}
        )
        runner = FakeRunner(
            {"sd-check": sd_review.Completed(0, "{}", ""), "codex": sd_review.Completed(0, payload, "")}
        )
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "blocking")
        self.assertEqual(result["findings"][0]["disposition"], "blocking")
        self.assertEqual(result["findings"][0]["backend"], "codex")

    def test_a_rate_limited_provider_stops_the_chain_and_names_the_rest(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner(
            {
                "sd-check": sd_review.Completed(0, "{}", ""),
                "codex": sd_review.Completed(1, "", "usage limit reached"),
                "prism": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "rate_limited")
        statuses = {row["backend"]: row["status"] for row in result["outcomes"]}
        self.assertEqual(statuses["codex"], sd_review.RATE_LIMITED)
        self.assertEqual(statuses["prism"], sd_review.NOT_RUN)
        self.assertEqual(sorted(result["remaining"]), ["codex", "prism"])
        self.assertNotIn("prism", [pathlib.Path(call["argv"][0]).name for call in runner.calls])

    def test_an_unavailable_provider_lets_the_chain_continue(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner(
            {
                "sd-check": sd_review.Completed(0, "{}", ""),
                "codex": sd_review.Completed(127, "", "codex: not found on PATH", False),
                "prism": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        result = self.run_review(root, runner)
        statuses = {row["backend"]: row["status"] for row in result["outcomes"]}
        self.assertEqual(statuses["codex"], sd_review.UNAVAILABLE)
        self.assertEqual(statuses["prism"], sd_review.CLEAN)
        self.assertEqual(result["status"], "clean")

    def test_every_provider_unavailable_is_not_a_clean_review(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner(
            {"sd-check": sd_review.Completed(0, "{}", "")},
            default=sd_review.Completed(127, "", "not found", False),
        )
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(sd_review.STATUS_EXIT[result["status"]], sd_review.EXIT_GATE)

    def test_rate_limited_and_unavailable_get_different_exit_codes(self) -> None:
        self.assertNotEqual(
            sd_review.STATUS_EXIT["rate_limited"], sd_review.STATUS_EXIT["unavailable"]
        )
        self.assertEqual(sd_review.STATUS_EXIT["rate_limited"], sd_review.EXIT_RATE_LIMITED)

    def test_explain_runs_nothing(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner()
        result = self.run_review(root, runner, explain=True)
        self.assertEqual(result["status"], "explained")
        self.assertEqual(runner.calls, [])
        self.assertTrue(result["route"]["reason"])

    def test_dry_run_prints_argv_and_runs_nothing(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner()
        result = self.run_review(root, runner, dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(runner.calls, [])
        codex = [row for row in result["planned_invocations"] if row["backend"] == "codex"]
        self.assertTrue(codex[0]["would_run"])
        self.assertEqual(codex[0]["argv"][:2], ["codex", "exec"])

    def test_challenge_adds_a_stance_without_removing_the_chain(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner()
        plain = self.run_review(root, runner, dry_run=True)
        challenged = self.run_review(root, runner, dry_run=True, challenge=True)
        self.assertEqual(set(plain["providers"]) <= set(challenged["providers"]), True)
        prompt = " ".join(
            row["argv"][-1] for row in challenged["planned_invocations"] if row["would_run"]
        )
        self.assertIn("Argue against the approach itself", prompt)

    def test_the_local_block_reaches_the_prompt(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        local = root / "CLAUDE.local.md"
        local.write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\n"
            "check: make check\n"
            "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n",
            encoding="utf-8",
        )
        result = self.run_review(root, FakeRunner(), dry_run=True)
        self.assertTrue(result["local_block_prepended"])
        prompt = [row for row in result["planned_invocations"] if row["would_run"]][0]["argv"][-1]
        self.assertIn("check: make check", prompt)
        self.assertTrue(prompt.startswith("Repository-local conventions"))

    def test_the_prompt_names_the_endpoints_the_scope_resolved(self) -> None:
        root = self.make_repo()
        subprocess.run(["git", "checkout", "--quiet", "-b", "topic"], cwd=str(root), check=True)
        (root / "feature.py").write_text("y = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "f"], cwd=str(root), check=True, capture_output=True
        )
        result = self.run_review(root, FakeRunner(), dry_run=True, scope="branch")
        prompt = [row for row in result["planned_invocations"] if row["would_run"]][0]["argv"][-1]
        self.assertIn(f"{result['subject']['base']}..{result['subject']['head']}", prompt)

    def test_a_docs_only_change_routes_to_skip_and_asks_nobody(self) -> None:
        root = self.make_repo()
        (root / "docs").mkdir()
        (root / "docs" / "note.md").write_text("hello\n", encoding="utf-8")
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = self.run_review(root, runner)
        self.assertEqual(result["route"]["tier"], "skip")
        self.assertEqual(result["providers"], [])
        self.assertEqual(result["status"], "skipped")


class CliTests(ReviewFixture):
    def run_cli(self, args: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SD_REVIEW), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_explain_against_this_repository_exits_zero(self) -> None:
        finished = self.run_cli(["--explain"], REPO_ROOT)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("route       tier", finished.stdout)
        self.assertIn("explain only, nothing ran", finished.stdout)

    def test_explain_json_is_one_object(self) -> None:
        finished = self.run_cli(["--explain", "--json"], REPO_ROOT)
        payload = json.loads(finished.stdout)
        self.assertFalse(payload["posted"])
        self.assertEqual(payload["status"], "explained")

    def test_outside_a_repository_is_a_usage_error(self) -> None:
        finished = self.run_cli(["--explain"], self.tmp)
        self.assertEqual(finished.returncode, sd_review.EXIT_USAGE)
        self.assertIn("not inside a git repository", finished.stderr)

    def test_a_bad_timeout_is_a_usage_error(self) -> None:
        finished = self.run_cli(["--explain", "--timeout", "0"], REPO_ROOT)
        self.assertEqual(finished.returncode, sd_review.EXIT_USAGE)

    def test_a_malformed_policy_exits_two_without_a_traceback(self) -> None:
        root = self.make_repo()
        (root / ".github").mkdir()
        (root / ".github" / "sd-review.json").write_text("{oops", encoding="utf-8")
        finished = self.run_cli(["--explain"], root)
        self.assertEqual(finished.returncode, sd_review.EXIT_USAGE)
        self.assertNotIn("Traceback", finished.stderr)
        self.assertIn("not valid JSON", finished.stderr)


class EnabledBackendTests(unittest.TestCase):
    """A row ships enabled only after its argv was checked against the real CLI.

    codex and prism were: `codex exec` with the hardened invocation, and
    `prism review range|codebase ... --format json`, both read off the installed
    binaries' help. gito's and kimi's transcribed spellings were wrong (gito
    takes `--what`, has no `--json`, and writes a report folder; `kimi review`
    is not a subcommand at all), so they ship disabled. Re-enabling one means
    editing this test too, which is the point: it is the record of what was
    verified, not a summary of what is intended.
    """

    def test_only_verified_argv_rows_ship_enabled(self) -> None:
        enabled = {row.name for row in sd_review.BACKENDS if row.enabled}
        self.assertEqual(enabled, {"codex", "prism"})

    def test_every_disabled_row_says_why(self) -> None:
        for row in sd_review.BACKENDS:
            if not row.enabled:
                self.assertTrue(row.disabled_reason.strip(), f"{row.name} is silently off")

class ScopeProvidersOverASkipTier(unittest.TestCase):
    """A `skip` tier silences the tier, not the scope.

    This exists because its absence let a false concern stand. C-18 in
    `docs/work/2026-09-02-dashboard-ack-and-mutation-count/design.md` claimed
    `sd-review --scope planning` never asks a provider, reasoning correctly that
    `docs_skip` routes every work item to tier `skip` and then stopping one
    function short of `plan_providers`, which prepends what a *scope* names
    ahead of whatever the tier asked for. Nothing in the repository disagreed,
    because nothing pinned the interaction. The concern survived a review round
    and an explanation to its owner before anyone ran it.

    So this is not coverage of a line. It is the assertion that would have
    refuted the claim in the round it was made.
    """

    def setUp(self) -> None:
        self.policy = json.loads((REPO_ROOT / ".github" / "sd-review.json").read_text())
        self.skip = sd_review.sd_route.route(
            ["docs/work/2026-01-01-any-item/prd.md"],
            lines=1, draft=False, policy=self.policy)

    def test_a_work_item_really_does_route_to_skip(self) -> None:
        """The half of C-18 that was right, kept so the rest has a subject."""

        self.assertEqual(self.skip.tier, "skip")
        self.assertEqual(tuple(self.skip.providers), ())

    def test_planning_scope_asks_a_provider_even_at_tier_skip(self) -> None:
        chain = sd_review.plan_providers(
            self.skip, self.policy, challenge=False, scope="planning")
        self.assertTrue(
            chain,
            "scope=planning produced an empty provider chain at tier skip. Either"
            " `plan_providers` stopped honouring `planning_providers`, or the"
            " policy stopped naming one -- and `sd-plan` gates `planning ->"
            " ready` on a lane that now asks nobody.")
        self.assertEqual(chain, tuple(self.policy["planning_providers"]))

    def test_challenge_asks_a_provider_even_at_tier_skip(self) -> None:
        """The same seam, reached by the other role that uses it."""

        chain = sd_review.plan_providers(
            self.skip, self.policy, challenge=True, scope="worktree")
        self.assertEqual(chain, tuple(self.policy["challenge_providers"]))

    def test_an_ordinary_scope_at_tier_skip_asks_nobody(self) -> None:
        """The control. Without it the three above pass on a chain that is
        never empty, which would prove nothing about the scope."""

        self.assertEqual(
            sd_review.plan_providers(
                self.skip, self.policy, challenge=False, scope="worktree"),
            ())

    def test_the_scope_adds_to_the_tier_rather_than_replacing_it(self) -> None:
        """`plan_providers` says "an extra stance, not a substitute". At tier
        `skip` those two readings agree, so the difference is only visible
        against a tier that asks for something."""

        deep = sd_review.sd_route.route(
            ["bin/sd_install.py"], lines=1, draft=False, policy=self.policy)
        self.assertEqual(deep.tier, "deep")
        chain = sd_review.plan_providers(
            deep, self.policy, challenge=False, scope="planning")
        for name in deep.providers:
            self.assertIn(name, chain, f"the scope dropped {name}, which the tier asked for")

    def test_the_scopes_provider_goes_in_front(self) -> None:
        """Ordering, pinned against a policy chosen so that it can fail.

        The live policy cannot show this. Its `deep` tier starts with codex and
        its `planning_providers` is codex, so prepending and appending produce
        the same chain and an ordering assertion over it passes either way --
        which is what the first version of this test did, and a mutation that
        swapped `extra + chain` for `chain + extra` survived it. The names here
        are deliberately disjoint from the tier's so the two orders differ.
        """

        policy = dict(self.policy, planning_providers=["prism"])
        deep = sd_review.sd_route.route(
            ["bin/sd_install.py"], lines=1, draft=False, policy=policy)
        self.assertEqual(tuple(deep.providers)[0], "codex", "fixture assumption")
        chain = sd_review.plan_providers(deep, policy, challenge=False, scope="planning")
        self.assertEqual(
            chain[0], "prism",
            "the scope's provider must lead the chain: it is the stance the run"
            " was asked for, and a chain read in order spends its budget on"
            " whatever comes first.")
        self.assertEqual(chain, ("prism", "codex", "gito"))

    def test_the_policy_still_names_a_planning_provider(self) -> None:
        """The claim above is about this repository's live policy, so it is
        asserted rather than assumed. A policy that dropped the key would make
        C-18 true again, and should fail here rather than quietly downstream."""

        self.assertTrue(self.policy.get("planning_providers"),
                        ".github/sd-review.json no longer names a planning provider")


if __name__ == "__main__":
    unittest.main()
