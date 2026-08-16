#!/usr/bin/env python3
"""Decide whether one consumer can be converted to a thin install.

Source-checkout tooling, like every other ``fleet-*`` helper: no
``manifest.json`` row and no ``templates/scripts/`` twin. A resweep running
inside a consumer would have no classification data at all --
``docs/fleet/surface-partition.json`` is not shipped -- so a row for this file
would be a defect, not an oversight.

The rule lives in ``installer/resweep.py``; this is the CLI over it. It adds
the three things a *verdict* needs that a *measurement* does not:

* ``classifierDigest``, binding every input that decides what a conversion
  does, so a verdict cannot outlive an edit to the rule that produced it;
* a clean-worktree requirement (``prd.md:62``), because converting a dirty tree
  mixes the conversion's deletions with the consumer's uncommitted work; and
* a ``clear``/``blocked`` decision that fails closed on unreadable files.

Run from an ``sd-ai-command-pack`` source checkout::

    .venv/bin/python scripts/sd-ai-command-pack-thin-resweep.py CONSUMER \\
        [--json] [--out PATH]

``CONSUMER`` is a registry name from ``docs/fleet/consumers.json``, or a path
to a checkout when ``--repo`` is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import difflib  # noqa: E402
import fnmatch  # noqa: E402
import hashlib  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402

from sd_ai_command_pack_lib import run_git_minimal  # noqa: E402

from installer import conversion, thin  # noqa: E402
from installer.manifest import load_manifest  # noqa: E402
from installer.provenance import PROVENANCE_FILE  # noqa: E402
from installer.registry import (  # noqa: E402
    COPILOT_GUIDANCE_START,
    COPILOT_INSTRUCTIONS_TARGET,
    FORCE_PRESERVED_TARGETS,
    INSTALLED_TARGETS_FILE,
    PACK_MANIFEST_FILE,
    PLATFORM_REGISTRY,
    TRELLIS_GITIGNORE_START,
    TRELLIS_GITIGNORE_TARGET,
)

PARTITION = ROOT / "docs/fleet/surface-partition.json"
REGISTRY = ROOT / "docs/fleet/consumers.json"

SCHEMA_VERSION = 1


# --------------------------------------------------------------------------
# The classification rule. Ported from
# `.trellis/tasks/08-10-thin-conversion-tooling/research/fleet-blocker-scan.py`,
# which stays in place as the reference implementation so the planning
# artifacts' counts can be re-derived against an independent copy. Kept in
# this file rather than under `installer/` for two reasons: `installer/` is
# the *installed* library and this never ships, and `classifier_digest`
# hashes this path -- which only binds the rule if the rule is here.
# --------------------------------------------------------------------------

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
# R11-C4, demonstrated. This list used to be written by hand, and a hand-written
# list of platform directories drifts from the registry that defines them. It
# named `.opencode/command/`; the registry's OpenCode surface is
# `.opencode/commands/` (registry.py:309), so the prefix matched nothing at all.
# Twelve further platform directories -- `.agent`, `.codebuddy`, `.cursor`,
# `.devin`, `.factory`, `.kilocode`, `.kiro`, `.pi`, `.qoder`, `.reasonix`,
# `.trae`, `.zcode` -- were absent outright. Every one of those holds commands,
# rules, or skills an agent executes. Deriving the set from `PLATFORM_REGISTRY`
# closes the class instead of fixing thirteen instances, and a platform added to
# the pack later is covered without anyone remembering this file.
#
# `.github` is excluded from the wholesale rule and kept as explicit
# sub-prefixes: it is the host's shared directory rather than one agent's, so
# `.github/ISSUE_TEMPLATE/` is not an execution surface the way
# `.github/workflows/` is.
PLATFORM_PREFIXES = tuple(
    sorted(
        f"{info.directory}/"
        for info in PLATFORM_REGISTRY.values()
        if info.directory != ".github"
    )
)
EXECUTABLE_PREFIXES = PLATFORM_PREFIXES + (
    ".github/workflows/",
    ".github/actions/",
    ".circleci/",
    ".devcontainer/",
    ".github/prompts/",
    ".github/instructions/",
    # R10-C6, demonstrated. `.prism/rules.json` is a list of *required review
    # rules* -- instructions a reviewing agent acts on, not inert config.
    # `rwbp-coordinator/.prism/rules.json:55` tells the reviewer that canonical
    # behaviour lives in `scripts/sd-ai-command-pack-full-check.sh`,
    # `scripts/sd-ai-command-pack-housekeeping.sh`, `docs/SD_AI_COMMAND_PACK.md`
    # and `.agents/skills/` -- three paths the conversion removes. The partition
    # keeps the file (`shared`/`consumer-config`), so conversion leaves the
    # broken rule in place. The text is not in the pack's shipped template, so
    # it is consumer-authored and belongs in that consumer's own cleanup.
    # `.prism` is not a platform directory, so it stays named here.
    ".prism/",
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
        # R9-C5: a command may take no argument -- "$(pwd)/scripts/x.sh" is an
        # invocation, and round 8's trailing \s excluded every such form while
        # its ledger claimed only arithmetic had been excluded.
      | \$\(\s*[\w./-]+\s*[\s)]
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


# R14-C4, executed: `./scripts/x.sh` is the canonical way to run a repository
# script and it names no runner word at all -- Codex piped exactly those bytes
# to bash and got them executed while the scanner filed the line as advisory.
#
# R15-C4 then demonstrated both halves of the boundary. Missed:
# `if ./scripts/x.sh; then :; fi` executes, and a bare separator rule does not
# see it, because what precedes the path is a shell keyword rather than a
# separator. Wrongly blocked: "After setup; ./scripts/x.sh is obsolete prose."
# is a sentence, and a bare separator rule calls it a command.
#
# So there are two forms, and the second is file-aware. A path at the start of a
# line -- optionally behind shell control words, `sudo`, `env`, or a variable
# assignment -- is an invocation in any file. A path after a mid-line separator
# is an invocation only where a sentence cannot be: not in prose. Prose is where
# the false positive lives and shell is where the true positive lives, and no
# regex can tell a sentence from a command without knowing which it is reading.
#
# R16-C4 corrected both halves again. Missed: `env -i ./scripts/x.sh` executes,
# and a prefix rule that demands the path *immediately* after the keyword does
# not see it -- real prefix commands take their own options. Wrongly blocked:
# valid JSON whose `"description"` value reads "After setup; ./scripts/x.sh is
# obsolete prose." is data, and the separator rule called it a command because
# `.json` is not a prose suffix. Suffix was standing in for two different
# questions -- "can a sentence live here?" and "does anything execute this?" --
# and structured data answers them differently from both prose and shell.
SHELL_WORD = r"(?:if|while|until|then|else|elif|do|time|command|exec|env|nohup|sudo|xargs|!)"
SHELL_PREFIX = (
    rf"(?:{SHELL_WORD}(?:\s+-{{1,2}}[\w-]+(?:[= ]\S+)?)*\s+|\w+=\S*\s+)*"
)
DIRECT_PATH = r"\.{1,2}/[-\w.$~/]*"
DIRECT_AT_START = re.compile(rf"^\s*{SHELL_PREFIX}{DIRECT_PATH}")
DIRECT_AFTER_SEPARATOR = re.compile(
    rf"(?:[;&|(]|&&|\|\|)\s*{SHELL_PREFIX}{DIRECT_PATH}"
)
PROSE_SUFFIXES = frozenset({".md", ".rst", ".txt", ".markdown"})
# Structured data. Nothing in these files executes because of where a string
# sits on a line; it executes because of the key it hangs from.
JSON_SUFFIXES = frozenset({".json"})
MAPPING_SUFFIXES = frozenset({".yaml", ".yml", ".toml", ".ini", ".cfg"})
MAPPING_BASENAMES = frozenset({"Procfile", "procfile"})
# Keys whose values a runner hands to a shell. `scripts` is the npm container:
# every string beneath it is a command regardless of its own key, which is why
# `"scripts": {"agent": "codex exec --help"}` runs under `npm run agent`.
EXEC_KEYS = frozenset(
    {
        "args", "build", "cmd", "command", "commands", "entrypoint", "exec",
        "postinstall", "poststart", "preinstall", "prestart", "run", "script",
        "scripts", "start", "test",
    }
)
MAPPING_EXEC_KEY = re.compile(r"^\s*(?:-\s+)?[\"']?([\w][\w.-]*)[\"']?\s*[:=]\s*\S")


def json_command_strings(body: str) -> set[str] | None:
    """Every string a JSON document hands to a runner, or None if it is not JSON.

    None means "ask the shell rules instead": an unparseable `.json` is not a
    document whose keys can be trusted, and failing to the text rules keeps a
    malformed file that a runner still reads from going quiet.
    """
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError):
        return None
    found: set[str] = set()

    def walk(node, executable: bool) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, executable or (isinstance(key, str) and key.lower() in EXEC_KEYS))
        elif isinstance(node, list):
            for item in node:
                walk(item, executable)
        elif isinstance(node, str) and executable and node.strip():
            found.add(node)

    walk(payload, False)
    return found


def structured_command_lines(lines: list[str], relative: str, body: str) -> set[int] | None:
    """Command-position lines in structured data, or None if this is not data.

    Returning a set means the file's execution surface is fully described by it:
    the caller must not also apply the line-start or separator rules, because in
    a data file those describe typography rather than execution.
    """
    path = Path(relative)
    suffix = path.suffix.lower()
    if suffix in JSON_SUFFIXES:
        strings = json_command_strings(body)
        if strings is None:
            return None
        # The *quoted* form, not the bare text: a `"description"` that quotes a
        # command in a sentence contains the command's characters and is not the
        # command. R16-C4's demonstration was exactly that collision.
        quoted = [json.dumps(value) for value in strings]
        return {
            number
            for number, line in enumerate(lines, start=1)
            if any(value in line for value in quoted)
        }
    if suffix in MAPPING_SUFFIXES or path.name in MAPPING_BASENAMES:
        # A Procfile is nothing but commands: every `name: value` line is a
        # process the runner starts, and the name is the consumer's choice, so
        # no key list can enumerate it. Elsewhere the key is what decides.
        every_key = path.name in MAPPING_BASENAMES
        hits = set()
        for number, line in enumerate(lines, start=1):
            match = MAPPING_EXEC_KEY.match(line)
            if match and (every_key or match.group(1).lower() in EXEC_KEYS):
                hits.add(number)
        return hits
    return None


def direct_path_lines(lines: list[str], relative: str, body: str | None = None) -> set[int]:
    """Line numbers carrying a direct `./path` invocation."""
    if body is None:
        body = "\n".join(lines)
    structured = structured_command_lines(lines, relative, body)
    if structured is not None:
        return {
            number
            for number in structured
            if re.search(DIRECT_PATH, lines[number - 1])
        }
    prose = Path(relative).suffix.lower() in PROSE_SUFFIXES
    hits = set()
    for number, line in enumerate(lines, start=1):
        if DIRECT_AT_START.search(line):
            hits.add(number)
        elif not prose and DIRECT_AFTER_SEPARATOR.search(line):
            hits.add(number)
    return hits


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

# `docs/FLEET_ROLLOUT.md:630` prescribes the consumer migration: stop naming a
# `scripts/sd-ai-command-pack-*` literal, and ask the surviving resolver where a
# pack script lives by passing that script's *name*. The name is a bare basename
# of a removed path, which is exactly what the bare-name rules of
# `cites_removed_path` block. Following the documented recipe produced a
# blocked verdict with no next step -- measured on `rwbp-coordinator` at
# 0.71.13, where the rewrite cleared 44 blockers and its own three resolver
# keys replaced them.
#
# A file that names the kept resolver has adopted the resolver contract, so a
# bare pack basename in it is a key rather than a path. Both bare-name rules
# have to yield, not only rule 5: a guard living in `scripts/` makes rule 3
# resolve the same key against its own directory and land on the removed path,
# which is how `rwbp-coordinator`'s `scripts/check-full.test.mjs` blocked while
# its sibling in `scripts/lib/` did not. Two further deliberate choices:
#
# * file-scoped, not line-scoped, because the key is normally a constant
#   declared away from the call site -- `const NAME = '<basename>'` on one line
#   and `--resolve` on another, which is the shape the resolver's own
#   `review-preflight.mjs` uses;
# * bare-name family only. Rules 1, 2, and 4 are untouched, and so is rule 3's
#   real job -- resolving a token that already contains a slash, such as
#   `lib/x.sh` cited from a subdirectory. Every path-shaped pack citation in the
#   same file therefore still blocks, which is precisely the half-migrated trap
#   `docs/FLEET_ROLLOUT.md:639` names -- adopting `--resolve` while still
#   naming the resolver under `scripts/`.
#
# The cost is the rest of the bare-name family inside such a file, which this
# check already describes as a distinctively-named-only lower bound;
# `--revert-thin`, not this rule, is what makes a conversion safe.
LAYOUT_RESOLVER_KEPT_TARGET = (
    ".sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py"
)

SKIP_DIRS = (".git/",)


def git(repo: Path, *args: str) -> str:
    """Read-only git, through the shared prompt-disabled runner.

    The research copy calls `subprocess.run` directly; a shipped script may
    not (`tests/test_git_invocation_boundary.py`), and the reason is not
    stylistic -- `run_git_minimal` is what guarantees `GIT_TERMINAL_PROMPT=0`,
    so a scan of a checkout whose remote wants credentials fails instead of
    blocking forever on a prompt nobody is watching.
    """
    completed = run_git_minimal(["-C", str(repo), *args])
    if completed.returncode != 0:
        raise SystemExit(
            f"error: git {' '.join(args)} failed in {repo}: "
            f"{(completed.stderr or '').strip()}"
        )
    return completed.stdout


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


# R9-2: there is deliberately no discovery prefilter here any more.
#
# Rounds 1-8 ran a `needle_pattern` regex over each file and each line before
# handing the line to `cites_removed_path`, on the theory that discovery could
# be cheap and broad while matching stayed strict. It was neither: the needle
# set was full removed paths, their >=2-segment suffixes, and only those
# basenames carrying the pack name, while the matcher independently accepts
# a glob whose whole population is removed and a bare unambiguous basename
# (rule 5, added in round 8). The two sets were never reconciled, so the
# matcher's last two rules were mostly unreachable.
#
# Measured against the committed round-8 scan: 512 lines across all 8
# consumers satisfy `cites_removed_path` and were skipped by the prefilter
# before it ever ran -- including `.github/copilot-instructions.md` citing
# `.agents/skills/sd-*/SKILL.md`, which is inside the pack's own managed block.
# A prefilter that hides pack defects is not an optimisation.
#
# Any substring gate has this failure mode, because a glob token shares no
# literal substring with the paths it selects. So the matcher now sees every
# line, and `cites_removed_path` is the only thing that decides.


def hidden_bytes_digest(repo: Path, index_flags: str) -> str:
    """Digest over the content of entries `git status` cannot see.

    `git ls-files -v` prefixes each path with a status letter. Lowercase means
    `assume-unchanged`; `S` means `skip-worktree`. Either hides the file from
    `git status`, so `worktreeDigest` and `worktreeClean` say nothing about it
    while the scanner reads it anyway. Hashing the flag list alone -- round 9's
    fix -- detects the flag being set and nothing about the bytes it hides.
    """
    parts: list[str] = []
    for line in sorted(index_flags.splitlines()):
        if len(line) < 3 or line[1] != " ":
            continue
        flag, relative = line[0], line[2:]
        if not (flag.islower() or flag == "S"):
            continue
        full = repo / relative
        try:
            content = f"sha256:{hashlib.sha256(full.read_bytes()).hexdigest()}"
        except OSError:
            content = "unreadable"
        parts.append(f"{flag} {relative} {content}")
    return digest_of("\n".join(parts))


# R12-C1, demonstrated against all eight consumers. `prd.md:19` and the parent
# `design.md:150` both require this and neither the scanner nor any earlier round
# implemented it: a codex or pi usage marker in a consumer whose registry
# `platforms` omits that platform is a **blocker**. The reason is not
# bookkeeping. `retainVendoredFor` intersects the consumer's *declared*
# platforms (parent `design.md:187`), so an undeclared user of a retained
# platform has their `.agents/**` deleted, and `.agents/skills/` is how that
# platform reads a skill. Silently deleting it is exactly the failure the gate
# exists to prevent.
#
# Which platforms that covers is derived, not written here. The blocker is
# justified only while a declaration would change the plan, so the set is read
# from the partition's `retainVendoredFor` lists -- the same artifact the
# conversion classifier reads -- and a consumer-owned marker for a platform
# outside it is recorded as an `advisories` entry instead. Detection is
# unchanged either way; only the bucket moves, and `packDefects` is unaffected.
#
# `codex` was in that set until an executed probe removed it. The clause above
# used to end "because Codex cannot consume the machine-installed plugin at
# all", which is true and irrelevant: the `.agents` families are the machine
# *installer's*, not the Claude plugin's, and Codex merges project-root
# `.agents/skills` with `$HOME/.agents/skills`. The machine install therefore
# serves it, declaring `codex` retains nothing, and blocking on it asks for a
# declaration that changes nothing -- exactly the R14-C1 disqualifier below,
# generalized from the empty-directory case to every codex marker. Evidence:
# `.trellis/tasks/08-09-codex-home-skills-family/research/codex-skills-resolution-probe.md`.
#
# R12 excluded Trellis-local paths, reasoning that a `.codex/` holding nothing
# but `trellis-*.toml` agents was a Trellis repository rather than an undeclared
# pack-codex consumer. R13 demonstrated that this was wrong in both directions
# and the PRD's unqualified rule is right.
#
# Hiding real usage: `.codex/config.toml` is on the Trellis-local list, so a
# consumer whose entire Codex surface is a project-scoped `config.toml` returned
# `clear` -- and `sd-github-review` is exactly that consumer, with
# `.agents/skills/**` in its receipt that `retainVendoredFor` keeps only for a
# declared codex or pi consumer. False blockers: an empty `.codex/hooks/` fired
# anyway, because the directory probe counts an empty directory. And the
# exclusion did not even work for pi: `is_trellis_local` matched patterns ending
# in `/` with a literal `startswith`, so `.pi/skills/trellis-*/` never matched
# the glob it contains.
#
# The exclusion's premise was that a Trellis-local `.codex/` is usage the
# conversion does not affect. It is not. Whoever authored those files runs Codex
# in that repository, and conversion deletes `.agents/**` out from under them
# regardless of which tool wrote the `.codex/` file. The presence of the surface
# is the fact that matters, so the marker is what `prd.md:19` says it is:
# unqualified. The resolution is not "do not block" but the canary's recorded
# choice -- declare `codex`, or remove the usage.
#
# R14-C1 corrected it once more, in both directions, and this is where it
# settles. An *empty* directory is not usage: Codex leaves one behind, the
# conversion plan against a consumer with one is byte-identical, and blocking on
# it asks for a declaration that changes nothing. So the directory marker
# requires at least one file under it. And a directory is not *necessary*
# either: a repository whose surviving guidance says `codex exec ...` is a Codex
# consumer whether or not it keeps a `.codex/` directory, which the previous
# rule missed entirely. That is a fourth marker, matched the same way
# `$CODEX_HOME` is.
#
# What no repository scan can see: a consumer whose Codex use is entirely global
# -- `~/.codex/`, a CLI flag, a CI environment variable. The scanner cannot
# close that, and pretending otherwise would be the worst kind of fail-open. The
# canary task carries it as an operator declaration instead (child 3,
# requirement 3), which is the only place the fact exists.
MARKER_PLATFORMS = ("codex", "pi")


def retained_platforms(partition: conversion.Partition) -> frozenset[str]:
    """Platforms some machine platform still keeps vendored rows for.

    Read from the partition rather than restated as a constant: the marker
    blocks *because* a declaration changes the conversion plan, and that is
    exactly what `retainVendoredFor` decides. Deriving it means the two cannot
    drift, and retiring a platform's retention retires its blocker in the same
    edit.
    """
    found: set[str] = set()
    for body in partition.platforms.values():
        found.update(body.get("retainVendoredFor") or ())
    return frozenset(found)


# The dispositions a marker can have, named the same way the classifier names
# them: the pack's own text is a pack defect, text inside a block the conversion
# strips leaves with it, and everything else is the consumer's. The consumer
# case is the only one that depends on the platform -- see `retained_platforms`.
BUCKET_FOR_OWNERSHIP = {
    "pack": "packDefects",
    "stripped": "scheduled",
    "consumer": "blockers",
}


def marker_bucket(ownership_kind: str, platform: str, retained: frozenset[str]) -> str:
    """Bucket for one marker, given who owns the text and which platform it is.

    Pack-owned and stripped text keep their fixed buckets: a pack defect is a
    pack defect whether or not anything is retained for the platform. Only the
    consumer's own usage is conditional, because only it was ever a statement
    about what the consumer would lose.
    """
    if ownership_kind != "consumer":
        return BUCKET_FOR_OWNERSHIP[ownership_kind]
    return "blockers" if platform in retained else "advisories"


CODEX_HOME = re.compile(r"\$(?:\{)?CODEX_HOME\b")
# The CLI. R15-C2 demonstrated both failure directions in the first attempt.
# False positive: "This repository does not use codex exec; that command is
# prohibited" is a sentence *forbidding* the tool, and a whole-file search for
# four adjacent words called it usage. False negatives: `codex --help` lists
# `review` as a command and `e` as the alias for `exec`, and global options may
# precede the subcommand, so `codex -C . exec`, `codex review`, and `codex e`
# are all real invocations the first pattern missed.
#
# So the pattern accepts global options and every subcommand, and the *line* has
# to be in command position -- the same test the classifier already applies to a
# citation. A sentence about Codex is not an invocation of it.
# R16-C2 retired the subcommand enumeration. Round 15 replaced four adjacent
# words with a list of accepted subcommands, and Codex broke it from both ends
# in one round: `codex plugin list` and a bare interactive `codex <prompt>` are
# real invocations the list does not contain, and the list will keep going stale
# every time the CLI grows a verb. Enumerating the callee was the wrong axis.
# What makes a line an invocation is the *position* of the command word, which
# is the same rule this scanner already applies to `./path` and to runners.
#
# `codex(?![\w./:-])` is the command word and nothing else: it excludes the
# `.codex/` path segment, a `codex:` mapping key, and `codex-cli`, none of which
# is a call.
CODEX_WORD = r"codex(?![\w./:-])"
CODEX_AT_START = re.compile(rf"^\s*{SHELL_PREFIX}{CODEX_WORD}")
CODEX_AFTER_SEPARATOR = re.compile(rf"(?:[;&|(]|&&|\|\|)\s*{SHELL_PREFIX}{CODEX_WORD}")
CODEX_ASSIGNED = re.compile(rf"^\s*\w+=[\"']?{CODEX_WORD}")
CODEX_TOKEN = re.compile(CODEX_WORD)
# Markdown wraps commands in prompts, bullets, quotes and headings, and those
# leaders precede a real invocation. The backtick used to be in this class and
# was R16-C2's false positive: stripping it turned the inline code span in
# "`codex exec` is prohibited here." into a line that starts with the command.
# A code span is how prose *names* a command; a prompt is how it *runs* one.
CODEX_LEADER = re.compile(r"^[\s>*\-+#$|]*")
# Anchored after the leader, not searched: an imperative *opens* a clause.
# R15-C2's false positive -- "This repository does not use codex exec" -- has
# `use` in the middle of a sentence that forbids the tool, and an unanchored
# search reads a prohibition as an instruction.
CODEX_IMPERATIVE = re.compile(
    rf"^(?:use|run|invoke|execute|call|launch)\b[^\n]{{0,32}}?\b{CODEX_WORD}",
    re.IGNORECASE,
)


def codex_in_command_position(
    line: str,
    number: int,
    commanded: set[int],
    structured: set[int] | None = None,
) -> bool:
    """Whether this line *calls* codex rather than mentioning it.

    In structured data the answer is the key the value hangs from and nothing
    else -- `"scripts": {"agent": "codex exec --help"}` runs under `npm run
    agent`, while a `"description"` containing the same words does not run at
    all. Line shape describes typography there, not execution, so the structured
    answer is returned alone rather than unioned with the text rules.
    """
    if structured is not None:
        return number in structured
    if number in commanded or COMMAND_CONTEXT.search(line):
        return True
    if (
        CODEX_AT_START.search(line)
        or CODEX_AFTER_SEPARATOR.search(line)
        or CODEX_ASSIGNED.search(line)
    ):
        return True
    stripped = CODEX_LEADER.sub("", line)
    if CODEX_AT_START.search(stripped):
        return True
    return bool(CODEX_IMPERATIVE.search(stripped))


def platform_marker_hits(
    repo: Path,
    files: list[str],
    declared: frozenset[str],
    removed: frozenset[str],
    retained: frozenset[str],
    owned_at=None,
    preread: dict[str, bytes] | None = None,
) -> dict[str, list[dict]]:
    """Undeclared codex/pi usage, bucketed by ownership and retention.

    Four markers, each with its own fixture, for the reason `prd.md` gives:
    one combined case would pass while the others were never implemented. A
    populated platform directory, a `$CODEX_HOME` reference, a pi adapter
    file, and a `codex` CLI invocation in command position are four different
    ways to be a codex or pi consumer. Two things that look like markers are
    not: an empty directory (R14-C1) and prose naming the command (R16-C2).
    The docstring said "three" through round 16 because the CLI marker was
    added to the rule and not to the paragraph describing it -- the same
    corrected-in-one-artifact drift the ledger keeps recording.

    Each marker aggregates to one entry per consumer rather than one per hit.
    The finding is a fact about the consumer -- "this repository uses Codex and
    the registry does not say so" -- and `mezmo_benchmark` alone names
    `$CODEX_HOME` in 49 files. Forty-nine copies of one fact is noise that
    hides the other blockers.

    ``retained`` is the set from `retained_platforms`. A consumer-owned marker
    for a platform in it blocks; one for a platform outside it is an advisory,
    because the declaration it asks for would not change the conversion plan.
    """
    hits: dict[str, list[dict]] = {
        "blockers": [],
        "packDefects": [],
        "scheduled": [],
        "advisories": [],
    }

    def ownership(relative: str, number: int | None) -> str:
        # R16-C1: ownership is per content, not per path. A managed block is a
        # span inside a file whose other lines the consumer wrote, so a marker
        # is the pack's text only if the *line* is, and the round-15 whole-file
        # set answered a question nobody asked. The classifier already proves
        # this per line; the marker pass now asks it the same way.
        if owned_at is None:
            return "consumer"
        return owned_at(relative, number)

    def record(bucket: str, entry: dict) -> None:
        hits[bucket].append(entry)

    for platform in MARKER_PLATFORMS:
        if platform in declared:
            continue
        info = PLATFORM_REGISTRY.get(platform)
        if info is None:
            continue
        # Probed from the filesystem, not from `git ls-files`. R12-C2: an empty
        # or wholly untracked `.codex/` leaves every recorded binding -- `head`,
        # both index digests, hidden bytes, worktree digest and cleanliness,
        # receipt occupancy, executable bits, symlink targets, binary count,
        # missing files -- byte-identical, because git does not track a
        # directory. The occupancy is the input; no file is.
        root = repo / info.directory
        if not root.is_dir():
            continue
        prefix = f"{info.directory}/"
        present = sorted(
            str(path.relative_to(repo).as_posix())
            for path in root.rglob("*")
            if path.is_file()
        )
        if present:
            # R16-C1: a directory whose every file the pack installed is the
            # pack's own occupancy, not the consumer's. It is still recorded --
            # a surviving pack directory for a platform the registry omits is a
            # pack defect -- but it does not decide the consumer's verdict.
            consumer_present = [
                relative for relative in present if ownership(relative, None) != "pack"
            ]
            evidence = consumer_present or present
            record(
                marker_bucket("consumer", platform, retained)
                if consumer_present
                else "packDefects",
                {
                    "file": info.directory,
                    "line": None,
                    "detail": (
                        f"undeclared {platform} usage: {prefix} exists with "
                        f"{len(evidence)} file(s), e.g. {evidence[0]}"
                    ),
                },
            )
        adapters = [
            relative
            for relative in files
            if any(
                fnmatch.fnmatch(relative, pattern)
                for pattern in (getattr(info, "markers", ()) or ())
            )
        ]
        if adapters:
            consumer_adapters = [
                relative for relative in adapters if ownership(relative, None) != "pack"
            ]
            evidence = consumer_adapters or adapters
            record(
                marker_bucket("consumer", platform, retained)
                if consumer_adapters
                else "packDefects",
                {
                    "file": evidence[0],
                    "line": None,
                    "detail": (
                        f"undeclared {platform} adapter file: {len(evidence)} of "
                        f"the registry's marker paths are present"
                    ),
                },
            )
    if "codex" not in declared:
        empty: dict[str, list[dict]] = {
            "blockers": [],
            "packDefects": [],
            "scheduled": [],
            "advisories": [],
        }
        referencing: dict[str, list[str]] = {key: [] for key in empty}
        invoking: dict[str, list[str]] = {key: [] for key in empty}
        for relative in files:
            # Two exclusions, each already a rule elsewhere in this scanner
            # rather than a judgement made here: a file the conversion removes
            # cannot be evidence of *surviving* usage (that is what `scheduled`
            # means), and a historical record of something said is not current
            # usage (R8-4).
            #
            # The third exclusion is gone. R14 keyed it on receipt membership,
            # which `prd.md:197` says is not ownership; R15 keyed it on
            # whole-file ownership, which R16 showed is not the granularity the
            # proof has -- and both *dropped* the hit rather than bucketing it,
            # so a marker in the pack's own text left every bucket and the
            # four-bucket claim with it. Pack-owned markers are now recorded as
            # what they are: the pack shipping text that names an undeclared
            # tool. That is a pack defect, and it is not the consumer's verdict.
            if relative in removed:
                continue
            if relative.startswith(HISTORICAL_PREFIXES) or relative in HISTORICAL_NAMES:
                continue
            # R16-C3 is a rule, not one call site: bytes that decide a
            # classification are read once. A marker is a classification.
            raw = (preread or {}).get(relative)
            if raw is None:
                try:
                    raw = (repo / relative).read_bytes()
                except OSError:
                    continue
            if is_binary(raw) and not is_executable_surface(repo, relative):
                continue
            body = raw.decode("utf-8", errors="replace")
            lines = body.splitlines()
            structured = structured_command_lines(lines, relative, body)
            commanded = command_lines(lines) | direct_path_lines(lines, relative, body)
            for number, line in enumerate(lines, start=1):
                bucket = marker_bucket(ownership(relative, number), "codex", retained)
                if CODEX_HOME.search(line) and relative not in referencing[bucket]:
                    referencing[bucket].append(relative)
                if (
                    CODEX_TOKEN.search(line)
                    and codex_in_command_position(line, number, commanded, structured)
                    and relative not in invoking[bucket]
                ):
                    invoking[bucket].append(relative)
        for bucket, found in invoking.items():
            if found:
                record(
                    bucket,
                    {
                        "file": "codex",
                        "line": None,
                        "detail": (
                            f"undeclared codex usage: the codex CLI is invoked in "
                            f"{len(found)} surviving file(s), e.g. {found[0]}"
                        ),
                    },
                )
        for bucket, found in referencing.items():
            if found:
                record(
                    bucket,
                    {
                        # A stable synthetic key, not `found[0]`: the first
                        # matching path is whatever `git ls-files` happened to
                        # sort first, so anchoring a fixture to it anchors to
                        # nothing.
                        "file": "$CODEX_HOME",
                        "line": None,
                        "detail": (
                            f"undeclared codex usage: $CODEX_HOME referenced in "
                            f"{len(found)} surviving file(s), e.g. {found[0]}"
                        ),
                    },
                )
    return hits


def platform_marker_digest(hits, repo: Path, declared: frozenset[str]) -> str:
    """R12-C2: bind directory occupancy, which no file-oriented digest sees.

    An empty `.codex/` directory added to a clean checkout leaves `head`, both
    index digests, the hidden-bytes digest, the worktree digest and cleanliness,
    receipt occupancy, executable bits, symlink targets, the binary count, and
    the missing-file list all byte-identical -- while the verdict must change
    from `clear` to `blocked`. The occupancy is the input; no file is.
    """
    parts = [f"declared:{','.join(sorted(declared))}"]
    for platform in MARKER_PLATFORMS:
        info = PLATFORM_REGISTRY.get(platform)
        if info is None:
            continue
        present = (repo / info.directory).is_dir()
        parts.append(f"{platform}:{info.directory}:{'present' if present else 'absent'}")
    for bucket in sorted(hits):
        parts += [
            f"hit:{bucket}:{hit['file']}:{hit['detail']}" for hit in hits[bucket]
        ]
    return digest_of("\n".join(parts))


def enumerate_files(repo: Path) -> list[str]:
    """Every file the conversion would run against: tracked *and* untracked.

    H10-1. The conversion runs against a working tree, not against the index,
    and an untracked script that invokes a removed path breaks exactly as hard
    as a committed one. Enumerating only `git ls-files` left that class unread
    while `worktreeClean` -- which the verdict does not require -- was the only
    signal it existed. Measured: 8 untracked files across the fleet at the time
    of the fix, all in `rwbp-coordinator`, none citing a removed path; by round
    11, six real `se-ai-command-pack` blockers lived in untracked files.

    Ignored files stay out: they are bound by `receiptOccupancyDigest` for the
    targets that matter, and are not part of a conversion PR.

    R11-C2: this was inline in `scan()`, so reverting it -- dropping untracked
    files -- changed real blocker counts and failed no fixture. A rule the
    harness cannot call is a rule the harness cannot protect.
    """
    files = [
        entry
        for entry in git(repo, "ls-files", "-z").split("\0")
        if entry and not entry.startswith(SKIP_DIRS)
    ]
    files += [
        entry
        for entry in git(
            repo, "ls-files", "-z", "--others", "--exclude-standard"
        ).split("\0")
        if entry and not entry.startswith(SKIP_DIRS)
    ]
    return files


def symlink_targets_digest(repo: Path, files: list[str]) -> str:
    """R11-C3, constructed. What each symlink in the tree actually resolves to.

    An *ignored* symlink is bound by nothing: switch an intermediate `alias`
    from `scripts` to `safe` and `resolve_link()` returns a different target,
    so a tracked link through it changes bucket -- while HEAD, both index
    digests, the hidden-bytes digest, the worktree digest and cleanliness, the
    receipt-occupancy digest, the executable-bits digest, and the missing-file
    list all stay identical. The resolution is the input; the link is not.
    """
    parts: list[str] = []
    for relative in sorted(files):
        if not (repo / relative).is_symlink():
            continue
        parts.append(f"{relative} -> {resolve_link(repo, relative)}")
    return digest_of("\n".join(parts))


def is_binary(raw: bytes) -> bool:
    """Whether these bytes look like an asset rather than text.

    R14-C6: this used to say "cannot carry a citation", and R13 stopped that
    being true -- an asset's bytes in command position still execute, and its
    weaker citations are recorded as advisories. The predicate answers one
    narrow question: do these bytes read as an asset. What follows from the
    answer is decided at the call site.

    R10-C5: "did not decode as strict UTF-8" is not "cannot carry a citation".
    A shell script with one Latin-1 comment and an invocation of a removed path
    is still a shell script; round 9 sent it to `binaryFiles` and
    cleared it. A NUL byte is the signal that actually distinguishes a binary
    asset -- and it is what all 16 of `rwbp-coordinator`'s decode failures
    have, being PNG and ICO files. Everything else is decoded leniently and
    classified normally: a replacement character in a comment cannot
    manufacture a citation, because matching still requires a removed path.

    R11: this was an inline `if b"\\0" in raw` inside `scan()`, which meant no
    fixture could reach it without standing up a whole synthetic consumer with
    a receipt. A rule the harness cannot call is a rule the harness cannot
    protect, so it is a function.
    """
    return b"\0" in raw


def resolve_link(repo: Path, relative: str, limit: int = 16) -> str | None:
    """Repository-relative path a tracked symlink ultimately names.

    ``None`` when it cannot be resolved -- unreadable, a cycle, or a target
    outside the repository -- which the caller treats as blocking rather than
    skipping.

    R9-C4. The earlier version compared ``os.readlink()`` output against a
    relative removal set, so ``link -> /repo/scripts/removed.sh`` matched
    nothing, and a link pointing at another link that ends on a removed path
    was invisible. Both are still empty across the fleet; the code now keeps
    the fail-closed promise it was making.
    """
    try:
        # R10-C4: resolve through the filesystem rather than lexically. Walking
        # `os.readlink` a component at a time only ever inspects the *last*
        # component, so `top -> alias/full-check.sh` where `alias -> scripts`
        # returned `alias/full-check.sh` -- a path that is not in the removal
        # set while the file it reaches is. `resolve(strict=True)` follows
        # intermediate directory links, and raises rather than inventing an
        # answer for a broken chain (ENOENT) or a cycle (ELOOP), which is the
        # fail-closed behaviour R9-C4 claimed and did not have. `limit` is kept
        # for signature stability; the OS enforces its own depth bound.
        target = (repo / relative).resolve(strict=True)
        return str(target.relative_to(repo.resolve()))
    except (OSError, RuntimeError, ValueError):
        # OSError: unreadable, broken, or cyclic. ValueError: outside the
        # repository, which the conversion does not remove -- but the caller
        # treats `None` as blocking either way, because a link this scan could
        # not follow is not a link it cleared.
        return None


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

    R9-3: and the name must carry the pack name. "Owned by exactly one removed
    path and by no survivor" is not the same as "can only mean that path": the
    survivor test only sees files this repository tracks, and a bare name in
    prose often means something the repository does not contain at all.
    Measured: se-ai-command-pack's se-author SKILL.md says "`review.md`:
    findings, decisions, approved edits", naming a workspace artifact the skill
    writes at runtime, and it matched the removed `.claude/commands/sd/review.md`
    -- the same shape as the round-6 `references/examples.md` false blocker, one
    level further in. `security.md` and `update-spec.md` collide the same way.
    A distinctive name -- `sd_ai_command_pack_lib.py` -- carries its own proof;
    `review.md` carries none. This keeps every recovery the rule was added for
    (the 36 `REPO_ROOT / "scripts" / "<pack file>"` citations) and drops the
    coincidences, at the cost of leaving a distinctively-named-only lower bound.
    """
    counts: dict[str, int] = {}
    for entry in removed:
        name = entry.rsplit("/", 1)[-1]
        counts[name] = counts.get(name, 0) + 1
    surviving = {entry.rsplit("/", 1)[-1] for entry in survivors}
    return frozenset(
        name
        for name, count in counts.items()
        if count == 1
        and name not in surviving
        and ("sd-ai-command-pack" in name or "sd_ai_command_pack" in name)
    )


