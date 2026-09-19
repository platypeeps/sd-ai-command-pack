"""sd:788 slice 4: the minimax meter is read at review start, its two
percents written as `meter` rows, and a bill whose window reads zero, whose
reading is missing or stale, or whose answer is unusable is passed over by
fallthrough and refused by name on a direct pick.

The reader is a seam like `client`: every case hands `review` a recorder that
answers with the one recorded `tests/fixtures/minimax/token_plan_remains.json`,
edited in memory, or raises. No test reaches a network, and the key the
registry names is a fixture variable, never the operator's.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any
from unittest import mock

from sd_db import connect
from sd_db.meter import sample

from tests.test_sd_registry import RECORDED_METER
from tests.test_sd_review import FakeClient, namespace, sd_review
from tests.test_sd_review_ledger import LedgerFixture, usage_answer

PINNED = "https://www.minimax.io/v1/token_plan/remains"
STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00"
#: A `plan` bill carrying the meter and its key variable, one `url` entry on
#: it with the price and `max_tokens` a capped base needs, and an uncapped
#: entry beside it so the fallthrough has somewhere to go.
REGISTRY = f"""\
bills:
  fixture: {{ cost: subscription }}
  plan:    {{ cost: plan, meter: "{PINNED}", meter_env: FAKE_METER_KEY }}
providers:
  metered: {{ url: "https://metered.example.test/v1", model: fixture, vendor: meteredvendor, bill: plan,
              roles: [reviewer], max_tokens: 1000, price: {{ in: 0, out: 0 }}, env: [REMOTE_KEY] }}
  free:    {{ url: "https://free.example.test/v1", model: fixture, vendor: freevendor, bill: fixture,
              roles: [reviewer], env: [REMOTE_KEY] }}
roles:
  author: []
  reviewer: [metered, free]
"""


def recorded(**changes: Any) -> str:
    """The recording, with `general`'s fields changed."""
    answer = json.loads(RECORDED_METER.read_text(encoding="utf-8"))
    general = next(entry for entry in answer["model_remains"] if entry["model_name"] == "general")
    general.update(changes)
    return json.dumps(answer)


class FakeMeter:
    """The reader seam, recording what it was asked and answering once."""

    def __init__(self, answer: Any = None) -> None:
        self.answer = answer if answer is not None else (0, recorded(), "", True, 200)
        self.read: list[dict[str, Any]] = []

    def __call__(self, bill: Any, environ: Any, timeout: int) -> Any:
        self.read.append({"bill": bill.name, "meter": bill.meter, "key": environ.get(bill.meter_env), "timeout": timeout})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class MeterFixture(LedgerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.registry_path.write_text(REGISTRY, encoding="utf-8")
        (self.root / "CLAUDE.local.md").write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\n"
            "reviewers: metered@metered.example.test, free@free.example.test\n"
            "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")
        self.seed()
        self.reader = FakeMeter()

    def review(self, client: FakeClient | None = None, **options: Any) -> dict[str, Any]:  # type: ignore[override]
        """Through the default seam: `review` reaches `sd_registry.meter_reading`
        by name, and the fixture stands in for it."""
        with mock.patch.object(sd_review.sd_registry, "meter_reading", self.reader):
            return sd_review.review(self.root, namespace(**options), self.runner,
                                    self.environment(REMOTE_KEY="fixture", FAKE_METER_KEY="fixture-meter"),
                                    client=client or FakeClient(default=usage_answer()))

    def meter_rows(self) -> list[tuple[Any, ...]]:
        connection = connect(self.database, write=False)
        try:
            return [tuple(row) for row in connection.execute(
                "SELECT provider, bill, window_minutes, used_percent FROM cost WHERE source = 'meter' ORDER BY id")]
        finally:
            connection.close()

    def seed_reading(self, used_percent: float, hours_ago: float = 0) -> None:
        moment = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours_ago)).isoformat(timespec="seconds")
        connection = connect(self.database)
        try:
            for window in (300, 10080):
                sample(connection, provider="metered", window_minutes=window, used_percent=used_percent, now=moment)
        finally:
            connection.close()

    def assert_passed_over_and_refused(self, line: str | re.Pattern[str]) -> dict[str, Any]:
        """Both roads on one line: fallthrough marks `metered` with it and
        goes to `free`; `--provider metered` raises it and sends nothing. A
        pattern stands for a line carrying the stamp of a row this run wrote."""
        def matches(found: str, prefix: str = "") -> None:
            if isinstance(line, str):
                self.assertEqual(found, prefix + line)
            else:
                self.assertRegex(found, "^" + re.escape(prefix) + line.pattern)

        client = FakeClient(default=usage_answer())
        result = self.review(client)
        self.assertEqual(result["reviewed_by"], ["free"])
        self.assertEqual(list(result["capped_bills"]), ["plan"])
        matches(result["capped_bills"]["plan"])
        reasons = {row["provider"]: row["reason"] for row in result["chain"] if not row["eligible"]}
        self.assertEqual(list(reasons), ["metered"])
        matches(reasons["metered"], "metered is billed to plan: ")
        picked = FakeClient(default=usage_answer())
        with self.assertRaises(sd_review.sd_registry.ConsentRefusal) as caught:
            self.review(picked, provider="metered")
        matches(str(caught.exception), "metered is billed to plan: ")
        self.assertEqual(picked.sent, [])
        return result


