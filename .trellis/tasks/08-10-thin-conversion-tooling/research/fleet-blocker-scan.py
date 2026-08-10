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
from installer.manifest import load_manifest  # noqa: E402
from installer.provenance import PROVENANCE_FILE  # noqa: E402
from installer.registry import (  # noqa: E402
    COPILOT_GUIDANCE_START,
    COPILOT_INSTRUCTIONS_TARGET,
    FORCE_PRESERVED_TARGETS,
    INSTALLED_TARGETS_FILE,
    PACK_MANIFEST_FILE,
    TRELLIS_GITIGNORE_START,
    TRELLIS_GITIGNORE_TARGET,
)

# R8-2. `plan.block_strip` names *files*; the conversion removes one exact
# marker pair per file (installer/removal.py:337). Treating every pack-labelled
# block in a listed file as stripped is wrong for a file that carries more than
# one -- measured: every consumer's `.gitignore` has both `trellis-gitignore`
# and `obsidian-kb`, and only the first is removed. The mapping is derived from
# the same constants removal uses, so the two cannot drift apart.
STRIPPED_BLOCK_LABEL = {
    TRELLIS_GITIGNORE_TARGET.as_posix(): TRELLIS_GITIGNORE_START,
    COPILOT_INSTRUCTIONS_TARGET.as_posix(): COPILOT_GUIDANCE_START,
}

# R8-4. `docs/review-learnings.md` is the pack's own generated ledger of past
# review comments (templates/scripts/sd-ai-command-pack-review-learnings.py:42,
# registry.py:1589). It quotes reviewers verbatim, so it contains
# command-shaped prose -- "the runnable command is `python3 scripts/....py`" --
# that is a record of something said, never an instruction. Same category as
# .trellis/audit/, derived from the pack constant rather than guessed.
HISTORICAL_NAMES = frozenset({"docs/review-learnings.md"})

# H-4, round 7. The three generated bookkeeping files describe the install
# itself: `manifest.json` alone names every shipped target, so a conversion
# that removes 179 of them produces 1055 "citations" per consumer -- 93% of
# every advisory list, all of it noise. The design already said generated
# bookkeeping is not a source of citations; this implements that. They are
# `scheduled` rather than skipped, because the conversion does rewrite them.
GENERATED_BOOKKEEPING = frozenset(
    {
        INSTALLED_TARGETS_FILE.as_posix(),
        PACK_MANIFEST_FILE.as_posix(),
        PROVENANCE_FILE.as_posix(),
    }
)

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

# U-1, generalized. Enumerating every file type that can execute did not
# converge: rounds 4, 5, and 6 each found a class the previous enumeration
# missed (nested scripts/, agent prompts, root CLAUDE.md, PR templates). The
# space of ways a *command* is written is far smaller and far more stable than
# the space of files that might run one, so a citation appearing in command
# position blocks regardless of what file it sits in. This only ever adds
# blockers; it never moves one to advisory.
# H-3, round 7. An interpreter word alone is not command position. `\bpython3?\s`
# under IGNORECASE matches the English word "Python" -- measured:
# rwbp-website/.gitignore:165, the comment "Python bytecode from scripts/*.py",
# was recorded as a blocker. The interpreter must be case-sensitive and must be
# followed by something that looks like a path, which is what an invocation
# actually is. "make sure" and "the node is" stop matching; "python3 scripts/x.py"
# and "make -f scripts/x.mk" still do. A flagged invocation whose argument is not
# path-shaped ("make -C build") does not match, and does not need to: it names no
# path this scan is looking for.
RUNNER = (
    r"(?:(?:ba|z|d)?sh|python3?|node|npx?|pnpm|yarn|deno|ruby|perl|exec|source"
    r"|make|uvx|uv\s+run|go\s+run)"
)

