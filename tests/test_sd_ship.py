"""Real bare Git, real CLI children, and a GitHubDouble; no model or GitHub traffic."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from sd_db import connect, create_assignment, create_item, initialise, upsert_repo
from sd_db import ship as receipts
from sd_db.testing.github import GitHubDouble
from sd_db.testing.remote import FixtureRemote, RemoteRefusal, _git

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
loader = importlib.machinery.SourceFileLoader("sd_ship_tested", str(ROOT / "bin/sd-ship"))
spec = importlib.util.spec_from_loader(loader.name, loader)
ship = importlib.util.module_from_spec(spec)
loader.exec_module(ship)


class ShipDouble(GitHubDouble):
    """Adds precisely the write/read surfaces this adapter calls to the shared double."""
    def __init__(self, remote):
        super().__init__(remote)
        self.admin = True
        self.moved = False
        self.lose_merge = False
        self.lose_create = False
        self.no_create_result = False
        self.statuses = []

    def _pull(self, pull):
        head = getattr(pull, "merged_head", None) or pull.head_sha(self.remote)
        return {"number": pull.number, "title": pull.title, "body": pull.body,
                "state": "closed" if pull.state == "MERGED" else pull.state.lower(),
                "merged": pull.state == "MERGED", "draft": pull.draft,
                "html_url": f"https://github.com/{self.remote.slug}/pull/{pull.number}",
                "head": {"ref": pull.head, "sha": head, "repo": {"full_name": self.remote.slug}},
                "base": {"ref": pull.base}, "mergeable": pull.mergeable == "MERGEABLE",
                "mergeable_state": pull.merge_state_status.lower(), "merge_commit_sha": pull.merge_commit_sha}

    def _route(self, method, path, body):
        query = parse_qs(urlsplit(path).query)
        path = urlsplit(path).path
        prefix = f"/repos/{self.remote.slug}"
        if method == "GET" and path == "/user":
            return 200, {"login": "fixture"}
        if method == "GET" and path == prefix:
            code, value = super()._route(method, path, body)
            value["allow_squash_merge"] = True
            value["permissions"]["admin"] = self.admin
            return code, value
        if method == "GET" and path == f"{prefix}/collaborators":
            page = int(query.get("page", [1])[0])
            return 200, self.remote.collaborators[(page - 1) * 100:page * 100]
        if path == f"{prefix}/pulls":
            if method == "POST":
                if self.no_create_result:
                    raise RemoteRefusal(503, "create transport failed")
                pull = self.remote.open_pull_request(body["head"], base=body["base"], title=body["title"], body=body["body"])
                pull.checks = [{"name": "check", "status": "completed", "conclusion": "success",
                                "head_sha": pull.head_sha(self.remote), "app": {"id": 7}}]
                if self.lose_create:
                    raise RemoteRefusal(503, "create response lost")
                return 201, self._pull(pull)
            return 200, [self._pull(pull) for pull in self.remote.pull_requests.values()]
        if path.endswith("/statuses"):
            return 200, self.statuses
        if method == "GET" and path.startswith(f"{prefix}/pulls/"):
            return 200, self._pull(self.remote.pull(int(path.rsplit("/", 1)[1])))
        if method == "PUT" and path.endswith("/merge"):
            number = int(path.split("/")[-2])
            pull = self.remote.pull(number)
            if self.moved:
                self.remote.commit_on(pull.head, "raced\n\nAuthored-with: human", files={"raced.py": "changed\n"})
            pull.merged_head = pull.head_sha(self.remote)
            pull.title = body["commit_title"] + "\n\n" + body["commit_message"]
            commit = self.remote.merge(number, sha=body["sha"], method=body["merge_method"])
            if self.lose_merge:
                raise RemoteRefusal(503, "merge response lost")
            return 200, {"merged": True, "sha": commit}
        return super()._route(method, path, body)

    def _handler(self):
        double = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def serve(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                status, value = double.answer(self.command, self.path, json.loads(raw) if raw else None, "gh")
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = serve
            do_POST = serve
            do_PUT = serve
        return Handler


SHIM = '''#!/usr/bin/env python3
import json,os,sys,urllib.request,urllib.error
args=sys.argv[1:]
assert args[0]=='api',args
path=args[1]
method=args[args.index('--method')+1]
data=sys.stdin.read().encode() if '--input' in args else None
req=urllib.request.Request(os.environ['SHIP_DOUBLE']+'/'+path,data=data,method=method,headers={'Content-Type':'application/json'})
try:
 with urllib.request.urlopen(req) as response: print(response.read().decode())
except urllib.error.HTTPError as error:
 print(error.read().decode(),file=sys.stderr);sys.exit(1)
'''


class ShipCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = pathlib.Path(self.temp.name).resolve()
        self.remote = FixtureRemote(self.directory / "fixture")
        self.remote.protection = {"enforce_admins": {"enabled": True}, "required_pull_request_reviews": {"required_approving_review_count": 0},
                                  "required_status_checks": {"strict": True, "contexts": ["check"], "checks": [{"context": "check", "app_id": 7}]}}
        self.remote.commit_on("topic", "change\n\nAuthored-with: human", files={"src.py": "value = 1\n", "Makefile": "check:\n\t@echo fixture-check-pass\n"})
        self.root = self.directory / "clone"
        subprocess.run(["git", "clone", "-q", str(self.remote.path), str(self.root)], check=True)
        _git(self.root, "checkout", "topic")
        _git(self.root, "config", "user.name", "Fixture")
        _git(self.root, "config", "user.email", "fixture@example.invalid")
        self.remote_url = "https://github.com/fixture/repo.git"
        _git(self.root, "remote", "set-url", "origin", self.remote_url)
        # Real Git resolves the GitHub-looking identity to this fixture's bare
        # remote. The adapter cannot read or mutate an operator repository.
        self.operator = self.directory / "operator"
        subprocess.run(["git", "clone", "-q", str(self.remote.path), str(self.operator)], check=True)
        _git(self.operator, "remote", "set-url", "origin", self.remote_url)
        (self.operator / "operator.txt").write_text("uncommitted operator work")
        self.home = self.directory / "home"
        self.database = self.home / ".local/share/sd/sd.db"
        initialise(self.database)
        self.connection = connect(self.database)
        self.addCleanup(self.connection.close)
        upsert_repo(self.connection, str(self.operator), remote=self.remote_url, status_source="row", merge_policy="auto")
        self.item = create_item(self.connection, kind="work", title="fixture work", status="in_progress", repo=str(self.operator), branch="topic")
        self.double = ShipDouble(self.remote)
        self.double.__enter__()
        self.addCleanup(self.double.close)
        self.programs = self.directory / "programs"
        self.programs.mkdir()
        (self.programs / "gh").write_text(SHIM)
        (self.programs / "gh").chmod(0o755)
        real_git = shutil.which("git")
        transport = self.programs / "git"
        transport.write_text("#!/usr/bin/env python3\nimport os,sys\n"
                             f"binary={real_git!r}\nargs=sys.argv[1:]\n"
                             f"rewrite=['-c', 'url.{self.remote.path}.insteadOf={self.remote_url}']\n"
                             "if any(a in ('fetch','push','ls-remote') for a in args): args=rewrite+args\n"
                             "os.execv(binary,[binary]+args)\n")
        transport.chmod(0o755)
        provider = self.programs / "review-fixture"
        provider.write_text("#!/usr/bin/env python3\nimport json\nprint(json.dumps({'type':'result','subtype':'success','structured_output':{'findings':[]}}))\n")
        provider.chmod(0o755)
        registry = self.database.parent / "providers.yaml"
        registry.write_text(f"""bills:
  fixture: {{ cost: subscription }}
