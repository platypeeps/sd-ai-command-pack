"""A read-only HTTP view over the fleet, on stdlib only.

GET is the only verb the handler implements. That is the design, not an
oversight to be filled in later: the plan's rule is that every UI mutation maps
to a `bin/` command the operator runs, and a server that cannot write cannot
drift into running agents, committing, or pushing on a page load.

Binds loopback. D14 (phone access) is undecided, and the honest default while it
is undecided is the one that cannot expose the fleet to the network; widening it
is a decision record, not a flag someone sets in passing.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import collect

DEFAULT_PORT = 8768
DEFAULT_HOST = "127.0.0.1"
CACHE_SECONDS = 20

PAGE = """<!doctype html>
<meta charset="utf-8"><title>sd dashboard</title>
<link rel="icon" href="data:,">
<style>
 :root{color-scheme:light dark}
 body{font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;margin:2rem;max-width:70rem}
 h1{font-size:1.1rem;margin:0 0 .25rem}
 .sub{opacity:.65;margin:0 0 1.5rem}
 table{border-collapse:collapse;width:100%}
 th,td{text-align:left;padding:.3rem .6rem;border-bottom:1px solid rgba(128,128,128,.25)}
 th{font-weight:600;opacity:.7}
 td.n{text-align:right;font-variant-numeric:tabular-nums}
 .dirty{color:#c2410c}.ahead{color:#1d4ed8}
</style>
<h1>sd dashboard</h1>
<p class="sub" id="sub">loading…</p>
<table><thead><tr>
 <th>repo</th><th>group</th><th>branch</th><th class="n">dirty</th>
 <th class="n">ahead</th><th class="n">behind</th><th>last</th><th>subject</th>
</tr></thead><tbody id="rows"></tbody></table>
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
    class Handler(BaseHTTPRequestHandler):
        server_version = "sd-dashboard"

        def log_message(self, fmt: str, *args: object) -> None:
            """Silent by default; the access log is noise nobody reads."""

        def send_body(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib's spelling
            path = self.path.split("?", 1)[0]
            if path == "/":
                return self.send_body(PAGE.encode(), "text/html; charset=utf-8")
            if path == "/app.js":
                return self.send_body(
                    script.encode(), "text/javascript; charset=utf-8"
                )
            if path == "/api/state":
                body = json.dumps(cache.state()).encode()
                return self.send_body(body, "application/json")
            self.send_error(404)

    return Handler


def script_source() -> str:
    return (Path(__file__).resolve().parent / "app.js").read_text(encoding="utf-8")


def serve(root: Path, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> None:
    handler = make_handler(Cache(root), script_source())
    with ThreadingHTTPServer((host, port), handler) as httpd:
        httpd.serve_forever()
