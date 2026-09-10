"""Contribution CLI delegates durable state and validation to the shared core."""

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sd_db

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import sd_work  # noqa: E402


def parser():
    result = argparse.ArgumentParser()
    groups = result.add_subparsers(dest="group", required=True)
    store = groups.add_parser("store").add_subparsers(dest="verb", required=True)
    sd_work.register(groups, store)
    return result


class ContributionAdapter(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        self.file = self.home / "changes.json"
        self.changes = {"pull_url": "https://github.com/example/project/pull/7"}
        self.file.write_text(json.dumps(self.changes))
        self.connection = mock.Mock()
        self.core = mock.Mock()
        self.core.capture.return_value = {"item": {"id": 42}, "revision": "item-revision"}
        self.core.configure.return_value = self.core.capture.return_value
        self.row = {"key": "item:42", "lane": "awaiting_you", "title": "Upstream fix",
                    "local_status": "planning", "external_state": "open", "freshness": "current",
                    "event_ids": ["review:7"], "reasons": ["changes requested"]}
        self.core.projection.return_value = [self.row]
        self.state = {"key": "item:42", "revision": "checkpoint-revision", "observation": {},
                      "attention": {"events": ["review:7"]}, "notifications": {}}
        self.core.snapshot.return_value = self.state
        self.core.acknowledge.return_value = {**self.state, "revision": "ack-revision"}
        for target, value in [("_contribution_library", (sd_db, self.core))]:
            patch = mock.patch.object(sd_work, target, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(sd_work.sd_handoff_rows, "connect", return_value=self.connection)
        self.connect = patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(sd_work.getpass, "getuser", return_value="operator")
        patch.start()
        self.addCleanup(patch.stop)

    def call(self, *arguments):
        args = parser().parse_args(["task", "contribution", *map(str, arguments)])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(args.handler(args), 0)
        return output.getvalue()

    def test_add_and_edit_delegate_exact_typed_payload_and_item_revision(self):
        self.call("add", "Upstream fix", "--file", self.file, "--json")
        self.core.capture.assert_called_once_with(
            self.connection, title="Upstream fix", changes=self.changes, who="operator")
        self.call("edit", 42, "--file", self.file, "--if-revision", "old-item", "--json")
        self.core.configure.assert_called_once_with(
            self.connection, 42, self.changes, who="operator", expected_revision="old-item")
        self.assertEqual(self.connect.call_args_list, [mock.call(sd_db, write=True)] * 2)
        self.assertEqual(self.connection.close.call_count, 2)

    def test_list_and_show_preserve_core_projection_and_open_readonly(self):
        self.assertEqual(json.loads(self.call("list", "--json")), [self.row])
        shown = json.loads(self.call("show", "item:42", "--json"))
        self.assertEqual(shown, {**self.state, "contribution": self.row})
        self.core.snapshot.assert_called_once_with(self.connection, "item:42")
        self.assertEqual(self.connect.call_args_list, [mock.call(sd_db, write=False)] * 2)
        text = self.call("show", "item:42")
        for value in ("awaiting_you", "Upstream fix", "review:7", "checkpoint-revision"):
            self.assertIn(value, text)
        self.assertIn("evidence_verified: false", text)

    def test_ack_requires_explicit_events_and_checkpoint_revision(self):
        self.call("ack", "item:42", "--event", "review:7", "--event", "comment:8",
                  "--if-revision", "checkpoint-revision", "--json")
        self.core.acknowledge.assert_called_once_with(
            self.connection, "item:42", ["review:7", "comment:8"], who="operator",
            expected_revision="checkpoint-revision")
        for arguments in (["ack", "item:42", "--event", "review:7"],
                          ["ack", "item:42", "--if-revision", "rev"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    self.call(*arguments)
                self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.core.acknowledge.call_count, 1)

    def test_show_joins_registered_item_and_separate_pull_attention_source(self):
        url_key = "github:https://github.com/example/project/pull/7"
        self.row.update({"item_id": 42, "attention_sources": [
            {"key": url_key, "revision": "pull-revision", "event_ids": ["review:7"]}]})
        self.core.snapshot.return_value = {**self.state, "key": url_key, "revision": "pull-revision"}
        shown = json.loads(self.call("show", url_key, "--json"))
        self.assertEqual(shown["contribution"], self.row)
        self.assertEqual(shown["revision"], "pull-revision")
        self.row["key"] = url_key
        self.core.snapshot.return_value = self.state
        self.assertEqual(json.loads(self.call("show", "item:42", "--json"))["contribution"], self.row)

    def test_empty_projection_is_visible_without_writing(self):
        self.core.projection.return_value = []
        self.assertEqual(self.call("list"), "No contributions.\n")
        self.connect.assert_called_once_with(sd_db, write=False)

    def test_invalid_json_refuses_before_database_or_shared_validation(self):
        invalid = [b"[]", b"{", b"{\"pull_url\":1,\"pull_url\":2}", b"{\"x\":NaN}",
                   b"{\"x\":Infinity}", b"\xff", b" " * 65537, b"[" * 1500]
        for raw in invalid:
            with self.subTest(raw=raw[:30]):
                self.file.write_bytes(raw)
                with self.assertRaises(sd_work.WorkRefusal):
                    self.call("add", "Bad input", "--file", self.file, "--json")
        self.connect.assert_not_called()
        self.core.capture.assert_not_called()

    def test_file_boundary_refuses_missing_directory_and_fifo_without_waiting(self):
        fifo = self.home / "fifo"
        os.mkfifo(fifo)
        for path in (self.home / "missing", self.home, fifo):
            with self.subTest(path=path), self.assertRaises(sd_work.WorkRefusal):
                self.call("edit", 42, "--file", path, "--json")
        self.connect.assert_not_called()

    def test_json_limit_and_stored_argv_are_data_only(self):
        marker = self.home / "must-not-exist"
        changes = {"evidence": [{"argv": ["touch", str(marker)]}]}
        raw = json.dumps(changes).encode()
        self.file.write_bytes(raw + b" " * (65536 - len(raw)))
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("must not execute")):
            self.call("edit", 42, "--file", self.file, "--json")
        self.assertEqual(self.core.configure.call_args.args[2], changes)
        self.assertFalse(marker.exists())

    def test_core_refusal_closes_connection_and_does_not_retry(self):
        self.core.configure.side_effect = sd_db.SdDbError("stale item revision")
        with self.assertRaisesRegex(sd_work.WorkRefusal, "stale item revision"):
            self.call("edit", 42, "--file", self.file, "--json")
        self.core.configure.assert_called_once()
        self.connection.close.assert_called_once()


class ContributionStoreCLI(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        sd_db.initialise(home=self.home)
        self.environment = {**os.environ, "HOME": str(self.home),
                            "XDG_CONFIG_HOME": str(self.home / "config"),
                            "XDG_DATA_HOME": str(self.home / "data")}
        self.file = self.home / "changes.json"

    def call(self, *arguments, code=0):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bin/sd"), "task", "contribution", *map(str, arguments)],
            cwd=self.home, env=self.environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_local_registration_filing_preserves_identity_and_stale_edit_refuses(self):
        clone = self.home / "clone"
        clone.mkdir()
        for arguments in (["init", "-b", "contribution"], ["config", "user.name", "Fixture"],
                          ["config", "user.email", "fixture@example.invalid"]):
            subprocess.run(["git", "-C", str(clone), *arguments], check=True, capture_output=True)
        (clone / "source.txt").write_text("source\n")
        subprocess.run(["git", "-C", str(clone), "add", "source.txt"], check=True)
        subprocess.run(["git", "-C", str(clone), "commit", "-m", "fixture"],
                       check=True, capture_output=True)
        head = subprocess.check_output(["git", "-C", str(clone), "rev-parse", "HEAD"], text=True).strip()
        evidence = self.home / "tests.log"
        evidence.write_text("fixture result\n")
        marker = self.home / "not-executed"
        changes = {"local_clone": str(clone), "local_branch": "contribution", "tested_commit": head,
                   "evidence": [{"argv": ["touch", str(marker)], "cwd": str(clone), "exit_code": 0,
                                 "commit": head, "artifact": str(evidence),
                                 "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}],
                   "blocked_on": "Waiting for a release", "depends_on": []}
        self.file.write_text(json.dumps(changes))
        added = json.loads(self.call("add", "Unfiled contribution", "--file", self.file, "--json").stdout)
        item = added["item"]["id"]
        rows = json.loads(self.call("list", "--json").stdout)
        self.assertEqual([row["item_id"] for row in rows], [item])
        self.assertEqual(rows[0]["local_branch"], "contribution")
        pull = "https://github.com/example/project/pull/7"
        self.file.write_text(json.dumps({"pull_url": pull}))
        filed = json.loads(self.call("edit", item, "--file", self.file,
                                    "--if-revision", added["revision"], "--json").stdout)
        self.assertEqual(filed["item"]["id"], item)
        shown = json.loads(self.call("show", f"item:{item}", "--json").stdout)
        self.assertEqual(shown["contribution"]["url"], pull)
        self.assertEqual(shown["contribution"]["evidence"], changes["evidence"])
        self.call("edit", item, "--file", self.file, "--if-revision", added["revision"], code=1)
        self.assertEqual(json.loads(self.call("show", f"item:{item}", "--json").stdout), shown)
        self.assertFalse(marker.exists())

    def test_acknowledgement_uses_actual_event_and_refuses_stale_checkpoint(self):
        from sd_db import contributions

        pull = "https://github.com/example/project/pull/7"
        key = f"github:{pull}"
        self.file.write_text(json.dumps({"pull_url": pull}))
        added = json.loads(self.call("add", "Filed contribution", "--file", self.file, "--json").stdout)
        observation = {
            "complete": True, "observed_at": "2026-09-09T01:00:00+00:00",
            "operator": {"id": "1", "login": "operator"},
            "author": {"id": "1", "login": "operator"}, "repo": "example/project",
            "title": "Filed contribution", "state": "open", "head": "a" * 40, "base": "b" * 40,
            "draft": False, "mergeable": "mergeable", "ci": "success", "ci_head": "a" * 40,
            "ci_ids": ["check-run:10"], "why": ["author"], "blocking_labels": [],
            "reviews": [], "events": [],
        }
        with sd_db.connect(sd_db.default_path(self.home)) as connection:
            before = contributions.snapshot(connection, key)
            baseline = contributions.observe_pull(connection, pull, observation,
                                                  expected_revision=before["revision"])
            observation["observed_at"] = "2026-09-09T02:00:00+00:00"
            observation["reviews"] = [{"id": "review:77", "actor_id": "2", "state": "CHANGES_REQUESTED",
                                       "at": "2026-09-09T01:30:00+00:00"}]
            contributions.observe_pull(connection, pull, observation, expected_revision=baseline["revision"])
        shown = json.loads(self.call("show", key, "--json").stdout)
        row = shown["contribution"]
        self.assertEqual(row["item_id"], added["item"]["id"])
        self.assertTrue(row["needs_you"])
        source = next(source for source in row["attention_sources"] if source["key"] == key)
        self.assertTrue(source["event_ids"])
        arguments = ["ack", key, "--if-revision", shown["revision"], "--json"]
        for event in source["event_ids"]:
            arguments.extend(["--event", event])
        acknowledged = json.loads(self.call(*arguments).stdout)
        self.assertFalse(acknowledged["contribution"]["needs_you"])
        self.assertEqual(acknowledged["contribution"]["local_status"], "planning")
        self.call(*arguments, code=1)
        self.assertEqual(json.loads(self.call("show", key, "--json").stdout), acknowledged)


if __name__ == "__main__":
    unittest.main()
