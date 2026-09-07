"""Shared detection and derivation for the sd-* tools under bin/.

Every question this module answers, it answers from the repository itself: the
git worktree you are standing in, the tracked artifacts under `docs/work`, the
repo's own check entrypoints. Nothing is read from stored state, because stored
state is state that goes stale without telling anyone.

Stdlib only, Python 3.10+, no network. A caller that cannot proceed gets a
`ConfigError` carrying a sentence a human can act on, never a traceback.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any

LOCAL_FILE_NAME = "CLAUDE.local.md"
LOCAL_BLOCK_START = "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->"
LOCAL_BLOCK_END = "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->"

CONFIG_RELATIVE_PATH = pathlib.Path("sd-ai-command-pack") / "config.json"

WORK_DIR = "docs/work"
ARCHIVE_DIR = "archive"

ITEM_STATUSES = ("planning", "ready", "in_progress", "done")
MODES = ("full", "minimal", "guest")
DEFAULT_MODE = "full"

#: The three names every repository is asked about, in the order they run.
CHECK_NAMES = ("check", "test", "lint")

#: Consent, not policy: the registry entries a repository allows to receive
#: its diff. The installer asks for it once and writes the key; nothing
#: derives the value. Named here so the installer's block, `WORKFLOW.md` and
#: the test that compares them all read one source.
CONSENT_KEY = "reviewers"

GIT_TIMEOUT_SECONDS = 15

_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_MAKE_TARGET_RE = re.compile(r"^(?P<names>[^\t#=:]+):(?!=)")
_TASKFILE_TASKS_RE = re.compile(r"^tasks:\s*$")
_TASKFILE_ENTRY_RE = re.compile(r"^(?P<indent>\s+)(?P<name>[A-Za-z0-9_][A-Za-z0-9_:.\-]*):")


class ConfigError(RuntimeError):
    """A configuration or environment fault a caller reports instead of raising."""


# --------------------------------------------------------------------------
# Flat scalar parsing, shared by prd frontmatter and the local block
# --------------------------------------------------------------------------


def parse_scalars(text: str, *, comments: bool, label: str = "block") -> dict[str, str]:
    """Read flat `key: value` scalars: no nesting, no lists, no anchors.

    Deliberately not a YAML parser. The frontmatter and the local block this
    reads are each a handful of flat scalars, and depending on PyYAML would
    turn a stdlib-only tool into a tool with an install step.

    With ``comments`` a line whose first non-space character is ``#`` is a
    comment, and an unquoted value ends at the first ``#``. A quoted value is
    taken to the end of the line, so a ``#`` inside quotes stays literal.
    """
    fields: dict[str, str] = {}
    for number, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if comments and stripped.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            if comments:
                raise ConfigError(f"{label} line {number}: {stripped!r} is not `key: value`")
            continue
        value = value.strip()
        if comments and value[:1] not in ('"', "'"):
            value = value.split("#", 1)[0].strip()
        fields[key.strip()] = _unquote(value)
    return fields


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if value[0] == '"' else inner
    return value


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Read a leading `---` block of flat `key: value` scalars, or None."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return parse_scalars(text[4:end], comments=False)


# --------------------------------------------------------------------------
# Git: which repository am I in, and where does its configuration live
# --------------------------------------------------------------------------


def _git(args: list[str], cwd: pathlib.Path) -> str | None:
    """Run a read-only git query; None when git cannot answer."""
    try:
        completed = subprocess.run(  # fixed argv, no shell
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def git_output(args: list[str], root: pathlib.Path) -> str | None:
    """`git <args>` in `root`: stripped stdout, or None when git cannot answer.

    The public face of the same read-only query the helpers below use, so a
    sibling tool that needs one more `git` fact does not grow a second
    subprocess policy (timeout, no shell, failure-is-None) of its own.
    """
    return _git(args, root)


def repo_root(start: pathlib.Path | str | None = None) -> pathlib.Path | None:
    """The enclosing worktree's own root, or None outside a repository.

    Inside a linked worktree this is that worktree's root, not the main
    checkout's: `--show-toplevel` is per-worktree, which is exactly what a
    command resolving its repo from cwd wants.
    """
    base = pathlib.Path(start) if start is not None else pathlib.Path.cwd()
    base = base if base.is_dir() else base.parent
    if not base.is_dir():
        return None
    answer = _git(["rev-parse", "--show-toplevel"], cwd=base)
    return pathlib.Path(answer).resolve() if answer else None


def main_worktree_root(root: pathlib.Path) -> pathlib.Path:
    """The main checkout's root, so linked worktrees share one local config.

    `--git-common-dir` points at the shared `.git` directory; its parent is the
    main worktree. A layout where that does not hold (a bare or separated git
    directory) falls back to the worktree it was asked about.
    """
    answer = _git(["rev-parse", "--git-common-dir"], cwd=root)
    if not answer:
        return root
    common = pathlib.Path(answer)
    if not common.is_absolute():
        common = root / common
    common = common.resolve()
    return common.parent if common.name == ".git" else root


# --------------------------------------------------------------------------
# Configuration: the per-repo local block and the per-machine config file
# --------------------------------------------------------------------------


def local_block_path(root: pathlib.Path) -> pathlib.Path:
    """Where `CLAUDE.local.md` lives for this worktree: in the main checkout."""
    return main_worktree_root(root) / LOCAL_FILE_NAME


def parse_local_block(text: str, label: str = LOCAL_FILE_NAME) -> dict[str, str]:
    """Extract the marked block's flat scalars. No block is an empty dict."""
    start = text.find(LOCAL_BLOCK_START)
    if start == -1:
        if LOCAL_BLOCK_END in text:
            raise ConfigError(f"{label}: end marker without a start marker")
        return {}
    if text.find(LOCAL_BLOCK_START, start + len(LOCAL_BLOCK_START)) != -1:
        raise ConfigError(f"{label}: duplicate start markers")
    end = text.find(LOCAL_BLOCK_END, start)
    if end == -1:
        raise ConfigError(f"{label}: start marker with no end marker")
    if text.find(LOCAL_BLOCK_END, end + len(LOCAL_BLOCK_END)) != -1:
        raise ConfigError(f"{label}: duplicate end markers")
    body = text[start + len(LOCAL_BLOCK_START) : end]
    return parse_scalars(body, comments=True, label=label)


