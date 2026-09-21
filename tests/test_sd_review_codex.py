"""The R10-D4 refusal matrix: codex runs are subscription-only or they do not run.

Every case here uses a fake `auth.json` under a temporary home. The real
`~/.codex/auth.json` is never read and never written by this file: a test that
had to mutate a developer's login to prove a billing guard would be a worse
hazard than the one it tests.

The assertions on scrubbing read the environment the runner *received*, not the
one the caller meant to build. That distinction is the whole point -- an
intention that never reaches `subprocess` bills the account anyway.
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys
import unittest
from typing import Any

from tests.test_sd_review import (
    PROMPT_INPUT_LOADED,
    PROMPT_INPUT_SUPPRESSED,
    FakeRunner,
    ReviewFixture,
    codex_sessions,
    namespace,
    prompt_input,
    sd_review,
)


def write_auth(home: pathlib.Path, payload: Any) -> pathlib.Path:
    home.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (home / "auth.json").write_text(text, encoding="utf-8")
    return home


class StdinTransportTests(ReviewFixture):
    def test_large_prompt_reaches_real_local_child_unchanged_through_stdin(self) -> None:
        program = self.tmp / "codex_protocol_fixture.py"
        receipt = self.tmp / "stdin-receipt.json"
        program.write_text("import hashlib,json,sys\nfrom pathlib import Path\n"
            "data=sys.stdin.read() if sys.argv[-1]=='-' else sys.argv[-1]\n"
            f"Path({str(receipt)!r}).write_text(json.dumps({{'bytes':len(data.encode()),'sha256':hashlib.sha256(data.encode()).hexdigest(),'last_arg':sys.argv[-1] if sys.argv[-1]=='-' else 'prompt-in-argv'}}))\n"
            "print('{\"findings\": []}')\n")
        prompt = "fixture-é-" * 100000
        self.assertLess(len(prompt.encode()), sd_review.MAX_OUTPUT_BYTES)
        provider = sd_review.sd_registry.Provider(name="fixture", vendor="openai", bill="fixture",
            reader="codex-json", start=f"{sys.executable} {program}")
        outcome = sd_review.run_provider(provider, self.tmp,
            sd_review.Subject("worktree", "HEAD", "worktree", (), 0, ""), prompt,
            sd_review.subprocess_runner, self.environment(), 10, self.chatgpt_home())
        self.assertEqual(outcome.status, sd_review.CLEAN, outcome.detail)
        self.assertEqual(json.loads(receipt.read_text()), {"bytes":len(prompt.encode()),
            "sha256":hashlib.sha256(prompt.encode()).hexdigest(), "last_arg":"-"})
        self.assertNotIn(prompt, outcome.argv)
        # `skill_suppression` is None because this call supplies no probe: the
        # key is null here rather than absent, so a reader of one outcome can
        # tell "not measured" from "measured and inert".
        self.assertEqual(outcome.diagnostic, {"prompt_transport": "stdin", "prompt_bytes": len(prompt.encode()),
                         "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                         "skill_suppression": None})


class PreflightTests(ReviewFixture):
    def home(self, name: str) -> pathlib.Path:
        return self.tmp / name

    def test_a_chatgpt_login_with_no_stored_key_passes(self) -> None:
        home = write_auth(self.home("ok"), {"auth_mode": "chatgpt", "OPENAI_API_KEY": None})
        self.assertEqual(sd_review.codex_preflight(home), home / "auth.json")

    def test_an_absent_openai_api_key_field_also_passes(self) -> None:
        home = write_auth(self.home("ok2"), {"auth_mode": "chatgpt"})
        self.assertEqual(sd_review.codex_preflight(home), home / "auth.json")

    def test_a_non_chatgpt_auth_mode_refuses(self) -> None:
        home = write_auth(self.home("apikey"), {"auth_mode": "apikey", "OPENAI_API_KEY": None})
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.codex_preflight(home)
        message = str(caught.exception)
        self.assertIn("auth_mode is 'apikey', not 'chatgpt'", message)
        self.assertIn("subscription-only", message)

    def test_a_stored_openai_api_key_refuses_without_printing_it(self) -> None:
        secret = "sk-do-not-print-me-0123456789"
        home = write_auth(self.home("stored"), {"auth_mode": "chatgpt", "OPENAI_API_KEY": secret})
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.codex_preflight(home)
        message = str(caught.exception)
        self.assertIn("OPENAI_API_KEY field holds a value (not shown)", message)
        self.assertNotIn(secret, message)

    def test_a_missing_auth_file_refuses(self) -> None:
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.codex_preflight(self.home("nothing"))
        self.assertIn("does not exist", str(caught.exception))

    def test_a_malformed_auth_file_refuses(self) -> None:
        home = write_auth(self.home("broken"), "{nope")
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.codex_preflight(home)
        self.assertIn("not valid JSON", str(caught.exception))

    def test_an_unprintable_auth_mode_is_described_not_quoted(self) -> None:
        home = write_auth(self.home("weird"), {"auth_mode": {"nested": "sk-secret-value"}})
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.codex_preflight(home)
        message = str(caught.exception)
        self.assertIn("not a recognised mode name", message)
        self.assertNotIn("sk-secret-value", message)

    def test_an_over_long_auth_mode_is_not_echoed(self) -> None:
        home = write_auth(self.home("long"), {"auth_mode": "x" * 200})
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.codex_preflight(home)
        self.assertNotIn("x" * 200, str(caught.exception))


class EnvironmentTests(ReviewFixture):
    def test_the_metered_variables_are_removed_by_construction(self) -> None:
        parent = {"PATH": "/bin", "CODEX_API_KEY": "sk-a", "CODEX_ACCESS_TOKEN": "tok-b"}
        child = sd_review.child_environment(parent)
        self.assertEqual(child, {"PATH": "/bin"})
        self.assertEqual(sd_review.scrubbed_names(parent), ("CODEX_API_KEY", "CODEX_ACCESS_TOKEN"))

    def test_openai_api_key_needs_a_declaration_but_is_not_a_billing_refusal(self) -> None:
        parent = {"PATH": "/bin", "OPENAI_API_KEY": "sk-unrelated"}
        self.assertEqual(sd_review.child_environment(parent), {"PATH": "/bin"})
        self.assertEqual(sd_review.child_environment(parent, ("OPENAI_API_KEY",)), parent)
        self.assertEqual(sd_review.scrubbed_names(parent), ())
        self.assertNotIn("OPENAI_API_KEY", sd_review.CODEX_METERED_ENV)

    def test_the_environment_handed_to_the_subprocess_has_no_metered_key(self) -> None:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner(
            {
                "sd-check": sd_review.Completed(0, "{}", ""),
                "codex": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        # HOME is where the run reads the provider registry from, so it is in
        # every environment here; it is not a credential and is not scrubbed.
        parent = self.environment(
            PATH=str(self.tool_bin) + ":/usr/bin",
            CODEX_API_KEY="sk-metered",
            CODEX_ACCESS_TOKEN="tok-metered",
            OPENAI_API_KEY="sk-unrelated",
        )
        result = sd_review.review(
            root, namespace(), runner, parent, self.chatgpt_home()
        )
        codex_calls = [call for call in runner.calls if call["argv"][0] == "codex"]
        # Two now: the skill-suppression probe and the review. Asserted over
        # every codex call rather than the first, so a third one cannot arrive
        # unscrubbed behind a test that only ever read call zero.
        self.assertEqual(len(codex_calls), 2, [call["argv"] for call in codex_calls])
        for handed in (call["env"] for call in codex_calls):
            self.assertNotIn("CODEX_API_KEY", handed)
            self.assertNotIn("CODEX_ACCESS_TOKEN", handed)
            self.assertNotIn("OPENAI_API_KEY", handed)
        self.assertEqual(
            result["outcomes"][0]["scrubbed_env_names"],
            ["CODEX_API_KEY", "CODEX_ACCESS_TOKEN"],
        )

    def test_a_parent_with_only_openai_api_key_still_runs(self) -> None:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner(
            {
                "sd-check": sd_review.Completed(0, "{}", ""),
                "codex": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        result = sd_review.review(
            root,
            namespace(),
            runner,
            self.environment(OPENAI_API_KEY="sk-unrelated"),
            self.chatgpt_home(),
        )
        self.assertEqual(result["outcomes"][0]["status"], sd_review.CLEAN)
        self.assertEqual(result["status"], "clean")


class RefusalReachesTheRunTests(ReviewFixture):
    def review_with_home(self, home: pathlib.Path) -> tuple[dict[str, Any], FakeRunner]:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = sd_review.review(root, namespace(), runner, self.environment(), home)
        return result, runner

    def test_a_refused_preflight_never_starts_codex(self) -> None:
        home = write_auth(self.tmp / "apikey-home", {"auth_mode": "apikey"})
        result, runner = self.review_with_home(home)
        self.assertNotIn("codex", [call["argv"][0] for call in runner.calls])
        statuses = {row["backend"]: row["status"] for row in result["outcomes"]}
        self.assertEqual(statuses["codex"], sd_review.REFUSED)

    def test_a_refusal_is_reported_and_exits_three(self) -> None:
        home = write_auth(self.tmp / "stored-home", {"auth_mode": "chatgpt", "OPENAI_API_KEY": "sk-x"})
        result, _ = self.review_with_home(home)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(sd_review.STATUS_EXIT[result["status"]], sd_review.EXIT_REFUSED)

    def test_explain_reports_the_preflight_without_running_it_against_the_real_home(self) -> None:
        root = self.make_repo()
        home = write_auth(self.tmp / "explain-home", {"auth_mode": "apikey"})
        runner = FakeRunner()
        result = sd_review.review(root, namespace(explain=True), runner, self.environment(), home)
        self.assertFalse(result["codex_preflight"]["ok"])
        self.assertIn("auth_mode", result["codex_preflight"]["reason"])
        self.assertEqual(runner.calls, [])


class NoCredentialReachesOutputTests(ReviewFixture):
    """Grep the tool's own output paths for anything a credential could ride on."""

    def test_no_env_value_appears_in_stdout_stderr_or_json(self) -> None:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        secrets = {
            "CODEX_API_KEY": "sk-codex-secret-AAAA",
            "CODEX_ACCESS_TOKEN": "tok-codex-secret-BBBB",
            "OPENAI_API_KEY": "sk-openai-secret-CCCC",
        }
        runner = FakeRunner(
            {
                "sd-check": sd_review.Completed(0, "{}", ""),
                "codex": sd_review.Completed(0, '{"findings": []}', ""),
            }
        )
        result = sd_review.review(
            root, namespace(), runner, self.environment(PATH="/bin", **secrets), self.chatgpt_home()
        )
        serialised = json.dumps(result)
        import io

        rendered = io.StringIO()
        sd_review.render(result, rendered)
        for name, value in secrets.items():
            self.assertNotIn(value, serialised, f"{name} value reached --json")
            self.assertNotIn(value, rendered.getvalue(), f"{name} value reached stdout")
        self.assertIn("CODEX_API_KEY", serialised)

    def test_a_refusal_message_carries_no_value_from_auth_json(self) -> None:
        home = write_auth(
            self.tmp / "leak-home",
            {"auth_mode": "chatgpt", "OPENAI_API_KEY": "sk-leak-DDDD", "tokens": {"id_token": "jwt-EEEE"}},
        )
        with self.assertRaises(sd_review.Refusal) as caught:
            sd_review.codex_preflight(home)
        message = str(caught.exception)
        self.assertNotIn("sk-leak-DDDD", message)
        self.assertNotIn("jwt-EEEE", message)


