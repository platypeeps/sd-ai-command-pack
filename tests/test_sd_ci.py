"""`sd ci local` (sd:1914): switch a repository to local CI, against a fake `gh`.

The fake is a script on `PATH` that answers `gh api` from a JSON model of one
repository and applies the writes to it, so a second run reads what the first
wrote. The database is a throwaway one; nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = REPO_ROOT / "bin" / "sd"
PREFIX = "repos/{owner}/{repo}"

FAKE_GH = textwrap.dedent('''\
    #!/usr/bin/env python3
    """A `gh api` for one repository, read from and written to $FAKE_GH_STATE."""
    import json, os, re, sys

    state_path = os.environ["FAKE_GH_STATE"]
    with open(state_path) as handle:
        state = json.load(handle)
    args = sys.argv[1:]
    assert args[0] == "api", args
    method, path = "GET", None
    rest = args[1:]
    while rest:
        word = rest.pop(0)
        if word == "-X":
            method = rest.pop(0)
        elif word == "--input":
            rest.pop(0)
        else:
            path = word
    body = json.loads(sys.stdin.read()) if "--input" in args else None
    with open(os.environ["FAKE_GH_LOG"], "a") as log:
        log.write(json.dumps([method, path, body]) + "\\n")
    prefix = "repos/{owner}/{repo}"
    route = path[len(prefix):].split("?")[0]

    def answer(value):
        print(json.dumps(value))
        sys.exit(0)

    def fail(status, message):
        # A warning ahead of gh's status line, as an interpreter hook prints one.
        print("sitecustomize: a warning on stderr", file=sys.stderr)
        print(f"gh: {message} (HTTP {status})", file=sys.stderr)
        sys.exit(1)

    def save():
        with open(state_path, "w") as handle:
            json.dump(state, handle)

    if f"{method} {route}" in state.get("fail", {}):
        fail(*state["fail"][f"{method} {route}"])
    branch = state["repo"]["default_branch"]
    if (method, route) == ("GET", ""):
        answer(state["repo"])
    if route == f"/branches/{branch}/protection" and method == "GET":
        if state.get("classic") is None:
            fail(404, "Branch not protected")
        answer(state["classic"])
    if route == f"/branches/{branch}/protection/required_status_checks" and method == "PATCH":
        if not (state.get("classic") or {}).get("required_status_checks"):
            fail(404, "Required status checks not enabled")
        state["classic"]["required_status_checks"] = {"strict": body["strict"], "checks": body["checks"],
                                                      "contexts": [c["context"] for c in body["checks"]]}
        save(); answer(state["classic"]["required_status_checks"])
    if route == f"/rules/branches/{branch}" and method == "GET":
        rules = []
        for key, ruleset in sorted(state.get("rulesets", {}).items()):
            if ruleset["enforcement"] == "active":
                rules += [dict(rule, ruleset_id=int(key), ruleset_source_type=ruleset["source_type"])
                          for rule in ruleset["rules"]]
        answer(rules)
    match = re.fullmatch(r"/rulesets/(\\d+)", route)
    if match and method == "GET":
        answer(state["rulesets"][match[1]])
    if match and method == "PUT":
        assert set(body) <= {"name", "target", "enforcement", "bypass_actors", "conditions", "rules"}, body
        state["rulesets"][match[1]].update(body)
        save(); answer(state["rulesets"][match[1]])
    if route == "/actions/permissions":
        if method == "PUT":
            state["actions"]["enabled"] = body["enabled"]
            save()
        answer(state["actions"])
    if route == "/actions/workflows" and method == "GET":
        answer({"total_count": len(state["workflows"]), "workflows": state["workflows"]})
    match = re.fullmatch(r"/actions/workflows/(\\d+)/disable", route)
    if match and method == "PUT":
        for workflow in state["workflows"]:
            if str(workflow["id"]) == match[1]:
                workflow["state"] = "disabled_manually"
        save(); sys.exit(0)
    fail(404, f"Not Found: {method} {path}")
''')


def repo(*, private: bool, admin: bool = True) -> dict:
    return {"full_name": "example/widget", "default_branch": "main", "private": private,
            "permissions": {"admin": admin}}


def ruleset(identity: int, rules: list, *, source_type: str = "Repository") -> dict:
    return {"id": identity, "name": f"guard-{identity}", "target": "branch", "enforcement": "active",
            "source_type": source_type, "source": "example/widget", "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
            "node_id": "RRS_x", "_links": {}, "current_user_can_bypass": "never", "rules": rules}


WORKFLOWS = [
    {"id": 1, "path": ".github/workflows/tests.yml", "state": "active"},
    {"id": 2, "path": ".github/workflows/old.yml", "state": "disabled_manually"},
    {"id": 3, "path": "dynamic/github-code-scanning/codeql", "state": "active"},
    {"id": 4, "path": "dynamic/dependabot/dependabot-updates", "state": "active"},
]


class CiLocal(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name).resolve()
        bindir = self.home / "fakebin"
        bindir.mkdir()
        (bindir / "gh").write_text(FAKE_GH, encoding="utf-8")
        (bindir / "gh").chmod(0o755)
        self.state_path = self.home / "gh-state.json"
        self.log = self.home / "gh-log.jsonl"
        self.root = self.home / "widget"
        self.root.mkdir()
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.root), "remote", "add", "origin",
                        "https://github.com/example/widget.git"], check=True)
        from sd_db import connect, initialise, upsert_repo

        self.database = self.home / "sd.db"
        initialise(self.database)
        connection = connect(self.database)
        upsert_repo(connection, str(self.root), remote="https://github.com/example/widget.git")
        connection.close()
        self.environ = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}",
                            FAKE_GH_STATE=str(self.state_path), FAKE_GH_LOG=str(self.log))

    def model(self, **values) -> None:
        self.state_path.write_text(json.dumps(values), encoding="utf-8")

    def state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def writes(self) -> list:
        if not self.log.exists():
            return []
        calls = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        return [call for call in calls if call[0] != "GET"]

    def ci(self) -> str:
        from sd_db import connect

        connection = connect(self.database, write=False)
        try:
            return connection.execute("SELECT ci FROM repo").fetchone()[0]
        finally:
            connection.close()

    def run_sd(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SD), "ci", "local", "--database", str(self.database), *extra],
                              cwd=self.root, env=self.environ, capture_output=True, text=True, timeout=60)

    def test_a_dry_run_writes_nothing(self) -> None:
        self.model(repo=repo(private=True), classic={"required_status_checks": {
            "strict": False, "contexts": ["tests"], "checks": [{"context": "tests", "app_id": 15368}]}},
            rulesets={}, actions={"enabled": True}, workflows=WORKFLOWS)
        before = self.state()
        done = self.run_sd()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("dry run", done.stdout)
        self.assertIn("repo.ci: github -> local", done.stdout)
        self.assertIn("require sd/local-gate, strict; drops tests", done.stdout)
        self.assertIn("disable for the whole repository (private)", done.stdout)
        self.assertIn("push a fresh commit", done.stdout)
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.state(), before)
        self.assertEqual(self.ci(), "github")

    def test_private_classic_applies_then_finds_nothing(self) -> None:
        self.model(repo=repo(private=True), classic={"enforce_admins": {"enabled": True}, "required_status_checks": {
            "strict": False, "contexts": ["tests"], "checks": [{"context": "tests", "app_id": 15368}]}},
            rulesets={}, actions={"enabled": True}, workflows=WORKFLOWS)
        done = self.run_sd("--apply")
        self.assertEqual(done.returncode, 0, done.stderr)
        state = self.state()
        self.assertEqual(state["classic"]["required_status_checks"]["checks"], [{"context": "sd/local-gate"}])
        self.assertIs(state["classic"]["required_status_checks"]["strict"], True)
        self.assertEqual(state["classic"]["enforce_admins"], {"enabled": True})
        self.assertIs(state["actions"]["enabled"], False)
        self.assertEqual(self.ci(), "local")
        self.assertNotIn("/disable", json.dumps(self.writes()))
        self.log.unlink()
        again = self.run_sd("--apply")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.writes(), [])
        self.assertIn("0 change(s) made.", again.stdout)

    def test_public_keeps_actions_and_dynamic_workflows(self) -> None:
        self.model(repo=repo(private=False), classic=None, rulesets={}, actions={"enabled": True},
                   workflows=[dict(workflow) for workflow in WORKFLOWS])
        done = self.run_sd("--apply")
        self.assertEqual(done.returncode, 0, done.stderr)
        state = self.state()
        self.assertIs(state["actions"]["enabled"], True)
        self.assertEqual({workflow["path"]: workflow["state"] for workflow in state["workflows"]}, {
            ".github/workflows/tests.yml": "disabled_manually",
            ".github/workflows/old.yml": "disabled_manually",
            "dynamic/github-code-scanning/codeql": "active",
            "dynamic/dependabot/dependabot-updates": "active",
        })
        self.assertEqual([call[:2] for call in self.writes()],
                         [["PUT", f"{PREFIX}/actions/workflows/1/disable"]])
        self.assertIn("unprotected", done.stdout)

    def test_a_ruleset_keeps_its_other_rules(self) -> None:
        rules = [{"type": "deletion"}, {"type": "non_fast_forward"},
                 {"type": "required_status_checks", "parameters": {
                     "strict_required_status_checks_policy": False, "do_not_enforce_on_create": True,
                     "required_status_checks": [{"context": "tests", "integration_id": 15368}]}}]
        self.model(repo=repo(private=True), classic=None, rulesets={"7": ruleset(7, rules)},
                   actions={"enabled": False}, workflows=[])
        done = self.run_sd("--apply")
        self.assertEqual(done.returncode, 0, done.stderr)
        written = self.state()["rulesets"]["7"]
        self.assertEqual([rule["type"] for rule in written["rules"]],
                         ["deletion", "non_fast_forward", "required_status_checks"])
        self.assertEqual(written["rules"][2]["parameters"], {
            "strict_required_status_checks_policy": True, "do_not_enforce_on_create": True,
            "required_status_checks": [{"context": "sd/local-gate"}]})
        self.assertEqual(written["bypass_actors"], [])
        self.assertIn("keeps 2 other rule(s)", done.stdout)
        self.log.unlink()
        self.assertEqual(self.run_sd("--apply").returncode, 0)
        self.assertEqual(self.writes(), [])

    def test_a_ruleset_without_a_check_rule_gains_one(self) -> None:
        self.model(repo=repo(private=True), classic=None,
                   rulesets={"9": ruleset(9, [{"type": "deletion"}])}, actions={"enabled": False}, workflows=[])
        done = self.run_sd("--apply")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.state()["rulesets"]["9"]["rules"], [
            {"type": "deletion"},
            {"type": "required_status_checks", "parameters": {
                "required_status_checks": [{"context": "sd/local-gate"}],
                "strict_required_status_checks_policy": True}}])

    def test_refusals_write_nothing(self) -> None:
        cases = {
            "no admin": dict(repo=repo(private=True, admin=False), classic=None, rulesets={},
                             actions={"enabled": True}, workflows=[]),
            "classic without checks": dict(repo=repo(private=True), classic={"enforce_admins": {"enabled": True}},
                                           rulesets={}, actions={"enabled": True}, workflows=[]),
            "protection unreadable": dict(repo=repo(private=True), classic=None, rulesets={},
                                          actions={"enabled": True}, workflows=[],
                                          fail={"GET /branches/main/protection": [502, "Server Error"]}),
        }
        for name, model in cases.items():
            with self.subTest(name):
                if self.log.exists():
                    self.log.unlink()
                self.model(**model)
                done = self.run_sd("--apply")
                self.assertEqual(done.returncode, 3, done.stdout)
                self.assertIn("sd ci local:", done.stderr)
                self.assertEqual(self.writes(), [])
                self.assertEqual(self.ci(), "github")

    def test_json_names_every_step(self) -> None:
        self.model(repo=repo(private=True), classic=None, rulesets={}, actions={"enabled": False}, workflows=[])
        done = self.run_sd("--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertFalse(payload["applied"])
        self.assertEqual([(step["state"], step["subject"]) for step in payload["steps"]], [
            ("change", "repo.ci"), ("ok", "main"), ("ok", "Actions"), ("note", "open pull requests")])


if __name__ == "__main__":
    unittest.main()