COMMAND_CONTEXT = re.compile(
    rf"""(
        (?-i:\b{RUNNER}\s+(?:-{{1,2}}[\w-]+\s+)*[-\w.$~"'`/]*[./][-\w.$~"'`/]*)
      | \brun:\s | ^\s*run\s*[:=] | \bcommand\s*[:=] | \bentrypoint\s*[:=]
        # Command substitution, but not arithmetic expansion: "$((delay * 2))"
        # quoted inside a review-feedback ledger is not an invocation.
      | \$\(\s*[\w./-]+\s
        # Checklist item a human works through, but only when the line also
        # names something runnable. Every Trellis PRD states its acceptance
        # criteria as checklist items, so an unqualified checklist rule blocks
        # on prose like "a refresh that modifies `docs/SD_AI_COMMAND_PACK.md`".
      | ^\s*[-*]?\s*\[[ x]\](?=.*\.(?:sh|bash|zsh|py|mjs|cjs|js|ts|rb|pl)\b)
      | \w+_(?:script|cmd|command|bin|path)\s*= # shell/py assignment of a runnable
      | \brun\b.{{0,24}}\b(?:script|command)\b
        # Imperative guidance naming a runnable file. Live agent guidance under
        # .trellis/spec/** causes execution without ever writing an interpreter:
        # "Use `scripts/sd-ai-command-pack-full-check.sh` as the local review
        # gate" is an instruction, and the agent supplies the interpreter.
      | \b(?:use|run|invoke|execute|call|launch)\b[^\n]{{0,48}}
        \.(?:sh|bash|zsh|py|mjs|cjs|js|rb|pl)\b
    )""",
    re.VERBOSE | re.IGNORECASE,
)

# Historical records. A Trellis task artifact, journal, or dated audit report
# quotes commands that were run at the time; it is a record of the past, not an
# instruction for the future, and nothing re-executes it. Blocking a conversion
# because an archived 2026-07 implement.md quotes a command is the same failure
# as blocking on docs/SD_AI_COMMAND_PACK.md -- measured: the unscoped rule put
# 28 of sd-github-review's 34 blockers in .trellis/tasks/archive/**. Live
# guidance under .trellis/spec/** is deliberately NOT here: an agent reads a
# spec and acts on it.
HISTORICAL_PREFIXES = (
    ".trellis/tasks/archive/",
    ".trellis/workspace/",
    ".trellis/audit/",
    ".trellis/journal/",
)

# H-2, round 7. Scoping out all of `.trellis/tasks/` was too broad: an
# *unarchived* task's implement.md is a live instruction a developer or agent
# is expected to follow, in exactly the sense that made the PR-template
# checklist blocking. Only `archive/` is a record of what was already run.

# Explicit tags only. A bare ``` can be either half of a pair, and real files
# nest fences (a generated repository map quotes Markdown that itself contains
# fences), so tracking parity across a whole file desynchronises and then labels
# ordinary prose as command context. Treating an untagged fence as *always
# closing* is the fail-safe direction: it can only lose a fence-derived blocker
# that the line's own syntax or a continuation would usually catch anyway.
RUNNABLE_FENCE_LANGS = frozenset(
    {"bash", "sh", "shell", "console", "zsh", "shell-session", "make", "python"}
)

FENCE = re.compile(r"^\s*(?:```+|~~~+)\s*([\w-]*)")


def command_lines(lines: list[str]) -> set[int]:
    r"""Line numbers that are in command position for a reason the line itself
    does not carry.

    Two cases, both found in real consumers and both previously advisory:

    - Inside a fenced block whose language is runnable. `docs/repomix-map.md`
      and task `implement.md` files put bare invocations in ```bash fences; the
      fence *is* the command context.
    - A shell continuation. `bash toolchain.sh run-python -- \` followed by the
      script path on the next line puts the removed path on a line with no
      command token of its own, which is how the fleet writes nearly every
      long invocation.
    """
    marked: set[int] = set()
    fenced = False
    runnable = False
    continued = False
    for number, line in enumerate(lines, start=1):
        match = FENCE.match(line)
        if match:
            if fenced:
                fenced = runnable = False
            elif match.group(1).lower() in RUNNABLE_FENCE_LANGS:
                fenced = runnable = True
            continued = False
            continue
        if fenced and runnable:
            marked.add(number)
        elif continued:
            marked.add(number)
        stripped = line.rstrip()
        continued = bool(stripped) and stripped.endswith("\\") and (
            (fenced and runnable) or continued or bool(COMMAND_CONTEXT.search(line))
        )
    return marked