def local_block(root: pathlib.Path) -> dict[str, str]:
    """The repo's local configuration block; missing file or block is `{}`."""
    path = local_block_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (IsADirectoryError, NotADirectoryError):
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from None
    return parse_local_block(text, str(path))


def machine_config_path() -> pathlib.Path:
    """`~/.config/sd-ai-command-pack/config.json`, honouring `XDG_CONFIG_HOME`."""
    base = os.environ.get("XDG_CONFIG_HOME") or ""
    home = pathlib.Path(base) if base else pathlib.Path.home() / ".config"
    return home / CONFIG_RELATIVE_PATH


def machine_config(path: pathlib.Path | None = None) -> dict[str, object]:
    """The per-machine config. Missing is `{}`; malformed is a `ConfigError`."""
    target = path if path is not None else machine_config_path()
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (IsADirectoryError, NotADirectoryError):
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"cannot read {target}: {error}") from None
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{target} is not valid JSON: {error}") from None
    if not isinstance(loaded, dict):
        raise ConfigError(f"{target} holds a {type(loaded).__name__}, not a JSON object")
    return loaded


def mode(root: pathlib.Path) -> str:
    """`full` (default), `minimal` or `guest`, from the local block's `mode:`."""
    value = local_block(root).get("mode", "").strip()
    if not value:
        return DEFAULT_MODE
    if value not in MODES:
        raise ConfigError(f"mode {value!r} is not one of {', '.join(MODES)}")
    return value


# --------------------------------------------------------------------------
# Work items: status derived from artifacts and git, never from stored state
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusReport:
    """A derived status plus every inconsistency found while deriving it."""

    status: str
    archived: bool
    inconsistencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkItem:
    """One work item directory, as the filesystem describes it."""

    path: pathlib.Path
    slug: str
    title: str
    status: str
    created: str
    branch: str
    archived: bool
    #: The frontmatter's `parked:` line verbatim, empty when the item is live.
    #: Written by whichever pass parked the item: `<date> age-sweep` from the
    #: 45-day sweep, `<date> bulk-park (D2)` from the one-time fleet-wide park.
    #: Read the value, do not assume the reason -- fleet-wide the split is 65
    #: age-sweep to 172 bulk-park. Set here and nowhere else --
    #: parked is a property of the item, never a row in a separate ledger.
    parked: str = ""
    inconsistencies: tuple[str, ...] = ()


