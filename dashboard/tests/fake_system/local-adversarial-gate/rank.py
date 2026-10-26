"""A fake of the system checkout's `rank.py` for the dashboard's tests (sd:6044): `finding_blocks` alone.

A finding is an ATX heading's block that holds a confidence tag; the level with the most of them wins, the shallower
on a tie. Headings inside a fence are text.
"""

import re

CONFIDENCE = re.compile(r"\b(CERTAIN|LIKELY|SPECULATIVE)\b")
HEADING = re.compile(r"^(#{1,6})\s+\S")
FENCE = re.compile(r"^\s*(```|~~~)")


def finding_blocks(lines):
    heads, fenced = [], False
    for number, line in enumerate(lines):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (found := HEADING.match(line)):
            heads.append((len(found[1]), number))
    tagged: dict[int, list[tuple[int, int]]] = {}
    for n, (level, start) in enumerate(heads):
        end = next((other for deeper, other in heads[n + 1:] if deeper <= level), len(lines))
        if CONFIDENCE.search("\n".join(lines[start:end])):
            tagged.setdefault(level, []).append((start, end))
    return tagged[min(tagged, key=lambda level: (-len(tagged[level]), level))] if tagged else []
