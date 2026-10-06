"""Review acknowledgements in the hub's workflow database (sd:2750).

A satellite read `sd-review-ack.json` in its own git common dir, which the
hub's acknowledgements never reached, so `sd-status` there counted answered
findings as late. Here the hub is a real `sd_db.serve --loopback` over a
scratch database, and the satellite is a second `HOME` whose `hub.json` names
it, so every read and write below crosses the same wire a tailnet satellite
uses. Two clones of one GitHub origin stand for the two machines' checkouts.
Nothing reads the operator's `HOME`, and no test reaches tailscale.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from typing import Any
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sd-543-review-round.json"

sys.path.insert(0, str(BIN))
import sd_lib  # noqa: E402

ack = sd_lib.sibling("sd_review_ack_hub_under_test", "sd-review-ack")
status = sd_lib.sibling("sd_status_hub_under_test", "sd-status")

import sd_db  # noqa: E402 - provisioned into this virtualenv by `make setup`

ROUND = json.loads(FIXTURE.read_text(encoding="utf-8"))["pull_requests"]
#: Eight findings on one pull request, so one can be imported and another written.
PULL = 857
ORIGIN = "https://github.com/example/acks.git"
SLUG = "example/acks"
GIT = ("git", "-c", "user.email=hub@example.invalid", "-c", "user.name=Hub Fixture",
       "-c", "commit.gpgsign=false")


def ids() -> list[str]:
    key = str(PULL)
    return [row["id"] for row in ack.findings(PULL, ROUND[key]["reviews"], ROUND[key]["comments"])]


class HubCase(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = tempfile.TemporaryDirectory()
        self.addCleanup(self.stack.cleanup)
        self.base = pathlib.Path(self.stack.name)
        self.hub_home = self.base / "hub"
        self.hub_home.mkdir()
        sd_db.initialise(home=self.hub_home)
        self.database = sd_db.default_path(self.hub_home)
        with contextlib.closing(sd_db.connect(self.database, write=True)) as connection:
            sd_db.upsert_repo(connection, str(self.base / "hub-clone"), remote=ORIGIN)
        self.satellite_home = self.base / "satellite"
        (self.satellite_home / ".config" / "sd").mkdir(parents=True)
        self.hub_clone = self.clone("hub-clone")
        self.satellite_clone = self.clone("satellite-clone")
        self.addCleanup(ack._forget_hub)

    def clone(self, name: str) -> pathlib.Path:
        root = self.base / name
        root.mkdir()
        for args in (("init", "-q", "--initial-branch=main"), ("remote", "add", "origin", ORIGIN),
                     ("commit", "-q", "--allow-empty", "-m", "landed")):
            subprocess.run([*GIT, *args], cwd=root, check=True, capture_output=True)
        return root

    def serve(self) -> None:
        log = self.base / "serve.log"
        stream = open(log, "w")
        process = subprocess.Popen(
            [sys.executable, "-m", "sd_db.serve", "--loopback", "--port", "0", "--database", str(self.database)],
            stdout=subprocess.DEVNULL, stderr=stream, cwd=self.base,
            env={**os.environ, "HOME": str(self.hub_home)})

        def stop() -> None:
            process.terminate()
            process.wait(timeout=30)
            stream.close()
        self.addCleanup(stop)
        deadline = time.monotonic() + 30
        while not (found := re.search(r"on 127\.0\.0\.1:(\d+)", log.read_text())):
            if process.poll() is not None or time.monotonic() > deadline:
                raise AssertionError(f"serve did not start: {log.read_text()}")
            time.sleep(0.05)
        self.name_hub(int(found.group(1)))

    def name_hub(self, port: int) -> None:
        token = self.database.with_name(self.database.name + ".serve.token")
        (self.satellite_home / ".config" / "sd" / "hub.json").write_text(
            json.dumps({"hub": "127.0.0.1", "port": port, "token_file": str(token)}), encoding="utf-8")

    def run_ack(self, home: pathlib.Path, root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(BIN / "sd-review-ack"), "-C", str(root), "--from", str(FIXTURE),
             "--pr", str(PULL), "--landed-in", "main", *args],
            capture_output=True, text=True, timeout=120, env={**os.environ, "HOME": str(home)})

    def hub_rows(self) -> dict[str, int]:
        """Finding id -> how many revisions the hub's file holds for it."""
        with contextlib.closing(sqlite3.connect(self.database)) as connection:
            found = connection.execute(
                "SELECT key, COUNT(*) FROM state WHERE kind = 'checkpoint' AND key LIKE ? GROUP BY key",
                (f"{ack.ROW_PREFIX}{SLUG}:%",)).fetchall()
        return {key.rsplit(":", 1)[1]: count for key, count in found}

    def unread(self, home: pathlib.Path, root: pathlib.Path) -> list[str]:
        done = self.run_ack(home, root, "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        return [row["id"] for row in json.loads(done.stdout)["unsatisfied"]]


class SatelliteWritesTheHubReads(HubCase):
    def test_an_acknowledgement_made_on_a_satellite_is_read_on_the_hub(self) -> None:
        self.serve()
        first = ids()[0]
        done = self.run_ack(self.satellite_home, self.satellite_clone, "--ack", first, "--dismiss", "out of scope")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.hub_rows(), {first: 1})
        self.assertFalse(ack.store_path(self.satellite_clone).exists(), "the satellite wrote its own file")
        self.assertNotIn(first, self.unread(self.hub_home, self.hub_clone))
        self.assertNotIn(first, self.unread(self.satellite_home, self.satellite_clone))

    def test_the_file_is_read_until_imported_and_imported_once(self) -> None:
        self.serve()
        legacy, written = ids()[:2]
        ack.write_store(self.satellite_clone, {legacy: {"pr": PULL, "disposition": "dismissed", "reason": "old"}})
        self.assertNotIn(legacy, self.unread(self.satellite_home, self.satellite_clone))
        self.assertIn(legacy, self.unread(self.hub_home, self.hub_clone))
        for _ in range(2):
            done = self.run_ack(self.satellite_home, self.satellite_clone, "--ack", written, "--dismiss", "why")
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.hub_rows(), {legacy: 1, written: 2})
        self.assertNotIn(legacy, self.unread(self.hub_home, self.hub_clone))

    def test_an_unregistered_repository_keeps_the_file(self) -> None:
        subprocess.run([*GIT, "remote", "set-url", "origin", "https://github.com/example/other.git"],
                       cwd=self.hub_clone, check=True)
        done = self.run_ack(self.hub_home, self.hub_clone, "--ack", ids()[0], "--dismiss", "why")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.hub_rows(), {})
        self.assertTrue(ack.store_path(self.hub_clone).exists())


