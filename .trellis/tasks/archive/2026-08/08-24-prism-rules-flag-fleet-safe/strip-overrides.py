#!/usr/bin/env python3
"""Remove the severityOverrides block from one consumer's .prism/rules.json.

Textual on purpose: json.dump would reformat a file whose only intended change
is the removal of one key, and `required` differs per repository -- it is the
one thing in these files that was deliberately authored locally.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

NEW = (
    "Configuration for the Prism code review tool, defining issue categories and "
    "required checks. The project-local schema file is distributed next to this file "
    "as rules.schema.json. Severity is the reviewer's per-finding judgement; do not "
    "add a severityOverrides block, which prism applies after the model answers and "
    "which replaces that judgement with a category lookup."
)
OLD = (
    "Configuration for the Prism code review tool, defining issue categories, severities, "
    "and required checks. The project-local schema file is distributed next to this file "
    "as rules.schema.json. The Prism config format keeps focus and severityOverrides "
    "separate; keep their category names in sync."
)


def main(repo: str) -> int:
    path = Path(repo) / ".prism/rules.json"
    raw = path.read_text(encoding="utf-8")
    before = json.loads(raw)
    changed = False

    block = re.search(r'\n  "severityOverrides": \{.*?\n  \},', raw, re.S)
    if block:
        raw = raw[: block.start()] + raw[block.end() :]
        changed = True
    if OLD in raw:
        raw = raw.replace(OLD, NEW, 1)
        changed = True
    if changed:
        path.write_text(raw, encoding="utf-8")

    after = json.loads(raw)
    assert "severityOverrides" not in after, path
    assert after.get("focus") == before.get("focus"), f"{path}: focus changed"
    assert after.get("required") == before.get("required"), f"{path}: required changed"
    print(
        f"{'stripped' if changed else 'no-change'}  {path}  "
        f"focus={len(after.get('focus') or [])} required={len(after.get('required') or [])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
