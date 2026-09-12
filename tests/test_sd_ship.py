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
import time
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
        self.assertIn("no provider pass was reserved", json.loads(result.stdout)["error"])
        key = receipts.receipt_key(self.remote.slug, "topic", self.item)
        state = receipts.read(connection, key)[1]
        self.assertFalse(state.get("passes"))
        self.assertEqual(state["review_preflight_error"]["kind"], "invalid_timing_plan")
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

    def test_prepare_hands_the_pull_request_body_to_the_docs_lint(self):
        # Rule 5 only runs with a body. The skill says the PR link is checked
        # locally in step 2, and until this test the call passed no body, so
        # the rule reported itself not run on every prepare.
        (self.root / "docs/work").mkdir(parents=True)
        calls = []
        original = ship.run

        def recording(root, argv, **kwargs):
            calls.append(argv)
            return original(root, argv, **kwargs)

        with patch.object(ship, "run", recording):
            self.assertEqual(self.prepare()["phase"], "ready_to_send")
        lint = [argv for argv in calls if str(argv[1]).endswith("sd-docs-lint")]
        self.assertEqual(len(lint), 1, calls)
        body = pathlib.Path(lint[0][lint[0].index("--pr-body") + 1])
        self.assertFalse(body.exists(), "the body file is temporary")

    def test_real_cli_review_prepare_slice_merge_and_repeat_reconcile(self):
        prepared = self.cli("prepare")
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        self.assertEqual(json.loads(prepared.stdout)["phase"], "ready_to_send")
        body = self.directory / "prepared-pr.md"
        body.write_text(self.remote.pull(1).body)
        (self.root / "docs/work").mkdir(parents=True)
        linted = subprocess.run([sys.executable, str(ROOT / "bin/sd-docs-lint"), "--pr-body", str(body)],
                                cwd=self.root, env=self.environment, text=True, capture_output=True, timeout=30)
        self.assertEqual(linted.returncode, 0, linted.stdout + linted.stderr)
        self.assertIn(f"database association sd:{self.item}", linted.stdout)
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

    def test_observe_without_receipt_returns_cli_refusal_without_writes(self):
        before = list(self.connection.iterdump())
        refs = _git(self.root, "show-ref")
        calls = len(self.remote.calls)
        result = self.cli("observe")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertFalse(value["ok"])
        self.assertTrue(value["manualRequired"])
        self.assertIn("no unique ship receipt", value["error"])
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(list(self.connection.iterdump()), before)
        self.assertEqual(_git(self.root, "show-ref"), refs)
        self.assertEqual(len(self.remote.calls), calls)

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

    def test_standing_review_revocation_invalidates_receipt_but_unrelated_settings_do_not(self):
        self.environment["XDG_CONFIG_HOME"] = str(self.home / ".config")
        os.environ["XDG_CONFIG_HOME"] = self.environment["XDG_CONFIG_HOME"]
        config = self.home / ".config/sd-ai-command-pack/config.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        self.prepare()
        operation = self.operation()
        head = _git(self.root, "rev-parse", "HEAD")
        config.write_text('{"config":{"sd":{"external_reviews":"configured","merge_authorization":"controlled"}},"unrelated":1}')
        operation.check_review(head)
        config.write_text('{"config":{"sd":{"external_reviews":"deny"}}}')
        with self.assertRaisesRegex(ship.Refusal, "policy changed"):
            self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_absent_to_dangling_local_config_cannot_reuse_a_completed_review(self):
        self.environment["XDG_CONFIG_HOME"] = str(self.home / ".config")
        os.environ["XDG_CONFIG_HOME"] = self.environment["XDG_CONFIG_HOME"]
        config = self.home / ".config/sd-ai-command-pack/config.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        local = self.root / "CLAUDE.local.md"
        local.unlink()
        self.prepare()
        operation = self.operation()
        head = _git(self.root, "rev-parse", "HEAD")
        operation.check_review(head)
        local.symlink_to(self.root / "missing-config")
        with self.assertRaises(OSError):
            operation.check_review(head)
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_linked_worktree_binding_changes_when_main_checkout_consent_is_revoked(self):
        linked = self.directory / "linked"
        _git(self.root, "worktree", "add", "--detach", str(linked), "HEAD")
        before = ship.binding(linked)
        local = self.root / "CLAUDE.local.md"
        local.write_text('<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\nreviewers: ""\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n')
        self.assertEqual(ship.sd_lib.local_block(linked)["reviewers"], "")
        self.assertNotEqual(ship.binding(linked), before)

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

    def test_explicit_retry_preserves_incomplete_pass_and_reviews_the_full_branch(self):
        provider = self.programs / "review-fixture"
        working = provider.read_text()
        provider.write_text("#!/usr/bin/env python3\nprint('not a review')\n")
        with self.assertRaises(ship.Refusal):
            self.prepare()
        first = self.operation().state["passes"][0]
        self.assertEqual(first["report"]["completed_reviews"], 0)
        self.assertEqual(len(self.remote.pull_requests), 0)
        _git(self.root, "commit", "--allow-empty", "-m", "recover parser\n\nAuthored-with: human")
        provider.write_text(working)
        self.prepare("--retry-review")
        state = self.operation().state
        self.assertEqual(state["passes"][0], first)
        self.assertEqual(len(state["passes"]), 2)
        report = state["passes"][1]["report"]
        self.assertIn("src.py", report["subject"]["paths"])
        self.assertEqual(report["subject"]["base"], report["authorship_base"])
        self.assertEqual(report["resume_report_digest"], ship.digest(first["report"]))
        self.assertEqual(self.merge()["phase"], "merged")

    def test_missing_receipt_retry_is_explicit_and_never_rolls_back_spent_pass(self):
        operation = self.operation()
        head = _git(self.root, "rev-parse", "HEAD")
        original = ship.review_process
        def malformed(root, argv, **kwargs):
            return original(root, argv, **kwargs) if "--explain" in argv else subprocess.CompletedProcess([], 1, "not JSON", "")
        with patch.object(ship, "review_process", side_effect=malformed):
            with self.assertRaisesRegex(ship.Refusal, "no valid receipt"):
                operation.review(head)
        first = self.operation().state["passes"][0]
        with self.assertRaisesRegex(ship.Refusal, "retry-review"):
            self.prepare()
        self.prepare("--retry-review")
        state = self.operation().state
        self.assertEqual(state["passes"][0], first)
        self.assertEqual(len(state["passes"]), 2)

    def test_zero_exit_with_unusable_json_receipt_can_retry(self):
        operation = self.operation()
        head = _git(self.root, "rev-parse", "HEAD")
        original = ship.review_process
        def malformed(root, argv, **kwargs):
            return original(root, argv, **kwargs) if "--explain" in argv else subprocess.CompletedProcess([], 0, "{}", "")
        with patch.object(ship, "review_process", side_effect=malformed):
            with self.assertRaises(ship.Refusal):
                operation.review(head)
        first = self.operation().state["passes"][0]
        self.prepare("--retry-review")
        self.assertEqual(self.operation().state["passes"][0], first)
        self.assertEqual(len(self.operation().state["passes"]), 2)

    def test_retry_cannot_spend_a_third_pass(self):
        provider = self.programs / "review-fixture"
        provider.write_text("#!/usr/bin/env python3\nprint('not a review')\n")
        with self.assertRaises(ship.Refusal):
            self.prepare()
        with self.assertRaises(ship.Refusal):
            self.prepare("--retry-review")
        with self.assertRaisesRegex(ship.Refusal, "spent"):
            self.prepare("--retry-review")
        self.assertEqual(len(self.operation().state["passes"]), 2)
        self.assertEqual(len(self.remote.pull_requests), 0)

    def test_retry_flag_cannot_replace_a_complete_review(self):
        self.prepare()
        _git(self.root, "commit", "--allow-empty", "-m", "fix\n\nAuthored-with: human")
        with self.assertRaisesRegex(ship.Refusal, "only an incomplete"):
            self.prepare("--retry-review")

    def spent_reviews(self, blockers=False):
        provider = self.programs / "review-fixture"
        working = provider.read_text()
        for index in range(2):
            if blockers:
                payload = {"type": "result", "subtype": "success", "structured_output": {"findings": [
                    {"path": "src.py", "line": 1, "severity": "high", "family": "correctness",
                     "summary": f"unresolved from pass {index + 1}"}]}}
                provider.write_text("#!/usr/bin/env python3\nprint(" + repr(json.dumps(payload)) + ")\n")
                if index:
                    _git(self.root, "commit", "--allow-empty", "-m", "fix attempt\n\nAuthored-with: human")
            else:
                provider.write_text("#!/usr/bin/env python3\nprint('not JSON')\n")
            with self.assertRaises(ship.Refusal):
                self.prepare(*(["--retry-review"] if index and not blockers else []))
        return provider, working, json.loads(json.dumps(self.operation().state["passes"]))

    def additional(self, head=None, reason="Operator requests one bounded fixture review", history_digest=None):
        extra = ["--review-history-digest", history_digest] if history_digest is not None else []
        return self.prepare("--additional-review-for", head or _git(self.root, "rev-parse", "HEAD"),
                            "--request-reason", reason, *extra)

    def test_additional_review_preserves_all_blockers_and_full_branch_coverage(self):
        provider, _, prior = self.spent_reviews(blockers=True)
        _git(self.root, "commit", "--allow-empty", "-m", "resolve findings\n\nAuthored-with: human")
        captured = self.directory / "third-prompt.txt"
        provider.write_text("#!/usr/bin/env python3\nimport pathlib,sys\n"
                           "work=pathlib.Path(sys.argv[sys.argv.index('--add-dir')+1])\n"
                           f"pathlib.Path({str(captured)!r}).write_text((work/'review-subject.md').read_text())\n"
                           "print('{\"type\":\"result\",\"subtype\":\"success\",\"structured_output\":{\"findings\":[]}}')\n")
        self.additional()
        state = self.operation().state
        self.assertEqual(state["passes"][:2], prior)
        self.assertEqual(len(state["passes"]), 3)
        request = state["passes"][2]["additional_review_request"]
        self.assertEqual(request["prior_history_digest"], ship.digest(prior))
        self.assertEqual(request["head"], _git(self.root, "rev-parse", "HEAD"))
        report = state["passes"][2]["report"]
        self.assertIn("src.py", report["subject"]["paths"])
        self.assertEqual(report["subject"]["base"], report["authorship_base"])
        self.assertEqual(report["resume_report_digest"], ship.digest(ship.review_history(prior)))
        prompt = captured.read_text()
        for index, old in enumerate(prior):
            self.assertIn(f"unresolved from pass {index + 1}", prompt)
            self.assertIn(ship.digest(old["report"]), prompt)
            self.assertIn(old["head"], prompt)
        self.assertIn("value = 1", prompt)
        self.assertEqual(self.merge()["phase"], "merged")

    def test_additional_failed_reservation_remains_spent_and_cannot_be_reused(self):
        _, _, prior = self.spent_reviews()
        with self.assertRaises(ship.Refusal):
            self.additional()
        saved = self.operation().state["passes"]
        self.assertEqual(saved[:2], prior)
        self.assertEqual(len(saved), 3)
        for flags in ([], ["--retry-review"], ["--additional-review-for", _git(self.root, "rev-parse", "HEAD"),
                                              "--request-reason", "A changed reason must not reset the request"]):
            with self.assertRaises(ship.Refusal):
                self.prepare(*flags)
            self.assertEqual(self.operation().state["passes"], saved)
        self.assertFalse(self.remote.pull_requests)

    def test_additional_request_validates_head_reason_and_existing_cap_before_dispatch(self):
        head = _git(self.root, "rev-parse", "HEAD")
        with self.assertRaises(ship.Refusal):
            self.additional(head)
        self.spent_reviews()
        prior = self.operation().state["passes"]
        for flags in (["--additional-review-for", head], ["--request-reason", "reason"],
                      ["--additional-review-for", head, "--request-reason", "  "],
                      ["--additional-review-for", head[:12], "--request-reason", "reason"],
                      ["--additional-review-for", "0" * 40, "--request-reason", "reason"],
                      ["--additional-review-for", head, "--request-reason", "reason", "--retry-review"]):
            operation = self.operation("prepare", *flags)
            with self.subTest(flags=flags), patch.object(ship.subprocess, "run", side_effect=AssertionError("review dispatched")):
                with self.assertRaises(ship.Refusal):
                    operation.review(head)
            self.assertEqual(self.operation().state["passes"], prior)

    def test_additional_request_refuses_dirty_or_commit_stage_before_mutation(self):
        self.spent_reviews()
        head = _git(self.root, "rev-parse", "HEAD")
        (self.root / "src.py").write_text("uncommitted = True\n")
        for extra in ([], ["--path", "src.py", "--message-file", str(self.directory / "missing-message"), "--author", "author"]):
            with self.assertRaises(ship.Refusal):
                self.prepare("--additional-review-for", head, "--request-reason", "reason", *extra)
            self.assertEqual(_git(self.root, "rev-parse", "HEAD"), head)
            self.assertEqual(_git(self.root, "diff", "--cached", "--name-only"), "")
        self.assertEqual(len(self.operation().state["passes"]), 2)

    def test_additional_receipt_revalidates_history_coverage_and_request_at_merge(self):
        provider, working, _ = self.spent_reviews()
        provider.write_text(working)
        self.additional()
        operation = self.operation()
        original = json.loads(json.dumps(operation.state))
        for change in ("missing-request", "history", "reason", "head", "coverage", "subject", "evidence"):
            operation.state = json.loads(json.dumps(original))
            last = operation.state["passes"][-1]
            if change == "missing-request":
                last.pop("additional_review_request")
            elif change == "history":
                operation.state["passes"][0]["report"]["findings"].append({"path": "src.py", "summary": "lost"})
            elif change in ("reason", "head"):
                last["additional_review_request"][change] = ""
            elif change == "coverage":
                last["report"]["completed_reviews"] = 0
            elif change == "subject":
                last["report"]["subject"]["base"] = last["head"]
            else:
                last["report"]["resume_report_digest"] = "invented"
            operation.save()
            with self.subTest(change=change), self.assertRaises(ship.Refusal):
                self.merge()
        operation.state = original
        operation.save()
        self.assertEqual(self.merge()["phase"], "merged")

    def test_additional_history_keeps_missing_reports_and_all_author_vendors(self):
        history = ship.review_history([
            {"head": "a" * 40, "report": {"findings": [], "authored_with": ["old-vendor"]}},
            {"head": "b" * 40}])
        self.assertEqual(history["authored_with"], ["old-vendor"])
        self.assertEqual(history["history"][1]["report_digest"], None)
        self.assertEqual(history["subject"]["head"], "b" * 40)
        self.assertNotIn("completed_reviews", history)

    def test_additional_timeout_keeps_reportless_reservation_spent(self):
        _, _, prior = self.spent_reviews()
        head = _git(self.root, "rev-parse", "HEAD")
        operation = self.operation("prepare", "--additional-review-for", head, "--request-reason", "reason")
        original_run = ship.review_process

        def timed_out(root, argv, **kwargs):
            if "--explain" not in argv:
                raise ship.ReviewTimeout({"kind": "watchdog_expired", "allowed_seconds": kwargs["timeout"]})
            return original_run(root, argv, **kwargs)

        with patch.object(ship, "review_process", side_effect=timed_out), self.assertRaisesRegex(ship.Refusal, "watchdog expired"):
            operation.review(head)
        state = self.operation().state
        self.assertEqual(state["passes"][:2], prior)
        self.assertEqual(len(state["passes"]), 3)
        self.assertNotIn("report", state["passes"][-1])
        self.assertEqual(state["passes"][-1]["execution_error"]["stage"], "execution")
        self.assertEqual(state["passes"][-1]["exit_code"], 124)
        self.assertIsNone(state["reviewed_head"])
        with self.assertRaises(ship.Refusal):
            self.additional()
        self.assertEqual(self.operation().state["passes"], state["passes"])

    def spent_additional(self):
        provider, working, _ = self.spent_reviews()
        with self.assertRaises(ship.Refusal):
            self.additional()
        return provider, working, json.loads(json.dumps(self.operation().state["passes"]))

    def test_renewed_fourth_and_fifth_reviews_preserve_each_prefix_and_full_branch(self):
        provider, working, prior = self.spent_additional()
        provider.write_text(working)
        for count in (4, 5):
            _git(self.root, "commit", "--allow-empty", "-m", f"renewal {count}\n\nAuthored-with: human")
            head = _git(self.root, "rev-parse", "HEAD")
            with self.assertRaises(ship.Refusal):
                self.operation().check_review(head)
            self.additional(history_digest=ship.digest(prior))
            state = self.operation().state
            self.assertEqual(len(state["passes"]), count)
            self.assertEqual(state["passes"][:-1], prior)
            last = state["passes"][-1]
            self.assertEqual(last["additional_review_request"]["prior_history_digest"], ship.digest(prior))
            self.assertEqual(last["additional_review_request"]["allowed_passes"], 1)
            self.assertEqual(last["report"]["subject"]["head"], head)
            self.assertEqual(last["report"]["subject"]["base"], last["report"]["authorship_base"])
            self.assertEqual(last["report"]["resume_report_digest"], ship.digest(ship.review_history(prior)))
            self.assertIn("src.py", last["report"]["subject"]["paths"])
            prior = json.loads(json.dumps(state["passes"]))
        with self.assertRaisesRegex(ship.Refusal, "required CI is not passing"):
            self.merge()
        pull = self.remote.pull(1)
        pull.checks = [{**row, "head_sha": head} for row in pull.checks]
        self.assertEqual(self.merge()["phase"], "merged")

    def test_renewal_replayed_or_missing_digest_never_reserves_or_dispatches(self):
        provider, working, prior = self.spent_additional()
        consumed = ship.digest(prior)
        provider.write_text(working)
        self.additional(history_digest=consumed)
        head = _git(self.root, "rev-parse", "HEAD")
        prefix = ["--additional-review-for", head, "--request-reason", "another reason"]
        saved = self.operation().state
        revision = self.operation().revision
        for flags in (prefix, [*prefix, "--review-history-digest", consumed],
                      [*prefix, "--review-history-digest", "0" * 64],
                      [*prefix, "--review-history-digest", "not-hex"],
                      [*prefix, "--review-history-digest", "NaN"],
                      ["--review-history-digest", ship.digest(saved["passes"])],
                      [*prefix, "--review-history-digest", ship.digest(saved["passes"]), "--retry-review"]):
            operation = self.operation("prepare", *flags)
            with self.subTest(flags=flags), patch.object(ship.subprocess, "run", side_effect=AssertionError("review dispatched")):
                with self.assertRaises(ship.Refusal):
                    operation.review(head)
            self.assertEqual(self.operation().state, saved)
            self.assertEqual(self.operation().revision, revision)
        operation = self.operation("prepare", *prefix, "--review-history-digest", consumed)
        with patch.object(operation.api, "api", side_effect=AssertionError("remote read attempted")), patch.object(ship, "run", side_effect=AssertionError("check started")):
            with self.assertRaisesRegex(ship.Refusal, ship.digest(saved["passes"])):
                operation.prepare()
        self.assertEqual(self.operation().state, saved)
        self.assertEqual(self.operation().revision, revision)

    def test_renewal_validates_every_additional_request_and_prior_evidence_before_reserving(self):
        self.spent_additional()
        operation = self.operation()
        original = json.loads(json.dumps(operation.state))
        head = _git(self.root, "rev-parse", "HEAD")
        for change in ("missing", "type", "reason", "head", "allowance", "digest", "earlier-history", "report-envelope"):
            state = json.loads(json.dumps(original))
            entry = state["passes"][2]
            request = entry["additional_review_request"]
            if change == "missing":
                entry.pop("additional_review_request")
            elif change == "type":
                entry["additional_review_request"] = []
            elif change in ("reason", "head"):
                request[change] = ""
            elif change == "allowance":
                request["allowed_passes"] = True
            elif change == "digest":
                request["prior_history_digest"] = "wrong"
            elif change == "earlier-history":
                state["passes"][0]["report"]["findings"].append({"summary": "changed evidence"})
            else:
                entry["report"]["findings"] = {}
            operation.state = state
            operation.save()
            revision = operation.revision
            candidate = self.operation("prepare", "--additional-review-for", head, "--request-reason", "renew",
                                       "--review-history-digest", ship.digest(state["passes"]))
            with self.subTest(change=change), patch.object(ship.subprocess, "run", side_effect=AssertionError("review dispatched")):
                with self.assertRaises(ship.Refusal):
                    candidate.review(head)
            self.assertEqual(self.operation().state, state)
            self.assertEqual(self.operation().revision, revision)

    def test_renewal_after_reportless_additional_pass_requires_a_new_complete_report(self):
        provider, working, _ = self.spent_reviews()
        head = _git(self.root, "rev-parse", "HEAD")
        operation = self.operation("prepare", "--additional-review-for", head, "--request-reason", "initial additional")
        original_run = ship.review_process

        def reportless(root, argv, **kwargs):
            if "--explain" not in argv:
                return subprocess.CompletedProcess(argv, 1, "not a receipt", "")
            return original_run(root, argv, **kwargs)

        with patch.object(ship, "review_process", side_effect=reportless), self.assertRaises(ship.Refusal):
            operation.review(head)
        prior = self.operation().state["passes"]
        self.assertNotIn("report", prior[-1])
        with self.assertRaises(ship.Refusal):
            self.operation().check_review(head)
        # A failed report need not retroactively acquire successful coverage fields.
        def failed(root, argv, **kwargs):
            if "--explain" not in argv:
                return subprocess.CompletedProcess(argv, 1, '{"status":"gate_failed"}', "")
            return original_run(root, argv, **kwargs)

        with patch.object(ship, "review_process", side_effect=failed), self.assertRaises(ship.Refusal):
            self.additional(history_digest=ship.digest(prior))
        saved = self.operation().state["passes"]
        self.assertEqual(saved[:-1], prior)
        self.assertEqual(saved[-1]["report"], {"status": "gate_failed"})
        prior = saved
        with self.assertRaises(ship.Refusal):
            self.operation().check_review(head)
        provider.write_text(working)
        self.additional(history_digest=ship.digest(prior))
        state = self.operation().state
        self.assertEqual(state["passes"][:-1], prior)
        self.assertEqual(state["passes"][-1]["report"]["resume_report_digest"], ship.digest(ship.review_history(prior)))
        self.assertTrue(ship.completed_depth(state["passes"][-1]["report"]))
        self.assertEqual(self.merge()["phase"], "merged")

    def test_renewed_receipt_rechecks_all_prefixes_and_only_current_success_at_merge(self):
        provider, working, prior = self.spent_additional()
        provider.write_text(working)
        self.additional(history_digest=ship.digest(prior))
        operation = self.operation()
        original = json.loads(json.dumps(operation.state))
        for change in ("earlier-request", "earlier-history", "base", "resume", "depth", "head", "check", "blocker", "binding"):
            operation.state = json.loads(json.dumps(original))
            report = operation.state["passes"][-1]["report"]
            if change == "earlier-request":
                operation.state["passes"][2].pop("additional_review_request")
                operation.state["passes"][-1]["additional_review_request"]["prior_history_digest"] = ship.digest(operation.state["passes"][:-1])
                report["resume_report_digest"] = ship.digest(ship.review_history(operation.state["passes"][:-1]))
            elif change == "earlier-history":
                operation.state["passes"][0]["report"]["findings"].append({"summary": "changed"})
            elif change == "base":
                report["subject"]["base"] = report["subject"]["head"]
            elif change == "resume":
                report["resume_report_digest"] = "wrong"
            elif change == "depth":
                report["completed_reviews"] = 0
            elif change == "head":
                report["subject"]["head"] = "0" * 40
            elif change == "check":
                report["check"]["status"] = "fail"
            elif change == "blocker":
                report["findings"].append({"disposition": "blocking"})
            else:
                operation.state["binding"] = "wrong"
            operation.save()
            with self.subTest(change=change), self.assertRaises(ship.Refusal):
                self.merge()
        operation.state = original
        operation.save()
        self.assertEqual(self.merge()["phase"], "merged")

    def test_renewed_current_report_requires_valid_full_branch_bases(self):
        provider, working, prior = self.spent_additional()
        provider.write_text(working)
        self.additional(history_digest=ship.digest(prior))
        operation = self.operation()
        original = json.loads(json.dumps(operation.state))
        head = _git(self.root, "rev-parse", "HEAD")
        for base in (None, "", "not-a-sha", [], "a" * 39, "g" * 40):
            operation.state = json.loads(json.dumps(original))
            report = operation.state["passes"][-1]["report"]
            if base is None:
                report.pop("authorship_base")
                report["subject"].pop("base")
            else:
                report["authorship_base"] = report["subject"]["base"] = base
            operation.save()
            with self.subTest(base=base), self.assertRaises(ship.Refusal):
                self.operation().check_review(head)
        operation.state = original
        operation.save()
        self.operation().check_review(head)

    def test_renewal_digest_with_commit_flags_refuses_before_index_or_commit_changes(self):
        _, _, prior = self.spent_additional()
        head = _git(self.root, "rev-parse", "HEAD")
        (self.root / "src.py").write_text("uncommitted = True\n")
        message = self.directory / "message.txt"
        message.write_text("Should never commit")
        commit = ["--path", "src.py", "--message-file", str(message), "--author", "author"]
        for extra in ([], ["--additional-review-for", head, "--request-reason", "renew"]):
            with self.subTest(extra=extra), patch.object(ship, "commit_paths", side_effect=AssertionError("commit attempted")):
                with self.assertRaises(ship.Refusal):
                    self.prepare("--review-history-digest", ship.digest(prior), *extra, *commit)
            self.assertEqual(_git(self.root, "rev-parse", "HEAD"), head)
            self.assertEqual(_git(self.root, "diff", "--cached", "--name-only"), "")
            self.assertEqual((self.root / "src.py").read_text(), "uncommitted = True\n")
            self.assertEqual(self.operation().state["passes"], prior)

    def test_renewal_digest_is_not_accepted_before_three_reservations(self):
        self.spent_reviews()
        prior = self.operation().state["passes"]
        head = _git(self.root, "rev-parse", "HEAD")
        operation = self.operation("prepare", "--additional-review-for", head, "--request-reason", "renew",
                                   "--review-history-digest", ship.digest(prior))
        with patch.object(ship.subprocess, "run", side_effect=AssertionError("review dispatched")), self.assertRaises(ship.Refusal):
            operation.review(head)
        self.assertEqual(self.operation().state["passes"], prior)

    def test_additional_review_rejects_rewritten_ancestry_before_reserving(self):
        _, _, prior = self.spent_reviews()
        unrelated = _git(self.root, "commit-tree", _git(self.root, "rev-parse", "HEAD^{tree}"), "-m", "unrelated")
        _git(self.root, "update-ref", "refs/heads/topic", unrelated)
        with self.assertRaises(ship.Refusal):
            self.additional(unrelated)
        self.assertEqual(self.operation().state["passes"], prior)
        self.assertFalse(self.remote.pull_requests)


    def test_timing_plan_allows_valid_sequential_work_without_another_reservation(self):
        from tests.test_sd_review import sd_review
        trace = []
        stages = []
        def child(root, argv, *, timeout):
            args = sd_review.build_parser().parse_args(argv[2:])
            stages.append((args.explain, timeout))
            elapsed = 0
            def logical_runner(command, env, cwd, allowance):
                nonlocal elapsed
                check = any(str(a).endswith("/sd-check") for a in command)
                elapsed += 899 if check else 1799
                self.assertLess(899 if check else 1799, allowance)
                if elapsed > timeout:
                    raise ship.ReviewTimeout({"kind": "watchdog_expired", "allowed_seconds": timeout})
                trace.append("check" if check else "provider")
                payload = {} if check else {"type": "result", "subtype": "success", "structured_output": {"findings": []}}
                return sd_review.Completed(0, json.dumps(payload), "")
            report = sd_review.review(root, args, logical_runner, self.environment)
            return subprocess.CompletedProcess(argv, sd_review.STATUS_EXIT.get(report["status"], 0), json.dumps(report), "")
        with patch.object(ship, "review_process", side_effect=child):
            self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        state = self.operation().state
        self.assertEqual(stages, [(True, 3600), (False, 9000)])
        self.assertEqual(trace, ["check", "provider", "provider"])
        self.assertEqual(len(state["passes"]), 1)
        self.assertEqual(state["passes"][0]["report"]["completed_reviews"], 2)

    def test_planning_timeout_saves_diagnostics_without_dispatch_or_reservation(self):
        diagnostic = {"kind": "watchdog_expired", "allowed_seconds": 3600,
                      "stdout": {"bytes": 8, "tail": "partial", "truncated": False},
                      "cleanup": {"term": "sent", "kill": "absent", "leader_reaped": True},
                      "captured_report": {"completed_reviews": 3, "status": "clean"}}
        with patch.object(ship, "review_process", side_effect=ship.ReviewTimeout(diagnostic)) as child:
            with self.assertRaisesRegex(ship.Refusal, "planning watchdog expired"):
                self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        state = self.operation().state
        self.assertEqual(child.call_count, 1)
        self.assertFalse(state.get("passes"))
        self.assertEqual(state["review_preflight_error"], dict(diagnostic, stage="planning"))
        self.assertIsNone(state.get("reviewed_head"))

    def test_invalid_timing_plan_never_starts_execution_or_reserves(self):
        with patch.object(ship, "review_process", return_value=subprocess.CompletedProcess([], 0, "{}", "")) as child:
            with self.assertRaisesRegex(ship.Refusal, "no valid timing plan"):
                self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        self.assertEqual(child.call_count, 1)
        state = self.operation().state
        self.assertFalse(state.get("passes"))
        self.assertEqual(state["review_preflight_error"]["exit_code"], 0)
        self.assertEqual(state["review_preflight_error"]["stdout"]["tail"], "{}")

    def assert_insufficient_reviewers_refuse(self, count):
        import sd_registry

        from tests.test_sd_review import sd_review
        registry = sd_registry.read_file(self.database.parent / "providers.yaml")
        consent = str(sd_registry.recipient(registry.providers["reviewer"])) if count else ""
        (self.root / "CLAUDE.local.md").write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\nmode: full\n"
            f"reviewers: {consent}\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")
        stages = []
        def child(root, argv, *, timeout):
            args = sd_review.build_parser().parse_args(argv[2:])
            stages.append(args.explain)
            self.assertTrue(args.explain, "undersupplied planning must not start execution")
            def no_execution(*_args):
                raise AssertionError("planning dispatched a check or provider")
            report = sd_review.review(root, args, no_execution, self.environment)
            self.assertEqual(report["requested_reviews"], 2)
            self.assertEqual(len(report["timing"]["candidates"]), count)
            return subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
        operation = self.operation()
        with patch.object(ship, "review_process", side_effect=child):
            with self.assertRaisesRegex(ship.Refusal, "no valid timing plan"):
                operation.review(_git(self.root, "rev-parse", "HEAD"))
        self.assertEqual(stages, [True])
        state = self.operation().state
        self.assertFalse(state.get("passes"))
        self.assertIsNone(state.get("reviewed_head"))
        self.assertEqual(state["review_preflight_error"]["kind"], "invalid_timing_plan")

    def test_no_eligible_reviewers_refuse_before_reservation_or_execution(self):
        self.assert_insufficient_reviewers_refuse(0)

    def test_one_eligible_reviewer_cannot_reserve_a_two_review_pass(self):
        self.assert_insufficient_reviewers_refuse(1)

    def test_planning_failure_diagnostics_are_bounded_and_hash_original_streams(self):
        stdout, stderr = "x" * 10000, "y" * 10000 + "prior evidence exceeds limit"
        with patch.object(ship, "review_process", return_value=subprocess.CompletedProcess([], 2, stdout, stderr)):
            with self.assertRaises(ship.Refusal):
                self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        state = self.operation().state
        self.assertFalse(state.get("passes"))
        diagnostic = state["review_preflight_error"]
        self.assertEqual((diagnostic["kind"], diagnostic["stage"], diagnostic["exit_code"]), ("invalid_timing_plan", "planning", 2))
        for name, text in (("stdout", stdout), ("stderr", stderr)):
            self.assertEqual(diagnostic[name]["bytes"], len(text))
            self.assertEqual(diagnostic[name]["sha256"], ship.hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(diagnostic[name]["tail"], text[-4096:])
            self.assertTrue(diagnostic[name]["truncated"])

    def test_oversized_resume_preflight_preserves_history_and_next_success_clears_diagnostic(self):
        from tests.test_sd_review import sd_review
        _, _, prior = self.spent_reviews()
        operation = self.operation()
        prior[0]["report"]["findings"] = [{"path": "src.py", "line": 1, "summary": "x" * (sd_review.MAX_OUTPUT_BYTES - 10000),
                                             "disposition": "blocking", "severity": "high", "family": "correctness"}]
        operation.save(passes=prior, review_preflight_error={"stage": "planning", "kind": "old"})
        head = _git(self.root, "rev-parse", "HEAD")
        operation = self.operation("prepare", "--additional-review-for", head, "--request-reason", "fixture")
        before = json.loads(json.dumps(operation.state))
        stages = []
        def child(root, argv, *, timeout):
            args = sd_review.build_parser().parse_args(argv[2:])
            stages.append(args.explain)
            def no_execution(*_args):
                raise AssertionError("check or provider dispatched during invalid planning")
            try:
                with patch.object(sd_review, "local_conventions", return_value="fixture convention " + "y" * 20000):
                    report = sd_review.review(root, args, no_execution, self.environment)
            except sd_review.UsageError as error:
                return subprocess.CompletedProcess(argv, 2, "", str(error))
            return subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
        with patch.object(ship, "review_process", side_effect=child), self.assertRaisesRegex(ship.Refusal, "no valid timing plan"):
            operation.review(head)
        self.assertEqual(stages, [True])
        failed = self.operation().state
        self.assertEqual(failed["passes"], before["passes"])
        self.assertEqual(failed["review_preflight_error"]["stderr"]["tail"], "fix verification evidence exceeds the bounded input")
        self.assertEqual(failed["review_preflight_error"]["exit_code"], 2)
        prior[0]["report"]["findings"][0]["summary"] = "bounded blocker"
        operation.save(passes=prior)
        valid = {"status": "explained", "requested_reviews": 1, "timing": {"phase_seconds": 1800, "setup_seconds": 3600,
                 "execution_seconds": 7200, "candidates": [{"name": "fixture", "recipient": "fixture@fixture"}]}}
        answers = [subprocess.CompletedProcess([], 0, json.dumps(valid), ""), subprocess.CompletedProcess([], 2, "", "failed")]
        with patch.object(ship, "review_process", side_effect=answers), self.assertRaisesRegex(ship.Refusal, "reserved pass remains recorded"):
            operation.review(head)
        saved = self.operation().state
        self.assertEqual(saved["passes"][:-1], prior)
        self.assertEqual(len(saved["passes"]), 3)
        self.assertIsNone(saved["review_preflight_error"])
        self.assertEqual(before["review_preflight_error"], {"stage": "planning", "kind": "old"})

    def captured_timeout_retry(self, extra_reviewer=False):
        from tests.test_sd_review import sd_review
        if extra_reviewer:
            registry = self.database.parent / "providers.yaml"
            provider = self.programs / "review-fixture"
            body = registry.read_text().replace("roles:\n  author:",
                f"  reviewer3: {{ start: '{provider}', vendor: fourthvendor, bill: fixture, roles: [reviewer], reader: claude-json }}\nroles:\n  author:")
            registry.write_text(body.replace("reviewer: [reviewer, reviewer2]", "reviewer: [reviewer, reviewer2, reviewer3]"))
            local = self.root / "CLAUDE.local.md"
            local.write_text(local.read_text().replace("reviewers: ", f"reviewers: reviewer3@{provider}, "))
        original = ship.review_process
        def expires(root, argv, **kwargs):
            if "--explain" in argv:
                return original(root, argv, **kwargs)
            args = sd_review.build_parser().parse_args(argv[2:])
            def canned(command, env, cwd, timeout):
                if any(str(a).endswith("/sd-check") for a in command):
                    return sd_review.Completed(0, "{}", "")
                payload = {"type": "result", "subtype": "success", "structured_output": {"findings": [
                    {"path": "src.py", "line": 1, "severity": "high", "family": "correctness", "summary": "captured timeout blocker"}]}}
                return sd_review.Completed(0, json.dumps(payload), "")
            report = sd_review.review(root, args, canned, self.environment)
            report["authored_with"] = ["secondvendor"]
            raise ship.ReviewTimeout({"kind": "watchdog_expired", "allowed_seconds": kwargs["timeout"], "captured_report": report})
        with patch.object(ship, "review_process", side_effect=expires), self.assertRaisesRegex(ship.Refusal, "watchdog expired"):
            self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        failed = self.operation().state["passes"][0]
        self.assertNotIn("report", failed)
        raw_capture = json.loads(json.dumps(failed["execution_error"]["captured_report"]))
        self.assertEqual(failed["exit_code"], 124)
        self.assertIsNone(self.operation().state["reviewed_head"])
        self.assertIn("captured timeout blocker", json.dumps(ship.review_history([failed])))
        observed = []
        def resumes(root, argv, **kwargs):
            if "--resume-report" in argv:
                observed.append(json.loads(pathlib.Path(argv[argv.index("--resume-report") + 1]).read_text()))
            return original(root, argv, **kwargs)
        with patch.object(ship, "review_process", side_effect=resumes):
            if extra_reviewer:
                self.prepare("--retry-review")
            else:
                with self.assertRaises(ship.Refusal):
                    self.prepare("--retry-review")
        self.assertEqual(len(observed), 2 if extra_reviewer else 1)
        self.assertTrue(all(value == ship.review_history([failed]) for value in observed))
        self.assertTrue(all("completed_reviews" not in value for value in observed))
        self.assertEqual(failed["execution_error"]["captured_report"], raw_capture)
        state = self.operation().state
        self.assertEqual(state["passes"][0], failed)
        if not extra_reviewer:
            self.assertEqual(state["passes"], [failed])
            self.assertIsNone(state["reviewed_head"])
            self.assertEqual(state["review_preflight_error"]["kind"], "invalid_timing_plan")
            return
        latest = state["passes"][-1]["report"]
        self.assertEqual(latest["completed_reviews"], 2)
        self.assertEqual(latest["authored_with"], ["secondvendor"])
        self.assertEqual(latest["reviewed_by"], ["reviewer2", "reviewer3"])

    def test_captured_timeout_blocker_and_authorship_survive_unavailable_retry_planning(self):
        self.captured_timeout_retry()

    def test_successful_captured_timeout_retry_reaches_verified_fixture_merge(self):
        self.captured_timeout_retry(extra_reviewer=True)
        self.assertEqual(self.merge()["phase"], "merged")

    def test_deep_timing_plan_refusal_does_not_reserve(self):
        raw = '{"timing":' + '[' * 10000 + '0' + ']' * 10000 + '}'
        with patch.object(ship, "review_process", return_value=subprocess.CompletedProcess([], 0, raw, "")):
            with self.assertRaises(ship.Refusal):
                self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        state = self.operation().state
        self.assertFalse(state.get("passes"))
        self.assertIsNone(state.get("reviewed_head"))


class ReviewWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def test_normal_nonzero_output_remains_available_for_report_validation(self):
        result = ship.review_process(self.root, [sys.executable, "-c",
            "import sys; print('{\"status\":\"blocking\"}'); print('diagnostic',file=sys.stderr); sys.exit(1)"], timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout), {"status": "blocking"})
        self.assertEqual(result.stderr, "diagnostic\n")

    def expired_group(self, *, ignores_term=False, valid_report=False, leader_exits=False):
        ready = self.root / "ready"
        grandchild = self.root / "grandchild"
        def stop_owned_fixture():
            if ready.exists():
                try:
                    os.killpg(int(ready.read_text()), ship.signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(stop_owned_fixture)
        script = self.root / "tree.py"
        script.write_text("import os,signal,time,pathlib,sys\n"
            + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if ignores_term else "")
            + "child=os.fork()\nif child==0:\n"
            + " signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            + f" pathlib.Path({str(grandchild)!r}).write_text(str(os.getpid()))\n"
            + " while True: time.sleep(1)\n"
            + f"while not pathlib.Path({str(grandchild)!r}).exists(): time.sleep(.005)\n"
            + ("print('{\"completed_reviews\":3,\"status\":\"clean\"}',flush=True)\n" if valid_report else "print('x'*10000,flush=True)\n")
            + "print('e'*10000,file=sys.stderr,flush=True)\n"
            + f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid()))\n"
            + ("sys.exit(0)\n" if leader_exits else "while True: time.sleep(1)\n"))
        original_communicate = subprocess.Popen.communicate
        waiting = False
        def after_ready(process, *args, **kwargs):
            nonlocal waiting
            if not waiting:
                waiting = True
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertTrue(ready.exists(), "fixture did not reach its explicit ready barrier")
            return original_communicate(process, *args, **kwargs)
        with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True) as unrelated:
            try:
                started = time.monotonic()
                with patch.object(subprocess.Popen, "communicate", after_ready), patch.object(ship, "REVIEW_CLEANUP_SECONDS", .05):
                    with self.assertRaises(ship.ReviewTimeout) as raised:
                        ship.review_process(self.root, [sys.executable, str(script)], timeout=.05)
                self.assertLess(time.monotonic() - started, 6)
                self.assertIsNone(unrelated.poll(), "the unrelated process must remain alive")
            finally:
                unrelated.terminate()
                unrelated.wait(timeout=5)
        for identity in (ready, grandchild):
            pid = int(identity.read_text())
            observed = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], text=True, capture_output=True, timeout=5)
            self.assertIn(observed.returncode, (0, 1), observed.stderr)
            self.assertTrue(not observed.stdout.strip() or observed.stdout.strip().startswith("Z"), observed.stdout)
        return raised.exception.diagnostic

    def test_timeout_stops_descendant_after_leader_exits_and_bounds_output(self):
        diagnostic = self.expired_group()
        self.assertEqual(diagnostic["kind"], "watchdog_expired")
        self.assertEqual(diagnostic["cleanup"]["kill"], "sent")
        self.assertTrue(diagnostic["cleanup"]["leader_reaped"])
        for stream in ("stdout", "stderr"):
            self.assertTrue(diagnostic[stream]["truncated"])
            self.assertEqual(diagnostic[stream]["bytes"], 10001)
            self.assertLessEqual(len(diagnostic[stream]["tail"]), 4096)

    def test_ignored_term_is_killed_and_captured_json_is_only_evidence(self):
        diagnostic = self.expired_group(ignores_term=True, valid_report=True)
        self.assertEqual(diagnostic["cleanup"], {"term": "sent", "kill": "sent", "drained": True, "leader_reaped": True})
        self.assertEqual(diagnostic["captured_report"], {"completed_reviews": 3, "status": "clean"})

    def test_exited_leader_cannot_leave_inherited_pipes_and_a_live_grandchild(self):
        diagnostic = self.expired_group(leader_exits=True)
        self.assertEqual(diagnostic["cleanup"]["kill"], "sent")
        self.assertTrue(diagnostic["cleanup"]["leader_reaped"])

    def test_cleanup_failure_is_bounded_and_explicit(self):
        process = unittest.mock.Mock(pid=123, returncode=None)
        process.communicate.side_effect = subprocess.TimeoutExpired([], .01)
        process.poll.return_value = None
        with patch.object(ship.subprocess, "Popen", return_value=process), patch.object(ship.os, "killpg", side_effect=PermissionError("fixture refusal")):
            with self.assertRaises(ship.ReviewTimeout) as raised:
                ship.review_process(self.root, ["fixture"], timeout=.01)
        self.assertEqual(process.communicate.call_count, 3)
        self.assertFalse(raised.exception.diagnostic["cleanup"]["leader_reaped"])
        self.assertIn("failed", raised.exception.diagnostic["cleanup"]["kill"])


    def test_initial_timeout_output_survives_both_failed_cleanup_drains(self):
        body = b'{"findings":[{"summary":"preserved blocker"}]}'
        process = unittest.mock.Mock(pid=123)
        process.communicate.side_effect = [subprocess.TimeoutExpired([], 1, output=body, stderr=b"initial stderr"),
                                           OSError("first drain failed"), subprocess.SubprocessError("second drain failed")]
        process.poll.return_value = 0
        with patch.object(ship.subprocess, "Popen", return_value=process), patch.object(ship.os, "killpg"):
            with self.assertRaises(ship.ReviewTimeout) as raised:
                ship.review_process(self.root, ["fixture"], timeout=1)
        diagnostic = raised.exception.diagnostic
        self.assertEqual(diagnostic["stdout"]["bytes"], len(body))
        self.assertEqual(diagnostic["stderr"]["tail"], "initial stderr")
        self.assertEqual(diagnostic["captured_report"], json.loads(body))
        self.assertFalse(diagnostic["cleanup"]["drained"])

    def test_deep_captured_json_stays_a_typed_timeout(self):
        body = ('{"deep":' + '[' * 10000 + '0' + ']' * 10000 + '}').encode()
        process = unittest.mock.Mock(pid=123)
        process.communicate.side_effect = [subprocess.TimeoutExpired([], 1), (body, b""), (body, b"")]
        process.poll.return_value = 0
        with patch.object(ship.subprocess, "Popen", return_value=process), patch.object(ship.os, "killpg"):
            with self.assertRaises(ship.ReviewTimeout) as raised:
                ship.review_process(self.root, ["fixture"], timeout=1)
        self.assertNotIn("captured_report", raised.exception.diagnostic)
        self.assertEqual(raised.exception.diagnostic["stdout"]["bytes"], len(body))

    def test_interrupt_also_cleans_the_owned_group(self):
        process = unittest.mock.Mock(pid=123)
        process.communicate.side_effect = [KeyboardInterrupt(), (b"", b""), (b"", b"")]
        process.poll.return_value = 0
        with patch.object(ship.subprocess, "Popen", return_value=process), patch.object(ship.os, "killpg") as stop:
            with self.assertRaises(KeyboardInterrupt):
                ship.review_process(self.root, ["fixture"], timeout=1)
        self.assertEqual([row.args[1] for row in stop.call_args_list], [ship.signal.SIGTERM, ship.signal.SIGKILL])

    def test_untrusted_timing_values_cannot_disable_the_watchdog(self):
        valid = {"setup_seconds": 3600, "phase_seconds": 1800, "execution_seconds": 9000,
                 "candidates": [{"name": "a", "recipient": "a@fixture"}, {"name": "b", "recipient": "b@fixture"}]}
        cases = [dict(valid, phase_seconds=0), dict(valid, execution_seconds=float("inf")),
                 dict(valid, execution_seconds=True), dict(valid, candidates="not a list"),
                 dict(valid, candidates=[{}]), dict(valid, execution_seconds=3600), dict(valid, setup_seconds=0)]
        for plan in cases:
            with self.subTest(plan=plan), self.assertRaises(ship.Refusal):
                ship.timing_plan(subprocess.CompletedProcess([], 0, json.dumps({"status": "explained", "requested_reviews": 2, "timing": plan}), ""))

    def test_timing_plan_requires_positive_integer_review_depth_and_enough_candidates(self):
        timing = {"setup_seconds": 3600, "phase_seconds": 1800, "execution_seconds": 9000,
                  "candidates": [{"name": "a", "recipient": "a@fixture"}, {"name": "b", "recipient": "b@fixture"}]}
        report = {"status": "explained", "timing": timing}
        for requested in (None, True, 0, -1, "2", 2.0, float("inf"), 3):
            with self.subTest(requested=requested), self.assertRaises(ship.Refusal):
                ship.timing_plan(subprocess.CompletedProcess([], 0, json.dumps(dict(report, requested_reviews=requested)), ""))
        with self.assertRaises(ship.Refusal):
            ship.timing_plan(subprocess.CompletedProcess([], 0, json.dumps(report), ""))
        for requested in (1, 2):
            self.assertEqual(ship.timing_plan(subprocess.CompletedProcess(
                [], 0, json.dumps(dict(report, requested_reviews=requested)), "")), timing)


if __name__ == "__main__":
    unittest.main()