# Managed-block delimiters. A citation inside a block the conversion strips is
# scheduled; the same citation outside it is judged normally.
BLOCK_START = re.compile(
    r"(?:SD-AI-COMMAND-PACK:([A-Z-]+):START|# sd-ai-command-pack ([a-z-]+) start)"
)
BLOCK_END = re.compile(
    r"(?:SD-AI-COMMAND-PACK:([A-Z-]+):END|# sd-ai-command-pack ([a-z-]+) end)"
)


def marker_label(match: re.Match[str]) -> str:
    """Which block this marker belongs to.

    One file legitimately carries several *distinct* pack blocks -- measured:
    rwbp-website/.gitignore has `trellis-gitignore` and `obsidian-kb`. What the
    installer rejects (installer/fileops.py:150) is a repeat of the *same*
    marker, which it looks for by exact string. Duplicate detection must key on
    the label, not on "a second block appeared".
    """
    return next(group for group in match.groups() if group is not None).lower()

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


def receipt_occupancy_digest(repo: Path, entries) -> str:
    """Digest over what the *receipt's* targets actually are on disk.

    `head`, `indexDigest`, and `worktreeDigest` all describe Git's view, and a
    gitignored file is in none of them. The conversion plan does not share that
    blind spot: `occupied_receipt_targets()` (installer/conversion.py:249) tests
    filesystem existence, and design.md:190 records that installed adapters can
    be gitignored. An adapter appearing or disappearing would otherwise change
    the plan while every recorded binding stayed identical.
    """
    digest = hashlib.sha256()
    for target in sorted(entries):
        digest.update(target.encode("utf-8"))
        full = repo / target
        try:
            if full.is_symlink():
                digest.update(b"\0symlink:" + os.readlink(full).encode("utf-8"))
            elif full.is_file():
                digest.update(b"\0file:")
                digest.update(hashlib.sha256(full.read_bytes()).digest())
            elif full.is_dir():
                digest.update(b"\0dir")
            else:
                digest.update(b"\0absent")
        except OSError:
            digest.update(b"\0unreadable")
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def executable_bits_digest(repo: Path, tracked: list[str]) -> str:
    """Digest over the filesystem executable bit of every tracked file.

    R8-3: `is_executable_surface()` consults `os.access(X_OK)`, which is
    filesystem state. `indexDigest` records Git's mode, and with
    `core.fileMode=false` the two can disagree -- chmod +x on a tracked Markdown
    file moves it onto the execution surface while `head`, `indexDigest`,
    `worktreeDigest`, `worktreeClean`, and `receiptOccupancyDigest` all stay
    identical. A classification input that nothing records is a verdict that can
    go stale in silence.
    """
    digest = hashlib.sha256()
    for relative in tracked:
        full = repo / relative
        try:
            bit = b"1" if os.access(full, os.X_OK) and full.is_file() else b"0"
        except OSError:
            bit = b"?"
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0" + bit + b"\0")
    return f"sha256:{digest.hexdigest()}"


