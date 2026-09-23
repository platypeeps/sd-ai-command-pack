"""Real bare Git, real CLI children, and a GitHubDouble; no model or GitHub traffic."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re
import shlex
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

import sd_db
from sd_db import connect, create_assignment, create_item, initialise, upsert_repo
from sd_db import ship as receipts
from sd_db.repos import set_runner_merge
from sd_db.testing.github import GitHubDouble
from sd_db.testing.remote import FixtureRemote, RemoteRefusal, _git

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: The directory `make setup` provisioned the library into, read off the copy
#: this run imported rather than off `ROOT / ".venv"`. A test that asks the
#: checkout for a virtualenv has to skip where there is none, and a skipped
#: test in CI asserts nothing; a run that got this far has the library by
#: definition, so this path always exists.
SITE_PACKAGES = pathlib.Path(sd_db.__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
loader = importlib.machinery.SourceFileLoader("sd_ship_tested", str(ROOT / "bin/sd-ship"))
spec = importlib.util.spec_from_loader(loader.name, loader)
ship = importlib.util.module_from_spec(spec)
loader.exec_module(ship)

#: The *Development / Code, before merge* cap. Read from the module that
#: owns it, so these fixtures follow the row instead of restating it.
CAP = importlib.import_module("sd_ship_history").AUTOMATIC_CODE_REVIEW_PASSES


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
        #: Workflow runs `GET /actions/runs` serves, filtered by the query's
        #: `head_sha` and `event` as GitHub filters them (sd:1110).
        self.workflow_runs = []
        self.review_payload = {"reviews": [], "comments": []}
        self.review_sequences = {"reviews": [], "comments": []}
        self.copilot_requests = []
        self.copilot_pending = set()
        self.copilot_requested_login = "copilot-pull-request-reviewer[bot]"
        self.lose_copilot_request = False
        self.create_draft = False
        #: What `GET /rules/branches/{b}` and `GET /rulesets/{id}` answer: no
        #: ruleset unless a test says so, the way the fixture's `main` had no
        #: classic protection before sd:1110 said so (sd:1327).
        self.rules = []
        self.rulesets = {}

    def _pull(self, pull):
        head = getattr(pull, "merged_head", None) or pull.head_sha(self.remote)
        return {"number": pull.number, "title": pull.title, "body": pull.body,
                "state": "closed" if pull.state == "MERGED" else pull.state.lower(),
                "merged": pull.state == "MERGED", "draft": pull.draft,
                "html_url": f"https://github.com/{self.remote.slug}/pull/{pull.number}",
                "head": {"ref": pull.head, "sha": head, "repo": {"full_name": self.remote.slug}},
                "base": {"ref": pull.base},
                "requested_reviewers": ([{"login": self.copilot_requested_login}]
                                          if pull.number in self.copilot_pending else []),
                "mergeable": pull.mergeable == "MERGEABLE",
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
                pull.draft = self.create_draft
                pull.checks = [{"name": "check", "status": "completed", "conclusion": "success",
                                "head_sha": pull.head_sha(self.remote), "app": {"id": 7}}]
                if self.lose_create:
                    raise RemoteRefusal(503, "create response lost")
                return 201, self._pull(pull)
            return 200, [self._pull(pull) for pull in self.remote.pull_requests.values()]
        if method == "POST" and path.startswith(f"{prefix}/pulls/") and path.endswith("/requested_reviewers"):
            number = int(path.split("/")[-2])
            if self.lose_copilot_request:
                raise RemoteRefusal(503, "review request transport failed")
            self.copilot_requests.append({"number": number, "body": body})
            self.copilot_pending.add(number)
            return 201, self._pull(self.remote.pull(number))
        if path.endswith("/statuses"):
            return 200, self.statuses
        if method == "GET" and path.endswith("/protection") and isinstance(self.remote.protection, RemoteRefusal):
            raise self.remote.protection  # a 403 or 5xx, which is not "absent" (sd:1110)
        if method == "GET" and "/rules/branches/" in path:
            # Paged as the endpoint pages: thirty a page unless asked otherwise.
            size, page = int(query.get("per_page", [30])[0]), int(query.get("page", [1])[0])
            return 200, self.rules[(page - 1) * size:page * size]
        if method == "GET" and "/rulesets/" in path:
            ruleset_id = int(path.rsplit("/", 1)[1])
            if ruleset_id not in self.rulesets:
                raise RemoteRefusal(404, f"no ruleset {ruleset_id}")
            return 200, self.rulesets[ruleset_id]
        if method == "GET" and path == f"{prefix}/actions/runs":
            wanted_sha = query.get("head_sha", [None])[0]
            wanted_event = query.get("event", [None])[0]
            runs = [run for run in self.workflow_runs
                    if (wanted_sha is None or run.get("head_sha") == wanted_sha)
                    and (wanted_event is None or run.get("event") == wanted_event)]
            return 200, {"total_count": len(runs), "workflow_runs": runs}
        # The review a `prepare` reads to record the findings its push answers.
        # Empty unless a test says otherwise, and answered here rather than by
        # the shared double because the adapter is the only caller of it.
        if method == "GET" and path.startswith(f"{prefix}/pulls/") and path.rsplit("/", 1)[1] in self.review_payload:
            kind = path.rsplit("/", 1)[1]
            sequence = self.review_sequences[kind]
            if sequence:
                return 200, sequence.pop(0) if len(sequence) > 1 else sequence[0]
            return 200, self.review_payload[kind]
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


#: The fixture `gh`. It answers the way the real one does: the body on stdout,
#: and with `--include` the response line and headers ahead of it, on a
#: refusal too (`HTTP/2.0 404 Not Found` then the JSON), which is what
#: `GitHub.api_status` reads the status from. Exit 1 on a non-2xx, as gh.
SHIM = '''#!/usr/bin/env python3
import json,os,sys,urllib.request,urllib.error
args=sys.argv[1:]
assert args[0]=='api',args
include='--include' in args
args=[a for a in args if a!='--include']
path=args[1]
method=args[args.index('--method')+1]
data=sys.stdin.read().encode() if '--input' in args else None
req=urllib.request.Request(os.environ['SHIP_DOUBLE']+'/'+path,data=data,method=method,headers={'Content-Type':'application/json'})
def emit(status,reason,body):
 if include: print('HTTP/2.0 %d %s\\nContent-Type: application/json\\n' % (status,reason))
 print(body)
try:
 with urllib.request.urlopen(req) as response: emit(response.status,response.reason,response.read().decode())
except urllib.error.HTTPError as error:
 body=error.read().decode()
 emit(error.code,error.reason,body)
 message=json.loads(body).get('message','') if body.startswith('{') else ''
 print('gh: %s (HTTP %d)' % (message,error.code),file=sys.stderr);sys.exit(1)
'''


def git_transport(binary: str, remote: pathlib.Path, url: str) -> str:
    """Keep real Git and local transport without starting Python for every call."""
    network = shlex.join([binary, "-c", f"url.{remote}.insteadOf={url}"])
    return (
        '#!/bin/sh\nfor arg in "$@"; do\n'
        '  case "$arg" in\n'
        f'    fetch|push|ls-remote) exec {network} "$@" ;;\n'
        '  esac\ndone\n'
        f'exec {shlex.quote(binary)} "$@"\n'
    )


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
        upsert_repo(self.connection, str(self.operator), remote=self.remote_url, status_source="row", runner_merge="auto")
        self.item = create_item(self.connection, kind="work", title="fixture work", status="in_progress", repo=str(self.operator), branch="topic")
        self.double = ShipDouble(self.remote)
        self.double.__enter__()
        self.addCleanup(self.double.close)
        self.programs = self.directory / "programs"
        self.programs.mkdir()
        (self.programs / "gh").write_text(SHIM)
        (self.programs / "gh").chmod(0o755)
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        transport = self.programs / "git"
        transport.write_text(git_transport(real_git, self.remote.path, self.remote_url))
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
        # `XDG_CONFIG_HOME` wins over `HOME` in `sd_lib.machine_config_path`, and
        # a GitHub runner sets it: pointed at the fixture here, or a machine
        # config written under `self.home` is never read (sd:1328).
        self.environment = {**os.environ, "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"),
                            "SHIP_DOUBLE": self.double.base_url,
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

    def enable_automatic_copilot(self):
        policy = self.root / ".github/sd-review.json"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps({
            "sensitive": ["src.py"],
            "copilot_review": {"automatic_deep": True},
        }))
        _git(self.root, "add", str(policy.relative_to(self.root)))
        _git(self.root, "commit", "-m", "select deep remote review\n\nAuthored-with: human")

    def disable_automatic_copilot(self):
        """The same file, opting the repository out of paid Copilot review.

        `sensitive` still escalates `src.py` to the deep tier, so the tier is
        never what stops the request in the test below -- the repository's own
        word is.
        """
        policy = self.root / ".github/sd-review.json"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps({
            "sensitive": ["src.py"],
            "copilot_review": {"automatic_deep": False},
        }))
        _git(self.root, "add", str(policy.relative_to(self.root)))
        _git(self.root, "commit", "-m", "opt out of paid remote review\n\nAuthored-with: human")

    def cli(self, command, *extra):
        return subprocess.run([sys.executable, str(ROOT / "bin/sd-ship"), command, "--item", str(self.item), "--json", *extra],
                              cwd=self.root, env=self.environment, text=True, capture_output=True, timeout=30)


    # -- criterion 21: a ship leaves `docs/work/archive/` untouched ---------
    #
    # The criterion's other clauses are greps: no deletion verb outside a
    # frozen set, no sweep or park code path. Those say the pack has no way
    # to touch the archive. These run the pack and look, which is the
    # different question -- a grep over the source cannot see a path reached
    # through a helper, nor one reached by a tool the pack shells out to.
    #
    # `sd-plan` is the criterion's other named command and has no
    # executable; it is `skills/sd-plan/SKILL.md`. Its own words are the
    # assertion for that half, checked below.

    def archive_digest(self) -> dict[str, str]:
        """Every file under the archive, by path, as a content hash.

        Hashes and not mtimes: a rewrite that restores the same bytes is not
        a touch worth failing, and a mtime comparison would call it one on
        every checkout.
        """
        root = self.root / "docs" / "work" / "archive"
        return {
            str(path.relative_to(self.root)):
                hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()
        }

    def seed_archive(self) -> dict[str, str]:
        buried = self.root / "docs" / "work" / "archive" / "2026-01" / "2026-01-02-shipped"
        buried.mkdir(parents=True)
        (buried / "prd.md").write_text(
            "---\ntitle: a shipped thing\ncreated: 2026-01-02\n"
            "status: done\n---\n\n# shipped\n", encoding="utf-8")
        (buried / "implement.md").write_text("done\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        # The trailer is not decoration: `sd-review` refuses to plan a review
        # of a commit that does not say who wrote it, and the refusal surfaces
        # here as an invalid timing plan rather than as anything about the
        # archive. Seeding without it tests the trailer rule, not criterion 21.
        _git(self.root, "commit", "-q", "-m",
             "archive a done item\n\nAuthored-with: human")
        return self.archive_digest()

    def test_a_prepare_leaves_every_archived_file_byte_identical(self) -> None:
        before = self.seed_archive()
        self.assertEqual(len(before), 2, "the fixture archive did not get written")
        self.prepare()
        self.assertEqual(self.archive_digest(), before)

    def test_a_prepare_stages_and_commits_nothing_under_the_archive(self) -> None:
        """The digest above would miss a file added and then removed again.

        `git status` over the one path is the check that sees the whole
        working tree rather than the files that happen to exist at the end.
        """
        self.seed_archive()
        head = _git(self.root, "rev-parse", "HEAD")
        self.prepare()
        self.assertEqual(
            _git(self.root, "status", "--porcelain", "--", "docs/work/archive").strip(), "")
        self.assertEqual(
            _git(self.root, "diff", "--name-only", head, "HEAD",
                 "--", "docs/work/archive").strip(), "")

    def test_the_plan_skill_still_disclaims_every_archive_step(self) -> None:
        page = (ROOT / "skills" / "sd-plan" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("There is no automatic archive, parking or sweep step.", page)

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
        set_provider_state(connection, "reviewer", enabled=False)
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

    def test_a_moved_binding_re_reviews_the_same_head_instead_of_bricking_it(self):
        # sd:1390, live on #1140. Reuse was decided on head equality and the
        # receipt then rejected on the binding, with nothing between them, so
        # a branch that already contained the default branch -- and therefore
        # never needed a merge-forward to move its head -- had no verb left
        # once an unrelated landing touched a review tool file. Prepare and
        # merge both refused, `--retry-review` refused a completed review, and
        # the post-cap operator request refuses below the cap.
        self.assertEqual(self.prepare()["phase"], "ready_to_send")
        before = self.operation().state["passes"]
        self.assertEqual(len(before), 1)
        operation = self.operation()
        operation.state["binding"] = "a review tool file landed on the default branch"
        operation.save()
        self.assertEqual(self.prepare()["phase"], "ready_to_send")
        state = self.operation().state
        self.assertEqual(state["binding"], ship.binding(self.root))
        self.assertEqual(len(state["passes"]), 2, "the re-review spends one pass")
        fresh = state["passes"][-1]
        # A full-branch pass at the same head, not a fix verification of it:
        # `--base <previous head>` would name this head and review nothing.
        self.assertEqual(fresh["head"], before[0]["head"])
        self.assertIsNone(fresh["base"])
        self.assertFalse(fresh["retry"])
        self.assertEqual(fresh["review_binding_change"]["superseded_binding"],
                         "a review tool file landed on the default branch")
        self.assertEqual(fresh["report"]["resume_report_digest"],
                         ship.digest(ship.review_history(before)))
        # The receipt reads back through the same coverage walk that merge uses.
        self.assertEqual(self.merge()["phase"], "merged")

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

    def test_standard_change_does_not_request_copilot_automatically(self):
        result = self.prepare()
        self.assertEqual(result["copilot_review"]["decision"], "not_selected")
        self.assertEqual(self.double.copilot_requests, [])

    # -- sd:1328: the Copilot decision is made at dispatch, from the policy as
    # it stands then and the tier the retained review recorded. A review that
    # already happened is evidence of the tier; its own `automatic` verdict is
    # not authoritative, or the operator's cost lever would not move until
    # the next review was paid for.

    def machine_copilot(self, value: str | None) -> None:
        """The fixture machine's `sd.copilot_review`, or no machine config at all."""
        config = self.home / ".config/sd-ai-command-pack/config.json"
        if value is None:
            config.unlink(missing_ok=True)
            return
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"config": {"sd": {"copilot_review": value}}}))

    def route_deep_saying_nothing_about_copilot(self) -> None:
        """A policy file that escalates `src.py` and leaves Copilot to the machine."""
        policy = self.root / ".github/sd-review.json"
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps({"sensitive": ["src.py"]}))
        _git(self.root, "add", str(policy.relative_to(self.root)))
        _git(self.root, "commit", "-m", "route deep, say nothing about Copilot\n\nAuthored-with: human")

    def test_never_set_after_a_deep_review_stops_the_automatic_request(self):
        """The reviewer's scenario: a deep review is retained under the default,
        the operator sets `never` because they just saw the bill, and the ship
        must not request Copilot on the strength of the old report."""
        self.route_deep_saying_nothing_about_copilot()
        self.machine_copilot(None)
        head = _git(self.root, "rev-parse", "HEAD")
        self.operation().review(head)
        recorded = self.operation().state["passes"][-1]["report"]["remote_reviews"]["copilot"]
        self.assertEqual((recorded["tier"], recorded["automatic"]), ("deep", True))
        self.machine_copilot("never")
        prepared = self.prepare()
        self.assertEqual(prepared["copilot_review"]["decision"], "not_selected")
        self.assertEqual(self.double.copilot_requests, [])

    def test_always_set_after_a_review_under_never_requests_at_dispatch(self):
        """The converse: the retained report said no, the policy now says
        always, and the standard-tier change is requested at dispatch."""
        self.machine_copilot("never")
        head = _git(self.root, "rev-parse", "HEAD")
        self.operation().review(head)
        recorded = self.operation().state["passes"][-1]["report"]["remote_reviews"]["copilot"]
        self.assertEqual((recorded["tier"], recorded["automatic"]), ("standard", False))
        self.machine_copilot("always")
        prepared = self.prepare()
        self.assertEqual(prepared["copilot_review"]["selection"], "automatic")
        self.assertEqual(len(self.double.copilot_requests), 1)

    def test_always_leaves_a_retained_skip_tier_pass_alone(self):
        """`always` means every reviewing tier; a `skip` pass has no local
        reviewer, and the selector reads the recorded depth, not the word."""
        self.machine_copilot("always")
        def pass_at(tier, depth):
            return [{"report": {"route": {"tier": tier, "depth": depth},
                                "remote_reviews": {"copilot": {"tier": tier, "repository": None}}}}]
        self.assertFalse(ship.Ship.copilot_selected(pass_at("skip", 0)))
        self.assertTrue(ship.Ship.copilot_selected(pass_at("cheap", 1)))
        self.assertTrue(ship.Ship.copilot_selected(pass_at("deep", 1)))
        self.machine_copilot("never")
        self.assertFalse(ship.Ship.copilot_selected(pass_at("deep", 1)))

    def test_a_delta_pass_of_a_later_push_does_not_hide_the_branch_tier(self):
        """A later push is reviewed as a delta whose own tier says what the push
        changed, not what Copilot would read: the deep pass behind it still
        selects, two skip passes do not, and `never` stops the pair."""
        def pass_at(tier, depth):
            return {"report": {"route": {"tier": tier, "depth": depth},
                               "remote_reviews": {"copilot": {"tier": tier, "repository": None}}}}
        self.assertTrue(ship.Ship.copilot_selected([pass_at("deep", 1), pass_at("skip", 0)]))
        self.assertFalse(ship.Ship.copilot_selected([pass_at("skip", 0), pass_at("skip", 0)]))
        self.machine_copilot("never")
        self.assertFalse(ship.Ship.copilot_selected([pass_at("deep", 1), pass_at("skip", 0)]))

    def test_a_report_from_before_the_key_keeps_its_recorded_opt_out(self):
        """A report written before `repository` travelled in it cannot say
        whether its `automatic: false` was the repository opting out, so that
        verdict is a ceiling: the machine default does not turn it into a
        request, and a report with no verdict at all grants nothing."""
        self.route_deep_saying_nothing_about_copilot()
        self.machine_copilot("never")
        head = _git(self.root, "rev-parse", "HEAD")
        self.operation().review(head)
        operation = self.operation()
        recorded = operation.state["passes"][-1]["report"]["remote_reviews"]["copilot"]
        self.assertEqual((recorded["tier"], recorded["automatic"]), ("deep", False))
        recorded.pop("repository", None)
        self.machine_copilot(None)
        prepared = operation.prepare()
        self.assertEqual(prepared["copilot_review"]["decision"], "not_selected")
        self.assertEqual(self.double.copilot_requests, [])
        bare = [{"report": {"route": {"tier": "deep", "depth": 1}}}]
        self.assertFalse(ship.Ship.copilot_selected(bare))

    def test_a_report_from_before_the_key_still_yields_to_never(self):
        """The verdict of its day is a ceiling and not a grant: `never` set
        since subtracts from a recorded `true`."""
        self.route_deep_saying_nothing_about_copilot()
        self.machine_copilot(None)
        head = _git(self.root, "rev-parse", "HEAD")
        self.operation().review(head)
        operation = self.operation()
        recorded = operation.state["passes"][-1]["report"]["remote_reviews"]["copilot"]
        self.assertEqual((recorded["tier"], recorded["automatic"]), ("deep", True))
        recorded.pop("repository", None)
        self.machine_copilot("never")
        prepared = operation.prepare()
        self.assertEqual(prepared["copilot_review"]["decision"], "not_selected")
        self.assertEqual(self.double.copilot_requests, [])

    def test_a_repository_that_named_the_key_still_wins_at_dispatch(self):
        """The repository's say travels in the report; a machine flip does not
        override a file that named `automatic_deep`."""
        self.machine_copilot("never")
        self.enable_automatic_copilot()
        prepared = self.prepare()
        self.assertEqual(prepared["copilot_review"]["selection"], "automatic")
        self.assertEqual(len(self.double.copilot_requests), 1)

    def test_a_silent_pass_cannot_outvote_a_later_repository_opt_out(self):
        """sd:1369, the reviewer's three-step sequence against committed source.

        Review once while the repository names no Copilot key, commit
        `automatic_deep: false` and verify, then set the machine to `always`.
        The first pass recorded `repository: None`, which falls through to the
        machine setting *as it stands now*; the second recorded the file's
        explicit `False`. Resolving the policy per pass and taking `any()`
        let the first outvote the second, and a paid Copilot request fired
        against a repository that had said no.
        """
        self.machine_copilot("never")
        self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        silent = self.operation().state["passes"][-1]["report"]["remote_reviews"]["copilot"]
        self.assertIsNone(silent["repository"])
        self.disable_automatic_copilot()
        self.operation().review(_git(self.root, "rev-parse", "HEAD"))
        state = self.operation().state
        opted_out = state["passes"][-1]["report"]["remote_reviews"]["copilot"]
        self.assertIs(opted_out["repository"], False)
        self.assertEqual(len(state["passes"]), 2, "both passes have to be retained")
        self.machine_copilot("always")
        prepared = self.prepare()
        self.assertEqual(prepared["copilot_review"]["decision"], "not_selected")
        self.assertEqual(self.double.copilot_requests, [])

    def test_the_repository_word_is_read_from_the_latest_pass_that_carries_it(self):
        """The converse of the opt-out, and the reason `latest` rather than
        `any no wins`: a file that dropped `automatic_deep` since an earlier
        pass hands the question back to the machine setting, and a pass from
        before the key never speaks for the repository at all."""
        def recorded(repository):
            return {"report": {"route": {"tier": "deep", "depth": 1},
                               "remote_reviews": {"copilot": {"repository": repository}}}}
        legacy = {"report": {"route": {"tier": "deep", "depth": 1},
                             "remote_reviews": {"copilot": {"automatic": True}}}}
        self.assertIs(ship.Ship.copilot_repository_now([recorded(None), recorded(False)]), False)
        self.assertIsNone(ship.Ship.copilot_repository_now([recorded(False), recorded(None)]))
        self.assertIs(ship.Ship.copilot_repository_now([recorded(False), legacy]), False)
        self.assertIsNone(ship.Ship.copilot_repository_now([legacy]))
        self.machine_copilot("always")
        self.assertFalse(ship.Ship.copilot_selected([recorded(None), recorded(False)]))
        self.assertTrue(ship.Ship.copilot_selected([recorded(False), recorded(None)]))

    def test_explicit_copilot_review_is_idempotent_while_the_request_is_present(self):
        first = self.prepare("--copilot-review", "request")
        second = self.prepare("--copilot-review", "request")
        self.assertEqual(first["copilot_review"]["selection"], "explicit")
        self.assertEqual(second["copilot_review"]["decision"], "already_recorded")
        self.assertEqual(len(self.double.copilot_requests), 1)
        self.assertEqual(self.double.copilot_requests[0]["body"], {
            "reviewers": ["copilot-pull-request-reviewer[bot]"]})

    def test_copilot_login_variant_keeps_an_explicit_request_idempotent(self):
        self.prepare("--copilot-review", "request")
        self.double.copilot_requested_login = "Copilot"
        repeated = self.prepare("--copilot-review", "request")
        self.assertEqual(repeated["copilot_review"]["decision"], "already_recorded")
        self.assertEqual(len(self.double.copilot_requests), 1)

    def test_deep_change_requests_one_copilot_review_and_waits_for_completion(self):
        self.enable_automatic_copilot()
        prepared = self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.assertEqual(prepared["copilot_review"]["selection"], "automatic")
        self.assertEqual(len(self.double.copilot_requests), 1)
        repeated = self.prepare()
        self.assertEqual(repeated["copilot_review"]["decision"], "not_repeated")
        self.assertEqual(len(self.double.copilot_requests), 1)
        with self.assertRaisesRegex(ship.Refusal, "has not completed"):
            self.merge()
        self.double.review_payload["reviews"] = [{
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "",
        }]
        with patch.object(ship.time, "sleep"):
            self.assertEqual(self.merge()["phase"], "merged")
        self.assertEqual(self.operation().state["copilot_reviews"][0]["status"], "completed")

    def test_later_push_keeps_one_automatic_review_but_requires_exact_head_review(self):
        self.enable_automatic_copilot()
        self.prepare()
        reviewed = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "commit_id": reviewed,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "",
        }]
        _git(self.root, "commit", "--allow-empty", "-m", "later fix\n\nAuthored-with: human")
        head = _git(self.root, "rev-parse", "HEAD")
        repeated = self.prepare()
        self.assertNotEqual(head, reviewed)
        self.assertEqual(self.operation().state["reviewed_head"], head)
        self.assertEqual(repeated["copilot_review"]["decision"], "not_repeated")
        self.assertEqual(len(self.double.copilot_requests), 1)
        pull = self.remote.pull(1)
        pull.checks = [{**row, "head_sha": head} for row in pull.checks]
        self.assertTrue(all(row["head_sha"] == head for row in pull.checks))
        with patch.object(ship.time, "sleep"):
            with self.assertRaisesRegex(ship.Refusal, "not the exact merge head"):
                self.merge()
        self.double.copilot_pending.clear()
        requested = self.prepare("--copilot-review", "request")
        self.assertEqual(requested["copilot_review"]["selection"], "explicit")
        self.assertEqual(len(self.double.copilot_requests), 2)
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:01:00Z",
            "body": "",
        }]
        with patch.object(ship.time, "sleep"):
            self.assertEqual(self.merge()["phase"], "merged")

    def test_later_push_accepts_the_single_automatic_review_on_the_new_head(self):
        self.enable_automatic_copilot()
        self.prepare()
        recorded = _git(self.root, "rev-parse", "HEAD")
        _git(self.root, "commit", "--allow-empty", "-m", "later fix\n\nAuthored-with: human")
        head = _git(self.root, "rev-parse", "HEAD")
        self.prepare()
        self.assertNotEqual(head, recorded)
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "",
        }]
        pull = self.remote.pull(1)
        pull.checks = [{**row, "head_sha": head} for row in pull.checks]
        with patch.object(ship.time, "sleep"):
            self.assertEqual(self.merge()["phase"], "merged")
        self.assertEqual(self.operation().state["copilot_reviews"][0]["status"], "requested")

    def test_explicit_skip_suppresses_a_deep_automatic_review(self):
        self.enable_automatic_copilot()
        result = self.prepare("--copilot-review", "skip")
        self.assertEqual(result["copilot_review"], {
            "decision": "skipped", "reason": "task-scoped suppression"})
        self.assertEqual(self.double.copilot_requests, [])

    def test_explicit_skip_suppresses_later_automatic_prepares(self):
        self.enable_automatic_copilot()
        self.prepare("--copilot-review", "skip")
        repeated = self.prepare()
        self.assertEqual(repeated["copilot_review"], {
            "decision": "skipped", "reason": "task-scoped suppression"})
        self.assertEqual(self.double.copilot_requests, [])

    def test_explicit_request_replaces_persisted_automatic_suppression(self):
        self.enable_automatic_copilot()
        self.prepare("--copilot-review", "skip")
        requested = self.prepare("--copilot-review", "request")
        self.assertEqual(requested["copilot_review"]["selection"], "explicit")
        self.assertFalse(self.operation().state["copilot_review_suppressed"])
        repeated = self.prepare()
        self.assertEqual(repeated["copilot_review"]["decision"], "not_repeated")
        self.assertEqual(len(self.double.copilot_requests), 1)

    def test_refused_explicit_request_preserves_persisted_suppression(self):
        self.enable_automatic_copilot()
        self.prepare("--copilot-review", "skip")
        with self.assertRaisesRegex(ship.Refusal, "provide a final --title"):
            self.prepare("--copilot-review", "request", "--title", "WIP incomplete")
        repeated = self.prepare()
        self.assertEqual(repeated["copilot_review"], {
            "decision": "skipped", "reason": "task-scoped suppression"})
        self.assertEqual(self.double.copilot_requests, [])

    def test_failed_explicit_dispatch_preserves_persisted_suppression(self):
        self.enable_automatic_copilot()
        self.prepare("--copilot-review", "skip")
        self.double.lose_copilot_request = True
        with self.assertRaisesRegex(ship.Refusal, "review request transport failed"):
            self.prepare("--copilot-review", "request")
        state = self.operation().state
        self.assertTrue(state["copilot_review_suppressed"])
        self.assertEqual(state["phase"], "ready_to_send")
        self.assertEqual(state["pull_request"]["number"], 1)
        self.assertEqual(self.double.copilot_requests, [])

    def test_failed_automatic_dispatch_warns_without_recording_a_request(self):
        self.enable_automatic_copilot()
        self.double.lose_copilot_request = True
        result = self.prepare()
        self.assertEqual(result["phase"], "ready_to_send")
        self.assertEqual(result["copilot_review"]["decision"], "request_failed")
        self.assertIn("automatic Copilot review request failed", "\n".join(result["warnings"]))
        self.assertEqual(self.operation().state.get("copilot_reviews"), None)
        self.assertEqual(self.double.copilot_requests, [])

    def test_failed_explicit_dispatch_keeps_prior_finding_acknowledgements(self):
        acknowledgements = ship.sd_lib.sibling("sd_review_ack_ship_explicit", "sd-review-ack")
        self.prepare()
        prior = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"}, "commit_id": prior,
            "body": "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (2 votes): fix. |\n",
        }]
        (self.root / "src.py").write_text("value = 2\n")
        _git(self.root, "commit", "-am", "answer finding\n\nAuthored-with: human")
        self.double.lose_copilot_request = True
        with self.assertRaisesRegex(ship.Refusal, "review request transport failed"):
            self.prepare("--copilot-review", "request")
        recorded = list(acknowledgements.read_store(self.root)[0].values())
        self.assertEqual([row["path"] for row in recorded], ["src.py"])
        self.assertEqual(self.operation().state["phase"], "ready_to_send")

    def test_invalid_new_prepare_creates_no_receipt_or_suppression(self):
        self.enable_automatic_copilot()
        with self.assertRaisesRegex(ship.Refusal, "provide a final --title"):
            self.prepare("--copilot-review", "skip", "--title", "WIP incomplete")
        self.assertEqual(self.operation().state, {})

    def test_invalid_retry_does_not_mutate_the_existing_receipt(self):
        self.enable_automatic_copilot()
        self.prepare("--copilot-review", "skip")
        before = self.operation().state
        with self.assertRaisesRegex(ship.Refusal, "provide a final --title"):
            self.prepare("--copilot-review", "request", "--title", "WIP incomplete")
        self.assertEqual(self.operation().state, before)

    def test_automatic_copilot_excludes_guest_mode(self):
        self.enable_automatic_copilot()
        self.set_written_mode("guest")
        result = self.prepare()
        self.assertEqual(result["copilot_review"]["reason"], "repository mode is guest")
        self.assertEqual(self.double.copilot_requests, [])

    def test_automatic_copilot_excludes_minimal_mode(self):
        self.enable_automatic_copilot()
        self.set_written_mode("minimal")
        result = self.prepare()
        self.assertEqual(result["copilot_review"]["reason"], "repository mode is minimal")
        self.assertEqual(self.double.copilot_requests, [])

    def test_explicit_copilot_requires_full_mode(self):
        self.set_written_mode("guest")
        with self.assertRaisesRegex(ship.Refusal, "requires a full-owned repository"):
            self.prepare("--copilot-review", "request")
        self.assertEqual(self.double.copilot_requests, [])
        self.assertEqual(self.operation().state, {})

    def test_automatic_copilot_excludes_draft_pull_requests(self):
        self.enable_automatic_copilot()
        self.double.create_draft = True
        result = self.prepare()
        self.assertEqual(result["copilot_review"]["reason"], "automatic Copilot review excludes drafts")
        self.assertEqual(self.double.copilot_requests, [])

    def test_failing_local_review_prevents_automatic_copilot_dispatch(self):
        self.enable_automatic_copilot()
        provider = self.programs / "review-fixture"
        payload = {"type": "result", "subtype": "success", "structured_output": {"findings": [{
            "path": "src.py", "line": 1, "severity": "high",
            "family": "correctness", "summary": "value is wrong",
        }]}}
        provider.write_text("#!/usr/bin/env python3\nimport json\nprint(" + repr(json.dumps(payload)) + ")\n")
        with self.assertRaisesRegex(ship.Refusal, "local review blocking"):
            self.prepare()
        self.assertEqual(self.double.copilot_requests, [])
        self.assertEqual(self.remote.pull_requests, {})

    def test_explicit_request_recovers_a_disappeared_request(self):
        first = self.prepare("--copilot-review", "request")
        self.double.copilot_pending.clear()
        second = self.prepare("--copilot-review", "request")
        self.assertEqual(first["copilot_review"]["decision"], "recorded")
        self.assertEqual(second["copilot_review"]["decision"], "recovered")
        self.assertEqual(len(self.double.copilot_requests), 2)

    def test_copilot_request_count_is_bounded_per_pull_request(self):
        operation = self.operation("prepare", "--copilot-review", "request")
        operation.state["copilot_reviews"] = [{
            "pull": 1,
            "head": str(index) * 40,
            "selection": "explicit",
            "status": "completed",
        } for index in (1, 2, 3)]
        with self.assertRaisesRegex(ship.Refusal, "limit of 3"):
            operation.prepare_copilot_review(1, {"draft": False}, "4" * 40, "full")

    def test_copilot_findings_require_disposition_before_merge(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (2 votes): verify the value. |\n",
        }]
        with self.assertRaisesRegex(ship.Refusal, "remain unacknowledged"):
            with patch.object(ship.time, "sleep"):
                self.merge()

    def test_remote_copilot_request_does_not_gate_without_a_local_request_receipt(self):
        self.enable_automatic_copilot()
        self.prepare()
        self.operation().save(copilot_reviews=[])
        self.assertEqual(self.merge()["phase"], "merged")

    def test_selected_automatic_review_adopts_an_existing_remote_request(self):
        self.enable_automatic_copilot()
        self.double.copilot_pending.add(1)
        prepared = self.prepare()
        self.assertEqual(prepared["copilot_review"]["status"], "pending")
        self.assertEqual(len(self.operation().state["copilot_reviews"]), 1)
        with self.assertRaisesRegex(ship.Refusal, "has not completed"):
            self.merge()

    def test_explicit_review_adopts_an_existing_remote_request(self):
        self.double.copilot_pending.add(1)
        prepared = self.prepare("--copilot-review", "request")
        self.assertEqual(prepared["copilot_review"]["selection"], "explicit")
        self.assertEqual(prepared["copilot_review"]["status"], "pending")
        with self.assertRaisesRegex(ship.Refusal, "has not completed"):
            self.merge()

    def test_abandonment_stops_completion_wait_and_preserves_request_history(self):
        self.enable_automatic_copilot()
        self.prepare()
        requests = self.operation().state["copilot_reviews"]
        result = self.merge("--abandon-copilot-review", "provider did not complete")
        self.assertEqual(result["phase"], "merged")
        state = self.operation().state
        self.assertEqual(state["copilot_reviews"], requests)
        self.assertEqual(state["copilot_review_abandonments"][0]["pull"], 1)
        self.assertEqual(state["copilot_review_abandonments"][0]["head"], _git(self.root, "rev-parse", "HEAD"))
        self.assertEqual(state["copilot_review_abandonments"][0]["reason"], "provider did not complete")
        self.assertRegex(state["copilot_review_abandonments"][0]["request_digest"], r"^[0-9a-f]{64}$")

    def test_abandonment_requires_a_nonempty_reason(self):
        self.enable_automatic_copilot()
        self.prepare()
        with self.assertRaisesRegex(ship.Refusal, "requires a nonempty reason"):
            self.merge("--abandon-copilot-review", "   ")
        self.assertNotIn("copilot_review_abandonments", self.operation().state)

    def test_abandonment_does_not_clear_published_copilot_findings(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"}, "commit_id": head, "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (2 votes): verify. |\n",
        }]
        with self.assertRaisesRegex(ship.Refusal, "remain unacknowledged"):
            with patch.object(ship.time, "sleep"):
                self.merge("--abandon-copilot-review", "provider result is no longer required")

    def test_completion_during_failed_merge_does_not_duplicate_abandonment(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"}, "commit_id": head, "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (2 votes): verify. |\n",
        }]
        reason = "provider result is no longer required"
        for _ in range(2):
            with self.assertRaisesRegex(ship.Refusal, "remain unacknowledged"):
                with patch.object(ship.time, "sleep"):
                    self.merge("--abandon-copilot-review", reason)
            state = self.operation().state
            self.assertEqual(state["copilot_reviews"][0]["status"], "completed")
            self.assertEqual(len(state["copilot_review_abandonments"]), 1)

    def test_later_head_can_abandon_the_latest_request_after_dispatch_failure(self):
        self.enable_automatic_copilot()
        self.prepare()
        _git(self.root, "commit", "--allow-empty", "-m", "later fix\n\nAuthored-with: human")
        head = _git(self.root, "rev-parse", "HEAD")
        self.prepare()
        pull = self.remote.pull(1)
        pull.checks = [{**row, "head_sha": head} for row in pull.checks]
        self.double.copilot_pending.clear()
        self.double.lose_copilot_request = True
        with self.assertRaisesRegex(ship.Refusal, "review request transport failed"):
            self.prepare("--copilot-review", "request")
        result = self.merge("--abandon-copilot-review", "later-head dispatch failed")
        self.assertEqual(result["phase"], "merged")
        state = self.operation().state
        self.assertEqual(len(state["copilot_reviews"]), 1)
        self.assertEqual(state["copilot_review_abandonments"][0]["head"], head)

    def test_later_head_can_abandon_the_latest_request_after_request_cap(self):
        self.enable_automatic_copilot()
        self.prepare()
        operation = self.operation()
        requests = operation.state["copilot_reviews"]
        operation.save(copilot_reviews=[*requests, *[{
            "pull": 1, "head": str(index) * 40, "selection": "explicit",
            "status": "completed", "requested_at": f"2026-09-19T20:0{index}:00Z",
        } for index in (2, 3)]])
        _git(self.root, "commit", "--allow-empty", "-m", "later fix\n\nAuthored-with: human")
        head = _git(self.root, "rev-parse", "HEAD")
        self.prepare()
        pull = self.remote.pull(1)
        pull.checks = [{**row, "head_sha": head} for row in pull.checks]
        self.double.copilot_pending.clear()
        with self.assertRaisesRegex(ship.Refusal, "limit of 3") as caught:
            self.prepare("--copilot-review", "request")
        self.assertIn("abandon", caught.exception.workflow["next_action"])
        result = self.merge("--abandon-copilot-review", "request cap reached")
        self.assertEqual(result["phase"], "merged")
        state = self.operation().state
        abandonment = state["copilot_review_abandonments"][0]
        self.assertEqual(abandonment["head"], head)
        self.assertEqual(abandonment["request_digest"], self.operation().copilot_abandonment_digest(
            state["copilot_reviews"], head))

    def test_abandonment_refuses_without_a_local_request_receipt(self):
        self.prepare()
        with self.assertRaisesRegex(ship.Refusal, "no locally recorded Copilot review request"):
            self.merge("--abandon-copilot-review", "there is no request")
        self.assertNotIn("copilot_review_abandonments", self.operation().state)

    def test_later_request_on_same_head_supersedes_an_abandonment(self):
        self.enable_automatic_copilot()
        self.prepare()
        operation = self.operation("merge", "--manual", "--expected-head", _git(self.root, "rev-parse", "HEAD"),
                                   "--abandon-copilot-review", "first request did not complete")
        operation.abandon_copilot_review(1, _git(self.root, "rev-parse", "HEAD"))
        self.double.copilot_pending.clear()
        self.prepare("--copilot-review", "request")
        with self.assertRaisesRegex(ship.Refusal, "has not completed"):
            self.merge()

    def test_runner_authority_cannot_abandon_a_copilot_request(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        operation = self.operation("merge", "--run", "fixture-run", "--expected-head", head,
                                   "--abandon-copilot-review", "runner chose to stop waiting")
        with self.assertRaisesRegex(ship.Refusal, "requires explicit manual merge authority"):
            operation.merge()

    def test_abandoned_completed_review_marks_matching_receipt_complete(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"}, "commit_id": head, "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z", "body": "",
        }]
        with patch.object(ship.time, "sleep"):
            self.assertEqual(self.merge(
                "--abandon-copilot-review", "completion arrived after the decision")["phase"], "merged")
        state = self.operation().state
        self.assertEqual(state["copilot_reviews"][0]["status"], "completed")
        self.assertEqual(len(state["copilot_review_abandonments"]), 1)

    def test_remote_copilot_findings_block_without_a_local_request_receipt(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.operation().save(copilot_reviews=[])
        self.double.copilot_pending.clear()
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (2 votes): verify the value. |\n",
        }]
        with self.assertRaisesRegex(ship.Refusal, "remain unacknowledged"):
            with patch.object(ship.time, "sleep"):
                self.merge()

    def test_human_review_comments_do_not_become_copilot_findings(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "",
        }, {
            "user": {"login": "human-reviewer"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:01Z",
            "body": "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (1 vote): human note. |\n",
        }]
        human = {"id": 7, "user": {"login": "human-reviewer"},
                 "path": "src.py", "line": 1, "in_reply_to_id": None,
                 "body": "This human finding remains open."}
        self.double.review_sequences["comments"] = [[], [human], [human]]
        with patch.object(ship.time, "sleep"):
            self.assertEqual(self.merge()["phase"], "merged")

    def test_copilot_inline_comment_requires_disposition(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "",
        }]
        self.double.review_payload["comments"] = [{
            "id": 8,
            "user": {"login": "Copilot"},
            "commit_id": head,
            "path": "src.py",
            "line": 1,
            "in_reply_to_id": None,
            "body": "Copilot inline finding remains open.",
        }]
        with self.assertRaisesRegex(ship.Refusal, "remain unacknowledged"):
            with patch.object(ship.time, "sleep"):
                self.merge()

    def test_pending_copilot_review_does_not_clear_merge(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "commit_id": head,
            "state": "PENDING",
            "submitted_at": None,
            "body": "",
        }]
        with self.assertRaisesRegex(ship.Refusal, "has not completed"):
            self.merge()

    def test_missing_copilot_review_head_has_a_precise_refusal(self):
        self.enable_automatic_copilot()
        self.prepare()
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"},
            "commit_id": "a" * 40,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "",
        }]
        with self.assertRaisesRegex(ship.Refusal, "unavailable in local Git history"):
            self.merge()

    def test_latest_nonancestor_copilot_review_cannot_fall_back_to_an_older_one(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        _git(self.root, "checkout", "-b", "unrelated", "origin/main")
        _git(self.root, "commit", "--allow-empty", "-m", "unrelated\n\nAuthored-with: human")
        unrelated = _git(self.root, "rev-parse", "HEAD")
        _git(self.root, "checkout", "topic")
        self.double.review_payload["reviews"] = [{
            "user": {"login": "Copilot"},
            "commit_id": head,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:00:00Z",
            "body": "",
        }, {
            "user": {"login": "Copilot"},
            "commit_id": unrelated,
            "state": "COMMENTED",
            "submitted_at": "2026-09-19T20:01:00Z",
            "body": "",
        }]
        with self.assertRaisesRegex(ship.Refusal, "not an ancestor"):
            self.merge()

    def test_late_copilot_findings_are_included_before_merge(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        base = {"user": {"login": "copilot-pull-request-reviewer[bot]"},
                "commit_id": head, "state": "COMMENTED",
                "submitted_at": "2026-09-19T20:00:00Z"}
        finding = "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (2 votes): late result. |\n"
        self.double.review_sequences["reviews"] = [
            [{**base, "body": ""}],
            [{**base, "body": finding}],
            [{**base, "body": finding}],
        ]
        with self.assertRaisesRegex(ship.Refusal, "remain unacknowledged"):
            with patch.object(ship.time, "sleep"):
                self.merge()

    def test_final_late_update_refuses_an_unstable_review_snapshot(self):
        self.enable_automatic_copilot()
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        base = {"user": {"login": "copilot-pull-request-reviewer[bot]"},
                "commit_id": head, "state": "COMMENTED",
                "submitted_at": "2026-09-19T20:00:00Z"}
        late = "| File | Summary |\n|---|---|\n| `src.py` | Moderate finding (2 votes): final result. |\n"
        self.double.review_sequences["reviews"] = [
            [{**base, "body": ""}],
            [{**base, "body": ""}],
            [{**base, "body": late}],
        ]
        with self.assertRaisesRegex(ship.Refusal, "did not stabilize"):
            with patch.object(ship.time, "sleep"):
                self.merge()

    def test_prepare_records_the_review_findings_its_push_answers(self):
        """The write that was missing between a review and a merge.

        `sd-status` reports a pull request carrying a review finding nobody has
        answered, and nothing on the way to a merge ever wrote an
        acknowledgement, so the row stood on every reviewed pull request. Here
        the reviewer states two findings, the next push answers one of them,
        and only that one is recorded -- a `prepare` that acknowledged both
        would clear the row for the act of pushing.
        """
        acknowledgements = ship.sd_lib.sibling("sd_review_ack_ship_case", "sd-review-ack")
        self.prepare()
        self.double.review_payload["reviews"] = [{
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "commit_id": _git(self.root, "rev-parse", "HEAD"),
            "body": ("| File | Summary |\n|---|---|\n"
                     "| `src.py` | Moderate finding (2 votes): the value is wrong. |\n"
                     "| `Makefile` | Moderate finding (1 vote): nobody went near this. |\n"),
        }]
        (self.root / "src.py").write_text("value = 2\n")
        _git(self.root, "commit", "-am", "answer the finding\n\nAuthored-with: human")
        answered = _git(self.root, "rev-parse", "HEAD")
        result = self.prepare()
        recorded = list(acknowledgements.read_store(self.root)[0].values())
        self.assertEqual([row["path"] for row in recorded], ["src.py"])
        self.assertEqual(recorded[0]["disposition"], "fixed")
        self.assertEqual(recorded[0]["commit"], answered)
        self.assertIn("recorded 1 review finding(s) on #1 as fixed", "\n".join(result["warnings"]))

    def test_a_review_github_will_not_enumerate_warns_and_never_refuses(self):
        """Bookkeeping may not stop a push that has already happened."""
        self.prepare()
        self.double.review_payload["reviews"] = {"message": "Not Found"}
        (self.root / "src.py").write_text("value = 2\n")
        _git(self.root, "commit", "-am", "answer the finding\n\nAuthored-with: human")
        result = self.prepare()
        self.assertEqual(result["phase"], "ready_to_send")
        self.assertIn("review findings on #1 were not read", "\n".join(result["warnings"]))

    def test_a_helper_that_will_not_load_warns_and_never_refuses(self):
        """The load is part of the advisory step, not a precondition of the push.

        With the load outside the guard a broken `bin/sd-review-ack` aborted
        `prepare` with a traceback after the push had already happened, which
        is a refusal over bookkeeping wearing a different exception.
        """
        self.prepare()
        real = ship.sd_lib.sibling

        def broken(module_name, filename):
            if filename == "sd-review-ack":
                raise OSError("sd-review-ack cannot be loaded")
            return real(module_name, filename)

        with patch.object(ship.sd_lib, "sibling", side_effect=broken):
            result = self.prepare()
        self.assertEqual(result["phase"], "ready_to_send")
        self.assertIn("were not read (sd-review-ack cannot be loaded)", "\n".join(result["warnings"]))

    def test_a_store_that_cannot_be_read_is_said_on_the_receipt(self):
        """Nothing recorded because the store is broken is not nothing to record."""
        acknowledgements = ship.sd_lib.sibling("sd_review_ack_ship_broken", "sd-review-ack")
        self.prepare()
        self.double.review_payload["reviews"] = [{
            "user": {"login": "copilot-pull-request-reviewer[bot]"},
            "commit_id": _git(self.root, "rev-parse", "HEAD"),
            "body": ("| File | Summary |\n|---|---|\n"
                     "| `src.py` | Moderate finding (2 votes): the value is wrong. |\n"),
        }]
        (self.root / "src.py").write_text("value = 2\n")
        _git(self.root, "commit", "-am", "answer the finding\n\nAuthored-with: human")
        acknowledgements.store_path(self.root).write_text("{not json", encoding="utf-8")
        result = self.prepare()
        self.assertEqual(result["phase"], "ready_to_send")
        warned = "\n".join(result["warnings"])
        self.assertIn("review findings on #1 were read and none recorded", warned)
        self.assertIn("is not valid JSON", warned)
        self.assertEqual(acknowledgements.store_path(self.root).read_text(), "{not json")

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

    def test_a_coowned_remote_merges_when_the_repository_row_says_auto(self):
        """sd:1347 -- the defect, end to end: a merge that used to be impossible.

        `sd-ship merge` refused sd:1337 in `answerbook/mezmo_benchmark` with
        "lets adrianfurlong, ... push too" -- repository ownership, asked at
        merge time, and its third question is false of every co-authored
        repository. The row said `auto` and nothing read it, so the Mezmo lane
        ended at `ready_to_send` and a human merged through the API by hand.

        Here the same remote names a second collaborator, the row says `auto`,
        and the merge lands. The receipt has to say why: a guard was loosened,
        and a reader must be able to tell this from a merge this account owned
        outright, without going back to the remote to find out who else may
        push.
        """

        self.prepare()
        self.remote.collaborators = [{"login": "fixture", "permissions": {"push": True}},
                                     {"login": "someone", "permissions": {"push": True}}]
        result = self.merge()
        self.assertEqual(result["phase"], "merged")
        authority = result["row_authorized_merge"]
        self.assertEqual(authority["runner_merge"], "auto")
        self.assertEqual(authority["other_pushers"], ["someone"])
        self.assertIn("someone", authority["remote_said"])
        self.assertEqual(authority["repository"], ship.slug(self.remote_url))
        # And the same sentence when a separate process reconciles the receipt.
        self.assertEqual(self.operation("reconcile").reconcile()["row_authorized_merge"], authority)

    def test_a_merge_this_account_owns_outright_claims_no_row_authority(self):
        """The regression guard: three yeses consult no row and claim none."""

        self.prepare()
        result = self.merge()
        self.assertEqual(result["phase"], "merged")
        self.assertNotIn("row_authorized_merge", result)

    def test_an_attempt_that_died_after_ownership_authorizes_no_later_merge(self):
        """Durable authority describes the merge dispatched, not the attempt allowed.

        Ownership clearing is not merging. CI, the review gate and the
        protection re-read all run after it and any of them can refuse -- on
        2026-09-22 both branches in flight came back blocking, so this is the
        ordinary case and not a corner. Recording the authority where the
        answer is read leaves it in the receipt of an attempt that never
        merged, and nothing on the ownership-only path takes it back: the next
        merge then reports a row authorization the row never gave for it, and
        `sd-ship reconcile` repeats it in a later process. A false line in an
        audit trail is worse than an absent one, because an absent one sends
        the reader to look.

        Here the first attempt clears ownership under the row and dies at the
        required check. The collaborator then goes, so the retry is owned
        outright and consults no row at all.
        """

        self.prepare()
        self.remote.collaborators = [{"login": "fixture", "permissions": {"push": True}},
                                     {"login": "someone", "permissions": {"push": True}}]
        pull = self.remote.pull(1)
        healthy = [dict(check) for check in pull.checks]
        pull.checks = [{**healthy[0], "conclusion": "failure"}]
        with self.assertRaises(ship.Refusal):
            self.merge()
        pull.checks = healthy
        self.remote.collaborators = [{"login": "fixture", "permissions": {"push": True}}]
        result = self.merge()
        self.assertEqual(result["phase"], "merged")
        self.assertNotIn("row_authorized_merge", result,
                         "an ownership-only merge must not inherit a failed attempt's authority")
        self.assertNotIn("row_authorized_merge", self.operation("reconcile").reconcile())

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
        # sd:1347 -- co-ownership is the one answer the repository row may
        # override, and this fixture's row says `auto`. `manual` is what makes
        # it a refusal again; the override's own case is
        # `test_a_coowned_remote_merges_when_the_repository_row_says_auto`.
        set_runner_merge(self.connection, str(self.operator), "manual")
        self.remote.collaborators = [{"login": "fixture", "permissions": {"push": True}}] * 100 + [{"login": "someone", "permissions": {"push": True}}]
        with self.assertRaisesRegex(ship.Refusal, "someone"):
            self.merge()
        set_runner_merge(self.connection, str(self.operator), "auto")
        self.remote.collaborators = []
        saved = self.remote.protection
        self.remote.protection = None
        # An unprotected branch is a 404 from GitHub. `GitHub.gate` reads the
        # status and, with no declaration at the reviewed head (this fixture
        # commits none), refuses with GitHub's message and the status; the
        # guard that refuses a body that is not an object is reached only
        # from `tests/test_sd_ship_remote.py` (sd:929). The declared-gap path
        # is `DeclaredGapCase` below (sd:1110).
        with self.assertRaisesRegex(ship.Refusal, "Branch not protected"):
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

    def test_a_remote_head_that_moved_before_merge_is_refused_with_no_merge_call(self):
        """The shared readiness guard answers before a merge is ever dispatched.

        `test_moved_head_at_remote_merge_is_refused_atomically` races the head
        *inside* the merge call, so the remote's own 405 is what refuses there.
        This is the earlier question: the branch already moved at the remote
        when the merge is asked for. `GitHub.ready` is the one guard both the
        item-backed and the no-item flow reach, and it has to refuse on the
        pull request's own head without spending a merge call to find out.
        """
        self.prepare()
        self.remote.commit_on("topic", "raced\n\nAuthored-with: human", files={"raced.py": "changed\n"})
        with self.assertRaisesRegex(ship.Refusal, "head or default base moved after local review"):
            self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_the_manual_merge_request_names_the_expected_head_and_a_stale_one_is_refused(self):
        """`--expected-head` has to reach GitHub as the request's own `sha`.

        The documented manual form is `sd-ship merge --item ID --expected-head
        SHA --manual`, and the head it names guards nothing unless the
        dispatched request carries it: GitHub answers 405 when `sha` is not the
        pull request's current head. Both halves are asserted here, that the
        body names the reviewed head, and that a server-side head which no
        longer matches it refuses rather than merges.
        """
        self.prepare()
        head = _git(self.root, "rev-parse", "HEAD")
        self.double.moved = True
        with self.assertRaisesRegex(ship.Refusal, "has not confirmed this pull request merged"):
            self.merge()
        dispatched = [call for call in self.remote.calls if call.method == "PUT"]
        self.assertEqual([call.body["sha"] for call in dispatched], [head])
        self.assertNotEqual(self.remote.pull(1).state, "MERGED")
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

    def unsited(self, command, *extra, library="provisioned"):
        """`bin/sd-ship` under an interpreter that can see no site-packages at all.

        `-S` is the point of the helper. The test run itself necessarily has
        `sd_db` importable, so it is the only honest way to describe the
        machine every developer actually has: a `python3` on PATH that is not
        the pack's virtualenv. Patching `sys.modules` cannot describe it,
        because a name bound to `None` defeats the second attempt as well as
        the first, which is exactly the attempt under test.

        The run happens in a copy of the pack rather than in this checkout so
        that `library` is the only thing that varies between the cases below.
        Pointed at the real `.venv` there would be no way to write the absent
        case at all, and the provisioned case would quietly depend on whether
        CI had run `make setup` before the tests.

        `PYTHONPATH` is set rather than inherited, and `-S` is why that is not
        redundant: no `site` module runs, but the interpreter still reads the
        variable, so a developer or a harness with one pointing at another
        `sd_db` hands the child a library the case did not put there. That is
        not hypothetical -- `.github/scripts/run-tests.sh` exports one, and
        the tests below turned green for the wrong reason under any value of
        it that holds the package. The copied pack's `bin` is what the child
        needs and all it needs, which is the same override the analogous
        `tests/test_status_source.py` cases make.
        """
        pack = self.directory / f"pack-{library}"
        shutil.copytree(ROOT / "bin", pack / "bin")
        site = pack / f".venv/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        site.parent.mkdir(parents=True)
        site.mkdir()
        # A real copy of the package, and deliberately NOT a symlink to
        # `SITE_PACKAGES`. Symlinking the whole directory worked -- the only
        # writes below are in the `broken` arm, which never symlinks -- but it
        # handed a live path into the developer's own virtualenv to a
        # subprocess, one careless future case away from writing through it.
        # That is not hypothetical: it happened while this change was being
        # reviewed, through exactly this shape, and truncated the installed
        # `sd_db/__init__.py`. Copying costs 36ms for 2.1MB and the fixture
        # then owns every byte under `site`. Only `sd_db` is copied, not the
        # 92MB directory around it, which is enough because its dist-info
        # declares no `Requires-Dist`.
        if library == "provisioned":
            # `__pycache__` is excluded rather than copied: `copy2` preserves
            # mtime, so a copied `.pyc` validates against its copied `.py` and
            # the child would load bytecode whose embedded `co_filename` names
            # the original absolute path. Harmless for these three cases --
            # `__file__` comes from the loader, not the bytecode -- but the
            # fixture exists to make the child's library unambiguous, and
            # leaving the question open costs more than the one argument.
            shutil.copytree(SITE_PACKAGES / "sd_db", site / "sd_db",
                            ignore=shutil.ignore_patterns("__pycache__"))
        elif library == "broken":
            # `elif`, so the exclusivity the safety of this rests on is stated
            # rather than left to the caller's three string literals.
            (site / "sd_db").mkdir()
            (site / "sd_db/__init__.py").write_text("raise ImportError('the provisioned copy is broken')\n")
        environment = {**self.environment, "PYTHONPATH": str(pack / "bin")}
        return subprocess.run([sys.executable, "-S", str(pack / "bin/sd-ship"), command, "--item", str(self.item), "--json", *extra],
                              cwd=self.root, env=environment, text=True, capture_output=True, timeout=60)

    def test_a_python3_without_the_library_ships_off_the_provisioned_copy(self):
        """The defect was every verb on every machine, not a verb on a rare one.

        `make setup` provisions `sd_db` into the pack's virtualenv and this
        entrypoint starts `#!/usr/bin/env python3`, so the import at the top
        of `main` failed under every interpreter anyone actually invokes it
        with, and the tool answered "install matching sd_db" about a library
        that was installed. `bin/sd` never showed it because `sd_lib` has
        always made the second attempt; the difference between the two tools
        was six lines, and this asserts they no longer differ.

        Asserting the happy path proves nothing here: run under an
        interpreter that already has the library, the one-try code passes.
        """
        self.prepare()
        result = self.unsited("observe")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(result.stdout)
        self.assertTrue(observed["ok"], result.stdout)
        self.assertEqual(observed["phase"], "ready_to_send")

    def test_a_library_absent_everywhere_still_refuses_in_the_shape_callers_read(self):
        """A machine before `make setup` must get a refusal, not a traceback.

        The fallback is allowed to find the library; it is not allowed to
        change what happens when there is nothing to find. Hooks and skills
        branch on this object rather than on the exit status alone, so the
        shape is the contract and the sentence has to name the library.
        """
        self.prepare()
        result = self.unsited("observe", library="absent")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        refusal = json.loads(result.stdout)
        self.assertFalse(refusal["ok"])
        self.assertTrue(refusal["manualRequired"])
        self.assertIn("sd_db is not installed here", refusal["error"])
        self.assertNotIn("Traceback", result.stderr)

    def test_a_provisioned_copy_that_will_not_import_is_not_called_absent(self):
        """Two faults, two remedies, and the old message named the wrong one.

        A virtualenv holding an `sd_db` that raises on import is not a machine
        without the library, and telling its reader to install one sends them
        to `make setup` for a package already sitting there. The refusal is
        the same shape as the one above -- what differs is the sentence.
        """
        self.prepare()
        result = self.unsited("observe", library="broken")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        refusal = json.loads(result.stdout)
        self.assertFalse(refusal["ok"])
        self.assertTrue(refusal["manualRequired"])
        self.assertIn("the provisioned copy is broken", refusal["error"])
        self.assertIn("will not import", refusal["error"])
        self.assertNotIn("is not installed here", refusal["error"])

    def test_the_three_library_cases_do_not_read_an_sd_db_from_the_run_around_them(self):
        """The three above describe machines, so no ambient variable may pick one.

        `-S` stops `site` from running; it does not stop the interpreter from
        reading `PYTHONPATH`. Inherit that from the test run and the child's
        library is whatever the developer or the harness happened to export:
        with an `sd_db` on it the absent case imports one and stops being
        absent, the broken case never reaches the copy it broke, and the
        provisioned case passes without the fallback it exists to prove --
        three green tests asserting nothing about the code under them.

        A stub is enough to show it. The cases turn on *which* `sd_db`
        answers, and a package with no `ship` submodule is a different answer
        from the pack's copy in every one of the three.
        """
        decoy = self.directory / "decoy"
        (decoy / "sd_db").mkdir(parents=True)
        (decoy / "sd_db/__init__.py").write_text("# importable, and not the pack's library\n")
        self.environment["PYTHONPATH"] = str(decoy)
        self.prepare()

        absent = self.unsited("observe", library="absent")
        self.assertEqual(absent.returncode, 3, absent.stdout + absent.stderr)
        self.assertIn("sd_db is not installed here", json.loads(absent.stdout)["error"])

        broken = self.unsited("observe", library="broken")
        self.assertEqual(broken.returncode, 3, broken.stdout + broken.stderr)
        self.assertIn("the provisioned copy is broken", json.loads(broken.stdout)["error"])

        provisioned = self.unsited("observe")
        self.assertEqual(provisioned.returncode, 0, provisioned.stdout + provisioned.stderr)
        self.assertEqual(json.loads(provisioned.stdout)["phase"], "ready_to_send")

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
            cancel_work(self.connection, self.item, reason="stop", who="user")
        with self.assertRaisesRegex(WorkflowError, "manual merge authority"):
            receipts.manual_merge_guard(self.connection, str(self.operator))

    def test_changed_acceptance_scope_refuses_before_spending_a_fix_review(self):
        from sd_db import set_item_fields
        acceptance = self.directory / "acceptance.json"
        acceptance.write_text(json.dumps({"item": self.item, "complete": True, "criteria": [
            {"criterion": "actual scope", "passed": True, "evidence": "fixture-check-pass"}]}))
        self.prepare("--deliver", "--acceptance-file", str(acceptance))
        before = self.operation().state
        set_item_fields(self.connection, self.item, body="new scope")
        with self.assertRaisesRegex(ship.Refusal, "acceptance scope changed"):
            self.prepare()
        self.assertEqual(self.operation().state, before)

    def test_author_assignment_cannot_borrow_manual_merge_authority(self):
        from sd_db.workflow import WorkflowError
        self.prepare()
        create_assignment(self.connection, item=self.item, role="author", status="running")
        with self.assertRaisesRegex(WorkflowError, "manual merge authority"):
            self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_standing_review_revocation_invalidates_receipt_but_unrelated_settings_do_not(self):
        config = self.home / ".config/sd-ai-command-pack/config.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        self.prepare()
        operation = self.operation()
        head = _git(self.root, "rev-parse", "HEAD")
        config.write_text('{"config":{"sd":{"external_reviews":"configured","assistant_merge":"controlled"}},"unrelated":1}')
        operation.check_review(head)
        config.write_text('{"config":{"sd":{"external_reviews":"deny"}}}')
        with self.assertRaisesRegex(ship.Refusal, "policy changed"):
            self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_absent_to_dangling_local_config_cannot_reuse_a_completed_review(self):
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

    def set_written_mode(self, word):
        local = self.root / "CLAUDE.local.md"
        local.write_text(local.read_text().replace("mode: full", f"mode: {word}"))

    def test_written_guest_mode_has_no_merge_authority(self):
        self.set_written_mode("guest")
        self.assertEqual(self.prepare()["phase"], "ready_to_send")
        with self.assertRaisesRegex(ship.Refusal, "guest mode has no merge authority"):
            self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_merge_authority_reads_the_one_validated_mode_line(self):
        """The merge-authority check reads `sd_lib.written_mode`, not the raw line (sd:930).

        On the real path a `mode:` word that is not a mode never reaches the
        check: `prepare` refuses it through `resolve_mode`, and a line changed
        after `prepare` trips the binding in `check_review` first. So this
        test stands the binding guard down to put the misspelled word in front
        of the check itself, and asks that the check name the word the way
        every other reader of the line does, rather than compare it to
        `"guest"` and let it through.
        """
        self.prepare()
        self.set_written_mode("gust")
        with patch.object(ship.Ship, "check_review", return_value=None):
            with self.assertRaisesRegex(ship.sd_lib.ConfigError, "mode 'gust' is not one of"):
                self.merge()
        self.assertFalse(any(call.method == "PUT" for call in self.remote.calls))

    def test_delivery_clone_identity_cannot_be_replaced(self):
        from sd_db.progress import deliver_work
        from sd_db.workflow import WorkflowError
        self.prepare()
        result = self.merge()
        _git(self.root, "remote", "set-url", "origin", "https://github.com/other/repo.git")
        with self.assertRaisesRegex(WorkflowError, "origin does not match"):
            deliver_work(self.connection, self.item, result["merge_commit"], who="sd-ship", verification_root=self.root)

    def test_forged_delivery_trailer_cannot_turn_a_slice_into_completion(self):
        body = self.directory / "body.txt"
        body.write_text(f"A slice\n\nDelivers: sd:{self.item}\n")
        with self.assertRaisesRegex(ship.Refusal, "owns association"):
            self.prepare("--body-file", str(body))
        self.assertFalse(any(call.method == "POST" for call in self.remote.calls))

    def test_fix_verifications_keep_prior_findings_and_refuse_a_pass_past_the_cap(self):
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
        for count in range(3, CAP + 1):
            previous = self.operation().state["passes"][-1]
            _git(self.root, "commit", "--allow-empty", "-m", f"change {count}\n\nAuthored-with: human")
            prepared = self.prepare()
            state = self.operation().state
            self.assertEqual(len(state["passes"]), count)
            self.assertEqual(state["passes"][-1]["report"]["subject"]["base"], previous["head"])
            self.assertEqual(state["passes"][-1]["report"]["verification_report_digest"],
                             ship.digest(previous["report"]))
        self.assertEqual(state["passes"][0]["report"]["findings"][0]["summary"], "value is wrong")
        _git(self.root, "commit", "--allow-empty", "-m", "past the cap\n\nAuthored-with: human")
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
        assignment = runner.enqueue(self.connection, [self.item], role="merge", who="user")[0]
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
        # The aggregate, not the first pass's report on its own. That pass
        # completed no review, so it superseded nothing and the retry resumes
        # everything before it. The two carry the same findings here; what
        # changed is which object is the evidence's identity.
        self.assertEqual(report["resume_report_digest"],
                         ship.digest(ship.review_history([first])))
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

    def test_retry_cannot_spend_a_pass_past_the_cap(self):
        provider = self.programs / "review-fixture"
        provider.write_text("#!/usr/bin/env python3\nprint('not a review')\n")
        with self.assertRaises(ship.Refusal):
            self.prepare()
        for _ in range(CAP - 1):
            with self.assertRaises(ship.Refusal):
                self.prepare("--retry-review")
        with self.assertRaisesRegex(ship.Refusal, "spent"):
            self.prepare("--retry-review")
        self.assertEqual(len(self.operation().state["passes"]), CAP)
        self.assertEqual(len(self.remote.pull_requests), 0)

    def test_retry_flag_cannot_replace_a_complete_review(self):
        self.prepare()
        _git(self.root, "commit", "--allow-empty", "-m", "fix\n\nAuthored-with: human")
        with self.assertRaisesRegex(ship.Refusal, "only an incomplete"):
            self.prepare("--retry-review")

    def spent_reviews(self, blockers=False):
        provider = self.programs / "review-fixture"
        working = provider.read_text()
        for index in range(CAP):
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
        self.assertEqual(state["passes"][:CAP], prior)
        self.assertEqual(len(state["passes"]), CAP + 1)
        request = state["passes"][CAP]["additional_review_request"]
        self.assertEqual(request["prior_history_digest"], ship.digest(prior))
        self.assertEqual(request["head"], _git(self.root, "rev-parse", "HEAD"))
        report = state["passes"][CAP]["report"]
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

    def test_the_pass_after_the_cap_refuses_and_an_explicit_request_still_admits_it(self):
        """The boundary itself, from both sides.

        The automatic allowance is the table's cap and no more: the pass after
        it is refused before any dispatch. The explicit-request mechanism is
        untouched by the raise and still opens exactly one further pass.
        """
        provider, working, prior = self.spent_reviews(blockers=True)
        self.assertEqual(len(prior), CAP)
        _git(self.root, "commit", "--allow-empty", "-m", "resolve findings\n\nAuthored-with: human")
        provider.write_text(working)
        head = _git(self.root, "rev-parse", "HEAD")
        operation = self.operation("prepare")
        with patch.object(ship.subprocess, "run", side_effect=AssertionError("review dispatched")):
            with self.assertRaisesRegex(ship.Refusal, "spent"):
                operation.review(head)
        self.assertEqual(self.operation().state["passes"], prior)
        self.additional()
        state = self.operation().state
        self.assertEqual(state["passes"][:CAP], prior)
        self.assertEqual(len(state["passes"]), CAP + 1)
        self.assertEqual(state["passes"][CAP]["additional_review_request"]["prior_history_digest"],
                         ship.digest(prior))

    def test_additional_failed_reservation_remains_spent_and_cannot_be_reused(self):
        _, _, prior = self.spent_reviews()
        with self.assertRaises(ship.Refusal):
            self.additional()
        saved = self.operation().state["passes"]
        self.assertEqual(saved[:CAP], prior)
        self.assertEqual(len(saved), CAP + 1)
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
        self.assertEqual(len(self.operation().state["passes"]), CAP)

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
        self.assertEqual(state["passes"][:CAP], prior)
        self.assertEqual(len(state["passes"]), CAP + 1)
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

    def test_renewed_reviews_past_the_cap_preserve_each_prefix_and_full_branch(self):
        provider, working, prior = self.spent_additional()
        provider.write_text(working)
        for count in (CAP + 2, CAP + 3):
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
            entry = state["passes"][CAP]
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
                operation.state["passes"][CAP].pop("additional_review_request")
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

    def test_renewal_digest_is_not_accepted_while_the_cap_is_only_just_spent(self):
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
        self.assertEqual(trace, ["check", "provider"])
        self.assertEqual(len(state["passes"]), 1)
        self.assertEqual(state["passes"][0]["report"]["completed_reviews"], 1)

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
            self.assertEqual(report["requested_reviews"], 1)
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

    def test_one_eligible_reviewer_can_complete_the_local_pass(self):
        import sd_registry
        registry = sd_registry.read_file(self.database.parent / "providers.yaml")
        consent = str(sd_registry.recipient(registry.providers["reviewer"]))
        (self.root / "CLAUDE.local.md").write_text(
            "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->\nmode: full\n"
            f"reviewers: {consent}\n<!-- SD-AI-COMMAND-PACK:LOCAL:END -->\n")
        result = self.prepare()
        self.assertEqual(result["phase"], "ready_to_send")
        report = self.operation().state["passes"][0]["report"]
        self.assertEqual(report["completed_reviews"], 1)

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
        reports = []
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
            reports.append(report)
            return subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
        with patch.object(ship, "review_process", side_effect=child), self.assertRaisesRegex(ship.Refusal, "input_oversized"):
            operation.review(head)
        self.assertEqual(stages, [True])
        failed = self.operation().state
        self.assertEqual(failed["passes"], before["passes"])
        self.assertEqual(failed["reviewed_head"], before["reviewed_head"])
        self.assertEqual(reports[0]["readiness"]["status"], "blocked")
        self.assertEqual(reports[0]["readiness"]["blockers"][0]["code"], "input_oversized")
        diagnostic = failed["review_preflight_error"]
        self.assertEqual(diagnostic["stdout"]["sha256"], ship.hashlib.sha256(json.dumps(reports[0]).encode()).hexdigest())
        self.assertEqual((diagnostic["exit_code"], diagnostic["stderr"]["tail"]), (0, ""))
        prior[0]["report"]["findings"][0]["summary"] = "bounded blocker"
        operation.save(passes=prior)
        valid = {"status": "explained", "requested_reviews": 1,
                 "readiness": {"status": "ready", "blockers": [], "warnings": [], "runtime_approval": "not_observable"},
                 "timing": {"phase_seconds": 1800, "setup_seconds": 3600,
                 "execution_seconds": 7200, "candidates": [{"name": "fixture", "recipient": "fixture@fixture"}]}}
        answers = [subprocess.CompletedProcess([], 0, json.dumps(valid), ""), subprocess.CompletedProcess([], 2, "", "failed")]
        with patch.object(ship, "review_process", side_effect=answers), self.assertRaisesRegex(ship.Refusal, "reserved pass remains recorded"):
            operation.review(head)
        saved = self.operation().state
        self.assertEqual(saved["passes"][:-1], prior)
        self.assertEqual(len(saved["passes"]), CAP + 1)
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
            report["authored_with"] = ["secondvendor", "thirdvendor"]
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
        self.assertEqual(latest["completed_reviews"], 1)
        self.assertEqual(latest["authored_with"], ["secondvendor", "thirdvendor"])
        self.assertEqual(latest["reviewed_by"], ["reviewer3"])

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

    @staticmethod
    def nested(depth: int) -> bytes:
        """A report whose deepest container sits `depth` levels down."""
        return ('{"deep":' + '[' * (depth - 1) + '0' + ']' * (depth - 1) + '}').encode()

    def expired(self, body: bytes) -> dict:
        process = unittest.mock.Mock(pid=123)
        process.communicate.side_effect = [subprocess.TimeoutExpired([], 1), (body, b""), (body, b"")]
        process.poll.return_value = 0
        with patch.object(ship.subprocess, "Popen", return_value=process), patch.object(ship.os, "killpg"):
            with self.assertRaises(ship.ReviewTimeout) as raised:
                ship.review_process(self.root, ["fixture"], timeout=1)
        return raised.exception.diagnostic

    def test_deep_captured_json_stays_a_typed_timeout(self):
        # One level past the limit this file states, not past whatever the
        # running interpreter's C recursion guard happens to allow. At 10000
        # -- what this fixture used until sd:818 -- the refusal came from
        # `json.loads` on 3.13 and did not come at all on 3.14, so the test
        # read the interpreter rather than the rule.
        body = self.nested(ship.REVIEW_CAPTURE_DEPTH + 1)
        diagnostic = self.expired(body)
        self.assertNotIn("captured_report", diagnostic)
        # `cleanup` names why each of its own steps failed; a dropped capture
        # is named the same way, or the receipt cannot tell a report refused
        # for depth from output that was never JSON at all.
        self.assertEqual(diagnostic["captured_report_refused"],
                         f"nesting deeper than {ship.REVIEW_CAPTURE_DEPTH}")
        self.assertEqual(diagnostic["stdout"]["bytes"], len(body))

    def test_output_that_is_not_json_is_not_reported_as_too_deep(self):
        # The other half of the sentence above. Naming depth is only useful if
        # depth is the only thing it names: output the review never meant as a
        # report must leave the receipt silent rather than accuse it of nesting.
        diagnostic = self.expired(b"review aborted: provider unreachable\n")
        self.assertNotIn("captured_report", diagnostic)
        self.assertNotIn("captured_report_refused", diagnostic)

    def test_an_oversize_body_is_refused_by_name_and_the_largest_admitted_one_is_kept(self):
        # The size bound is older than the depth one and sits outside it, and
        # until sd:837 it was the one refusal that stayed silent: a 2 MB report
        # left the receipt looking exactly like a review that emitted nothing.
        # The sentence names the budget and what was measured against it, as
        # the depth one names the depth. `stdout.bytes` already carries the
        # length, but a reader of the refusal should not have to correlate two
        # fields to learn why the report is not there.
        cap = ship.REVIEW_CAPTURE_BYTES
        frame = b'{"pad":"' + b'"}'
        largest = b'{"pad":"' + b"x" * (cap - len(frame)) + b'"}'
        self.assertEqual(len(largest), cap)
        self.assertEqual(self.expired(largest)["captured_report"], json.loads(largest))
        oversize = largest[:-2] + b'x"}'
        self.assertEqual(len(oversize), cap + 1)
        diagnostic = self.expired(oversize)
        self.assertNotIn("captured_report", diagnostic)
        self.assertEqual(diagnostic["captured_report_refused"], f"{cap + 1} bytes, more than {cap}")
        self.assertEqual(diagnostic["stdout"]["bytes"], cap + 1)

    def test_json_that_is_not_an_object_is_refused_by_its_kind(self):
        # A review's stdout that decodes but is not an object was dropped at
        # `isinstance(captured, dict)` since #802, explicitly and silently. The
        # decoder said what it found, so the receipt says it too, in JSON's
        # own names rather than Python's: a reader of the receipt is looking
        # at a review's output, not at an interpreter.
        cases = ((b"[1]", "array"), (b'"report"', "string"), (b"42", "number"),
                 (b"4.2", "number"), (b"true", "boolean"), (b"null", "null"))
        for body, kind in cases:
            with self.subTest(body=body):
                diagnostic = self.expired(body)
                self.assertNotIn("captured_report", diagnostic)
                self.assertEqual(diagnostic["captured_report_refused"], f"a JSON {kind}, not an object")

    def test_captured_json_at_the_depth_limit_is_still_evidence(self):
        body = self.nested(ship.REVIEW_CAPTURE_DEPTH)
        self.assertEqual(self.expired(body)["captured_report"], json.loads(body))

    def test_a_report_with_more_findings_than_the_limit_is_still_evidence(self):
        # The shape the limit must never refuse, end to end. `sd-review` caps
        # each provider's response at MAX_FINDINGS (50) and merges every
        # provider's rows into one list, so a report grows wide long before it
        # grows deep: these 150 findings are three responses' worth, and 3
        # levels deep. A reader that counted containers instead of nesting
        # would drop exactly this, and drop it silently.
        body = json.dumps({"scope": "branch", "subject": {"head": "a" * 40},
                           "findings": [{"path": "bin/sd-ship", "line": n} for n in range(150)],
                           "authored_with": ["claude"]}).encode()
        self.assertFalse(ship.capture_too_deep(body, limit=3))
        self.assertEqual(self.expired(body)["captured_report"], json.loads(body))

    def test_brackets_inside_a_string_are_text_and_not_depth(self):
        # A shallow report that quotes some JSON is still evidence. Counting
        # every bracket would refuse it, and the tail it quotes is often the
        # only thing that says what the review was doing when it expired. The
        # leading quote is escaped in the encoded body, so a scan that does not
        # honour escapes ends the string there and counts the rest as depth.
        body = json.dumps({"deep": '"' + "[" * (ship.REVIEW_CAPTURE_DEPTH * 10)}).encode()
        self.assertIn(rb'\"[[[', body)
        self.assertEqual(self.expired(body)["captured_report"], json.loads(body))

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


class CaptureDepthTests(unittest.TestCase):
    """`capture_too_deep` is read directly, not only through the watchdog.

    Until sd:818 the depth rule was CPython's C recursion guard, which is
    correct by construction. This scan replaces it with a reader of our own,
    and a reader can be wrong in two directions: drop a report the operator
    needed, or admit one the limit exists to refuse. Strings are where that
    goes wrong -- #941 had just fixed the same class of bug in the launch
    check's reader of bash quoting -- so each escape case is a row here.
    """

    def test_a_real_shaped_report_is_nowhere_near_the_limit(self):
        # The part of a report `timeout_evidence` reads: the report object,
        # `findings`, a finding -- 3 levels, with `subject` beside `findings`
        # and not under it. It is not as deep as a report gets. Real reports go
        # deeper in fields that reader passes over, 7 in the store on
        # 2026-09-14, which is what `REVIEW_CAPTURE_DEPTH` is measured against.
        # The two limits below keep this comment's "3" honest.
        body = json.dumps({"scope": "branch", "subject": {"head": "a" * 40},
                           "findings": [{"path": "bin/sd-ship", "summary": "x"}],
                           "authored_with": ["claude"]}).encode()
        self.assertTrue(ship.capture_too_deep(body, limit=2))
        self.assertFalse(ship.capture_too_deep(body, limit=3))
        self.assertFalse(ship.capture_too_deep(body))

    def test_the_limit_is_the_deepest_container_that_is_kept(self):
        at_limit = b"[" * ship.REVIEW_CAPTURE_DEPTH + b"0" + b"]" * ship.REVIEW_CAPTURE_DEPTH
        self.assertFalse(ship.capture_too_deep(at_limit))
        self.assertTrue(ship.capture_too_deep(b"[" + at_limit + b"]"))

    def test_every_kind_of_closed_container_gives_its_depth_back(self):
        # Depth is nesting, not a running count of opening brackets. Siblings
        # must not accumulate, or a long findings list is refused for its
        # length rather than its shape.
        #
        # Both kinds, and interleaved. Asserting on `[]` alone left a reader
        # that decrements for `]` and not for `}` passing: braces are what a
        # findings list is actually made of, so that reader refused every real
        # report while this row stayed green (review-950, M6).
        many = ship.REVIEW_CAPTURE_DEPTH * 100
        for body in (b"[]" * many, b"{}" * many, b"[]{}" * many, b"[{}]" * many):
            with self.subTest(body=body[:8]):
                self.assertFalse(ship.capture_too_deep(body))

    def test_brackets_inside_a_string_are_text(self):
        deep = b"[" * (ship.REVIEW_CAPTURE_DEPTH + 1)
        self.assertTrue(ship.capture_too_deep(deep))
        self.assertFalse(ship.capture_too_deep(b'{"quoted":"' + deep + b'"}'))

    def test_an_escaped_quote_does_not_end_a_string(self):
        # A `\"` in the body is a quote in the text, not the end of the string,
        # so what follows it is still text. Read as an ending, the brackets
        # after it become structure and a legitimate report is refused.
        body = rb'{"quoted":"\"' + b"[" * (ship.REVIEW_CAPTURE_DEPTH + 1) + b'"}'
        self.assertEqual(json.loads(body)["quoted"][0], '"')
        self.assertFalse(ship.capture_too_deep(body))

    def test_an_escaped_backslash_leaves_the_closing_quote_closing(self):
        # The mirror case, and the one that fails the other way. A `\\` is a
        # backslash in the text and consumes itself, so the quote after it does
        # end the string and the brackets that follow are structure. A reader
        # that lets that backslash escape the quote hides them, and admits a
        # report past the limit.
        deep = ship.REVIEW_CAPTURE_DEPTH + 1
        body = rb'{"quoted":"x\\","deep":' + b"[" * deep + b"0" + b"]" * deep + b"}"
        self.assertEqual(json.loads(body)["quoted"], "x\\")
        self.assertTrue(ship.capture_too_deep(body))

    def test_an_unterminated_string_swallows_what_follows(self):
        # Under-counting is the safe direction here: an unterminated string is
        # not JSON, so `json.loads` refuses the body a moment later and no
        # report is kept either way. Recorded because it is a real input --
        # output cut off mid-write by the kill the watchdog just sent.
        body = b'{"quoted":"' + b"[" * (ship.REVIEW_CAPTURE_DEPTH + 1)
        self.assertFalse(ship.capture_too_deep(body))
        with self.assertRaises(ValueError):
            json.loads(body)

    def test_the_largest_body_the_gate_admits_is_read_in_one_pass(self):
        # `REVIEW_CAPTURE_BYTES` is the size bound the gate applies before this
        # scan, so these are the worst cases that can reach it. The 60s bound
        # is a guard against a hang and nothing more; a reader that became
        # quadratic is caught by the ratio below, not by this loop.
        cap = ship.REVIEW_CAPTURE_BYTES
        deep = b"[" * (ship.REVIEW_CAPTURE_DEPTH + 1)
        front = deep + b"x" * (cap - len(deep))
        for body in (front,                       # too deep at the first bytes
                     b'"' * cap,                  # nothing but quotes
                     b'"' + b"x" * (cap - 1)):    # one unterminated string
            started = time.monotonic()
            ship.capture_too_deep(body)
            self.assertLess(time.monotonic() - started, 60)
        self.assertTrue(ship.capture_too_deep(front))
        # Eight times the bytes should cost about eight times the work; a reader
        # that copies the rest of the body at every byte (`data[index:][0]`)
        # costs 62 to 77 times as much. That ratio is measured in this thread's
        # CPU time, `time.thread_time`, not on the clock: at load average 107
        # the same scan by wall clock gave the linear reader ratios from 1.6 to
        # 154.3, because the 1 MB scan spans many scheduler slices and the
        # 125 KB scan few, while CPU time gave it 6.0 to 12.0 across sixteen
        # runs on 3.13 and 3.14. The 24 sits between those two ranges.
        small, large = b'"' * 125_000, b'"' * 1_000_000
        small_cpu: list[float] = []
        large_cpu: list[float] = []
        for _ in range(3):
            for body, spent in ((small, small_cpu), (large, large_cpu)):
                started = time.thread_time()
                ship.capture_too_deep(body)
                spent.append(time.thread_time() - started)
        self.assertLess(min(large_cpu) / min(small_cpu), 24)


class DeclaredGapCase(unittest.TestCase):
    """`sd-ship merge` under `.github/sd-status.json`'s `unprotected` entry (sd:1110).

    The rig is `ShipCase`'s with the protection object removed -- borrowed
    method by method rather than inherited, so `ShipCase`'s own tests do not
    run a second time under this name. Every test
    here starts from a 404, commits a declaration (or a wrong one) on the
    branch the merge will land, and answers check runs, statuses and
    workflow runs for the exact head. `PUT` counts are the assertion that
    matters; a refusal that still merged is the failure the item exists to
    prevent.
    """

    TESTS = "name: Tests\n\non:\n  pull_request:\n  push:\n    branches: [main]\n\njobs:\n  unittest:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
    ROUTE = "name: sd-review route\n\non:\n  pull_request:\n\njobs:\n  route:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
    DECLARATION = {
        "accepted_gaps": [{
            "id": "unprotected", "state": {"branch_protection": False},
            "because": "fixture: one operator", "since": "2026-09-12",
            "until": "a second account with push or merge rights exists",
        }]
    }

    args, operation, prepare, merge = ShipCase.args, ShipCase.operation, ShipCase.prepare, ShipCase.merge

    def setUp(self):
        ShipCase.setUp(self)
        self.remote.protection = None
        # Every declaration here commits `.github/workflows/*.yml`, a sensitive
        # path that routes deep, and since sd:1328 a deep change asks Copilot
        # unless something says otherwise. These tests are about check gaps,
        # and the double never completes a Copilot review, so the fixture's
        # machine says `never` rather than letting the default turn every
        # merge below into a wait for a review nobody answers.
        config = self.home / ".config" / ship.sd_lib.CONFIG_RELATIVE_PATH
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('{"config":{"sd":{"copilot_review":"never"}}}')

    def commit(self, files: dict[str, str], message: str = "declare\n\nAuthored-with: human") -> str:
        """Commit `files` on `topic` at the remote and pull them into the clone.

        The reviewed head is what the merge reads, so every fixture file has
        to be in the commit, not the working tree.
        """
        sha = self.remote.commit_on("topic", message, files=files)
        _git(self.root, "fetch", "-q", "origin", "topic")
        _git(self.root, "reset", "-q", "--hard", "FETCH_HEAD")
        return sha

    def declare(self, entries=None, *, workflows=None, raw: str | None = None) -> str:
        declaration = raw if raw is not None else json.dumps(entries if entries is not None else self.DECLARATION, indent=2) + "\n"
        files = {".github/sd-status.json": declaration}
        for name, text in (workflows if workflows is not None else {"tests.yml": self.TESTS, "sd-review-route.yml": self.ROUTE}).items():
            files[f".github/workflows/{name}"] = text
        return self.commit(files)

    def restart(self) -> None:
        """A fresh rig mid-test: the loops below merge, and a merged fixture cannot merge twice."""
        self.doCleanups()
        self.setUp()

    def head(self) -> str:
        return _git(self.root, "rev-parse", "HEAD")

    def adapter(self) -> ship.GitHub:
        return ship.GitHub(self.root, self.remote.slug)

    def run_record(self, path: str, *, event: str = "pull_request", conclusion: str = "success", sha: str | None = None, status: str = "completed") -> dict:
        return {"path": path, "name": path.rsplit("/", 1)[-1], "event": event, "status": status,
                "conclusion": conclusion, "head_sha": sha or self.head()}

    def check(self, name: str, *, conclusion: str = "success", sha: str | None = None, status: str = "completed") -> dict:
        return {"name": name, "status": status, "conclusion": conclusion, "head_sha": sha or self.head(), "app": {"id": 7}}

    def green(self) -> None:
        """Every check, status and expected workflow run passing at the head."""
        self.prepare()
        pull = next(iter(self.remote.pull_requests.values()))
        pull.checks = [self.check("unittest (ubuntu-latest, 3.13)"), self.check("route"), self.check("copilot-pull-request-reviewer")]
        self.double.workflow_runs = [self.run_record(".github/workflows/tests.yml"), self.run_record(".github/workflows/sd-review-route.yml")]

    def puts(self) -> int:
        return len([call for call in self.remote.calls if call.method == "PUT"])

    def refuse(self, pattern: str, code: str | None = None) -> None:
        with self.assertRaisesRegex(ship.Refusal, pattern) as caught:
            self.merge()
        if code is not None:
            self.assertEqual(caught.exception.workflow["blocker"]["code"], code)
        self.assertEqual(self.puts(), 0)

    def test_a_declared_gap_with_every_check_green_merges_once_and_the_receipt_says_so(self):
        self.declare()
        self.green()
        result = self.merge()
        self.assertEqual(self.puts(), 1)
        self.assertEqual(result["protection"], {"declared_gap": "unprotected", "until": "a second account with push or merge rights exists"})
        key = receipts.receipt_key(self.remote.slug, "topic", self.item)
        self.assertEqual(receipts.read(self.connection, key)[1]["protection"]["declared_gap"], "unprotected")

    def test_a_ruleset_that_gates_the_merge_is_path_a_without_a_declaration(self):
        """answerbook/log-distiller's shape on the fixture: no classic object, one
        active ruleset requiring a pull request and the strict `route` check
        bound to app 7. No declaration, and the merge lands once; the receipt's
        protection object says where it came from (sd:1327)."""
        self.commit({".github/workflows/tests.yml": self.TESTS, ".github/workflows/sd-review-route.yml": self.ROUTE})
        self.double.rules = self.gating_rules()
        self.double.rulesets = {42: {"id": 42, "name": "main", "enforcement": "active", "bypass_actors": []}}
        self.green()
        result = self.merge()
        self.assertEqual(self.puts(), 1)
        self.assertEqual(result["protection"]["source"], "ruleset")
        self.assertEqual([entry["id"] for entry in result["protection"]["rulesets"]], [42])
        self.assertEqual(result["protection"]["required_status_checks"]["checks"], [{"context": "route", "app_id": 7}])

    @staticmethod
    def gating_rules() -> list:
        return [
            {"type": "deletion", "ruleset_id": 42},
            {"type": "pull_request", "ruleset_id": 42, "parameters": {"required_approving_review_count": 0}},
            {"type": "required_status_checks", "ruleset_id": 42,
             "parameters": {"strict_required_status_checks_policy": True,
                            "required_status_checks": [{"context": "route", "integration_id": 7}]}}]

    def test_gating_rules_on_the_second_page_of_rules_still_gate(self):
        """Thirty rules fill the endpoint's first page; the rules that gate
        the merge sit on the second. A reader that stopped at one page would
        take Path B and refuse for want of a declaration. The merge lands,
        and the receipt's object carries the second page's check."""
        self.commit({".github/workflows/tests.yml": self.TESTS, ".github/workflows/sd-review-route.yml": self.ROUTE})
        filler = [{"type": "tag_name_pattern", "ruleset_id": 42, "parameters": {"pattern": f"v{n}"}} for n in range(30)]
        self.double.rules = filler + self.gating_rules()
        self.double.rulesets = {42: {"id": 42, "name": "main", "enforcement": "active", "bypass_actors": []}}
        self.green()
        result = self.merge()
        self.assertEqual(self.puts(), 1)
        self.assertEqual(result["protection"]["required_status_checks"]["checks"], [{"context": "route", "app_id": 7}])

    def test_a_ruleset_that_does_not_show_its_bypass_actors_refuses_the_merge(self):
        """The same ruleset with `bypass_actors` withheld, which is what GitHub
        answers a token that cannot edit it: unknown, and unknown does not
        merge. Nothing is pushed."""
        self.commit({".github/workflows/tests.yml": self.TESTS, ".github/workflows/sd-review-route.yml": self.ROUTE})
        self.double.rules = self.gating_rules()
        self.double.rulesets = {42: {"id": 42, "name": "main", "enforcement": "active"}}
        self.green()
        self.refuse("did not show its bypass actors", "prerequisite_failed")
        self.assertEqual(self.puts(), 0)

    def test_a_ruleset_that_only_forbids_deletion_is_not_protection(self):
        """answerbook/mezmo-world-simulator's ruleset 21772988: `deletion` and
        `non_fast_forward`, nothing a pull request must satisfy. Path B, so the
        refusal is the present one and a declaration is honoured."""
        self.double.rules = [{"type": "deletion", "ruleset_id": 42}, {"type": "non_fast_forward", "ruleset_id": 42}]
        self.double.rulesets = {42: {"id": 42, "name": "main", "enforcement": "active"}}
        self.commit({".github/workflows/tests.yml": self.TESTS, ".github/workflows/sd-review-route.yml": self.ROUTE})
        self.green()
        self.refuse("Branch not protected", "protection_required")
        self.restart()
        self.double.rules = [{"type": "deletion", "ruleset_id": 42}, {"type": "non_fast_forward", "ruleset_id": 42}]
        self.double.rulesets = {42: {"id": 42, "name": "main", "enforcement": "active"}}
        self.declare()
        self.green()
        self.merge()
        self.assertEqual(self.puts(), 1)

    def test_without_the_declaration_the_refusal_is_the_present_one(self):
        self.commit({".github/workflows/tests.yml": self.TESTS, ".github/workflows/sd-review-route.yml": self.ROUTE})
        self.green()
        self.refuse("Branch not protected", "protection_required")

    def test_a_failing_check_run_at_the_head_refuses(self):
        self.declare()
        self.green()
        pull = next(iter(self.remote.pull_requests.values()))
        pull.checks[0] = self.check("unittest (ubuntu-latest, 3.13)", conclusion="failure")
        self.refuse("CI is not passing", "ci_not_passing")

    def test_a_failing_run_at_another_sha_with_a_passing_rerun_at_the_head_still_refuses(self):
        """`filter=latest` at the head is what counts; the double reports both."""
        self.declare()
        self.green()
        pull = next(iter(self.remote.pull_requests.values()))
        pull.checks.append(self.check("unittest (ubuntu-latest, 3.13)", conclusion="failure", sha="0" * 40))
        self.refuse("CI is not passing", "ci_not_passing")

    def test_status_history_is_read_newest_first_per_context(self):
        for history, puts in (("success,pending", 1), ("success,failure", 1), ("failure,success", 0), ("pending,success", 0)):
            with self.subTest(history=history):
                self.restart()
                self.declare()
                self.green()
                self.double.statuses = [{"context": "legacy", "state": state, "sha": self.head()} for state in history.split(",")]
                if puts:
                    self.merge()
                    self.assertEqual(self.puts(), 1)
                else:
                    self.refuse("status is not passing", "ci_not_passing")

    def test_nothing_validated_the_head_refuses(self):
        self.declare()
        self.green()
        next(iter(self.remote.pull_requests.values())).checks = []
        self.double.workflow_runs = []
        self.refuse("nothing validated", "ci_missing")

    def test_only_the_advisory_workflow_ran_refuses_naming_tests(self):
        for spelling in ("tests.yml", "tests.yaml"):
            with self.subTest(spelling=spelling):
                self.restart()
                self.declare(workflows={spelling: self.TESTS, "sd-review-route.yml": self.ROUTE})
                self.prepare()
                next(iter(self.remote.pull_requests.values())).checks = [self.check("route")]
                self.double.workflow_runs = [self.run_record(".github/workflows/sd-review-route.yml")]
                self.refuse(r"workflow Tests \(\.github/workflows/" + re.escape(spelling) + r"\) has no successful pull_request run", "ci_missing")

    def test_the_expected_set_is_read_at_the_head_not_the_working_tree(self):
        """`merge` refuses a dirty tree before it reads anything, so the
        reader is asked directly: the tree has no say either way."""
        head = self.declare()
        expected = [(".github/workflows/sd-review-route.yml", "sd-review route"), (".github/workflows/tests.yml", "Tests")]
        # Present at head, deleted from the working tree: still expected.
        (self.root / ".github/workflows/tests.yml").unlink()
        self.assertEqual(self.adapter().expected_workflows(head), expected)
        # Absent at head, present only in the working tree: not expected.
        _git(self.root, "rm", "-q", ".github/workflows/tests.yml")
        _git(self.root, "commit", "-q", "-m", "drop tests\n\nAuthored-with: human")
        head = self.head()
        (self.root / ".github/workflows/tests.yml").write_text(self.TESTS)
        self.assertEqual(self.adapter().expected_workflows(head), expected[:1])

    def test_a_push_run_is_not_evidence_of_the_pull_request_validation(self):
        self.declare()
        self.green()
        self.double.workflow_runs = [self.run_record(".github/workflows/tests.yml", event="push"), self.run_record(".github/workflows/sd-review-route.yml")]
        self.refuse("workflow Tests", "ci_missing")
        self.double.workflow_runs.append(self.run_record(".github/workflows/tests.yml", event="pull_request"))
        self.merge()
        self.assertEqual(self.puts(), 1)

    def test_a_trigger_with_an_inline_comment_is_still_that_trigger(self):
        """Codex on the branch: `- pull_request # Validate PRs` used to carry the
        comment as the event name, and the Tests workflow silently stopped
        being expected. The only run at the head is the advisory one."""
        commented = self.TESTS.replace("on:\n  pull_request:\n  push:\n    branches: [main]\n",
                                       "on:\n  - pull_request # Validate PRs\n  - push\n")
        self.assertNotEqual(commented, self.TESTS)
        self.declare(workflows={"tests.yml": commented, "sd-review-route.yml": self.ROUTE})
        self.prepare()
        next(iter(self.remote.pull_requests.values())).checks = [self.check("route")]
        self.double.workflow_runs = [self.run_record(".github/workflows/sd-review-route.yml")]
        self.refuse(r"workflow Tests \(\.github/workflows/tests\.yml\) has no successful pull_request run", "ci_missing")

    def test_a_trigger_the_reader_cannot_resolve_refuses_rather_than_drops_the_workflow(self):
        odd = self.TESTS.replace("on:\n  pull_request:\n  push:\n    branches: [main]\n", "on: [pull_request, ${{ vars.EVENT }}]\n")
        self.declare(workflows={"tests.yml": odd, "sd-review-route.yml": self.ROUTE})
        self.green()
        self.refuse(r"tests\.yml at [0-9a-f]{12}: could not read its triggers \('\$\{\{ vars\.EVENT \}\}'\)", "ci_missing")

    def test_a_filtered_workflow_that_did_not_run_is_a_refusal_naming_it(self):
        """Requirement 2: a `paths`, `branches` or `types` filter under the
        trigger does not make the workflow optional. GitHub's scheduling is
        not reconstructed here; the workflow ran for the event or the merge
        names it."""
        for filtered in ("on:\n  pull_request:\n    paths: ['docs/**']\n",
                         "on:\n  pull_request:\n    branches: [main]\n",
                         "on:\n  pull_request:\n    types: [labeled]\n"):
            with self.subTest(filtered=filtered.splitlines()[2].strip()):
                self.restart()
                tests = self.TESTS.replace("on:\n  pull_request:\n  push:\n    branches: [main]\n", filtered)
                self.assertNotEqual(tests, self.TESTS)
                self.declare(workflows={"tests.yml": tests, "sd-review-route.yml": self.ROUTE})
                self.prepare()
                next(iter(self.remote.pull_requests.values())).checks = [self.check("route")]
                self.double.workflow_runs = [self.run_record(".github/workflows/sd-review-route.yml")]
                self.refuse(r"workflow Tests \(\.github/workflows/tests\.yml\) has no successful pull_request run", "ci_missing")
                self.double.workflow_runs.append(self.run_record(".github/workflows/tests.yml"))
                self.merge()
                self.assertEqual(self.puts(), 1)

    def test_a_quoted_event_key_is_the_same_key(self):
        """Post-cap review: `"pull_request":` beside an unquoted `push:` was
        dropped while its sibling parsed, so the workflow silently stopped
        being expected."""
        for spelling in ('on:\n  push:\n    branches: [main]\n  "pull_request":\n',
                         "on:\n  push:\n    branches: [main]\n  'pull_request':\n"):
            with self.subTest(spelling=spelling.splitlines()[-1].strip()):
                self.restart()
                tests = self.TESTS.replace("on:\n  pull_request:\n  push:\n    branches: [main]\n", spelling)
                self.assertNotEqual(tests, self.TESTS)
                self.declare(workflows={"tests.yml": tests, "sd-review-route.yml": self.ROUTE})
                self.prepare()
                next(iter(self.remote.pull_requests.values())).checks = [self.check("route")]
                self.double.workflow_runs = [self.run_record(".github/workflows/sd-review-route.yml")]
                self.refuse(r"workflow Tests \(\.github/workflows/tests\.yml\) has no successful pull_request run", "ci_missing")

    def test_a_space_before_the_colon_is_still_that_key(self):
        """Verification pass: `pull_request :` read as no key while `push:`
        beside it parsed, so the block looked complete."""
        self.declare(workflows={"tests.yml": self.TESTS.replace(
            "on:\n  pull_request:\n  push:\n    branches: [main]\n",
            "on:\n  push:\n    branches: [main]\n  pull_request :\n"), "sd-review-route.yml": self.ROUTE})
        self.prepare()
        next(iter(self.remote.pull_requests.values())).checks = [self.check("route")]
        self.double.workflow_runs = [self.run_record(".github/workflows/sd-review-route.yml")]
        self.refuse(r"workflow Tests \(\.github/workflows/tests\.yml\) has no successful pull_request run", "ci_missing")

    def test_a_line_in_the_trigger_block_this_cannot_read_refuses(self):
        """A sibling that parses must not make an unreadable line invisible."""
        self.declare(workflows={"tests.yml": self.TESTS.replace(
            "on:\n  pull_request:\n  push:\n    branches: [main]\n",
            "on:\n  push:\n  ?  [a, b]\n"), "sd-review-route.yml": self.ROUTE})
        self.green()
        self.refuse(r"tests\.yml at [0-9a-f]{12}: could not read its triggers \('\?  \[a, b\]'\)", "ci_missing")

    def test_the_base_advancing_before_the_put_refuses(self):
        """Under the declared gap nothing server-side keeps the branch fresh,
        so the freshness `ready` read is read again before the dispatch."""
        self.declare()
        self.green()
        seen = {"count": 0}
        double = self.double
        saved = double._route

        def route(method, path, body):
            if method == "GET" and "/compare/" in path:
                seen["count"] += 1
                if seen["count"] >= 2:
                    return 200, {"behind_by": 3, "ahead_by": 1, "status": "diverged"}
            return saved(method, path, body)
        double._route = route
        self.refuse("default branch advanced after the readiness check", "base_moved")

    def test_the_single_event_form_is_read(self):
        """Codex on the verification pass: `on: pull_request` returned no
        trigger and refused every merge under the declaration."""
        for spelling in ("on: pull_request\n", "on: [pull_request, push]\n"):
            with self.subTest(spelling=spelling.strip()):
                self.restart()
                tests = self.TESTS.replace("on:\n  pull_request:\n  push:\n    branches: [main]\n", spelling)
                self.declare(workflows={"tests.yml": tests, "sd-review-route.yml": self.ROUTE})
                self.prepare()
                next(iter(self.remote.pull_requests.values())).checks = [self.check("route")]
                self.double.workflow_runs = [self.run_record(".github/workflows/sd-review-route.yml")]
                self.refuse(r"workflow Tests", "ci_missing")
                self.double.workflow_runs.append(self.run_record(".github/workflows/tests.yml"))
                self.merge()
                self.assertEqual(self.puts(), 1)

    def test_an_unrelated_manual_workflow_blocks_nothing(self):
        manual = "name: Manual\n\non: workflow_dispatch\n\njobs:\n  job:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
        self.declare(workflows={"tests.yml": self.TESTS, "sd-review-route.yml": self.ROUTE, "manual.yml": manual})
        self.green()
        self.merge()
        self.assertEqual(self.puts(), 1)

    def test_a_push_only_workflow_is_not_expected(self):
        nightly = "name: Nightly\n\non:\n  push:\n    branches: [main]\n\njobs:\n  job:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"
        self.declare(workflows={"tests.yml": self.TESTS, "sd-review-route.yml": self.ROUTE, "nightly.yml": nightly})
        self.green()
        self.merge()
        self.assertEqual(self.puts(), 1)

    def test_another_gaps_acceptance_does_not_authorize_this_one(self):
        entries = {"accepted_gaps": [dict(self.DECLARATION["accepted_gaps"][0], id="reviews")]}
        self.declare(entries)
        self.green()
        self.refuse("carries no `unprotected` entry", "protection_required")

    def test_a_declaration_beside_a_protection_object_is_a_mismatch(self):
        self.declare()
        self.green()
        self.remote.protection = {"enforce_admins": {"enabled": True}, "required_pull_request_reviews": {"required_approving_review_count": 0},
                                  "required_status_checks": {"strict": True, "contexts": ["check"], "checks": [{"context": "check", "app_id": 7}]}}
        self.refuse("does not match the observed state")

    def test_an_invalid_declaration_file_names_its_fault(self):
        for label, raw, fault in (
            ("unknown key", json.dumps({"accepted_gaps": [], "extra": 1}), "unknown key"),
            ("bad JSON", "{not json", "not valid JSON"),
            ("wrong state shape", json.dumps({"accepted_gaps": [dict(self.DECLARATION["accepted_gaps"][0], state=[])]}), "state must be a non-empty object"),
        ):
            with self.subTest(label=label):
                self.restart()
                self.declare(raw=raw)
                self.green()
                self.refuse(fault, "protection_required")

    def test_the_declaration_is_read_at_the_head_not_the_working_tree(self):
        """Same reason as the workflow set: the reader, asked over a dirty tree."""
        head = self.commit({".github/workflows/tests.yml": self.TESTS, ".github/workflows/sd-review-route.yml": self.ROUTE})
        (self.root / ".github/sd-status.json").write_text(json.dumps(self.DECLARATION))
        api = self.adapter()
        self.assertIsNone(api.declared_gap(head))
        self.assertEqual(api.declaration_faults, [f".github/sd-status.json is not in the tree at {head[:12]}"])
        head = self.declare()
        (self.root / ".github/sd-status.json").unlink()
        self.assertEqual(self.adapter().declared_gap(head), {"declared_gap": "unprotected", "until": "a second account with push or merge rights exists"})

    def test_a_403_from_the_protection_endpoint_is_not_absence(self):
        self.declare()
        self.green()
        self.remote.protection = RemoteRefusal(403, "Resource not accessible by integration")
        self.refuse(r"Resource not accessible by integration \(HTTP 403\)")

    def test_protection_appearing_between_the_two_reads_refuses_as_changed(self):
        self.declare()
        self.green()
        reads = {"count": 0}
        double = self.double
        saved = double._route

        def route(method, path, body):
            if method == "GET" and path.endswith("/protection"):
                reads["count"] += 1
                if reads["count"] >= 2:
                    return 200, {"enforce_admins": {"enabled": True}, "required_pull_request_reviews": {"required_approving_review_count": 0},
                                 "required_status_checks": {"strict": True, "contexts": ["check"], "checks": [{"context": "check", "app_id": 7}]}}
            return saved(method, path, body)
        double._route = route
        self.refuse("ownership or branch protection changed before merge")



if __name__ == "__main__":
    unittest.main()