def _is_archived(item_dir: pathlib.Path) -> bool:
    return ARCHIVE_DIR in item_dir.resolve().parts


def _read_prd(item_dir: pathlib.Path) -> tuple[dict[str, str], list[str]]:
    """The prd's frontmatter fields, and what went wrong reading them."""
    prd = item_dir / "prd.md"
    try:
        parsed = parse_frontmatter(prd.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}, [f"{prd} is missing or unreadable"]
    if parsed is None:
        return {}, [f"{prd} has no --- frontmatter block"]
    return parsed, []


def _status_report(
    item_dir: pathlib.Path, fields: dict[str, str], problems: list[str]
) -> StatusReport:
    archived = _is_archived(item_dir)
    prd = item_dir / "prd.md"
    if archived:
        return StatusReport("done", True, tuple(problems))

    declared = fields.get("status", "").strip()
    if declared not in ITEM_STATUSES:
        problems.append(
            f"{prd}: status {declared!r} is not one of {', '.join(ITEM_STATUSES)}"
        )
        return StatusReport("unknown", False, tuple(problems))
    if declared == "in_progress" and not fields.get("branch", "").strip():
        problems.append(f"{prd}: an in_progress item records the branch it lives on")
    return StatusReport(declared, False, tuple(problems))


def status_report(item_dir: pathlib.Path) -> StatusReport:
    """Derive a work item's status from its own artifacts.

    An item under `archive/` is `done` by virtue of where it lives -- the move
    is the record. Anything else states its status in `prd.md` frontmatter. A
    status that is missing, unknown, or contradicted by the rest of the
    frontmatter is reported as an inconsistency rather than raised: a lint rule
    is the place to fail, and this function is also called by tools that only
    want to show you the tree.
    """
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    return _status_report(item_dir, fields, problems)


def derive_status(item_dir: pathlib.Path) -> str:
    """The derived status alone; `unknown` when the artifacts do not say."""
    return status_report(item_dir).status


def work_item(item_dir: pathlib.Path) -> WorkItem:
    """Read one work item directory into a `WorkItem`, reading the prd once."""
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    report = _status_report(item_dir, fields, problems)
    name = item_dir.name
    return WorkItem(
        path=item_dir,
        slug=_DATE_PREFIX_RE.sub("", name),
        title=fields.get("title", ""),
        status=report.status,
        created=fields.get("created", ""),
        branch=fields.get("branch", ""),
        archived=report.archived,
        parked=fields.get("parked", "").strip(),
        inconsistencies=report.inconsistencies,
    )


def work_item_dirs(root: pathlib.Path, work_dir: str = WORK_DIR) -> list[pathlib.Path]:
    """Every work item directory, active and archived, from the filesystem."""
    work_root = pathlib.Path(root) / work_dir
    if not work_root.is_dir():
        return []
    found = [
        path for path in work_root.iterdir() if path.is_dir() and path.name != ARCHIVE_DIR
    ]
    archive = work_root / ARCHIVE_DIR
    if archive.is_dir():
        for month in archive.iterdir():
            if month.is_dir():
                found.extend(path for path in month.iterdir() if path.is_dir())
    return sorted(found)


def work_items(root: pathlib.Path, work_dir: str = WORK_DIR) -> list[WorkItem]:
    """Every work item, enumerated from the tree rather than from an index."""
    return [work_item(path) for path in work_item_dirs(root, work_dir)]


# --------------------------------------------------------------------------
# Entrypoints: the repo's own check commands, however it happens to spell them
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Detection:
    """What was detected and how, so a caller can explain itself."""

    source: str | None
    origin: pathlib.Path | None
    commands: dict[str, list[str]] = field(default_factory=dict)
    reason: str = ""


