"""Credential presence and expiry (sd:2203): facts into a heartbeat, never a value.

Every probe is stubbed: `get` stands in for the HTTPS GET and `run` for `gh`
and `claude`, so no test reaches the network or reads a real credential. The
tokens below are synthetic; the test that matters most greps the whole
database and the verb's output for them.
"""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

from sd_db import connect, credentials, initialise
from sd_db.jobs import cli

PAT = "ghp_example_SECRET_pat_value"
HA = "ha_example_SECRET_token_value"
ENV = {"GITHUB_PERSONAL_ACCESS_TOKEN": PAT, "HA_TOKEN": HA, "HA_URL": "http://ha.example.test:8123/"}
MCP_OUT = ("Checking MCP server health...\n\n"
           "github: https://api.example.test/mcp (HTTP) - ✓ Connected\n"
           "plugin:slack:slack: https://slack.example.test/mcp (HTTP) - ! Needs authentication\n"
           "local: /usr/bin/example --token=" + PAT + " - ✗ Failed to connect\n")


class Fakes:
    def __init__(self, *, github=(200, {"github-authentication-token-expiration": "2026-11-01 00:00:00 UTC"}),
                 ha=(401, {}), gh=0, mcp=(0, MCP_OUT), sdm=(9, ""), auth=(0, '{"loggedIn": true, "orgId": "' + PAT + '"}'),
                 sts=(0, ""), grant=200):
        self.answers = {credentials.GITHUB_USER: github, "http://ha.example.test:8123/api/": ha}
        self.programs = {"gh": (gh, "Logged in to github.com account example (keyring)\n- Token: " + PAT),
                         "claude mcp": mcp, "claude auth": auth, "sdm": sdm, "aws": sts}
        self.grant = grant
        self.gets, self.runs, self.posts = [], [], []

    def get(self, url, token):
        self.gets.append(url)
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def run(self, argv, timeout):
        self.runs.append(argv)
        return self.programs[" ".join(argv[:2]) if argv[0] == "claude" else argv[0]]

    def post(self, url, form):
        self.posts.append((url, form["grant_type"]))
        if isinstance(self.grant, Exception):
            raise self.grant
        return self.grant


