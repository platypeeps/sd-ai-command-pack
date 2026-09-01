"""The write path: what may run, who may ask, and what a GET still promises.

Three things are pinned here, and they are the three that make a POST safe to
add to a dashboard that had none. A command is **resolved** from an id and
never built from request text. A request is refused unless its `Host` is one
this server answers to and its token matches. And **no GET route mutates
anything** -- the guarantee that replaced "GET is the only verb", and the one
the dashboard being replaced does not keep: it answers
`GET /api/state?refresh=1` by starting a rebuild behind the Host check alone.
"""

from __future__ import annotations

import ast
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import unittest
import unittest.mock
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dashboard import actions, plugins, server  # noqa: E402 - after the path insert


def plugin_entry(**overrides) -> dict:
    """A registry entry as `sd plugin list --json` prints one."""
    return {
        "root": "/tmp/plug",
        "prefix": "sys",
        "readable": True,
        "actions": [{"id": "queue-set", "label": "sort the queue", "run": "sd-sys queue"}],
        **overrides,
    }


class Catalog(unittest.TestCase):
    def test_the_backbone_action_is_offered_by_id_and_label(self) -> None:
        self.assertEqual(
            actions.catalog([]),
            [{"id": "index", "label": "collect issues and pull requests"}],
        )

    def test_the_backbone_action_names_a_file_and_not_a_path_lookup(self) -> None:
        """Under launchd the `PATH` is launchd's, and `sd-dashboard` is not on it.

        This is why the button 502'd the first time it was pressed. An absolute
        argv[0] is the fix, and a test that only checked the label would not
        have noticed either time.
        """
        argv = actions.RUN_ALLOWLIST["index"]["argv"]
        self.assertTrue(Path(argv[0]).is_file(), argv[0])

    def test_the_argv_never_reaches_the_page(self) -> None:
        """A page that has never seen a command cannot be talked into echoing one."""
        offered = actions.catalog([plugin_entry()])
        self.assertEqual(
            {key for entry in offered for key in entry}, {"id", "label"})

    def test_a_declared_action_is_namespaced_by_its_plugin(self) -> None:
        self.assertIn(
            "sys/queue-set", {entry["id"] for entry in actions.catalog([plugin_entry()])})

    def test_a_plugin_cannot_claim_a_backbone_id(self) -> None:
        """The namespace is the whole defence, so it is tested by trying.

        A plugin declaring `index` gets `sys/index`; the backbone's own
        `index` still resolves to the backbone's argv.
        """
        entry = plugin_entry(
            actions=[{"id": "index", "label": "mine", "run": "curl evil.example"}])
        resolved = actions.declared([entry])
        self.assertIn("sys/index", resolved)
        self.assertNotIn("index", resolved)
        self.assertEqual(
            actions.RUN_ALLOWLIST["index"]["argv"],
            [str(actions.SD_DASHBOARD), "index"])

    def test_the_order_is_declaration_order_and_not_sorted(self) -> None:
        """R11-D23 chose a list over an object keyed by id to keep this.

        Sorting reads as tidier and throws away the thing the shape was chosen
        for: the buttons would reorder themselves when an id was renamed. The
        backbone's own action comes first, then each manifest in its order.
        """
        entry = plugin_entry(actions=[
            {"id": "zebra", "label": "z", "run": "sd-sys z"},
            {"id": "alpha", "label": "a", "run": "sd-sys a"},
        ])
        self.assertEqual(
            [action["id"] for action in actions.catalog([entry])],
            ["index", "sys/zebra", "sys/alpha"],
        )

    def test_a_plugin_cannot_shadow_another_plugins_action(self) -> None:
        first = plugin_entry(prefix="sys")
        second = plugin_entry(prefix="ops", root="/tmp/other")
        resolved = actions.declared([first, second])
        self.assertEqual(set(resolved), {"sys/queue-set", "ops/queue-set"})

    def test_a_declaration_that_will_not_parse_is_dropped_not_fatal(self) -> None:
        """An unrunnable button is a smaller failure than a loader that stops."""
        entry = plugin_entry(
            actions=[{"id": "bad", "label": "x", "run": 'sd-sys "unclosed'},
                     {"id": "good", "label": "y", "run": "sd-sys ok"}])
        self.assertEqual(set(actions.declared([entry])), {"sys/good"})

    def test_an_entry_without_a_root_declares_nothing(self) -> None:
        """The root is the working directory; an empty one is the dashboard's own."""
        self.assertEqual(actions.declared([plugin_entry(root="")]), {})


