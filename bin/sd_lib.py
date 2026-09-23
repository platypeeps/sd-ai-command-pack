"""Shared detection and derivation for the sd-* tools under bin/.

Repository state is derived from Git, work artifacts, and check entrypoints.
Operator policy comes from the current machine configuration, read on demand.

Stdlib only, Python 3.10+, no network. A caller that cannot proceed gets a
`ConfigError` carrying a sentence a human can act on, never a traceback.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any, Callable, NamedTuple

LOCAL_FILE_NAME = "CLAUDE.local.md"
LOCAL_BLOCK_START = "<!-- SD-AI-COMMAND-PACK:LOCAL:START -->"
LOCAL_BLOCK_END = "<!-- SD-AI-COMMAND-PACK:LOCAL:END -->"

CONFIG_RELATIVE_PATH = pathlib.Path("sd-ai-command-pack") / "config.json"
#: The words `sd.copilot_review` takes, and what an unset key reads as. One
#: inventory: the pattern `sd config set` validates against is built from it,
#: and `sd-review` resolves the effective policy against the same tuple.
COPILOT_REVIEW_POLICIES = ("deep", "never", "always")
COPILOT_REVIEW_DEFAULT = "deep"


def copilot_policy(repository: bool | None, machine: str | None) -> tuple[str, str]:
    """The effective Copilot policy word and who said it.

    The repository's `.github/sd-review.json` wins when it named
    `copilot_review.automatic_deep` (`True` is `deep`, `False` is `never`);
    otherwise the machine's `sd.copilot_review`; otherwise the default, so a
    repository with no file gets one Copilot review on a deep-tier change and
    none on anything else (sd:1328). Pure on purpose: `sd-review` resolves it
    when it reports, and `sd-ship` resolves it again when it dispatches,
    against the setting as it stands then.
    """
    if repository is not None:
        return ("deep" if repository else "never"), "repository"
    if machine is not None:
        return machine, "machine config"
    return COPILOT_REVIEW_DEFAULT, "machine default"


def copilot_automatic(policy: str, tier: str, depth: int) -> bool:
    """Whether `policy` selects a Copilot review of a change routed to `tier`.

    `depth` is the tier's own reviewer count from the route plan: `always`
    means every reviewing tier, and a `skip` change nobody local reads is not
    sent to a remote reader either.
    """
    if policy == "deep":
        return tier == "deep"
    if policy == "always":
        return depth > 0
    return False
CORE_CONFIG = {
    "external_reviews": {"pattern": "configured|deny",
                         "description": "Standing private-code/context review authorization; unset uses local consent."},
    "assistant_merge": {"pattern": "controlled|ask",
                        "description": "Assistant merge permission for active controlled-repo work; unset asks, explicit wait wins."},
    "copilot_review": {"pattern": "|".join(COPILOT_REVIEW_POLICIES),
                       "description": "When sd-ship requests a Copilot review by itself: deep (unset reads deep) on deep-tier "
                                      "changes only, always on every reviewing tier, never on none; a repository's "
                                      ".github/sd-review.json copilot_review overrides it."},
}

#: `{current name: the name it was stored under before 1.1.0}`. A rename must
#: not orphan a grant a machine already recorded, and this checkout cannot
#: reach the machines that recorded one, so the old name is *read* rather than
#: migrated: nothing has to have run, and an operator who rolls back to 1.0.0
#: finds the file they left. `sd config set` and `unset` clear the old name as
#: they write, so the two never disagree.
#:
#: Deprecated, not permanent. 1.1.0 reads these; 1.2.0 removes this map and
#: the old names stop resolving. `sd config list sd` already names a stored
#: key the declarations dropped, which is how a machine still holding one
#: finds out.
RENAMED_CORE_KEYS = {"assistant_merge": "merge_authorization"}


def stored_name(stored: dict, key: str) -> str | None:
    """The name `stored` actually holds one declared key under, or `None`.

    The current name wins whenever it is present, so a file carrying both --
    written by 1.0.0 and then set by 1.1.0 before the clearing landed --
    reads the one the operator set last.
    """
    if key in stored:
        return key
    former = RENAMED_CORE_KEYS.get(key)
    return former if former is not None and former in stored else None

WORK_DIR = "docs/work"
ARCHIVE_DIR = "archive"

ITEM_STATUSES = ("planning", "ready", "in_progress", "done")
MODES = ("full", "minimal", "guest")
DEFAULT_MODE = "full"

#: The three names every repository is asked about, in the order they run.
CHECK_NAMES = ("check", "test", "lint")

#: Optional repository restriction, overriding standing operator review consent.
#: Shared by the installer, runtime reader, and workflow inventory check.
CONSENT_KEY = "reviewers"

GIT_TIMEOUT_SECONDS = 15
GH_TIMEOUT_SECONDS = 20

#: `WORKFLOW.md`'s three questions as the endpoints that ask them; `gh` fills
#: `{owner}` and `{repo}` from the checkout's origin, so no URL parser is needed
#: here. The last is *the* collaborator query criterion 11 asks `bin/` to hold
#: once: both gates reach it through `remote_permits_full` and neither restates.
VIEWER_QUERY = "user"
REPOSITORY_QUERY = "repos/{owner}/{repo}"
COLLABORATOR_QUERY = "repos/{owner}/{repo}/collaborators"
#: How one of those questions is put. Injected, so a test never asks the network.
Asker = Callable[[str, pathlib.Path], tuple[Any, str]]

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
    for key, raw in scalar_lines(text, comments=comments, label=label):
        value = raw.strip()
        if comments and value[:1] not in ('"', "'"):
            value = value.split("#", 1)[0].strip()
        fields[key] = _unquote(value)
    return fields


def scalar_lines(
    text: str, *, comments: bool, label: str = "block", strict: bool = True
) -> Iterator[tuple[str, str]]:
    """Each `key: value` line of `text` as (key, raw): the key stripped, the
    text after its first colon as written.

    This is the line splitting and key normalization `parse_scalars` reads
    by, on its own so a caller that needs the line rather than the value --
    the installer carrying an operator's lines across a refresh -- takes
    the same key from the same line. A second parser beside this one is
    how `check : make check` came to be a different key to the carry than
    to the reader, and a refresh reactivated the `check:` line the reader
    had already overridden (codex review of sd:1340). The last line for a
    key is the one `parse_scalars` keeps, under every spelling this accepts.

    With ``comments`` a line that is neither blank, a comment nor
    `key: value` is refused; ``strict=False`` skips it instead, for a caller
    that runs after the reader has already refused the block it is in.
    """
    for number, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if comments and stripped.startswith("#"):
            continue
        key, separator, raw = line.partition(":")
        if not separator:
            if comments and strict:
                raise ConfigError(f"{label} line {number}: {stripped!r} is not `key: value`")
            continue
        yield key.strip(), raw


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
    """Run one `git` command; None when git cannot answer."""
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


def sibling(module_name: str, filename: str):
    """Import a `bin/` tool that has no `.py` suffix, so callers can share it.

    Three callers is what moved it here: `bin/sd-status:97` had one copy and
    `bin/sd_skill.py` a second, and a third would have made copying the policy
    the policy. `spec_from_file_location` infers no loader for a suffixless
    file, so the `SourceFileLoader` is named explicitly.

    Deferred by every caller rather than imported at module load: `bin/sd`
    imports its verb modules for every verb it runs, and a sibling is only
    needed by the ones that talk to GitHub.
    """
    import importlib.machinery  # noqa: PLC0415 - only siblings need it
    import importlib.util  # noqa: PLC0415

    path = str(pathlib.Path(__file__).resolve().parent / filename)
    loader = importlib.machinery.SourceFileLoader(module_name, path)
    spec = importlib.util.spec_from_file_location(module_name, path, loader=loader)
    if spec is None:  # pragma: no cover - a bin/ layout this broken cannot run
        raise ConfigError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def git_output(args: list[str], root: pathlib.Path) -> str | None:
    """`git <args>` in `root`: stripped stdout, or None when git cannot answer.

    The public face of the same call the helpers below use, so a sibling
    tool needing one more `git` fact grows no second subprocess policy
    (timeout, no shell, failure-is-None). Most are reads; `delivered` fetches.
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

    Only a linked worktree gets its own `<common>/worktrees/<name>` git dir.
    A main checkout, a separated git directory (which `--separate-git-dir`
    can name `.git` beside any unrelated tree), a submodule and a bare clone
    all answer `--git-dir` with the common one, so its name settles nothing.
    """
    def path(flag: str) -> pathlib.Path | None:
        answer = _git(["rev-parse", flag], cwd=root)
        return (root / answer).resolve() if answer else None
    common, git_dir = path("--git-common-dir"), path("--git-dir")
    if common is None or git_dir is None or common.name != ".git":
        return root
    return common.parent if git_dir.parent == common / "worktrees" else root


# --------------------------------------------------------------------------
# Configuration: the per-repo local block and the per-machine config file
# --------------------------------------------------------------------------


def local_block_path(root: pathlib.Path) -> pathlib.Path:
    """Where `CLAUDE.local.md` lives for this worktree: in the main checkout."""
    return main_worktree_root(root) / LOCAL_FILE_NAME


def local_block_body(text: str, label: str = LOCAL_FILE_NAME) -> str | None:
    """The text between one well-formed marker pair; None when there is no block.

    The markers and the grammar are two checks, and this is the first alone:
    the installer reads the body with its own old prose taken out before the
    grammar sees it, so it needs the markers checked on their own. A marker
    fault is the operator's file and is refused here whichever caller asks.
    """
    start = text.find(LOCAL_BLOCK_START)
    if start == -1:
        if LOCAL_BLOCK_END in text:
            raise ConfigError(f"{label}: end marker without a start marker")
        return None
    if text.find(LOCAL_BLOCK_START, start + len(LOCAL_BLOCK_START)) != -1:
        raise ConfigError(f"{label}: duplicate start markers")
    end = text.find(LOCAL_BLOCK_END, start)
    if end == -1:
        raise ConfigError(f"{label}: start marker with no end marker")
    if text.find(LOCAL_BLOCK_END, end + len(LOCAL_BLOCK_END)) != -1:
        raise ConfigError(f"{label}: duplicate end markers")
    return text[start + len(LOCAL_BLOCK_START) : end]


def parse_local_block(text: str, label: str = LOCAL_FILE_NAME) -> dict[str, str]:
    """Extract the marked block's flat scalars. No block is an empty dict."""
    body = local_block_body(text, label)
    if body is None:
        return {}
    return parse_scalars(body, comments=True, label=label)


def local_block(root: pathlib.Path) -> dict[str, str]:
    """The repo's local configuration block; missing file or block is `{}`."""
    path = local_block_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if path.is_symlink():
            raise ConfigError(f"cannot read dangling local configuration link: {path}") from None
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from None
    return parse_local_block(text, str(path))


def machine_config_path(environ: dict[str, str] | None = None) -> pathlib.Path:
    """Read the supplied operator's XDG/HOME, or the current environment."""
    env = os.environ if environ is None else environ
    home = pathlib.Path(env.get("XDG_CONFIG_HOME") or pathlib.Path(env.get("HOME") or pathlib.Path.home()) / ".config")
    return home / CONFIG_RELATIVE_PATH


