"""The `agy-json` reader: how it is invoked, read back, and kept independent.

`agy` is one command in front of several vendors' models. It serves Google's
Gemini, Anthropic's Claude and OpenAI's GPT-OSS from the same executable, so
an entry's `vendor` is a claim about the model rather than about the program.
The independence guard in `bin/sd_registry.py` compares that claim against the
branch's authorship trailers, which makes a wrong claim worse than a missing
one: the review would run on the author's own model and be reported as
independent. The refusals below are what keeps the claim honest.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_registry  # noqa: E402

from tests.test_sd_review import sd_review  # noqa: E402

#: The smallest registry that runs `agy`. Each test edits one line of it, so
#: the line a test changes is the reason it fails.
AGY = """\
bills:
  free: { cost: local }
providers:
  one: { url: "http://localhost:1/v1", vendor: alpha, bill: free, roles: [author] }
  agy: { start: "agy", model: MODEL, vendor: VENDOR, bill: free,
         roles: [reviewer], reader: agy-json }
roles:
  author: [one]
  reviewer: [agy]
"""


def registry_text(vendor: str = "google", model: str | None = "gemini-3.1-pro-high",
                  start: str = "agy", reader: str = "agy-json") -> str:
    text = AGY.replace("VENDOR", vendor).replace('"agy"', f'"{start}"')
    text = text.replace("reader: agy-json", f"reader: {reader}")
    return text.replace("model: MODEL, ", "") if model is None else text.replace("MODEL", model)


def written(text: str) -> pathlib.Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    with handle:
        handle.write(text)
    return pathlib.Path(handle.name)


def provider(**overrides: object) -> object:
    fields: dict[str, object] = {
        "name": "agy", "vendor": "google", "bill": "free", "start": "agy",
        "model": "gemini-3.1-pro-high", "reader": "agy-json",
    }
    fields.update(overrides)
    return sd_registry.Provider(**fields)  # type: ignore[arg-type]


class TheReaderIsRunnable(unittest.TestCase):
    """A name in `READERS` that nothing runs is eligible and then refused."""

    def test_the_reader_is_listed(self) -> None:
        self.assertIn("agy-json", sd_review.READERS)

    def test_the_reader_carries_its_material_in_the_prompt(self) -> None:
        """`agy` reviews what it is handed; it does not resolve the subject."""
        self.assertIn("agy-json", sd_review.MATERIAL_READERS)

    def test_provider_argv_routes_to_the_agy_builder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workdir = pathlib.Path(raw)
            argv = sd_review.provider_argv(provider(), REPO_ROOT, workdir)
            self.assertEqual(argv, sd_review.agy_argv(workdir, "agy", "gemini-3.1-pro-high"))
            self.assertEqual(argv[0], "agy")


class TheArgvIsConfined(unittest.TestCase):
    """What the spawned session may reach, pinned flag by flag."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.workdir = pathlib.Path(self.dir.name)
        self.argv = sd_review.agy_argv(self.workdir, "agy", "gemini-3.1-pro-high")

    def test_it_sandboxes_and_refuses_slash_expansion(self) -> None:
        for flag in ("--sandbox", "--disable-slash-commands"):
            self.assertIn(flag, self.argv)

    def test_the_workspace_is_the_review_workdir(self) -> None:
        self.assertEqual(self.argv[self.argv.index("--add-dir") + 1], str(self.workdir))

    def test_it_never_skips_permissions(self) -> None:
        self.assertNotIn("--dangerously-skip-permissions", self.argv)
        self.assertNotIn("accept-edits", self.argv)

    def test_it_asks_for_the_declared_schema_as_json(self) -> None:
        self.assertEqual(self.argv[self.argv.index("--output-format") + 1], "json")
        schema = json.loads(self.argv[self.argv.index("--json-schema") + 1])
        self.assertEqual(schema, sd_review.CODEX_OUTPUT_SCHEMA)

    def test_the_prompt_is_attached_to_the_flag(self) -> None:
        """A separate word is read as the prompt by `agy`, whatever it is."""
        prompts = [word for word in self.argv if word.startswith("--print=")]
        self.assertEqual(len(prompts), 1, self.argv)
        self.assertIn(str(self.workdir / "review-subject.md"), prompts[0])

    def test_the_model_comes_from_the_entry(self) -> None:
        self.assertEqual(self.argv[self.argv.index("--model") + 1], "gemini-3.1-pro-high")
        self.assertNotIn("--model", sd_review.agy_argv(self.workdir, "agy", None))