class Resolution(unittest.TestCase):
    def test_an_unknown_id_is_a_404_and_never_an_attempt(self) -> None:
        ran: list[list[str]] = []
        with unittest.mock.patch.object(
            actions, "bounded_run", lambda argv, **kw: ran.append(argv) or b""
        ):
            body, status = actions.run("rm -rf /", [])
        self.assertEqual(status, 404)
        self.assertEqual(ran, [], "an unresolved id reached a subprocess")

    def test_a_non_string_id_is_refused_before_the_map_is_read(self) -> None:
        self.assertEqual(actions.run({"argv": ["sh"]}, [])[1], 400)
        self.assertEqual(actions.run(None, [])[1], 400)

    def test_a_declared_action_runs_its_own_argv_in_its_own_root(self) -> None:
        seen: dict = {}

        def fake(argv, cwd, **kw):
            seen.update(argv=argv, cwd=cwd)
            return b"done\n"

        with unittest.mock.patch.object(actions, "bounded_run", fake):
            body, status = actions.run("sys/queue-set", [plugin_entry()])
        self.assertEqual(status, 200)
        self.assertEqual(seen["argv"], ["sd-sys", "queue"])
        self.assertEqual(str(seen["cwd"]), "/tmp/plug")
        self.assertEqual(body["output"], "done")

    def test_a_refused_command_says_why_rather_than_going_quiet(self) -> None:
        """The operator pressed a button. Silence is the failure mode."""

        def fake(argv, cwd, **kw):
            raise plugins.Bounded("exited 1: no such queue")

        with unittest.mock.patch.object(actions, "bounded_run", fake):
            body, status = actions.run("index", [])
        self.assertEqual(status, 502)
        self.assertIn("no such queue", body["error"])