class Probes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        initialise(Path(self.tmp.name) / "sd.db")
        self.db = connect(Path(self.tmp.name) / "sd.db")
        self.addCleanup(self.db.close)

    def check(self, env=ENV, only=None, **fakes):
        fake = Fakes(**fakes)
        body = credentials.check(self.db, env=env, get=fake.get, run=fake.run, post=fake.post, now="2026-10-06T09:10:00Z",
                                 only=only)
        self.order = [probe["id"] for probe in body["probes"]]
        return {probe["id"]: probe for probe in body["probes"]}, fake

    def logins(self, google=True):
        """A home with two workspace-mcp accounts and three AWS profiles, two of which sign in (sd:6722)."""
        home = Path(self.tmp.name) / "home"
        (home / ".aws").mkdir(parents=True)
        (home / ".aws" / "config").write_text("[default]\nlogin_session = arn:example\n[profile dev]\nsso_session = corp\n"
                                             "[profile keys]\nregion = us-east-1\n[sso-session corp]\nsso_start_url = x\n")
        folder = home / ".google_workspace_mcp" / "credentials"
        folder.mkdir(parents=True)
        if google:
            for account in ("a@example.test", "b@example.test"):
                (folder / f"{account}.json").write_text(json.dumps({
                    "token": PAT, "refresh_token": HA, "client_id": "id", "client_secret": "s",
                    "token_uri": "https://oauth.example.test/token"}))
        (folder / "oauth_states.json").write_text("[]")
        return {**ENV, "HOME": str(home)}

    def test_each_login_is_a_probe_with_its_sign_in(self):
        """sd:6722: Google, AWS, SDM and Claude logins, each with the line Sign in starts; no value stored."""
        probes, fake = self.check(env=self.logins(), grant=400)
        self.assertEqual(self.order[4:], ["google:a@example.test", "google:b@example.test", "aws:default", "aws:dev",
                                          "sdm", "claude"])
        self.assertEqual(probes["google:a@example.test"], {"id": "google:a@example.test", "name": "Google login (a@example.test)",
                                                           "signin": "workspace-mcp start_google_auth for a@example.test",
                                                           "present": True, "valid": False})
        self.assertEqual(fake.posts, [("https://oauth.example.test/token", "refresh_token")] * 2)
        self.assertEqual((probes["aws:default"]["signin"], probes["aws:dev"]["signin"]),
                         ("aws login --profile default", "aws sso login --profile dev"))
        self.assertEqual(probes["aws:dev"]["signed_in"], True)
        self.assertIn(["aws", "sts", "get-caller-identity", "--profile", "dev"], fake.runs)
        self.assertEqual((probes["sdm"]["signed_in"], probes["claude"]["signed_in"]), (False, True))
        self.assertNotIn(PAT, "\n".join(self.db.iterdump()))
        self.assertNotIn(HA, "\n".join(self.db.iterdump()))

    def test_a_status_command_that_fails_otherwise_is_a_reason(self):
        probes, _ = self.check(env=self.logins(), sdm=(2, ""), auth=(0, "not json"), grant=500)
        self.assertEqual((probes["sdm"].get("signed_in"), probes["sdm"]["reason"]), (None, "sdm status exited 2"))
        self.assertEqual(probes["claude"]["signed_in"], False)
        self.assertEqual(probes["google:a@example.test"]["reason"], "answered HTTP 500")

    def test_a_token_file_of_another_shape_is_unreadable_and_siblings_still_probe(self):
        """A valid JSON file that is not an object, or holds a non-string field, is one unreadable probe."""
        env = self.logins()
        folder = Path(env["HOME"]) / ".google_workspace_mcp" / "credentials"
        shapes = {"c": "[]", "d": "null", "e": '"text"', "f": json.dumps({
            "refresh_token": "r", "client_id": "id", "client_secret": "s", "token_uri": ["https://x"]})}
        for name, text in shapes.items():
            (folder / f"{name}@example.test.json").write_text(text)
        probes, fake = self.check(env=env)
        for name in shapes:
            self.assertEqual(probes[f"google:{name}@example.test"].get("reason"), "token file unreadable", name)
        self.assertEqual((probes["google:a@example.test"]["valid"], len(fake.posts)), (True, 2))

    def test_check_now_runs_one_family_and_keeps_the_rest(self):
        env = self.logins()
        self.check(env=env, sdm=(9, ""))
        before = list(self.order)
        probes, fake = self.check(env=env, only="sdm", sdm=(0, ""))
        self.assertEqual(fake.runs, [["sdm", "status"]])
        self.assertEqual((self.order, probes["sdm"]["signed_in"]), (before, True))
        probes, fake = self.check(env=env, only="google:b@example.test")
        self.assertEqual((len(fake.posts), self.order), (2, before))
        with self.assertRaises(ValueError):
            self.check(env=env, only="nothing")

    def test_sign_in_is_read_from_disk_for_a_known_probe_only(self):
        env = self.logins()
        self.assertEqual(credentials.signin("aws:dev", env), "! aws sso login --profile dev")
        self.assertEqual(credentials.signin("sdm", env), "! sdm-login")
        self.assertEqual(credentials.signin("claude", env), "! claude auth login")
        self.assertIn("user_google_email=a@example.test", credentials.signin("google:a@example.test", env) or "")
        for unknown in ("aws:keys", "aws:nope", "google:c@example.test", "gh", "sdm:x", "aws:dev; rm -rf /"):
            self.assertIsNone(credentials.signin(unknown, env), unknown)

    def test_a_rate_limited_answer_is_a_reason_not_a_rejection(self):
        probes, _ = self.check(github=(403, {}), ha=(403, {}))
        for key in ("github_pat", "ha_token"):
            self.assertEqual((probes[key]["valid"], probes[key]["reason"]), (None, "answered HTTP 403"), key)

    def test_each_probe_records_presence_validity_and_expiry(self):
        probes, fake = self.check()
        self.assertEqual(probes["github_pat"], {"id": "github_pat", "name": "GitHub PAT (GITHUB_PERSONAL_ACCESS_TOKEN)",
                                                "present": True, "valid": True, "expires": "2026-11-01T00:00:00Z"})
        self.assertEqual((probes["ha_token"]["present"], probes["ha_token"]["valid"]), (True, False))
        self.assertEqual(probes["gh"]["signed_in"], True)
        self.assertEqual(probes["mcp"]["servers"], [{"name": "github", "status": "connected"},
                                                    {"name": "plugin:slack:slack", "status": "needs_auth"},
                                                    {"name": "local", "status": "failed"}])
        self.assertEqual(fake.runs, [["gh", "auth", "status", "--hostname", "github.com"], ["claude", "mcp", "list"],
                                     ["sdm", "status"], ["claude", "auth", "status"]])
        row = self.db.execute("SELECT timestamp, body FROM state WHERE kind = 'heartbeat' AND key = ?",
                              (credentials.HEARTBEAT_KEY,)).fetchone()
        self.assertEqual(row["timestamp"], "2026-10-06T09:10:00Z")
        self.assertEqual(json.loads(row["body"])["probes"][0]["expires"], "2026-11-01T00:00:00Z")

    def test_no_value_reaches_the_database_or_the_description(self):
        probes, _ = self.check()
        dump = "\n".join(self.db.iterdump())
        lines = "\n".join(credentials.describe(probe) for probe in probes.values())
        for secret in (PAT, HA):
            self.assertNotIn(secret, dump)
            self.assertNotIn(secret, lines)
        self.assertNotIn("example.test", dump, "an MCP target or HA URL was stored")

    def test_an_absent_token_is_recorded_absent_and_never_sent(self):
        probes, fake = self.check(env={})
        self.assertEqual((probes["github_pat"]["present"], probes["ha_token"]["present"]), (False, False))
        self.assertNotIn("valid", probes["github_pat"])
        self.assertEqual(fake.gets, [])

    def test_an_unreachable_service_is_a_reason_not_a_verdict(self):
        probes, _ = self.check(github=OSError("down"), ha=(500, {}), gh=1, mcp=(1, ""))
        self.assertEqual(probes["github_pat"]["reason"], "not reached: OSError")
        self.assertNotIn("valid", probes["github_pat"])
        self.assertEqual((probes["ha_token"]["valid"], probes["ha_token"]["reason"]), (None, "answered HTTP 500"))
        self.assertEqual(probes["gh"]["signed_in"], False)
        self.assertEqual(probes["mcp"], {"id": "mcp", "name": "MCP servers (claude mcp list)",
                                         "reason": "claude mcp list exited 1"})

    def test_ha_without_a_url_is_present_and_untested(self):
        probes, fake = self.check(env={"HA_TOKEN": HA})
        self.assertEqual(probes["ha_token"]["reason"], "HA_URL unset, so the token was not tested")
        self.assertNotIn("http://ha.example.test:8123/api/", fake.gets)

    def test_a_pat_with_no_expiry_header_has_none(self):
        probes, _ = self.check(github=(200, {}))
        self.assertEqual((probes["github_pat"]["valid"], probes["github_pat"]["expires"]), (True, None))