class SkillSuppressionProbeTests(ReviewFixture):
    """sd:1248. The lane passes `-c skills.include_instructions=false`, and a
    build that does not know the key ignores it and exits 0. Every state below
    is pinned with an injected runner, so none of the three is reachable only
    by accident: unscripted, the fixture answers the probe with a render that
    carries no block, and every probe would read as `suppressed`.
    """

    #: What `codex debug prompt-input` renders when skill instructions load.
    LOADED = PROMPT_INPUT_LOADED
    SUPPRESSED = PROMPT_INPUT_SUPPRESSED

    def entry(self, start: str = "codex exec") -> Any:
        return sd_review.sd_registry.Provider(name="codex", vendor="openai", bill="first",
                                              reader="codex-json", start=start)

    def probe(self, answer: Any, start: str = "codex exec") -> tuple[dict[str, Any], FakeRunner]:
        runner = FakeRunner({"codex": answer})
        state = sd_review.codex_skill_state(self.entry(start), self.tmp, runner,
                                            self.environment(), self.chatgpt_home())
        return state, runner

    def test_a_rendered_block_reports_unsuppressed(self) -> None:
        state, _ = self.probe(sd_review.Completed(0, self.LOADED, ""))
        self.assertEqual(state["state"], sd_review.SKILLS_UNSUPPRESSED)
        self.assertIn("<skills_instructions>", state["reason"])

    def test_an_absent_block_reports_suppressed(self) -> None:
        state, _ = self.probe(sd_review.Completed(0, self.SUPPRESSED, ""))
        self.assertEqual(state["state"], sd_review.SKILLS_SUPPRESSED)
        self.assertIn("took effect", state["reason"])

    def test_a_build_without_the_subcommand_reports_unknown(self) -> None:
        """The state sd:1248 exists for. An older codex has no `debug
        prompt-input`, and "cannot tell" must not read as either answer."""

        state, _ = self.probe(sd_review.Completed(2, "", "error: unrecognized subcommand 'prompt-input'"))
        self.assertEqual(state["state"], sd_review.SKILLS_UNKNOWN)
        self.assertIn("unrecognized subcommand", state["reason"])

    def test_a_probe_that_never_started_reports_unknown(self) -> None:
        state, _ = self.probe(sd_review.Completed(127, "", "codex: not found on PATH", launched=False))
        self.assertEqual(state["state"], sd_review.SKILLS_UNKNOWN)

    def test_a_clean_exit_with_nothing_rendered_reports_unknown(self) -> None:
        """Exit 0 and empty output is not evidence of suppression. Read as
        `suppressed` it would be the false belief this probe removes."""

        state, _ = self.probe(sd_review.Completed(0, "   \n", ""))
        self.assertEqual(state["state"], sd_review.SKILLS_UNKNOWN)

    def test_a_help_page_on_exit_0_reports_unknown(self) -> None:
        """Found by the codex review of this change. A wrapper that does not
        know `debug prompt-input` may print its help and exit 0. No marker in
        a help page is not suppression, and reading it so removed the warning
        the probe exists to raise."""

        state, _ = self.probe(sd_review.Completed(0, "Usage: wrapper exec [OPTIONS]\n", ""))
        self.assertEqual(state["state"], sd_review.SKILLS_UNKNOWN)
        self.assertIn("no prompt input list", state["reason"])

    def test_json_that_is_not_a_render_reports_unknown(self) -> None:
        for stdout in ("[]", "{}", '{"findings": []}', '[{"type": "message", "content": "text"}]',
                       '[{"type": "reasoning", "content": []}]'):
            with self.subTest(stdout=stdout):
                state, _ = self.probe(sd_review.Completed(0, stdout, ""))
                self.assertEqual(state["state"], sd_review.SKILLS_UNKNOWN)

    def test_the_marker_is_read_from_the_render_text_and_not_the_bytes(self) -> None:
        """A block inside any message's text part counts, wherever it sits."""

        state, _ = self.probe(sd_review.Completed(0, prompt_input("first", "x <skills_instructions> y"), ""))
        self.assertEqual(state["state"], sd_review.SKILLS_UNSUPPRESSED)

    def test_an_entry_with_no_program_is_not_probed(self) -> None:
        state, runner = self.probe(sd_review.Completed(0, self.SUPPRESSED, ""), start="")
        self.assertEqual(state["state"], sd_review.SKILLS_NOT_PROBED)
        self.assertIn("names no program", state["reason"])
        self.assertEqual(runner.calls, [])

    def test_a_start_line_without_exec_is_not_probed_and_says_so(self) -> None:
        """No `exec` to replace means no probe command can be derived. That is
        `not_probed` with the start line in the reason, never a guess."""

        state, runner = self.probe(sd_review.Completed(0, self.SUPPRESSED, ""), start="codex review")
        self.assertEqual(state["state"], sd_review.SKILLS_NOT_PROBED)
        self.assertIn("'codex review'", state["reason"])
        self.assertIn("does not end in `exec`", state["reason"])
        self.assertEqual(runner.calls, [])

    def test_the_probe_argv_is_the_entrys_program_and_not_the_lanes(self) -> None:
        """`codex debug prompt-input` rejects `--ignore-user-config` with exit
        2, so the probe cannot carry the lane's confinement flags. It answers
        for the entry's own program, not for whatever `codex` PATH resolves."""

        argv = sd_review.codex_skill_probe_argv("wrapped codex exec")
        self.assertEqual(argv[:4], ["wrapped", "codex", "debug", "prompt-input"])
        self.assertNotIn("--ignore-user-config", argv)
        self.assertNotIn("exec", argv)
        self.assertEqual(argv[argv.index("skills.include_instructions=false") - 1], "-c")

    def test_the_probe_keeps_a_launcher_prefix_whole(self) -> None:
        """Found by the codex review of this change. Taking only the first
        token turned `python3 -m codex_wrapper exec` into `python3 debug
        prompt-input`, which probes the interpreter and not the provider."""

        argv = sd_review.codex_skill_probe_argv("python3 -m codex_wrapper exec")
        self.assertEqual(argv[:5], ["python3", "-m", "codex_wrapper", "debug", "prompt-input"])
        self.assertEqual(sd_review.codex_skill_probe_argv("python3 -m codex_wrapper"), [])

    def test_the_probe_runs_in_the_lanes_scrubbed_child_environment(self) -> None:
        """A probe of another `CODEX_HOME` answers about another run, and one
        carrying a metered variable would hand it to a codex process."""

        home = self.chatgpt_home()
        runner = FakeRunner({"codex": sd_review.Completed(0, self.SUPPRESSED, "")})
        sd_review.codex_skill_state(self.entry(), self.tmp, runner,
                                    self.environment(CODEX_API_KEY="sk-metered"), home)
        handed = runner.calls[0]["env"]
        self.assertEqual(handed["CODEX_HOME"], str(home))
        self.assertNotIn("CODEX_API_KEY", handed)

    def review_with_probe(self, answer: Any, **options: Any) -> dict[str, Any]:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")

        def codex(argv, env, cwd, timeout):
            if argv[1:3] == ["debug", "prompt-input"]:
                return answer
            return sd_review.Completed(0, '{"findings": []}', "")

        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", ""), "codex": codex})
        return sd_review.review(root, namespace(**options), runner, self.environment(), self.chatgpt_home())

    def test_an_inert_key_warns_on_the_run_it_ran_under_and_refuses_nothing(self) -> None:
        """A refusal would turn a hardening flag into a review blocker, so the
        measurement rides the outcome that ran under it and the review stands."""

        result = self.review_with_probe(sd_review.Completed(0, self.LOADED, ""))
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["codex_skill_suppression"]["state"], sd_review.SKILLS_UNSUPPRESSED)
        measured = result["outcomes"][0]["diagnostic"]["skill_suppression"]
        self.assertEqual(measured["state"], sd_review.SKILLS_UNSUPPRESSED)
        rendered = io.StringIO()
        sd_review.render(result, rendered)
        self.assertIn("warning: codex skill instructions unsuppressed", rendered.getvalue())

    def test_a_suppressed_key_warns_about_nothing(self) -> None:
        result = self.review_with_probe(sd_review.Completed(0, self.SUPPRESSED, ""))
        self.assertEqual(result["codex_skill_suppression"]["state"], sd_review.SKILLS_SUPPRESSED)
        rendered = io.StringIO()
        sd_review.render(result, rendered)
        self.assertNotIn("warning:", rendered.getvalue())

    def test_explain_reports_the_probe_beside_the_auth_preflight(self) -> None:
        """`.claude/rules/sd-operator-defaults.md` sends the operator to
        `--explain --json` before an expensive check. The answer is there."""

        result = self.review_with_probe(sd_review.Completed(0, self.LOADED, ""), explain=True)
        self.assertEqual(result["status"], "explained")
        self.assertTrue(result["codex_preflight"]["ok"])
        self.assertEqual(result["codex_skill_suppression"]["state"], sd_review.SKILLS_UNSUPPRESSED)
        self.assertIn("debug prompt-input", result["codex_skill_suppression"]["probe"])

    def test_a_refused_auth_starts_no_probe_and_says_why(self) -> None:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner()
        home = write_auth(self.tmp / "apikey-probe-home", {"auth_mode": "apikey"})
        result = sd_review.review(root, namespace(explain=True), runner, self.environment(), home)
        self.assertEqual(result["codex_skill_suppression"]["state"], sd_review.SKILLS_NOT_PROBED)
        self.assertIn("auth preflight refused", result["codex_skill_suppression"]["reason"])
        self.assertEqual(runner.calls, [])

    def test_the_probe_and_the_review_are_separate_codex_calls(self) -> None:
        """One probe per codex dispatch, and the review session is unchanged:
        the probe must not become an argument of the run it measures."""

        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", ""),
                             "codex": sd_review.Completed(0, '{"findings": []}', "")})
        sd_review.review(root, namespace(), runner, self.environment(), self.chatgpt_home())
        sessions = codex_sessions(runner)
        self.assertEqual(len(sessions), 1)
        self.assertNotIn("debug", sessions[0]["argv"])
        self.assertEqual([call["argv"][1:3] for call in runner.calls if call["argv"][0] == "codex"],
                         [["debug", "prompt-input"], ["exec", "--sandbox"]])


if __name__ == "__main__":
    unittest.main()