class Hosts(unittest.TestCase):
    def setUp(self) -> None:
        patcher = unittest.mock.patch.object(
            server, "_HOSTS", {"127.0.0.1", "localhost", "::1", "[::1]", "tg-sol"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_loopback_names_are_served_with_and_without_a_port(self) -> None:
        for header in ["127.0.0.1", "127.0.0.1:8767", "localhost:8768", "[::1]:8767"]:
            self.assertTrue(server.host_ok(header), header)

    def test_the_allow_list_cannot_be_widened_after_it_is_built(self) -> None:
        """It is handed to every request; a mutable set is a widenable one."""
        with unittest.mock.patch.object(server, "_HOSTS", None), \
                unittest.mock.patch.object(server, "tailnet_names", set):
            self.assertIsInstance(server.allowed_hosts(), frozenset)

    def test_a_tailnet_name_is_served_because_a_proxy_forwards_it(self) -> None:
        self.assertTrue(server.host_ok("tg-sol:8767"))

    def test_a_name_this_node_does_not_answer_to_is_refused(self) -> None:
        """This is the DNS-rebinding guard, so the refusal is the feature.

        `evil.example` resolving to 127.0.0.1 makes a page on the open
        internet same-origin with this port; the binding cannot tell the
        difference and the `Host` header can.
        """
        for header in ["evil.example", "evil.example:8767", "", None]:
            self.assertFalse(server.host_ok(header), repr(header))


class TailnetBind(unittest.TestCase):
    """The second address, and the reason it is opt-in.

    R11-D10's correction: the system dashboard reaches a phone by two paths,
    a direct tailnet bind and a `tailscale serve` proxy, and 6b had to carry
    both or knowingly drop one.
    """

    def run_with(self, value: object) -> list[str]:
        env = {} if value is None else {server.TAILNET_BIND: str(value)}
        with unittest.mock.patch.dict(os.environ, env, clear=False):
            if value is None:
                os.environ.pop(server.TAILNET_BIND, None)
            return server.tailnet_addrs()

    def test_the_second_bind_is_off_unless_it_is_asked_for(self) -> None:
        """It widens the audience from this machine to a whole tailnet.

        `tailscale` is not called at all when it is off, which is what the
        mock proves: the guard is before the probe, not after it.
        """
        with unittest.mock.patch.object(server.subprocess, "run") as run:
            for value in [None, "0", "", "false", "no", "NO", " 0 "]:
                self.assertEqual(self.run_with(value), [], repr(value))
            run.assert_not_called()

    def test_asking_for_it_returns_the_addresses_tailscale_reports(self) -> None:
        done = subprocess.CompletedProcess([], 0, stdout="100.82.165.108\nfd7a::1\n\n")
        with unittest.mock.patch.object(server.subprocess, "run", return_value=done):
            self.assertEqual(self.run_with("1"), ["100.82.165.108", "fd7a::1"])

    def test_a_tailscale_that_is_not_there_is_a_loopback_dashboard(self) -> None:
        with unittest.mock.patch.object(server.subprocess, "run", side_effect=OSError):
            self.assertEqual(self.run_with("1"), [])

    def test_an_address_it_binds_is_an_address_it_answers_to(self) -> None:
        """Otherwise the bind serves 403s to the one path it exists for.

        A browser at `http://100.82.165.108:8767/` sends that as its `Host`,
        and v6 arrives bracketed, which is the spelling `host_ok` keeps.
        """
        with unittest.mock.patch.object(server, "_HOSTS", None), \
                unittest.mock.patch.object(server, "tailnet_names", set), \
                unittest.mock.patch.object(
                    server, "bound_addrs", lambda: ["100.82.165.108", "fd7a::1"]):
            hosts = server.allowed_hosts()
            self.assertTrue(server.host_ok("100.82.165.108:8767"))
            self.assertTrue(server.host_ok("[fd7a::1]:8767"))
            self.assertIn("fd7a::1", hosts)
            self.assertFalse(server.host_ok("evil.example:8767"))

    def test_a_tailscale_that_failed_reports_nothing_rather_than_its_output(self) -> None:
        """Its stdout on a bad exit is a diagnostic, not an address list.

        The fixture prints an address *and* exits non-zero on purpose: a
        failure whose output happens to be unparseable is caught by the shape
        filter one line below, and a test built on that one proves the shape
        filter twice and the exit code never. This is the case where only the
        exit code can say no -- half-written output from a command that then
        failed, which would otherwise widen the allow-list.
        """
        done = subprocess.CompletedProcess([], 1, stdout="100.82.165.108\nlost it\n")
        with unittest.mock.patch.object(server.subprocess, "run", return_value=done):
            self.assertEqual(self.run_with("1"), [])

    def test_only_lines_that_are_addresses_widen_the_allow_list(self) -> None:
        """`tailnet_names` filters a hostname by shape; this is the same rule.

        These become `Host` values this server answers to, so a stray line on
        stdout must not be able to add one.
        """
        done = subprocess.CompletedProcess(
            [], 0, stdout="100.82.165.108\nWarning: something\nfd7a::1\n \n")
        with unittest.mock.patch.object(server.subprocess, "run", return_value=done):
            self.assertEqual(self.run_with("1"), ["100.82.165.108", "fd7a::1"])

    def test_the_allow_list_and_the_binding_read_one_answer(self) -> None:
        """Asked twice, the tailnet can come up between them.

        The server would then bind an address the cached allow-list never
        heard of, and answer 403 on exactly the path the bind exists for. So
        the probe happens once and both callers read the same list.
        """
        with unittest.mock.patch.object(server, "_ADDRS", None), \
                unittest.mock.patch.object(server, "_HOSTS", None), \
                unittest.mock.patch.object(server, "tailnet_names", set), \
                unittest.mock.patch.object(
                    server, "tailnet_addrs", return_value=["100.82.165.108"]) as probe:
            server.allowed_hosts()
            self.assertEqual(server.bound_addrs(), ["100.82.165.108"])
            self.assertEqual(probe.call_count, 1)
            self.assertTrue(server.host_ok("100.82.165.108:8767"))

    def test_the_wildcard_address_is_never_bound(self) -> None:
        """`0.0.0.0` publishes this on every network the machine joins.

        Read out of `serve`'s source rather than asserted about a running
        server: the point is that the string is not there to be reached.
        """
        source = (REPO_ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        serve = next(n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == "serve")
        literals = {c.value for c in ast.walk(serve)
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        for wildcard in ["0.0.0.0", "::", "*"]:
            self.assertNotIn(wildcard, literals)

    def test_a_second_address_that_refuses_does_not_cost_the_first(self) -> None:
        """The tailnet coming up after login is the ordinary case."""
        source = (REPO_ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        serve = next(n for n in ast.walk(ast.parse(source))
                     if isinstance(n, ast.FunctionDef) and n.name == "serve")
        handlers = [h for n in ast.walk(serve) if isinstance(n, ast.Try) for h in n.handlers]
        self.assertTrue(any(isinstance(h.body[-1], ast.Continue) for h in handlers),
                        "a refused bind must be skipped, not fatal")
        self.assertTrue(any(isinstance(n, ast.Raise) for n in ast.walk(serve)),
                        "nothing bound at all must still be fatal")

    def test_the_v6_server_is_the_same_server_on_a_different_family(self) -> None:
        self.assertEqual(server.ServerV6.address_family, socket.AF_INET6)
        self.assertTrue(issubclass(server.ServerV6, server.ThreadingHTTPServer))


def get_routes() -> list[str]:
    """Every path `do_GET` answers, read out of the source.

    Enumerated rather than listed here: a route added next month is in this
    test the day it is written, which is the only version of this check that
    keeps working.
    """
    tree = ast.parse((REPO_ROOT / "dashboard" / "server.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "do_GET":
            return sorted({
                child.value for child in ast.walk(node)
                if isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and child.value.startswith("/")
            })
    raise AssertionError("do_GET is gone; this test no longer checks anything")


class NoGetSideEffect(unittest.TestCase):
    """The promise that replaced "GET is the only verb"."""

    def test_do_get_never_calls_the_runner(self) -> None:
        """Read out of the syntax tree, so it holds for routes not yet written."""
        source = (REPO_ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.FunctionDef) and node.name == "do_GET"):
                continue
            called = {
                ast.unparse(child.func) for child in ast.walk(node)
                if isinstance(child, ast.Call)
            }
            self.assertNotIn("actions.run", called)
            self.assertFalse(
                {name for name in called if name.startswith("subprocess.")},
                f"do_GET forks: {called}",
            )
            return
        raise AssertionError("do_GET is gone")

    def test_every_get_route_refuses_to_run_anything_query_or_not(self) -> None:
        """Including `?refresh=1`, which is the shape being refused.

        The dashboard this replaces answers that exact request by starting a
        rebuild, guarded by the Host check alone while its POST twin demands
        the token. This walks every route the handler serves, with and
        without the parameter, and fails if any of them reaches the runner.
        """
        ran: list[object] = []
        with Live(self) as live, unittest.mock.patch.object(
            actions, "run", lambda *a, **kw: ran.append(a) or ({}, 200)
        ):
            for route in get_routes():
                for path in (route, f"{route}?refresh=1"):
                    live.request("GET", path)
        self.assertEqual(ran, [], "a GET route reached the runner")


class HandlerShape(unittest.TestCase):
    """R11-D10 asked for this by name.

    Its cost paragraph says the old "there is no `do_POST`" assertion is to be
    *replaced by a stronger one -- every mutating handler enforces the three
    guards* -- and not simply deleted. A test of one route would not be that:
    it would pass while a second mutating route dispatched above the guards.
    So the handlers are enumerated from the syntax tree and the guards are
    checked by position.
    """

    def handlers(self) -> list[ast.FunctionDef]:
        source = (REPO_ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        found = [
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("do_") and node.name != "do_GET"
        ]
        self.assertTrue(found, "no mutating handler found; this test checks nothing")
        return found

    def test_every_mutating_handler_guards_before_it_dispatches(self) -> None:
        for handler in self.handlers():
            steps = [ast.unparse(step) for step in handler.body]
            host = next(i for i, s in enumerate(steps) if "host_ok" in s)
            token = next(i for i, s in enumerate(steps) if "compare_digest" in s)
            work = next(i for i, s in enumerate(steps) if "actions." in s)
            self.assertLess(host, token, handler.name)
            self.assertLess(token, work, handler.name)
            # Nothing but the docstring and the path parse may precede the
            # Host check: a read of the body, a route branch or a call placed
            # above it would run for a caller this server does not serve.
            for step in handler.body[:host]:
                self.assertIsInstance(
                    step, (ast.Expr, ast.Assign), f"{handler.name} acts before its guards")

    def test_the_host_list_is_resolved_before_the_socket_opens(self) -> None:
        """`allowed_hosts` forks; lazily it would fork inside the first request.

        Position, not presence: a call placed after `serve_forever` would be
        no call at all, and one left out entirely puts a ten-second timeout in
        front of whoever loads the page first.
        """
        source = (REPO_ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "serve":
                steps = [ast.unparse(step) for step in node.body]
                asked = next(i for i, s in enumerate(steps) if "allowed_hosts()" in s)
                served = next(i for i, s in enumerate(steps) if "ThreadingHTTPServer" in s)
                self.assertLess(asked, served)
                return
        raise AssertionError("serve is gone")

    def test_the_third_guard_is_the_absence_of_cors(self) -> None:
        """R11-D10's third guard is a header that must never be sent.

        Nothing enforces the absence of a line nobody wrote, which is why it
        is asserted rather than assumed: the token lives in the page, and a
        cross-origin caller allowed to read it would already have the page.
        """
        source = (REPO_ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("Access-Control-Allow", source)


class Live:
    """A real server on an ephemeral port, for the guards that are HTTP's.

    Host and token are header checks inside `BaseHTTPRequestHandler`, and a
    test that called the handler's methods directly would be testing its own
    fake instead of the thing a browser reaches.
    """

    def __init__(self, case: unittest.TestCase) -> None:
        self.case = case

    def __enter__(self) -> "Live":
        self.patch = unittest.mock.patch.object(plugins, "catalog", lambda: ([], ""))
        self.patch.start()
        handler = server.make_handler(server.Cache(REPO_ROOT / "missing"), "// none")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]
        return self

    def __exit__(self, *_) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.patch.stop()

    def request(self, method: str, path: str, body: bytes = b"",
                headers: dict | None = None, host: str | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            sent = dict(headers or {})
            if host is not None:
                sent["Host"] = host
            conn.request(method, path, body=body, headers=sent)
            reply = conn.getresponse()
            return reply.status, reply.read()
        finally:
            conn.close()


class Guards(unittest.TestCase):
    def test_a_post_without_the_token_is_refused(self) -> None:
        with Live(self) as live:
            status, _ = live.request(
                "POST", "/api/run", json.dumps({"action": "index"}).encode())
        self.assertEqual(status, 403)

    def test_a_post_with_the_wrong_token_is_refused(self) -> None:
        with Live(self) as live:
            status, _ = live.request(
                "POST", "/api/run", b"{}",
                {server.TOKEN_HEADER: "0" * 32, "Content-Type": "application/json"})
        self.assertEqual(status, 403)

    def test_a_request_from_a_host_this_server_does_not_serve_is_refused(self) -> None:
        """Before the token, so a rebound page cannot learn whether it guessed."""
        with Live(self) as live:
            status, _ = live.request(
                "POST", "/api/run", b"{}",
                {server.TOKEN_HEADER: server.TOKEN}, host="evil.example")
            self.assertEqual(status, 403)
            read, _ = live.request("GET", "/api/state", host="evil.example")
        self.assertEqual(read, 403, "the Host guard covers reads too")

    def test_a_token_holder_reaches_the_allow_list_and_not_a_shell(self) -> None:
        ran: list[str] = []
        with Live(self) as live, unittest.mock.patch.object(
            actions, "run", lambda name, entries: (ran.append(name) or ({"ok": True}, 200))
        ):
            status, body = live.request(
                "POST", "/api/run", json.dumps({"action": "index"}).encode(),
                {server.TOKEN_HEADER: server.TOKEN, "Content-Type": "application/json"})
        self.assertEqual((status, ran), (200, ["index"]))
        self.assertEqual(json.loads(body), {"ok": True})

    def test_the_only_writable_path_is_api_run(self) -> None:
        with Live(self) as live:
            status, _ = live.request(
                "POST", "/api/state", b"{}", {server.TOKEN_HEADER: server.TOKEN})
        self.assertEqual(status, 404)

    def test_a_body_larger_than_the_cap_is_refused_unread(self) -> None:
        """A POST names an id. Anything else is not a request with a shape."""
        with Live(self) as live:
            status, _ = live.request(
                "POST", "/api/run", b"x" * (server.BODY_BYTES + 1),
                {server.TOKEN_HEADER: server.TOKEN})
        self.assertEqual(status, 413)

    def test_a_body_with_no_length_is_refused_rather_than_read_as_empty(self) -> None:
        """A chunked body has no length to bound, and empty is the wrong read.

        Without this the handler answered a perfectly good POST with "no
        action named", which sends the operator looking at the allow-list for
        a bug that is in the request framing.
        """
        with Live(self) as live:
            conn = http.client.HTTPConnection("127.0.0.1", live.port, timeout=10)
            try:
                conn.putrequest("POST", "/api/run")
                conn.putheader(server.TOKEN_HEADER, server.TOKEN)
                conn.putheader("Transfer-Encoding", "chunked")
                conn.endheaders()
                conn.send(b"12\r\n{\"action\": \"index\"}\r\n0\r\n\r\n")
                self.assertEqual(conn.getresponse().status, 411)
            finally:
                conn.close()

    def test_a_negative_length_is_a_framing_error_not_an_empty_body(self) -> None:
        """`-1` parses. Reading it as zero blames the allow-list for the framing."""
        with Live(self) as live:
            status, _ = live.request(
                "POST", "/api/run", b"",
                {server.TOKEN_HEADER: server.TOKEN, "Content-Length": "-1"})
        self.assertEqual(status, 400)

    def test_a_body_that_is_not_json_is_a_400_not_a_traceback(self) -> None:
        with Live(self) as live:
            status, _ = live.request(
                "POST", "/api/run", b"action=index", {server.TOKEN_HEADER: server.TOKEN})
        self.assertEqual(status, 400)


class RegistryFailure(unittest.TestCase):
    def test_a_registry_that_will_not_read_is_said_and_not_shown_as_none(self) -> None:
        """`plugins.catalog` returns a complaint; dropping it is the quiet it refuses.

        A broken loader and a machine with no plugins are different answers,
        and the run strip would otherwise render both as an empty row of
        buttons.
        """
        broken = unittest.mock.patch.object(
            plugins, "catalog", lambda: ([], "plugin registry is not JSON"))
        broken.start()
        self.addCleanup(broken.stop)
        handler = server.make_handler(server.Cache(REPO_ROOT / "missing"), "// none")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection(*httpd.server_address, timeout=10)
            conn.request("GET", "/api/actions")
            payload = json.loads(conn.getresponse().read())
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
        self.assertEqual(payload["reason"], "plugin registry is not JSON")


class TokenDelivery(unittest.TestCase):
    def test_nothing_served_here_may_be_cached(self) -> None:
        """The page carries a secret and every route carries live state.

        A cached page persists a per-process token to disk, which is the
        opposite of what minting it in memory was for, and it POSTs a dead
        token after a restart -- a 403 that looks like a broken dashboard.
        """
        with Live(self) as live:
            for path in ("/", "/api/state"):
                conn = http.client.HTTPConnection("127.0.0.1", live.port, timeout=10)
                try:
                    conn.request("GET", path)
                    reply = conn.getresponse()
                    self.assertEqual(reply.getheader("Cache-Control"), "no-store", path)
                    reply.read()
                finally:
                    conn.close()

    def test_the_page_carries_the_token_and_the_source_does_not(self) -> None:
        """Per process, in memory: a token on disk is a credential nothing rotates."""
        self.assertIn(server.TOKEN_SLOT, server.PAGE)
        with Live(self) as live:
            status, body = live.request("GET", "/")
        page = body.decode()
        self.assertEqual(status, 200)
        self.assertIn(server.TOKEN, page)
        self.assertNotIn(server.TOKEN_SLOT, page)


if __name__ == "__main__":
    unittest.main()
