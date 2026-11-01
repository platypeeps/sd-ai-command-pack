"""The release chain a merge owes in a repository whose policy declares `release` (sd:6881).

docs/work/2026-10-29-repo-policy/design.md § Failure table. After the lane lands a PR it runs the chain one
step at a time, as far as it can go now, and stores where it stopped on the merged entry, so the next run
resumes there:

    version  the next semver from the Conventional Commit types since the last tag (`release_types`)
    tag      push the tag on origin's main                       asks when the policy holds `push` at ask
    verify   run `verify` on the tagged commit with SD_RELEASE_TAG and SD_RELEASE_VERSION; a failure reports,
             never rolls back

The deploy bump and its merge land with pack sd:7014; until then the policy reader refuses their keys.
A freeze window (`sd-db repo freeze`) holds the tag. A step that fails or waits keeps its step; only `done`
and `stopped` end a chain. An ask files one question on the item; a ruling on it that starts with `go` or
`yes` runs the step, any other stops the chain.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
from typing import Any, Callable

import sd_lib

FINAL = ("done", "stopped")
#: The types that release when the convention names none: semantic-release's defaults.
DEFAULT_TYPES = ("feat", "fix")
TAG = re.compile(r"^(?P<prefix>v?)(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\Z")
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<bang>!?): \S")
BREAKING = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
#: How long `verify` may run before it counts as failed.
VERIFY_SECONDS = 600


class ReleaseError(RuntimeError):
    """A step that could not finish; the chain keeps the step and the next run tries it again."""


def next_tag(last: str | None, messages: list[str], types: list[str] | tuple[str, ...]) -> str | None:
    """The tag after `last` the commit `messages` call for, keeping its `v` or not; None when none releases.

    A breaking change (`type!:` or a `BREAKING CHANGE:` footer) bumps the major, `feat` the minor, any other
    type in `types` the patch. No last tag counts from `v0.0.0`.
    """
    held = TAG.match(last or "v0.0.0")
    if held is None:
        raise ReleaseError(f"the last tag {last!r} is not a semver tag")
    level = 0
    for message in messages:
        subject = SUBJECT.match(message)
        if subject is None:
            continue
        if subject["bang"] or BREAKING.search(message):
            level = 3
        elif subject["type"] in types:
            level = max(level, 2 if subject["type"] == "feat" else 1)
    if not level:
        return None
    major, minor, patch = int(held["major"]), int(held["minor"]), int(held["patch"])
    major, minor, patch = {3: (major + 1, 0, 0), 2: (major, minor + 1, 0), 1: (major, minor, patch + 1)}[level]
    return f"{held['prefix']}{major}.{minor}.{patch}"


def _semver(tag: str) -> tuple[int, int, int]:
    held = TAG.match(tag)
    assert held is not None  # noqa: S101 -- callers pass only tags `TAG` matched
    return int(held["major"]), int(held["minor"]), int(held["patch"])


class Wait(Exception):
    """The chain stops here this run; `failed` says whether the reason is a failure or a wait."""

    def __init__(self, reason: str, failed: bool = False) -> None:
        super().__init__(reason)
        self.failed = failed


def _ask(state: dict, step: str, act: str, question: str, world: Any) -> None:
    """Go on when `act` is auto or the operator ruled go; otherwise wait, or stop the chain on another ruling."""
    if act != "ask":
        return
    ruled = world.ruling(state["tag"], step, question)
    if ruled is None:
        raise Wait(f"waiting for the operator's ruling on: {question}")
    if (ruled.split() or [""])[0].strip(".,;:!").lower() not in ("go", "yes"):
        state["step"] = "stopped"
        raise Wait(f"the operator stopped the chain at {step}: {ruled.strip()}")


def _version(state: dict, release: dict, acts: dict, world: Any, types: list[str]) -> str:
    sha = world.tip()
    last = world.last_tag()
    tag = next_tag(last, world.messages_since(last, sha), types)
    if tag is None:
        state["step"] = "done"
        raise Wait(f"nothing to release: no {' or '.join(types)} commit since {last or 'the first commit'}")
    state.update(tag=tag, sha=sha, last=last)
    return "tag"


def _tag(state: dict, release: dict, acts: dict, world: Any, types: list[str]) -> str:
    frozen = world.frozen()
    if frozen:
        raise Wait(f"the repository's freeze window holds the tag: {frozen}")
    _ask(state, "tag", acts.get("push", "auto"), f"push the tag {state['tag']} on {state['sha'][:12]}?", world)
    world.push_tag(state["tag"], state["sha"])
    state["version"] = state["tag"].removeprefix("v")
    return "verify"


def _verify(state: dict, release: dict, acts: dict, world: Any, types: list[str]) -> str:
    if not release.get("verify"):
        return "done"
    try:
        world.verify(release["verify"], state["tag"], state["version"], state["sha"])
    except ReleaseError as error:
        state["step"] = "stopped"  # rollback is the org's process, never automatic
        raise Wait(f"{state['tag']} tagged; verify failed: {error}. Nothing was rolled back.", failed=True) from None
    return "done"


STEPS = {"version": _version, "tag": _tag, "verify": _verify}


def advance_release(state: dict, release: dict, acts: dict, world: Any,
                    types: list[str] | tuple[str, ...] = DEFAULT_TYPES,
                    save: Callable[[dict], None] = lambda state: None) -> dict:
    """`state` moved as far as the chain goes now; `reason` and `failed` say why it stopped where it did.

    `acts` is the repository's effective policy. `save` stores each step as it is reached, before the next
    external act: a kill after the tag push otherwise left the stored step at `version`, and the restart read
    the pushed tag as the last one and released nothing.
    """
    state.pop("reason", None)
    state["failed"] = False
    try:
        while state["step"] not in FINAL:
            state["step"] = STEPS[state["step"]](state, release, acts, world, list(types))
            if state["step"] not in FINAL:
                save(state)
    except Wait as stop:
        state.update(reason=str(stop), failed=stop.failed)
    except ReleaseError as error:
        state.update(reason=f"{state['step']} failed: {error}", failed=True)
    if state["step"] == "done" and "reason" not in state:
        state["reason"] = f"released {state['tag']}"
    return state


class Repositories:
    """What the chain reads and does, on disk: `git` in the lane's main checkout, `verify` in a worktree of it.

    `environ` is the whole environment git and `verify` run in; the lane passes its own. `frozen` and
    `ruling` read the hub; the lane passes them in (`sd_lane.release_chain`).
    """

    def __init__(self, main: pathlib.Path, environ: dict[str, str], frozen: Callable[[], str | None],
                 ruling: Callable[[str, str, str], str | None]) -> None:
        # `environ` whole, never over `os.environ`: that put back what a caller dropped, such as GIT_DIR
        self.main, self.env, self.frozen, self.ruling = main, dict(environ), frozen, ruling
        self._tip: str | None = None
        self._tags: dict[str, str] = {}  # origin's tags as `last_tag` read them, for `messages_since`

    def _run(self, *argv: str, ok: tuple[int, ...] = (0,), timeout: float = 120) -> str:
        try:
            done = subprocess.run(list(argv), cwd=self.main, env=self.env, capture_output=True, text=True,
                                  timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReleaseError(f"{' '.join(argv[:3])} did not finish: {error}") from None
        if done.returncode not in ok:
            raise ReleaseError(f"{' '.join(argv[:3])} exited {done.returncode}: "
                               f"{(done.stderr or done.stdout).strip()[-300:]}")
        return done.stdout.strip()

    def tip(self) -> str:
        """The commit origin's default branch names, as origin advertises it, read and fetched once per chain run.

        Origin's `HEAD` symref and its commit come from one `ls-remote`, as `sd_lane.publish_head` reads them:
        `git fetch` never moves a local `origin/HEAD`, which kept naming master after origin moved to main.
        No tags are fetched: release history is origin's (`_origin_tags`), and `--tags` failed on a local tag
        at odds with origin's, as a would-clobber.
        """
        if self._tip is None:
            branch = sha = ""
            for line in self._run("git", "ls-remote", "--symref", "origin", "HEAD").splitlines():
                left, _, name = line.partition("\t")
                if name == "HEAD" and left.startswith("ref: refs/heads/"):
                    branch = left.removeprefix("ref: refs/heads/")
                elif name == "HEAD":
                    sha = left
            if not branch or not sha:
                raise ReleaseError("origin advertises no default branch, so its release commit is unknown")
            self._run("git", "fetch", "-q", "--no-tags", "origin", f"refs/heads/{branch}")
            if not self._run("git", "rev-parse", "-q", "--verify", f"{sha}^{{commit}}", ok=(0, 1)):
                raise ReleaseError(f"origin's {branch} moved off {sha[:12]} during the fetch; the next run reads it again")
            self._tip = sha
        return self._tip

    def _origin_tags(self, *patterns: str) -> dict[str, str]:
        """Each tag origin holds, as the commit it names: an annotated tag's peeled `^{}` line wins.

        Never a local tag: one that was never pushed, or was moved, is not release history.
        """
        found: dict[str, str] = {}
        for line in self._run("git", "ls-remote", "--tags", "origin", *patterns).splitlines():
            sha, _, ref = line.partition("\t")
            name = ref.removeprefix("refs/tags/")
            if name.endswith("^{}") or name not in found:
                found[name.removesuffix("^{}")] = sha
        return found

    def last_tag(self) -> str | None:
        """The highest semver tag on origin whose commit is in origin's main."""
        tip, self._tags = self.tip(), self._origin_tags()
        for name, sha in sorted(((name, sha) for name, sha in self._tags.items() if TAG.match(name)),
                                key=lambda tag: _semver(tag[0]), reverse=True):
            present = self._run("git", "rev-parse", "-q", "--verify", f"{sha}^{{commit}}", ok=(0, 1))
            if present and self._run("git", "merge-base", sha, tip, ok=(0, 1)) == sha:
                return name
        return None

    def messages_since(self, tag: str | None, sha: str) -> list[str]:
        """The commit messages after origin's `tag`, by the commit origin's tag names, not a local one."""
        if tag is not None and tag not in self._tags:
            raise ReleaseError(f"origin holds no tag {tag}")
        span = f"{self._tags[tag]}..{sha}" if tag else sha
        return [message.strip() for message in self._run("git", "log", "--format=%B%x00", span).split("\0")
                if message.strip()]

    def push_tag(self, tag: str, sha: str) -> None:
        """The tag on `sha`, here and on origin; a rerun after a failed push pushes the same tag."""
        remote = self._origin_tags(f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}").get(tag)  # a pattern omits the peel
        if remote and remote != sha:
            raise ReleaseError(f"origin already has {tag} on {remote[:12]}, not {sha[:12]}")
        if remote:
            return
        local = self._run("git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", ok=(0, 1))
        if local and local != sha:
            raise ReleaseError(f"the local tag {tag} is on {local[:12]}, not {sha[:12]}")
        if not local:
            self._run("git", "tag", tag, sha)
        self._run("git", "push", "-q", "origin", f"refs/tags/{tag}")

    def verify(self, command: str, tag: str, version: str, sha: str) -> None:
        """`command` in a detached worktree at the tagged `sha`, with the tag and version in its environment.

        Not in the main checkout: the landing does not always move it to origin's tip (a pinned or deploying
        checkout, a failed fast-forward), so its files could be older than the commit the tag names.
        """
        with tempfile.TemporaryDirectory(prefix="sd-release-") as scratch:
            tree = pathlib.Path(scratch) / "verify"
            self._run("git", "worktree", "add", "-q", "--detach", str(tree), sha)
            try:
                done = sd_lib.run_group(["sh", "-c", command], cwd=tree, timeout=VERIFY_SECONDS,
                                        env={**self.env, "SD_RELEASE_TAG": tag, "SD_RELEASE_VERSION": version})
            except sd_lib.GroupTimeout:
                raise ReleaseError(f"{command!r} ran past {VERIFY_SECONDS}s") from None
            finally:
                self._run("git", "worktree", "remove", "--force", str(tree), ok=(0, 128))
        if done.returncode:
            raise ReleaseError(f"{command!r} exited {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}")