def worktree_digest(repo: Path) -> str:
    """Digest over the dirty *contents*, not over `git status` output.

    Hashing the porcelain status hashes the set of dirty paths; two different
    edits to the same file produce the same value, so a dirty tree stayed
    unidentifiable exactly where identification mattered. Six of the eight
    consumer trees are dirty, so this is the common case here, not the corner.

    ``-uall`` matters as much as the content hashing: the default collapses an
    untracked directory to a single ``dir/`` record, so every file inside it
    would be invisible to the digest. Rename records carry a second path field,
    which is consumed rather than misread as the next record's status.
    """
    digest = hashlib.sha256()
    fields = iter(
        field
        for field in git(repo, "status", "--porcelain=v1", "-z", "-uall").split("\0")
        if field
    )
    for record in fields:
        status, relative = record[:2], record[3:] if len(record) > 3 else ""
        digest.update(record[:3].encode("utf-8"))
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if status[0] in "RC" or status[1] in "RC":
            digest.update(next(fields, "").encode("utf-8"))
            digest.update(b"\0")
        full = repo / relative
        try:
            if full.is_symlink():
                digest.update(b"symlink:" + os.readlink(full).encode("utf-8"))
            elif full.is_file():
                digest.update(hashlib.sha256(full.read_bytes()).digest())
            else:
                digest.update(b"absent")
        except OSError:
            digest.update(b"unreadable")
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


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
    """Every string worth searching for when looking for a removed path.

    Discovery only. Matching is decided by ``cites_removed_path``, which is
    stricter: a form here merely makes a line a candidate.

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


def unambiguous_basenames(
    removed: frozenset[str], survivors: frozenset[str]
) -> frozenset[str]:
    """Basenames that can only mean one removed path.

    Round 5 matched any bare basename against the removal set and produced real
    false blockers, because the removal set contains names like SKILL.md and
    config.toml that surviving files also carry. Round 6 removed basename
    matching entirely, which lost the citations that never spell a path --
    os.path.join("scripts", "x.sh"), a Windows separator, a name passed as an
    argument. A basename owned by exactly one removed path and by nothing that
    survives carries no ambiguity to lose.
    """
    counts: dict[str, int] = {}
    for entry in removed:
        name = entry.rsplit("/", 1)[-1]
        counts[name] = counts.get(name, 0) + 1
    surviving = {entry.rsplit("/", 1)[-1] for entry in survivors}
    return frozenset(
        name for name, count in counts.items() if count == 1 and name not in surviving
    )


def cites_removed_path(
    token: str,
    removed: frozenset[str],
    repo: Path,
    relative_to: str,
    survivors: frozenset[str],
    unambiguous: frozenset[str],
) -> bool:
    """Does this token name something the conversion removes?

    Four ways, and deliberately not a fifth:

    1. the token is a removed path;
    2. a tail of the token is, at a path boundary -- this is what handles a
       runtime prefix, e.g. mezmo_benchmark's preflight-pr.sh assigning
       "$repo_root/scripts/sd-ai-command-pack-review-learnings.py", which
       tokenizes to repo_root/scripts/... and matches nothing exactly;
    3. it resolves, relative to the citing file's own directory, to a removed
       path;
    4. it is a glob whose whole matched population is removed.

    The qualifier on (4) is not a detail. hoa-manager's scripts/update_repomix
    passes INCLUDE_PATTERNS="...,docs/**,.trellis/spec/**,..."; those globs match
    removed files *and* surviving ones, so the script keeps working and needs no
    repoint. A glob is only broken when nothing it selects survives.

    5. it is a bare basename that belongs to exactly one removed path and to
       no surviving file. This is the narrow, checked form of the matching that
       round 5 removed wholesale. It recovers the citations a static reader
       cannot resolve otherwise -- a Windows-separator path, an
       os.path.join("scripts", "x.sh") -- without the ambiguity that made the
       wholesale version wrong: a name shared with anything that survives, or
       with a second removed path, is not evidence about either.

    What is deliberately absent is bare-suffix guessing: associating a short
    relative reference with any removed path that happens to end the same way.
    That produced real false blockers -- se-ai-command-pack's se-help SKILL.md
    says "Read `references/examples.md`", which collided with the removed
    .agents/skills/sd-help/references/examples.md while naming its own sibling.
    A reference that resolves nowhere is a broken reference, not evidence about
    a path elsewhere in the tree, and a false blocker refuses a conversion that
    should proceed.

    Still a lower bound: a path assembled from a variable whose value is set
    elsewhere remains invisible. --revert-thin, not this check, is what makes
    the conversion safe.
    """
    # R8-1: a removed path at the end of a sentence keeps its period, and the
    # token pattern deliberately includes "." so extensions survive. Measured in
    # all 8 consumers: `.gitignore` carries "# Generated by
    # scripts/sd-ai-command-pack-update-spec-kb.py. DO NOT EDIT MANUALLY." and
    # the citation landed in no bucket at all. Stripping is trailing-only so
    # "./scripts/x.sh" keeps its leading "./".
    token = token.strip("'\"`,;:()[]{}<>").rstrip(".")
    if not token:
        return False
    if "*" in token or "?" in token:
        if not any(fnmatch.fnmatch(entry, token) for entry in removed):
            return False
        return not any(fnmatch.fnmatch(entry, token) for entry in survivors)
    if token in removed:
        return True
    parts = token.split("/")
    if any("/".join(parts[index:]) in removed for index in range(1, len(parts))):
        return True
    parent = str(Path(relative_to).parent)
    resolved = os.path.normpath(token if parent == "." else f"{parent}/{token}")
    if resolved in removed:
        return True
    return "/" not in token and token in unambiguous


def block_spans(lines: list[str]) -> list[tuple[int, int]] | None:
    """Marker spans, or None when the markers are malformed.

    None means "cannot determine ownership", which fails closed to a pack
    defect rather than silently claiming a span. installer/fileops.py:138
    rejects incomplete and duplicate markers; treating an unterminated start as
    a block running to EOF -- the earlier behaviour -- would label consumer tail
    content as pack-owned, which is the opposite of failing closed.
    """
    spans: list[tuple[int, int]] = []
    seen: set[str] = set()
    open_label: str | None = None
    start: int | None = None
    for number, line in enumerate(lines, start=1):
        opening = BLOCK_START.search(line)
        closing = None if opening else BLOCK_END.search(line)
        if opening:
            label = marker_label(opening)
            # A repeat of the same label is a duplicate even when the first pair
            # closed cleanly: installer/fileops.py:150 rejects any repeat of
            # either marker, so accepting it would let the resweep vouch an
            # ownership shape the conversion itself refuses to parse.
            if start is not None or label in seen:
                return None
            seen.add(label)
            open_label = label
            start = number
        elif closing:
            if start is None or marker_label(closing) != open_label:
                return None
            spans.append((start, number))
            start = None
            open_label = None
    if start is not None:
        return None
    return spans


def stripped_spans(
    relative: str,
    lines: list[str],
    all_spans: list[tuple[int, int]] | None,
) -> list[tuple[int, int]]:
    """Only the span the conversion actually removes, not every pack block.

    A file can carry several pack blocks with different labels; the conversion
    removes exactly one marker pair per file. A hit inside a block that survives
    is not `scheduled` -- it is pack content citing a removed path, which is a
    pack defect.
    """
    marker = STRIPPED_BLOCK_LABEL.get(relative)
    if marker is None or not all_spans:
        return []
    return [span for span in all_spans if marker in lines[span[0] - 1]]


def shipped_template_digests() -> dict[str, str]:
    """Digest of the pack's own shipped bytes, per force-preserved target.

    Provenance never vouches a force-preserved target, and the earlier rule
    concluded from that alone that the file was the consumer's. It is not, when
    the bytes are still the pack's: .github/PULL_REQUEST_TEMPLATE.md is
    force-preserved (installer/registry.py:2265), its shipped template cites the
    removed full-check script, and rwbp-coordinator and loadsmith carry
    byte-identical copies. Comparing against the shipped source recovers the
    ownership that provenance deliberately declines to record.
    """
    _, files = load_manifest()
    forced = {path.as_posix() for path in FORCE_PRESERVED_TARGETS}
    digests: dict[str, str] = {}
    for file in files:
        target = file.target.as_posix()
        if target not in forced or file.source is None:
            continue
        digest = file_digest(file.source)
        if digest is not None:
            digests[target] = digest
    return digests


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
    stripped = frozenset(plan.block_strip)
    managed = frozenset(receipt.entries)
    recorded = provenance_digests(repo)
    shipped = shipped_template_digests()
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
    survivors = frozenset(tracked) - removed
    binary: list[str] = []
    missing: list[str] = []
    unambiguous = unambiguous_basenames(removed, survivors)
    for relative in tracked:
        if relative in removed:
            buckets["scheduled"].append({"file": relative, "line": None})
            continue
        if relative in GENERATED_BOOKKEEPING:
            buckets["scheduled"].append(
                {"file": relative, "line": None, "detail": "generated bookkeeping"}
            )
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
            # A symlink is a citation in its most executable form: following it
            # *is* the reference. No consumer has a tracked symlink today, so
            # this classifies an empty class -- which is the point, since
            # "measured zero" and "never looked" are different claims.
            try:
                link = os.readlink(full)
            except OSError:
                continue
            parent = str(Path(relative).parent)
            resolved = os.path.normpath(
                link if parent == "." or link.startswith("/") else f"{parent}/{link}"
            )
            if resolved in removed or link in removed:
                buckets["blockers"].append(
                    {
                        "file": relative,
                        "line": None,
                        "detail": f"symlink to removed path: {link}",
                    }
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
            elif full.is_file():
                # Present and not UTF-8: a binary asset, which cannot carry a
                # citation a static reader could see. Recorded, not silent.
                binary.append(relative)
            else:
                # Tracked and absent. A sparse checkout or a skip-worktree entry
                # looks identical to a complete tree in `git ls-files -s`, so
                # this is the difference between "measured zero" and "did not
                # look", and it invalidates the scan rather than reducing it.
                missing.append(relative)
            continue
        lines = body.splitlines()
        if not needles.search(body):
            continue

        all_spans = block_spans(lines)
        malformed_markers = all_spans is None
        spans = stripped_spans(relative, lines, all_spans) if relative in stripped else []
        vouched = recorded.get(relative)
        actual = file_digest(full)
        pack_owned = relative in managed and vouched is not None and vouched == actual
        # Provenance never vouches a managed-block, force-preserved, or generated
        # target, so a missing digest proves nothing about ownership. Managed
        # blocks are resolved by their markers; force-preserved targets are
        # resolved against the pack's own shipped bytes; malformed markers are
        # unresolvable and fail closed to pack-owned.
        if relative in managed and vouched is None:
            pack_owned = pack_owned or (
                relative in shipped and shipped[relative] == actual
            )
        unvouchable = relative in managed and vouched is None
        executable = is_executable_surface(repo, relative)
        historical = (
            relative.startswith(HISTORICAL_PREFIXES) or relative in HISTORICAL_NAMES
        )
        commanded = command_lines(lines)

        for number, line in enumerate(lines, start=1):
            if not needles.search(line):
                continue
            if not any(
                cites_removed_path(
                    token, removed, repo, relative, survivors, unambiguous
                )
                for token in TOKEN.findall(line)
            ):
                continue
            entry = {"file": relative, "line": number, "detail": line.strip()[:160]}
            in_block = any(start <= number <= end for start, end in spans)
            in_pack_block = bool(all_spans) and any(
                start <= number <= end for start, end in (all_spans or [])
            )
            if in_block:
                # The block itself is stripped, so this reference leaves with it.
                buckets["scheduled"].append(entry)
            elif pack_owned or (unvouchable and (in_pack_block or malformed_markers)):
                # Kept, still the pack's own content, and it names something that
                # disappears: the pack ships a broken reference. A pack defect,
                # not a consumer verdict, and it blocks until a release fixes it.
                if malformed_markers and not in_pack_block:
                    entry = {**entry, "detail": f"[malformed markers] {entry['detail']}"}
                buckets["packDefects"].append(entry)
            elif executable or (
                not historical
                and (COMMAND_CONTEXT.search(line) or number in commanded)
            ):
                buckets["blockers"].append(entry)
            else:
                buckets["advisories"].append(entry)

    index = git(repo, "ls-files", "-s")
    return {
        "consumer": name,
        "repo": str(repo),
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "indexDigest": digest_of(index),
        "worktreeDigest": worktree_digest(repo),
        "worktreeClean": not git(repo, "status", "--porcelain").strip(),
        "receiptOccupancyDigest": receipt_occupancy_digest(repo, receipt.entries),
        "executableBitsDigest": executable_bits_digest(repo, tracked),
        "binaryTrackedFiles": len(binary),
        "missingTrackedFiles": sorted(missing),
        "receiptEntries": len(receipt.entries),
        "removedTargets": len(removed),
        "trackedFiles": len(tracked),
        "counts": {key: len(value) for key, value in buckets.items()},
        "blockerFiles": sorted({entry["file"] for entry in buckets["blockers"]}),
        "packDefectFiles": sorted({entry["file"] for entry in buckets["packDefects"]}),
        "verdict": (
            # A tracked file the scan could not read is not a file it cleared.
            # An incomplete tree fails closed, like every other input the rule
            # cannot resolve.
            "clear"
            if not buckets["blockers"] and not buckets["packDefects"] and not missing
            else "blocked"
        ),
        **buckets,
    }


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
        "packWorktreeDigest": worktree_digest(ROOT),
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