def cites_removed_path(
    token: str,
    removed: frozenset[str],
    repo: Path,
    relative_to: str,
    survivors: frozenset[str],
    unambiguous: frozenset[str],
    *,
    bare_names: bool = True,
) -> bool:
    """Does this token name something the conversion removes?

    Five ways, and deliberately not a sixth (`prd.md:42` is authoritative):

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
    # R9-1: TOKEN cannot contain ":", so a URL tokenizes to its authority plus
    # path -- "https://example.com/docs/SD_AI_COMMAND_PACK.md" becomes
    # "//example.com/docs/SD_AI_COMMAND_PACK.md", whose tail matches a removed
    # path. A URL names a resource on a host, not a file the conversion
    # deletes. No repository-relative path begins with "//", so the residue is
    # unambiguous. Measured zero occurrences in the blockers and packDefects
    # buckets of all 8 consumers at the time of the fix: this closes the class
    # before it has an instance rather than after.
    if token.startswith("//"):
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
    # Rules 3 and 5 are the bare-name family: neither reads a path out of the
    # token, both infer one from context. `bare_names=False` turns that
    # inference off for a slash-free token while leaving rule 3's real job --
    # a relative path like `lib/x.sh` cited from a subdirectory -- intact.
    if bare_names or "/" in token:
        parent = str(Path(relative_to).parent)
        resolved = os.path.normpath(token if parent == "." else f"{parent}/{token}")
        if resolved in removed:
            return True
    return bare_names and "/" not in token and token in unambiguous


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


def aligned_line_numbers(original: list[str], rewritten: list[str]) -> list[int]:
    """Map each rewritten line back to a line number in the file on disk.

    The citation test runs against post-repoint bytes, but everything the hit is
    then classified against -- `spans`, `all_spans`, `commanded` -- is indexed
    off the bytes actually present, and the reported `line` has to point at a
    line an operator can open. Positional indexing only agrees with both when
    the rewrite preserves the line count. It stopped doing that in 0.71.21,
    where a rewritten Copilot glob bullet gains a `narrow-globs: skip` comment
    line: the equal-count guard this replaces then fell back to the unrewritten
    text and reported seven already-repointed citations as pack defects, which
    no release could clear.

    A diff answers the question the line count was standing in for. Unchanged
    and substituted lines map to the line they came from. An inserted line has
    no line of its own, so it takes the original line it was inserted after --
    adjacency is the right answer for block membership and command context, and
    the alternative, inventing a number past the end of the file, is not.
    """
    mapping: list[int] = []
    matcher = difflib.SequenceMatcher(a=original, b=rewritten, autojunk=False)
    for tag, first, last, other_first, other_last in matcher.get_opcodes():
        if tag == "delete":
            continue
        for offset in range(other_last - other_first):
            # `first + offset` is the line this one replaced, when there was
            # one; past the end of the replaced run -- and for every inserted
            # line, whose run is empty -- fall back to the last original line
            # at or before the splice, clamped to a real line.
            index = first + offset
            if index >= last:
                index = max(first - 1, 0) if first == last else last - 1
            mapping.append(min(index, len(original) - 1) + 1 if original else 1)
    return mapping


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


def provenance_digests(raw: bytes | None) -> dict[str, str]:
    """Ownership's recorded digests, parsed from bytes the caller already read.

    R16-C3: this used to open the file itself, so ownership parsed one read
    while `scannedBytesDigest` hashed another. R15 bound the bookkeeping bytes
    without making them the *same* bytes, and Codex moved a hit from `blockers`
    to `packDefects` through the gap with `changedBindings: []` and an identical
    `scannedBytesDigest`. Taking bytes rather than a path is what closes it:
    there is no second read to disagree with.
    """
    if raw is None:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError):
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


def scan(
    name: str, repo: Path, platforms: frozenset[str], partition_path: Path
) -> dict:
    """Measure one consumer. The caller decides the verdict from the result.

    ``partition_path`` is passed rather than derived: this module must not
    assume it sits inside a source checkout at a fixed depth, and both the
    shipped CLI and the tests supply it explicitly.
    """
    receipt = conversion.read_installed_targets_receipt(repo)
    partition = conversion.load_partition(partition_path)
    occupied = conversion.occupied_receipt_targets(repo, receipt)
    plan = conversion.build_conversion_plan(
        receipt, partition, platforms, occupied=occupied
    )
    removed = frozenset(plan.delete) | frozenset(plan.retire)
    stripped = frozenset(plan.block_strip)
    # The bytes a *kept, pack-owned* file will have once the conversion this
    # verdict authorizes has run, rather than the bytes it has now.
    #
    # `repoint_kept_references` (installer/thin.py) rewrites exactly this
    # population, for exactly this reason -- its docstring says the kept
    # repo-native files "still say `scripts/<name>` and
    # `docs/SD_AI_COMMAND_PACK.md`... and the resweep reports every one of them
    # as a `packDefect`". Reading the pre-conversion bytes made that prophecy
    # self-fulfilling: `decide` blocks on any packDefect and `--thin` refuses a
    # verdict that is not `clear`, so a fat consumer whose pack files correctly
    # name the paths it currently has could never reach `clear`. Measured
    # 2026-08-15 across the canary cohort: 15 pack defects each, 14 of them
    # repointed by the conversion, and no consumer in the fleet convertible.
    #
    # Sourced from the installer's own computation rather than restated here.
    # Two implementations of "what will the conversion write" is precisely the
    # drift that would let a verdict authorize bytes nobody is going to write.
    # Consumer-owned files are deliberately excluded: nothing rewrites those,
    # so their citations are scanned exactly as they are written.
    repointed = thin.planned_repoints(repo, tuple(plan.keep))
    managed = frozenset(receipt.entries)
    # One read per generated bookkeeping file, before anything consults them.
    # Ownership parses these bytes and `scannedBytesDigest` hashes these bytes.
    bookkeeping: dict[str, bytes] = {}
    bookkeeping_unreadable: set[str] = set()
    for relative in sorted(GENERATED_BOOKKEEPING):
        try:
            bookkeeping[relative] = (repo / relative).read_bytes()
        except OSError:
            bookkeeping_unreadable.add(relative)
    recorded = provenance_digests(bookkeeping.get(PROVENANCE_FILE.as_posix()))
    shipped = shipped_template_digests()

    buckets: dict[str, list[dict]] = {
        "blockers": [],
        "packDefects": [],
        "scheduled": [],
        "advisories": [],
    }
    tracked = enumerate_files(repo)
    survivors = frozenset(tracked) - removed
    binary: list[str] = []
    missing: list[str] = []
    # R13-C3, constructed: a `.gitattributes` clean filter that maps any
    # worktree content to the committed blob leaves `git status` empty, so
    # `worktreeDigest` -- which hashes only the paths git reports dirty -- sees
    # nothing, while the scanner reads the real worktree bytes and classifies
    # them. Codex built one and moved a consumer from `clear` to `blocked` with
    # all twelve bindings byte-identical. Every other binding is a proxy for the
    # bytes; this one is the bytes, digested as they are read.
    read: list[str] = []
    # R15-C1: the marker pass needs the ownership the classifier proves, not the
    # receipt membership it used to stand in for. R16-C1: and it needs it at the
    # granularity the proof has -- per line for a managed block, per file for a
    # digest or a shipped-bytes comparison -- so what is recorded here is the
    # evidence, and `owned_at` below answers the question from it.
    ownership_info: dict[str, dict] = {}
    unambiguous = unambiguous_basenames(removed, survivors)
    for relative in tracked:
        if relative in removed:
            buckets["scheduled"].append({"file": relative, "line": None})
            continue
        if relative in GENERATED_BOOKKEEPING:
            # R15-C3, demonstrated: these are not classified, but `provenance.json`
            # *decides* classification -- every ownership verdict compares against
            # its digests. Skipping them left those bytes bound by nothing, and
            # Codex moved a hit from `blockers` to `packDefects` by feeding
            # ownership different provenance while every digest stayed identical.
            # The bytes that decide a classification are inputs to it.
            if relative in bookkeeping_unreadable:
                missing.append(relative)
                continue
            buckets["scheduled"].append(
                {"file": relative, "line": None, "detail": "generated bookkeeping"}
            )
            read.append(
                f"{relative}\0"
                f"{hashlib.sha256(bookkeeping[relative]).hexdigest()}"
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
            # R9-C4: resolve the link the way the filesystem does, not the way
            # the string reads. Three forms were missed: an absolute target
            # inside the repository (compared as-is against a relative removal
            # set, so it matched nothing), a chain of links ending at a removed
            # path, and an unreadable link, which simply `continue`d. All three
            # are still empty across the fleet -- no consumer has a tracked
            # symlink -- but "fails closed" was a claim the code did not keep.
            target = resolve_link(repo, relative)
            if target is None:
                buckets["blockers"].append(
                    {
                        "file": relative,
                        "line": None,
                        "detail": "unresolvable symlink",
                    }
                )
            elif target in removed:
                buckets["blockers"].append(
                    {
                        "file": relative,
                        "line": None,
                        "detail": f"symlink to removed path: {target}",
                    }
                )
            continue
        try:
            raw = full.read_bytes()
        except OSError:
            # R9-C2: an OSError is not a binary file. Round 8's handler shared
            # one branch with UnicodeError, so a present-but-unreadable file --
            # a permission-denied UTF-8 file full of blockers -- was counted as
            # a binary asset and cleared. Present-and-unreadable is the same
            # epistemic state as absent: bytes this scan did not read. Both go
            # to `missingFiles`, which forces the verdict `blocked`. A
            # sparse checkout or a skip-worktree entry looks identical to a
            # complete tree in `git ls-files -s`, so this is the difference
            # between "measured zero" and "did not look".
            if relative in managed:
                buckets["packDefects"].append(
                    {"file": relative, "line": None, "detail": "unreadable pack target"}
                )
            else:
                missing.append(relative)
            continue
        read.append(f"{relative}\0{hashlib.sha256(raw).hexdigest()}")
        # R12-C4, constructed but executable: a NUL byte means "binary", and
        # binary does not mean "cannot execute". Codex fed bash a NUL-bearing
        # source stream and it ran, printing `NUL_SCRIPT_EXECUTED` -- so a
        # shell script carrying one NUL plus an invocation of a removed path
        # could clear. The NUL test decides whether the *bytes* look like an
        # asset; it is not licence to skip a file the execution-surface rule
        # says can run.
        #
        # R13-C5: round 12 closed only the path-derived half. Execution is
        # decided by *path* -- `nul.sh` is a script -- and by *content* -- a
        # line in command position invokes what follows regardless of the file's
        # name. Codex constructed the other combination, a NUL-bearing
        # `notes.dat` whose second line runs a removed script, and it cleared.
        # So an unmanaged asset is no longer skipped: it is decoded leniently
        # and read for command position only. The weaker citation forms stay
        # suppressed, which is what the NUL test is actually for -- a PNG whose
        # bytes happen to contain a path is not a citation -- while the one form
        # that executes still blocks. Matching always requires a removed path,
        # so a replacement character cannot manufacture a citation.
        asset = is_binary(raw) and not is_executable_surface(repo, relative)
        if asset:
            # R14-C5, demonstrated: this branch used to emit a whole-file
            # `unreadable pack target` defect for any *managed* file containing
            # a NUL, and a `.gitignore` carrying harmless NUL bytes and no
            # citation at all blocked the conversion. The read succeeded --
            # "contains NUL" and "could not be read" are different facts, and
            # only the second is a defect. A managed asset is an asset: the pack
            # ships binary files. `unreadable pack target` is now reserved for
            # the `OSError` handler above and the symlink case before it.
            binary.append(relative)
        body = raw.decode("utf-8", errors="replace")
        lines = body.splitlines()
        all_spans = block_spans(lines)
        malformed_markers = all_spans is None
        spans = stripped_spans(relative, lines, all_spans) if relative in stripped else []
        vouched = recorded.get(relative)
        # R14-C2, demonstrated with a split-read fixture and again with an ACL
        # race: this used to be `file_digest(full)`, a *second* read of the same
        # path. The classification then rested on bytes no binding recorded --
        # Codex made the two reads disagree and moved a consumer from `blocked`
        # to `clear` with `changedBindings: []`. Ownership is now decided from
        # the same bytes `scannedBytesDigest` hashed, so a second-read
        # disagreement cannot exist: there is no second read.
        actual = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        pack_owned = relative in managed and vouched is not None and vouched == actual
        # Provenance never vouches a managed-block, force-preserved, or generated
        # target, so a missing digest proves nothing about ownership. Managed
        # blocks are resolved by their markers; force-preserved targets are
        # resolved against the pack's own shipped bytes; malformed markers are
        # unresolvable and fail closed to pack-owned.
        forced = relative in shipped
        if relative in managed and vouched is None and forced:
            # R16-C1: a force-preserved target's ownership *is* the comparison
            # against the pack's shipped bytes -- identical means the pack wrote
            # it, edited means the consumer did. Nothing else decides it. This
            # used to fall through to the malformed-marker rule below, and Codex
            # showed a consumer-edited PR template carrying an unmatched pack
            # marker being called a pack defect on the strength of the marker
            # while the byte comparison said consumer.
            pack_owned = shipped[relative] == actual
        elif relative in managed and vouched is None:
            pack_owned = pack_owned or (forced and shipped[relative] == actual)
        unvouchable = relative in managed and vouched is None and not forced
        ownership_info[relative] = {
            "whole": pack_owned,
            "unvouchable": unvouchable,
            "malformed": malformed_markers,
            "packSpans": all_spans or [],
            "strippedSpans": spans,
        }
        executable = is_executable_surface(repo, relative)
        historical = (
            relative.startswith(HISTORICAL_PREFIXES) or relative in HISTORICAL_NAMES
        )
        commanded = command_lines(lines) | direct_path_lines(lines, relative, body)
        # Scan what the conversion will leave behind, for pack-owned kept files
        # only. Everything above -- ownership, markers, spans, command context,
        # and `scannedBytesDigest` -- stays on the bytes actually present: those
        # decide *whose* file this is and *what a binding recorded*, questions
        # the rewrite does not touch. Only the citation test moves.
        #
        # A rewrite may change the line count -- 0.71.21's narrow-globs comment
        # does -- so the scanned index is not a line number. `aligned_line_numbers`
        # carries each scanned line back to the line it came from, and every
        # lookup below and the reported `line` use that, not the position.
        # Membership in `repointed` is the whole test. `plan.keep` is built from
        # the *receipt*, so it holds pack-installed targets and nothing else: a
        # consumer-authored file like `scripts/check.sh` is not in it and is
        # never scanned rewritten. It is not only `packDefects` that this can
        # move, and the difference is not a leak. A pack-installed target the
        # consumer has since edited -- measured: `rwbp-coordinator`'s
        # `.prism/rules.json`, a `consumer-config` row it has taken over --
        # reports as a `blocker` because the text is the consumer's, and the
        # conversion repoints it all the same. One citation there stopped
        # blocking, correctly: the question a verdict answers is whether the
        # converted tree still names a removed path. Ownership decides who is
        # accountable for a citation, not whether it survives.
        # Ownership is deliberately not consulted here --
        # `.github/copilot-instructions.md` is a managed-block target whose
        # prologue the consumer owns, so whole-file ownership is false while the
        # conversion rewrites the file all the same. Gating on ownership left
        # its seven citations blocking a conversion that repoints them.
        scanned = lines
        origin = list(range(1, len(lines) + 1))
        if relative in repointed:
            scanned = repointed[relative].splitlines()
            origin = aligned_line_numbers(lines, scanned)

        # See `LAYOUT_RESOLVER_KEPT_TARGET`. Read from `scanned`, not `lines`:
        # a kept file whose resolver citation the conversion writes has adopted
        # the contract in the tree the verdict is about.
        bare_names = not any(
            LAYOUT_RESOLVER_KEPT_TARGET in line for line in scanned
        )

        for position, line in enumerate(scanned):
            number = origin[position]
            if not any(
                cites_removed_path(
                    token,
                    removed,
                    repo,
                    relative,
                    survivors,
                    unambiguous,
                    bare_names=bare_names,
                )
                for token in TOKEN.findall(line)
            ):
                continue
            entry = {"file": relative, "line": number, "detail": line.strip()[:160]}
            if asset:
                # R13-C5: command position in an asset's bytes still executes.
                # R14-C6: and every other form is *recorded*, not discarded --
                # the PRD says each hit lands in exactly one of four buckets,
                # and silently dropping one made that false. Advisory is the
                # honest bucket: a PNG whose bytes happen to spell a removed
                # path is real information about the tree and no reason to
                # refuse a conversion.
                if COMMAND_CONTEXT.search(line) or number in commanded:
                    buckets["blockers"].append(entry)
                else:
                    buckets["advisories"].append(
                        {**entry, "detail": f"[asset bytes] {entry['detail']}"}
                    )
                continue
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

    def owned_at(relative: str, number: int | None) -> str:
        info = ownership_info.get(relative)
        if info is None:
            # Never classified -- untracked, removed, or unreadable. Nothing
            # proved the pack owns it, so it is the consumer's.
            return "consumer"
        if number is not None and any(
            start <= number <= end for start, end in info["strippedSpans"]
        ):
            return "stripped"
        if info["whole"]:
            return "pack"
        if number is None:
            return "consumer"
        if info["unvouchable"] and (
            info["malformed"]
            or any(start <= number <= end for start, end in info["packSpans"])
        ):
            return "pack"
        return "consumer"

    marker_hits = platform_marker_hits(
        repo,
        tracked,
        platforms,
        removed,
        retained_platforms(partition),
        owned_at,
        bookkeeping,
    )
    for bucket, entries in marker_hits.items():
        buckets[bucket].extend(entries)

    index = git(repo, "ls-files", "-s")
    # R9-C3 / R10-C3. `git status` hides a file marked `assume-unchanged` or
    # `skip-worktree`, so its bytes can change while `head`, `indexDigest`,
    # `worktreeDigest`, `worktreeClean`, `executableBitsDigest`, and
    # `missingFiles` all stay identical -- and the scanner still reads
    # the new bytes and can classify them differently.
    #
    # Round 9 hashed `git ls-files -v` and called that binding. It is not: the
    # output carries the flag letter and the path, so it detects a flag being
    # *set* and nothing about the content it hides. A file already carrying the
    # flag when the scan ran could then change freely. `hidden_bytes_digest`
    # hashes the content of exactly those entries, which is the only thing that
    # closes it. No consumer sets either flag today.
    index_flags = git(repo, "ls-files", "-v")
    return {
        "consumer": name,
        "repo": str(repo),
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "indexDigest": digest_of(index),
        "indexFlagsDigest": digest_of(index_flags),
        "hiddenBytesDigest": hidden_bytes_digest(repo, index_flags),
        "worktreeDigest": worktree_digest(repo),
        "worktreeClean": not git(repo, "status", "--porcelain").strip(),
        "receiptOccupancyDigest": receipt_occupancy_digest(repo, receipt.entries),
        "executableBitsDigest": executable_bits_digest(repo, tracked),
        "symlinkTargetsDigest": symlink_targets_digest(repo, tracked),
        "scannedBytesDigest": digest_of("\n".join(read)),
        "platformMarkerDigest": platform_marker_digest(
            marker_hits, repo, platforms
        ),
        "binaryFiles": len(binary),
        "missingFiles": sorted(missing),
        "receiptEntries": len(receipt.entries),
        "removedTargets": len(removed),
        "trackedFiles": len(tracked),
        "counts": {key: len(value) for key, value in buckets.items()},
        "blockerFiles": sorted({entry["file"] for entry in buckets["blockers"]}),
        "packDefectFiles": sorted({entry["file"] for entry in buckets["packDefects"]}),
        **buckets,
    }




def load_registry() -> dict:
    """The fleet registry, keyed by consumer name."""
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {str(entry["name"]): entry for entry in payload["consumers"]}


def resolve_consumer(name: str, repo: Path | None) -> tuple[dict, Path]:
    """Return the registry entry and checkout path for one consumer."""
    entries = load_registry()
    entry = entries.get(name)
    if entry is None:
        known = ", ".join(sorted(entries)) or "none"
        raise SystemExit(
            f"error: {name} is not a registered consumer; known consumers: {known}"
        )
    # `pathHint` is a hint by name: the registry records where a checkout
    # usually lives, not where it must. `--repo` is the authoritative form and
    # the only one a caller should rely on for anything but a local sweep.
    checkout = repo if repo is not None else Path(entry["pathHint"]).expanduser()
    if not (checkout / ".git").exists():
        raise SystemExit(f"error: {checkout} is not a Git checkout")
    return entry, checkout.resolve()


def decide(result: dict) -> tuple[str, tuple[str, ...]]:
    """The verdict and its reasons, failing closed on every unresolved input.

    Kept separate from the scan so the reasons are enumerable rather than
    implied by a boolean: a caller that is told `blocked` and not why cannot
    act on it, and "the tree was dirty" and "the pack ships a broken
    reference" call for opposite responses.
    """
    reasons: list[str] = []
    if result["blockers"]:
        reasons.append(
            f"{len(result['blockers'])} consumer reference(s) to removed paths"
        )
    if result["packDefects"]:
        reasons.append(
            f"{len(result['packDefects'])} pack-owned reference(s) to removed paths"
        )
    if result["missingFiles"]:
        reasons.append(
            f"{len(result['missingFiles'])} tracked file(s) could not be read"
        )
    if not result["worktreeClean"]:
        # Not a property of the rule -- a property of when it is safe to act on
        # the answer. The research scanner deliberately omits this.
        reasons.append("worktree is dirty; commit or stash before converting")
    return ("clear" if not reasons else "blocked"), tuple(reasons)


def resweep_consumer(name: str, repo: Path | None = None) -> dict:
    """Scan one consumer and return its verdict document."""
    entry, checkout = resolve_consumer(name, repo)
    platforms = frozenset(entry.get("platforms") or ())
    result = scan(name, checkout, platforms, PARTITION)
    verdict, reasons = decide(result)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "thin-resweep-verdict",
        "verdict": verdict,
        "reasons": list(reasons),
        "classifierDigest": conversion.classifier_digest(ROOT, entry),
        **result,
    }


def render(document: dict) -> str:
    """The human summary. The JSON form is the machine contract."""
    counts = document["counts"]
    lines = [
        f"{document['consumer']}: {document['verdict']}",
        f"  repo:     {document['repo']}",
        f"  head:     {document['head']}"
        f"{'' if document['worktreeClean'] else ' (dirty)'}",
        f"  buckets:  blockers {counts['blockers']}, "
        f"packDefects {counts['packDefects']}, "
        f"scheduled {counts['scheduled']}, "
        f"advisories {counts['advisories']}",
    ]
    lines.extend(f"  reason:   {reason}" for reason in document["reasons"])
    for bucket in ("blockers", "packDefects"):
        for entry in document[bucket][:20]:
            location = entry["file"]
            if entry.get("line") is not None:
                location = f"{location}:{entry['line']}"
            lines.append(f"  {bucket[:-1]:11} {location}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("consumer", help="registry name from docs/fleet/consumers.json")
    parser.add_argument(
        "--repo", type=Path, help="scan this checkout instead of the registered path"
    )
    parser.add_argument("--json", action="store_true", help="emit the verdict document")
    parser.add_argument("--out", type=Path, help="write the verdict document here")
    args = parser.parse_args(argv)

    document = resweep_consumer(args.consumer, args.repo)
    if args.out is not None:
        args.out.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        print(render(document))
    return 0 if document["verdict"] == "clear" else 1


if __name__ == "__main__":
    raise SystemExit(main())