class TheReading(MeterFixture):
    def test_the_recorded_answer_writes_two_meter_rows_per_entry_and_the_bill_dispatches(self) -> None:
        client = FakeClient(default=usage_answer())
        result = self.review(client)
        self.assertEqual(result["reviewed_by"], ["metered"])
        self.assertEqual(self.reader.read, [{"bill": "plan", "meter": PINNED, "key": "fixture-meter",
                                             "timeout": sd_review.METER_TIMEOUT_SECONDS}])
        self.assertEqual(self.meter_rows(), [("metered", "plan", 300, 0.0), ("metered", "plan", 10080, 0.0)])
        self.assertEqual((result["capped_bills"], result["meter_faults"]), ({}, {}))

    def test_a_zero_five_hour_window_is_passed_over_and_refused_by_name(self) -> None:
        self.reader = FakeMeter((0, recorded(current_interval_remaining_percent=0), "", True, 200))
        self.assert_passed_over_and_refused(re.compile(r"plan's five-hour window reads 0 percent remaining \(read at " + STAMP + r"\)$"))
        self.assertEqual([row[2:] for row in self.meter_rows()][:2], [(300, 100.0), (10080, 0.0)])

    def test_a_zero_weekly_window_is_passed_over_and_refused_by_name(self) -> None:
        self.reader = FakeMeter((0, recorded(current_weekly_remaining_percent=0), "", True, 200))
        self.assert_passed_over_and_refused(re.compile(r"plan's weekly window reads 0 percent remaining \(read at " + STAMP + r"\)$"))
        self.assertEqual([row[2:] for row in self.meter_rows()][:2], [(300, 0.0), (10080, 100.0)])

    def test_a_fresh_answer_is_written_before_classification(self) -> None:
        self.seed_reading(100)
        client = FakeClient(default=usage_answer())
        result = self.review(client)
        self.assertEqual(result["reviewed_by"], ["metered"])
        self.assertEqual([row[3] for row in self.meter_rows()], [100.0, 100.0, 0.0, 0.0])

    def with_second_entry(self, enabled: bool) -> None:
        """A second entry on the bill, before the rows are seeded: the
        `provider` row carries the enabled state once the database exists."""
        self.registry_path.write_text(REGISTRY.replace(
            "roles:\n", f'  second:  {{ url: "https://second.example.test/v1", model: fixture, vendor: v2, bill: plan,\n'
                         f'              roles: [reviewer], max_tokens: 1000, price: {{ in: 0, out: 0 }}, env: [REMOTE_KEY],\n'
                         f'              enabled: {str(enabled).lower()}, reason: "a fixture" }}\nroles:\n')
            .replace("reviewer: [metered, free]", "reviewer: [metered, second, free]"), encoding="utf-8")
        self.database.unlink()
        self.seed()

    def test_the_rows_name_every_enabled_entry_on_the_bill(self) -> None:
        self.with_second_entry(enabled=True)
        self.review()
        self.assertEqual(sorted(row[0] for row in self.meter_rows()), ["metered", "metered", "second", "second"])

    def test_the_rows_skip_a_disabled_entry_on_the_bill(self) -> None:
        self.with_second_entry(enabled=False)
        self.review()
        self.assertEqual([row[0] for row in self.meter_rows()], ["metered", "metered"])

    def test_the_reader_is_a_seam_on_review(self) -> None:
        reader = FakeMeter()
        result = sd_review.review(self.root, namespace(), self.runner,
                                  self.environment(REMOTE_KEY="fixture", FAKE_METER_KEY="fixture-meter"),
                                  client=FakeClient(default=usage_answer()), meter=reader)
        self.assertEqual((result["reviewed_by"], len(reader.read)), (["metered"], 1))


