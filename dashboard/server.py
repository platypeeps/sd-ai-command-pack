"""An HTTP view over the fleet, on stdlib only.

**No GET has a side effect, and that is the promise rather than "GET is the
only verb".** 6b-7 gave the handler a POST, because the queue tabs exist to be
decided in and a read-only port of them is a list of questions nobody can
answer. Writing is POST, POST is Host-allowlisted and token-gated, and every
mutation resolves to an id in `RUN_ALLOWLIST` -- see `dashboard/actions.py`,
which is where the write path is reasoned about and what it deliberately does
not inherit from the dashboard being replaced.

Binds loopback, and this node's tailnet addresses when
`SD_DASHBOARD_TAILNET_BIND` asks -- never the wildcard, which would publish it
on every network the machine ever joins. D14 is decided as option (c)
(R11-D10): the replacement dashboard takes :8767 with the tailnet reach and
the token-gated writes the phone uses today. The Host allow-list is what makes the second half safe -- a
`tailscale serve` proxy in front of the loopback socket sends its own name, so
the list holds this node's MagicDNS names as well as the loopback ones, and
nothing else. No CORS header is sent, and none should be: the token lives in
the page, and a cross-origin caller that could read it would already have the
page.

The issue endpoint reads the index and never collects. A page load that could
reach GitHub would make refresh latency a property of opening a browser tab, and
would put a network call behind a verb whose whole promise is that it only
reads. `sd-dashboard index` is what fills the index; this serves what it finds.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import actions, collect, now, plugins, sessions, skills, store, work

# Per process, in memory, never written down. A restart invalidates it, which
# is correct: the page fetches it with the page, and a token that outlived the
# process would be a credential on disk that nothing rotates.
TOKEN = secrets.token_hex(16)
TOKEN_HEADER = "X-Dashboard-Token"
TOKEN_SLOT = "__SD_DASHBOARD_TOKEN__"

LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

# 8767, which the system dashboard held until 6b-8. It landed on 8768 at P3 so
# the two could run side by side while the parity checks ran; taking the port
# is what makes the swap a swap rather than a second dashboard.
DEFAULT_PORT = 8767
# A POST body names an action id and nothing else. Anything larger is not a
# request this server has a shape for, and reading it would be reading it.
BODY_BYTES = 4096
DEFAULT_HOST = "127.0.0.1"
CACHE_SECONDS = 20

def tailnet_names() -> set[str]:
    """This node's own MagicDNS names, or nothing.

    A `tailscale serve` proxy forwards the name the browser typed, so a list
    of only loopback names answers `http://tg-sol:8767/` with a 403 that looks
    like a network fault. Both spellings: `serve` publishes the short name and
    the FQDN as separate vhosts. No tailscale is a loopback-only dashboard.
    """
    try:
        out = subprocess.run(["tailscale", "status", "--json"],
                             capture_output=True, text=True, timeout=10, check=False)
        node = json.loads(out.stdout)["Self"]
        fqdn = (node.get("DNSName") or "").rstrip(".").lower()
        names = {fqdn, fqdn.split(".", 1)[0], (node.get("HostName") or "").lower()}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return set()
    # `HostName` is a display name -- "Sven's Mac Studio" -- and not always a
    # label, so it is filtered by shape rather than trusted for being reported.
    return {name for name in names if name and re.fullmatch(r"[a-z0-9.-]+", name)}


TAILNET_BIND = "SD_DASHBOARD_TAILNET_BIND"
OFF = frozenset({"0", "", "false", "no"})


def tailnet_addrs() -> list[str]:
    """This node's own tailnet addresses, when the operator has asked for them.

    Off unless `SD_DASHBOARD_TAILNET_BIND` says otherwise, because it widens
    the audience from this machine to every device on the tailnet. Why bind
    them at all when a `tailscale serve` proxy already forwards to loopback:
    an IP URL is the path that survives a phone whose resolver ignores
    MagicDNS, and a stale DNS answer cannot point it somewhere else. R11-D10's
    correction says carry both paths or knowingly drop one.
    """
    if os.environ.get(TAILNET_BIND, "0").strip().lower() in OFF:
        return []
    try:
        out = subprocess.run(["tailscale", "ip"], capture_output=True,
                             text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode:
        return []
    # Kept only if it parses as an address, the same treatment `tailnet_names`
    # gives a hostname and for the same reason: this widens a security
    # boundary, so a diagnostic line printed on stdout must not be able to add
    # a `Host` this server answers to. Found in review.
    addrs = []
    for line in out.stdout.splitlines():
        try:
            addrs.append(str(ipaddress.ip_address(line.strip())))
        except ValueError:
            continue
    return addrs


_HOSTS: frozenset[str] | None = None
_ADDRS: list[str] | None = None


PROBES = 3
PROBE_WAIT = 2.0


def bound_addrs(sleep=time.sleep) -> list[str]:
    """The tailnet addresses, probed a bounded number of times, then latched.

    One answer feeds both the allow-list and the binding. Asked twice, the
    tailnet could come up between them, and the server would bind an address
    the cached allow-list had never heard of -- 403 on exactly the path the
    bind exists to serve. Found in review.

    The cache is right and its *timing* was the defect (D-4). Latched on the
    first answer, a probe that came up empty because `tailscaled` had not
    finished starting left the dashboard loopback-only for the life of the
    process -- no crash, no error line, and nothing exiting for `KeepAlive` to
    restart. Retry first, then latch.

    Three probes two seconds apart, chosen not derived. Every way
    `tailnet_addrs` returns empty is immediate, so an ordinary failing start
    pays the 4 seconds of delay and nothing more; `tailscale` present but
    hanging costs its 10-second timeout three times, which exceeds
    `ThrottleInterval` and is accepted rather than argued away.
    """
    global _ADDRS
    if _ADDRS is None:
        for attempt in range(PROBES):
            found = tailnet_addrs()
            if found:
                _ADDRS = found
                return _ADDRS
            if attempt < PROBES - 1:
                sleep(PROBE_WAIT)
        _ADDRS = []
    return _ADDRS


def allowed_hosts() -> frozenset[str]:
    """The `Host` values this server answers to, asked once: this forks.

    Frozen because it is a security boundary handed to every request, and a
    mutable one could be widened in place. Found in review.

    An address it binds is an address it must answer to: a browser typing
    `http://100.82.165.108:8767/` sends that as its `Host`, and a list of
    names alone would 403 the one path the bind exists to serve. Both
    spellings for v6, since `host_ok` keeps the brackets the URL had.
    """
    global _HOSTS
    if _HOSTS is None:
        addrs = bound_addrs()
        _HOSTS = LOOPBACK | tailnet_names() | set(addrs) | {
            f"[{addr}]" for addr in addrs if ":" in addr}
    return _HOSTS


class ServerV6(ThreadingHTTPServer):
    """The same server, for an address that is not IPv4."""

    address_family = socket.AF_INET6


LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "[::1]", "::1", ""})


def host_name(header: str | None) -> str:
    """The host out of a `Host` header, port removed, lowercased.

    Split out of `host_ok` when a second caller appeared and got it wrong.
    `[::1]:8767` has three colons and only the one after `]` is the port, so
    `split(":")[0]` yields `[` -- which is not a loopback name, so the IPv6
    loopback the server explicitly supports was recorded as tailnet demand.
    One parser, two callers, no second chance to disagree.

    A header this cannot parse is returned unparsed rather than repaired. The
    bracketed branch used to end `+ "]"`, and `partition` yields the whole
    string when the separator is absent, so `[::1` came back as `[::1]` -- a
    closing bracket the header never carried. `[::1]evil.com` came back the
    same way, and so did every other `[::1]<anything>`: an unbounded family
    admitted as the loopback, not a list of cases. No allow-list holds an
    unparsed header, so `host_ok` refuses it and `tailnet_host` records what
    arrived; returning `""` would land in `LOOPBACK_NAMES` instead and file a
    malformed header as local.
    """
    if not header:
        return ""
    name = header.strip().lower()
    if name.startswith("["):
        # `[addr]` or `[addr]:digits`, or it is not parsed at all. A colon
        # alone does not bound this -- it admits `[::1]:<anything>`, the same
        # unbounded family wearing a port.
        address, bracket, port = name.partition("]")
        return address + bracket if bracket and (
            not port or (port[0] == ":" and port[1:].isdigit())) else name
    if name.count(":") == 1:
        # Unbracketed repairs nothing to begin with: one colon is a port and
        # is dropped, anything else returns whole. `localhost:evil` yields
        # `localhost`, which is the host that was actually asked for.
        return name.rsplit(":", 1)[0]
    return name


def host_ok(header: str | None) -> bool:
    """Whether a request's `Host` is one this server serves.

    This is what stops DNS rebinding: a name resolving to 127.0.0.1 makes a
    page on the open internet same-origin with this port, and the binding
    cannot tell it from the operator's own. The `Host` is what differs, so it
    is what is checked -- on reads too, because the reads are the fleet.
    """
    return bool(header) and host_name(header) in allowed_hosts()


PAGE = """<!doctype html>
<meta charset="utf-8"><title>sd dashboard</title>
<meta name="dashboard-token" content="__SD_DASHBOARD_TOKEN__">
<link rel="icon" href="data:,">
<style>
 :root{color-scheme:light dark}
 body{font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;margin:2rem;max-width:70rem}
 h1{font-size:1.1rem;margin:0 0 .25rem}
 .sub{opacity:.65;margin:0 0 1rem}
 nav{margin:0 0 1rem;display:flex;gap:.5rem}
 nav button{font:inherit;padding:.2rem .8rem;cursor:pointer;background:none;
  border:1px solid rgba(128,128,128,.4);border-radius:.25rem;color:inherit}
 nav button[aria-selected=true]{border-color:currentColor;font-weight:600}
 /* `display:contents` so plugin buttons sit in the nav's own flex row rather
    than in a box of their own -- the container exists to be replaced wholesale
    on every poll, not to group anything visually. */
 #plugin-tabs{display:contents}
 /* Severity is a band derived from `rank` and never from `kind` (R11-D20):
    the pill says how loud, the row says what. */
 .pill{display:inline-block;padding:0 .45rem;border-radius:.75rem;font-size:.8rem;
  border:1px solid currentColor}
 .broken{color:#c2410c}.look{color:#a16207}.queued{opacity:.6}
 nav .badge{display:inline-block;margin-left:.4rem;padding:0 .4rem;border-radius:.7rem;
  font-size:.75rem;background:#c2410c;color:#fff}
 nav .badge:empty{display:none}
 /* A button that reads as a link. It is a button because what it does is
    select a tab on this page, and a real `<a href>` would need a scroll
    target the panels do not have. */
 #run-buttons{display:flex;gap:.5rem;flex-wrap:wrap;margin:0 0 1rem}
 #run-buttons button{font:inherit;padding:.2rem .8rem;cursor:pointer;background:none;
  border:1px solid rgba(128,128,128,.4);border-radius:.25rem;color:inherit}
 #run-buttons button[disabled]{opacity:.5;cursor:progress}
 .linklike{font:inherit;padding:0;border:0;background:none;color:inherit;
  cursor:pointer;text-decoration:underline}
 input.filter{font:inherit;margin:0 0 .5rem;padding:.2rem .4rem;width:14rem;
  background:none;color:inherit;border:1px solid rgba(128,128,128,.4);border-radius:.25rem}
 th.sortable{cursor:pointer}
 th[aria-sort]{opacity:1}
 th[aria-sort=ascending]::after{content:" \u2191"}
 th[aria-sort=descending]::after{content:" \u2193"}
 table{border-collapse:collapse;width:100%}
 th,td{text-align:left;padding:.3rem .6rem;border-bottom:1px solid rgba(128,128,128,.25)}
 th{font-weight:600;opacity:.7}
 td.n{text-align:right;font-variant-numeric:tabular-nums}
 .dirty{color:#c2410c}.ahead{color:#1d4ed8}
 .you{font-weight:600}
 h2{font-size:.95rem;margin:1.5rem 0 .4rem;opacity:.8}
 [hidden]{display:none}
 a{color:inherit}
</style>
<h1>sd dashboard</h1>
<p class="sub" id="sub">loading\u2026</p>
<nav role="tablist" aria-label="views">
 <button id="tab-now" role="tab" aria-selected="true"
  aria-controls="panel-now">now<span class="badge" id="now-badge"></span></button>
 <button id="tab-repos" role="tab" aria-selected="false"
  aria-controls="panel-repos">repos</button>
 <button id="tab-prs" role="tab" aria-selected="false"
  aria-controls="panel-prs">prs</button>
 <button id="tab-issues" role="tab" aria-selected="false"
  aria-controls="panel-issues">issues</button>
 <button id="tab-work" role="tab" aria-selected="false"
  aria-controls="panel-work">work</button>
 <button id="tab-skills" role="tab" aria-selected="false"
  aria-controls="panel-skills">skills</button>
 <button id="tab-sessions" role="tab" aria-selected="false"
  aria-controls="panel-sessions">sessions</button>
 <span id="plugin-tabs"></span>
</nav>
<section id="panel-now" role="tabpanel" aria-labelledby="tab-now">
<p class="sub" id="now-sub"></p>
<table><thead><tr>
 <th>how</th><th>what</th><th>detail</th><th>where</th>
</tr></thead><tbody id="now-rows"></tbody></table>
</section>
<section id="panel-repos" role="tabpanel" aria-labelledby="tab-repos" hidden>
<table><thead><tr>
 <th>repo</th><th>group</th><th>branch</th><th class="n">dirty</th>
 <th class="n">ahead</th><th class="n">behind</th><th>last</th><th>subject</th>
</tr></thead><tbody id="rows"></tbody></table>
</section>
<section id="panel-prs" role="tabpanel" aria-labelledby="tab-prs" hidden>
<p class="sub" id="pr-sub"></p>
<h2>waiting on you</h2>
<table><thead><tr>
 <th>where</th><th>what</th><th>why</th><th>updated</th>
</tr></thead><tbody id="pr-needs"></tbody></table>
<details><summary id="pr-more-count">other open pull requests</summary>
<table><thead><tr>
 <th>where</th><th>what</th><th>why</th><th>updated</th>
</tr></thead><tbody id="pr-more"></tbody></table>
</details>
</section>
<section id="panel-issues" role="tabpanel" aria-labelledby="tab-issues" hidden>
<p class="sub" id="issue-sub"></p>
<h2>needs you</h2>
<table><thead><tr>
 <th>where</th><th>what</th><th>why</th><th>updated</th>
</tr></thead><tbody id="needs"></tbody></table>
<details><summary id="issue-more-count">other open issues</summary>
<table><thead><tr>
 <th>where</th><th>what</th><th>why</th><th>updated</th>
</tr></thead><tbody id="issue-more"></tbody></table>
</details>
</section>
<section id="panel-work" role="tabpanel" aria-labelledby="tab-work" hidden>
<p class="sub" id="work-sub"></p>
<h2>moving</h2>
<table><thead><tr>
 <th>repo</th><th>item</th><th>status</th><th>why</th><th>created</th>
</tr></thead><tbody id="work-moving"></tbody></table>
<h2>no status</h2>
<table><thead><tr>
 <th>repo</th><th>item</th><th>missing</th>
</tr></thead><tbody id="work-unstated"></tbody></table>
</section>
<section id="panel-skills" role="tabpanel" aria-labelledby="tab-skills" hidden>
<p class="sub" id="skill-sub"></p>
<table data-sd-search="filter skills"><thead><tr>
 <th>skill</th><th>ships here</th><th>installed</th><th>what it does</th>
</tr></thead><tbody id="skill-rows"></tbody></table>
</section>
<section id="panel-sessions" role="tabpanel" aria-labelledby="tab-sessions" hidden>
<p class="sub" id="session-sub"></p>
<h2>worktrees</h2>
<table><thead><tr>
 <th>repo</th><th>worktree</th><th>branch</th><th>state</th><th>path</th>
</tr></thead><tbody id="session-trees"></tbody></table>
<h2>running</h2>
<table><thead><tr>
 <th>pid</th><th>elapsed</th><th>command</th>
</tr></thead><tbody id="session-procs"></tbody></table>
</section>
<div id="plugin-panels"></div>
<h2>run</h2>
<p class="sub" id="run-sub">every button here is one allow-listed command</p>
<div id="run-buttons"></div>
<script src="/app.js"></script>
"""


class Cache:
    """One collection shared by every request, refreshed on a timer.

    Without it a page polling every few seconds re-shells `git` across the whole
    fleet each time, which is both slow and a good way to make the dashboard the
    reason the machine feels busy.
    """

    def __init__(self, root: Path, seconds: float = CACHE_SECONDS) -> None:
        self.root = root
        self.seconds = seconds
        self._lock = threading.Lock()
        self._state: dict | None = None
        self._at = 0.0

    def state(self, now: float | None = None) -> dict:
        stamp = time.monotonic() if now is None else now
        with self._lock:
            fresh = self._state is not None and stamp - self._at < self.seconds
            if not fresh:
                self._state = collect.build_state(self.root)
                self._at = stamp
            return dict(self._state or {}, cachedFor=round(self.seconds))


def _drop(kind: str, **fields: object) -> bool:
    """The default record sink: a server nobody handed a ledger to.

    Not `None` and a branch at each call site. Every write here is a byproduct
    (D-6), so the shape that cannot fail is the one where the sink is always
    callable and the *caller* decides whether records go anywhere.

    Returns True: a server with no ledger stored the ack as well as it was ever
    going to, and 503-ing the dismiss button because nobody wired one up would
    break the page for the plain `serve()` case.
    """

    return True


def make_handler(cache: Cache, script: str, record=_drop,
                 acked=frozenset) -> type[BaseHTTPRequestHandler]:
    # Substituted rather than formatted: `PAGE` is full of CSS braces, and
    # `.format` would have to escape every one of them to reach one slot.
    page = PAGE.replace(TOKEN_SLOT, TOKEN)

    class Handler(BaseHTTPRequestHandler):
        server_version = "sd-dashboard"

        def log_message(self, fmt: str, *args: object) -> None:
            """Silent by default; the access log is noise nobody reads."""

        def send_body(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            # Live fleet state, and the page carries a per-process token: a
            # cached copy is stale and a secret on somebody's disk. In review.
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib's spelling
            path = self.path.split("?", 1)[0]
            if not host_ok(self.headers.get("Host")):
                return self.send_error(403, "host not allowed")
            if path == "/":
                return self.send_body(page.encode(), "text/html; charset=utf-8")
            if path == "/app.js":
                return self.send_body(
                    script.encode(), "text/javascript; charset=utf-8"
                )
            if path == "/api/state":
                body = json.dumps(cache.state()).encode()
                return self.send_body(body, "application/json")
            if path == "/api/work":
                # Its own endpoint for the reason /api/plugins is: this reads
                # several hundred files across the fleet, and /api/state is
                # cached against a git fan-out on a different timer. Neither
                # should be able to hold up the other.
                body = json.dumps(work.collect_work(cache.root)).encode()
                return self.send_body(body, "application/json")
            if path == "/api/now":
                # Merged here rather than in the page: the two halves arrive
                # on two clocks, and joining them client-side would put the
                # ranking and the row text somewhere no test can reach. Both
                # sources are already cached -- the fleet for twenty seconds,
                # the loader for five -- so this adds a merge, not a collect.
                dismissed = acked()
                body = json.dumps({
                    "rows": [row for row in now.merge(
                        now.backbone_rows(cache.state()["repos"])
                        + now.pr_rows(tracker_payload("pull"))
                        + now.session_rows(sessions.fleet_worktrees(cache.root)),
                        plugins.cached_load()["rows"],
                    ) if row.get("id") not in dismissed],
                }).encode()
                return self.send_body(body, "application/json")
            if path == "/api/sessions":
                body = json.dumps(sessions.collect_sessions(cache.root)).encode()
                return self.send_body(body, "application/json")
            if path == "/api/skills":
                # The pack's own checkout, not the fleet root: this compares
                # what this repository ships against what is installed, and
                # `cache.root` is the directory full of everybody's checkouts.
                body = json.dumps(
                    skills.collect_skills(Path(__file__).resolve().parent.parent)
                ).encode()
                return self.send_body(body, "application/json")
            if path == "/api/issues":
                body = json.dumps(tracker_payload("issue")).encode()
                return self.send_body(body, "application/json")
            if path == "/api/prs":
                # The same index and the same shape as /api/issues. A pull
                # request is not a different fact about the world, only a
                # different tab, and the collect never knew the difference.
                body = json.dumps(tracker_payload("pull")).encode()
                return self.send_body(body, "application/json")
            if path == "/api/actions":
                # Ids and labels; the argv never leaves the process. The
                # registry's complaint rides along, because "none declared"
                # for a loader that cannot be read is the quiet it refuses.
                entries, failure = plugins.catalog()
                body = json.dumps(
                    {"actions": actions.catalog(entries), "reason": failure}
                ).encode()
                return self.send_body(body, "application/json")
            if path == "/api/plugins":
                # Not folded into /api/state: that payload is cached for
                # twenty seconds against a git fan-out, and a tile budgeted at
                # five seconds does not belong behind the same timer. Keeping
                # them apart also means one slow plugin cannot delay the repo
                # table, which is the view that works when nothing else does.
                body = json.dumps(plugins.cached_load()).encode()
                return self.send_body(body, "application/json")
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802 - stdlib's spelling
            """The only verb that writes, behind three guards (R11-D10).

            Host, then token, then an id that resolves in `RUN_ALLOWLIST`. In
            that order: a request from somewhere this server does not serve is
            refused before it can learn whether its token was right.
            """
            path = self.path.split("?", 1)[0]
            if not host_ok(self.headers.get("Host")):
                return self.send_error(403, "host not allowed")
            # Constant-time, because the comparison is against a secret and
            # the caller controls one side of it.
            if not hmac.compare_digest(self.headers.get(TOKEN_HEADER, ""), TOKEN):
                return self.send_error(403, "bad or missing token")
            if path not in ("/api/run", "/api/ack"):
                return self.send_error(404)
            # A length is required and `-1` is not one. Both were once read
            # as an empty body, which answers a real POST with "no action
            # named" -- the allow-list blamed for a fault in the framing. The
            # first was found by pressing the button, the second in review.
            try:
                length = int(self.headers["Content-Length"])
            except (KeyError, TypeError, ValueError):
                return self.send_error(411, "Content-Length required")
            if length < 0:
                return self.send_error(400, "Content-Length is not a length")
            if length > BODY_BYTES:
                return self.send_error(413, "body too large")
            try:
                sent = json.loads(self.rfile.read(max(length, 0)) or b"{}")
            except (OSError, ValueError):
                return self.send_error(400, "body is not JSON")
            if path == "/api/ack":
                # R11-D25 stands: this is not a parameterised action. The id is
                # written to a store and compared against on render -- it never
                # reaches `actions.run`, never reaches an argv, and there is no
                # interpolation site here for it to reach. That is why an ack
                # needs no parameter validator and no allow-list entry.
                identifier = sent.get("id") if isinstance(sent, dict) else None
                if not isinstance(identifier, str) or not identifier:
                    return self.send_error(400, "ack needs an id")
                # The one record whose failure the caller must hear about. A
                # mutation row is telemetry and may be dropped; an ack is a
                # command, and answering 200 to a write that never landed makes
                # the row vanish from the page and return on the next poll with
                # no explanation. Found in review.
                if not record("ack", id=identifier):
                    return self.send_error(503, "the ack was not stored")
                return self.send_body(b'{"ok":true}', "application/json")
            body, status = actions.run(
                sent.get("action") if isinstance(sent, dict) else None,
                plugins.catalog()[0],
            )
            # After the guards and after the action, and only when the action
            # was *served*: an unknown verb or a failed run comes back 4xx/5xx
            # and mutated nothing, so counting it would inflate the one number
            # R11-D10 turns into a deletion decision. Found in review, where
            # this recorded every outcome and the step's own gate claimed
            # otherwise without testing it.
            #
            # The `Host` is carried as a boolean rather than as itself:
            # R11-D10 counts requests *from a tailnet Host*, and the name adds
            # nothing the criterion asks for while making the ledger a log of
            # where the operator was. It is classified by `host_name`, not by
            # `split(":")` -- `[::1]:8767` splits at the wrong colon and turns
            # the supported IPv6 loopback into recorded tailnet demand.
            # Never before `send_body` and never able to affect it (D-6).
            if 200 <= status < 300:
                record("mutation",
                       action=sent.get("action") if isinstance(sent, dict) else None,
                       tailnet_host=host_name(self.headers.get("Host"))
                       not in LOOPBACK_NAMES)
            self.send_body(json.dumps(body).encode(), "application/json", status)

    return Handler


def tracker_payload(kind: str, path: Path | None = None) -> dict:
    """What the Issues or PRs tab renders, read straight from the index.

    One function for both because they are one table: GitHub's search returns
    issues and pull requests together and the index stores them together, so
    the only thing that differs between the two tabs is a `kind`.

    An absent index is a reported state, not an empty list and not an error: the
    two are different answers, and "no issues" where the truth is "nothing has
    collected yet" is the kind of wrong that looks right. Deliberately checked
    by existence rather than by opening the database, because `store.connect`
    creates one -- a GET that quietly creates a file is a write.
    """
    target = store.index_path() if path is None else path
    if not target.exists():
        return {
            "available": False,
            "reason": "no index yet -- run `sd-dashboard index`",
            "needsYou": [],
            "other": [],
            "indexedAt": "",
        }
    connection = store.connect(target)
    try:
        rows = store.issues(connection, state="open", kind=kind)
        # From every row, not from `rows`: an index holding only closed issues
        # has still been collected, and saying otherwise would report a fresh
        # index as never filled.
        indexed_at = store.latest_seen(connection)
    finally:
        connection.close()
    return {
        "available": True,
        "reason": "",
        "needsYou": [row for row in rows if store.needs_you(row)],
        "other": [row for row in rows if not store.needs_you(row)],
        # The newest evidence in the index, so the page can say how stale it is
        # rather than implying it is live.
        "indexedAt": indexed_at,
    }


def script_source() -> str:
    return (Path(__file__).resolve().parent / "app.js").read_text(encoding="utf-8")


def serve(root: Path, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST,
          record=_drop, acked=frozenset) -> None:
    """One server per address, never `0.0.0.0`.

    Binding the wildcard would publish this on every network the machine ever
    joins; binding named addresses publishes it on exactly the ones asked for.
    An address that refuses is reported and skipped rather than fatal -- the
    tailnet coming up after login is the ordinary case, and losing loopback
    because of it would be the wrong trade. Nothing bound at all is fatal.
    """
    # Asked before the socket opens: `allowed_hosts` forks, and lazily it
    # would do it inside the first request, putting a ten-second timeout in
    # front of a page load. Found in review.
    allowed_hosts()
    handler = make_handler(Cache(root), script_source(), record, acked)
    bound = []
    # Kept apart from `requested` because they fail differently and requirement
    # 6 cares about both. A probe that finds nothing makes `requested` exactly
    # `[host]`, so `requested == bound` and the counts alone report a clean
    # start -- which is the silent loopback-only bind this item exists to end,
    # reported as a success. Found in review.
    tailnet = bound_addrs()
    requested = [host] + tailnet
    for addr in requested:
        server = ServerV6 if ":" in addr else ThreadingHTTPServer
        try:
            httpd = server((addr, port), handler)
        except OSError as error:
            print(f"cannot bind {addr}:{port}: {error}", flush=True)
            continue
        bound.append(f"[{addr}]" if ":" in addr else addr)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # D-5. Written on every start, achieved or not, because it is what makes
    # R11-D10's count readable: a ledger with `bind` rows and no `mutation`
    # rows is genuine zero demand, while a ledger with neither is a server
    # that never ran and is "no evidence" rather than a zero. It is also the
    # only durable trace that a start went loopback-only.
    #
    # Before the `SystemExit`, not after. Review found the worst start of all
    # -- nothing bound at all -- leaving no row, so the total failure and the
    # server that never ran were the same evidence. `tailnet` is recorded
    # beside the counts because a probe that returned nothing cannot be seen
    # in them.
    record("bind", requested=len(requested), bound=len(bound), tailnet=len(tailnet))
    if not bound:
        raise SystemExit(f"nothing bound on port {port}")
    if not tailnet:
        print("WARNING: no tailnet address found after "
              f"{PROBES} probes; serving on {host} only. A phone on the "
              "tailnet cannot reach this.", flush=True)
    if len(bound) < len(requested):
        # Requirement 6: a start that publishes fewer addresses than were asked
        # for is not a successful start, and saying nothing is not available.
        print(f"WARNING: asked for {len(requested)} address(es), bound "
              f"{len(bound)} -- reachable only at {' '.join(bound)}", flush=True)
    print("dashboard on " + " ".join(f"http://{a}:{port}/" for a in bound), flush=True)
    while True:
        time.sleep(3600)
