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
import io
import json
import os
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
        "provider": None,
        "timeout": 60,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


#: The fixture's own registry, deliberately not the shipped one. A test that
#: read `providers.yaml` would assert against whichever providers happen to be
#: pinned this month, and every chain assertion below would change meaning the
#: next time an entry is added. Two entries with the same reader is the shape
#: the chain tests need: a second reviewer that actually runs.
FIXTURE_REGISTRY = """
bills:
  first:  { cost: subscription }
  second: { cost: subscription }

providers:
  codex:  { start: "codex exec", vendor: openai, bill: first,
            roles: [reviewer], reader: codex-json, env: [] }
  second: { start: "second exec", vendor: secondvendor, bill: second,
            roles: [author, reviewer], reader: codex-json, env: [] }

roles:
  author: [second]
  reviewer: [codex, second]
"""

#: What the fixture repository consents to. `entry@executable` for both, which
#: is what `recipient()` derives from each entry's start line.
FIXTURE_CONSENT = "codex@codex, second@second"


class ReviewFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.registry_home = self.tmp / "registry-home"
        (self.registry_home / ".local" / "share" / "sd").mkdir(parents=True)
        (self.registry_home / ".local" / "share" / "sd" / "providers.yaml").write_text(
            FIXTURE_REGISTRY, encoding="utf-8"
        )

    def environment(self, **extra: str) -> dict[str, str]:
        """An environment whose HOME is the fixture's, so the run reads the
        fixture's registry rather than the developer's."""
        return {"HOME": str(self.registry_home), **extra}

    def local_block(self, root: pathlib.Path, *lines: str) -> None:
        body = "\n".join((f"{sd_review.sd_lib.CONSENT_KEY}: {FIXTURE_CONSENT}", *lines))
        (root / "CLAUDE.local.md").write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\n"
            f"{body}\n"
            "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n",
            encoding="utf-8",
        )

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
        self.local_block(root)
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
        self.assert_rejects({"tiers": {"cheap": []}}, "tiers is retired")
        self.assert_rejects({"default_tier": "gold"}, "default_tier must be one of")
        self.assert_rejects({"categories": [{"paths": ["a"]}]}, "name must be a non-empty string")
        self.assert_rejects({"categories": [{"name": "x", "paths": []}]}, "must name at least one glob")
        self.assert_rejects({"large_change_lines": -1}, "non-negative integer")
        self.assert_rejects({"large_change_lines": True}, "non-negative integer")
        self.assert_rejects({"severity_floor": "urgent"}, "severity_floor must be one of")
        self.assert_rejects({"authors": [3]}, "authors[0] must be a string")
        self.assert_rejects({"tier_order": ["a", "a"]}, "must not repeat a tier")
        self.assert_rejects({"challenge_providers": ["x"]}, "challenge_providers is retired")
        self.assert_rejects({"planning_providers": ["x"]}, "planning_providers is retired")

    def test_a_broken_policy_never_falls_back_to_the_default(self) -> None:
        root = self.make_repo()
        (root / ".github").mkdir()
        (root / ".github" / "sd-review.json").write_text("{", encoding="utf-8")
        with self.assertRaises(sd_review.PolicyError):
            sd_review.load_policy(root)


def _planned_for(case: Any, *, start: str) -> list[dict[str, Any]]:
    return sd_review._planned([case.provider(start=start)], pathlib.Path("/repo"), "prompt")


