#!/usr/bin/env python3
"""Summarize kcov's merged shipped-shell coverage from a Cobertura report.

kcov (the shell-coverage lane's collector) writes a Cobertura XML report for the
merged run data. This reads that report, counts line coverage across the shipped
``scripts/sd-ai-command-pack-*.sh`` surface only, and prints one line:

    <covered> <total> <pct>

Exit status:
    0  the report parsed and shipped-shell lines were measured (total > 0);
       the printed percentage may legitimately be 0.0% when the surface is
       present but unexercised — that is data, not a failure (measure before
       gating: no floor is enforced here)
    2  the report parsed but measured zero shipped-shell LINES (total == 0): a
       kcov run that instrumented nothing exits 0 and looks like success, so
       the caller treats a zero-line report as broken plumbing
    1  the report is missing or unparseable
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Matches the shipped shell scripts by basename, regardless of the absolute
# prefix kcov records. The subprocess tests run the scripts from many ephemeral
# tempdir copies, so the same script appears under many different paths; we
# normalize by basename and union covered line numbers across every copy so the
# result is a real per-script reach number rather than a per-copy sum.
_MARKER = "sd-ai-command-pack-"


def summarize(cobertura_path: Path) -> tuple[int, int]:
    """Return (covered_lines, total_lines) for shipped shell in the report.

    Executable and covered line numbers are unioned per basename across all
    copies of each script, so a line reached in any copy counts once.
    """
    tree = ET.parse(cobertura_path)
    executable: dict[str, set[int]] = {}
    covered_lines: dict[str, set[int]] = {}
    for cls in tree.iter("class"):
        filename = cls.get("filename", "")
        if _MARKER not in filename or not filename.endswith(".sh"):
            continue
        name = os.path.basename(filename)
        exe = executable.setdefault(name, set())
        cov = covered_lines.setdefault(name, set())
        for line in cls.iter("line"):
            number = int(line.get("number", "0"))
            exe.add(number)
            if int(line.get("hits", "0")) > 0:
                cov.add(number)
    total = sum(len(lines) for lines in executable.values())
    covered = sum(len(lines) for lines in covered_lines.values())
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
    if total == 0:
        # total == 0 means kcov attributed no shipped-shell lines at all — a
        # plumbing break, since a real run always parses executable lines. A
        # covered == 0 / total > 0 report is NOT a failure: the surface was
        # measured and simply not exercised (0.0%). Failing on covered == 0
        # would install a hidden >0% floor, which R4 (measure before gating)
        # forbids.
        print(
            f"error: kcov measured zero shipped-shell lines "
            f"(covered={covered} total={total}). Coverage plumbing is broken, "
            f"not merely unexercised code.",
            file=sys.stderr,
        )
        # Diagnostic: show what filenames the report DID contain, so a zero
        # result is debuggable without local kcov.
        try:
            seen = sorted(
                {cls.get("filename", "") for cls in ET.parse(path).iter("class")}
            )
        except (OSError, ET.ParseError):
            seen = []
        print(f"diagnostic: {len(seen)} class filename(s) in report", file=sys.stderr)
        for name in seen[:40]:
            print(f"diagnostic:   {name}", file=sys.stderr)
        return 2
    pct = 100.0 * covered / total
    print(f"{covered} {total} {pct:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
