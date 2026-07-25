#!/usr/bin/env python3
"""Deterministic provider fixture for the exact-scope review-stage tests."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

provider, artifact, log_value, mode = sys.argv[1:]
log = Path(log_value)
Path(artifact).mkdir(parents=True, exist_ok=True)
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as stream:
    stream.write(f"{provider}:start:{time.time()}\n")
if mode == "barrier":
    deadline = time.time() + 2
    starts = 0
    while time.time() < deadline:
        starts = sum(
            ":start:" in line for line in log.read_text(encoding="utf-8").splitlines()
        )
        if starts >= 2:
            break
        time.sleep(0.02)
    if starts < 2:
        raise SystemExit("parallel start barrier timed out")
else:
    time.sleep(2 if mode == "slow" else 0.35)
with log.open("a", encoding="utf-8") as stream:
    stream.write(f"{provider}:end:{time.time()}\n")
if mode == "finding":
    print(
        json.dumps(
            {
                "status": "findings",
                "findings": [
                    {
                        "path": "src/app.py",
                        "line": 2,
                        "severity": "high",
                        "summary": "validate state",
                        "family": "boundary-validation",
                    }
                ],
            }
        )
    )
elif mode == "finding-alt":
    print(
        json.dumps(
            {
                "status": "findings",
                "findings": [
                    {
                        "path": "src/app.py",
                        "line": 2,
                        "severity": "low",
                        "summary": "validate state",
                        "family": "security",
                    }
                ],
            }
        )
    )
elif mode in {"case-upper", "case-lower"}:
    path = "SRC/App.py" if mode == "case-upper" else "src/app.py"
    print(
        json.dumps(
            {
                "status": "findings",
                "findings": [
                    {
                        "path": path,
                        "line": 2,
                        "severity": "medium",
                        "summary": "same summary",
                    }
                ],
            }
        )
    )
elif mode == "finding-fail":
    print(
        json.dumps(
            {
                "status": "findings",
                "findings": [
                    {
                        "path": "src/app.py",
                        "line": 2,
                        "summary": "mapped clean finding",
                    }
                ],
            }
        )
    )
    raise SystemExit(9)
elif mode == "malicious-finding":
    print(
        json.dumps(
            {
                "status": "findings",
                "findings": [
                    {
                        "path": "../secret",
                        "line": True,
                        "summary": "unsafe provider fields",
                        "disposition": "fixed",
                    }
                ],
            }
        )
    )
elif mode == "fail":
    print(json.dumps({"status": "clean", "findings": []}))
    print("provider failed", file=sys.stderr)
    raise SystemExit(9)
elif mode == "rate-limit":
    print("provider rate limited", file=sys.stderr)
    raise SystemExit(8)
elif mode == "cancelled":
    print("provider cancelled", file=sys.stderr)
    raise SystemExit(10)
else:
    print(json.dumps({"status": "clean", "findings": []}))
