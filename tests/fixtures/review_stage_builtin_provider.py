#!/usr/bin/env python3
"""Native Prism/Gito output fixture selected by the executable filename."""

from __future__ import annotations

import json
import sys
from pathlib import Path

config = json.loads(Path(__file__).with_name("provider-config.json").read_text())
provider = Path(sys.argv[0]).name
log = Path(config["log"])
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as stream:
    stream.write(f"{provider} {' '.join(sys.argv[1:])}\n")

if provider == "prism":
    if config["prismMode"] == "invalid":
        print("human finding that must not become clean")
    else:
        print(
            json.dumps(
                {
                    "findings": [
                        {
                            "severity": "medium",
                            "category": "correctness",
                            "title": "Prism finding",
                            "locations": [
                                {
                                    "path": "src/app.py",
                                    "lines": {"start": 2, "end": 2},
                                }
                            ],
                        }
                    ]
                }
            )
        )
elif provider == "gito":
    try:
        output = Path(sys.argv[sys.argv.index("--out") + 1])
    except (ValueError, IndexError):
        raise SystemExit("gito fixture requires --out <path>") from None
    output.mkdir(parents=True, exist_ok=True)
    count = config["gitoCount"]
    issues = [
        {
            "title": "Gito finding" if count == 1 else f"Gito finding {index + 1}",
            "details": "details",
            "severity": 2,
            "tags": ["correctness"],
            "affected_lines": [{"start_line": index + 1}],
        }
        for index in range(count)
    ]
    report = {"total_issues": count, "issues": {"src/app.py": issues}}
    (output / "code-review-report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
else:
    raise SystemExit(f"unsupported fixture provider: {provider}")