class AFailureIsNeverSilent(HubCase):
    """Review round 1 (sd:2750): a failed write or read reads as a failure, never as a skip or a zero."""

    def in_home(self, home: pathlib.Path) -> Any:
        patcher = mock.patch.dict(os.environ, {"HOME": str(home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        module = sd_lib.sibling("sd_review_ack", "sd-review-ack")
        module._forget_hub()
        self.addCleanup(module._forget_hub)
        return module

    def test_a_hub_failure_mid_write_refuses_rather_than_skips(self) -> None:
        from sd_db import remote, ship

        self.in_home(self.hub_home)
        with mock.patch.object(ship, "save", side_effect=remote.HubUnreachable("127.0.0.1", 1, "reset")):
            with self.assertRaisesRegex(ack.UsageError, "not recorded: HubUnreachable"):
                ack._hub_save(SLUG, {"aa11": {"pr": PULL}}, replace=False)
        self.assertEqual(self.hub_rows(), {})

    def test_a_row_another_writer_recorded_first_is_skipped(self) -> None:
        from sd_db import ship

        self.in_home(self.hub_home)
        real = ship.save

        def racing(connection: Any, key: str, previous: int, value: dict) -> int:
            real(connection, key, previous, {**value, "row": {"pr": PULL, "by": "the other writer"}})
            return real(connection, key, previous, value)
        with mock.patch.object(ship, "save", side_effect=racing):
            self.assertEqual(ack._hub_save(SLUG, {"aa11": {"pr": PULL}}, replace=False), [])
        self.assertEqual(self.hub_rows(), {"aa11": 1})

    def test_a_record_that_fails_after_answering_registration_reads_unknown_not_late(self) -> None:
        """The `repo` read answers and the `state` read does not, inside one report."""
        from sd_db import database

        self.in_home(self.hub_home)
        real = database.connect

        class Failing:
            def __init__(self, inner: Any) -> None:
                self.inner = inner

            def execute(self, sql: str, *args: Any) -> Any:
                if "FROM state" in sql:
                    raise sqlite3.OperationalError("disk I/O error")
                return self.inner.execute(sql, *args)

            def close(self) -> None:
                self.inner.close()

        merged = {"repo": SLUG, "pull_requests": [{
            "number": PULL, "title": "t", "merged_at": "2026-10-04T12:00:00Z",
            "review_findings": {"ids": ids()}, "head_oid": "", "merge_oid": ""}]}
        unchecked: dict[str, str] = {}
        with mock.patch.object(database, "connect", lambda *args, **kwargs: Failing(real(*args, **kwargs))):
            late = status.late_reviews(self.hub_clone, merged, status.datetime.date(2026, 10, 5))
            rows = status._merged_review_rows(self.hub_clone, merged, status.datetime.date(2026, 10, 5), unchecked)
        self.assertIsNone(late["findings"])
        self.assertIn("unknown (workflow database unreadable: OperationalError", late["unchecked"])
        self.assertEqual(rows, [])
        self.assertIn("unknown (workflow database unreadable", unchecked["merged-pr-review-unacknowledged"])


class TheHubDoesNotAnswer(HubCase):
    def setUp(self) -> None:
        super().setUp()
        import socket

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.name_hub(port)

    def test_a_write_refuses_and_writes_nothing(self) -> None:
        done = self.run_ack(self.satellite_home, self.satellite_clone, "--ack", ids()[0], "--dismiss", "why")
        self.assertEqual(done.returncode, 2)
        self.assertIn("not recorded: acknowledgements unknown (hub unreachable", done.stderr)
        self.assertFalse(ack.store_path(self.satellite_clone).exists())

    def test_sd_status_reports_unknown_and_counts_nothing_late(self) -> None:
        merged = {"repo": SLUG, "pull_requests": [{
            "number": PULL, "title": "t", "merged_at": "2026-10-04T12:00:00Z",
            "review_findings": {"ids": ids()}, "head_oid": "", "merge_oid": ""}]}
        with mock.patch.dict(os.environ, {"HOME": str(self.satellite_home)}):
            module = sd_lib.sibling("sd_review_ack", "sd-review-ack")
            self.addCleanup(module._forget_hub)
            late = status.late_reviews(self.satellite_clone, merged, status.datetime.date(2026, 10, 5))
            unchecked: dict[str, str] = {}
            rows = status._merged_review_rows(self.satellite_clone, merged, status.datetime.date(2026, 10, 5),
                                              unchecked)
        self.assertIsNone(late["findings"])
        self.assertIn("unknown (hub unreachable", late["unchecked"])
        self.assertEqual(rows, [])
        self.assertIn("unknown (hub unreachable", unchecked["merged-pr-review-unacknowledged"])
        lines: list[str] = []
        status._render_unread("late", late, "merged in the last 14 days are unread", lines.append)
        self.assertEqual(lines, [f"  late: {late['unchecked']}\n"])


if __name__ == "__main__":
    unittest.main()
