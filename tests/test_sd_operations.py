"""CLI boundary checks use a fake service and never execute launchctl."""

import argparse
import importlib
import io
import json
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import sd_db

ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(ROOT / "bin"), *sys.path]):
    cli = importlib.import_module("sd_operations")


class OperationsCLI(unittest.TestCase):
    def setUp(self):
        self.parser = argparse.ArgumentParser()
        cli.register(self.parser.add_subparsers(required=True))
        self.connection = Mock()
        self.service = types.ModuleType("sd_db.operations")
        for name in ("inventory", "job_state", "assignment_state", "retry_job", "cancel_job", "cancel_assignment"):
            setattr(self.service, name, Mock())
        self.service.job_state.return_value = {"name": "daily", "state": "failed", "revision": "fresh"}
        self.service.assignment_state.return_value = {"id": 8, "status": "queued", "revision": "fresh"}
        self.service.retry_job.return_value = {"request": {"status": "accepted"}, "job": {"state": "failed"}}
        self.service.cancel_job.return_value = {"request": {"status": "accepted"}, "job": {"state": "running"}}
        self.service.cancel_assignment.return_value = {"id": 8, "status": "cancelled"}
        self.launchd = types.ModuleType("sd_db.services")
        for name in ("inventory", "service_state", "start_service", "stop_service", "restart_service"):
            setattr(self.launchd, name, Mock())
        self.launchd.service_state.return_value = {
            "id": "user:com.example.server", "label": "com.example.server",
            "state": "running", "revision": "current-service"}
        self.connect = Mock(return_value=self.connection)
        for patcher in (patch.dict(sys.modules, {"sd_db.operations": self.service, "sd_db.services": self.launchd}),
                        patch.object(sd_db, "operations", self.service, create=True),
                        patch.object(sd_db, "services", self.launchd, create=True),
                        patch.object(cli.sd_handoff_rows, "library", return_value=sd_db),
                        patch.object(cli.sd_handoff_rows, "connect", self.connect),
                        patch.object(cli.getpass, "getuser", return_value="operator")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, *argv):
        arguments = self.parser.parse_args(argv)
        output = io.StringIO()
        with redirect_stdout(output):
            code = arguments.handler(arguments)
        return code, output.getvalue()

    def test_read_inventory_uses_read_only_connection(self):
        self.service.inventory.return_value = {"jobs": [], "assignments": []}
        code, output = self.call("jobs", "list", "--json")
        self.assertEqual((code, json.loads(output)), (0, []))
        self.connect.assert_called_once_with(sd_db, write=False)
        self.connection.close.assert_called_once()

    def test_explicit_revision_is_preserved_for_backend_stale_check(self):
        self.service.retry_job.side_effect = sd_db.SdDbError("state changed")
        with self.assertRaisesRegex(cli.WorkRefusal, "state changed"):
            self.call("jobs", "retry", "daily", "--if-revision", "inspected", "--json")
        self.service.retry_job.assert_called_once_with(
            self.connection, "daily", expected_revision="inspected", who="operator")
        self.connect.assert_called_once_with(sd_db, write=True)
        self.connection.close.assert_called_once()

    def test_default_revision_uses_current_snapshot_and_accepted_does_not_mean_running(self):
        code, output = self.call("jobs", "retry", "daily", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["job"]["state"], "failed")
        self.service.retry_job.assert_called_once_with(
            self.connection, "daily", expected_revision="fresh", who="operator")

    def test_failed_and_unknown_requests_exit_one_and_keep_observed_state(self):
        for status in ("failed", "unknown"):
            self.service.cancel_job.return_value = {"request": {"status": status}, "job": {"state": "running"}}
            code, output = self.call("jobs", "cancel", "daily", "--json")
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output)["job"]["state"], "running")

    def test_assignment_cancel_uses_integer_identity_and_shared_revision(self):
        code, output = self.call("assignments", "cancel", "8", "--json")
        self.assertEqual((code, json.loads(output)["status"]), (0, "cancelled"))
        self.service.cancel_assignment.assert_called_once_with(
            self.connection, 8, expected_revision="fresh", who="operator")

    def test_invalid_assignment_identity_refuses_and_closes_connection(self):
        with self.assertRaises(cli.WorkRefusal):
            self.call("assignments", "get", "not-an-id", "--json")
        self.service.assignment_state.assert_not_called()
        self.connection.close.assert_called_once()

    def test_services_inventory_is_read_only_and_preserves_scope(self):
        self.launchd.inventory.return_value = {"services": [
            {"id": "system:com.example.server", "state": "running"},
            {"id": "user:com.example.server", "state": "unloaded"}]}
        code, output = self.call("services", "list")
        self.assertEqual(code, 0)
        self.assertIn("system:com.example.server  running", output)
        self.assertIn("user:com.example.server  unloaded", output)
        self.connect.assert_called_once_with(sd_db, write=False)
        self.service.inventory.assert_not_called()

    def test_service_get_preserves_system_identity(self):
        self.call("services", "get", "system:com.example.server", "--json")
        self.launchd.service_state.assert_called_once_with(self.connection, "system:com.example.server")
        self.connect.assert_called_once_with(sd_db, write=False)

    def test_service_restart_preserves_revision_and_observed_state(self):
        self.launchd.restart_service.return_value = {
            "request": {"status": "accepted", "phase": "loaded"},
            "service": {"state": "idle"}}
        code, output = self.call("services", "restart", "com.example.server",
                                 "--if-revision", "inspected", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["service"]["state"], "idle")
        self.launchd.restart_service.assert_called_once_with(
            self.connection, "com.example.server", expected_revision="inspected", who="operator")
        self.connect.assert_called_once_with(sd_db, write=True)

    def test_service_unknown_outcome_exits_one_and_keeps_phase(self):
        self.launchd.stop_service.return_value = {
            "request": {"status": "unknown", "phase": "bootout"}, "service": {"state": "unknown"}}
        code, output = self.call("services", "stop", "com.example.server", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)["request"]["phase"], "bootout")
        self.launchd.stop_service.assert_called_once_with(
            self.connection, "com.example.server", expected_revision="current-service", who="operator")

    def test_service_refusal_closes_connection_without_another_action(self):
        self.launchd.start_service.side_effect = sd_db.SdDbError("service changed")
        with self.assertRaisesRegex(cli.WorkRefusal, "service changed"):
            self.call("services", "start", "com.example.server", "--if-revision", "old")
        self.launchd.stop_service.assert_not_called()
        self.launchd.restart_service.assert_not_called()
        self.connection.close.assert_called_once()

    def test_parser_excludes_unsupported_actions_and_client_paths(self):
        for arguments in (("assignments", "retry", "8"),
                          ("jobs", "retry", "daily", "--database", "/tmp/sd.db"),
                          ("jobs", "get", "daily", "--repo", "/tmp/repo"),
                          ("services", "restart", "com.example.server", "--command", "arbitrary"),
                          ("services", "enable", "com.example.server"),
                          ("jobs", "cancel")):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    self.parser.parse_args(arguments)
                self.assertEqual(error.exception.code, 2)
        self.connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