class Redirects(unittest.TestCase):
    """A token goes only where it was addressed: `_get` follows no redirect (sd:2203 review)."""

    def serve(self, handler):
        server = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def test_a_redirect_is_its_status_and_the_token_never_reaches_the_target(self):
        seen = []

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        target = self.serve(Target)

        class Mover(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", f"{target}/api/")
                self.end_headers()

            def log_message(self, *args):
                pass

        status, headers = credentials._get(self.serve(Mover) + "/api/", HA)
        self.assertEqual((status, headers), (302, {}))
        self.assertEqual(seen, [], "the redirect was followed with the token")


class TheVerb(unittest.TestCase):
    def setUp(self):
        # A seam the verb misses must fail here, not reach GitHub or run gh and claude.
        for target, name in ((credentials, "build_opener"), (credentials.subprocess, "run")):
            patcher = mock.patch.object(target, name, side_effect=AssertionError(f"the test reached the real {name}"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_credentials_records_the_heartbeat_and_prints_no_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            target = home / ".local/share/sd/sd.db"
            target.parent.mkdir(parents=True)
            initialise(target)
            fake = Fakes()
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.dict(os.environ, {"HOME": str(home), **ENV}), \
                    mock.patch.object(credentials, "_get", fake.get), mock.patch.object(credentials, "_run", fake.run), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["credentials"])
            self.assertEqual(code, 0, err.getvalue())
            self.assertIn("github_pat: present True, valid True, expires 2026-11-01T00:00:00Z", out.getvalue())
            self.assertIn("mcp: 1 of 3 servers connected", out.getvalue())
            for secret in (PAT, HA):
                self.assertNotIn(secret, out.getvalue() + err.getvalue())
            db = connect(target)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM state WHERE kind = 'heartbeat' AND key = ?",
                                            (credentials.HEARTBEAT_KEY,)).fetchone()[0], 1)
            finally:
                db.close()

    def test_an_argument_is_refused(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["credentials", "--now"]), 1)
        self.assertIn("takes no arguments", err.getvalue())


if __name__ == "__main__":
    unittest.main()
