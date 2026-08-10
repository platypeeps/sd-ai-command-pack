#!/usr/bin/env python3
"""Measure, per fleet consumer, what a thin conversion would break.

This is the reproducible form of the fleet-wide measurement quoted in
``design.md``. It is research, not shipped tooling: it lives in the task's
``research/`` directory, carries no ``manifest.json`` row, and the real
``scripts/sd-ai-command-pack-thin-resweep.py`` supersedes it. It exists so the
counts in the planning artifacts can be re-derived instead of trusted, and so a
later reader can see the exact classification rule the counts came from.

Run from an ``sd-ai-command-pack`` source checkout::

    .venv/bin/python .trellis/tasks/08-10-thin-conversion-tooling/research/\
fleet-blocker-scan.py --out .trellis/tasks/08-10-thin-conversion-tooling/\
research/fleet-blocker-scan.json

Discovery starts from the **removal set**, not from the string
``sd-ai-command-pack``. An earlier version searched for the pack name and then
claimed in prose to match removed paths; the two are not the same set, and the
difference was not theoretical -- ``sd-github-review/test/metadata.test.js:490``
names the removed ``.agents/skills/sd-status/SKILL.md`` without containing the
pack name anywhere on the line, and was silently absent from the first
published counts.

Every consumer's ``head``, ``indexDigest``, ``worktreeDigest``, and per-file
results land in the JSON. A dirty tree does not invalidate the measurement, but
``head`` alone cannot identify it, so the digests are what make a rerun
comparable.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from installer import conversion  # noqa: E402
from installer.provenance import PROVENANCE_FILE  # noqa: E402

PARTITION = ROOT / "docs/fleet/surface-partition.json"
REGISTRY = ROOT / "docs/fleet/consumers.json"

# Executable-by-nature classification. The rule fails *closed*: a file that
# might cause execution is on the execution surface, and only files that plainly
# cannot are advisory. A top-level directory allowlist fails open instead --
# measured counterexamples: se-ai-command-pack's
# templates/skills/se-review-skills/scripts/skill_review.py (nested scripts/),
# and mezmo_benchmark's root CLAUDE.md, which tells an agent to run a script
# conversion removes.
EXECUTABLE_SUFFIXES = frozenset(
    {".sh", ".bash", ".zsh", ".py", ".mjs", ".cjs", ".js", ".ts", ".rb", ".pl"}
)
EXECUTABLE_SEGMENTS = frozenset(
    {"scripts", "bin", "tools", "test", "tests", ".githooks", ".husky"}
)
EXECUTABLE_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    ".circleci/",
    ".devcontainer/",
    # Agent-executed surfaces. A prompt or rule that tells an agent to run a
    # script is an execution surface even though nothing about it is a shell
    # file.
    ".github/prompts/",
    ".github/instructions/",
    ".claude/commands/",
    ".claude/rules/",
    ".claude/skills/",
    ".agents/",
    ".gemini/commands/",
    ".opencode/command/",
    ".codex/",
)
EXECUTABLE_NAMES = frozenset(
    {
        "Makefile",
        "makefile",
        "GNUmakefile",
        "package.json",
        "pyproject.toml",
        "tox.ini",
        "noxfile.py",
        "justfile",
        "Justfile",
        "Taskfile.yml",
        "Taskfile.yaml",
        ".pre-commit-config.yaml",
        ".gitlab-ci.yml",
        "Dockerfile",
        # Root agent instruction files. These are read by an agent as
        # instructions to act on, which is execution by proxy.
        "CLAUDE.md",
        "AGENTS.md",
        "GEMINI.md",
        "QWEN.md",
        "copilot-instructions.md",
        ".cursorrules",
        "SKILL.md",
    }
)
EXECUTABLE_NAME_SUFFIXES = (".prompt.md", ".instructions.md")

# Managed-block delimiters. A citation inside a block the conversion strips is
# scheduled; the same citation outside it is judged normally.
BLOCK_START = re.compile(
    r"(SD-AI-COMMAND-PACK:[A-Z-]+:START|# sd-ai-command-pack [a-z-]+ start)"
)
BLOCK_END = re.compile(
    r"(SD-AI-COMMAND-PACK:[A-Z-]+:END|# sd-ai-command-pack [a-z-]+ end)"
)

# Path-shaped tokens. The class keeps "*" and "?" so a glob citation survives
# tokenization -- measured: loadsmith/.github/workflows/ci.yml:149 addresses the
# removed population as scripts/sd-ai-command-pack-*.sh and names no exact path
# or basename at all.
TOKEN = re.compile(r"[\w.*?/-]*[\w*?][./][\w.*?/-]*")

SKIP_DIRS = (".git/",)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def digest_of(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def is_executable_surface(repo: Path, relative: str) -> bool:
    path = Path(relative)
    if path.suffix in EXECUTABLE_SUFFIXES:
        return True
    if path.name in EXECUTABLE_NAMES:
        return True
    if path.name.endswith(EXECUTABLE_NAME_SUFFIXES):
        return True
    if relative.startswith(EXECUTABLE_PREFIXES):
        return True
    if EXECUTABLE_SEGMENTS.intersection(path.parts[:-1]):
        return True
    full = repo / relative
    return not full.is_symlink() and full.is_file() and os.access(full, os.X_OK)


def reference_forms(removed: frozenset[str]) -> frozenset[str]:
    """Every string that unambiguously names a removed path.

    Full paths, their >=2-segment suffixes (so a reference written relative to
    another directory still matches), and distinctive basenames -- only those
    carrying the pack name. A bare basename is deliberately excluded: the
    removal set contains `SKILL.md`, `config.toml`, and `ci.yml`, and admitting
    those matched 67 lines across the fleet that name nothing removed, 12 of
    them in the two blocking buckets. Precision matters more here than reach,
    because a false blocker refuses a conversion that should proceed.
    """
    forms: set[str] = set()
    for entry in removed:
        forms.add(entry)
        parts = entry.split("/")
        for index in range(1, len(parts) - 1):
            forms.add("/".join(parts[index:]))
        if "sd-ai-command-pack" in parts[-1]:
            forms.add(parts[-1])
    return frozenset(forms)


def needle_pattern(removed: frozenset[str]) -> re.Pattern[str]:
    """Regex over every reference form, plus the pack name.

    The pack name is in the discovery set but not in the matching set: it is
    what makes a glob citation like scripts/sd-ai-command-pack-*.sh
    discoverable, while the match itself is still decided against removed paths.
    """
    needles = set(reference_forms(removed)) | {"sd-ai-command-pack"}
    ordered = sorted(needles, key=len, reverse=True)
    return re.compile("|".join(re.escape(needle) for needle in ordered))


def cites_removed_path(
    token: str, removed: frozenset[str], suffixes: frozenset[str]
) -> bool:
    """Does this token name something the conversion removes?

    Exact, suffix, and fnmatch, in that order. All three are a lower bound: a
    path composed at runtime from variables is invisible to any static reader,
    which is why --revert-thin -- not this check -- is what makes the conversion
    safe.
    """
    token = token.strip("'\"`,;:()[]{}<>")
    if not token:
        return False
    if "*" in token or "?" in token:
        return any(fnmatch.fnmatch(entry, token) for entry in removed)
    return token in removed or token in suffixes


def block_spans(lines: list[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for number, line in enumerate(lines, start=1):
        if start is None and BLOCK_START.search(line):
            start = number
        elif start is not None and BLOCK_END.search(line):
            spans.append((start, number))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def provenance_digests(repo: Path) -> dict[str, str]:
    path = repo / PROVENANCE_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError):
        return {}
    files = payload.get("files")
    return files if isinstance(files, dict) else {}


def file_digest(path: Path) -> str | None:
    """Digest in provenance's own ``sha256:<hex>`` form, or None.

    Returning bare hex fails open: every recorded value carries the prefix, a
    bare comparison never matches, every pack file looks consumer-authored, and
    packDefects stays empty while appearing healthy. Measured on this scanner's
    first run, which reported packDefects=0 for all 8 consumers.
    """
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    except OSError:
        return None


def scan(name: str, repo: Path, platforms: frozenset[str]) -> dict:
    receipt = conversion.read_installed_targets_receipt(repo)
    partition = conversion.load_partition(PARTITION)
    occupied = conversion.occupied_receipt_targets(repo, receipt)
    plan = conversion.build_conversion_plan(
        receipt, partition, platforms, occupied=occupied
    )
    removed = frozenset(plan.delete) | frozenset(plan.retire)
    suffixes = reference_forms(removed)
    stripped = frozenset(plan.block_strip)
    managed = frozenset(receipt.entries)
    recorded = provenance_digests(repo)
    needles = needle_pattern(removed)

    buckets: dict[str, list[dict]] = {
        "blockers": [],
        "packDefects": [],
        "scheduled": [],
        "advisories": [],
    }
    tracked = [
        entry
        for entry in git(repo, "ls-files", "-z").split("\0")
        if entry and not entry.startswith(SKIP_DIRS)
    ]
    for relative in tracked:
        if relative in removed:
            buckets["scheduled"].append({"file": relative, "line": None})
            continue
        full = repo / relative
        if full.is_symlink():
            # Fails closed: a symlink is not read, and a receipt entry that is a
            # symlink is not vouchable, so it cannot earn the pack exemption.
            if relative in managed:
                buckets["packDefects"].append(
                    {"file": relative, "line": None, "detail": "symlinked pack target"}
                )
            continue
        try:
            body = full.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            # Binary or unreadable. Unreadable *pack* content is unverifiable
            # and therefore blocking; unreadable consumer content cannot cite
            # anything a static reader can see, and is reported as such.
            if relative in managed:
                buckets["packDefects"].append(
                    {"file": relative, "line": None, "detail": "unreadable pack target"}
                )
            continue
        lines = body.splitlines()
        if not needles.search(body):
            continue

        spans = block_spans(lines) if relative in stripped else []
        vouched = recorded.get(relative)
        actual = file_digest(full)
        pack_owned = relative in managed and vouched is not None and vouched == actual
        # A receipt entry provenance never vouches (managed block, force
        # preserved, generated) has no digest to compare. Managed-block content
        # is still the pack's inside its markers; everything else in that class
        # is user-tunable by design and is judged as consumer-authored.
        unvouchable = relative in managed and vouched is None
        executable = is_executable_surface(repo, relative)

        for number, line in enumerate(lines, start=1):
            if not needles.search(line):
                continue
            if not any(
                cites_removed_path(token, removed, suffixes)
                for token in TOKEN.findall(line)
            ):
                continue
            entry = {"file": relative, "line": number, "detail": line.strip()[:160]}
            in_block = any(start <= number <= end for start, end in spans)
            if in_block:
                # The block itself is stripped, so this reference leaves with it.
                buckets["scheduled"].append(entry)
            elif pack_owned or (unvouchable and _inside_pack_block(lines, number)):
                # Kept, still the pack's own bytes, and it names something that
                # disappears: the pack ships a broken reference. A pack defect,
                # not a consumer verdict, and it blocks until a release fixes it.
                buckets["packDefects"].append(entry)
            elif executable:
                buckets["blockers"].append(entry)
            else:
                buckets["advisories"].append(entry)

    index = git(repo, "ls-files", "-s")
    return {
        "consumer": name,
        "repo": str(repo),
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "indexDigest": digest_of(index),
        "worktreeDigest": digest_of(git(repo, "status", "--porcelain")),
        "worktreeClean": not git(repo, "status", "--porcelain").strip(),
        "receiptEntries": len(receipt.entries),
        "removedTargets": len(removed),
        "trackedFiles": len(tracked),
        "counts": {key: len(value) for key, value in buckets.items()},
        "blockerFiles": sorted({entry["file"] for entry in buckets["blockers"]}),
        "packDefectFiles": sorted({entry["file"] for entry in buckets["packDefects"]}),
        "verdict": (
            "clear"
            if not buckets["blockers"] and not buckets["packDefects"]
            else "blocked"
        ),
        **buckets,
    }


def _inside_pack_block(lines: list[str], number: int) -> bool:
    """Is this line inside a pack-managed block in a file we cannot vouch?

    Managed-block targets are shared ownership: provenance never records a
    whole-file digest for them, so digest comparison cannot decide. The markers
    can. Outside the markers the file is the consumer's.
    """
    return any(start <= number <= end for start, end in block_spans(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the full JSON result here")
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    results = []
    for entry in registry["consumers"]:
        repo = Path(os.path.expanduser(entry["pathHint"]))
        if not repo.is_dir():
            results.append({"consumer": entry["name"], "error": "checkout missing"})
            continue
        results.append(scan(entry["name"], repo, frozenset(entry["platforms"])))

    payload = {
        "schemaVersion": 2,
        "kind": "thin-conversion-fleet-blocker-scan",
        "packHead": git(ROOT, "rev-parse", "HEAD").strip(),
        "packWorktreeDigest": digest_of(git(ROOT, "status", "--porcelain")),
        "packWorktreeClean": not git(ROOT, "status", "--porcelain").strip(),
        "scannerDigest": file_digest(Path(__file__)),
        "consumers": results,
    }
    if args.out:
        args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for result in results:
        if "error" in result:
            print(f"{result['consumer']}: {result['error']}")
            continue
        counts = result["counts"]
        print(
            f"{result['consumer']}: {result['verdict']} "
            f"blockers={counts['blockers']} in {len(result['blockerFiles'])} file(s), "
            f"packDefects={counts['packDefects']} in "
            f"{len(result['packDefectFiles'])} file(s), "
            f"scheduled={counts['scheduled']}, advisories={counts['advisories']}"
        )
    clear = [r for r in results if r.get("verdict") == "clear"]
    print(f"consumers with a clear verdict: {len(clear)} of {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