class TheEnvelopeIsReadBack(unittest.TestCase):
    """The observed shape, and every malformed one that must not crash."""

    def answer(self, stdout: str, exit_code: int = 0) -> tuple[object, object]:
        return sd_review.agy_answer(sd_review.Completed(exit_code, stdout, ""))

    def test_a_successful_envelope_yields_its_findings(self) -> None:
        finding = {"path": "src.py", "line": 1, "severity": "high",
                   "summary": "defect", "family": "correctness"}
        result, parsed = self.answer(json.dumps(
            {"conversation_id": "x", "status": "SUCCESS", "response": "{}",
             "structured_output": {"findings": [finding]},
             "usage": {"total_tokens": 1}}))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(parsed.findings[0]["summary"], "defect")

    def test_an_error_envelope_is_nonzero_even_at_exit_zero(self) -> None:
        result, parsed = self.answer(json.dumps(
            {"conversation_id": "", "status": "ERROR", "response": "",
             "error": "invalid model selection"}))
        self.assertEqual(result.exit_code, 1)
        self.assertIn("invalid model selection", result.stderr)
        self.assertIsNone(parsed)

    def test_malformed_envelopes_do_not_crash(self) -> None:
        for stdout in ("", "not json", "[]", "null", '"text"', "{}",
                       '{"status": 7}', '{"status": "SUCCESS"}',
                       '{"status": "SUCCESS", "structured_output": []}',
                       '{"status": "ERROR", "error": null}',
                       '{"status": "SUCCESS", "structured_output": {"findings": "no"}}'):
            with self.subTest(stdout=stdout):
                result, parsed = self.answer(stdout)
                self.assertNotEqual((result, parsed), (None, None))

    def test_a_denied_tool_run_is_not_read_as_a_clean_review(self) -> None:
        """Observed: `agy` reports SUCCESS when a tool was auto-denied.

        The response is empty and no schema key is written, so reading
        `status` alone would turn a session that did nothing into a clean bill.
        """
        result, parsed = self.answer(json.dumps(
            {"conversation_id": "x", "status": "SUCCESS", "response": "",
             "denied_actions": [{"action": "write_file", "display_name": "WriteToFile"}],
             "usage": {"total_tokens": 1}}))
        self.assertEqual(result.exit_code, 0)
        self.assertIsNone(parsed)

    def test_an_oversized_response_becomes_a_blocker(self) -> None:
        _result, parsed = self.answer("x" * (sd_review.MAX_OUTPUT_BYTES + 1))
        self.assertEqual(parsed.error, "response exceeds the declared byte limit")


