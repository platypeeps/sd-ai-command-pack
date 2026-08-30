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

import json
import pathlib
import unittest
from typing import Any

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review


def write_auth(home: pathlib.Path, payload: Any) -> pathlib.Path:
    home.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    (home / "auth.json").write_text(text, encoding="utf-8")
    return home


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

    def test_openai_api_key_is_not_scrubbed_and_is_not_a_refusal(self) -> None:
        # The codex CLI does not read OPENAI_API_KEY. Removing it, or refusing
        # because it is set, would be a false positive on any machine that has
        # it exported for an unrelated tool -- which is most of them.
        parent = {"PATH": "/bin", "OPENAI_API_KEY": "sk-unrelated"}
        self.assertEqual(sd_review.child_environment(parent), parent)
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
        parent = {
            "PATH": "/usr/bin",
            "CODEX_API_KEY": "sk-metered",
            "CODEX_ACCESS_TOKEN": "tok-metered",
            "OPENAI_API_KEY": "sk-unrelated",
        }
        result = sd_review.review(
            root, namespace(), runner, parent, self.chatgpt_home()
        )
        codex_calls = [call for call in runner.calls if call["argv"][0] == "codex"]
        self.assertEqual(len(codex_calls), 1)
        handed = codex_calls[0]["env"]
        self.assertNotIn("CODEX_API_KEY", handed)
        self.assertNotIn("CODEX_ACCESS_TOKEN", handed)
        self.assertEqual(handed["OPENAI_API_KEY"], "sk-unrelated")
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
            {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-unrelated"},
            self.chatgpt_home(),
        )
        self.assertEqual(result["outcomes"][0]["status"], sd_review.CLEAN)
        self.assertEqual(result["status"], "clean")


class RefusalReachesTheRunTests(ReviewFixture):
    def review_with_home(self, home: pathlib.Path) -> tuple[dict[str, Any], FakeRunner]:
        root = self.make_repo()
        (root / "src.py").write_text("x = 1\n", encoding="utf-8")
        runner = FakeRunner({"sd-check": sd_review.Completed(0, "{}", "")})
        result = sd_review.review(root, namespace(), runner, {"PATH": "/bin"}, home)
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
        result = sd_review.review(root, namespace(explain=True), runner, {}, home)
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
            root, namespace(), runner, {"PATH": "/bin", **secrets}, self.chatgpt_home()
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


if __name__ == "__main__":
    unittest.main()