def _local_block_entrypoints(root: pathlib.Path) -> Detection | None:
    block = local_block(root)
    commands: dict[str, list[str]] = {}
    for name in CHECK_NAMES:
        raw = block.get(name, "").strip()
        if not raw:
            continue
        try:
            argv = shlex.split(raw)
        except ValueError as error:
            raise ConfigError(
                f"{LOCAL_FILE_NAME}: {name}: {raw!r} does not parse: {error}"
            ) from None
        if not argv:
            raise ConfigError(f"{LOCAL_FILE_NAME}: {name}: is empty")
        commands[name] = argv
    if not commands:
        return None
    return Detection(
        source="local-block",
        origin=local_block_path(root),
        commands=commands,
        reason=f"{LOCAL_FILE_NAME} declares {', '.join(commands)}",
    )


def _makefile_targets(path: pathlib.Path) -> set[str]:
    targets: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return targets
    for line in text.split("\n"):
        if not line or line[:1].isspace():
            continue
        match = _MAKE_TARGET_RE.match(line)
        if not match:
            continue
        for name in match.group("names").split():
            if name.startswith(".") or "%" in name or "$" in name:
                continue
            targets.add(name)
    return targets


def _makefile_entrypoints(root: pathlib.Path) -> Detection | None:
    for candidate in ("Makefile", "makefile", "GNUmakefile"):
        path = root / candidate
        if path.is_file():
            break
    else:
        return None
    targets = _makefile_targets(path)
    commands = {name: ["make", name] for name in CHECK_NAMES if name in targets}
    if not commands:
        return None
    return Detection(
        source="makefile",
        origin=path,
        commands=commands,
        reason=f"{path.name} defines {', '.join(commands)}",
    )


def _taskfile_tasks(path: pathlib.Path) -> list[str]:
    """Top-level task names under `tasks:`, read line-wise.

    A YAML parser is not stdlib, so this reads exactly the shape a Taskfile
    conventionally has: a `tasks:` mapping whose keys sit one indent in.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    names: list[str] = []
    indent: str | None = None
    inside = False
    for line in text.split("\n"):
        if not line.strip():
            continue
        if _TASKFILE_TASKS_RE.match(line):
            inside = True
            continue
        if not inside:
            continue
        if not line[:1].isspace():
            break
        match = _TASKFILE_ENTRY_RE.match(line)
        if not match:
            continue
        if indent is None:
            indent = match.group("indent")
        if match.group("indent") == indent:
            names.append(match.group("name"))
    return names


def _taskfile_entrypoints(root: pathlib.Path) -> Detection | None:
    for candidate in ("Taskfile.yml", "Taskfile.yaml"):
        path = root / candidate
        if path.is_file():
            break
    else:
        return None
    tasks = _taskfile_tasks(path)
    commands = {name: ["task", name] for name in CHECK_NAMES if name in tasks}
    if not commands:
        return None
    return Detection(
        source="taskfile",
        origin=path,
        commands=commands,
        reason=f"{path.name} defines {', '.join(commands)}",
    )


def _package_json_entrypoints(root: pathlib.Path) -> Detection | None:
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from None
    scripts = loaded.get("scripts") if isinstance(loaded, dict) else None
    if not isinstance(scripts, dict):
        return None
    commands = {name: ["npm", "run", name] for name in CHECK_NAMES if name in scripts}
    if not commands:
        return None
    return Detection(
        source="package.json",
        origin=path,
        commands=commands,
        reason=f"package.json scripts define {', '.join(commands)}",
    )


def _cargo_entrypoints(root: pathlib.Path) -> Detection | None:
    path = root / "Cargo.toml"
    if not path.is_file():
        return None
    return Detection(
        source="cargo",
        origin=path,
        commands={"check": ["cargo", "check"], "test": ["cargo", "test"]},
        reason="Cargo.toml: cargo check and cargo test",
    )


def _pyproject_entrypoints(root: pathlib.Path) -> Detection | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    return Detection(
        source="pyproject",
        origin=path,
        commands={"test": ["python3", "-m", "pytest"]},
        reason="pyproject.toml: python3 -m pytest",
    )


#: Autodetection order. The first probe that finds a runnable check wins; a
#: probe that finds its file but no usable target is not a hit, so a Makefile
#: with no check/test/lint target does not stop the search.
DETECTORS = (
    _local_block_entrypoints,
    _makefile_entrypoints,
    _taskfile_entrypoints,
    _package_json_entrypoints,
    _cargo_entrypoints,
    _pyproject_entrypoints,
)


def detect_entrypoints(root: pathlib.Path) -> Detection:
    """Resolve the repo's check commands, reporting which probe answered."""
    root = pathlib.Path(root)
    for detector in DETECTORS:
        found = detector(root)
        if found is not None:
            return found
    return Detection(source=None, origin=None, commands={}, reason="no check entrypoint detected")


