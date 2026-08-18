#!/usr/bin/env python3
"""Enforce the single pack-helper resolution rule in authored payloads.

A shipped skill reaches a pack helper only through the toolchain, and locates
the toolchain with the canonical bootstrap recorded in
``templates/.agents/skills/sd-help/references/pack-helper-resolution.md``.

The rule exists because ``bash scripts/sd-ai-command-pack-toolchain.sh`` is
working-directory-relative and nothing resolves it: a thin consumer has no
``scripts/`` directory, so the invocation fails before the toolchain's own
resolver is ever reached.

Scanned trees are enumerated from the filesystem, not from a fixed list, so a
skill or reference document added later is covered without editing this gate.
Only authored trees are scanned; the generated copies under
``templates/{.commands,.claude,.gemini,.github}`` and the repository's own
``.agents/skills``/``.claude/skills`` are refreshed by ``make generate`` and
``make sync``, and scanning them would report every defect twice and fail a
tree whose only repair is regeneration.
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Iterable, NamedTuple

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

REFERENCE = pathlib.Path(
    "templates/.agents/skills/sd-help/references/pack-helper-resolution.md"
)

AUTHORED_TREES: tuple[tuple[str, str], ...] = (
    ("templates/.agents/skills", "*.md"),
    ("templates/docs", "SD_AI_COMMAND_PACK.md"),
    (".github/command-sources", "*.md"),
)

HELPER = r"sd-ai-command-pack-[A-Za-z0-9_-]+\.(?:mjs|py|sh)"
TOOLCHAIN_HELPER = "sd-ai-command-pack-toolchain.sh"
HELPER_RE = re.compile(HELPER)
SCRIPTS_PREFIXED_RE = re.compile(r"scripts/" + HELPER)
# `^\s*`, not `^`: a fenced block nested under a list item carries the list's
# indentation on every line, and so does any command inside an `if` or a loop.
# Anchoring at column zero made the whole rule inapplicable to exactly those
# blocks -- the ones long enough to need the structure.
DIRECT_INVOKE_RE = re.compile(r"(?:^\s*|[|&;(]\s*|\$\(\s*)(node|python3|bash)\s+(?:-{1,2}[\w-]+(?:=\S+)?\s+)*(?:scripts/)?(" + HELPER + r")")
RUN_INTERPRETER_RE = re.compile(r"\brun(?:-python)?\s+--\s+(node|python3|bash)\b")

EXEC_INFO_STRINGS = frozenset({"bash", "sh", "shell", ""})
EXEMPT_MARKER = "pack-helper-resolution: exempt"
EXEMPT_LOOKBACK = 4
REASON_NOISE_RE = re.compile(r"(?:-->|^[\s\-:]+|[\s]+)")

FENCE_RE = re.compile(r"^(\s*)```(\S*)\s*$")
CLOSING_FENCE_RE = re.compile(r"^\s*```\s*$")


class Finding(NamedTuple):
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.detail}"


class Block(NamedTuple):
    info: str
    indent: str
    start: int  # 1-indexed line of the opening fence
    body: list[str]
    exempt_reason: str | None


def read_canonical_bootstrap() -> list[str]:
    """The bootstrap is defined once, in the reference file skills cite."""
    text = (REPO_ROOT / REFERENCE).read_text(encoding="utf-8")
    for block in iter_blocks(text):
        if block.info == "bash" and any(
            line.startswith("SD_PACK_TOOLCHAIN=") for line in block.body
        ):
            return list(block.body)
    raise SystemExit(
        f"error: no canonical bootstrap block found in {REFERENCE}"
    )


def iter_blocks(text: str) -> Iterable[Block]:
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        match = FENCE_RE.match(lines[i])
        if not match:
            i += 1
            continue
        indent, info = match.group(1), match.group(2)
        reason = None
        for k in range(max(0, i - EXEMPT_LOOKBACK), i):
            if EXEMPT_MARKER in lines[k]:
                tail = lines[k].split(EXEMPT_MARKER, 1)[1]
                if k + 1 < len(lines):
                    # The reason may wrap onto the comment's second line.
                    tail += " " + lines[k + 1]
                reason = REASON_NOISE_RE.sub(" ", tail).strip()
        body: list[str] = []
        j = i + 1
        while j < len(lines) and not CLOSING_FENCE_RE.match(lines[j]):
            body.append(lines[j])
            j += 1
        yield Block(info, indent, i + 1, body, reason)
        i = j + 1


def logical_lines(body: list[str]) -> Iterable[tuple[int, str]]:
    """Join backslash continuations so an operand on its own line is seen."""
    joined: list[tuple[int, str]] = []
    buf = ""
    start = 0
    for offset, raw in enumerate(body):
        if not buf:
            start = offset
        stripped = raw.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        joined.append((start, buf + raw))
        buf = ""
    if buf:
        joined.append((start, buf))
    return joined


def check_file(path: pathlib.Path, bootstrap: list[str]) -> list[Finding]:
    rel = str(path.relative_to(REPO_ROOT))
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8")
    for block in iter_blocks(text):
        if block.info not in EXEC_INFO_STRINGS:
            continue
        # A block earns inspection by naming a helper *or* by using the
        # variable the bootstrap defines. Requiring the helper name alone made
        # the missing-bootstrap check unreachable for a block that only runs
        # toolchain subcommands -- `bash "$SD_PACK_TOOLCHAIN" doctor`, or
        # `run -- gh ...` -- which is exactly a block whose variable nothing
        # else sets.
        if not any(
            HELPER_RE.search(line) or "$SD_PACK_TOOLCHAIN" in line
            for line in block.body
        ):
            continue
        if block.exempt_reason:
            continue
        stripped = [
            line[len(block.indent):] if line.startswith(block.indent) else line
            for line in block.body
        ]
        bootstrap_lines: set[int] = set()
        has_bootstrap = False
        for offset in range(len(stripped) - len(bootstrap) + 1):
            if stripped[offset:offset + len(bootstrap)] == bootstrap:
                has_bootstrap = True
                bootstrap_lines.update(
                    range(offset, offset + len(bootstrap))
                )
        for offset, raw in enumerate(block.body):
            if offset in bootstrap_lines:
                continue
            line_no = block.start + 1 + offset
            if SCRIPTS_PREFIXED_RE.search(raw):
                findings.append(Finding(
                    rel, line_no, "scripts-prefix",
                    "a scripts/-prefixed pack helper in an executable block; "
                    "resolve through the toolchain and drop the prefix",
                ))
        for offset, logical in logical_lines(block.body):
            if offset in bootstrap_lines:
                continue
            line_no = block.start + 1 + offset
            direct = DIRECT_INVOKE_RE.search(logical)
            if direct and "$SD_PACK_TOOLCHAIN" not in direct.group(0):
                # The toolchain cannot resolve itself: `run --` is one of its
                # own subcommands, so the ordinary remedy would be circular
                # advice. Its remedy is the bootstrap, which is what locates
                # the toolchain in the first place.
                remedy = (
                    f"run the bootstrap from {REFERENCE} and invoke "
                    'bash "$SD_PACK_TOOLCHAIN" <subcommand>'
                    if direct.group(2) == TOOLCHAIN_HELPER
                    else 'use bash "$SD_PACK_TOOLCHAIN" run[-python] -- <helper>'
                )
                findings.append(Finding(
                    rel, line_no, "direct-invocation",
                    f"{direct.group(1)} invokes {direct.group(2)} directly; "
                    f"{remedy}",
                ))
            interpreter = RUN_INTERPRETER_RE.search(logical)
            if interpreter and HELPER_RE.search(logical):
                findings.append(Finding(
                    rel, line_no, "run-interpreter",
                    f"run -- names the interpreter {interpreter.group(1)}; "
                    "run resolves only its first operand, so the helper "
                    "argument is left unresolved",
                ))
        uses = [
            offset
            for offset, line in enumerate(block.body)
            if offset not in bootstrap_lines and "$SD_PACK_TOOLCHAIN" in line
        ]
        if uses and not has_bootstrap:
            findings.append(Finding(
                rel, block.start, "missing-bootstrap",
                'the block uses "$SD_PACK_TOOLCHAIN" without a byte-identical '
                f"copy of the bootstrap from {REFERENCE}; each fenced block "
                "runs in its own shell",
            ))
        # Present is not the same as reached: a use above the bootstrap runs
        # with the variable still empty, which is the failure the bootstrap
        # exists to prevent, in a block the presence check calls clean.
        elif uses and bootstrap_lines and uses[0] < min(bootstrap_lines):
            findings.append(Finding(
                rel, block.start + 1 + uses[0], "bootstrap-after-use",
                'the block uses "$SD_PACK_TOOLCHAIN" before the bootstrap '
                "sets it; move the bootstrap above its first use",
            ))
    return findings


def main(argv: list[str]) -> int:
    bootstrap = read_canonical_bootstrap()
    findings: list[Finding] = []
    scanned = 0
    for tree, glob in AUTHORED_TREES:
        root = REPO_ROOT / tree
        if not root.exists():
            print(f"error: authored tree missing: {tree}", file=sys.stderr)
            return 2
        for path in sorted(root.rglob(glob)):
            scanned += 1
            findings.extend(check_file(path, bootstrap))
    if findings:
        print(
            f"error: {len(findings)} pack-helper resolution violation(s) "
            f"across {scanned} authored file(s):",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            f"\nThe rule and the canonical bootstrap live in {REFERENCE}.",
            file=sys.stderr,
        )
        return 1
    print(
        f"pack-helper resolution: {scanned} authored file(s) clean "
        f"({len(bootstrap)}-line bootstrap from {REFERENCE})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
