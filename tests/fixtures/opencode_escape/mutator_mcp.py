#!/usr/bin/env python3
"""Inert MCP stdio server for the config-escape regression fixture (sd:1329).

One tool, `mutate`, that records nothing beyond an append to the file named by
`MUTATOR_EVIDENCE`. It never touches the checkout, the network or any other
path, so a run that started it leaves evidence without doing harm.
`server-started` is appended at import time -- before any permission check --
so the evidence file proves whether opencode loaded and spawned this server at
all, which is the escape the test measures.
"""
import json
import os
import sys
import time

EV = os.environ["MUTATOR_EVIDENCE"]


def note(kind, payload=None):
    with open(EV, "a") as handle:
        handle.write(json.dumps({"t": time.time(), "kind": kind, "payload": payload}) + "\n")


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


note("server-started", {"argv": sys.argv})
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except ValueError:
        continue
    m, i, p = req.get("method"), req.get("id"), req.get("params") or {}
    if m == "initialize":
        send({"jsonrpc": "2.0", "id": i, "result": {
            "protocolVersion": p.get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mutator", "version": "0"}}})
    elif m == "notifications/initialized":
        note("initialized")
    elif m == "tools/list":
        send({"jsonrpc": "2.0", "id": i, "result": {"tools": [{
            "name": "mutate",
            "description": "Records a mutation with the given token.",
            "inputSchema": {"type": "object",
                            "properties": {"token": {"type": "string"}},
                            "required": ["token"]}}]}})
    elif m == "tools/call":
        note("tool-called", p)
        send({"jsonrpc": "2.0", "id": i, "result": {"content": [{"type": "text", "text": "recorded"}]}})
    elif m == "ping":
        send({"jsonrpc": "2.0", "id": i, "result": {}})
    elif i is not None:
        send({"jsonrpc": "2.0", "id": i, "error": {"code": -32601, "message": "no"}})
