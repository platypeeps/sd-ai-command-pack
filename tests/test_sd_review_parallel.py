"""sd:7519. Every reviewing tier asks two readers, at once, and Claude's gets the ranked prompt.

The registry orders the readers; a tier's depth says how many must answer. The
first `depth` start together, a slot whose reader failed goes to the next one,
and the receipt keeps the registry's order whatever order the answers came in.
"""

from __future__ import annotations

import json
import os
import pathlib
import signal
import subprocess
import sys
import textwrap
import threading
import time
from typing import Any

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review

#: How long a fake reader waits for its partner before it calls the run serial.
PARTNER_SECONDS = 5

THREE_READERS = """
bills:
  first:  { cost: subscription }
  second: { cost: subscription }
  third:  { cost: subscription }
  fourth: { cost: subscription }

providers:
  codex:  { start: "codex exec", vendor: openai, bill: first, roles: [reviewer], reader: codex-json, env: [] }
  second: { start: "second exec", vendor: secondvendor, bill: second, roles: [reviewer], reader: codex-json, env: [] }
  third:  { start: "third exec", vendor: thirdvendor, bill: third, roles: [reviewer], reader: codex-json, env: [] }
  fourth: { start: "fourth exec", vendor: fourthvendor, bill: fourth, roles: [reviewer], reader: codex-json, env: [] }

roles:
  author: []
  reviewer: [codex, second, third, fourth]
"""

CLAUDE_AND_CODEX = """
bills:
  first:  { cost: subscription }
  second: { cost: subscription }

providers:
  codex:  { start: "codex exec", vendor: openai, bill: first, roles: [reviewer], reader: codex-json, env: [] }
  claude: { start: "claude exec", vendor: anthropic, bill: second, roles: [reviewer], reader: claude-json, env: [] }

roles:
  author: []
  reviewer: [codex, claude]
"""

CLEAN = sd_review.Completed(0, '{"findings": []}', "")
FAILED = sd_review.Completed(1, "", "runtime failed")
CLAUDE_CLEAN = sd_review.Completed(0, json.dumps({"type": "result", "subtype": "success",
                                                  "structured_output": {"findings": []}}), "")


def review_session(argv: Any) -> bool:
    """A review session, not the codex skill probe or its version read."""
    return list(argv[1:3]) != ["debug", "prompt-input"] and list(argv[1:]) != ["--version"]


class ParallelFixture(ReviewFixture):
    def prepare(self, registry: str | None = None, consent: str | None = None) -> pathlib.Path:
        if registry is not None:
            (self.registry_home / ".local/share/sd/providers.yaml").write_text(registry, encoding="utf-8")
        root = self.make_repo()
        if consent is not None:
            (root / "CLAUDE.local.md").write_text(
                "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\n"
                f"{sd_review.sd_lib.CONSENT_KEY}: {consent}\n"
                "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n", encoding="utf-8")
        (root / "src.py").write_text("the_review_subject = 123\n", encoding="utf-8")
        self.stub_policy({"default_tier": "standard"})
        return root

    def review(self, root: pathlib.Path, runner: Any, **options: Any) -> dict[str, Any]:
        return sd_review.review(root, namespace(**options), runner, self.environment(), self.chatgpt_home())