class ReaderTests(ReviewFixture):
    """What a registry entry's `reader` decides, now that no table does."""

    def provider(self, **overrides: Any) -> Any:
        fields: dict[str, Any] = {
            "name": "someone",
            "vendor": "somevendor",
            "bill": "first",
            "start": "someone review",
            "reader": "codex-json",
        }
        fields.update(overrides)
        return sd_review.sd_registry.Provider(**fields)

    def test_an_unimplemented_reader_is_not_run_and_names_itself(self) -> None:
        runner = FakeRunner()
        outcome = sd_review.run_provider(
            self.provider(reader="claude-json"),
            pathlib.Path("/nonexistent"),
            sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""),
            "prompt",
            runner,
            {},
            60,
        )
        self.assertEqual(outcome.status, sd_review.NOT_RUN)
        self.assertIn("claude-json", outcome.detail)
        self.assertEqual(runner.calls, [], "an unreadable provider is not started")

    def test_an_entry_whose_start_line_names_no_program_is_refused(self) -> None:
        """Copilot found this. `shlex.split("")` is empty, so the hardened
        invocation's first flag became the executable and the run tried to
        start `--sandbox`."""

        runner = FakeRunner()
        outcome = sd_review.run_provider(
            self.provider(start=""),
            pathlib.Path("/nonexistent"),
            sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""),
            "prompt",
            runner,
            {},
            60,
        )
        self.assertEqual(outcome.status, sd_review.REFUSED)
        self.assertIn("names no program", outcome.detail)
        self.assertEqual(runner.calls, [], "nothing is started")

    def test_the_dry_run_does_not_offer_an_argv_that_starts_with_a_flag(self) -> None:
        """The same defect reached `--dry-run`, which prints the invocation for
        a person to read. Asserted over the whole plan rather than one entry, so
        a future reader that forgets the check fails here too."""

        for row in _planned_for(self, start=""):
            self.assertFalse(row["would_run"])
            self.assertEqual(row["argv"], [])
        for row in _planned_for(self, start="codex exec"):
            self.assertTrue(row["would_run"])
            self.assertFalse(row["argv"][0].startswith("-"), row["argv"])

    def test_the_entrys_start_line_is_what_runs(self) -> None:
        """`codex-json` names a protocol, not one executable. An entry that
        speaks it through a wrapper runs the wrapper, and a reader that
        hardcoded `codex` would silently review with the wrong binary."""

        argv = sd_review.codex_argv(
            pathlib.Path("/repo"), pathlib.Path("/work"), "prompt", "wrapped codex exec"
        )
        self.assertEqual(argv[:3], ["wrapped", "codex", "exec"])
        self.assertIn("--sandbox", argv)


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

    def test_item_narrows_planning_scope_to_one_of_two_active_items(self) -> None:
        root = self.make_repo()
        for name in ("2026-01-01-first", "2026-01-02-second"):
            item = root / "docs" / "work" / name
            item.mkdir(parents=True)
            (item / "prd.md").write_text(
                "---\nstatus: planning\nbranch: topic\n---\n\n- [ ] one\n", encoding="utf-8"
            )
        both = sd_review.resolve_subject(root, "planning")
        self.assertEqual(len(both.paths), 2)
        one = sd_review.resolve_subject(root, "planning", "2026-01-02-second")
        self.assertEqual(one.paths, ("docs/work/2026-01-02-second/prd.md",))

    def test_item_that_names_no_active_item_is_a_usage_error_naming_the_active_ones(self) -> None:
        root = self.make_repo()
        item = root / "docs" / "work" / "2026-01-01-thing"
        item.mkdir(parents=True)
        (item / "prd.md").write_text(
            "---\nstatus: planning\nbranch: topic\n---\n\n- [ ] one\n", encoding="utf-8"
        )
        with self.assertRaises(sd_review.UsageError) as caught:
            sd_review.resolve_subject(root, "planning", "2026-01-01-other")
        self.assertIn("2026-01-01-thing", str(caught.exception))

    def test_item_outside_planning_scope_is_a_usage_error(self) -> None:
        root = self.make_repo()
        with self.assertRaises(sd_review.UsageError):
            sd_review.resolve_subject(root, "worktree", "2026-01-01-thing")


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
            self.environment(**dict(env or {})),
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
                "second": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        result = self.run_review(root, runner)
        self.assertEqual(result["status"], "rate_limited")
        statuses = {row["backend"]: row["status"] for row in result["outcomes"]}
        self.assertEqual(statuses["codex"], sd_review.RATE_LIMITED)
        self.assertEqual(statuses["second"], sd_review.NOT_RUN)
        self.assertEqual(sorted(result["remaining"]), ["codex", "second"])
        self.assertNotIn("second", [pathlib.Path(call["argv"][0]).name for call in runner.calls])

    def test_an_unavailable_provider_lets_the_chain_continue(self) -> None:
        root = self.make_repo()
        self.prepare(root)
        runner = FakeRunner(
            {
                "sd-check": sd_review.Completed(0, "{}", ""),
                "codex": sd_review.Completed(127, "", "codex: not found on PATH", False),
                "second": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        result = self.run_review(root, runner)
        statuses = {row["backend"]: row["status"] for row in result["outcomes"]}
        self.assertEqual(statuses["codex"], sd_review.UNAVAILABLE)
        self.assertEqual(statuses["second"], sd_review.CLEAN)
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
        self.local_block(root, "check: make check")
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
            ["git", "commit", "--quiet", "-m", "f\n\nAuthored-with: human"],
            cwd=str(root), check=True, capture_output=True
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
        # The fixture's HOME, so the CLI reads the fixture registry. Without it
        # these tests would pass or fail on whether whoever runs them has run
        # the installer, which is not what they are about.
        return subprocess.run(
            [sys.executable, str(SD_REVIEW), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "HOME": str(self.registry_home)},
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


class TheExplainRenderTests(ReviewFixture):
    """What `--explain` prints, and what a run that is not explaining must not.

    Copilot found this on the pull request. `render`'s explain block had been
    edited by text substitution and its nesting was wrong: the chain table sat
    inside the consent-refusal branch, so it printed only when consent was
    refused, and a real run that hit a consent refusal printed "explain only,
    nothing ran" and returned before its outcomes.

    The manual check that passed before this landed had both a missing registry
    and a missing consent line, which is the one combination under which the
    broken nesting looks right.
    """

    def explain(self, root: pathlib.Path, env: Mapping[str, str] | None = None) -> str:
        result = sd_review.review(
            root,
            namespace(explain=True),
            FakeRunner(),
            dict(env) if env is not None else self.environment(),
            self.chatgpt_home(),
        )
        stream = io.StringIO()
        sd_review.render(result, stream)
        return stream.getvalue()

    def test_a_scope_with_no_commits_does_not_claim_human_authorship(self) -> None:
        """Copilot found this. The fixture repository's only commit says
        `Authored-with: human`, but a worktree scope never reads a trailer at
        all, and printing "human-authored" there answers a question the run did
        not ask. It printed exactly that over a repository whose only commit
        said `claude/anthropic`."""

        text = self.explain(self.make_repo())
        self.assertIn("not read: worktree scope", text)
        self.assertNotIn("human-authored", text)

    def test_the_chain_prints_when_nothing_is_refused(self) -> None:
        """The fixture repository consents to both entries and has a registry,
        so there is no refusal to carry the table into view."""

        text = self.explain(self.make_repo())
        self.assertIn("reviewer chain", text)
        self.assertIn("use codex", " ".join(text.split()))
        self.assertIn("second", text)
        self.assertIn("explain only, nothing ran", text)

    def test_a_real_run_does_not_print_the_explain_footer(self) -> None:
        """A run that reviews must not claim it explained. This is the half of
        the defect that changed what a real invocation reported."""

        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner(
            {
                "sd-check": sd_review.Completed(0, "{}", ""),
                "codex": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        result = sd_review.review(
            root, namespace(), runner, self.environment(), self.chatgpt_home()
        )
        stream = io.StringIO()
        sd_review.render(result, stream)
        text = stream.getvalue()
        self.assertNotIn("explain only", text)
        self.assertIn("outcomes:", text)

    def test_a_consent_refusal_does_not_turn_a_real_run_into_an_explain(self) -> None:
        """The exact shape of the defect: a repository with no `reviewers`
        line, reviewed for real."""

        root = self.make_repo()
        (root / "CLAUDE.local.md").unlink()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = sd_review.review(
            root, namespace(), runner, self.environment(), self.chatgpt_home()
        )
        stream = io.StringIO()
        sd_review.render(result, stream)
        text = stream.getvalue()
        self.assertNotIn("explain only", text)
        self.assertNotIn("reviewer chain", text)


class DepthCountsProvidersThatCanAnswerTests(ReviewFixture):
    """A tier's depth is a count of reviewers, not of chain positions.

    Copilot found this. Entries were marked eligible without regard to whether
    this build can run them, so on the shipped registry a `deep` change --
    depth 3, chain `codex, claude, minimax, ...` -- spent two of its three
    slots on readers that do not exist, ran one provider, and reported `clean`
    with exit 0. The commit that introduced the depth model claimed "a change
    is read by as many providers as before", which that made false.

    Whether a reader is implemented is a fact about the build, knowable without
    touching the machine, so unlike preflight it belongs in the chain.
    """

    def registry_with(self, *readers: str) -> pathlib.Path:
        entries = "\n".join(
            f'  p{i}: {{ start: "p{i} exec", vendor: v{i}, bill: first, '
            f"roles: [reviewer], reader: {reader}, env: [] }}"
            for i, reader in enumerate(readers)
        )
        names = ", ".join(f"p{i}" for i in range(len(readers)))
        text = (
            "bills:\n  first: { cost: subscription }\n\n"
            f"providers:\n{entries}\n  author: {{ start: \"author exec\", vendor: av, "
            "bill: first, roles: [author], reader: codex-json, env: [] }\n\n"
            f"roles:\n  author: [author]\n  reviewer: [{names}]\n"
        )
        home = self.tmp / f"home-{abs(hash(readers))}"
        (home / ".local" / "share" / "sd").mkdir(parents=True)
        (home / ".local" / "share" / "sd" / "providers.yaml").write_text(text, encoding="utf-8")
        return home

    def consenting_repo(self, count: int) -> pathlib.Path:
        """A repository consenting to every `pN` entry, so the only thing left
        to make an entry ineligible is its reader."""
        root = self.make_repo()
        self.local_block(root)
        line = ", ".join(f"p{i}@p{i}" for i in range(count))
        (root / "CLAUDE.local.md").write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\n"
            f"{sd_review.sd_lib.CONSENT_KEY}: {line}\n"
            "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n",
            encoding="utf-8",
        )
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        return root

    def explained(self, home: pathlib.Path, count: int) -> dict[str, Any]:
        return sd_review.review(
            self.consenting_repo(count),
            namespace(explain=True),
            FakeRunner(),
            {"HOME": str(home)},
            self.chatgpt_home(),
        )

    def test_an_unimplemented_reader_is_ineligible_and_says_why(self) -> None:
        rows = self.explained(self.registry_with("claude-json", "codex-json"), 2)["chain"]
        self.assertFalse(rows[0]["eligible"])
        self.assertIn("claude-json", rows[0]["reason"])
        self.assertTrue(rows[1]["eligible"], rows[1]["reason"])

    def test_it_does_not_consume_a_depth_slot(self) -> None:
        """The defect in one assertion: with an unrunnable entry ahead of a
        runnable one, the run still picks the one that can answer."""

        result = self.explained(self.registry_with("claude-json", "codex-json"), 2)
        self.assertGreaterEqual(result["route"]["depth"], 1)
        self.assertEqual(result["providers"][:1], ["p1"], result["chain"])

    def test_every_reader_this_build_names_is_one_a_provider_can_run(self) -> None:
        """`READERS` is the allow-list the chain filters on. A name in it that
        `run_provider` does not implement would mark an entry eligible and then
        refuse it at the run, which is the hole this closes reopened."""

        self.assertEqual(sd_review.READERS, ("codex-json",))


class AnEmptyChainThatWantedReviewersTests(ReviewFixture):
    """`skipped` exits zero. Only tier `skip` may claim it.

    Copilot found the second half of this. The missing-registry case was fixed
    by special-casing that one refusal, which left every other way of emptying
    the chain reporting `skipped` -- a repository with a registry and no
    `reviewers` line reviewed nothing and exited 0 saying so. The rule is not
    about registries: a run that wanted reviewers and got none is
    `unavailable`, and `depth == 0` is the only thing that earns `skipped`.
    """

    def review(self, root: pathlib.Path, **overrides: Any) -> dict[str, Any]:
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        return sd_review.review(
            root, namespace(**overrides), runner, self.environment(), self.chatgpt_home()
        )

    def test_no_consent_line_is_unavailable_not_skipped(self) -> None:
        root = self.make_repo()
        (root / "CLAUDE.local.md").unlink()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        result = self.review(root)
        self.assertEqual(result["providers"], [])
        self.assertEqual(result["status"], "unavailable")
        self.assertNotEqual(sd_review.STATUS_EXIT[result["status"]], sd_review.EXIT_OK)

    def test_an_ordinary_run_says_why_it_had_nobody(self) -> None:
        """Copilot found this. The reasons were computed either way and
        printed only under `--explain`, so a plain run said the one word
        "unavailable" and exited 5. The operator whose repository has no
        'reviewers' line is the last one who would think to re-run with a flag
        to learn that."""
        root = self.make_repo()
        (root / "CLAUDE.local.md").unlink()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        result = self.review(root)
        stream = io.StringIO()
        sd_review.render(result, stream)
        printed = stream.getvalue()
        self.assertIn("no reviewer was available:", printed)
        self.assertIn("reviewers", printed)
        self.assertIn("unavailable", printed)

    def test_every_entry_being_the_authors_vendor_is_unavailable(self) -> None:
        """The chain empties for a third reason, and answers the same way."""

        root = self.make_repo()
        # A branch, so `base..head` holds the commit whose trailer is the point.
        subprocess.run(["git", "checkout", "--quiet", "-b", "topic"], cwd=str(root), check=True)
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "c\n\nAuthored-with: codex/openai"],
            cwd=str(root), check=True, capture_output=True,
        )
        result = self.review(root, scope="branch")
        self.assertEqual(result["authored_with"], ["openai"])
        reasons = " ".join(row["reason"] for row in result["chain"] if not row["eligible"])
        self.assertIn("openai", reasons)

    def test_a_docs_only_change_is_still_skipped_and_exits_zero(self) -> None:
        """The control. Tier `skip` means nothing needed reviewing, which is a
        different sentence from "nobody could review", and still exits 0."""

        root = self.make_repo()
        (root / "docs").mkdir()
        (root / "docs" / "note.md").write_text("hello\n", encoding="utf-8")
        result = self.review(root)
        self.assertEqual(result["route"]["depth"], 0)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(sd_review.STATUS_EXIT.get(result["status"], sd_review.EXIT_OK), sd_review.EXIT_OK)


class TheTrailerBlockTests(ReviewFixture):
    """A trailer is the last paragraph, unindented. Not any matching line.

    Found by running the tool on its own branch. A commit whose message
    *quoted* a refusal -- "2 commit(s) carry no Authored-with: trailer" --
    had that quoted line read as its own trailer, and the branch refused
    itself with a value of "trailer, starting at 76fb9d750096.".
    """

    def commit(self, root: pathlib.Path, message: str) -> str:
        (root / f"f{len(list(root.iterdir()))}.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--quiet", "-m", message], cwd=str(root), check=True, capture_output=True
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), check=True, capture_output=True, text=True
        ).stdout.strip()

    def subject(self, root: pathlib.Path, base: str) -> Any:
        return sd_review.Subject("branch", base, "HEAD", (), 0, "")

    def test_a_quoted_trailer_in_the_body_is_not_this_commits_trailer(self) -> None:
        root = self.make_repo()
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), check=True, capture_output=True, text=True
        ).stdout.strip()
        self.commit(
            root,
            "chore: describe a refusal\n\n"
            "    sd-review: refused: a commit carries no\n"
            "    Authored-with: trailer, starting at abc123.\n\n"
            "Authored-with: human",
        )
        self.assertEqual(sd_review.author_vendors(root, self.subject(root, base)), ())

    def test_an_indented_trailer_is_not_a_trailer(self) -> None:
        """Git does not read one, so neither does this. A commit that only
        mentions a trailer has said nothing, and saying nothing refuses."""

        root = self.make_repo()
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), check=True, capture_output=True, text=True
        ).stdout.strip()
        self.commit(root, "chore: mention one\n\n    Authored-with: claude/anthropic")
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.author_vendors(root, self.subject(root, base))
        self.assertIn("carry no Authored-with:", str(caught.exception))

    def test_a_commits_own_trailer_outranks_a_later_claim_about_it(self) -> None:
        """Copilot found this, and it inverted the rule the trailers exist for.

        Both dictionaries were merged in one walk with `setdefault`, and the
        log is newest-first, so a later commit's `Attributes:` won. Relabelling
        an anthropic-authored commit as an openai one -- and thereby buying it
        an anthropic reviewer, the exact thing the vendor rule forbids -- took
        one line in a later commit message.
        """

        root = self.make_repo()
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), check=True, capture_output=True, text=True
        ).stdout.strip()
        early = self.commit(root, "real work\n\nAuthored-with: claude/anthropic")
        self.commit(root, f"later\n\nAuthored-with: human\nAttributes: {early} codex/openai")
        self.assertEqual(
            sd_review.sd_lib.attribution(root, base, "HEAD")[early], "claude/anthropic"
        )
        self.assertEqual(sd_review.author_vendors(root, self.subject(root, base)), ("anthropic",))

    def test_attributes_names_an_earlier_commit_from_a_later_one(self) -> None:
        root = self.make_repo()
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), check=True, capture_output=True, text=True
        ).stdout.strip()
        early = self.commit(root, "feat: written before the convention")
        self.commit(root, f"chore: attribute it\n\nAuthored-with: human\nAttributes: {early} codex/openai")
        self.assertEqual(sd_review.author_vendors(root, self.subject(root, base)), ("openai",))

    def test_attributes_naming_a_commit_outside_the_range_says_nothing(self) -> None:
        """Copilot's fourth pass. A claim about a commit nobody is reviewing
        put its vendor in the author set anyway, and an author's vendor is
        barred from reviewing -- so one line naming an already-merged sha
        struck a reviewer off the chain for work it did not write."""

        root = self.make_repo()
        outsider = self.commit(root, "on main\n\nAuthored-with: kimi/moonshot")
        subprocess.run(
            ["git", "checkout", "--quiet", "-b", "work"],
            cwd=str(root), check=True, capture_output=True,
        )
        self.commit(
            root,
            f"the only commit under review\n\nAuthored-with: human\n"
            f"Attributes: {outsider} kimi/moonshot",
        )
        self.assertEqual(
            sd_review.author_vendors(root, self.subject(root, outsider)), ()
        )

    def test_a_padded_or_capitalised_vendor_still_names_its_vendor(self) -> None:
        """The chain compares `provider.vendor in author_vendors` by exact
        match. `claude / anthropic` yielded " anthropic", which matched no
        entry, so the branch's own vendor stayed eligible and reviewed what it
        had written. The rule failed open, and said nothing."""

        root = self.make_repo()
        for value in ("claude / anthropic", "Claude/Anthropic", " claude/anthropic "):
            with self.subTest(trailer=value):
                base = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(root), check=True, capture_output=True, text=True,
                ).stdout.strip()
                self.commit(root, f"work\n\nAuthored-with: {value}")
                self.assertEqual(
                    sd_review.author_vendors(root, self.subject(root, base)),
                    ("anthropic",),
                )

    def test_a_short_sha_still_names_its_commit(self) -> None:
        """Git takes a prefix everywhere else, so the range check does too."""

        root = self.make_repo()
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), check=True, capture_output=True, text=True
        ).stdout.strip()
        early = self.commit(root, "feat: written before the convention")
        self.commit(
            root, f"chore: attribute it\n\nAuthored-with: human\nAttributes: {early[:8]} codex/openai"
        )
        self.assertEqual(sd_review.author_vendors(root, self.subject(root, base)), ("openai",))