class TheMeterSelection(MeterFixture):
    def set_registry(self, text: str) -> None:
        self.registry_path.write_text(text, encoding="utf-8")
        self.database.unlink()
        self.seed()

    def test_an_unranked_provider_does_not_trigger_a_meter_request(self) -> None:
        self.set_registry(REGISTRY.replace("reviewer: [metered, free]", "reviewer: [free]"))
        result = self.review()
        self.assertEqual(result["reviewed_by"], ["free"])
        self.assertEqual((self.reader.read, self.meter_rows()), ([], []))
        self.assertEqual((result["capped_bills"], result["meter_faults"]), ({}, {}))

    def test_an_explicit_unranked_provider_still_reads_its_meter(self) -> None:
        self.set_registry(REGISTRY.replace("reviewer: [metered, free]", "reviewer: [free]"))
        result = self.review(provider="metered")
        self.assertEqual(result["reviewed_by"], ["metered"])
        self.assertEqual([row["bill"] for row in self.reader.read], ["plan"])
        self.assertEqual(len(self.meter_rows()), 2)

    def test_an_explicit_pick_does_not_meter_another_ranked_provider(self) -> None:
        result = self.review(provider="free")
        self.assertEqual(result["reviewed_by"], ["free"])
        self.assertEqual((self.reader.read, self.meter_rows()), ([], []))

    def test_a_provider_without_consent_does_not_trigger_a_meter_request(self) -> None:
        local = self.root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace("metered@metered.example.test, ", ""))
        result = self.review()
        self.assertEqual(result["reviewed_by"], ["free"])
        with self.assertRaises(sd_review.sd_registry.ConsentRefusal):
            self.review(provider="metered")
        self.assertEqual((self.reader.read, self.meter_rows()), ([], []))

    def test_an_author_provider_does_not_trigger_a_meter_request(self) -> None:
        with mock.patch.object(sd_review, "author_vendors", return_value=("meteredvendor",)):
            result = self.review()
            self.assertEqual(result["reviewed_by"], ["free"])
            with self.assertRaises(sd_review.sd_registry.ConsentRefusal):
                self.review(provider="metered")
        self.assertEqual((self.reader.read, self.meter_rows()), ([], []))

    def test_an_unsupported_reader_does_not_trigger_a_meter_request(self) -> None:
        self.set_registry(REGISTRY.replace("cost: plan,", "cost: subscription,").replace(
            'url: "https://metered.example.test/v1", model: fixture,',
            'start: "fixture-cli", reader: unknown-reader,',
        ))
        result = self.review()
        self.assertEqual(result["reviewed_by"], ["free"])
        with self.assertRaises(sd_review.sd_registry.ConsentRefusal):
            self.review(provider="metered")
        self.assertEqual((self.reader.read, self.meter_rows()), ([], []))

    def test_a_disabled_provider_does_not_trigger_a_meter_request(self) -> None:
        self.set_registry(REGISTRY.replace(
            "vendor: meteredvendor, bill: plan,", 'vendor: meteredvendor, bill: plan, enabled: false, reason: "fixture",',
        ))
        result = self.review()
        self.assertEqual(result["reviewed_by"], ["free"])
        self.assertEqual((self.reader.read, self.meter_rows()), ([], []))

    def test_zero_review_depth_does_not_trigger_a_meter_request(self) -> None:
        with mock.patch.object(sd_review, "review_depth", return_value=0):
            self.review()
        self.assertEqual((self.reader.read, self.meter_rows()), ([], []))


class TheMissingAndTheStale(MeterFixture):
    def test_no_reading_caps_naming_the_missing_reading(self) -> None:
        self.reader = FakeMeter(OSError("connection refused"))
        result = self.assert_passed_over_and_refused("no meter reading for plan")
        self.assertEqual(result["meter_faults"], {"plan": "the meter reading for plan failed and nothing was written: connection refused"})
        self.assertEqual(self.meter_rows(), [])

    def test_a_stale_reading_caps_naming_its_age(self) -> None:
        self.seed_reading(0, hours_ago=6)
        self.reader = FakeMeter(OSError("connection refused"))
        result = self.review()
        line = result["capped_bills"]["plan"]
        self.assertRegex(line, r"^plan's newest reading is 36[01] minutes old, older than its five-hour window$")
        self.assert_passed_over_and_refused(line)

    def test_a_failed_get_writes_nothing_names_the_failure_and_reads_the_prior_rows(self) -> None:
        self.seed_reading(40)
        self.reader = FakeMeter((1, "", "the meter of bill 'plan': timed out", False, None))
        client = FakeClient(default=usage_answer())
        result = self.review(client)
        self.assertEqual(result["reviewed_by"], ["metered"])
        self.assertEqual(result["meter_faults"], {"plan": "the meter reading for plan failed and nothing was written: the meter of bill 'plan': timed out"})
        self.assertEqual(result["capped_bills"], {})
        self.assertEqual([row[3] for row in self.meter_rows()], [40.0, 40.0])

    def test_an_http_error_is_a_failed_get(self) -> None:
        self.seed_reading(100)
        self.reader = FakeMeter((401, "{}", "HTTP 401 from the meter of bill 'plan'", True, 401))
        result = self.assert_passed_over_and_refused(re.compile(r"plan's five-hour window reads 0 percent remaining \(read at " + STAMP + r"\)$"))
        self.assertIn("HTTP 401", result["meter_faults"]["plan"])
        self.assertEqual(len(self.meter_rows()), 2)