def entrypoints(root: pathlib.Path) -> dict[str, list[str]]:
    """The repo-native check commands, keyed by name, in `CHECK_NAMES` order."""
    return detect_entrypoints(root).commands


# --------------------------------------------------------------------------
# Commit trailers: who wrote a change, said by the change itself
# --------------------------------------------------------------------------

#: The scopes that resolve to a commit range. Only these carry trailers.
TRAILER_SCOPES = ("branch", "pr")

#: `Authored-with: <entry>/<vendor>` on the commit that made the change, and
#: `Attributes: <sha> <entry>/<vendor>` on a later commit for one that was made
#: before the convention reached it. `sd-ship` and `sd attribute` write them.
AUTHORED_TRAILER = "Authored-with:"
ATTRIBUTES_TRAILER = "Attributes:"

#: What a commit a person wrote says. Spelled out rather than left implicit,
#: because the absence of a trailer has to keep meaning "nobody said" -- if an
#: untagged commit read as human-authored, an anthropic-written commit would
#: become reviewable by anthropic every time the trailer was forgotten.
HUMAN_AUTHOR = "human"


class TrailerError(Exception):
    """A commit that does not say, or says something unreadable."""


def commit_messages(root: pathlib.Path, base: str, head: str) -> list[tuple[str, str]]:
    """Each commit in the range as `(sha, message)`, newest first.

    Merges are not among them. A merge commit introduces no change of its
    own -- it records that two histories met -- so there is no work for it to
    say who wrote, and asking cost a real branch its review: merging `main` to
    catch up produced one untagged commit, and the whole range refused. The
    commits it brings in are already in the range, each answering for itself.
    """
    raw = git_output(["log", "--no-merges", "--format=%H%x1f%B%x1e", f"{base}..{head}"], root)
    if not raw:
        return []
    records = []
    for chunk in raw.split("\x1e"):
        if "\x1f" not in chunk:
            continue
        sha, _, message = chunk.strip().partition("\x1f")
        records.append((sha.strip(), message))
    return records


def attribution(root: pathlib.Path, base: str, head: str) -> dict[str, str]:
    """`<sha> -> <entry>/<vendor>` for every commit in the range that says.

    A commit says either by carrying its own `Authored-with:` or by being named
    in a later commit's `Attributes:`. Nothing takes a flag for this: a branch
    is a set of commits and each one answers for itself, because a single
    `--author` for the whole range is a claim about work the person making the
    claim may not have done.
    """
    own: dict[str, str] = {}
    claimed: dict[str, str] = {}
    commits = commit_messages(root, base, head)
    shas = [sha for sha, _ in commits]
    for sha, message in commits:
        # Git's trailer block -- the last paragraph -- and unindented, which is
        # what makes a trailer a trailer. Reading the whole message, stripped,
        # reads a trailer quoted inside a commit that was describing one.
        for line in message.rstrip().rsplit("\n\n", 1)[-1].splitlines():
            line = line.rstrip()
            if line.startswith(AUTHORED_TRAILER):
                own.setdefault(sha, line[len(AUTHORED_TRAILER) :].strip())
            elif line.startswith(ATTRIBUTES_TRAILER):
                parts = line[len(ATTRIBUTES_TRAILER) :].split()
                if len(parts) == 2:
                    named = _in_range(parts[0], shas)
                    if named:
                        claimed.setdefault(named, parts[1])
    # A commit's own trailer outranks a later commit's claim about it, and the
    # two dictionaries exist to make that ordering explicit. Merging in one
    # walk let a later `Attributes:` overwrite what a commit said about itself,
    # so relabelling an anthropic-authored commit as an openai one -- and
    # thereby buying it an anthropic reviewer -- took one line in a later
    # message. `Attributes:` is for commits that said nothing.
    return {**claimed, **own}