def core_setting(key: str, environ: dict[str, str] | None = None) -> str | None:
    """Validated standing user policy; absence grants no new permission."""
    config = machine_config(machine_config_path(environ)).get("config", {})
    mine = config.get("sd", {}) if isinstance(config, dict) else None
    if not isinstance(mine, dict):
        raise ConfigError("machine config config.sd must be an object")
    name = stored_name(mine, key)
    if name is None:
        return None
    value = mine[name]
    if not isinstance(value, str) or not re.fullmatch(CORE_CONFIG[key]["pattern"], value):
        raise ConfigError(f"invalid sd.{key} policy")
    return value


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


@dataclass(frozen=True)
class RemoteAnswer:
    """What the remote said when asked whether this run may be `full`. Not a
    bool: the demotion note `sd-ship` writes on the item, through
    `demotion_note`, and the merge refusal `sd_ship_remote.GitHub.owned`
    raises each name *which* answer said no, and a bool throws that away at
    that moment. `sd-status` prints the reason beside the word, through
    `mode_answer`; `mode` is for the readers that want the word alone."""

    #: Three yeses, or the no-remote / no-git case. Never reached from an error.
    full: bool
    #: False when the question could not be put at all -- no `gh`, no network, a
    #: refusing remote. It changes the sentence, never the outcome.
    answered: bool
    #: Empty when `full`; otherwise the sentence naming what said no.
    reason: str = ""