class TheUnusable(MeterFixture):
    def test_a_malformed_answer_caps_and_writes_no_row(self) -> None:
        self.reader = FakeMeter((0, recorded(model_name="video"), "", True, 200))
        result = self.assert_passed_over_and_refused("plan's meter answer was not written: model_remains carries 0 'general' entries, not one")
        self.assertEqual((self.meter_rows(), result["meter_faults"]), ([], {}))
        self.reader = FakeMeter((0, recorded(current_weekly_remaining_percent="50"), "", True, 200))
        self.assert_passed_over_and_refused("plan's meter answer was not written: current_weekly_remaining_percent is '50', not a number from 0 to 100")
        self.assertEqual(self.meter_rows(), [])

    def test_meter_without_meter_env_caps_naming_the_missing_field_and_sends_nothing(self) -> None:
        self.registry_path.write_text(REGISTRY.replace(", meter_env: FAKE_METER_KEY", ""), encoding="utf-8")
        self.assert_passed_over_and_refused(f"bill 'plan' carries meter: and no meter_env:, so no variable names the key "
                                            f"the reading sends; add meter_env beside meter in {self.registry_path}")
        self.assertEqual(self.reader.read, [])

    def test_a_meter_off_the_pin_caps_and_sends_nothing(self) -> None:
        self.registry_path.write_text(REGISTRY.replace(PINNED, "http://www.minimax.io/v1/token_plan/remains"), encoding="utf-8")
        result = self.review()
        self.assertIn("whose scheme is not the pinned meter's", result["capped_bills"]["plan"])
        self.assertEqual(self.reader.read, [])

    def test_no_value_for_the_key_caps_and_sends_nothing(self) -> None:
        with mock.patch.object(sd_review.sd_registry, "meter_reading", self.reader):
            result = sd_review.review(self.root, namespace(), self.runner, self.environment(REMOTE_KEY="fixture"),
                                      client=FakeClient(default=usage_answer()))
        self.assertEqual(result["capped_bills"], {"plan": "bill 'plan' has no value for FAKE_METER_KEY in this environment"})
        self.assertEqual(self.reader.read, [])

    def test_a_ledger_fault_caps_the_metered_bill_naming_the_fault(self) -> None:
        """On a `subscription` bill, so `capped_bills` lists nothing and the
        line can only be the meter step's own."""
        self.registry_path.write_text(REGISTRY.replace("cost: plan,", "cost: subscription,"), encoding="utf-8")
        self.database.unlink()
        self.seed()
        absent = sd_review.sd_lib.Imported(None, "sd_db is not installed in this virtualenv", "")
        with mock.patch.object(sd_review.sd_lib, "import_sd_db", return_value=absent):
            result = self.review()
        self.assertIn("no library to hold the reservation", result["ledger_fault"])
        self.assertEqual(result["capped_bills"], {"plan": result["ledger_fault"]})
        self.assertEqual((result["reviewed_by"], self.reader.read), (["free"], []))


class TheDryRuns(MeterFixture):
    def test_explain_and_dry_run_send_nothing_and_classify_on_the_rows(self) -> None:
        self.seed_reading(100)
        for option in ("explain", "dry_run"):
            with self.subTest(option=option):
                client = FakeClient(default=usage_answer())
                result = self.review(client, **{option: True})
                self.assertEqual(self.reader.read, [])
                self.assertEqual(client.sent, [])
                self.assertIn("plan's five-hour window reads 0 percent remaining", result["capped_bills"]["plan"])
                self.assertEqual(result["meter_faults"], {})
        self.assertEqual(len(self.meter_rows()), 2)
