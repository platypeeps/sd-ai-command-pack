"""The release chain a merge owes in a repository whose policy declares `release` (sd:6881, sd:7014).

docs/work/2026-11-01-release-bump-merge/design.md § Failure table. After the lane lands a PR it runs the chain
one step at a time, as far as it can go now, and stores where it stopped on the merged entry, so the next run
resumes there:

    version  the next semver from the Conventional Commit types since the last tag (`release_types`)
    tag      push the tag on origin's main                       asks when the policy holds `push` at ask
    bump     a PR in `deploy_repo` setting `key` in `file`      asks when the deploy repo holds `commit`,
                                                                 `push` or `pr` at ask
    merge    merge that PR once the deploy policy's gates pass   asks when the deploy repo holds `push` at ask;
             the step ends only when GitHub reads the PR MERGED, so a merge queue holds it
    verify   run `verify` in a detached worktree at the merged deploy commit, or the tagged one when no
             `deploy_repo` is declared, with SD_RELEASE_TAG and SD_RELEASE_VERSION; a failure reports, never
             rolls back

A freeze window (`sd-db repo freeze`) holds every act: the tag on the source, the merge on both repositories.
A step that fails or waits keeps its step; only `done` and `stopped` end a chain. An ask files one question on
the item; a ruling on it that starts with `go` or `yes` runs the step, any other stops the chain.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile
from typing import Any, Callable

import sd_lib
import sd_repo_policy
import sd_ship_jenkins

FINAL = ("done", "stopped")
#: The types that release when the convention names none: semantic-release's defaults.
DEFAULT_TYPES = ("feat", "fix")
TAG = re.compile(r"^(?P<prefix>v?)(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\Z")
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<bang>!?): \S")
BREAKING = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
#: How long `verify` may run before it counts as failed.
VERIFY_SECONDS = 600
#: The check conclusions that count as passed; any other completed one is red.
PASSED = ("SUCCESS", "NEUTRAL", "SKIPPED")


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



def set_value(text: str, key: str, value: str) -> tuple[str | None, str]:
    """The old scalar at the dotted `key` of a YAML block mapping, and `text` with `value` in its place.

    Its quotes and a trailing comment stay. None and `text` unchanged when the key is not there; a
    ReleaseError when it holds a mapping, a sequence, a block, flow or multi-line scalar, or an anchor.
    """
    path, depth, lines = key.split("."), 0, text.splitlines(keepends=True)
    parent, child = -1, None  # the matched parent's indent; its children's, once the first one shows it
    for number, line in enumerate(lines):
        body = line.rstrip("\r\n")
        stripped = body.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(body) - len(stripped)
        if indent <= parent:
            break
        child = indent if child is None else child
        found = re.match(r"""(?P<name>[^\s:#"']+|"[^"]*"|'[^']*'):(?P<gap>\s*)(?P<value>.*?)(?P<tail>\s+#.*)?\Z""",
                         stripped)
        if indent != child or found is None or found["name"].strip("\"'") != path[depth]:
            continue
        if depth < len(path) - 1:
            depth, parent, child = depth + 1, indent, None
            continue
        old, quote = found["value"], found["value"][:1] if found["value"][:1] in "\"'" else ""
        if not old or old[0] in "|>[{&*!" or _continues(lines[number + 1:], indent):
            raise ReleaseError(f"{key} is not a scalar on one line; the file is left as it was")
        lines[number] = (f"{' ' * indent}{found['name']}:{found['gap'] or ' '}{quote}{value}{quote}"
                         f"{found['tail'] or ''}{line[len(body):]}")
        return old.strip("\"'"), "".join(lines)
    return None, text


def _continues(rest: list[str], indent: int) -> bool:
    """Whether the next content line sits deeper than `indent`: children, or a scalar's continuation."""
    for line in rest:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return len(line) - len(line.lstrip(" ")) > indent
    return False


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
    frozen = world.frozen(False)
    if frozen:
        raise Wait(f"the repository's freeze window holds the tag: {frozen}")
    _ask(state, "tag", acts.get("push", "auto"), f"push the tag {state['tag']} on {state['sha'][:12]}?", world)
    world.push_tag(state["tag"], state["sha"])
    if release.get("deploy_repo"):
        return "bump"
    state["version"] = state["tag"].removeprefix("v")
    return "verify"


def _deploy_message(message: str, convention: dict | None, released: list[str]) -> str:
    """`message` as the deploy repository's convention commits it, its footer lines taken from the released commits.

    A footer such as `Ref: LOG-\\d+$` names a ticket the chain cannot invent; the commits it releases carry theirs.
    A message the convention still refuses waits, failed, before anything is pushed.
    """
    footer = (convention or {}).get("footer")
    if footer:
        found = dict.fromkeys(line.strip() for text in released for line in text.splitlines()
                              if re.search(footer, line.strip()))
        message = message.rstrip("\n") + ("\n\n" + "\n".join(found) if found else "") + "\n"
    try:
        return sd_repo_policy.check_message(message, convention)
    except sd_repo_policy.ConventionRefused as refused:
        raise Wait(f"the deploy repository's commit convention refuses the bump: {refused}", failed=True) from None


def _bump(state: dict, release: dict, acts: dict, world: Any, types: list[str]) -> str:
    tag, (text, deployed_at) = state["tag"], world.deployed()
    old, _ = set_value(text, release["key"], tag)
    if old is None:
        raise Wait(f"{release['file']} in {release['deploy_repo']} has no {release['key']}", failed=True)
    version = ("v" if old.startswith("v") else "") + tag.removeprefix("v")  # the deployed value's form, not the tag's
    if old == version:  # nothing to bump, but the deploy is still verified, on the commit that holds it
        state.update(version=version, merged=deployed_at,
                     no_bump=f"{release['deploy_repo']} already deploys {version}; no bump")
        return "verify"
    held = "ask" if any(acts.get(act, "auto") == "ask" for act in ("commit", "push", "pr")) else "auto"
    _ask(state, "bump", held,  # `open_bump` commits, pushes a branch and opens the PR
         f"commit, push and open a PR in {release['deploy_repo']} setting {release['key']} from {old} to {version}?", world)
    convention = acts.get("commit_convention")
    released = world.messages_since(state.get("last"), state["sha"]) if (convention or {}).get("footer") else []
    message = _deploy_message(f"chore: release {version}\n\nSet {release['key']} in {release['file']} to {version}.\n",
                              convention, released)
    state["version"] = version
    # A kill after `gh pr create` and before the save reruns this step; `open_bump` finds the PR by its branch.
    state["pr"] = world.open_bump(f"release/{tag}", set_value(text, release["key"], version)[1], message)
    return "merge"


def _merge(state: dict, release: dict, acts: dict, world: Any, types: list[str]) -> str:
    merged = world.merged(state["pr"])  # first: a kill after the merge, before its save, or a queue that merged it
    if merged:
        state["merged"] = merged
        return "verify"
    for deploy, where in ((False, "the repository's"), (True, f"{release['deploy_repo']}'s")):
        frozen = world.frozen(deploy)
        if frozen:
            raise Wait(f"{where} freeze window holds the merge of {state['pr']}: {frozen}")
    checks = world.pr_state(state["pr"], acts)
    if checks != "green":
        raise Wait(f"{state['pr']} stays open: {checks}", failed=checks.startswith("red"))
    _ask(state, "merge", acts.get("push", "auto"), f"merge {state['pr']}, its checks green?", world)
    world.merge_bump(state["pr"])
    merged = world.merged(state["pr"])
    if not merged:  # `gh pr merge` exits 0 when it only adds the PR to a merge queue
        raise Wait(f"{state['pr']} is queued to merge; the chain stays at merge until GitHub reads it MERGED")
    state["merged"] = merged
    return "verify"


def _verify(state: dict, release: dict, acts: dict, world: Any, types: list[str]) -> str:
    deploy = bool(release.get("deploy_repo"))
    if deploy and not state.get("merged"):  # tagged under a tag-only policy that since named a deploy
        return "bump"
    if not release.get("verify"):
        return "done"
    try:
        world.verify(release["verify"], state["tag"], state["version"], state["merged"] if deploy else state["sha"],
                     deploy=deploy)
    except ReleaseError as error:
        state["step"] = "stopped"  # rollback is the org's process, never automatic
        done = f"merged as {state['version']}" if deploy else "tagged"
        raise Wait(f"{state['tag']} {done}; verify failed: {error}. Nothing was rolled back.", failed=True) from None
    return "done"


STEPS = {"version": _version, "tag": _tag, "bump": _bump, "merge": _merge, "verify": _verify}
#: The steps that act on the deploy repository, so its policy holds them, not the source's.
DEPLOY_STEPS = ("bump", "merge")


def advance_release(state: dict, release: dict, acts: dict, world: Any,
                    types: list[str] | tuple[str, ...] = DEFAULT_TYPES,
                    save: Callable[[dict], None] = lambda state: None, deploy_acts: dict | None = None) -> dict:
    """`state` moved as far as the chain goes now; `reason` and `failed` say why it stopped where it did.

    `acts` is the source repository's effective policy, `deploy_acts` the deploy repository's. `save` stores
    each step as it is reached, before the next external act: a kill after the tag push otherwise left the
    stored step at `version`, and the restart read the pushed tag as the last one and released nothing.
    """
    state.pop("reason", None)
    state["failed"] = False
    try:
        while state["step"] not in FINAL:
            held = deploy_acts if state["step"] in DEPLOY_STEPS else acts
            if state["step"] in DEPLOY_STEPS and not release.get("deploy_repo"):
                raise ReleaseError("the policy no longer declares deploy_repo, so the deploy this chain began is "
                                   "unknown; finish it by hand or declare it again")
            if held is None:
                raise ReleaseError("the deploy repository's policy was not read, so its acts are unknown")
            state["step"] = STEPS[state["step"]](state, release, held, world, list(types))
            if state["step"] not in FINAL:
                save(state)
    except Wait as stop:
        state.update(reason=str(stop), failed=stop.failed)
    except ReleaseError as error:
        state.update(reason=f"{state['step']} failed: {error}", failed=True)
    if state["step"] == "done" and "reason" not in state:
        state["reason"] = state.get("no_bump") or (f"released {state['tag']}"
                                                   + (f": {state['pr']}" if state.get("pr") else ""))
    return state


class Repositories:
    """What the chain reads and does, on disk: `git` in the lane's main checkout and the deploy checkout, `gh`
    for the deploy PR, and `verify` in a detached worktree of one of them.

    `environ` is the whole environment git, `gh` and `verify` run in; the lane passes its own. `frozen` and
    `ruling` read the hub; the lane passes them in (`sd_lane.release_chain`). `deploy` is the deploy
    repository's checkout, None for a tag-only release; `merge_method` is its policy's.
    """

    def __init__(self, main: pathlib.Path, environ: dict[str, str], frozen: Callable[[bool], str | None],
                 ruling: Callable[[str, str, str], str | None], *, deploy: pathlib.Path | None = None,
                 file: str = "", merge_method: str = "squash") -> None:
        # `environ` whole, never over `os.environ`: that put back what a caller dropped, such as GIT_DIR
        self.main, self.env, self.frozen, self.ruling = main, dict(environ), frozen, ruling
        self.deploy, self.file, self.merge_method = deploy, file, merge_method
        self._tips: dict[pathlib.Path, str] = {}
        self._tags: dict[str, str] | None = None  # origin's tags as `last_tag` read them, for `messages_since`
        self._gated: dict[str, str] = {}  # each PR's head the merge gates passed, which the merge is bound to

    def _run(self, *argv: str, cwd: pathlib.Path | None = None, ok: tuple[int, ...] = (0,), timeout: float = 120,
             strip: bool = True) -> str:
        """`argv`'s stdout in `cwd`, the main checkout by default; stripped unless `strip` is off, so a file
        read keeps its edge whitespace."""
        try:
            done = subprocess.run(list(argv), cwd=self.main if cwd is None else cwd, env=self.env,
                                  capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReleaseError(f"{' '.join(argv[:3])} did not finish: {error}") from None
        if done.returncode not in ok:
            raise ReleaseError(f"{' '.join(argv[:3])} exited {done.returncode}: "
                               f"{(done.stderr or done.stdout).strip()[-300:]}")
        return done.stdout.strip() if strip else done.stdout

    def _origin_tip(self, tree: pathlib.Path) -> str:
        """The commit origin's default branch names in `tree`, as origin advertises it, read and fetched once
        per chain run.

        Origin's `HEAD` symref and its commit come from one `ls-remote`, as `sd_lane.publish_head` reads them:
        `git fetch` never moves a local `origin/HEAD`, which kept naming master after origin moved to main.
        No tags are fetched: release history is origin's (`_origin_tags`), and `--tags` failed on a local tag
        at odds with origin's, as a would-clobber.
        """
        if tree not in self._tips:
            branch = sha = ""
            for line in self._run("git", "ls-remote", "--symref", "origin", "HEAD", cwd=tree).splitlines():
                left, _, name = line.partition("\t")
                if name == "HEAD" and left.startswith("ref: refs/heads/"):
                    branch = left.removeprefix("ref: refs/heads/")
                elif name == "HEAD":
                    sha = left
            if not branch or not sha:
                raise ReleaseError(f"origin advertises no default branch for {tree}, so its release commit is unknown")
            self._run("git", "fetch", "-q", "--no-tags", "origin", f"refs/heads/{branch}", cwd=tree)
            if not self._has(tree, sha):
                raise ReleaseError(f"origin's {branch} moved off {sha[:12]} during the fetch; the next run reads it again")
            self._tips[tree] = sha
        return self._tips[tree]

    def _has(self, tree: pathlib.Path, sha: str) -> bool:
        return bool(self._run("git", "rev-parse", "-q", "--verify", f"{sha}^{{commit}}", cwd=tree, ok=(0, 1)))

    def tip(self) -> str:
        return self._origin_tip(self.main)

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
            if self._has(self.main, sha) and self._run("git", "merge-base", sha, tip, ok=(0, 1)) == sha:
                return name
        return None

    def messages_since(self, tag: str | None, sha: str) -> list[str]:
        """The commit messages after origin's `tag`, by the commit origin's tag names, not a local one.

        A run that resumes past `version` never read origin's tags, so this reads them then.
        """
        if tag is not None and self._tags is None:
            self._tags = self._origin_tags()
        if tag is not None and tag not in (self._tags or {}):
            raise ReleaseError(f"origin holds no tag {tag}")
        span = f"{(self._tags or {})[tag]}..{sha}" if tag else sha
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

    def _deploy(self) -> pathlib.Path:
        if self.deploy is None or not self.deploy.is_dir():
            raise ReleaseError(f"the deploy repository's checkout {self.deploy} is not on this disk")
        return self.deploy

    def deployed(self) -> tuple[str, str]:
        """`file` as origin's default branch of the deploy repository holds it, raw, and that branch's commit."""
        deploy = self._deploy()
        sha = self._origin_tip(deploy)
        return self._run("git", "show", f"{sha}:{self.file}", cwd=deploy, strip=False), sha

    def open_bump(self, branch: str, text: str, message: str) -> str:
        """The open PR from `branch`, opened from origin's tip with `text` as the file when there is none yet.

        The branch carries the source checkout's name, so two repositories that share a deploy repository never
        meet on one `release/v1.2.0`. A PR a killed run opened is found by its branch, not opened again.
        """
        deploy, branch = self._deploy(), branch.replace("release/", f"release/{self.main.name}-", 1)
        listed = json.loads(self._run("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url",
                                      cwd=deploy) or "[]")
        if listed:  # bound to this bump: the branch must hold `text`, not another release's file
            self._pushed(deploy, branch, text)
            return listed[0]["url"]
        if self._run("git", "ls-remote", "origin", f"refs/heads/{branch}", cwd=deploy):
            self._pushed(deploy, branch, text)  # a push that landed before a failed `gh pr create`
        else:
            self._push_bump(deploy, branch, text, message)
        subject, _, body = message.partition("\n\n")
        return self._run("gh", "pr", "create", "--head", branch, "--title", subject, "--body", body, cwd=deploy)

    def _pushed(self, deploy: pathlib.Path, branch: str, text: str) -> None:
        """Reuse the release branch an earlier try pushed, or its open PR, only when it holds `text`."""
        self._run("git", "fetch", "-q", "--no-tags", "origin", f"refs/heads/{branch}", cwd=deploy)
        held = self._run("git", "show", f"FETCH_HEAD:{self.file}", cwd=deploy, strip=False)
        if held != text:
            raise ReleaseError(f"origin's {branch} holds another {self.file}; delete the branch or open its PR")

    def _push_bump(self, deploy: pathlib.Path, branch: str, text: str, message: str) -> None:
        """One commit on origin's tip in a detached worktree, pushed as `branch`; a failed push leaves nothing."""
        with tempfile.TemporaryDirectory(prefix="sd-release-") as scratch:
            tree = pathlib.Path(scratch) / "deploy"
            self._run("git", "worktree", "add", "-q", "--detach", str(tree), self._origin_tip(deploy), cwd=deploy)
            try:
                (tree / self.file).write_text(text, encoding="utf-8")
                self._run("git", "commit", "-q", "-m", message, "--", self.file, cwd=tree)
                self._run("git", "push", "-q", "origin", f"HEAD:refs/heads/{branch}", cwd=tree)
            finally:
                self._run("git", "worktree", "remove", "--force", str(tree), cwd=deploy, ok=(0, 128))

    def merged(self, url: str) -> str | None:
        """The commit GitHub merged `url` as, or None while it is not MERGED: a merge-queue add is not a merge."""
        held = json.loads(self._run("gh", "pr", "view", url, "--json", "state,mergeCommit", cwd=self._deploy()))
        if held.get("state") != "MERGED":
            return None
        sha = (held.get("mergeCommit") or {}).get("oid")
        if not sha:
            raise ReleaseError(f"{url} reads MERGED with no merge commit, so the commit to verify is unknown")
        return str(sha)

    def pr_state(self, url: str, policy: dict) -> str:
        """`green`, `pending: ...` or `red: ...`; no check at all is pending, never green, unless the policy's `ci`
        is Jenkins, whose build of the head then stands in for the GitHub checks.

        Green also needs what `sd-ship merge` holds a merge for under the deploy repository's `policy`: its
        `review.human` approvals of the head, and a green build of the head on its Jenkins `ci` (sd:6880).
        """
        held = json.loads(self._run("gh", "pr", "view", url, "--json", "state,number,headRefOid,statusCheckRollup",
                                    cwd=self._deploy()))
        if held.get("state") == "MERGED":  # `merged` read it open a moment ago; the next run verifies it
            return "pending: it merged as this run read it"
        if held.get("state") != "OPEN":
            return f"red: the PR is {str(held.get('state')).lower()}"
        checks = held.get("statusCheckRollup") or []
        if not checks and (policy.get("ci") or {}).get("provider") != "jenkins":
            return "pending: no check has reported yet"
        results = [str(check.get("conclusion") or check.get("state") or "").upper() for check in checks]
        red = [str(check.get("name") or check.get("context")) for check, result in zip(checks, results, strict=True)
               if result and result not in (*PASSED, "PENDING", "EXPECTED", "QUEUED", "IN_PROGRESS")]
        if red:
            return f"red: {', '.join(red)} failed"
        waiting = sum(result not in PASSED for result in results)
        if waiting:
            return f"pending: {waiting} of {len(checks)} checks running"
        head = str(held.get("headRefOid") or "")
        held_back = self._policy_gates(int(held.get("number") or 0), head, policy)
        if held_back:
            return held_back
        self._gated[url] = head
        return "green"

    def _policy_gates(self, number: int, head: str, policy: dict) -> str | None:
        """What the deploy policy still holds the merge of `head` for, as `sd-ship merge`'s `policy_hold` and
        Jenkins wait read it; None when nothing does."""
        need = (policy.get("review") or {}).get("human") or 0
        if need:
            lines = self._run("gh", "api", "--paginate", f"repos/{{owner}}/{{repo}}/pulls/{number}/reviews",
                              "--jq", ".[]", cwd=self._deploy())
            approved = sd_repo_policy.approvals([json.loads(line) for line in lines.splitlines() if line.strip()], head)
            if len(approved) < need:
                return (f"pending: the deploy policy requires {need} human approval{'s' if need > 1 else ''} of "
                        f"{head[:12]}; {len(approved)} approve it")
        ci = policy.get("ci") or {}
        if ci.get("provider") == "jenkins":
            try:
                sd_ship_jenkins.wait_green(ci, number, head, wait_seconds=0)
            except sd_ship_jenkins.Refusal as refused:
                return f"{'red' if refused.workflow['blocker']['code'] == 'ci_not_passing' else 'pending'}: {refused}"
        return None

    def merge_bump(self, url: str) -> None:
        """Merge at the head `pr_state` gated, so a push after the gates read it refuses rather than lands."""
        if url not in self._gated:
            raise ReleaseError(f"{url} was not gated in this run; the next run reads its gates again")
        self._run("gh", "pr", "merge", url, f"--{self.merge_method}", "--match-head-commit", self._gated[url],
                  cwd=self._deploy())

    def verify(self, command: str, tag: str, version: str, sha: str, deploy: bool = False) -> None:
        """`command` in a detached worktree at `sha`, with the tag and version in its environment: the merged
        commit of the deploy repository when `deploy`, else the tagged one of the source.

        Not in a checkout: the landing does not always move the main one to origin's tip (a pinned or deploying
        checkout, a failed fast-forward), and the deploy one is never moved, so its files could be older than the
        commit released. A commit the checkout lacks is fetched from origin's default branch.
        """
        where = self._deploy() if deploy else self.main
        if not self._has(where, sha):
            self._tips.pop(where, None)  # this run read it before the merge: read and fetch it again
            self._origin_tip(where)
            if not self._has(where, sha):
                raise ReleaseError(f"{sha[:12]} is not on origin's default branch of {where}")
        with tempfile.TemporaryDirectory(prefix="sd-release-") as scratch:
            tree = pathlib.Path(scratch) / "verify"
            self._run("git", "worktree", "add", "-q", "--detach", str(tree), sha, cwd=where)
            try:
                done = sd_lib.run_group(["sh", "-c", command], cwd=tree, timeout=VERIFY_SECONDS,
                                        env={**self.env, "SD_RELEASE_TAG": tag, "SD_RELEASE_VERSION": version})
            except sd_lib.GroupTimeout:
                raise ReleaseError(f"{command!r} ran past {VERIFY_SECONDS}s") from None
            finally:
                self._run("git", "worktree", "remove", "--force", str(tree), cwd=where, ok=(0, 128))
        if done.returncode:
            raise ReleaseError(f"{command!r} exited {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}")
