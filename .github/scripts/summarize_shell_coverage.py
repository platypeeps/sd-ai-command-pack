#!/usr/bin/env python3
"""Summarize kcov's merged shipped-shell coverage from a Cobertura report.

kcov (the shell-coverage lane's collector) writes a Cobertura XML report for the
merged run data. This reads that report, counts line coverage across the shipped
``scripts/sd-ai-command-pack-*.sh`` surface only, and prints one line:

    <covered> <total> <pct>

Exit status:
    0  a non-zero measurement was found and printed
    2  the report parsed but measured zero shipped-shell lines (a kcov run that
       instrumented nothing exits 0 and looks like success — the caller treats
       this as a broken-plumbing failure, not merely unexercised code)
    1  the report is missing or unparseable
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Matches the shipped shell scripts regardless of the absolute prefix kcov
# records, while excluding tempdir copies and unrelated files.
_MARKER = "sd-ai-command-pack-"


def summarize(cobertura_path: Path) -> tuple[int, int]:
    """Return (covered_lines, total_lines) for shipped shell in the report."""
    tree = ET.parse(cobertura_path)
    covered = 0
    total = 0
    for cls in tree.iter("class"):
        filename = cls.get("filename", "")
        if _MARKER not in filename or not filename.endswith(".sh"):
            continue
        for line in cls.iter("line"):
            total += 1
            if int(line.get("hits", "0")) > 0:
                covered += 1
    return covered, total


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: summarize_shell_coverage.py <cobertura.xml>", file=sys.stderr)
        return 1
    path = Path(argv[1])
    try:
        covered, total = summarize(path)
    except (OSError, ET.ParseError) as exc:
        print(f"error: cannot read kcov report {path}: {exc}", file=sys.stderr)
        return 1
    if total == 0 or covered == 0:
        print(
            f"error: kcov measured zero shipped-shell lines "
            f"(covered={covered} total={total}). Coverage plumbing is broken, "
            f"not merely unexercised code.",
            file=sys.stderr,
        )
        return 2
    pct = 100.0 * covered / total
    print(f"{covered} {total} {pct:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