class TwoReadersAtOnce(ParallelFixture):
    def test_every_reviewing_tier_asks_two_readers(self) -> None:
        for tier in ("cheap", "standard", "deep"):
            with self.subTest(tier=tier):
                self.assertEqual(sd_review.sd_route.TIER_DEPTH[tier], 2)
        self.assertEqual(sd_review.sd_route.TIER_DEPTH["skip"], 0)

    def test_a_lensed_brief_that_routes_to_skip_still_asks_two_readers(self) -> None:
        root = self.prepare()
        (root / "src.py").unlink()
        (root / "brief.md").write_text("# A brief\n", encoding="utf-8")
        for options in ({"lens": "research-brief"}, {"challenge": True}):
            with self.subTest(options=options):
                planned = self.review(root, FakeRunner(), explain=True, **options)
                self.assertEqual(planned["route"]["tier"], "skip")
                self.assertEqual(planned["requested_reviews"], 2)
                self.assertEqual(planned["providers"], ["codex", "second"])

    def test_the_two_readers_run_at_the_same_time(self) -> None:
        root = self.prepare()
        barrier = threading.Barrier(2, timeout=PARTNER_SECONDS)

        def meets_its_partner(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            if not review_session(argv):
                return sd_review.Completed(0, "[]", "")
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                return sd_review.Completed(1, "", "the other reader never ran beside this one")
            return CLEAN

        runner = FakeRunner({"codex": meets_its_partner, "second": meets_its_partner})
        result = self.review(root, runner)
        self.assertEqual((result["requested_reviews"], result["completed_reviews"]), (2, 2), result["outcomes"])
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["reviewed_by"], ["codex", "second"])

    def test_a_failed_slot_goes_to_the_next_reader_while_the_other_still_runs(self) -> None:
        root = self.prepare(THREE_READERS, "codex@codex, second@second, third@third, fourth@fourth")
        third_started = threading.Event()

        def waits_for_third(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            return CLEAN if third_started.wait(PARTNER_SECONDS) else sd_review.Completed(1, "", "third never ran beside second")

        def third(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            third_started.set()
            return CLEAN

        def codex(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            return FAILED if review_session(argv) else sd_review.Completed(0, "[]", "")

        runner = FakeRunner({"codex": codex, "second": waits_for_third, "third": third})
        result = self.review(root, runner)
        self.assertEqual(result["status"], "clean", result["outcomes"])
        self.assertEqual(result["reviewed_by"], ["second", "third"])
        self.assertEqual([row["backend"] for row in result["outcomes"]], ["codex", "second", "third"])
        self.assertEqual(result["remaining"], [])
        self.assertNotIn("fourth", [pathlib.Path(call["argv"][0]).name for call in runner.calls])

    def test_outcomes_keep_the_registry_order_whatever_finishes_first(self) -> None:
        root = self.prepare()
        second_answered = threading.Event()

        def codex(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            if review_session(argv):
                second_answered.wait(PARTNER_SECONDS)
                time.sleep(0.05)
            return CLEAN if review_session(argv) else sd_review.Completed(0, "[]", "")

        def second(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            second_answered.set()
            return CLEAN

        result = self.review(root, FakeRunner({"codex": codex, "second": second}))
        self.assertEqual([row["backend"] for row in result["outcomes"]], ["codex", "second"])
        self.assertEqual(result["reviewed_by"], ["codex", "second"])

    def test_two_failures_leave_the_review_incomplete_and_name_both(self) -> None:
        root = self.prepare()

        def fails(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            return FAILED if review_session(argv) else sd_review.Completed(0, "[]", "")

        result = self.review(root, FakeRunner({"codex": fails, "second": fails}))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual((result["requested_reviews"], result["completed_reviews"]), (2, 0))
        self.assertEqual(result["remaining"], ["codex", "second"])


class ClaudeGetsTheRankedPrompt(ParallelFixture):
    def test_only_the_claude_reader_is_asked_to_trace_and_rank(self) -> None:
        root = self.prepare(CLAUDE_AND_CODEX, "codex@codex, claude@claude")
        read: list[str] = []

        def claude(argv: Any, env: Any, cwd: Any, timeout: int) -> Any:
            subject = pathlib.Path(argv[-1].split(" ", 2)[1])
            read.append(subject.read_text(encoding="utf-8"))
            return CLAUDE_CLEAN

        runner = FakeRunner({"claude": claude})
        for name in ("claude", "codex"):
            result = self.review(root, runner, provider=name)
            self.assertEqual(result["reviewed_by"], [name], result["outcomes"])
        sessions = [call for call in runner.calls if call["argv"][0] == "codex" and review_session(call["argv"])]
        self.assertEqual(len(read), 1)
        self.assertEqual(len(sessions), 1)
        for phrase in ("trace each changed function to its callers", "Rank findings by likely production impact"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, read[0])
                self.assertNotIn(phrase, sessions[0]["stdin"])


DRIVER = textwrap.dedent("""
    import pathlib, sys
    sys.path.insert(0, sys.argv[1])
    from tests.test_sd_review import sd_review
    out = pathlib.Path(sys.argv[2])
    child = "import os, pathlib, sys, time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(120)"
    def run_one(name):
        return sd_review.subprocess_runner([sys.executable, "-c", child, str(out / name)], {}, out, 300)
    sd_review.sd_lib.fill_slots(["a", "b"], 2, run_one, lambda answer: True, sd_review.READER_GROUPS)
""")


class ATermEndsBothReaders(ParallelFixture):
    def test_a_sigterm_to_the_review_ends_every_reader_group(self) -> None:
        """Only the main thread hears SIGTERM (`sd_lib.term_ends_group`); the readers run in threads."""
        out = self.tmp / "groups"
        out.mkdir()
        driver = subprocess.Popen([sys.executable, "-c", DRIVER, str(pathlib.Path(__file__).resolve().parents[1]), str(out)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(driver.kill)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not all((out / name).is_file() and (out / name).read_text() for name in "ab"):
            time.sleep(0.05)
        pids = [int((out / name).read_text()) for name in "ab"]
        for pid in pids:
            self.addCleanup(lambda pid=pid: _quietly_kill(pid))
        driver.send_signal(signal.SIGTERM)
        _out, errors = driver.communicate(timeout=30)
        self.assertEqual(driver.returncode, -signal.SIGTERM, errors)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and any(_alive(pid) for pid in pids):
            time.sleep(0.05)
        self.assertEqual([pid for pid in pids if _alive(pid)], [])


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _quietly_kill(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
