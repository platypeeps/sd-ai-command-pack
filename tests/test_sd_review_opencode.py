"""The `opencode-json` reader: how it is invoked, confined, read back, and
kept independent (sd:1329).

`opencode` is one client in front of every vendor it holds a credential for:
`-m provider/model` picks the model per run, and this machine's copy lists
OpenAI, Anthropic, Moonshot, MiniMax, Baseten and Google among them. So an
entry's `vendor` is a claim about the model rather than about the program,
exactly as for `agy`, and `sd_registry.MULTIVENDOR_READERS` requires the
entry to pin one. The fixtures below are captured from `opencode 1.18.30`
(`opencode run --format json`, 2026-09-22); each is labelled with what
produced it.
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

import sd_opencode  # noqa: E402
import sd_registry  # noqa: E402

from tests.test_sd_review import sd_review  # noqa: E402

SHIPPED = sd_registry.shipped_path(REPO_ROOT)

#: Verbatim from a real run: `opencode run --format json --pure --agent
#: sd-review -m openai/gpt-5.5 'Reply with exactly ... {"findings": []}'`.
#: One event per line; the answer is the whole `text` part, not deltas.
CLEAN_STREAM = "\n".join((
    '{"type":"step_start","timestamp":1790102253601,"sessionID":"ses_f3597732effeNUZHQD02qHERYn",'
    '"part":{"id":"prt_0ca68b01f001z32fsoo7DoAPdD","messageID":"msg_0ca688e86001nRr7dUn5yXBXkZ",'
    '"sessionID":"ses_f3597732effeNUZHQD02qHERYn","snapshot":"3942cedfea53e999bd13d0a27a905957c5e62b1a","type":"step-start"}}',
    '{"type":"text","timestamp":1790102254459,"sessionID":"ses_f3597732effeNUZHQD02qHERYn",'
    '"part":{"id":"prt_0ca68b02000188iqz8NpAYEq3y","messageID":"msg_0ca688e86001nRr7dUn5yXBXkZ",'
    '"sessionID":"ses_f3597732effeNUZHQD02qHERYn","type":"text","text":"{\\"findings\\": []}",'
    '"time":{"start":1790102253600,"end":1790102254456},'
    '"metadata":{"openai":{"itemId":"msg_06a8b808bb42eb03016ab2caed8b9c87d0aae43d3a93736fb0","phase":"final_answer"}}}}',
    '{"type":"step_finish","timestamp":1790102254702,"sessionID":"ses_f3597732effeNUZHQD02qHERYn",'
    '"part":{"id":"prt_0ca68b46c001Moxxhp6UhiqvTO","reason":"stop","snapshot":"3942cedfea53e999bd13d0a27a905957c5e62b1a",'
    '"messageID":"msg_0ca688e86001nRr7dUn5yXBXkZ","sessionID":"ses_f3597732effeNUZHQD02qHERYn","type":"step-finish",'
    '"tokens":{"total":122176,"input":122166,"output":10,"reasoning":0,"cache":{"write":0,"read":0}},"cost":0}}',
))

#: Verbatim shape of the `error` event a run with an unsupported model
#: printed (`-m openai/gpt-5.4-mini` under a ChatGPT credential); the
#: response headers are cut, nothing else is.
ERROR_STREAM = (
    '{"type":"error","timestamp":1790102120244,"sessionID":"ses_f35997149ffeoF77r7ycSv9zZb",'
    '"error":{"name":"APIError","data":{"message":"Bad Request: {\\"detail\\":\\"The \'gpt-5.4-mini\' model '
    'is not supported when using Codex with a ChatGPT account.\\"}","statusCode":400,"isRetryable":false,'
    '"metadata":{"url":"https://api.openai.com/v1/responses"}}}}'
)


def finding_stream(text: str) -> str:
    """The clean stream with the model's answer replaced, fence and all."""
    return CLEAN_STREAM.replace('{\\"findings\\": []}', json.dumps(text)[1:-1])


FINDING = {"findings": [{"path": "bin/x.py", "line": 3, "severity": "high",
                         "summary": "unchecked input", "family": "correctness"}]}


class TheReaderIsRunnable(unittest.TestCase):
    """A name in `READERS` that nothing runs is eligible and then refused."""

    def test_the_reader_is_listed(self) -> None:
        self.assertIn("opencode-json", sd_review.READERS)

    def test_the_reader_carries_its_material_in_the_prompt(self) -> None:
        """`opencode` reviews what it is handed, attached as a file."""
        self.assertIn("opencode-json", sd_review.MATERIAL_READERS)

    def test_the_reader_is_multivendor(self) -> None:
        """One program, every vendor: the entry has to pin a model."""
        self.assertIn("opencode-json", sd_registry.MULTIVENDOR_READERS)

    def test_provider_argv_routes_to_the_opencode_builder(self) -> None:
        provider = sd_registry.Provider(name="opencode", vendor="openai", bill="openai",
                                        start="opencode run", model="openai/gpt-5.5",
                                        reader="opencode-json")
        with tempfile.TemporaryDirectory() as raw:
            workdir = pathlib.Path(raw)
            argv = sd_review.provider_argv(provider, REPO_ROOT, workdir)
            self.assertEqual(argv, sd_opencode.opencode_argv(workdir, "opencode run", "openai/gpt-5.5"))
            self.assertEqual(argv[:2], ["opencode", "run"])