class NoRegistryOnThisMachineTests(ReviewFixture):
    """A machine with no installed registry still answers.

    CI found this, not a test. The routing lane runs `sd-review --explain` on a
    bare runner, which has never run the installer, and the first version of the
    registry reader let the refusal reach `main` and exit 2: `sd-review: error:
    no provider registry at /home/runner/.local/share/sd/providers.yaml`. The
    lane exists to report the plan and asks nobody, so needing an install to
    print one was backwards.
    """

    def bare(self) -> dict[str, str]:
        """An environment whose HOME holds no registry."""
        empty = self.tmp / "no-registry-home"
        empty.mkdir()
        return {"HOME": str(empty)}

    def test_explain_answers_without_an_installed_registry(self) -> None:
        root = self.make_repo()
        runner = FakeRunner()
        result = sd_review.review(
            root, namespace(explain=True), runner, self.bare(), self.chatgpt_home()
        )
        self.assertEqual(result["status"], "explained")
        self.assertIn("no provider registry", result["registry_refusal"])
        self.assertEqual(result["providers"], [])
        self.assertEqual(runner.calls, [])

    def test_the_explain_render_prints_the_reason(self) -> None:
        root = self.make_repo()
        result = sd_review.review(
            root, namespace(explain=True), FakeRunner(), self.bare(), self.chatgpt_home()
        )
        stream = io.StringIO()
        sd_review.render(result, stream)
        self.assertIn("no provider registry", stream.getvalue())

    def test_a_real_review_is_unavailable_and_not_skipped(self) -> None:
        """`skipped` exits 0 and means "nothing needed reviewing". A machine
        that could not have reviewed anything must not borrow that word."""

        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = sd_review.review(
            root, namespace(), runner, self.bare(), self.chatgpt_home()
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(sd_review.STATUS_EXIT[result["status"]], sd_review.EXIT_GATE)
        self.assertNotEqual(sd_review.STATUS_EXIT[result["status"]], sd_review.EXIT_OK)

    def test_a_named_provider_is_refused_rather_than_answered_emptily(self) -> None:
        """With no registry, `pick` would say "no provider 'codex'", which reads
        as "that name is wrong" rather than "there is no registry here"."""

        root = self.make_repo()
        with self.assertRaises(sd_review.sd_registry.RegistryError) as caught:
            sd_review.review(
                root, namespace(provider="codex"), FakeRunner(), self.bare(), self.chatgpt_home()
            )
        self.assertIn("no provider registry", str(caught.exception))


class TheRoutingLaneRunsOnABareRunner(ReviewFixture):
    """The lane's own invocation, run the way the workflow runs it.

    `.github/actions/review-route` calls `bin/sd-review --scope pr --explain`
    and fails the job on a non-zero exit. This asserts that exit code against a
    HOME with no registry, which is what a GitHub runner is.
    """

    def test_explain_exits_zero_with_an_empty_home(self) -> None:
        empty = self.tmp / "runner-home"
        empty.mkdir()
        finished = subprocess.run(
            [sys.executable, str(SD_REVIEW), "--explain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "HOME": str(empty)},
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("no provider registry", finished.stdout)


class ScopeProvidersOverASkipTier(unittest.TestCase):
    """A `skip` tier silences the tier, not the scope.

    Kept last in this file on purpose. Its line span is cited from
    `docs/work/2026-09-02-dashboard-ack-and-mutation-count/design.md`, and it
    drifted four times in one pull request because every new class landed above
    it. Last means only its own edits move it.

    This exists because its absence let a false concern stand. C-18 in
    `docs/work/2026-09-02-dashboard-ack-and-mutation-count/design.md` claimed
    `sd-review --scope planning` never asks a provider, reasoning correctly that
    `docs_skip` routes every work item to tier `skip` and then stopping one
    function short of the floor a scope puts under the tier's depth. Nothing in
    the repository disagreed, because nothing pinned the interaction. The
    concern survived a review round and an explanation to its owner before
    anyone ran it.

    The seam moved when the tier stopped naming providers: it used to be
    `plan_providers`, prepending names to the tier's chain, and it is now
    `review_depth`, raising the tier's count. The claim it refutes is the same
    one, so the class is kept and re-aimed rather than deleted with the
    function -- a deleted test is a claim that becomes true again quietly.
    """

    def setUp(self) -> None:
        self.policy = json.loads((REPO_ROOT / ".github" / "sd-review.json").read_text())
        self.skip = sd_review.sd_route.route(
            ["docs/work/2026-01-01-any-item/prd.md"],
            lines=1, draft=False, policy=self.policy)

    def test_a_work_item_really_does_route_to_skip(self) -> None:
        """The half of C-18 that was right, kept so the rest has a subject."""

        self.assertEqual(self.skip.tier, "skip")
        self.assertEqual(self.skip.depth, 0)

    def test_planning_scope_asks_a_provider_even_at_tier_skip(self) -> None:
        self.assertEqual(
            sd_review.review_depth(self.skip, challenge=False, scope="planning"), 1,
            "scope=planning earned no reviewer at tier skip. Either `review_depth`"
            " stopped honouring FLOOR_SCOPES, or `planning` left it -- and"
            " `sd-plan` gates `planning -> ready` on a lane that now asks nobody.")

    def test_challenge_asks_a_provider_even_at_tier_skip(self) -> None:
        """The same seam, reached by the other role that uses it."""

        self.assertEqual(
            sd_review.review_depth(self.skip, challenge=True, scope="worktree"), 1)

    def test_an_ordinary_scope_at_tier_skip_asks_nobody(self) -> None:
        """The control. Without it the two above pass on a floor that is never
        zero, which would prove nothing about the scope."""

        self.assertEqual(
            sd_review.review_depth(self.skip, challenge=False, scope="worktree"), 0)

    def test_the_scope_adds_to_the_tier_rather_than_replacing_it(self) -> None:
        """The floor is a minimum, not a setting. At tier `skip` those two
        readings agree, so the difference is only visible against a tier that
        already asks for more than one."""

        deep = sd_review.sd_route.route(
            ["bin/sd_install.py"], lines=1, draft=False, policy=self.policy)
        self.assertEqual(deep.tier, "deep")
        self.assertGreater(deep.depth, 1, "the deep tier asks for one reviewer, so a"
                           " floor of one and a replacement of one agree here")
        self.assertEqual(
            sd_review.review_depth(deep, challenge=False, scope="planning"), deep.depth,
            "the scope's floor reduced the deep tier's read")

    def test_every_floor_scope_is_a_scope_the_cli_accepts(self) -> None:
        """A typo in FLOOR_SCOPES is a floor that never fires, and every
        assertion above would still pass: they name their scope directly."""

        for scope in sd_review.FLOOR_SCOPES:
            self.assertIn(scope, sd_review.SCOPES, f"{scope!r} is not a scope")


if __name__ == "__main__":
    unittest.main()
