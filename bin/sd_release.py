"""The release chain a merge owes in a repository whose policy declares `release` (sd:6881).

docs/work/2026-10-29-repo-policy/design.md § Failure table. After the lane lands a PR it runs the chain one
step at a time, as far as it can go now, and stores where it stopped on the merged entry, so the next run
resumes there:

    version  the next semver from the Conventional Commit types since the last tag (`release_types`)
    tag      push the tag on origin's main                       asks when the policy holds `push` at ask
    verify   run `verify` with SD_RELEASE_TAG and SD_RELEASE_VERSION; a failure reports, never rolls back

The deploy bump and its merge land with pack sd:7014; until then the policy reader refuses their keys.
A freeze window (`sd-db repo freeze`) holds the tag. A step that fails or waits keeps its step; only `done`
and `stopped` end a chain. An ask files one question on the item; a ruling on it that starts with `go` or
`yes` runs the step, any other stops the chain.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
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
        world.verify(release["verify"], state["tag"], state["version"])
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
    """What the chain reads and does, on disk: `git` in the lane's main checkout, and `verify` there.

    `frozen` and `ruling` read the hub; the lane passes them in (`sd_lane.release_chain`).
    """

    def __init__(self, main: pathlib.Path, environ: dict[str, str], frozen: Callable[[], str | None],
                 ruling: Callable[[str, str, str], str | None]) -> None:
        self.main, self.env, self.frozen, self.ruling = main, {**os.environ, **environ}, frozen, ruling
        self._tip: str | None = None

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
        """origin's default branch tip, fetched once per chain run, tags included."""
        if self._tip is None:
            self._run("git", "fetch", "-q", "--tags", "origin")
            for ref in ("origin/HEAD", "origin/main", "origin/master"):
                self._tip = self._run("git", "rev-parse", "-q", "--verify", f"{ref}^{{commit}}", ok=(0, 1)) or None
                if self._tip:
                    break
            else:
                raise ReleaseError(f"{self.main} has no origin/HEAD, origin/main or origin/master")
        return self._tip

    def last_tag(self) -> str | None:
        tags = self._run("git", "tag", "--merged", self.tip(), "--sort=-v:refname").splitlines()
        return next((tag for tag in tags if TAG.match(tag)), None)

    def messages_since(self, tag: str | None, sha: str) -> list[str]:
        span = f"{tag}..{sha}" if tag else sha
        return [message.strip() for message in self._run("git", "log", "--format=%B%x00", span).split("\0")
                if message.strip()]

    def push_tag(self, tag: str, sha: str) -> None:
        """The tag on `sha`, here and on origin; a rerun after a failed push pushes the same tag."""
        remote = self._run("git", "ls-remote", "origin", f"refs/tags/{tag}").split()
        if remote and remote[0] != sha:
            raise ReleaseError(f"origin already has {tag} on {remote[0][:12]}, not {sha[:12]}")
        if remote:
            return
        local = self._run("git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", ok=(0, 1))
        if local and local != sha:
            raise ReleaseError(f"the local tag {tag} is on {local[:12]}, not {sha[:12]}")
        if not local:
            self._run("git", "tag", tag, sha)
        self._run("git", "push", "-q", "origin", f"refs/tags/{tag}")

    def verify(self, command: str, tag: str, version: str) -> None:
        """`command` in the source checkout, with the tag and version in its environment."""
        try:
            done = sd_lib.run_group(["sh", "-c", command], cwd=self.main, timeout=VERIFY_SECONDS,
                                    env={**self.env, "SD_RELEASE_TAG": tag, "SD_RELEASE_VERSION": version})
        except sd_lib.GroupTimeout:
            raise ReleaseError(f"{command!r} ran past {VERIFY_SECONDS}s") from None
        if done.returncode:
            raise ReleaseError(f"{command!r} exited {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}")
