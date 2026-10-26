"""A fake of the system checkout's `mail_intake.py` for the dashboard's tests (sd:6044).

What the dashboard calls: the conf and state paths, the conf parser, the two state readers, and the JSON-RPC client
that reaches workspace-mcp, which each test serves from a fixture server.
"""

import csv
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    account: str
    me: set
    aliases: dict


def paths(environ):
    config = Path(environ.get("SYSTEM_TOOLS_CONFIG")
                  or Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "system")
    return (Path(environ.get("MAIL_INTAKE_CONFIG") or config / "mail-intake" / "mail-intake.conf"),
            Path(environ.get("MAIL_INTAKE_STATE", Path.home() / ".local/share/mail-intake")))


def parse_config(text):
    account, me, aliases, problems = "", set(), {}, []
    for number, raw in enumerate(text.splitlines(), start=1):
        parts = [part.strip() for part in raw.strip().split("|")]
        if parts == [""] or parts[0].startswith("#"):
            continue
        if parts[0] == "account" and len(parts) == 2:
            account = parts[1]
        elif parts[0] == "me" and len(parts) == 2:
            me.add(parts[1].lower())
        elif parts[0] == "alias" and len(parts) == 3:
            aliases[parts[1]] = parts[2].lower()
        else:
            problems.append(f"line {number}: cannot read {raw.strip()!r}")
    for missing, problem in ((account, "no account row: the MCP server needs to know whose mailbox"),
                             (aliases, "no alias rows: nothing to watch"),
                             (me, "no me rows: every message would look like it needs a reply")):
        if not missing:
            problems.append(problem)
    return (None, problems) if problems else (Config(account, me | {account.lower()}, aliases), [])


def read_thread_rows(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["thread_id"]: [row.get(column, "") for column in ("thread_id", "last_message_id", "last_at",
                                                                       "seen_at")]
                for row in csv.DictReader(handle) if row.get("thread_id")}


def read_arrivals(path, unreported_only=True):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("thread_id")]
    return [row for row in rows if not (row.get("reported_at") or "").strip()] if unreported_only else rows


class McpError(RuntimeError):
    pass


class Mcp:
    def __init__(self, url, timeout=60):
        self.url, self.timeout, self.session, self._id = url, timeout, None, 0

    def _post(self, body):
        self._id += 1
        body = {"jsonrpc": "2.0", **({"id": self._id} if "method" in body and "id" not in body else {}), **body}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   **({"mcp-session-id": self.session} if self.session else {})}
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8", "replace"), dict(response.headers)
        except urllib.error.URLError as error:
            raise McpError(f"cannot reach {self.url}: {error}") from error

    def connect(self):
        _, headers = self._post({"id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "mail-intake", "version": "1.0"}}})
        self.session = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        if not self.session:
            raise McpError("workspace-mcp gave no session id")
        self._post({"method": "notifications/initialized"})

    def call(self, name, arguments):
        payload, _ = self._post({"method": "tools/call", "params": {"name": name, "arguments": arguments}})
        data = [line[5:].strip() for line in payload.splitlines() if line.startswith("data:")]
        try:
            parsed = json.loads(data[-1] if data else payload)
        except json.JSONDecodeError as error:
            raise McpError(f"{name}: unparseable reply: {error}") from error
        if "error" in parsed:
            raise McpError(f"{name}: {parsed['error']}")
        result = parsed.get("result", {})
        out = "".join(part.get("text", "") for part in result.get("content", []) if isinstance(part, dict))
        if result.get("isError"):
            raise McpError(f"{name}: {out[:300]}")
        return out