class TheArgvIsConfined(unittest.TestCase):
    """What the spawned session may reach, pinned flag by flag."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.workdir = pathlib.Path(self.dir.name)
        self.argv = sd_opencode.opencode_argv(self.workdir, "opencode run", "openai/gpt-5.5")

    def test_it_asks_for_json_events_and_no_external_plugins(self) -> None:
        self.assertEqual(self.argv[self.argv.index("--format") + 1], "json")
        self.assertIn("--pure", self.argv)

    def test_it_runs_the_private_agent(self) -> None:
        self.assertEqual(self.argv[self.argv.index("--agent") + 1], sd_opencode.AGENT)

    def test_it_never_auto_approves(self) -> None:
        self.assertNotIn("--auto", self.argv)

    def test_the_subject_is_attached_after_the_message(self) -> None:
        """`--file` is an array flag: placed before the message it swallows
        the message as a file name (measured: "File not found: Three tasks")."""
        attached = self.argv.index("--file")
        self.assertEqual(self.argv[attached + 1], str(self.workdir / "review-subject.md"))
        self.assertEqual(attached, len(self.argv) - 2)
        self.assertIn("review-subject.md", self.argv[attached - 1])

    def test_the_model_comes_from_the_entry(self) -> None:
        self.assertEqual(self.argv[self.argv.index("--model") + 1], "openai/gpt-5.5")
        self.assertNotIn("--model", sd_opencode.opencode_argv(self.workdir, "opencode run", None))


class TheEnvironmentCarriesTheAgent(unittest.TestCase):
    """The private agent travels as inline config, and denies every tool
    that writes, runs, fetches or leaves the project."""

    def test_the_agent_denies_writes_and_commands(self) -> None:
        child = sd_opencode.opencode_environment({"PATH": "/usr/bin", "HOME": "/h"})
        self.assertEqual(child["PATH"], "/usr/bin")
        config = json.loads(child["OPENCODE_CONFIG_CONTENT"])
        permission = config["agent"][sd_opencode.AGENT]["permission"]
        for tool in ("edit", "bash", "webfetch", "websearch", "task", "skill", "external_directory"):
            self.assertEqual(permission[tool], "deny", tool)
        for tool in ("read", "glob", "grep"):
            self.assertEqual(permission[tool], "allow", tool)

    def test_the_parent_is_not_mutated(self) -> None:
        parent = {"PATH": "/usr/bin"}
        sd_opencode.opencode_environment(parent)
        self.assertEqual(parent, {"PATH": "/usr/bin"})


class TheStreamIsReadBack(unittest.TestCase):
    def answer(self, stdout: str, exit_code: int = 0):
        result = sd_review.Completed(exit_code, stdout, "")
        return sd_opencode.opencode_answer(result, parse=sd_review.parse_findings,
                                  oversized=sd_review.oversized_findings,
                                  limit=sd_review.MAX_OUTPUT_BYTES)

    def test_a_clean_answer_is_clean(self) -> None:
        result, parsed = self.answer(CLEAN_STREAM)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.findings, ())
        self.assertEqual(parsed.error, "")

    def test_findings_come_out_in_the_codex_shape(self) -> None:
        _result, parsed = self.answer(finding_stream(json.dumps(FINDING)))
        self.assertEqual(parsed.error, "")
        self.assertEqual(len(parsed.findings), 1)
        self.assertEqual(parsed.findings[0]["path"], "bin/x.py")
        self.assertEqual(parsed.findings[0]["line"], 3)
        self.assertEqual(parsed.findings[0]["severity"], "high")

    def test_a_fenced_answer_is_still_read(self) -> None:
        fenced = "```json\n" + json.dumps(FINDING) + "\n```"
        _result, parsed = self.answer(finding_stream(fenced))
        self.assertIsNotNone(parsed)
        self.assertEqual(len(parsed.findings), 1)

    def test_the_last_text_event_is_the_answer(self) -> None:
        """A run that thinks aloud, calls a tool and then answers prints
        more than one `text` part; the final one carries the findings."""
        earlier = CLEAN_STREAM.replace('{\\"findings\\": []}', "Looking at the diff first.")
        _result, parsed = self.answer(earlier + "\n" + finding_stream(json.dumps(FINDING)))
        self.assertEqual(len(parsed.findings), 1)

    def test_an_error_event_refuses_and_names_the_cause(self) -> None:
        result, parsed = self.answer(ERROR_STREAM)
        self.assertIsNone(parsed)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("gpt-5.4-mini", result.stderr)

    def test_no_text_event_is_not_a_clean_review(self) -> None:
        only_steps = "\n".join(line for line in CLEAN_STREAM.splitlines() if '"type":"text"' not in line)
        result, parsed = self.answer(only_steps)
        self.assertIsNone(parsed)
        self.assertNotEqual(result.exit_code, 0)

    def test_prose_is_not_a_clean_review(self) -> None:
        _result, parsed = self.answer(finding_stream("Looks fine to me."))
        self.assertIsNone(parsed)

    def test_an_oversized_stream_is_a_blocker(self) -> None:
        result, parsed = self.answer("x" * (sd_review.MAX_OUTPUT_BYTES + 1))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(parsed.findings[0]["severity"], "high")


class TheShippedEntry(unittest.TestCase):
    """The tracked registry: the entry parses, sits third, and pins a model
    whose vendor it names honestly."""

    def setUp(self) -> None:
        self.registry = sd_registry.read_file(SHIPPED)

    def test_the_entry_parses_with_its_reader(self) -> None:
        entry = self.registry.providers["opencode"]
        self.assertEqual(entry.reader, "opencode-json")
        self.assertEqual(entry.start, "opencode run")
        self.assertIn("reviewer", entry.roles)
        self.assertNotIn("author", entry.roles)

    def test_the_vendor_is_the_pinned_model_s(self) -> None:
        entry = self.registry.providers["opencode"]
        self.assertIsNotNone(entry.model)
        self.assertEqual(sd_registry.model_vendor(entry.model), entry.vendor)
        self.assertEqual(entry.bill, entry.vendor)
        self.assertFalse(self.registry.bills[entry.bill].capped)

    def test_the_reviewer_order_is_codex_claude_opencode(self) -> None:
        self.assertEqual([p.name for p in self.registry.order("reviewer")],
                         ["codex", "claude", "opencode"])

    def test_the_entry_without_a_model_is_refused(self) -> None:
        text = SHIPPED.read_text(encoding="utf-8")
        entry = next(line for line in text.splitlines() if line.startswith("  opencode:"))
        self.assertIn("model:", entry)
        without = text.replace(entry, entry.replace(
            entry[entry.index("model:"):entry.index(",", entry.index("model:")) + 2], ""))
        with self.assertRaises(sd_registry.RegistryError) as caught:
            sd_registry.parse(without, SHIPPED)
        self.assertIn("pins no model", str(caught.exception))


class TheChainReachesOpencode(unittest.TestCase):
    """A claude-authored branch with codex out of the running falls through
    to opencode rather than refusing for want of a reviewer."""

    def setUp(self) -> None:
        self.registry = sd_registry.read_file(SHIPPED)
        self.readers = sd_review.READERS

    def consent(self, *names: str) -> dict:
        return sd_registry.parse_consent(" ".join(
            str(sd_registry.recipient(self.registry.providers[name])) for name in names))

    def eligible(self, **kwargs) -> list[str]:
        return [c.provider.name for c in sd_registry.reviewer_chain(
            self.registry, readers=self.readers, **kwargs) if c.eligible]

    def test_claude_authored_with_codex_unconsented_routes_to_opencode(self) -> None:
        names = self.eligible(consent=self.consent("claude", "opencode"), author_vendors=("anthropic",))
        self.assertEqual(names, ["opencode"])

    def test_claude_authored_with_codex_disabled_routes_to_opencode(self) -> None:
        from dataclasses import replace
        self.registry.providers["codex"] = replace(self.registry.providers["codex"], enabled=False,
                                                   reason="rate limited this hour")
        names = self.eligible(consent=self.consent("codex", "claude", "opencode"),
                              author_vendors=("anthropic",))
        self.assertEqual(names, ["opencode"])

    def test_codex_authored_work_skips_opencode_by_vendor(self) -> None:
        """The shipped pin is an OpenAI model, so the entry is honest about
        being the author's vendor when codex wrote the branch."""
        names = self.eligible(consent=self.consent("codex", "claude", "opencode"),
                              author_vendors=("openai",))
        self.assertEqual(names, ["claude"])
        reasons = {c.provider.name: c.reason for c in sd_registry.reviewer_chain(
            self.registry, readers=self.readers, consent=self.consent("codex", "claude", "opencode"),
            author_vendors=("openai",))}
        self.assertIn("different vendor from the author", reasons["opencode"])


if __name__ == "__main__":
    unittest.main()
