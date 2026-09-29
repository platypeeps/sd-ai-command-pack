"""A repository's declared docs-only check scope (sd:2072).

A Markdown-only change ran the whole repository check twice, once at prepare
and once at the merge gate. A repository may declare, in its reviewed tree,
which paths are documentation and which command checks them:

    .github/sd-check-scope.json
    {"schema_version": 1, "docs_paths": ["docs/**", "*.md"], "docs_command": ["make", "docs-check"]}

When every path changed between the merge base and the head matches a
`docs_paths` glob, `sd-check --base REF` runs only `docs_command`. Anything
else runs the full check, and so does a change to a file that decides what the
check is: the declaration itself, a Makefile, the file the entrypoints were
detected from, `CLAUDE.local.md`, and any repository file a check command
names in its argv. No declaration, no `--base`, an empty diff or a declaration
that does not parse all run the full check: the scope only ever narrows what
runs when every condition for narrowing holds.

Globs are `glob.translate` globs: `*` stays inside one path segment, `**`
spans segments, and a leading dot is matched like any other character.
"""

from __future__ import annotations

import glob
import json
import pathlib
import re
from dataclasses import dataclass, field

import sd_lib

DECLARATION = ".github/sd-check-scope.json"
FIELDS = {"schema_version", "docs_paths", "docs_command"}
FULL = "full"
DOCS_ONLY = "docs-only"
#: Build files that decide what a check runs, wherever they sit.
BUILD_FILES = re.compile(r"(?:^|/)(?:[Mm]akefile|GNUmakefile|[^/]*\.mk)$")


class DeclarationError(ValueError):
    """The declaration exists and does not say what it must."""


@dataclass(frozen=True)
class Scope:
    """What `sd-check` runs, and why; `fork` is the merge base the diff started from."""

    mode: str
    reason: str
    fork: str | None = None
    command: tuple[str, ...] = ()
    paths: tuple[str, ...] = field(default_factory=tuple)

    def as_report(self) -> dict[str, object]:
        return {"mode": self.mode, "reason": self.reason, "fork": self.fork,
                "command": list(self.command) or None, "paths": len(self.paths)}


def declaration(root: pathlib.Path) -> tuple[list[str], list[str]] | None:
    """`(docs_paths, docs_command)`, None when the tree has none; `DeclarationError` when it is malformed."""
    path = root / DECLARATION
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DeclarationError(f"{DECLARATION} does not parse: {error}") from None
    if not isinstance(value, dict) or set(value) != FIELDS or value.get("schema_version") != 1:
        raise DeclarationError(f"{DECLARATION} needs exactly {sorted(FIELDS)} with schema_version 1")
    for name in ("docs_paths", "docs_command"):
        entries = value[name]
        if not isinstance(entries, list) or not entries or any(not isinstance(v, str) or not v for v in entries):
            raise DeclarationError(f"{DECLARATION}: {name} must be a non-empty list of non-empty strings")
    return list(value["docs_paths"]), list(value["docs_command"])


def matcher(patterns: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(glob.translate(pattern, recursive=True, include_hidden=True) for pattern in patterns))


def range_paths(root: pathlib.Path, fork: str) -> list[str] | None:
    """Every path the range touches, both sides of a rename; None when git cannot say."""
    listed = sd_lib.git_output(["diff", "--name-only", "--no-renames", "-z", f"{fork}..HEAD"], root)
    if listed is None:
        return None
    return sorted({path for path in listed.split("\0") if path})


def named_files(commands: list[list[str]]) -> set[str]:
    """Repository-relative files a command line names: `sh scripts/x.sh` names `scripts/x.sh`."""
    named = set()
    for argv in commands:
        for word in argv:
            relative = pathlib.PurePosixPath(word)
            if not relative.is_absolute() and ".." not in relative.parts and str(relative) not in (".", ""):
                named.add(str(relative))
    return named


def forcing(path: str, detection: sd_lib.Detection, root: pathlib.Path, named: set[str]) -> bool:
    """Whether a change to `path` changes what the check is, so only the full check may answer."""
    if path in (DECLARATION, sd_lib.LOCAL_FILE_NAME) or BUILD_FILES.search(path) or path in named:
        return True
    origin = detection.origin
    return origin is not None and origin.resolve() == (root / path).resolve()


def decide(root: pathlib.Path, base: str | None, detection: sd_lib.Detection) -> Scope:
    """The scope for HEAD against `base`; raises `DeclarationError` for a declaration that does not parse."""
    if base is None:
        return Scope(FULL, "no --base given")
    value = declaration(root)
    if value is None:
        return Scope(FULL, f"no {DECLARATION}")
    fork = sd_lib.git_output(["merge-base", base, "HEAD"], root)
    if not fork:
        return Scope(FULL, f"no merge base with {base}")
    paths = range_paths(root, fork)
    if not paths:
        return Scope(FULL, "no changed path to scope", fork)
    patterns, command = value
    named = named_files([*detection.commands.values(), command])
    docs = matcher(patterns)
    for path in paths:
        if forcing(path, detection, root, named):
            return Scope(FULL, f"{path} decides what the check runs", fork, paths=tuple(paths))
        if not docs.fullmatch(path):
            return Scope(FULL, f"{path} is not a docs path", fork, paths=tuple(paths))
    return Scope(DOCS_ONLY, f"all {len(paths)} changed paths are docs paths", fork, tuple(command), tuple(paths))
