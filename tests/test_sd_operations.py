"""CLI boundary checks use a fake service and never execute launchctl."""

import argparse
import importlib
import io
import json
import os
import sqlite3
import sys
import tempfile
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

    def test_assignments_build_queues_every_item_on_a_write_connection(self):
        """pack sd:6093: the Build press from the CLI, the items as `sd:N` or bare."""
        queue = Mock(return_value=[{"id": 31, "item": 7, "status": "queued"}, {"id": 32, "item": 9, "status": "queued"}])
        builds = types.ModuleType("sd_db.build")
        builds.queue = queue
        with patch.dict(sys.modules, {"sd_db.build": builds}), patch.object(sd_db, "build", builds, create=True):
            code, output = self.call("assignments", "build", "sd:7", "9")
            with self.assertRaises(cli.WorkRefusal):
                queue.side_effect = sd_db.SdDbError("item 9 is planning; a build takes a ready item")
                self.call("assignments", "build", "9")
        self.assertEqual(code, 0)
        self.assertEqual(output.splitlines(), ["#31  queued  build  sd:7", "#32  queued  build  sd:9"])
        self.assertEqual(queue.call_args_list[0].args[1:], ([7, 9],))
        self.assertEqual(queue.call_args_list[0].kwargs, {"who": "operator"})
        self.connect.assert_called_with(sd_db, write=True)
        self.assertEqual(self.connection.close.call_count, 2)

    def builds(self):
        """`sd_db.build` and `sd_db.build_run` fakes; `dispatch` answers an empty tick."""
        build, run = types.ModuleType("sd_db.build"), types.ModuleType("sd_db.build_run")
        run.dispatch = Mock(return_value={"reaped": [], "moved": [], "claimed": ["r1"], "spawned": ["r1"], "why": ""})
        run.now = Mock(return_value="2026-10-25T09:00:00+00:00")
        run.paths = types.SimpleNamespace(key=lambda value: value, expand=Path)
        run.Tools = lambda **tools: types.SimpleNamespace(**tools)
        for patcher in (patch.dict(sys.modules, {"sd_db.build": build, "sd_db.build_run": run}),
                        patch.object(sd_db, "build", build, create=True),
                        patch.object(sd_db, "build_run", run, create=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        return run

    def test_assignments_dispatch_reads_the_load_and_the_log_folder_before_the_tick(self):
        """pack sd:6094: an unread load is None, never room; an unset bulk root is a reason for no claim."""
        run = self.builds()
        with patch.object(cli, "gate_load", return_value=(None, None)), \
                patch.object(cli, "interactive_builders", return_value=[]), \
                patch.object(cli, "log_root", return_value=None):
            code, output = self.call("assignments", "dispatch")
        self.assertEqual(code, 0)
        kwargs = run.dispatch.call_args.kwargs
        self.assertEqual((kwargs["load"], kwargs["load_cap"], kwargs["interactive"]), (None, None, []))
        self.assertIn("bulk_storage_root is unset", kwargs["why"])
        self.assertIn("claimed 1, spawned 1", output)
        self.connect.assert_called_with(sd_db, write=True)
        self.connection.close.assert_called_once()

    def test_a_spawn_runs_the_supervise_verb_the_real_parser_reads(self):
        """Review round 1: the spawned argv is `sd`'s own `assignments supervise RUN`, parsed by the real parser."""
        run = self.builds()
        sys.modules["sd_db.build"].run = Mock(return_value={"repo": "/repo"})
        run.spawn, run.log_dir = Mock(), lambda root, repo: root
        run.dispatch.side_effect = lambda connection, **kwargs: (kwargs["spawn"]("r1"), {
            "reaped": [], "moved": [], "claimed": [], "spawned": ["r1"], "why": ""})[1]
        with patch.object(cli, "gate_load", return_value=(1.0, 0.0)), \
                patch.object(cli, "interactive_builders", return_value=[]), \
                patch.object(cli, "log_root", return_value=Path("/bulk")):
            self.call("assignments", "dispatch")
        argv = run.spawn.call_args.args[0]
        self.assertEqual(Path(argv[1]), ROOT / "bin" / "sd")
        arguments = self.parser.parse_args(argv[2:])
        self.assertEqual((arguments.handler, arguments.run), (cli.supervise_build, "r1"))
        self.assertEqual(run.spawn.call_args.kwargs["log"], Path("/bulk/r1.supervisor.log"))

    def test_interactive_builders_count_as_the_dashboard_counts_them(self):
        """Review round 1: one entry per slot the dashboard's own `claude_sessions.builders` counts."""
        with patch.object(sys, "path", [str(ROOT / "dashboard"), *sys.path]):
            sessions_module = importlib.import_module("sd_dashboard.claude_sessions")
        def session(ident, status, builder, agents, cwd="/repos/a/src"):
            return {"id": ident, "name": ident, "cwd": cwd, "status": status, "builder": builder, "age": 5,
                    "safe": {"state": "yes", "why": []},
                    "agents": [{"name": f"{ident}-{n}", "builder": kind, "state": state, "age": 5}
                               for n, (kind, state) in enumerate(agents)]}
        listed = [session("s1", "busy", True, [(True, "running"), (False, "running"), (True, "stalled")]),
                  session("s2", "idle", True, [(True, "running")], cwd="/elsewhere"),
                  session("s3", "waiting", True, []), session("s4", "unknown", False, [(True, "unknown")])]
        document = {"sessions": listed, "builders": sessions_module.builders(listed, "")}
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE repo (path TEXT)")
        connection.execute("INSERT INTO repo VALUES ('/repos/a')")
        with patch.object(sessions_module, "document", return_value=document):
            found = cli.interactive_builders(connection, "2026-10-25T09:00:00+00:00", lambda path: path)
        self.assertEqual(len(found), document["builders"]["running"])
        self.assertEqual([row["repo"] for row in found if row["session_id"] == "s1"], ["/repos/a"] * 3)

    def test_the_log_folder_is_the_real_bulk_storage_setting(self):
        """Review round 1: `log_root` reads `sd.bulk_storage_root` through `sd_lib`; a malformed one claims nothing."""
        sd_lib = importlib.import_module("sd_lib")
        with tempfile.TemporaryDirectory() as home:
            config = Path(home) / sd_lib.CONFIG_RELATIVE_PATH
            config.parent.mkdir(parents=True)
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": home}):
                config.write_text(json.dumps({"config": {"sd": {"bulk_storage_root": home}}}))
                self.assertEqual(cli.log_root(), Path(home))
                config.write_text(json.dumps({"config": {"sd": {"bulk_storage_root": "relative/path"}}}))
                run = self.builds()
                with patch.object(cli, "gate_load", return_value=(1.0, 0.0)), \
                        patch.object(cli, "interactive_builders", return_value=[]):
                    code, _ = self.call("assignments", "dispatch")
        self.assertEqual(code, 0)
        self.assertIn("sd.bulk_storage_root", run.dispatch.call_args.kwargs["why"])

    def test_gate_load_reads_the_real_gate_status(self):
        """Review round 1: the real `sd gate status --json`, on a machine with no gate settings: load off is 0."""
        with tempfile.TemporaryDirectory() as home:
            environ = {key: value for key, value in os.environ.items() if not key.startswith("SD_GATE")}
            with patch.dict("os.environ", {**environ, "HOME": home, "XDG_CONFIG_HOME": home, "XDG_STATE_HOME": home},
                            clear=True):
                load, cap = cli.gate_load()
        self.assertIsInstance(load, float)
        self.assertEqual(cap, 0.0, "the gate's default load rule is off, which `build.room` reads as no cap")

    def test_gate_load_is_unread_on_any_odd_answer(self):
        answers = [("", 1), ("{}", 0), (json.dumps({"load": [1, float("nan"), 1], "load_max": 40}), 0),
                   (json.dumps({"load": [1.0, 2.5, 3.0], "load_max": 40}), 0)]
        found = []
        for stdout, code in answers:
            with patch.object(cli.subprocess, "run", return_value=Mock(stdout=stdout, returncode=code)):
                found.append(cli.gate_load())
        self.assertEqual(found, [(None, None), (None, None), (None, None), (2.5, 40.0)])

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