class TheVendorMustMatchTheModel(unittest.TestCase):
    """The defeat this guard exists for, at both of the places it can arrive."""

    def read(self, text: str) -> object:
        """Both readers, because a machine with a database uses the other one.

        `read` answers through `sd_db.registry` where the library is present
        and `read_file` never does, so checking one would leave the entry
        refused on half the machines.
        """
        path, outcomes = written(text), []
        for reader in (sd_registry.read_file, sd_registry.read):
            try:
                outcomes.append(reader(path))
            except sd_registry.RegistryError as error:
                outcomes.append(error)
        refused = [isinstance(one, sd_registry.RegistryError) for one in outcomes]
        self.assertEqual(refused[0], refused[1], outcomes)
        if isinstance(outcomes[0], sd_registry.RegistryError):
            raise outcomes[0]
        return outcomes[0]

    def test_a_matching_entry_reads(self) -> None:
        registry = self.read(registry_text())
        self.assertEqual(registry.providers["agy"].reader, "agy-json")

    def test_a_model_of_another_vendor_is_refused_at_parse_time(self) -> None:
        with self.assertRaises(sd_registry.RegistryError) as caught:
            self.read(registry_text(model="claude-opus-4-6-thinking"))
        message = str(caught.exception)
        self.assertIn("claude-opus-4-6-thinking", message)
        self.assertIn("anthropic", message)
        self.assertIn("independent", message)

    def test_a_model_hidden_in_the_start_line_is_refused_too(self) -> None:
        """A start line is argv: `--model` written there selects a model."""
        with self.assertRaises(sd_registry.RegistryError) as caught:
            self.read(registry_text(start="agy --model claude-sonnet-4-6"))
        self.assertIn("claude-sonnet-4-6", str(caught.exception))

    def test_an_entry_pinning_no_model_is_refused(self) -> None:
        """The defeat reached by omitting a key rather than by lying in one.

        `agy` picks its own default when no `--model` is given, and that
        default is configuration this registry cannot read. An operator who
        repoints it at an Anthropic model turns a `vendor: google` entry into
        an Anthropic reviewer, with the guard still reporting independence.
        """
        with self.assertRaises(sd_registry.RegistryError) as caught:
            self.read(registry_text(model=None))
        message = str(caught.exception)
        self.assertIn("pins no model", message)
        self.assertIn("independent", message)
        self.assertIn("cannot read", message)

    def test_a_start_line_model_satisfies_the_requirement(self) -> None:
        """`declared_models` reads both, so either place pins the entry."""
        registry = self.read(registry_text(model=None, start="agy --model gemini-3.1-pro-high"))
        self.assertIsNone(registry.providers["agy"].model)

    def test_the_requirement_is_keyed_on_the_reader_not_on_every_entry(self) -> None:
        """`claude -p` pins no model in the shipped registry and must not have to."""
        registry = self.read(registry_text(vendor="anthropic", model=None, reader="claude-json"))
        self.assertIsNone(registry.providers["agy"].model)
        self.assertNotIn("claude-json", sd_registry.MULTIVENDOR_READERS)

    def test_the_chain_refuses_a_missing_model_where_no_file_was_parsed(self) -> None:
        candidate = sd_registry._reviewer_candidate(
            provider(model=None), consent={}, author_vendors=(),
            capped_bills={}, readers=sd_review.READERS)
        self.assertFalse(candidate.eligible)
        self.assertIn("pins no model", candidate.reason)

    def test_an_unfamiliar_model_name_draws_no_conclusion(self) -> None:
        registry = self.read(registry_text(vendor="moonshot", model="kimi-k3"))
        self.assertEqual(registry.providers["agy"].model, "kimi-k3")

    def test_the_shipped_registry_still_reads(self) -> None:
        shipped = sd_registry.read(sd_registry.shipped_path(REPO_ROOT))
        self.assertTrue(shipped.providers)

    def test_the_chain_refuses_it_where_no_file_was_parsed(self) -> None:
        """`_adapt` builds providers from `sd_db` rows without `_provider`."""
        candidate = sd_registry._reviewer_candidate(
            provider(model="claude-opus-4-6-thinking"), consent={},
            author_vendors=(), capped_bills={}, readers=sd_review.READERS)
        self.assertFalse(candidate.eligible)
        self.assertIn("anthropic", candidate.reason)

    def test_a_matching_entry_is_not_refused_by_the_same_check(self) -> None:
        self.assertIsNone(
            sd_registry.refuse_vendor_model("agy", "google", "gemini-3.1-pro-high", "agy", "agy-json"))


class TheBillCannotBeCapped(unittest.TestCase):
    """A spawned command has no call to reserve, so a cap would enforce nothing."""

    def test_a_capped_bill_refuses_the_entry(self) -> None:
        text = registry_text().replace("free: { cost: local }", "free: { cost: company, cap_usd_month: 50 }")
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.read(written(text))
        self.assertIn("nothing enforces", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