providers:
  reviewer: {{ start: '{provider}', vendor: secondvendor, bill: fixture, roles: [reviewer], reader: claude-json }}
  reviewer2: {{ start: '{provider}', vendor: thirdvendor, bill: fixture, roles: [reviewer], reader: claude-json }}
  author: {{ start: 'unused-author', vendor: firstvendor, bill: fixture, roles: [author], reader: claude-json }}
roles:
  author: [author]
  reviewer: [reviewer, reviewer2]
""")
        import sd_registry
        allowed = ", ".join(str(sd_registry.recipient(sd_registry.read_file(registry).providers[name])) for name in ("reviewer", "reviewer2"))
        local = self.root / "CLAUDE.local.md"
        local.write_text("<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\nmode: full\n"
                         f"reviewers: {allowed}\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")
        with (self.root / ".git/info/exclude").open("a") as stream:
            stream.write("\nCLAUDE.local.md\n")
        self.environment = {**os.environ, "HOME": str(self.home), "SHIP_DOUBLE": self.double.base_url,
                            "PATH": str(self.programs) + os.pathsep + os.environ["PATH"]}
        self.patch = patch.dict(os.environ, self.environment, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def args(self, command="prepare", *extra):
        return ship.parser().parse_args([command, "--item", str(self.item), "--json", *extra])

    def operation(self, command="prepare", *extra):
        return ship.Ship(self.root, self.connection, self.database, self.args(command, *extra))

    def prepare(self, *extra):
        return self.operation("prepare", *extra).prepare()

    def merge(self, *extra):
        return self.operation("merge", "--manual", "--expected-head", _git(self.root, "rev-parse", "HEAD"), *extra).merge()

    def cli(self, command, *extra):
        return subprocess.run([sys.executable, str(ROOT / "bin/sd-ship"), command, "--item", str(self.item), "--json", *extra],
                              cwd=self.root, env=self.environment, text=True, capture_output=True, timeout=30)

    def test_custom_database_controls_ship_receipts_and_the_actual_reviewer(self):
        from sd_db import set_provider_state
        from sd_db.registry import read, seed
        custom = self.directory / "custom.db"
        alternate = sqlite3.connect(custom)
        self.connection.backup(alternate)
        alternate.close()
        connection = connect(custom)
        self.addCleanup(connection.close)
        seed(connection, read(self.database.with_name("providers.yaml")))
        set_provider_state(connection, "reviewer2", enabled=False)
        result = self.cli("prepare", "--database", str(custom))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("1/2 completed", json.loads(result.stdout)["error"])
        key = receipts.receipt_key(self.remote.slug, "topic", self.item)
        self.assertTrue(receipts.read(connection, key)[1]["passes"])
        self.assertEqual(receipts.read(self.connection, key), (0, {}))

    def test_reprepare_preserves_whole_item_acceptance_and_reviewable_description(self):
        acceptance = self.directory / "acceptance.json"
        acceptance.write_text(json.dumps({"item": self.item, "complete": True, "criteria": [
            {"criterion": "actual scope", "passed": True, "evidence": "fixture-check-pass"}]}))
        body = self.directory / "body.md"
        body.write_text("Concrete change, behavior and validation.")
        self.prepare("--deliver", "--acceptance-file", str(acceptance), "--body-file", str(body))
        before = self.operation().state
        _git(self.root, "commit", "--allow-empty", "-m", "verified integration\n\nAuthored-with: human")
        self.prepare()
        after = self.operation().state
        self.assertTrue(after["deliver"])
        self.assertEqual(after["acceptance"], before["acceptance"])
        self.assertEqual(after["body"], before["body"])
        self.assertEqual(len(after["passes"]), 2)

    def test_real_cli_review_prepare_slice_merge_and_repeat_reconcile(self):
        prepared = self.cli("prepare")
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        self.assertEqual(json.loads(prepared.stdout)["phase"], "ready_to_send")
        result = self.merge()
        self.assertEqual(result["phase"], "merged")
        self.assertEqual(self.connection.execute("SELECT status FROM item WHERE id=?", (self.item,)).fetchone()[0], "in_progress")
        self.assertIn("Item: sd:", _git(self.root, "show", "-s", "--format=%B", result["merge_commit"]))
        self.assertNotIn("Delivers:", _git(self.root, "show", "-s", "--format=%B", result["merge_commit"]))
        count = len([call for call in self.remote.calls if call.method == "PUT"])
        self.operation("reconcile").reconcile()
        self.assertEqual(len([call for call in self.remote.calls if call.method == "PUT"]), count)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM note WHERE body LIKE 'Code delivery %'").fetchone()[0], 1)
        self.assertEqual(_git(self.root, "branch", "--show-current"), "topic")
        self.assertTrue(self.root.exists())

    def test_required_ci_failure_missing_wrong_head_or_app_cannot_merge(self):
        self.prepare()
        pull = self.remote.pull(1)
        valid = dict(pull.checks[0])
        for changes in ({"conclusion": "failure"}, {"status": "queued"}, {"head_sha": "0" * 40}, {"app": {"id": 8}}):
            with self.subTest(changes=changes):
                pull.checks = [{**valid, **changes}]
                with self.assertRaises(ship.Refusal):
                    self.merge()
        pull.checks = []
        with self.assertRaisesRegex(ship.Refusal, "no current result"):
            self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_remote_ownership_protection_and_rules_are_fresh(self):
        self.prepare()
        self.double.admin = False
        with self.assertRaisesRegex(ship.Refusal, "administer"):
            self.merge()
        self.double.admin = True
        self.remote.collaborators = [{"login": "fixture", "permissions": {"push": True}}] * 100 + [{"login": "someone", "permissions": {"push": True}}]
        with self.assertRaisesRegex(ship.Refusal, "someone"):
            self.merge()
        self.remote.collaborators = []
        saved = self.remote.protection
        self.remote.protection = None
        with self.assertRaises(ship.Refusal):
            self.merge()
        self.remote.protection = saved
        self.remote.protection["enforce_admins"]["enabled"] = False
        with self.assertRaisesRegex(ship.Refusal, "administrators"):
            self.merge()

    def test_moved_head_at_remote_merge_is_refused_atomically(self):
        self.prepare()
        original = self.remote.rev_parse("main")
        self.double.moved = True
        with self.assertRaisesRegex(ship.Refusal, "not confirmed"):
            self.merge()
        self.assertEqual(self.remote.rev_parse("main"), original)
        self.assertEqual(self.connection.execute("SELECT status FROM item WHERE id=?", (self.item,)).fetchone()[0], "in_progress")

    def test_lost_merge_response_reconciles_without_a_second_merge(self):
        self.prepare()
        self.double.lose_merge = True
        self.assertEqual(self.merge()["phase"], "merged")
        self.assertEqual(self.merge()["phase"], "merged")
        self.assertEqual(len([call for call in self.remote.calls if call.method == "PUT"]), 1)

    def test_empty_search_after_uncertain_create_cannot_duplicate_pr(self):
        self.double.no_create_result = True
        with self.assertRaises(ship.Refusal):
            self.prepare()
        self.double.no_create_result = False
        with self.assertRaisesRegex(ship.Refusal, "empty search"):
            self.prepare()
        self.assertEqual(len([call for call in self.remote.calls if call.method == "POST"]), 1)

    def test_lost_create_response_finds_one_matching_pr(self):
        self.double.lose_create = True
        with self.assertRaises(ship.Refusal):
            self.prepare()
        self.assertEqual(self.prepare()["pull_request"]["number"], 1)
        self.assertEqual(len([call for call in self.remote.calls if call.method == "POST"]), 1)

    def test_invented_or_stale_review_receipt_refuses(self):
        self.prepare()
        operation = self.operation()
        operation.state["passes"][-1]["report"]["check"] = None
        operation.save()
        with self.assertRaises(ship.Refusal):
            self.merge()

    def test_head_change_after_review_prevents_push(self):
        original = ship.Ship.review
        def changed(operation, head):
            original(operation, head)
            _git(operation.root, "commit", "--allow-empty", "-m", "changed\n\nAuthored-with: human")
        with patch.object(ship.Ship, "review", changed), self.assertRaisesRegex(ship.Refusal, "HEAD moved"):
            self.prepare()
        self.assertFalse(any(call.method == "POST" for call in self.remote.calls))

    def test_delivery_requires_acceptance_and_reconciles_failed_database_write(self):
        acceptance = self.directory / "acceptance.json"
        acceptance.write_text(json.dumps({"item": self.item, "complete": True, "criteria": [{"criterion": "actual scope", "passed": True, "evidence": "fixture-check-pass"}]}))
        self.prepare("--deliver", "--acceptance-file", str(acceptance))
        before_refs = _git(self.operator, "show-ref")
        before_status = _git(self.operator, "status", "--porcelain")
        with patch("sd_db.progress.deliver_work", side_effect=sqlite3.OperationalError("DB write unavailable")):
            result = self.merge()
        self.assertTrue(result["delivery_pending"])
        missing = subprocess.run(["git", "cat-file", "-e", result["merge_commit"]], cwd=self.operator, capture_output=True)
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(self.connection.execute("SELECT status FROM item WHERE id=?", (self.item,)).fetchone()[0], "in_progress")
        fixed = self.operation("reconcile").reconcile()
        self.assertFalse(fixed["delivery_pending"])
        self.assertEqual(_git(self.operator, "show-ref"), before_refs)
        self.assertEqual(_git(self.operator, "status", "--porcelain"), before_status)
        self.assertEqual((self.operator / "operator.txt").read_text(), "uncommitted operator work")
        self.assertEqual(self.connection.execute("SELECT status FROM item WHERE id=?", (self.item,)).fetchone()[0], "done")
        self.assertEqual(len([call for call in self.remote.calls if call.method == "PUT"]), 1)

    def test_dirty_checkout_and_preexisting_index_are_unchanged(self):
        (self.root / "unrelated.txt").write_text("operator work")
        before = _git(self.root, "status", "--porcelain")
        with self.assertRaisesRegex(ship.Refusal, "uncommitted"):
            self.prepare()
        self.assertEqual(_git(self.root, "status", "--porcelain"), before)
        _git(self.root, "add", "unrelated.txt")
        message = self.directory / "message.txt"
        message.write_text("focused change")
        before = _git(self.root, "diff", "--cached")
        with self.assertRaisesRegex(ship.Refusal, "index already"):
            self.prepare("--path", "src.py", "--message-file", str(message), "--author", "author")
        self.assertEqual(_git(self.root, "diff", "--cached"), before)

    def test_no_repository_path_flag_or_unreviewed_head_override(self):
        for flag in ("--repo", "--reviewed-head"):
            result = self.cli("prepare", flag, "elsewhere")
            self.assertEqual(result.returncode, 2)

    def test_only_enumerated_files_commit_and_unrelated_work_stays(self):
        (self.root / "src.py").write_text("intended = True\n")
        (self.root / "unrelated.txt").write_text("operator work")
        message = self.directory / "message.txt"
        message.write_text("Ship only the intended file")
        args = self.args("prepare", "--path", "src.py", "--message-file", str(message), "--author", "author")
        ship.commit_paths(self.root, args)
        self.assertEqual(_git(self.root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), "src.py")
        self.assertEqual((self.root / "unrelated.txt").read_text(), "operator work")
        self.assertIn("Authored-with: author/firstvendor", _git(self.root, "show", "-s", "--format=%B", "HEAD"))

    def test_observe_uses_item_branch_without_mutating_operator_checkout_or_receipts(self):
        self.prepare()
        before_refs = _git(self.operator, "show-ref")
        before_status = _git(self.operator, "status", "--porcelain")
        before_rows = self.connection.execute("SELECT COUNT(*) FROM state").fetchone()[0]
        operation = ship.Ship(self.operator, self.connection, self.database, self.args("observe"))
        observed = operation.observe()
        self.assertEqual(observed["phase"], "ready_to_send")
        self.assertFalse(observed["merged"])
        self.assertFalse(observed["verified"])
        self.assertEqual(_git(self.operator, "show-ref"), before_refs)
        self.assertEqual(_git(self.operator, "status", "--porcelain"), before_status)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM state").fetchone()[0], before_rows)

    def test_repository_lock_cannot_be_owned_by_two_clones(self):
        from sd_db.workflow import WorkflowError
        with receipts.repository_lock(self.database, "fixture/repo"):
            with self.assertRaisesRegex(WorkflowError, "another ship"):
                with receipts.repository_lock(self.database, "fixture/repo"):
                    self.fail("second owner")

    def test_ending_assignment_keeps_work_and_manual_merge_controls_guarded(self):
        from sd_db.progress import cancel_work, work_controls
        from sd_db.workflow import WorkflowError
        create_assignment(self.connection, item=self.item, role="author", status="ending")
        self.assertFalse(work_controls(self.connection, self.item)["cancel"])
        with self.assertRaisesRegex(WorkflowError, "ending assignment"):
            cancel_work(self.connection, self.item, reason="stop")
        with self.assertRaisesRegex(WorkflowError, "manual merge authority"):
            receipts.manual_merge_guard(self.connection, str(self.operator))

    def test_changed_acceptance_scope_refuses_before_spending_a_fix_review(self):
        from sd_db import set_item_fields
        acceptance = self.directory / "acceptance.json"
        acceptance.write_text(json.dumps({"item": self.item, "complete": True, "criteria": [
            {"criterion": "actual scope", "passed": True, "evidence": "fixture-check-pass"}]}))
        self.prepare("--deliver", "--acceptance-file", str(acceptance))
        set_item_fields(self.connection, self.item, body="new scope")
        with self.assertRaisesRegex(ship.Refusal, "acceptance scope changed"):
            self.prepare()
        self.assertEqual(len(self.operation().state["passes"]), 1)

    def test_author_assignment_cannot_borrow_manual_merge_authority(self):
        from sd_db.workflow import WorkflowError
        self.prepare()
        create_assignment(self.connection, item=self.item, role="author", status="running")
        with self.assertRaisesRegex(WorkflowError, "manual merge authority"):
            self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_new_review_configuration_invalidates_the_saved_receipt(self):
        self.prepare()
        with (self.root / "CLAUDE.local.md").open("a") as stream:
            stream.write("\nconfiguration changed\n")
        with self.assertRaisesRegex(ship.Refusal, "policy changed"):
            self.merge()

    def test_delivery_clone_identity_cannot_be_replaced(self):
        from sd_db.progress import deliver_work
        from sd_db.workflow import WorkflowError
        self.prepare()
        result = self.merge()
        _git(self.root, "remote", "set-url", "origin", "https://github.com/other/repo.git")
        with self.assertRaisesRegex(WorkflowError, "origin does not match"):
            deliver_work(self.connection, self.item, result["merge_commit"], verification_root=self.root)

    def test_forged_delivery_trailer_cannot_turn_a_slice_into_completion(self):
        body = self.directory / "body.txt"
        body.write_text(f"A slice\n\nDelivers: sd:{self.item}\n")
        with self.assertRaisesRegex(ship.Refusal, "owns association"):
            self.prepare("--body-file", str(body))
        self.assertFalse(any(call.method == "POST" for call in self.remote.calls))

    def test_one_fix_verification_keeps_prior_findings_and_refuses_a_third_pass(self):
        program = self.programs / "review-fixture"
        payload = {"type": "result", "subtype": "success", "structured_output": {"findings": [
            {"path": "src.py", "line": 1, "severity": "high", "family": "correctness", "summary": "value is wrong"}]}}
        program.write_text("#!/usr/bin/env python3\nimport json\nprint(" + repr(json.dumps(payload)) + ")\n")
        with self.assertRaisesRegex(ship.Refusal, "local review blocking"):
            self.prepare()
        first = self.operation().state["passes"][0]
        (self.root / "src.py").write_text("value = 2\n")
        _git(self.root, "add", "src.py")
        _git(self.root, "commit", "-m", "correct value\n\nAuthored-with: human")
        payload["structured_output"]["findings"] = []
        program.write_text("#!/usr/bin/env python3\nimport json\nprint(" + repr(json.dumps(payload)) + ")\n")
        prepared = self.prepare()
        state = self.operation().state
        self.assertEqual(len(state["passes"]), 2)
        self.assertEqual(state["passes"][1]["report"]["subject"]["base"], first["head"])
        self.assertEqual(state["passes"][1]["report"]["verification_report_digest"], ship.digest(first["report"]))
        self.assertEqual(state["passes"][0]["report"]["findings"][0]["summary"], "value is wrong")
        _git(self.root, "commit", "--allow-empty", "-m", "third change\n\nAuthored-with: human")
        with self.assertRaisesRegex(ship.Refusal, "spent"):
            self.prepare()
        self.assertEqual(self.remote.rev_parse("topic"), prepared["reviewed_head"])

    def test_tampered_fix_receipt_cannot_claim_original_blockers_were_verified(self):
        self.prepare()
        _git(self.root, "commit", "--allow-empty", "-m", "fix\n\nAuthored-with: human")
        self.prepare()
        operation = self.operation()
        operation.state["passes"][1]["report"]["verification_report_digest"] = "invented"
        operation.save()
        with self.assertRaisesRegex(ship.Refusal, "fix verification"):
            self.merge()

    def prepare_owned_delivery(self):
        from sd_db import runner
        acceptance = self.directory / "acceptance.json"
        acceptance.write_text(json.dumps({"item": self.item, "complete": True, "criteria": [
            {"criterion": "scope", "passed": True, "evidence": "real fixture check"}]}))
        self.prepare("--deliver", "--acceptance-file", str(acceptance))
        assignment = runner.enqueue(self.connection, [self.item], role="merge")[0]
        claimed = runner.claim(self.connection, assignment["id"], owner="fixture", work_root=self.directory / "work",
                               retention_root=self.directory / "retained")
        run = claimed["run"]
        target = pathlib.Path(run["work_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(self.root, target)
        self.root = target
        head = _git(self.root, "rev-parse", "HEAD")
        runner.update_run(self.connection, run["id"], authored_head=head, reviewed_head=head)
        result = self.operation("merge", "--run", run["id"], "--expected-head", head).merge()
        self.assertTrue(result["delivery_pending"])
        runner.record_merge(self.connection, self.item, run_id=run["id"], evidence={
            "url": result["pull_request"]["url"], "head": head, "merge_commit": result["merge_commit"],
            "base": result["pull_request"]["base"], "repository": result["pull_request"]["repository"], "observed_at": result["observed_at"]})
        proof = receipts.prepare_delivery(self.connection, run["id"], verification_root=self.root)
        runner.update_run(self.connection, run["id"], delivery_proof=json.dumps(proof))
        runner.begin_ending(self.connection, run["id"], outcome="done", detail="merged")
        retained = pathlib.Path(run["retained_path"])
        retained.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(self.root, retained)
        runner.update_run(self.connection, run["id"], end_step="retained")
        return run["id"], proof

    def test_owned_delivery_finalizes_atomically_after_retention_without_network(self):
        from sd_db import runner
        run_id, proof = self.prepare_owned_delivery()
        with patch("sd_db.progress._git", side_effect=AssertionError("no Git after retention")):
            result = runner.release(self.connection, run_id)
        self.assertTrue(result["released_at"])
        self.assertEqual(self.connection.execute("SELECT status FROM item WHERE id=?", (self.item,)).fetchone()[0], "done")
        self.assertIsNotNone(self.connection.execute("SELECT resolved_at FROM state WHERE id=?", (proof["receipt"],)).fetchone()[0])

    def test_scope_change_rolls_back_release_and_preserves_the_lease(self):
        from sd_db import add_note, runner
        from sd_db.workflow import StaleItem
        run_id, _ = self.prepare_owned_delivery()
        add_note(self.connection, self.item, "decision", "new acceptance requirement")
        with self.assertRaises(StaleItem):
            runner.release(self.connection, run_id)
        self.assertIsNone(runner.run_state(self.connection, run_id)["released_at"])
        self.assertIsNone(self.connection.execute("SELECT released_at FROM runner_lease WHERE run=?", (run_id,)).fetchone()[0])
        self.assertEqual(self.connection.execute("SELECT status FROM item WHERE id=?", (self.item,)).fetchone()[0], "in_progress")

    def test_forged_delivery_descriptor_cannot_close_or_release_work(self):
        from sd_db import runner
        from sd_db.workflow import WorkflowError
        run_id, proof = self.prepare_owned_delivery()
        proof["receipt"] += 10000
        runner.update_run(self.connection, run_id, delivery_proof=json.dumps(proof))
        with self.assertRaisesRegex(WorkflowError, "proof is missing"):
            runner.release(self.connection, run_id)
        self.assertIsNone(runner.run_state(self.connection, run_id)["released_at"])

    def test_delayed_release_keeps_the_durable_historical_merge_proof(self):
        from sd_db import runner
        with patch("sd_db.ship.now", return_value="2000-01-01T00:00:00+00:00"):
            run_id, proof = self.prepare_owned_delivery()
        with patch("sd_db.progress._git", side_effect=AssertionError("no Git after retention")):
            runner.release(self.connection, run_id)
        assignment = runner.queue_state(self.connection, runner.run_state(self.connection, run_id)["assignment"])
        self.assertEqual(assignment["phase"], "merged")
        self.assertEqual(json.loads(assignment["result"])["merge_commit"], proof["commit"])
        self.assertEqual(assignment["status"], "done")
        self.assertEqual(self.connection.execute("SELECT status FROM item WHERE id=?", (self.item,)).fetchone()[0], "done")

    def test_conflicting_merge_receipt_rolls_back_release_without_losing_merge(self):
        from sd_db import runner
        from sd_db.workflow import WorkflowError
        run_id, proof = self.prepare_owned_delivery()
        key = receipts.receipt_key(self.remote.slug, "topic", self.item)
        revision, state = receipts.read(self.connection, key)
        state["merge_commit"] = "f" * 40
        receipts.save(self.connection, key, revision, state)
        with self.assertRaisesRegex(WorkflowError, "merge evidence conflicts"):
            runner.release(self.connection, run_id)
        self.assertIsNone(runner.run_state(self.connection, run_id)["released_at"])
        assignment = runner.queue_state(self.connection, runner.run_state(self.connection, run_id)["assignment"])
        self.assertEqual(json.loads(assignment["result"])["merge_commit"], proof["commit"])
        self.assertIsNone(self.connection.execute("SELECT released_at FROM runner_lease WHERE run=?", (run_id,)).fetchone()[0])

    def test_status_contexts_are_bound_by_exact_sha_endpoint_without_an_invented_sha_field(self):
        self.prepare()
        self.remote.protection["required_status_checks"]["checks"] = []
        self.remote.pull(1).checks = []
        self.double.statuses = [{"context": "check", "state": "pending"}, {"context": "check", "state": "success"}]
        with self.assertRaisesRegex(ship.Refusal, "required status"):
            self.merge()
        self.double.statuses = [{"context": "check", "state": "success"}]
        self.assertEqual(self.merge()["phase"], "merged")

    def test_incomplete_original_depth_cannot_be_repaired_by_only_reviewing_a_fix(self):
        self.prepare()
        operation = self.operation()
        operation.state["passes"][0]["report"]["completed_reviews"] = 0
        operation.state["reviewed_head"] = None
        operation.save()
        _git(self.root, "commit", "--allow-empty", "-m", "new fix\n\nAuthored-with: human")
        with self.assertRaisesRegex(ship.Refusal, "preceding review did not complete"):
            self.prepare()


if __name__ == "__main__":
    unittest.main()
