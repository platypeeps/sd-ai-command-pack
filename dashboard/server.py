"""An HTTP view over the fleet, on stdlib only.

**No GET has a side effect, and that is the promise rather than "GET is the
only verb".** 6b-7 gave the handler a POST, because the queue tabs exist to be
decided in and a read-only port of them is a list of questions nobody can
answer. Writing is POST, POST is Host-allowlisted and token-gated, and every
mutation resolves to an id in `RUN_ALLOWLIST` -- see `dashboard/actions.py`,
which is where the write path is reasoned about and what it deliberately does
not inherit from the dashboard being replaced.

Binds loopback. D14 is decided as option (c) (R11-D10): the replacement
dashboard takes :8767 with the tailnet reach and the token-gated writes the
phone uses today. The Host allow-list is what makes the second half safe -- a
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
import json
import re
import secrets
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

DEFAULT_PORT = 8768
# A POST body names an action id and nothing else. Anything larger is not a
# request this server has a shape for, and reading it would be reading it.
BODY_BYTES = 4096
DEFAULT_HOST = "127.0.0.1"
CACHE_SECONDS = 20

def tailnet_names() -> set[str]:
    """This node's own MagicDNS names, or nothing.

    A `tailscale serve` proxy forwards the name the browser typed, so a list
    holding only the loopback names answers `http://tg-sol:8767/` with a 403
    indistinguishable from a network fault. Both spellings, because `serve`
    publishes the short name and the FQDN as separate vhosts. Best effort: no
    tailscale is a loopback-only dashboard, which is smaller, not broken.
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


_HOSTS: set[str] | None = None


def allowed_hosts() -> set[str]:
    """The `Host` values this server answers to, asked once: this forks."""
    global _HOSTS
    if _HOSTS is None:
        _HOSTS = set(LOOPBACK) | tailnet_names()
    return _HOSTS


def host_ok(header: str | None) -> bool:
    """Whether a request's `Host` is one this server serves.

    This is what stops DNS rebinding: a name resolving to 127.0.0.1 makes a
    page on the open internet same-origin with this port, and the binding
    cannot tell it from the operator's own. The `Host` is what differs, so it
    is what is checked -- on reads too, because the reads are the fleet.
    """
    if not header:
        return False
    name = header.strip().lower()
    # `[::1]:8767` splits at the bracket; everything else at the last colon,
    # and only when there is exactly one to split at.
    if name.startswith("["):
        name = name.partition("]")[0] + "]"
    elif name.count(":") == 1:
        name = name.rsplit(":", 1)[0]
    return name in allowed_hosts()


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
<h2>other open</h2>
<table><thead><tr>
 <th>where</th><th>what</th><th>why</th><th>updated</th>
</tr></thead><tbody id="pr-other"></tbody></table>
</section>
<section id="panel-issues" role="tabpanel" aria-labelledby="tab-issues" hidden>
<p class="sub" id="issue-sub"></p>
<h2>needs you</h2>
<table><thead><tr>
 <th>where</th><th>what</th><th>why</th><th>updated</th>
</tr></thead><tbody id="needs"></tbody></table>
<h2>other open</h2>
<table><thead><tr>
 <th>where</th><th>what</th><th>why</th><th>updated</th>
</tr></thead><tbody id="other"></tbody></table>
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


def make_handler(cache: Cache, script: str) -> type[BaseHTTPRequestHandler]:
    # Substituted rather than formatted: `PAGE` is full of CSS braces, and
    # `.format` would have to escape every one of them to reach one slot.
    page = PAGE.replace(TOKEN_SLOT, TOKEN)

    class Handler(BaseHTTPRequestHandler):
        server_version = "sd-dashboard"

        def log_message(self, fmt: str, *args: object) -> None:
            """Silent by default; the access log is noise nobody reads."""

        def send_body(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
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
                body = json.dumps({
                    "rows": now.merge(
                        now.backbone_rows(cache.state()["repos"])
                        + now.pr_rows(tracker_payload("pull"))
                        + now.session_rows(sessions.fleet_worktrees(cache.root)),
                        plugins.cached_load()["rows"],
                    ),
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
                # registry's own complaint rides along, because a loader that
                # cannot be read has no actions to offer and reporting that as
                # "none declared" is the quiet it refuses. Found in review.
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
            if path != "/api/run":
                return self.send_error(404)
            # Required, not defaulted to zero: a chunked body has no length
            # to bound, and reading it as empty answers a real POST with the
            # wrong error. Found by pressing the button.
            try:
                length = int(self.headers["Content-Length"])
            except (KeyError, TypeError, ValueError):
                return self.send_error(411, "Content-Length required")
            # `-1` parses, and reading it as an empty body gives the same
            # wrong answer the missing header used to: "no action named" for a
            # fault in the framing. Found in review.
            if length < 0:
                return self.send_error(400, "Content-Length is not a length")
            if length > BODY_BYTES:
                return self.send_error(413, "body too large")
            try:
                sent = json.loads(self.rfile.read(max(length, 0)) or b"{}")
            except (OSError, ValueError):
                return self.send_error(400, "body is not JSON")
            body, status = actions.run(
                sent.get("action") if isinstance(sent, dict) else None,
                plugins.catalog()[0],
            )
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


def serve(root: Path, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> None:
    handler = make_handler(Cache(root), script_source())
    with ThreadingHTTPServer((host, port), handler) as httpd:
        httpd.serve_forever()