def _in_range(named: str, shas: list[str]) -> str:
    """The full sha `named` refers to, or "" if the range does not hold it.

    A claim about a commit outside `base..head` says nothing about the work
    under review, and keeping it bought a vendor a place in the author set --
    and so cost that vendor its seat as a reviewer -- for a commit nobody is
    reviewing. Three ways it happens, one answer for all of them: the named
    commit already merged, a rebase moved it, or the line is simply wrong.

    A prefix is enough, the way it is everywhere else in git, but only when it
    picks out one commit. Two matches name nothing in particular.
    """
    if len(named) < 7:
        return ""
    matches = [sha for sha in shas if sha.startswith(named)]
    return matches[0] if len(matches) == 1 else ""


def author_vendors(root: pathlib.Path, base: str, head: str) -> tuple[str, ...]:
    """The vendors this range was written with. Raises when a commit is silent."""
    said = attribution(root, base, head)
    untagged = [sha for sha, _ in commit_messages(root, base, head) if sha not in said]
    if untagged:
        raise TrailerError(
            f"{len(untagged)} commit(s) in {base}..{head} carry no "
            f"{AUTHORED_TRAILER} trailer, starting at {untagged[-1][:12]}. A "
            f"commit that does not say who wrote it cannot be reviewed by "
            f"somebody else on purpose. Record it with "
            f"`sd attribute {untagged[-1][:12]} <entry>`."
        )
    vendors = []
    for sha, value in said.items():
        if value == HUMAN_AUTHOR:
            continue
        entry, separator, vendor = value.partition("/")
        # Stripped and folded, because the comparison this feeds is an exact
        # `in` against the registry's vendor. `claude / anthropic` yielded
        # " anthropic", which matched no entry, so the author's own vendor
        # stayed on the chain and reviewed the branch it had written -- the
        # one thing the trailer exists to stop, failing open and in silence.
        entry, vendor = entry.strip(), vendor.strip().lower()
        if not separator or not entry or not vendor:
            raise TrailerError(
                f"{sha[:12]} says {AUTHORED_TRAILER} {value!r}, which is neither "
                f"{HUMAN_AUTHOR!r} nor an '<entry>/<vendor>' pair. A trailer that "
                f"cannot be read is not a weaker claim than one that is missing."
            )
        if vendor not in vendors:
            vendors.append(vendor)
    return tuple(vendors)


def attribution_value(name: str, registry: Any) -> str:
    """What a trailer says when it names `name`: `<entry>/<vendor>`, or `human`.

    The inverse of the parse in `author_vendors`, so the two cannot drift, and
    folding the vendor to lower case on the way out as well as on the way in,
    so the line `git log` shows is the string the independence check compares.

    Everything else refuses, because a value that does not survive the round
    trip is not read as a weaker claim -- it is read as *no* claim.
    `attribution` drops an `Attributes:` line that does not split into two
    fields, a commit with no claim keeps its vendor out of the author set, and
    the author's own vendor stays on the reviewer chain, open and in silence.
    """
    entry = name.strip()
    provider = registry.providers.get(entry)
    if entry == HUMAN_AUTHOR:
        if provider is not None:
            raise TrailerError(
                f"{HUMAN_AUTHOR!r} is what a commit a person wrote says, so it is "
                f"not a name a registry entry may take, and {registry.path} has "
                f"one. Its trailer would read as the operator and hide its vendor."
            )
        return HUMAN_AUTHOR
    if provider is None:
        known = ", ".join(sorted(registry.providers)) or "nothing"
        raise TrailerError(
            f"no registry entry named {entry!r} in {registry.path}, which holds "
            f"{known}. Name an entry the registry has, or {HUMAN_AUTHOR!r} bare: a "
            f"trailer nothing resolves records no vendor, and a range with no "
            f"vendor is one its own author may review."
        )
    vendor = provider.vendor.strip().lower()
    value = f"{entry}/{vendor}"
    if value.split() != [value] or "/" in entry or "/" in vendor or not vendor:
        raise TrailerError(
            f"entry {entry!r} carries vendor {provider.vendor!r} in {registry.path}, "
            f"and {value!r} is no '<entry>/<vendor>' pair a trailer can carry: a "
            f"space or a second slash makes the line unreadable, and an unreadable "
            f"claim is dropped rather than questioned. Fix the registry."
        )
    return value


