#!/usr/bin/env bash
# Enforce doc coverage for shipped scripts: every manifest scripts/ target is
# either named in the installed guide or on the explicit internal allowlist.
# The allowlist is the public/internal classification made executable; adding
# a script forces a deliberate choice instead of a silent doc gap.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd -- "$REPO_ROOT" || exit 1

MANIFEST="${SHIPPED_SCRIPT_DOCS_MANIFEST:-manifest.json}"
GUIDE="${SHIPPED_SCRIPT_DOCS_GUIDE:-docs/SD_AI_COMMAND_PACK.md}"

if [ -z "${PYTHON_BIN:-}" ]; then
  if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

# Internal shipped scripts, exempt from guide coverage. Keep in sync with the
# classification record in CONTRIBUTING.md: manifest paths stay stable, but
# these are not operator entry points and their CLIs are not public surface.
INTERNAL_ALLOWLIST='
sd-ai-command-pack-review-local.py
sd_ai_command_pack_lib.py
'

MANIFEST_PATH="$MANIFEST" GUIDE_PATH="$GUIDE" ALLOWLIST="$INTERNAL_ALLOWLIST" \
  "$PYTHON_BIN" - <<'PY'
import json
import os
import sys
from pathlib import Path

manifest_path = Path(os.environ["MANIFEST_PATH"])
guide_path = Path(os.environ["GUIDE_PATH"])
allowlist = {line.strip() for line in os.environ["ALLOWLIST"].splitlines() if line.strip()}

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
targets = sorted({
    entry["source"]
    for entry in manifest["files"]
    if entry.get("kind") == "script"
})
if not targets:
    print(f"error: no script targets found in {manifest_path}", file=sys.stderr)
    sys.exit(1)

guide = guide_path.read_text(encoding="utf-8")

stale_allowlist = sorted(
    name for name in allowlist
    if not any(target.rsplit("/", 1)[-1] == name for target in targets)
)
missing = sorted(
    target for target in targets
    if target.rsplit("/", 1)[-1] not in allowlist
    and target.rsplit("/", 1)[-1] not in guide
)

if stale_allowlist:
    print("error: internal allowlist names scripts missing from the manifest:", file=sys.stderr)
    for name in stale_allowlist:
        print(f"  {name}", file=sys.stderr)
if missing:
    print(f"error: shipped scripts named neither in {guide_path} nor on the internal allowlist:", file=sys.stderr)
    for target in missing:
        print(f"  {target}", file=sys.stderr)
if stale_allowlist or missing:
    sys.exit(1)

print(f"Shipped-script doc coverage OK: {len(targets)} targets, {len(allowlist)} allowlisted internal.")
PY