def gh_api(endpoint: str, root: pathlib.Path) -> tuple[Any, str]:
    """One read-only `gh api` call: `(payload, error-sentence)`, never raising.
    `gh` is a process and not an import, so stdlib-only holds; it is also the
    seam tests replace, so no test in this repository touches the network."""
    try:
        completed = subprocess.run(  # fixed argv, no shell
            ["gh", "api", endpoint],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"gh could not be run: {error}"
    if completed.returncode != 0:
        said = (completed.stderr or completed.stdout).strip().splitlines()
        return None, said[0] if said else f"gh api {endpoint} exited {completed.returncode}"
    try:
        return json.loads(completed.stdout or "null"), ""
    except json.JSONDecodeError as error:
        return None, f"gh api {endpoint} did not answer in JSON: {error}"


def remote_permits_full(root: pathlib.Path, *, ask: Asker = gh_api) -> RemoteAnswer:
    """Ask the remote the three questions of `WORKFLOW.md`, fresh, every call.

    `full` comes back on three yeses -- you administer it, it is not a fork,
    nobody else may push -- and for a root with no remote or no git at all,
    where there is no one to expose anything to. Never from an error path: a
    question that could not be put is not a permission that was granted, so an
    unanswerable query is `guest` with `answered` false. Nothing is cached; the
    questions are asked again before every artifact write and every push.
    """
    # Case 6, decided on its own rather than caught out of the remote lookup.
    if not (root / ".git").exists():
        return RemoteAnswer(full=True, answered=True)
    # A `.git` git itself cannot read is not the no-git case: it is no answer.
    if git_output(["rev-parse", "--is-inside-work-tree"], root) != "true":
        return RemoteAnswer(False, False, f"git could not be asked about {root}")
    if not git_output(["remote", "get-url", "origin"], root):
        return RemoteAnswer(full=True, answered=True)

    viewer, error = ask(VIEWER_QUERY, root)
    login = viewer.get("login") if isinstance(viewer, dict) else None
    if not login:
        return RemoteAnswer(False, False, f"the remote did not say who you are: {error or 'no login'}")

    repo, error = ask(REPOSITORY_QUERY, root)
    rights = repo.get("permissions") if isinstance(repo, dict) else None
    if not isinstance(repo, dict) or not isinstance(rights, dict):
        return RemoteAnswer(False, False, f"the remote did not say what you may do: {error or 'no permissions'}")
    name = str(repo.get("full_name") or "the remote")
    if not rights.get("admin"):
        return RemoteAnswer(False, True, f"you do not administer {name}")
    if repo.get("fork"):
        parent = repo.get("parent")
        upstream = parent.get("full_name") if isinstance(parent, dict) else None
        return RemoteAnswer(False, True, f"{name} is a fork of {upstream or 'another repository'}")

    people, error = ask(COLLABORATOR_QUERY, root)
    if not isinstance(people, list):
        return RemoteAnswer(False, False, f"the remote did not list who may push to {name}: {error or 'no list'}")
    # Parsing and filtering are separate questions, and doing them in one pass
    # fails open: an entry dropped for being unreadable leaves `others` empty,
    # and an empty `others` is one of only three places `full` is returned. So
    # "nobody I could parse" would arrive as "nobody else may push". Every entry
    # is read first, and the first one that cannot be read is no answer.
    others: list[str] = []
    for index, person in enumerate(people):
        rights = person.get("permissions") if isinstance(person, dict) else None
        who = str(person.get("login") or "") if isinstance(person, dict) else ""
        if not who or not isinstance(rights, dict):
            return RemoteAnswer(
                False, False, f"the list of who may push to {name} has an entry ({index}) this cannot read"
            )
        if who != login and rights.get("push"):
            others.append(who)
    if others:
        return RemoteAnswer(False, True, f"{name} lets {', '.join(sorted(others))} push too")
    return RemoteAnswer(full=True, answered=True)


#: The written modes detection leaves exactly as they are. Both already write
#: less than `full` does, so a remote's `no` has nothing to take away from
#: either: there is no demotion to record and no question worth asking.
SETTLED_MODES = ("guest", "minimal")


def written_mode(root: pathlib.Path) -> str:
    """The `mode:` line as the operator wrote it, validated. No line is `""`.

    Detection's input, before any remote is asked. The validation lives here
    rather than at each reader, so a `mode:` word that is not a mode is named
    wherever it is first read instead of quietly failing to match a list.
    """
    value = local_block(root).get("mode", "").strip()
    if value and value not in MODES:
        raise ConfigError(f"mode {value!r} is not one of {', '.join(MODES)}")
    return value


def remote_can_lower(written: str) -> bool:
    """Whether a remote's answer can lower `written`, the mode line as written.

    The one statement of that rule, for the two readers that need it.
    `mode_answer` below asks the remote nothing when this is false and hands
    back a `None` demotion. `sd-ship`'s merge-time ownership check reaches
    `remote_permits_full` by the other route, through
    `sd_ship_remote.GitHub.owned`, so the `None` never arrives there and it
    has to put the question itself before it writes a demotion note -- and a
    second copy of the rule at that call site is a second place for it to
    drift. A repository written down as `guest` or `minimal` was lowered by
    its operator, not by the remote, and a `no` about it demotes nothing.
    """
    return written not in SETTLED_MODES


def mode_answer(root: pathlib.Path, *, ask: Asker = gh_api) -> tuple[str, RemoteAnswer | None]:
    """The resolved mode and, when the remote lowered it, the answer that did.

    Detection is a ceiling and never a floor. A written `full`, and no line at
    all, are both offered to `remote_permits_full` and come back `guest` unless
    the remote says yes three times. A written `guest` stays `guest`. A written
    `minimal` stays `minimal`: it is set by hand, detection's six cases never
    produce it, and it already writes no artifacts anywhere -- so rewriting it
    to `guest`, which puts a triad on a fork's branch, would raise exposure
    rather than lower it, the one thing detection is forbidden to do.

    The second value is the demotion, or None when nothing was lowered: a
    written `guest` or `minimal` asks the remote nothing, and a `full` the
    remote confirmed was not lowered. `sd-ship` writes that answer on the item
    as the demotion note, so the reason travels with the item and not only
    with the refusal that printed it.
    """
    value = written_mode(root)
    if not remote_can_lower(value):
        return value, None
    answer = remote_permits_full(root, ask=ask)
    return (DEFAULT_MODE, None) if answer.full else ("guest", answer)


def mode(root: pathlib.Path, *, ask: Asker = gh_api) -> str:
    """The resolved mode: the local block's `mode:` line, lowered by detection.

    `mode_answer` with the demotion dropped, for the readers that need only
    the word: `sd-suggest`, the GitHub setup, and `guest_artifact_refusal`
    below. Not `sd-status`, which prints the reason beside the word and so
    reads `mode_answer` itself.
    """
    return mode_answer(root, ask=ask)[0]


#: The kind of the demotion note. A comment, not a decision: nobody decided
#: anything; the remote answered differently from what the line says.
DEMOTION_NOTE_KIND = "comment"


def demotion_note(repository: str, answer: RemoteAnswer) -> tuple[str, str]:
    """The note `sd-ship` writes on an item when `repository` lowered its mode.

    Returns `(marker, body)`. The marker is the body's first line, and
    `demotion_note_key` below turns it into the idempotence key: one note per
    item and remote, however many runs the remote lowers, so a second refusal
    for the same item on the same remote finds it and writes nothing. The
    marker is not itself the key -- it is built from the repository name, and
    one name prefixes another often enough that a bare prefix match reads the
    wrong remote's note. The body names which answer said no,
    as `RemoteAnswer` keeps it, and what the operator is left holding: the
    written line stays, and the mode is `full` again the day the remote says
    yes, with no edit to the line.
    """
    marker = f"Mode demoted to guest on {repository}"
    said = ("the remote answered: " if answer.answered else "the remote could not be asked: ") + (
        answer.reason or "no reason was given"
    )
    body = (
        f"{marker}\n{said}. The written mode stays as it is: detection is a ceiling, and the next run "
        "is full again once the remote says yes to all three questions. Planning artifacts this branch "
        "carries under docs/work/, docs/spec/ or docs/decisions/ were not pushed to that remote; what is "
        "already in its shared tree from before the answer changed is yours to move."
    )
    return marker, body


def demotion_note_key(marker: str) -> str:
    """The idempotence key for `marker`: the marker line, terminator included.

    `sd-ship` finds an existing note by matching the head of its body, and the
    bare marker is the wrong thing to match: markers are built from repository
    names, so one marker is a prefix of another whenever one name is a prefix
    of another -- `sven/thing` of `sven/thing-two`, which is what a rename, a
    move between owners, or a sibling fork looks like. Matched bare, the
    longer name's note answers for the shorter name and the shorter name's
    demotion is never written down: the remote that is actually refusing the
    push leaves nothing on the item, and the note that is there names some
    other remote. The terminator ends the name, and no repository name carries
    a newline, so one key matches one marker and no other.
    """
    return marker + "\n"



# --------------------------------------------------------------------------
# Work items: status derived from artifacts and git, never from stored state
# --------------------------------------------------------------------------


#: The tracked marker the retire commit writes beside the lines it removes:
#: `docs/work/.status-source`, one word. It travels in git, so a checkout with
#: no database still knows which question to ask. **No marker is `file`**, and
#: `file` is the path every reader took before rows existed -- the same path,
#: not a new one that happens to agree with it.
STATUS_MARKER = ".status-source"
FROM_FILE, FROM_ROW = "file", "row"

#: How `sd_db` keys an item row. Both halves are read out of
#: `sd_db/sources/docs_work.py` rather than guessed: `source` is the string
#: below and `external_id` is `<registered checkout>::docs/work/<item>/prd.md`.
#: The pair is that table's unique index.
ITEM_ROW_SOURCE = "docs/work"

#: The six words a row may carry, two more than a `status:` line ever said.
#: `ready_to_send` and `blocked` are states the file vocabulary had no word
#: for; they pass through rather than being folded into one of the four,
#: because folding is how `blocked` would become workable.
ROW_STATUSES = ("planning", "ready", "in_progress", "ready_to_send", "blocked", "done")


@dataclass(frozen=True)
class StatusReport:
    """A derived status plus every inconsistency found while deriving it."""

    status: str
    archived: bool
    inconsistencies: tuple[str, ...] = ()
    #: The latest timestamp the database carries for this item, empty when
    #: there is no database, no row for it, or no readable stamp. Attached by
    #: `_reported`, which is the one place holding an open `Statuses`.
    activity: str = ""


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
    inconsistencies: tuple[str, ...] = ()
    #: When the database last recorded anything against this item -- its row's
    #: `updated_at` or the newest of its notes, whichever is later. Empty on a
    #: checkout with no database, which is an absence of evidence and never a
    #: statement that nothing happened. Read by the aging basis,
    #: `last_active` below, and by nothing that decides a status.
    activity: str = ""


def status_marker(root: pathlib.Path, work_dir: str = WORK_DIR) -> tuple[str, str]:
    """Where this checkout's item statuses come from: `(word, problem)`.

    No marker at all is `file`. A marker that is present and says something
    this cannot read comes back as no word and a sentence, and deliberately
    *not* as `file`: the marker exists only on a checkout whose `status:`
    lines have been removed, so falling back to the line there is answering
    from a line that is not in the file. Every item is then `unknown` with
    the marker named, which is the loud form of the same finding.
    """
    path = pathlib.Path(root) / work_dir / STATUS_MARKER
    try:
        said = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return FROM_FILE, ""
    except (OSError, UnicodeDecodeError) as error:
        return "", f"{path} cannot be read: {error}"
    if said in (FROM_FILE, FROM_ROW):
        return said, ""
    return "", f"{path} says {said!r}, which is neither {FROM_FILE!r} nor {FROM_ROW!r}"


def external_id(root: pathlib.Path | str, item_dir: pathlib.Path) -> str:
    """One item's row key. A writer needs it and no read connection to get it."""
    return (f"{main_worktree_root(pathlib.Path(root).resolve())}::"
            f"{WORK_DIR}/{item_dir.name}/prd.md")


def registered_base(root: pathlib.Path | str, sd_db: Any, connection: Any) -> str:
    """The registered checkout this one is, spelled as the `repo` table spells it.

    Rows are keyed by the registered path, and a runner clone is never at
    that path: it carries the same files under `/Volumes/sd-work/...` with
    the same `origin`. `sd work register` already resolves such a checkout
    to the registered repository through `sd_db.repos.registered_for` --
    the path when the path is itself registered, else the origin, else the
    checkout itself -- so a clone could register a folder and then not read
    the row it made (sd:981). This is the one resolver the readers share;
    the rule stays the library's, and the pack does not restate it.

    The main worktree root first, the library second: a linked worktree of
    the registered checkout resolves at one indexed lookup with the origin
    read but unused, as before. A library without `registered_for` keeps
    the path-keyed answer rather than raising; that is an older machine,
    not a second path anybody runs on purpose.
    """
    here = pathlib.Path(root).resolve()
    base = str(main_worktree_root(here))
    registered_for = getattr(getattr(sd_db, "repos", None), "registered_for", None)
    if registered_for is None:
        return base
    origin = git_output(["remote", "get-url", "origin"], here)
    return str(registered_for(connection, base, origin or None))


def _provisioned_library_paths() -> list[str]:
    """Where `make setup` put `sd_db`, for an interpreter that did not find it.

    The pack provisions the library into its own virtualenv and every
    entrypoint runs under `#!/usr/bin/env python3`, so on a machine whose
    `python3` is not that virtualenv the import fails and git answers in the
    row's place -- silently, and differently. The run that found this reported
    `in_progress` for an item whose row says `done`.

    The library is pure Python and its floor is 3.11, so the interpreter that
    found no `sd_db` can read the *pinned* one off the virtualenv it was
    installed into. That is the same copy `make setup` chose, not a second
    source: reading the checkout's source instead would answer from something
    nothing pinned.

    Ordered by version number and newest first, because a rebuilt virtualenv
    can leave two `lib/python*` directories behind and the first path on
    `sys.path` is the one that answers. Sorting the names compares text, and
    text agrees with the numbers only by luck: it happens to be right for
    `python3.9` against `python3.13`, and wrong for `python3.1` against
    `python3.10`, where the shorter name is a prefix of the longer and sorts
    first. Empty when there is no provisioned copy to offer.
    """
    root = pathlib.Path(__file__).resolve().parent.parent
    found = []
    for path in root.glob(".venv/lib/python*/site-packages"):
        if not (path / "sd_db").is_dir():
            continue
        version = tuple(int(part) for part in re.findall(r"\d+", path.parent.name))
        found.append((version, str(path)))
    return [path for _, path in sorted(found, reverse=True)]


class Imported(NamedTuple):
    """What one entrypoint's attempt to reach `sd_db` came to.

    Three fields because "did it work" is not the whole question. `problem`
    is the sentence to show; `provisioned` says which of the two faults
    produced it -- a path when the pack's own copy was there and would not
    import, empty when there was no copy to try. A caller with a canned
    remedy of its own needs that distinction, and the alternative is matching
    on the wording of the sentences below, which is a coupling that breaks
    the first time somebody rewords one. Both are meaningful only when
    `module` is `None`.
    """

    module: Any
    problem: str
    provisioned: str


def import_sd_db() -> Imported:
    """`sd_db` for an entrypoint running under whatever `python3` is on PATH.

    The one place the two tries live. `_provisioned_library_paths` above says
    why there has to be a second try; this says why every caller has to make
    it. No `python3` on a developer's PATH carries `sd_db` -- the pack
    provisions it into its own virtualenv and every entrypoint starts
    `#!/usr/bin/env python3` -- so an entrypoint that tries once and gives up
    is not degraded on an unusual machine, it is broken on all of them. That
    is sd:745: `bin/sd-ship` refused every verb with "install matching
    sd_db" while `bin/sd`, which had this fallback, answered fine, and the
    only difference between the two was a copy of these six lines.

    Returns the module, or `None` and the problem, so each caller still
    decides for itself whether an absent library is a refusal, a fall back to
    the revision history, or a field on a report. The two problem sentences
    stay apart for the reason the retry below states: a provisioned copy that
    will not import is not a machine without the library, and one message over
    both sends half its readers to the wrong remedy.
    """
    try:
        import sd_db  # noqa: PLC0415 - `make setup` provisions it; absent is a state
    except ImportError as error:
        offered = _provisioned_library_paths()
        # Prepended, and that is the difference between the provisioned copy
        # answering and an incompatible one keeping the answer. The retry
        # only runs because the first try failed, and it can fail two ways:
        # nothing on `sys.path` held an `sd_db`, or something earlier on it
        # held one that raised. Appended, the pack's copy sits behind that
        # second one, the finder walks the path in order and reaches the same
        # incompatible package again, and the sentence below then names the
        # provisioned path as the thing that would not import -- about a copy
        # that was never tried. At the front, the copy `make setup` chose is
        # the copy this run gets, and any error reported is that copy's own.
        #
        # No deliberate `PYTHONPATH` is overridden by this. An `sd_db` a
        # developer put there that imports has already answered the first try
        # and never reaches here; the only thing that loses is one that
        # raised. Ordering among the offered paths is preserved -- newest
        # interpreter first, which is `_provisioned_library_paths`'s contract
        # and pointless anywhere but the front of the list.
        #
        # What is prepended is a whole `site-packages`, so in principle it
        # shadows more than `sd_db`. In this pack it shadows nothing -- but
        # not for the reason the first version of this comment gave, which
        # said every import in `bin/` and `dashboard/` is stdlib, a sibling
        # module, or `sd_db` itself. An AST scan of both trees finds one
        # exception: `bin/sd_research_render.py:51 import markdown`.
        #
        # The safety survives on other grounds. Python-Markdown is not
        # provisioned into the pack's virtualenv, so the `site-packages` this
        # prepends has no `markdown` in it to shadow anything with, and that
        # module's only consumer, `bin/sd-research-kit`, never reaches this
        # function. So a third-party dependency arriving in either tree is
        # not by itself the thing to watch for -- one that is also
        # PROVISIONED is, and that is what would make this worth narrowing to
        # the one module it is for.
        for path in offered:
            if path in sys.path:
                sys.path.remove(path)
        sys.path[:0] = offered
        try:
            import sd_db  # noqa: PLC0415 - the provisioned copy, second and last try
        except ImportError as retry:
            # Two faults, two sentences. A provisioned copy that will not
            # import is not a machine without the library, and saying "not
            # installed" over the top of one sends the reader to `make
            # setup` for a package that is already there. Where nothing
            # was offered, the first error is the only one there is.
            return Imported(None, (
                f"sd_db is provisioned at {offered[0]} but will not import: {retry}"
                if offered else f"sd_db is not installed here: {error}"
            ), offered[0] if offered else "")
    return Imported(sd_db, "", "")


class Rows:
    """This checkout's item rows, read through `sd_db` and through nothing else.

    Opened once for an enumeration rather than once per item: sixty-four
    items would otherwise open the database sixty-four times to draw one
    `sd-status`. `sqlite3` is not imported here and never will be -- item B's
    requirement 2 is that the library owns every connection.

    `opened` is the distinction this class exists to keep. A machine with no
    database is the designed database-free case and asks git instead; a
    machine that *has* one and holds no row for an item has lost that item,
    and reading "no row" as "so the item is open" is how delivered work gets
    picked up and done a second time.

    `installed` is the third state, and it was kept and then thrown away.
    `sd_db` lives in this pack's virtualenv, so one machine has two answers:
    under `.venv/bin/python` the row decides, under the system `python3` the
    import fails and git decides, and until this attribute was read the two
    printed different words for the same item with nothing to say which had
    run. That is how an item whose row has said `planning` since it was opened
    got reported `in_progress`.
    """

    def __init__(self, root: pathlib.Path) -> None:
        # Rows are keyed by the registered checkout, which for a linked
        # worktree is the main one: the migration enumerates the `repo` table
        # and a worktree was never added to it.
        self.base = str(main_worktree_root(pathlib.Path(root).resolve()))
        self.opened = False
        # Two absences, and they are not the same absence. `installed` is
        # whether this interpreter can import the library at all; `opened` is
        # whether it found a database to read. A library that says there is no
        # database is the designed database-free case. A library that is not
        # here has said nothing, and the answer that follows came from a
        # different source than the marker named.
        self.installed = False
        self.problem = ""
        self._connection: Any = None
        self._read: Any = None
        self._artifact_read: Any = None
        self._completion_read: Any = None
        self._notes_read: Any = None
        self._id_read: Any = None
        imported = import_sd_db()
        self.problem = imported.problem
        if imported.module is None:
            return
        sd_db = imported.module
        self.installed = True
        try:
            self._connection = sd_db.connect(write=False)
        except Exception as error:  # no file, or a schema this cannot read
            self.problem = f"sd_db could not open the database: {error}"
            return
        # Only now, with a database to ask: the path-keyed base above is the
        # answer for a machine with nothing to read, and this is the one the
        # rows were written under -- for a runner clone, the registered
        # checkout it is a clone of, not the path it stands at (sd:981).
        self.base = registered_base(root, sd_db, self._connection)
        self._read = sd_db.writes.item_by_external
        try:
            from sd_db.progress import completion_record, item_for_artifact
        except ImportError:
            pass  # Older installations retain their original identity reader.
        else:
            self._artifact_read = item_for_artifact
            self._completion_read = completion_record
        try:
            # Optional, like the two above: an older installation without it
            # reports what the row says and nothing the notes say.
            from sd_db.reads import item_notes  # noqa: PLC0415
        except ImportError:
            pass  # An installation without it reports row activity alone.
        else:
            self._notes_read = item_notes
        try:
            from sd_db.reads import item_by_id  # noqa: PLC0415
        except ImportError:
            pass  # A folder keyed `item: sd:<id>` then reads as before the key.
        else:
            self._id_read = item_by_id
        self.opened = True

    def external_id(self, item_dir: pathlib.Path) -> str:
        """The row's key, off the base this instance already resolved."""
        return f"{self.base}::{WORK_DIR}/{item_dir.name}/prd.md"

    def status(self, item_dir: pathlib.Path) -> tuple[str, str]:
        """`(word, problem)` for one item; both empty means no database."""
        if not self.opened:
            return "", ""
        identity = self.external_id(item_dir)
        try:
            row = self.item(item_dir)
        except Exception as error:
            return "", f"the row for {identity} could not be read: {error}"
        if row is None:
            _, trouble = named_row(item_dir, self._connection, self._id_read)
            return "", trouble or f"the database holds no {ITEM_ROW_SOURCE} row for {identity}"
        said = str(row["status"] or "").strip()
        if said not in ROW_STATUSES:
            return "", (f"the row for {identity} says status {said!r}, which is not "
                        f"one of {', '.join(ROW_STATUSES)}")
        return said, ""

    def item(self, item_dir: pathlib.Path) -> Any:
        """The row for one folder: by its path, else the one its `item:` key names."""
        if self._artifact_read is not None:
            relative = (item_dir / "prd.md").relative_to(_root_of(item_dir)).as_posix()
            row = self._artifact_read(self._connection, self.base, relative)
        else:
            row = self._read(self._connection, ITEM_ROW_SOURCE, self.external_id(item_dir))
        if row is not None:
            return row
        return named_row(item_dir, self._connection, self._id_read)[0]

    def activity(self, item_dir: pathlib.Path) -> str:
        """The latest stamp this item's row or any of its notes carries.

        **`updated_at` is not the answer on its own.** `sd_db.writes.add_note`
        inserts the note and leaves the item row alone, so a decision recorded
        against an item moves nothing on it. Measured on item 492, whose
        `comment` note stands four and a half hours after an `updated_at` that
        still equals `created_at`. Aging on the row alone would therefore call
        an item nobody has touched and an item triaged this morning the same
        age, which is the defect `idle-planning` was reported for.

        Empty for every absence -- no database, no row, no readable stamp --
        because a caller that cannot distinguish them would still be wrong in
        only one direction: an absent stamp never *lowers* an age, so the
        answer degrades to the item's own date rather than to silence.
        """
        if not self.opened:
            return ""
        try:
            row = self.item(item_dir)
        except Exception:  # noqa: BLE001 - a read that failed said nothing
            return ""
        if row is None:
            return ""
        stamps = [str(row["updated_at"] or "")]
        if self._notes_read is not None:
            try:
                stamps += [
                    str(note["timestamp"] or "")
                    for note in self._notes_read(self._connection, int(row["id"]))
                ]
            except Exception:  # noqa: BLE001 - notes are evidence, not a gate
                pass
        return max((stamp for stamp in stamps if stamp), default="")

    def completed(self, item_dir: pathlib.Path) -> bool:
        if self._completion_read is None:
            return False
        row = self.item(item_dir)
        return row is not None and self._completion_read(row) is not None

    def identity(self, item_dir: pathlib.Path) -> str:
        """`sd:<id>` for this folder's row, or `""` when no row answers.

        The spelling every writer in the pack uses: `bin/sd-ship` puts
        `Delivers: sd:<id>` on the squash and `sd work deliver` refuses a
        commit that carries anything else. A reader that asks git for the
        folder's name asks for a string nothing writes.
        """
        if not self.opened:
            return ""
        try:
            row = self.item(item_dir)
        except Exception:  # noqa: BLE001 - a read that failed named nothing
            return ""
        return f"sd:{row['id']}" if row is not None else ""

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        self._connection, self._read, self.opened = None, None, False


@dataclass
class Statuses:
    """One checkout's answer to "where does a status come from", resolved once.

    The marker is a property of the checkout and not of the item, so reading
    it per item puts the same question sixty-four times; the database is
    opened once too, and closed by whoever opened it.
    """

    root: pathlib.Path
    source: str
    problem: str = ""
    rows: Rows | None = None

    @classmethod
    def of(cls, root: pathlib.Path | str, work_dir: str = WORK_DIR) -> "Statuses":
        root = pathlib.Path(root)
        source, problem = status_marker(root, work_dir)
        return cls(root, source, problem, Rows(root) if source == FROM_ROW else None)

    def close(self) -> None:
        if self.rows is not None:
            self.rows.close()


def _root_of(item_dir: pathlib.Path) -> pathlib.Path:
    """The repository root an item sits in, from its own path and no git call.

    `<root>/docs/work/<item>`, or `<root>/docs/work/archive/<month>/<item>`
    two levels deeper. Derived rather than asked, so reading one directory
    stays as cheap as it was before there was a marker to find.
    """
    root = item_dir.resolve()
    for _ in range(5 if root.parent.parent.name == ARCHIVE_DIR else 3):
        root = root.parent
    return root


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


def _from_git(
    root: pathlib.Path,
    item_dir: pathlib.Path,
    prd: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
) -> StatusReport:
    """What a checkout with no database derives once the marker is present.

    `yes` is `done`. `unknown` is emphatically not `no`: a shallow clone and
    an unreachable remote cannot see the trailer, and reading either as "not
    delivered" hands finished work back to the next reader that picks it.
    What the retire left behind says which kind of open the rest are -- an
    item recording the branch it lives on is being worked, one that records
    none is still being planned.
    """
    answer = delivered(root, item_dir.name)
    if answer == YES:
        return StatusReport("done", False, tuple(problems))
    if answer == UNKNOWN:
        problems.append(
            f"{prd}: this checkout cannot see whether {item_dir.name} was "
            f"delivered; run `{answer.repair}`"
        )
        return StatusReport("unknown", False, tuple(problems))
    branch = fields.get("branch", "").strip()
    return StatusReport("in_progress" if branch else "planning", False, tuple(problems))


def _from_row(
    item_dir: pathlib.Path,
    prd: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
    statuses: "Statuses",
) -> StatusReport:
    """The status the row says, and the two things it says about the tree.

    *Stale*: the item's `status:` line survived the retire -- on a worktree
    kept across it, on a branch that still carries the line -- and says
    something the row does not. What is checked is what the line says, not
    that there is one: a line that agrees is a leftover for the lint to fail
    on, and calling it stale would report a disagreement that is not there.

    *Unmarked*: the row is `done` and no commit carries a closing trailer for
    the item, so every database-free checkout goes on picking it. `delivered`
    is the one question asked about that, here as everywhere else.
    """
    said, trouble = statuses.rows.status(item_dir) if statuses.rows else ("", "")
    if trouble:
        problems.append(f"{prd}: {trouble}")
        return StatusReport("unknown", False, tuple(problems))
    if not said:
        # Git answers, as it does for any checkout with no database -- but the
        # marker said the row was the authority, so a fall-through has to be
        # audible. Only the not-installed case is named: a library that opened
        # and found no database has answered the question, and saying so on
        # every item of a database-free checkout would be noise about the
        # designed path.
        if statuses.rows is not None and not statuses.rows.installed:
            problems.append(
                f"{prd}: {statuses.rows.problem}, so this status came from git "
                f"and not from the row this checkout's marker names"
            )
        return _from_git(statuses.root, item_dir, prd, fields, problems)
    line = fields.get("status", "").strip()
    if line and line != said:
        problems.append(
            f"{prd}: its `status:` line says {line!r} where the row says {said!r}; "
            f"the line is stale"
        )
    recorded = statuses.rows is not None and statuses.rows.completed(item_dir)
    # Both spellings, because both are written. `sd-ship` writes
    # `Delivers: sd:<id>` and `sd work deliver` accepts nothing else, so the
    # id is what a checkout holding the row must ask for; asking by the folder
    # name alone asked for a string no writer emits, and the clause could
    # never clear -- permanently false on any row a completion record cannot
    # reach, such as a `followup` row, which `sd work relink` refuses to give
    # a path. The folder name stays beside it: `main` carries two trailers in
    # that form, and it is the only spelling a database-free checkout can
    # resolve, which is why `_from_git` asks by it.
    wanted = tuple(dict.fromkeys(
        name for name in
        ((statuses.rows.identity(item_dir) if statuses.rows else ""), item_dir.name)
        if name
    ))
    if said == "done" and not recorded and delivered(statuses.root, wanted) != YES:
        carries = " or ".join(f"{DELIVERS_TRAILER} {name}" for name in wanted)
        problems.append(
            f"{prd}: the row is done and no commit carries {carries}, nor the "
            f"same value after {CLOSES_TRAILER}; the item is unmarked"
        )
    return StatusReport(said, False, tuple(problems))


def _status_report(
    item_dir: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
    statuses: "Statuses",
) -> StatusReport:
    archived = _is_archived(item_dir)
    prd = item_dir / "prd.md"
    if archived:
        if statuses.source == FROM_ROW and statuses.rows is not None and statuses.rows.opened:
            report = _from_row(item_dir, prd, fields, problems, statuses)
            return StatusReport(report.status, True, report.inconsistencies)
        return StatusReport("done", True, tuple(problems))

    if not statuses.source:
        problems.append(f"{prd}: {statuses.problem}")
        return StatusReport("unknown", False, tuple(problems))
    if statuses.source == FROM_ROW:
        return _from_row(item_dir, prd, fields, problems, statuses)

    declared = fields.get("status", "").strip()
    if declared not in ITEM_STATUSES:
        problems.append(
            f"{prd}: status {declared!r} is not one of {', '.join(ITEM_STATUSES)}"
        )
        return StatusReport("unknown", False, tuple(problems))
    if declared == "in_progress" and not fields.get("branch", "").strip():
        problems.append(f"{prd}: an in_progress item records the branch it lives on")
    return StatusReport(declared, False, tuple(problems))


def _recorded(statuses: "Statuses", item_dir: pathlib.Path) -> str:
    """What the database last recorded against this item, `""` when none.

    A `file` checkout holds no `Rows` and answers `""`, which is the right
    answer rather than a missing one: there is no database to have recorded
    anything, and the aging basis falls back to git and to the item's own date
    exactly as it does for a row the database has lost.

    A function rather than a `Statuses.activity` method beside `Rows.activity`:
    `tests/test_code_health.py` counts two functions of one name as a place its
    dead-code check cannot speak for, and that ceiling only falls.
    """
    return statuses.rows.activity(item_dir) if statuses.rows is not None else ""


def _reported(
    item_dir: pathlib.Path,
    fields: dict[str, str],
    problems: list[str],
    statuses: "Statuses | None",
) -> StatusReport:
    """`_status_report`, resolving and closing its own `Statuses` when given none.

    The activity stamp is attached here rather than inside `_status_report`,
    which has six returns and no business reading a second fact on each of
    them. This is also the only frame that is holding an open `Statuses` in
    both branches, so it is the one place that can ask.
    """
    if statuses is not None:
        return replace(
            _status_report(item_dir, fields, problems, statuses),
            activity=_recorded(statuses, item_dir),
        )
    own = Statuses.of(_root_of(item_dir))
    try:
        return replace(
            _status_report(item_dir, fields, problems, own),
            activity=_recorded(own, item_dir),
        )
    finally:
        own.close()


def status_report(
    item_dir: pathlib.Path, *, statuses: "Statuses | None" = None
) -> StatusReport:
    """Derive a work item's status from its artifacts, or from its row.

    An item under `archive/` is `done` by virtue of where it lives -- the move
    is the record. Anything else answers wherever `docs/work/.status-source`
    says: with no marker, from the `status:` line in `prd.md` frontmatter, and
    with the marker saying `row`, from the item's row in the one database. A
    status that is missing, unknown, or contradicted by the rest of the
    frontmatter is reported as an inconsistency rather than raised: a lint rule
    is the place to fail, and this function is also called by tools that only
    want to show you the tree.
    """
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    return _reported(item_dir, fields, problems, statuses)


def derive_status(item_dir: pathlib.Path) -> str:
    """The derived status alone; `unknown` when the artifacts do not say."""
    return status_report(item_dir).status


def work_item(item_dir: pathlib.Path, *, statuses: "Statuses | None" = None) -> WorkItem:
    """Read one work item directory into a `WorkItem`, reading the prd once."""
    item_dir = pathlib.Path(item_dir)
    fields, problems = _read_prd(item_dir)
    report = _reported(item_dir, fields, problems, statuses)
    name = item_dir.name
    return WorkItem(
        path=item_dir,
        slug=_DATE_PREFIX_RE.sub("", name),
        title=fields.get("title", ""),
        status=report.status,
        created=fields.get("created", ""),
        branch=fields.get("branch", ""),
        archived=report.archived,
        inconsistencies=report.inconsistencies,
        activity=report.activity,
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
    """Every work item, enumerated from the tree rather than from an index.

    The one place the marker is read and the one place the database is
    opened, so every reader that picks an item -- `sd-review`, `sd-plan`,
    `sd-status` -- comes through here and none of them restates where a
    status comes from.
    """
    statuses = Statuses.of(root, work_dir)
    try:
        return [
            work_item(path, statuses=statuses)
            for path in work_item_dirs(root, work_dir)
        ]
    finally:
        statuses.close()


# --------------------------------------------------------------------------
# The aging basis: when an item last showed evidence of activity
# --------------------------------------------------------------------------
#
# These four names came out of the 45-day age sweep when sd:10's criterion 21
# cut it. The sweep reported what the threshold would park and nothing else
# ran it; `sd-status`'s `idle-planning` was its other reader, and the reason
# the two shared one definition was that two definitions of idle would let
# the sweep park what the report had just cleared. The report is the reader
# left, and the definition lives here so that the next reader reads it
# rather than restating it.

#: R10-D1's threshold, in days: an item idle in `planning` past this is
#: reported. `sd-status` reads this name; it does not restate 45.
DEFAULT_DAYS = 45


def item_date(item: WorkItem) -> datetime.date | None:
    """The item's own date, or None when it cannot be established.

    `created:` first, because it is what the item says about itself; the
    directory prefix second, because every templated item carries one and it is
    what the bulk-park actually sorted on. None is an answer, not a failure.

    **This is not the aging basis.** It decides whether an item can be aged at
    all -- None is undated -- and it is the floor `last_active` starts from.
    Ages are measured from `last_active`, because a birth date says when an
    item began and the check that reads it says the item has been neglected.
    """
    raw = (item.created or "").strip()
    if raw:
        try:
            return datetime.date.fromisoformat(raw[:10])
        except ValueError:
            pass
    if _DATE_PREFIX_RE.match(item.path.name):
        try:
            return datetime.date.fromisoformat(item.path.name[:10])
        except ValueError:
            return None
    return None


def _item_directory(path: str, work_dir: str) -> str:
    """The item directory a tracked path belongs to, or `""` for anything else.

    `<work_dir>/<name>/<file>` and `<work_dir>/archive/<month>/<name>/<file>`,
    the same two shapes `work_item_dirs` enumerates. A path directly inside
    `<work_dir>` -- `.status-source` is the one this repository has -- names no
    item and must not be read as one, which is what the length test below is.
    """
    parts = path.split("/")
    head = work_dir.split("/")
    if parts[: len(head)] != head:
        return ""
    rest = parts[len(head):]
    if rest[:1] == [ARCHIVE_DIR]:
        rest = rest[2:]
    return rest[0] if len(rest) > 1 else ""


def touched(root: pathlib.Path, work_dir: str = WORK_DIR) -> dict[str, datetime.date]:
    """The day each item directory was last committed to, keyed by directory.

    One `git log` per root, never one per item: the whole of the cost
    argument. `--name-only` output is bounded by the commits that touched the
    item tree rather than by the repository's history -- 2,082 lines and 116
    KB over this checkout's entire history, measured 2026-09-12 -- so no
    `--since` window is needed and none is used. A window would have to be
    bounded by the oldest candidate anyway, and a miss inside one is
    indistinguishable from no activity at all.

    Merge commits carry no diff and contribute no names. That is right rather
    than a gap: this repository squash-merges, and the squash is the commit
    that touched the files.

    An empty map is an answer, and the only one this returns when git refuses.
    `None` would buy a caller nothing: git refusing and git finding nothing
    both leave the aging basis on its other two sources, and a third state
    nobody can act on differently is a state nobody should have to handle.
    """
    listing = git_output(["log", "--format=%x00%cs", "--name-only", "--", work_dir], root)
    found: dict[str, datetime.date] = {}
    day: datetime.date | None = None
    for line in (listing or "").splitlines():
        if line.startswith("\0"):
            try:
                day = datetime.date.fromisoformat(line[1:].strip())
            except ValueError:
                day = None
            continue
        name = _item_directory(line, work_dir)
        # Newest commit first, so the first sighting of a path is its latest.
        if day is not None and name and name not in found:
            found[name] = day
    return found


def last_active(when: datetime.date, name: str, activity: str,
                marks: dict[str, datetime.date] | None = None) -> datetime.date:
    """The most recent day this item shows evidence of activity.

    **The one definition of the aging basis.** `sd-status`'s `idle-planning`
    producer reads it, for the same reason that producer reads `DEFAULT_DAYS`
    from here rather than restating it: one definition of idle, in one place.

    Three sources, latest wins, each of them evidence that something happened:

    * `when`, the item's own date from `item_date` -- `created:` or the
      directory prefix. The floor, never the answer on its own: an item is at
      least as old as its birth, and this is what the check used to read.
    * the last commit touching `name`, its directory, from `marks`.
    * `activity`, the last stamp the database holds against it -- its row's
      `updated_at` or the newest of its notes, which `WorkItem.activity` is.

    Four loose arguments rather than a `WorkItem`, because `sd-status` reads
    the same three facts off the section dict it already built and would
    otherwise have to fabricate an item to ask the question.

    A union rather than a precedence chain, because each source is blind where
    the others see. A `row` checkout records a triage decision as a note and
    touches no file; a `file` checkout has no database at all; an item nobody
    has committed or recorded has only its birth date. Twenty-one of
    mezmo_benchmark's twenty-four planning items read past the threshold on
    birth dates alone while every one of them had been triaged live the day
    before, and the triage was notes.
    """
    days = [when]
    marked = (marks or {}).get(name)
    if marked is not None:
        days.append(marked)
    recorded = _stamp(activity)
    if recorded is not None:
        days.append(recorded)
    return max(days)


def _stamp(text: str) -> datetime.date | None:
    """The day part of a database timestamp, or None when it will not parse."""
    try:
        return datetime.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


# --------------------------------------------------------------------------
# The row a folder names: a task or followup row, keyed by its frontmatter
# --------------------------------------------------------------------------
#
# Seven pack folders were written for rows `sd task add` made (sd:994). Such
# a row's `kind` is `task` or `followup` and its `source`, `external_id` and
# `path` are NULL, so no path lookup reaches it and `sd-status` reported each
# folder `status-unreadable`. Registering a second, `work` row per folder
# would split the notes and the decisions from the status; the folder names
# its row instead. The key is read only once the path finds nothing, and it
# never reaches a `work` row: a work row is found by its path, and a folder
# that could borrow another item's row through this key would report that
# item's status as its own.

#: The frontmatter key, and the shape of its value: `sd:` then digits.
ITEM_KEY = "item"
ITEM_KEY_RE = re.compile(r"sd:(\d+)\Z")

#: The largest row id `sqlite3` binds; past it the driver raises rather than
#: reporting no row, and the key's value comes from a file, not from a row.
ROW_ID_CEILING = 2**63 - 1

#: How many digits are converted at all. Far above `ROW_ID_CEILING`, which has
#: nineteen, and far below the limit `int()` itself raises at, so an oversized
#: id is still refused by its value, with that value in the sentence, and only
#: an absurd one is refused by its length.
ROW_ID_DIGITS = 64


def named_item(item_dir: pathlib.Path) -> tuple[int | None, str]:
    """`(id, "")` for the row `<item_dir>/prd.md` names as `item: sd:<id>`.

    `(None, "")` when the frontmatter carries no key, or the file cannot be
    read as one; `(None, problem)` when the key is there and is not `sd:`
    followed by digits, with the problem naming the key and its value.
    `sd-docs-lint` fails the same shape where the file is, by `ITEM_KEY_RE`.
    """
    prd = item_dir / "prd.md"
    try:
        fields = parse_frontmatter(prd.read_text(encoding="utf-8"))
    except OSError:
        return None, ""
    except UnicodeDecodeError:
        # Not an `OSError`, and the readers that take this key are not all
        # inside a `try`: the dashboard's is not, so a file that is not UTF-8
        # read as a traceback rather than as a finding naming the file.
        return None, f"{prd} is not valid UTF-8 and its frontmatter cannot be read"
    if fields is None or ITEM_KEY not in fields:
        return None, ""
    value = fields[ITEM_KEY].strip()
    match = ITEM_KEY_RE.match(value)
    if match is None:
        return None, (f"the frontmatter key {ITEM_KEY}: {value} is not sd: followed "
                      f"by digits")
    digits = match.group(1)
    # Before `int()`, not after: past `sys.get_int_max_str_digits()` the
    # conversion itself raises `ValueError`, so a long enough value never
    # reached the ceiling `named_row` checks. The digits are a file's line,
    # and no row id is ever this long.
    if len(digits) > ROW_ID_DIGITS:
        return None, (f"the frontmatter key {ITEM_KEY}: sd:<{len(digits)} digits> is "
                      f"longer than any row id")
    return int(digits), ""


def named_row(item_dir: pathlib.Path, connection: Any, read: Any) -> tuple[Any, str]:
    """The row the folder's `item:` key names through `read`, else `(None, why)`.

    `read` is `sd_db.reads.item_by_id`, or None on an installation without
    it, which keeps the answer the path gave: `(None, "")`. A key that names
    no row, or names a `work` row, is `(None, problem)` with the key and its
    value in the text, so `Rows.status` can say which line to fix. The one
    read `Rows` and `sd_handoff_rows.item_for` both take, so the dashboard
    and `sd-status` name one row for one folder.
    """
    number, problem = named_item(item_dir)
    if problem or number is None or read is None:
        return None, problem
    if number > ROW_ID_CEILING:
        # `sqlite3` raises `OverflowError` rather than returning no row for an
        # integer past its range, and this value is a line in a file anybody
        # can edit. Refused before it is bound, so the answer is a finding.
        return None, (f"the frontmatter key {ITEM_KEY}: sd:{number} is past the largest "
                      f"row id a database can hold")
    row = read(connection, number)
    if row is None:
        return None, f"the frontmatter key {ITEM_KEY}: sd:{number} names no row"
    if row["kind"] == "work":
        return None, (f"the frontmatter key {ITEM_KEY}: sd:{number} names a work row, "
                      f"and a work row is found by its path, not by this key")
    return row, ""


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
    claims = list(said.items())
    for sha, message in commit_messages(root, base, head):
        claims.extend((sha, line[len(AUTHORED_TRAILER):].strip())
                      for line in message.rstrip().rsplit("\n\n", 1)[-1].splitlines()
                      if line.startswith(AUTHORED_TRAILER))
    for sha, value in claims:
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


#: The pack's own hook bypass, read by `hooks/pre-commit`. Named here so the
#: one caller that sets it and the hook that reads it share a spelling, and so
#: a bypass stays greppable -- which is the reason that hook gives for having a
#: variable at all, where `--no-verify` leaves no trace.
SKIP_HOOKS_VARIABLE = "SD_SKIP_HOOKS"


def _attribution_environment(root: pathlib.Path) -> dict[str, str] | None:
    """The environment for the attributing commit, or None to inherit this one.

    `git commit` with no pathspec commits the index, and `attribute` passes
    none, so the commit it makes is empty exactly while the index is. When it
    is, a content gate has no content to read and running it is pure cost:
    this repository's `hooks/pre-commit` runs two whole-tree test passes,
    measured at 6.3 to 6.7 s under a load average near 85 on 2026-09-20,
    against the 15 s bound `GIT_TIMEOUT_SECONDS` puts on the commit. A slower
    machine spends the whole bound and `attribute` raises
    `subprocess.TimeoutExpired` where an attribution should have landed --
    reproduced that day in a fresh worktree, which is every agent's worktree.

    `SD_SKIP_HOOKS=1` and not `--no-verify`: it is the bypass the hook
    documents, it prints a notice rather than passing in silence, and it
    leaves a `commit-msg` hook running, which does have something to read --
    this commit carries the `Attributes:` and `Authored-with:` trailers.

    A staged index is not this case. It rides into the commit, so it is
    content, and the gate that reads content still runs on it. Git failing to
    answer reads as staged for the same reason: the gate stays on.
    """
    staged = git_output(["diff", "--cached", "--name-only"], root)
    if staged is None or staged:
        return None
    return {**os.environ, SKIP_HOOKS_VARIABLE: "1"}


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

    Empty is also why the content gate is skipped for it; the condition and
    its measurement are in `_attribution_environment`.
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
        env=_attribution_environment(root),
        timeout=GIT_TIMEOUT_SECONDS, check=False,
    )
    if written.returncode != 0:
        raise TrailerError(
            f"git refused the attributing commit: "
            f"{(written.stderr or written.stdout).strip() or 'no reason given'}"
        )
    return git_output(["rev-parse", "HEAD"], root) or "", value, covered


# --------------------------------------------------------------------------
# Delivery: the one question a checkout with no database puts to git
# --------------------------------------------------------------------------

#: The closing trailers. `Delivers:` rides the merge that delivers the item;
#: `Closes:` a later merge in the same repository, or an empty commit on the
#: item's own branch, for a delivery or a cancellation whose own merge went
#: out without one. `Item:` is deliberately not here: it ties a merge to an
#: item and closes nothing, so a slice shipped without `--deliver` carries it
#: alone, and the item stays open.
DELIVERS_TRAILER = "Delivers:"
CLOSES_TRAILER = "Closes:"

#: `no` is a positive finding from history the checkout actually has;
#: `unknown` is what a checkout that cannot see far enough says instead.
#: Swapping the two silently reopens delivered work, since every reader that
#: picks an item excludes a `yes` and treats an `unknown` as not selectable.
YES, NO, UNKNOWN = "yes", "no", "unknown"


class Answer(str):
    """One of those three words, plus the repair an `unknown` asks for.

    A string, so `delivered(...) == "yes"` is the whole of it for a caller
    that wants only the word; `repair` rides along for the reader that has to
    refuse by name, since a boundary and an unreachable remote differ.
    """

    repair: str

    def __new__(cls, word: str, repair: str = "") -> "Answer":
        answer = super().__new__(cls, word)
        answer.repair = repair
        return answer


def _spellings(item: "str | tuple[str, ...]") -> tuple[str, ...]:
    """The one name a caller asks about, or the several it accepts.

    A bare string stays one name. Membership on a string is a substring test,
    so `sd:78` would close `sd:788`; normalising here is what keeps every
    comparison below an equality against a whole trailer value.
    """
    return (item,) if isinstance(item, str) else tuple(item)


def _closes(message: str, item: "str | tuple[str, ...]") -> bool:
    """True when this message's trailer block -- its last paragraph, which is
    what makes a trailer a trailer -- closes `item`. Reading the whole message
    would let a commit that quoted a trailer close the item it named.

    `item` may be several spellings of one item, and any one of them closes
    it. The id `sd-ship` writes, `Delivers: sd:<id>`, and the folder name a
    database-free checkout has to ask by are the same item said two ways, and
    `main` carries both forms.
    """
    wanted = _spellings(item)
    for line in message.rstrip().rsplit("\n\n", 1)[-1].splitlines():
        name, _, value = line.rstrip().partition(" ")
        if name in (DELIVERS_TRAILER, CLOSES_TRAILER) and value.strip() in wanted:
            return True
    return False


def _closed_by(root: pathlib.Path, ref: str, item: "str | tuple[str, ...]") -> bool:
    """Whether a commit reachable from `ref` closes `item`; a ref git cannot
    resolve closes nothing. `--grep` only narrows the walk; `_closes` decides."""
    grep = f"{DELIVERS_TRAILER}|{CLOSES_TRAILER}"
    raw = git_output(["log", "--format=%H%x1f%B%x1e", "-E", "--grep", grep, ref], root) or ""
    return any(_closes(c.partition("\x1f")[2], item) for c in raw.split("\x1e"))


def upstream(root: pathlib.Path) -> tuple[str, str]:
    """The remote this checkout can be behind, and that remote's default branch:
    HEAD's upstream then `origin`, and what the remote publishes then the first
    of `main` and `master` this checkout resolves. A checkout with no remote is
    never behind, and gets `""` -- it answers from what it has."""
    names = (git_output(["remote"], root) or "").split()
    head = git_output(["rev-parse", "--abbrev-ref", "HEAD"], root) or ""
    tracked = git_output(["config", "--get", f"branch.{head}.remote"], root)
    fallback = "origin" if "origin" in names else (names[0] if names else "")
    remote = tracked if tracked in names else fallback
    published = git_output(["symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"], root)
    if published:
        return remote, published.partition("/")[2] or published
    for name in ("main", "master"):
        if git_output(["rev-parse", "--verify", "--quiet", name], root) is not None:
            return remote, name
    return remote, "main"


def delivered(root: pathlib.Path, item: "str | tuple[str, ...]") -> Answer:
    """`yes`, `no` or `unknown`: is `item` delivered, asked of git and nothing else.

    `yes` when a commit reachable from the remote's default branch as just
    fetched, from the checkout's branch as just fetched from its upstream, or
    from `HEAD`, carries `Delivers: <item>` or `Closes: <item>`; `item` may be
    a tuple of spellings, any one of which answers for it. `no` when
    none does *and* the history is whole *and* it is current; `unknown` when
    it is neither, because a shallow clone's trailer may sit past the boundary
    and a clone retained while another machine delivered or cancelled the item
    holds neither trailer -- both would answer `no` for finished work.

    The default branch is fetched first and answers `yes` alone when it carries
    the trailer; only otherwise is the checkout's branch fetched, because the
    mark for a branch-only cancel and for a guest delivery lives on that branch
    and on no other. A branch the remote no longer has, deleted at its own
    merge, is nothing to be behind and the answer comes from the default branch
    and `HEAD`; a branch fetch that fails while the ref is still published is
    `unknown`, since the tip it lacks may carry the mark.
    """
    # "false" is the one answer meaning a repository, and a whole one: None is
    # no git at all, "true" a boundary the trailer may be sitting past.
    if git_output(["rev-parse", "--is-shallow-repository"], root) != "false":
        return Answer(UNKNOWN, "git fetch --unshallow")
    remote, default = upstream(root)
    if not remote:
        return Answer(YES if any(_closed_by(root, r, item) for r in ("HEAD", default)) else NO)
    if git_output(["fetch", remote, default], root) is None:
        return Answer(UNKNOWN, f"git fetch {remote} {default}")
    if _closed_by(root, "FETCH_HEAD", item):
        return Answer(YES)
    branch = git_output(["rev-parse", "--abbrev-ref", "HEAD"], root) or ""
    if branch not in ("", "HEAD", default):
        if git_output(["fetch", remote, branch], root) is None:
            # The remote answered a moment ago, so a refusal here is about the
            # ref -- unless it is still published, and then the tip is missing.
            listed = git_output(["ls-remote", "--heads", remote, branch], root)
            if listed is None or listed:
                return Answer(UNKNOWN, f"git fetch {remote} {branch}")
        elif _closed_by(root, "FETCH_HEAD", item):
            return Answer(YES)
    return Answer(YES if _closed_by(root, "HEAD", item) else NO)


# --------------------------------------------------------------------------
# Guest mode: the planning artifacts that do not belong in an upstream tree
# --------------------------------------------------------------------------


#: The three trees `WORKFLOW.md` keeps out of an upstream checkout in
#: `mode: guest`: the planning triad, the specs and the decision records.
#: Written once here because `bin/sd-ship` already spells the same three at
#: push time, and two lists is how one of them gains a fourth entry alone.
GUEST_REFUSED_DIRS = ("docs/work", "docs/spec", "docs/decisions")


def guest_artifacts(paths: Any) -> tuple[str, ...]:
    """The repo-relative `paths` that live under a guest-refused tree.

    Separate from the mode question on purpose: this half is pure, so a caller
    with nothing to refuse never reaches the network to find that out.
    """

    found = set()
    for entry in paths:
        text = re.sub(r"^(?:\./)+", "", str(entry).replace(os.sep, "/"))
        for directory in GUEST_REFUSED_DIRS:
            if text == directory or text.startswith(directory + "/"):
                found.add(text)
    return tuple(sorted(found))


def guest_artifact_refusal(root: pathlib.Path, paths: Any, *, ask: Asker = gh_api) -> str:
    """One sentence refusing planning artifacts in the upstream tree, or `""`.

    `WORKFLOW.md` states the refusal as a mechanical property -- "every writing
    skill refuses the upstream tree" -- and until this existed the only copy of
    the rule was a bullet in `skills/sd-plan/SKILL.md` addressed to an agent. A
    sentence an agent may skip is not a refusal, and two repositories reached
    `guest` carrying 162 committed `prd.md` files between them with nothing
    objecting at write time.

    `mode` is the authority, not the remote directly, so detection stays a
    ceiling: a written `full` that the remote lowers refuses here too, and a
    remote that cannot be asked at all resolves `guest` and refuses -- the same
    way `bin/sd-ship` refuses a guest push carrying these paths. The sentence
    names the paths and where they belong instead; the caller decides the exit
    code, because this module raises nothing.
    """

    refused = guest_artifacts(paths)
    if not refused:
        return ""
    if mode(root, ask=ask) != "guest":
        return ""
    shown = ", ".join(refused[:3])
    if len(refused) > 3:
        shown += f" and {len(refused) - 3} more"
    return (
        f"this repository is in guest mode, so {shown} cannot be written into the "
        "upstream tree; planning artifacts live on the fork's integration branch "
        "(WORKFLOW.md, `mode: guest`). Detection is a ceiling: a `mode: full` line "
        "the remote lowers, and a remote that cannot be asked, both resolve guest here."
    )


def shared_tree_artifacts(root: pathlib.Path) -> tuple[str, ...]:
    """The planning artifacts the remote's default branch already carries.

    The refusal keeps new ones out; it can do nothing about what a repository
    was already carrying on the day the remote's answer changed. That is the
    operator's to move, and moving it needs the list. Read off the remote's
    default branch as this checkout last saw it -- `refs/remotes/<remote>/<default>`
    -- and not off the working tree, because the question is what the shared
    tree holds, not what this branch does. Nothing is fetched: `sd-status`
    reports, and a report does not reach the network on the reader's behalf.

    Empty for a checkout with no remote, for a remote-tracking ref this clone
    does not have, and for a shared tree holding none of the three trees --
    all of which are the same answer to the reader, "nothing to move".
    """
    remote, default = upstream(root)
    if not remote:
        return ()
    listed = git_output(["ls-tree", "-r", "--name-only", "-z", f"refs/remotes/{remote}/{default}",
                         "--", *GUEST_REFUSED_DIRS], root)
    if listed is None:
        return ()
    return tuple(sorted(name for name in listed.split("\0") if name))


# --------------------------------------------------------------------------
# The trailer block git actually reads, and the lines that fell out of it
# --------------------------------------------------------------------------


#: The trailer names whose demotion costs something. `Delivers:` and `Closes:`
#: close an item; `Item:` associates a merge with one. A line naming any of the
#: three outside the block git reads is a statement the tools cannot see.
STATED_TRAILERS = (DELIVERS_TRAILER, CLOSES_TRAILER, "Item:")

#: A trailer as it has to be written to count: at column zero, a name, a colon,
#: and a value. Indented and backticked forms are prose *about* a trailer --
#: this repository's own commit messages quote them constantly -- and matching
#: those would turn every message that explains the convention into a finding.
_STATED_RE = re.compile(
    r"^(?:" + "|".join(re.escape(name.rstrip(":")) for name in STATED_TRAILERS) + r"):[ \t]*\S"
)


def trailer_block(message: str) -> str:
    """The last paragraph of `message`, which is the whole of what a trailer is.

    The same slice `_closes` takes, and the same one `git interpret-trailers
    --parse` takes: a trailer block is the final paragraph and nothing else. It
    is spelled once here so the two readers cannot drift, and named so the
    property has somewhere to be tested from.
    """
    return message.rstrip().rsplit("\n\n", 1)[-1]


def demoted_trailers(message: str) -> tuple[str, ...]:
    """The closing trailers this message states that git will not read back.

    One blank line is the whole failure. `git interpret-trailers --parse` reads
    only the last block, so a message ending

        Delivers: sd:5

        Co-Authored-By: ...

    parses to `Co-Authored-By:` alone and the delivery is invisible: `sd work
    deliver` refuses the commit, the item stays open, and the code is on main.
    Nothing reported it, because a demoted trailer and an absent one look the
    same to every reader downstream -- which is exactly why the check has to
    run against the message *before* the reader that will not see it.

    Measured over `origin/main` at 730d4541: 5 of 3,431 commits state a trailer
    outside the block git reads, and one of them (193d8e87) is the `Delivers:
    sd:5` that had to be re-recorded by an empty commit. No commit trips this
    on a quoted trailer, which is what `_STATED_RE`'s column-zero anchor buys.
    """
    block = trailer_block(message).splitlines()
    return tuple(
        line for line in message.splitlines()
        if _STATED_RE.match(line) and line not in block
    )


def display_fields(
    row: dict[str, Any],
    order: tuple[str, ...],
    shown: tuple[str, ...] = (),
) -> list[str]:
    """The keys of `row` to print: `order` first, then everything else.

    A renderer that iterates a hand-written tuple makes that tuple the
    membership as well as the order, so every key a producer adds later is
    dropped in silence. `order` stays the display order; the row decides what
    exists. `shown` names keys a caller already printed, such as in a header.
    """
    skip = set(shown)
    # `dict.fromkeys` rather than a set: it removes a repeat while keeping the
    # caller's order. A tuple that names a key twice printed it twice, which
    # is the kind of thing a hand-written list acquires and nobody notices.
    named = list(dict.fromkeys(key for key in order if key not in skip))
    known = skip | set(order)
    return named + sorted(key for key in row if key not in known)


def display_value(value: Any) -> bool:
    """Whether a text report prints a field holding `value`.

    Only `None`, `[]` and `""` are empty. `False` and `0` are answers:
    `draft_verified: false` says a draft no longer matches its digest, and a
    report that hides it reads the same as one whose producer never set the
    key (sd:360). The two contribution renderers share this so they cannot
    disagree again about what empty means.
    """
    return value is not None and value != [] and value != ""


# --------------------------------------------------------------------------
# Workflow files and the protection acknowledgement, read once for two commands
# --------------------------------------------------------------------------
#
# Moved here from `bin/sd-status` on sd:1110. `sd-status` reads the working
# tree to report; `sd-ship merge` reads the reviewed head to decide, and both
# must read the same shape or one of them is wrong without anyone knowing.

#: A mapping key, quoted or not. `"pull_request":` is the same key as
#: `pull_request:`, and a reader that matched only the bare form dropped
#: the entry while its unquoted siblings still parsed -- a workflow that
#: silently stopped being expected (sd:1110 post-cap review).
YAML_KEY_RE = re.compile(r"^(?P<indent>\s*)(?:\"(?P<dquoted>[^\"]+)\"|'(?P<squoted>[^']+)'|(?P<bare>[A-Za-z_][A-Za-z0-9_.\-]*))[ \t]*:\s*(?P<value>.*?)\s*$")


def yaml_key(match: re.Match[str]) -> str:
    """The key `YAML_KEY_RE` matched, whichever of its three forms it took."""
    return match.group("dquoted") or match.group("squoted") or match.group("bare")
YAML_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s*(?P<rest>.*?)\s*$")

PR_TRIGGERS = ("pull_request", "pull_request_target")


def yaml_scalar(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def yaml_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def yaml_uncommented(line: str) -> str:
    """`line` without a trailing ` # comment`, quotes respected.

    `- pull_request # validate PRs` is valid YAML naming `pull_request`, and a
    reader that kept the comment would carry a trigger no event is called,
    which is how a workflow silently stops being expected (sd:1110 review).
    """
    quote = ""
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index].rstrip()
    return line.rstrip()


def yaml_lines(text: str) -> list[str]:
    """Non-blank, non-comment lines, right-stripped. Enough YAML for job names.

    A workflow file's job list is a handful of nested mappings, and PyYAML is
    not stdlib. This reads the shape workflows actually have -- the same
    bargain `_taskfile_tasks` above already makes -- and every construct it
    cannot resolve becomes a stated note rather than a silent wrong answer.
    """
    return [
        stripped
        for line in text.split("\n")
        if (stripped := yaml_uncommented(line)).strip()
    ]


def yaml_children(lines: list[str], index: int) -> list[str]:
    base = yaml_indent(lines[index])
    out = []
    for line in lines[index + 1 :]:
        if yaml_indent(line) <= base:
            break
        out.append(line)
    return out


def yaml_entries(lines: list[str]) -> list[tuple[int, str, str]]:
    """`(offset, key, inline value)` for the mapping keys at the top indent."""
    if not lines:
        return []
    base = yaml_indent(lines[0])
    found = []
    for offset, line in enumerate(lines):
        if yaml_indent(line) != base:
            continue
        match = YAML_KEY_RE.match(line)
        if match:
            found.append((offset, yaml_key(match), match.group("value")))
    return found


def yaml_field(lines: list[str], key: str) -> str | None:
    for _, name, value in yaml_entries(lines):
        if name == key:
            return value
    return None


def yaml_sub(lines: list[str], key: str) -> list[str]:
    for offset, name, _ in yaml_entries(lines):
        if name == key:
            return yaml_children(lines, offset)
    return []


def yaml_inline_list(value: str) -> list[str] | None:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        return [yaml_scalar(part) for part in text[1:-1].split(",") if part.strip()]
    return None


def yaml_sequence(lines: list[str], inline: str) -> list[str]:
    parsed = yaml_inline_list(inline)
    if parsed is not None:
        return parsed
    if not lines:
        return []
    base = yaml_indent(lines[0])
    return [
        yaml_scalar(match.group("rest"))
        for line in lines
        if yaml_indent(line) == base and (match := YAML_ITEM_RE.match(line))
    ]


def yaml_unreadable(lines: list[str]) -> list[str]:
    """The lines at this block's top indent that are neither a key nor an item.

    A partial reader's real danger is not the line it cannot parse; it is
    that the line's siblings parse, so the block looks complete and the
    missing entry is invisible. A caller deciding a merge asks this and
    refuses, rather than acting on what it did read (sd:1110 review).
    """
    if not lines:
        return []
    base = yaml_indent(lines[0])
    return [line for line in lines if yaml_indent(line) == base
            and not YAML_KEY_RE.match(line) and not YAML_ITEM_RE.match(line)]


def workflow_trigger_block(lines: list[str]) -> list[str] | None:
    """The children of the workflow's `on:` key, or `None` when it has none."""
    for offset, key, _ in yaml_entries(lines):
        if key in ("on", "true"):  # a YAML 1.1 loader would fold `on` to true
            return yaml_children(lines, offset)
    return None


def workflow_triggers(lines: list[str]) -> set[str]:
    """The workflow's event names; an empty set means "could not tell"."""
    for offset, key, inline in yaml_entries(lines):
        if key not in ("on", "true"):  # a YAML 1.1 loader would fold `on` to true
            continue
        parsed = yaml_sequence(yaml_children(lines, offset), inline)
        if parsed:
            return set(parsed)
        if inline:  # `on: pull_request`, the single-event form
            return {yaml_scalar(inline)}
        return {name for _, name, _ in yaml_entries(yaml_children(lines, offset))}
    return set()


#: A GitHub event name is lower-case words joined by underscores and nothing
#: else. A trigger that reads otherwise is not an event this reader misnamed;
#: it is a construct this reader could not resolve, and a caller deciding on
#: the set must refuse rather than treat the workflow as not expected.
EVENT_NAME_RE = re.compile(r"^[a-z][a-z_]*$")

#: Where a repository records that it has looked at a protection state and
#: decided to keep it. A sibling of `.github/sd-review.json` rather than a key
#: inside it: that file is `bin/sd-review`'s routing policy, it rejects unknown
#: keys by design, and a malformed acknowledgement must not take the review
#: lane down with it. Same directory, same `<command>.json` convention, same
#: property that matters -- it is in git, so a collaborator sees it in a diff
#: instead of finding it in somebody's machine config.
ACKNOWLEDGEMENT_RELATIVE_PATH = pathlib.Path(".github") / "sd-status.json"

#: The facts an acknowledgement may pin, and the whole vocabulary it may use.
#: Deliberately not the gap id: `reviews` is emitted for two opposite states of
#: the branch -- the review object being absent, which means no pull request is
#: required at all, and the object existing while asking for 0 approvals. An
#: acknowledgement keyed on the id alone would accept the first while meaning
#: the second, which is how a suppression becomes a hole. A key outside this
#: tuple is rejected at load time rather than quietly matching nothing.
#:
#: `branch_protection` is the same move one level up. The others reduce a
#: protection *object*, so on a branch that has none they are all constants --
#: an `unprotected` entry pinning only those would accept the id whatever the
#: branch looked like, which is the shape the non-empty `state` rule forbids.
#: This is the fact that can be wrong there, and therefore the one that can go
#: stale.
#:
#: `bypass` is the list the `bypass` gap prints -- every ruleset bypass that
#: does not reach administrators, as `<ruleset> (#<id>): <actor> (<mode>)`,
#: sorted -- rather than a boolean, for the same reason `reviews` pins a
#: count: an entry that accepted "an app can bypass" as a yes/no would go on
#: accepting the branch after a team was added beside the app.
ACKNOWLEDGED_FACTS = (
    "branch_protection",
    "bypass",
    "enforce_admins",
    "required_approving_review_count",
    "required_pull_request_reviews",
    "strict",
)


#: Every finding an acknowledgement can name, and the whole vocabulary `id`
#: may use. One tuple, read by the producers below and by the loader, because
#: the ids used to be scattered string literals with no set anywhere: an entry
#: reading `unprotectd` or `enforce-admins` passed every check the loader made,
#: matched no finding, printed nothing, and left the gap it was written to
#: accept printing on every run -- a silent suppression of the accept, which is
#: the failure this file exists to prevent.
#:
#: What is deliberately *not* here is as load-bearing as what is.
#: `squash_message` and `rebase_merge` are real ids the report prints, on merge
#: settings that never pass through `_apply_acknowledgements`; `acknowledgements`
#: is the id a fault in the file itself carries, and a broken file must not be
#: able to accept its own breakage. All three are ids no acknowledgement could
#: ever match, so admitting them here would re-open the hole under a
#: better-spelled name.
ACKNOWLEDGEABLE_GAPS = (
    "bypass",
    "enforce_admins",
    "produced_not_required",
    "required_checks",
    "required_not_produced",
    "reviews",
    "strict",
    "unprotected",
)


def load_acknowledgements(root: pathlib.Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Accepted protection states, read from `.github/sd-status.json`.

    **Incident.** One of this repository's protection gaps cannot be closed:
    `main` requires a pull request but zero approving reviews, and with
    `enforce_admins` on, one maintainer, and GitHub refusing self-approval,
    raising the count locks the repository while deleting the review object
    loses the pull-request requirement outright. So the row printed `GAP` on
    every run with no action behind it -- and a section that always has a
    standing red line is a section a reader learns to skim, which is where a
    real regression would land unread.

    **Deletion criterion.** Each entry carries `until:`, the condition that
    ends it, and it is printed every run beside the acceptance. When that
    condition is met the entry is deleted from the file and the gap returns on
    its own; nothing here needs changing for that to happen. An entry whose
    `until` has come true and which is still in the file is a bug in the file,
    not in this reader.

    Returns `(entries, problems)`. A file that exists and is wrong yields no
    entries and a problem per fault: never a silent fall back, and never a
    partial application. Failing this way fails closed -- every gap the file
    meant to accept goes on printing as a gap.
    """
    path = root / ACKNOWLEDGEMENT_RELATIVE_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except (OSError, UnicodeDecodeError) as error:
        return [], [f"{ACKNOWLEDGEMENT_RELATIVE_PATH}: cannot be read ({error})"]
    return parse_acknowledgements(text)


def parse_acknowledgements(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """The file's content, wherever it was read from, to `(entries, problems)`.

    `load_acknowledgements` reads the working tree and hands the text here;
    `sd-ship merge` reads the reviewed head (`git show <head>:...`) and hands
    its text here. One parser, two readers: a declaration the merge honours
    is the one `sd-status` reports, by construction rather than by agreement.
    """
    try:
        loaded = json.loads(text)
    except ValueError as error:
        return [], [f"{ACKNOWLEDGEMENT_RELATIVE_PATH}: not valid JSON ({error})"]

    where = str(ACKNOWLEDGEMENT_RELATIVE_PATH)
    if not isinstance(loaded, dict):
        return [], [f"{where}: the top level must be a JSON object"]
    known = ("$schema", "accepted_gaps")
    unknown = sorted(set(loaded) - set(known))
    if unknown:
        # Both known keys are named, `$schema` included: a message that listed
        # only `accepted_gaps` would read as though the schema pointer this
        # repository's own file carries were itself the mistake.
        return [], [
            f"{where}: unknown key(s) {', '.join(unknown)}; known keys are {', '.join(known)}"
        ]
    raw = loaded.get("accepted_gaps", [])
    if not isinstance(raw, list):
        return [], [f"{where}: accepted_gaps must be a list"]

    entries: list[dict[str, Any]] = []
    problems: list[str] = []
    for index, entry in enumerate(raw):
        faults = acknowledgement_problems(f"{where}: accepted_gaps[{index}]", entry)
        problems.extend(faults)
        if not faults:
            # A faulty entry is not carried, and it makes no difference which
            # way that goes: one fault anywhere discards the whole file two
            # lines below. Dropping it here keeps the list that reaches the
            # matcher to entries this reader has fully checked.
            entries.append(entry)
    if problems:
        return [], problems
    return entries, []


def acknowledgement_problems(label: str, entry: Any) -> list[str]:
    """Everything wrong with one `accepted_gaps` entry, in the order read.

    Split out of `load_acknowledgements` rather than inlined: the loader reads
    a file, and this decides whether one entry can mean anything, which are
    two jobs that grew past what one function can hold at a glance.

    The two vocabularies are the substance. `state` may name only facts this
    reader can observe, and `id` may name only a finding an acknowledgement
    can be matched against -- both rejected here rather than quietly matching
    nothing, which is the failure this whole file was written to remove.
    """
    problems: list[str] = []
    if not isinstance(entry, dict):
        return [f"{label} must be an object"]
    missing = [key for key in ("id", "state", "because", "since", "until") if key not in entry]
    if missing:
        # `because` and `until` are required rather than optional because an
        # acknowledgement without a reason and an end condition is a
        # suppression, and a suppression is the thing this replaces.
        return [f"{label} is missing {', '.join(missing)}"]
    for key in ("id", "because", "since", "until"):
        if not isinstance(entry[key], str) or not entry[key].strip():
            problems.append(f"{label}.{key} must be a non-empty string")
    gap_id = entry["id"]
    if isinstance(gap_id, str) and gap_id.strip() and gap_id not in ACKNOWLEDGEABLE_GAPS:
        # Compared exactly rather than stripped, and that is not pedantry:
        # `_apply_acknowledgements` matches `entry["id"] == gap["id"]`, so
        # ` reviews ` would load clean and accept nothing, which is the whole
        # defect being closed here, one space to the left.
        problems.append(
            f"{label}.id {gap_id!r} is not an acknowledgeable gap, so it would accept "
            f"nothing; known ids are {', '.join(ACKNOWLEDGEABLE_GAPS)}"
        )
    state = entry["state"]
    if not isinstance(state, dict) or not state:
        # An empty `state` would accept the id whatever the branch looks like,
        # which is exactly the shape this file must not be able to take: see
        # ACKNOWLEDGED_FACTS.
        problems.append(f"{label}.state must be a non-empty object of observed facts")
    else:
        problems.extend(
            f"{label}.state.{fact} is not an observable protection fact; "
            f"known facts are {', '.join(ACKNOWLEDGED_FACTS)}"
            for fact in sorted(set(state) - set(ACKNOWLEDGED_FACTS))
        )
    return problems


# --------------------------------------------------------------------------
# The Jev stage switch, shared by every gate in this repository
#
# Last in the file rather than beside the other small helpers, because work
# items cite this one by `path:line`: inserting thirty lines at the top moved
# every citation below them, and `test_doc_citations` measured one falling out
# of the symbol it named. Append here and nothing above can move.
# --------------------------------------------------------------------------

#: The words that switch a Jev stage off, in any case. Anything else leaves it
#: on, including the ``1`` these gates used to require -- a typo is not an
#: outage.
#:
#: This vocabulary is `jev.py`'s `FLAG_OFF`, copied rather than imported: `jev`
#: ships in a private companion repository and this one is public, so there is
#: nothing to import from. Two copies drift, so the words are pinned by
#: `tests/test_sd_review_jev.py` and named here to be grepped for.
JEV_FLAG_OFF = ("0", "off", "false", "no", "disabled")


def jev_stage_off(value: str | None) -> bool:
    """Whether a stage variable has been used to switch its Jev reading off.

    Unset means on, and so does any word outside `JEV_FLAG_OFF`. The variable
    only ever subtracts: setting it cannot make a reading happen that `jev`
    itself would decline.

    One definition, reached by both gates. Two of these lived in `bin/` for
    the length of one rejected commit, and the dead-code check refused it:
    a name defined twice is a name its evidence can no longer count.
    """

    return value is not None and value.strip().lower() in JEV_FLAG_OFF