def _own_trailer(root: pathlib.Path, sha: str) -> str:
    """Its own `Authored-with:` value, or "" -- last paragraph, unindented,
    `attribution`'s rule, so a commit that quotes a trailer stays repairable.
    """
    message = git_output(["log", "-1", "--format=%B", sha], root) or ""
    for line in message.rstrip().rsplit("\n\n", 1)[-1].splitlines():
        if line.rstrip().startswith(AUTHORED_TRAILER):
            return line.rstrip()[len(AUTHORED_TRAILER) :].strip()
    return ""


def _on_this_branch(root: pathlib.Path, ref: str) -> str:
    """`ref` as a full sha when it names one commit reachable from `HEAD`.

    A claim about a commit off this branch is a line its review never reads:
    written, reported as done, and dropped by `_in_range` just as quietly.
    """
    full = git_output(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], root)
    if not full:
        return ""
    return full if git_output(["merge-base", "--is-ancestor", full, "HEAD"], root) is not None else ""


def _covered(root: pathlib.Path, target: str) -> list[str]:
    """The commits `target` names that still need an author, newest first.

    Commits that already say are left alone rather than restated. After a
    rebase -- the one case that loses an attribution, since neither integration
    path rewrites a branch -- a range holds both the commits whose own trailer
    survived and the one whose claim named a hash that is gone, and a range
    form refusing that mixture could not repair it. A single commit that says
    is refused instead: its own trailer outranks any later claim about it.
    """
    if ".." not in target:
        full = _on_this_branch(root, target)
        if not full:
            raise TrailerError(f"{target!r} names no commit reachable from HEAD")
        if len((git_output(["rev-list", "--parents", "-n", "1", full], root) or "").split()) > 2:
            raise TrailerError(
                f"{full[:12]} is a merge, which wrote nothing to answer for; the "
                f"review skips merges and would skip this claim with them.")
        said = _own_trailer(root, full)
        if said:
            raise TrailerError(
                f"{full[:12]} already says {AUTHORED_TRAILER} {said!r}, which "
                f"outranks any later {ATTRIBUTES_TRAILER} claim about it."
            )
        return [full]
    base, _, head = target.partition("..")
    if not base or not head or ".." in head or not _on_this_branch(root, head):
        raise TrailerError(f"{target!r} is no `<from>..<to>` range ending on this branch")
    commits = [sha for sha, _ in commit_messages(root, base, head)]
    if not commits:
        raise TrailerError(
            f"no commit in {target} carries work to attribute: a merge introduces "
            f"no change of its own, and what it brought in answers for itself."
        )
    covered = [sha for sha in commits if not _own_trailer(root, sha)]
    if not covered:
        raise TrailerError(f"every commit in {target} already names its author")
    return covered


def attribute(
    root: pathlib.Path, target: str, name: str, registry: Any
) -> tuple[str, str, list[str]]:
    """Record `name` as the author of `target`, as one empty commit on `HEAD`.

    `target` is one commit or a `<from>..<to>` range. What lands is a single
    empty commit carrying an `Attributes:` line per repaired commit and its own
    `Authored-with: human`, because the operator made it and a repair that
    needs repairing is not one (C-40). Returns the new sha, the value written
    and the commits covered.

    A commit rather than a note: a notes ref is one mutable ref a repository
    shares, and two clones attributing different commits of one branch diverge
    on it. A commit is branch-local, pushes with the branch, and squashes away
    at the merge with everything else.
    """
    value = attribution_value(name, registry)
    covered = _covered(root, target)
    trailers = [f"{ATTRIBUTES_TRAILER} {sha} {value}" for sha in covered]
    trailers.append(f"{AUTHORED_TRAILER} {HUMAN_AUTHOR}")
    written = subprocess.run(  # fixed argv, no shell
        ["git", "commit", "--allow-empty", "--quiet",
         "-m", f"chore(attribution): {len(covered)} commit(s) written with {value}",
         "-m", "Recorded by the operator, after the fact, for commits that predate "
               "the trailer or lost it to a rewrite.",
         "-m", "\n".join(trailers)],
        cwd=str(root), capture_output=True, text=True,
        timeout=GIT_TIMEOUT_SECONDS, check=False,
    )
    if written.returncode != 0:
        raise TrailerError(
            f"git refused the attributing commit: "
            f"{(written.stderr or written.stdout).strip() or 'no reason given'}"
        )
    return git_output(["rev-parse", "HEAD"], root) or "", value, covered
