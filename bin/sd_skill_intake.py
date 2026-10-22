"""`sd skill intake`: judge a GitHub skill against the installed set; install only on approval.

The fetched skill is untrusted data. It is fetched into a fresh empty
directory and read as git blobs: nothing is checked out, so no file of it
runs, no hook of it fires and no link of it is followed. No model reads it:
risk, match and value are scored here by rules a reader can check, and the
verdict is advice to the operator, never an approval.

The pre-screen, lint, name transform and provenance block are
`sd-skill-adopt`'s, loaded as its sibling, so one set of rules guards both
doors. Provenance stays where that tool already writes it, in the skill's own
`## Provenance` section; a re-import reads the URL back from there.

Installing writes `--approve REVISION` only, where the revision is the one the
report printed. It binds the upstream commit, the fetched bytes, the target
and the installed copy, so an approval of one report cannot install what a
later fetch or a local edit changed. An install keeps the copy it replaced,
or an `absent` marker, beside the root (`kept`), one per skill (system sd:5779).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import difflib
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
from typing import Any

import sd_lib

ADOPT = sd_lib.sibling("sd_skill_adopt", "sd-skill-adopt")

GITHUB = "https://github.com/"
SKILL_FILE = "SKILL.md"
PACK_NAME_RE = re.compile(r"sd-[a-z0-9-]+")
TOOL = "sd skill intake"
#: The one line `with_provenance` writes for this tool, matched whole. Nothing
#: else in a skill names its source: the body is upstream's text.
PROVENANCE_LINE_RE = re.compile(
    r"Adopted by `sd skill intake` on \d{4}-\d{2}-\d{2} from `(https://github\.com/[^`\s]+)` "
    r"at revision `([0-9a-f]{40}) \(sha256:[0-9a-f]{16}\)`\.")

#: The catalog's own limits (`skills_catalog._snapshot`), so an installed
#: skill never breaks `sd skill list`.
MAX_FILES = 200
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 8 * MAX_FILE
GIT_TIMEOUT = 120

#: Overlap at or above this folds the candidate into the nearest skill.
#: Measured on 2026-10-13: the closest distinct pair among the installed
#: skills scored 0.23, a copy of an installed skill 1.00.
FOLD_AT = 0.35
#: Fewer instruction lines than this teach nothing worth a skill.
MIN_BODY_LINES = 5
DIFF_LINES = 400

#: Where an install stages, beside the skills root rather than in it, so
#: `sd skill list` never reads a half-written skill.
STAGING = ".sd-skill-intake"

SCRIPT_SUFFIXES = frozenset({".sh", ".bash", ".zsh", ".fish", ".py", ".js", ".mjs", ".cjs", ".ts",
                             ".rb", ".pl", ".php", ".ps1", ".bat", ".cmd"})
HOOK_FILES = frozenset({"hooks.json", "settings.json", "settings.local.json"})
#: Variables that point git at another repository; the fetch runs in its own.
GIT_LOCATION = frozenset({"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                          "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE"})
STOPWORDS = frozenset(
    "about after also another any before being can does each else from have into its more must "
    "only other over same should skill than that their them then there these they this those "
    "through under user users wants what when where which while will with without your".split())


class IntakeError(Exception):
    """An intake that cannot answer or may not write. Nothing was installed."""


# --------------------------------------------------------------------------
# Fetch: one fresh directory, blobs only
# --------------------------------------------------------------------------


def parse_url(url: str) -> tuple[str, list[str], str]:
    """`(clone URL, the parts after tree/ or blob/, kind)` for a GitHub skill URL."""

    if not url.startswith(GITHUB) or any(ch.isspace() or ch == "`" for ch in url):
        raise IntakeError(f"not a GitHub URL: {url!r}; give https://github.com/<owner>/<repo>/tree/<ref>/<path>")
    parts = [part for part in url[len(GITHUB):].split("?")[0].split("#")[0].split("/") if part]
    if len(parts) < 2 or any(part in (".", "..") for part in parts):
        raise IntakeError(f"no repository in {url}")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    kind = parts[2] if len(parts) > 2 else ""
    if kind not in ("", "tree", "blob") or (kind and len(parts) < 4):
        raise IntakeError(f"cannot read a ref and path from {url}")
    return f"{GITHUB}{owner}/{repo}.git", parts[3:], kind


def _git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in GIT_LOCATION}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"})
    return sd_lib.without_fsmonitor(env)


def _git(work: pathlib.Path, *args: str, text: bool = True) -> Any:
    """One git call in the fetch directory. A failure is an error, never an empty answer."""

    try:
        done = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(work), *args],
                              capture_output=True, text=text, timeout=GIT_TIMEOUT, env=_git_env(), check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise IntakeError(f"git {args[0]} did not finish: {error}") from error
    if done.returncode:
        stderr = done.stderr if text else done.stderr.decode("utf-8", "replace")
        raise IntakeError(f"git {args[0]} failed: {_printable(stderr.strip())[:300]}")
    return done.stdout


def _resolve(work: pathlib.Path, remote: str, parts: list[str]) -> tuple[str, list[str]]:
    """The ref to fetch and the path inside it. A branch name may hold slashes."""

    if not parts:
        return "HEAD", []
    if re.fullmatch(r"[0-9a-f]{40}", parts[0]):
        return parts[0], parts[1:]
    refs = set()
    for line in _git(work, "ls-remote", "--heads", "--tags", remote).splitlines():
        name = line.split("\t", 1)[-1]
        refs.add(name.removeprefix("refs/heads/").removeprefix("refs/tags/"))
    for cut in range(len(parts), 0, -1):
        if "/".join(parts[:cut]) in refs:
            return "/".join(parts[:cut]), parts[cut:]
    raise IntakeError(f"no branch or tag of {remote} starts {'/'.join(parts)}")


def _listing(work: pathlib.Path, path: str) -> list[tuple[str, str, str, str]]:
    """`(mode, oid, size, path)` for every entry under `path` at the fetched commit."""

    raw = _git(work, "ls-tree", "-r", "-l", "-z", "--full-tree", "FETCH_HEAD", "--", path or ".")
    entries = []
    for record in raw.split("\0"):
        if record:
            meta, name = record.split("\t", 1)
            mode, _kind, oid, size = meta.split()
            if not path or name == path or name.startswith(path + "/"):
                entries.append((mode, oid, size, name))
    return entries


def fetch_skill(url: str) -> dict[str, Any]:
    """The skill at `url`: its commit, its path and every file as `(mode, bytes)`."""

    remote, parts, kind = parse_url(url)
    with tempfile.TemporaryDirectory(prefix="sd-skill-intake-") as scratch:
        work = pathlib.Path(scratch) / "fetch"
        _git(pathlib.Path(scratch), "init", "-q", "--template=", str(work))
        ref, rest = _resolve(work, remote, parts)
        if kind == "blob" and rest and rest[-1] == SKILL_FILE:
            rest = rest[:-1]
        _git(work, "fetch", "-q", "--depth", "1", "--no-tags", "--no-recurse-submodules", remote, ref)
        commit = _git(work, "rev-parse", "FETCH_HEAD^{commit}").strip()
        prefix = "/".join(rest)
        return _skill_at(work, _listing(work, prefix), url, commit, prefix)


def _skill_at(work: pathlib.Path, entries: list[tuple[str, str, str, str]], url: str, commit: str,
              prefix: str) -> dict[str, Any]:
    """The skill whose `entries` sit under `prefix` at the fetched commit, its blobs read and bounded."""

    sizes = [int(size) for _m, _o, size, _n in entries if size.isdigit()]
    if len(entries) > MAX_FILES or sum(sizes) > MAX_TOTAL or any(size > MAX_FILE for size in sizes):
        raise IntakeError(f"the skill at {url} exceeds {MAX_FILES} files, {MAX_FILE} bytes a file "
                          f"or {MAX_TOTAL} bytes in all")
    files = {}
    for mode, oid, _size, name in entries:
        # A link or submodule has no blob worth reading; `risk` refuses it by mode.
        linked = mode in ("120000", "160000")
        files[name[len(prefix) + 1:] if prefix else name] = (
            mode, b"" if linked else _git(work, "cat-file", "blob", oid, text=False))
    if SKILL_FILE not in files:
        raise IntakeError(f"no {SKILL_FILE} at {prefix or 'the repository root'} of {url}")
    return {"url": url, "commit": commit, "path": prefix, "files": files}


# --------------------------------------------------------------------------
# Score: risk, match, value
# --------------------------------------------------------------------------


def _finding(severity: str, rule: str, file: str, line: int = 0) -> dict[str, Any]:
    return {"severity": severity, "rule": rule, "file": file, "line": line}


def _file_risk(name: str, mode: str, body: bytes) -> list[dict[str, Any]]:
    if mode in ("120000", "160000"):
        return [_finding(ADOPT.REFUSE, "link-or-submodule", name)]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if "\0" in text or (body and not text):
        return [_finding(ADOPT.REFUSE, "unscreenable-binary", name)]
    found = [_finding(f.severity, f.rule, name, f.line) for f in ADOPT.prescreen(text)]
    if mode == "100755" or text.startswith("#!") or pathlib.PurePosixPath(name).suffix in SCRIPT_SUFFIXES:
        found.append(_finding(ADOPT.WARN, "ships-script", name))
    if pathlib.PurePosixPath(name).name in HOOK_FILES:
        found.append(_finding(ADOPT.REFUSE, "ships-hook-config", name))
    return found


def risk(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Scripts, network calls, secrets, hooks and text aimed at the agent, file by file."""

    found = []
    for name, (mode, body) in sorted(candidate["files"].items()):
        found += _file_risk(name, mode, body)
    text = candidate["files"][SKILL_FILE][1].decode("utf-8", "replace")
    head = text.split("\n---", 1)[0] if text.startswith("---\n") else ""
    dropped = text.find("\n" + ADOPT.PROVENANCE_HEADING)
    if dropped != -1:
        # `with_provenance` cuts here: what follows never lands, and never reads as ours.
        found.append(_finding(ADOPT.WARN, "upstream-provenance-dropped", SKILL_FILE, text.count("\n", 0, dropped) + 2))
    if re.search(r"(?m)^hooks\s*:", head):
        found.append(_finding(ADOPT.REFUSE, "declares-hooks", SKILL_FILE, 1))
    fields = sd_lib.parse_frontmatter(text) or {}
    name = fields.get("name", "")
    found += [_finding(f.severity, f.rule, SKILL_FILE, f.line) for f in ADOPT.lint(name, text)]
    if fields.get(ADOPT.MARKER) == "true":
        found.append(_finding(ADOPT.REFUSE, "adopted-surface-claims-command-authority", SKILL_FILE, 1))
    return found


def _words(text: str) -> set[str]:
    head = text.split("\n---", 1)[0] if text.startswith("---\n") else text[:600]
    head = re.sub(r"(?m)^[A-Za-z_-]+:", " ", head)
    return {word for word in re.findall(r"[a-z][a-z0-9]{3,}", head.lower()) if word not in STOPWORDS}


def installed_skills(root: pathlib.Path, home: pathlib.Path) -> dict[str, str]:
    """Name to SKILL.md text for the pack's two roots and the user's skills."""

    found: dict[str, str] = {}
    for directory in (root / "skills", root / "contrib", home / ".claude" / "skills"):
        for path in sorted(directory.glob(f"*/{SKILL_FILE}")) if directory.is_dir() else []:
            found.setdefault(path.parent.name, path.read_text(encoding="utf-8", errors="replace"))
    return found


def match(text: str, installed: dict[str, str], *, skip: set[str]) -> list[dict[str, Any]]:
    """The three installed skills whose name and description share the most words with this one."""

    mine = _words(text)
    scores: list[tuple[float, str]] = []
    for name, other in installed.items():
        theirs = _words(other)
        if name not in skip and mine & theirs:
            scores.append((round(len(mine & theirs) / len(mine | theirs), 2), name))
    ranked = sorted(scores, key=lambda score: (-score[0], score[1]))[:3]
    return [{"skill": name, "overlap": overlap} for overlap, name in ranked]


def _body(text: str) -> str:
    body = text.split("\n---", 1)[1] if text.startswith("---\n") and "\n---" in text else text
    return body.split("\n" + ADOPT.PROVENANCE_HEADING, 1)[0]


def value(text: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    lines = [line for line in _body(text).splitlines()[1:] if line.strip()]
    nearest = matches[0]["overlap"] if matches else 0.0
    return {"instruction_lines": len(lines), "novelty": round(1 - nearest, 2)}


def verdict(findings: list[dict[str, Any]], matches: list[dict[str, Any]], worth: dict[str, Any]) -> dict[str, str]:
    refused = sorted({f["rule"] for f in findings if f["severity"] == ADOPT.REFUSE})
    if refused:
        return {"action": "decline", "reason": "refused: " + ", ".join(refused)}
    if worth["instruction_lines"] < MIN_BODY_LINES:
        return {"action": "decline", "reason": f"value: under {MIN_BODY_LINES} instruction lines"}
    if matches and matches[0]["overlap"] >= FOLD_AT:
        return {"action": "fold", "reason": f"into {matches[0]['skill']}: overlap {matches[0]['overlap']}"}
    return {"action": "install", "reason": "no refusal, enough instructions, no close match"}


def _landing(files: dict[str, bytes], scope: str) -> list[dict[str, Any]]:
    """Refusals of what would land: the catalog must still read every skill afterwards."""

    if not files:
        return []
    found = []
    if max(map(len, files.values())) > MAX_FILE or sum(map(len, files.values())) > MAX_TOTAL:
        found.append(_finding(ADOPT.REFUSE, "oversized-after-provenance", SKILL_FILE))
    if scope == "pack":
        imported = sd_lib.import_sd_db()
        if imported.module is None:
            raise IntakeError(f"cannot check the skill against the catalog: {imported.problem}")
        # Deferred: only a pack install needs the catalog.
        from sd_db import skills_catalog  # noqa: PLC0415
        from sd_db.sources.frontmatter import split  # noqa: PLC0415

        try:
            # The catalog's own reader: a description it cannot read breaks `sd skill list`.
            skills_catalog._description(split(files[SKILL_FILE].decode("utf-8"))[0])
        except (skills_catalog.workflow.WorkflowError, ValueError):
            found.append(_finding(ADOPT.REFUSE, "catalog-unreadable", SKILL_FILE, 1))
    return found


# --------------------------------------------------------------------------
# Where it goes, and what is there now
# --------------------------------------------------------------------------


def source_of(skill_dir: pathlib.Path) -> tuple[str, str] | None:
    """`(URL, commit)` this tool recorded for an installed skill, or None.

    Read from the trailing Provenance section alone, from the last line there
    that is this tool's line whole; a line after it is a local edit.
    `with_provenance` cuts the text at the first Provenance heading before it
    writes its own, so a skill this tool installed holds exactly one, at the
    end; a phrase planted anywhere in upstream's body is never read as the
    source. A linked folder is never this tool's: it writes none.
    """

    path = skill_dir / SKILL_FILE
    if skill_dir.is_symlink() or path.is_symlink() or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    heading = "\n" + ADOPT.PROVENANCE_HEADING
    start = text.find(heading)
    if start == -1 or text.rfind(heading) != start or not text[start + len(heading):].startswith("\n"):
        return None
    entries = [found for line in text[start + len(heading):].splitlines()
               if (found := PROVENANCE_LINE_RE.fullmatch(line))]
    return (entries[-1][1], entries[-1][2]) if entries else None


def scope_roots(scope: str, root: pathlib.Path, home: pathlib.Path) -> list[pathlib.Path]:
    """Where a skill of this scope may live, the install root first."""

    return [root / "contrib", root / "skills"] if scope == "pack" else [home / ".claude" / "skills"]


def locate(name: str, scope: str | None, root: pathlib.Path, home: pathlib.Path) -> tuple[str, pathlib.Path, str]:
    """`(scope, directory, URL)` of an installed skill that records a GitHub source."""

    for each in ([scope] if scope else ["pack", "user"]):
        for directory in scope_roots(each, root, home):
            recorded = source_of(directory / name)
            if recorded:
                return each, directory / name, recorded[0]
    raise IntakeError(f"no installed skill {name} records a GitHub source; give its URL")


def installed_digests(directory: pathlib.Path) -> dict[str, str]:
    """Relative path to content digest for what is installed; a link is named, never followed.

    A file or a link where the skill folder belongs is named too, so it never reads as nothing there.
    """

    if directory.is_symlink() or (_present(directory) and not directory.is_dir()):
        return {".": "symlink" if directory.is_symlink() else "file"}
    if not directory.is_dir():
        return {}
    files = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            files[relative] = "symlink"
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def transform(candidate: dict[str, Any], claimed: str, target: str, today: str) -> dict[str, bytes]:
    """What lands on disk: the name moved to the target and the Provenance section written."""

    text = candidate["files"][SKILL_FILE][1].decode("utf-8", "replace")
    if target != claimed:
        text = text.replace(f"name: {claimed}", f"name: {target}", 1).replace(f"# {claimed}", f"# {target}", 1)
    digest = hashlib.sha256(candidate["files"][SKILL_FILE][1]).hexdigest()[:16]
    text = ADOPT.with_provenance(text, candidate["url"], f"{candidate['commit']} (sha256:{digest})", today, tool=TOOL)
    files = {name: body for name, (_mode, body) in candidate["files"].items()}
    files[SKILL_FILE] = text.encode("utf-8")
    return files


def _printable(text: str) -> str:
    """Text with control and format characters escaped, so a diff cannot drive the terminal."""

    return "".join(ch if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cf", "Co", "Cs")
                   else f"\\u{ord(ch):04x}" for ch in text)


def _lines(name: str, data: bytes | None) -> list[str]:
    if data is None:
        return []
    text = data.decode("utf-8", "replace")
    if name == SKILL_FILE:
        text = text.split("\n" + ADOPT.PROVENANCE_HEADING, 1)[0].rstrip("\n") + "\n"
    return text.splitlines(keepends=True)


def installed_diff(directory: pathlib.Path, files: dict[str, bytes], theirs: str = "upstream") -> list[str]:
    """Installed against upstream, or the kept copy, file by file, Provenance left out of both sides."""

    names = sorted(set(installed_digests(directory)) | set(files))
    out: list[str] = []
    for name in names:
        path = directory / name
        installed = path.read_bytes() if path.is_file() and not path.is_symlink() else None
        out += difflib.unified_diff(_lines(name, installed), _lines(name, files.get(name)),
                                    f"installed/{name}", f"{theirs}/{name}")
    return [_printable(line.rstrip("\n")) for line in out]


def approval_revision(candidate: dict[str, Any], destination: pathlib.Path) -> str:
    """What an approval binds: the commit, the fetched bytes, the target and the installed copy."""

    bound = {"url": candidate["url"], "commit": candidate["commit"], "target": str(destination),
             "files": {name: [mode, hashlib.sha256(body).hexdigest()] for name, (mode, body) in candidate["files"].items()},
             "installed": installed_digests(destination)}
    return hashlib.sha256(json.dumps(bound, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------
# Install in steps, and finish or undo a stopped one
# --------------------------------------------------------------------------


def staging(destination: pathlib.Path) -> pathlib.Path:
    return destination.parent.parent / STAGING / destination.parent.name / destination.name


def _stage(stage: pathlib.Path, files: dict[str, bytes]) -> None:
    new = stage / "new"
    for name, body in files.items():
        path = new / name
        if not path.resolve().is_relative_to(new.resolve()):
            raise IntakeError(f"{_printable(name)} resolves outside the skill")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        path.chmod(0o644)


def _present(path: pathlib.Path) -> bool:
    """There, counting a link whose target no longer resolves from where it sits."""

    return os.path.lexists(path)


def _swap_out(destination: pathlib.Path, stage: pathlib.Path) -> None:
    if _present(destination):
        os.replace(destination, stage / "old")


def _swap_in(destination: pathlib.Path, stage: pathlib.Path) -> None:
    os.replace(stage / "new", destination)


def _drop(stage: pathlib.Path) -> None:
    """Remove the stage, with the staging folders above it that hold nothing else."""

    top = stage
    for parent in (stage.parent, stage.parent.parent):
        if list(parent.iterdir()) != [top]:
            break
        top = parent
    _discard(top)


def _discard(top: pathlib.Path) -> None:
    """Remove a folder of the intake's own: a stage, or a kept copy rotated out."""

    shutil.rmtree(top)  # the intake's own staging folder, never a work item (sd:3560)


def kept(destination: pathlib.Path, suffix: str = "") -> pathlib.Path:
    """The previous copy an install keeps (system sd:5779): `skill/`, or an `absent` marker, and `wrote.json`.

    It sits in the staging folder, outside the skill roots, so `sd skill list`
    never reads it. `~next` and `~prev` are the rotation's names: `~` is never
    in a skill name.
    """

    return destination.parent.parent / STAGING / "kept" / destination.parent.name / (destination.name + suffix)


def _keep(destination: pathlib.Path, stage: pathlib.Path) -> None:
    """Write the new kept copy under its `~next` name, then rotate it in.

    `wrote.json` records what the intake put at the destination, so a rollback
    can tell a local edit since.
    """

    following = kept(destination, "~next")
    if _present(following):
        _discard(following)  # an earlier stop's partial write; the stage still holds its source
    following.mkdir(parents=True)
    # What the stage meant to put there, recorded before the swap: a recovery after a local edit keeps the edit visible.
    planned = stage / "wrote.json"
    wrote = planned.read_text(encoding="utf-8") if _present(planned) else json.dumps(installed_digests(destination))
    (following / "wrote.json").write_text(wrote, encoding="utf-8")
    if _present(stage / "old"):
        os.replace(stage / "old", following / "skill")
    else:
        (following / "absent").touch()
    _settle(destination)


def _settle(destination: pathlib.Path) -> None:
    """Rename a written `~next` over the kept copy, through `~prev`; each stop leaves a state this finishes."""

    current, following, previous = kept(destination), kept(destination, "~next"), kept(destination, "~prev")
    if _present(following):
        if _present(current):
            if _present(previous):
                _discard(previous)
            os.replace(current, previous)
        os.replace(following, current)
    if _present(previous):
        _discard(previous)


def install(destination: pathlib.Path, files: dict[str, bytes]) -> None:
    """Stage beside the root, move the old copy aside, move the new one in, keep the old.

    A stop between any two steps leaves state `recover` finishes or undoes.
    """

    stage = staging(destination)
    stage.mkdir(parents=True, exist_ok=True)
    _stage(stage, files)
    _plan(stage, {name: hashlib.sha256(body).hexdigest() for name, body in files.items()})
    if not _present(destination):
        (stage / "absent").touch()
    _swap_out(destination, stage)
    _swap_in(destination, stage)
    _keep(destination, stage)
    _drop(stage)


def _plan(stage: pathlib.Path, digests: dict[str, str]) -> None:
    (stage / "wrote.json").write_text(json.dumps(digests, sort_keys=True), encoding="utf-8")


def recover(roots: list[pathlib.Path]) -> list[str]:
    """Finish or undo every install a stop left behind under these roots."""

    done = []
    for root in roots:
        base = root.parent / STAGING / root.name
        for stage in sorted(base.iterdir()) if base.is_dir() else []:
            destination = root / stage.name
            old, new = _present(stage / "old"), _present(stage / "new")
            # A rollback restores a copy this tool kept, its own or one written by hand before;
            # a rollback that removes the skill swaps nothing in.
            rollback = _present(stage / "rollback")
            what = "rollback" if rollback else "install"
            if old and not _present(destination) and (new or not rollback):
                os.replace(stage / "old", destination)
                done.append(f"undid a stopped {what} of {destination}: the previous copy is back")
            elif old and not rollback and source_of(destination) is None:
                raise IntakeError(f"{destination} is not one this tool wrote, and the previous copy waits in "
                                  f"{stage / 'old'}; move one of them by hand")
            elif old or (_present(stage / "absent") and not new):
                _keep(destination, stage)
                done.append(f"finished a stopped {what} of {destination}: kept the previous copy")
            elif new:
                done.append(f"dropped an unfinished stage of {destination}")
            elif _present(kept(destination, "~next")) or _present(kept(destination, "~prev")):
                _settle(destination)
                done.append(f"finished a stopped install of {destination}: kept the previous copy")
            else:
                done.append(f"dropped the empty stage of {destination}")
            _drop(stage)
    return done


# --------------------------------------------------------------------------
# Roll back to the kept copy, and the pack skills an import informed (system sd:5779)
# --------------------------------------------------------------------------

#: A repository a Lineage or Provenance section names, as prose writes it.
MENTION_RE = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100})")
INFORMING = ("## Lineage", ADOPT.PROVENANCE_HEADING)


def _informing(text: str) -> str:
    """The text of the skill's `## Lineage` and `## Provenance` sections."""

    out, inside = [], False
    for line in text.splitlines():
        if line.startswith(("# ", "## ")):
            inside = line.rstrip() in INFORMING
        elif inside:
            out.append(line)
    return "\n".join(out)


def informed(url: str | None, root: pathlib.Path, skip: set[str]) -> list[dict[str, Any]]:
    """Each pack skill whose Lineage or Provenance names the repository of `url`, with the commits that added it.

    A failed `git log` leaves `commits` None and says why in `unknown`: never "no commit".
    """

    repo = repo_of(url) if url else None
    if repo is None:
        return []
    wanted = repo.removeprefix(GITHUB).lower()
    rows = []
    for directory in (root / "skills", root / "contrib"):
        for path in sorted(directory.glob(f"*/{SKILL_FILE}")) if directory.is_dir() else []:
            if path.parent.name in skip:
                continue
            names = sorted({f"github.com/{found[1]}/{found[2].rstrip('.').removesuffix('.git')}"
                            for found in MENTION_RE.finditer(_informing(path.read_text(encoding="utf-8", errors="replace")))
                            if f"{found[1]}/{found[2].rstrip('.').removesuffix('.git')}".lower() == wanted})
            if not names:
                continue
            relative = path.relative_to(root).as_posix()
            try:
                commits, unknown = _git(root, "log", "--format=%h", "-S", names[0], "--", relative).split(), None
            except IntakeError as error:
                commits, unknown = None, str(error)
            rows.append({"skill": path.parent.name, "path": relative, "names": names[0], "commits": commits,
                         "unknown": unknown})
    return rows


def _informed_text(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["informed: none"]
    return ["informed:"] + [f"  {row['skill']} ({row['path']}) names {row['names']}: "
                            + (f"unknown: {row['unknown']}" if row["commits"] is None
                               else ", ".join(row["commits"]) or "no commit adds it") for row in rows]


def _held(name: str, scope: str | None, root: pathlib.Path, home: pathlib.Path) -> tuple[str, pathlib.Path]:
    """`(scope, destination)` of the skill with a kept copy."""

    if not ADOPT.SAFE_NAME_RE.match(name):
        raise IntakeError(f"--rollback takes the name of an installed skill, not {_printable(name)!r}")
    for each in ([scope] if scope else ["pack", "user"]):
        for directory in scope_roots(each, root, home):
            if _present(kept(directory / name)):
                return each, directory / name
    raise IntakeError(f"no kept copy of {name}: only an install by `{TOOL}` keeps one; nothing to roll back")


def _committed(root: pathlib.Path, destination: pathlib.Path) -> str | None:
    """The commit that holds a pack skill git tracks and the tree leaves clean; else None. A failed git raises."""

    if not any((each / ".git").exists() for each in (root, *root.parents)):
        return None
    relative = destination.relative_to(root).as_posix()
    try:
        if not _git(root, "ls-files", "--deduplicate", "--", relative).strip() or _git(root, "status", "--porcelain", "--", relative).strip():
            return None
        return _git(root, "log", "-1", "--format=%h", "--", relative).strip() or None
    except IntakeError as error:
        raise IntakeError(f"cannot tell whether git holds {destination}: {error}; nothing written") from error


def _files(folder: pathlib.Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in sorted(folder.rglob("*")) if path.is_file() and not path.is_symlink()}


def _roll(destination: pathlib.Path, restore: pathlib.Path | None) -> None:
    """The install's steps, from the kept copy: the replaced copy becomes the kept one."""

    stage = staging(destination)
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "rollback").touch()
    if restore is not None:
        shutil.copytree(restore, stage / "new", symlinks=True)
    _plan(stage, installed_digests(stage / "new") if restore is not None else {})
    if not _present(destination):
        (stage / "absent").touch()
    _swap_out(destination, stage)
    if restore is not None:
        _swap_in(destination, stage)
    _keep(destination, stage)
    _drop(stage)


def rollback(name: str, *, scope: str | None, approve: str | None, root: pathlib.Path,
             home: pathlib.Path) -> dict[str, Any]:
    """Report the swap of an installed skill with its kept copy; with `approve`, make it.

    Refused when the installed copy changed since the intake wrote it, and for a
    pack skill git holds clean: the lane moves the pack, through `git revert`.
    """

    recovered = recover(scope_roots("pack", root, home) + scope_roots("user", root, home))
    scope, destination = _held(name, scope, root, home)
    entry = kept(destination)
    try:
        wrote = json.loads((entry / "wrote.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise IntakeError(f"cannot read {entry / 'wrote.json'}: {error}; nothing written") from error
    now = installed_digests(destination)
    changed = sorted(path for path in set(wrote) | set(now) if wrote.get(path) != now.get(path))
    if changed:
        raise IntakeError(f"{destination} changed since the intake wrote it ({', '.join(map(_printable, changed))}): "
                          "a local edit; nothing written")
    held = _committed(root, destination) if scope == "pack" else None
    if held:
        raise IntakeError(f"{destination} is committed in the pack at {held}; revert it through the lane: "
                          f"git revert {held}; nothing written")
    restore = entry / "skill" if _present(entry / "skill") else None
    installed, held_copy = source_of(destination), source_of(restore) if restore else None
    source = installed or held_copy
    report = {"skill": name, "scope": scope, "destination": str(destination), "kept": str(entry),
              "mode": "rollback" if restore else "remove",
              "installed_commit": installed[1] if installed else None, "kept_commit": held_copy[1] if held_copy else None,
              "diff": installed_diff(destination, _files(restore) if restore else {}, "kept"),
              "informed": informed(source[0] if source else None, root, {name}),
              "revision": hashlib.sha256(json.dumps({"rollback": str(destination), "installed": now,
                                                     "kept": installed_digests(entry)}, sort_keys=True).encode()).hexdigest()[:16],
              "recovered": recovered, "rolled_back": False}
    if approve is None:
        return report
    if approve != report["revision"]:
        raise IntakeError(f"approved revision {approve} is not this report's {report['revision']}: "
                          "the installed or the kept copy changed; nothing written")
    _roll(destination, restore)
    report["rolled_back"] = True
    return report


def rollback_text(report: dict[str, Any]) -> str:
    out = [f"skill: {report['skill']} ({report['scope']}) -> {report['destination']}", f"kept: {report['kept']}"]
    out += [f"recovered: {line}" for line in report["recovered"]]
    out.append("mode: remove: the intake installed this skill new; a rollback removes it" if report["mode"] == "remove"
               else f"mode: rollback: restores the kept copy (commit {report['kept_commit'] or 'not recorded'})")
    out += _informed_text(report["informed"])
    shown = report["diff"][:DIFF_LINES]
    out += ["diff:", *shown] if shown else ["diff: none"]
    if len(report["diff"]) > DIFF_LINES:
        out.append(f"... {len(report['diff']) - DIFF_LINES} more diff lines; --json holds them all")
    out.append(f"revision: {report['revision']}")
    if report["rolled_back"]:
        out.append(f"rolled back: {report['destination']}; the replaced copy is kept, so a second rollback undoes this")
    else:
        out.append(f"approve: sd skill intake {report['skill']} --rollback --scope {report['scope']} "
                   f"--approve {report['revision']}")
    return _printable("\n".join(out))


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def _target(claimed: str, scope: str, url: str, root: pathlib.Path, home: pathlib.Path) -> tuple[pathlib.Path, list[dict[str, Any]]]:
    """Where the candidate lands, and any refusal of that name."""

    roots = scope_roots(scope, root, home)
    taken = {path.parent.name for each in roots for path in ADOPT.skill_files(each)}
    name = claimed if scope == "user" or claimed.startswith(ADOPT.PREFIX) else ADOPT.PREFIX + claimed
    destination = next((each / name for each in roots if _present(each / name)), roots[0] / name)
    own = source_of(destination)
    ours = own is not None and own[0] == url
    if ours:
        taken.discard(name)
    _name, collisions = ADOPT.canonical_name(claimed, scope, taken)
    found = [_finding(f.severity, f.rule, SKILL_FILE, f.line) for f in collisions]
    if _present(destination) and not ours:
        # Whatever stands there, a folder with no SKILL.md, a file or another
        # tool's skill, an install would replace and then delete it.
        found.append(_finding(ADOPT.REFUSE, "destination-not-from-this-source", name))
    if scope == "pack" and not PACK_NAME_RE.fullmatch(name):
        found.append(_finding(ADOPT.REFUSE, "pack-name-shape", SKILL_FILE, 1))
    if destination.is_symlink():
        # Something else manages a linked skill folder; an install would cut the link.
        found.append(_finding(ADOPT.REFUSE, "destination-is-a-link", name))
    return destination, found


def evaluate(source: str, scope: str | None, root: pathlib.Path, home: pathlib.Path, today: str) -> dict[str, Any]:
    """The report. Reads only, apart from finishing or undoing a stopped install."""

    recovered = recover(scope_roots("pack", root, home) + scope_roots("user", root, home))
    if source.startswith(GITHUB):
        url, scope = source, scope or "pack"
    else:
        scope, _directory, url = locate(source, scope, root, home)
    report = judge(fetch_skill(url), scope, root, home, today, recovered)
    report["informed"] = informed(url, root, {report["skill"]})
    return report


def judge(candidate: dict[str, Any], scope: str, root: pathlib.Path, home: pathlib.Path, today: str,
          recovered: list[str]) -> dict[str, Any]:
    """The report on one fetched skill: what `evaluate` answers, and each skill of a `refresh`."""

    url = candidate["url"]
    text = candidate["files"][SKILL_FILE][1].decode("utf-8", "replace")
    claimed = (sd_lib.parse_frontmatter(text) or {}).get("name", "")
    if not ADOPT.SAFE_NAME_RE.match(claimed):
        # Checked before the name becomes a path: the report reads and diffs
        # what is installed there, and `../..` would name somewhere else.
        raise IntakeError(f"{url} declares no name that is one path segment; nothing to judge")
    findings = risk(candidate)
    destination, collisions = _target(claimed, scope, url, root, home)
    findings += collisions
    previous = source_of(destination)
    # A collision names someone else's skill: a diff against it would read as an update.
    files = {} if collisions else transform(candidate, claimed, destination.name, today)
    findings += _landing(files, scope)
    lines = installed_diff(destination, files) if files else []
    matches = match(text, installed_skills(root, home), skip={claimed, destination.name})
    worth = value(text, matches)
    mode = ("blocked" if collisions else "new" if not destination.exists()
            else "re-import" if lines else "unchanged")
    return {"url": url, "commit": candidate["commit"], "scope": scope, "skill": destination.name,
            "destination": str(destination), "mode": mode, "installed_commit": previous[1] if previous else None,
            "files": {name: mode_ for name, (mode_, _b) in sorted(candidate["files"].items())},
            "risk": findings, "match": matches, "value": worth, "verdict": verdict(findings, matches, worth),
            "diff": lines, "revision": approval_revision(candidate, destination), "recovered": recovered,
            "_files": files}


def intake(source: str, *, scope: str | None, approve: str | None, root: pathlib.Path,
           home: pathlib.Path, today: str) -> dict[str, Any]:
    """Evaluate; with `approve`, install the exact revision that report printed."""

    report = evaluate(source, scope, root, home, today)
    files = report.pop("_files")
    report["installed"] = False
    if approve is None:
        return report
    if approve != report["revision"]:
        raise IntakeError(f"approved revision {approve} is not this report's {report['revision']}: "
                          "the source, the target or the installed copy changed; nothing written")
    refused = [f["rule"] for f in report["risk"] if f["severity"] == ADOPT.REFUSE]
    if refused:
        raise IntakeError(f"a refusal blocks the install ({', '.join(sorted(set(refused)))}); nothing written")
    if report["mode"] in ("new", "re-import"):
        install(pathlib.Path(report["destination"]), files)
        report["installed"] = True
    return report


def report_text(report: dict[str, Any]) -> str:
    out = [f"skill: {report['skill']} ({report['scope']}) -> {report['destination']}",
           f"source: {report['url']} at {report['commit']}", f"mode: {report['mode']}"]
    out += [f"recovered: {line}" for line in report["recovered"]]
    out.append(f"risk: {len(report['risk'])} finding(s)")
    out += [f"  {f['severity']}: {f['rule']} in {f['file']}" + (f" line {f['line']}" if f["line"] else "")
            for f in report["risk"]]
    out.append("match: " + (", ".join(f"{m['skill']} {m['overlap']}" for m in report["match"]) or "none"))
    out.append(f"value: {report['value']['instruction_lines']} instruction lines, novelty {report['value']['novelty']}")
    out += _informed_text(report.get("informed", []))
    out.append(f"verdict: {report['verdict']['action']} ({report['verdict']['reason']})")
    shown = report["diff"][:DIFF_LINES]
    out += ["diff:", *shown] if shown else ["diff: none"]
    if len(report["diff"]) > DIFF_LINES:
        out.append(f"... {len(report['diff']) - DIFF_LINES} more diff lines; --json holds them all")
    out.append(f"revision: {report['revision']}")
    if report["installed"]:
        out.append(f"installed: {report['destination']}")
    elif any(f["severity"] == ADOPT.REFUSE for f in report["risk"]):
        out.append("blocked: a refusal stops any install; nothing was written")
    elif report["mode"] == "unchanged":
        out.append("unchanged: the installed copy matches upstream; nothing to approve")
    elif report["mode"] in ("new", "re-import"):
        out.append(f"approve: sd skill intake {report['url']} --scope {report['scope']} --approve {report['revision']}")
    # File names come from upstream too, so the whole report is escaped, not only the diff.
    return _printable("\n".join(out))


def run_intake(args: argparse.Namespace, root: pathlib.Path, home: pathlib.Path) -> int:
    if getattr(args, "rollback", False):
        report = rollback(args.source, scope=args.scope, approve=args.approve, root=root, home=home)
        print(json.dumps(report, ensure_ascii=False) if args.json else rollback_text(report))
        return 0
    report = intake(args.source, scope=args.scope, approve=args.approve, root=root, home=home,
                    today=datetime.date.today().isoformat())
    print(json.dumps(report, ensure_ascii=False) if args.json else report_text(report))
    return 0



# --------------------------------------------------------------------------
# Tracked repositories: the list a refresh reads (pack sd:5498, system sd:5478)
# --------------------------------------------------------------------------

#: The one setting row that lists the repositories intake tracks: JSON, a list of
#: `{url, scope, refreshed, result}`. A row never held reads as the repositories
#: the installed skills' Provenance names, and the first write keeps that seed;
#: a row that is held is the list, so an untracked repository stays untracked.
TRACKED_KEY = "skills.intake_repos"
MAX_TRACKED = 50
#: A refresh judges at most this many skills; a larger repository is refused, not cut short.
MAX_REPO_SKILLS = 100
RESULT_LENGTH = 300
REPO_RE = re.compile(r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?")


def repo_url(text: str) -> str:
    """`https://github.com/<owner>/<repo>` for a repository URL; anything else, a path inside one too, refuses."""

    found = REPO_RE.fullmatch(text.strip()) if isinstance(text, str) else None
    if not found or found[2] in (".", ".."):
        raise IntakeError(f"not a GitHub repository URL: {text!r}; give https://github.com/<owner>/<repo>")
    return f"{GITHUB}{found[1]}/{found[2]}"


def repo_of(url: str) -> str | None:
    """The repository a recorded skill URL names, or None."""

    try:
        return repo_url(parse_url(url)[0])
    except IntakeError:
        return None


def adopted(root: pathlib.Path, home: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Lower-cased repository URL to `{url, skills}` for each installed skill this tool recorded.

    A folder that cannot be listed or read raises `OSError`: unknown, never "adopted from nothing".
    """

    found: dict[str, dict[str, Any]] = {}
    for scope in ("pack", "user"):
        for directory in scope_roots(scope, root, home):
            for folder in sorted(directory.iterdir()) if directory.is_dir() else []:
                recorded = source_of(folder)
                repo = repo_of(recorded[0]) if recorded else None
                if recorded and repo:
                    entry = found.setdefault(repo.lower(), {"url": repo, "skills": []})
                    entry["skills"].append({"name": folder.name, "scope": scope, "url": recorded[0],
                                            "commit": recorded[1]})
    return found


LOCK_FILE = pathlib.Path(".agents") / ".skill-lock.json"  # the `skills` CLI's record, under the home folder
GITHUB_REMOTE_RE = re.compile(r"(?:https://(?:[^@/]+@)?|ssh://git@|git@)github\.com[:/]([^/]+)/(.+)")


def _locked(home: pathlib.Path) -> list[tuple[str, str]]:
    """`(skill, repository URL)` for each GitHub skill the `skills` CLI's lock file holds; no file, none.

    A file that does not read raises: unknown, never "installed nothing".
    """

    path = home / LOCK_FILE
    if not path.exists():
        return []
    try:
        skills = json.loads(path.read_text(encoding="utf-8"))["skills"]
        rows = [(name, row) for name, row in skills.items() if row.get("sourceType") == "github"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise IntakeError(f"cannot read {path}: {error}") from error
    out = []
    for name, row in rows:
        for text in (row.get("sourceUrl"), f"{GITHUB}{row.get('source')}"):
            with contextlib.suppress(IntakeError):
                out.append((name, repo_url(text)))
                break
    return out


def _origin(top: pathlib.Path) -> str | None:
    """The GitHub repository a checkout's `origin` names, or None: no origin, or not GitHub."""

    try:
        done = subprocess.run(["git", "-C", str(top), "config", "--get", "remote.origin.url"], capture_output=True,
                              text=True, timeout=GIT_TIMEOUT, env=_git_env(), check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise IntakeError(f"cannot read the origin of {top}: {error}") from error
    if done.returncode not in (0, 1):  # 1 is "no such key"
        raise IntakeError(f"cannot read the origin of {top}: {_printable(done.stderr.strip())[:300]}")
    found = GITHUB_REMOTE_RE.fullmatch(done.stdout.strip())
    try:
        return repo_url(f"{GITHUB}{found[1]}/{found[2]}") if found else None
    except IntakeError:
        return None


def _linked(root: pathlib.Path, home: pathlib.Path) -> list[tuple[str, str]]:
    """`(skill, repository URL)` for each user skill that resolves inside a git checkout with a GitHub origin.

    The pack's own checkout is not a source: its skills ship with it.
    """

    out, origins = [], {}
    directory = home / ".claude" / "skills"
    for folder in sorted(directory.iterdir()) if directory.is_dir() else []:
        real = folder.resolve()
        top = next((each for each in (real, *real.parents) if (each / ".git").exists()), None)
        if top is None or top == root.resolve():
            continue
        if top not in origins:
            origins[top] = _origin(top)
        origin = origins[top]
        if origin:
            out.append((folder.name, origin))
    return out


def installed_from(root: pathlib.Path, home: pathlib.Path) -> dict[str, dict[str, Any]]:
    """`adopted`, plus the repositories the lock file and linked checkouts name, as user skills with no commit.

    Only the seed and the not-tracked list read these; a refresh places only what Provenance records.
    """

    found = adopted(root, home)
    named = {skill["name"] for value in found.values() for skill in value["skills"]}
    for name, repo in _locked(home) + _linked(root, home):
        if name not in named:
            named.add(name)
            entry = found.setdefault(repo.lower(), {"url": repo, "skills": []})
            entry["skills"].append({"name": name, "scope": "user", "url": repo, "commit": None})
    return found


def _writes() -> Any:
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise IntakeError(f"cannot read the tracked repositories: {imported.problem}")
    from sd_db import writes  # noqa: PLC0415 - only the tracked list needs the database

    return writes


def _entries(raw: str) -> list[dict[str, Any]]:
    try:
        rows = json.loads(raw)
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(
            isinstance(row, dict) and isinstance(row.get("url"), str) and row.get("scope") in ("pack", "user")
            for row in rows):
        raise IntakeError(f"the {TRACKED_KEY} setting row does not read; set it again with --track")
    return [{"url": repo_url(row["url"]), "scope": row["scope"], "refreshed": row.get("refreshed"),
             "result": row.get("result")} for row in rows]


def read_tracked(connection: Any, root: pathlib.Path, home: pathlib.Path) -> tuple[str | None, list[dict[str, Any]], bool]:
    """`(row text, entries, seeded)`. A row never held is seeded from `installed_from` and written by nothing here."""

    held = _writes().read_settings(connection, [TRACKED_KEY])
    if TRACKED_KEY in held:
        return held[TRACKED_KEY], [] if held[TRACKED_KEY] is None else _entries(held[TRACKED_KEY]), False
    seed = [{"url": value["url"], "scope": "user" if all(s["scope"] == "user" for s in value["skills"]) else "pack",
             "refreshed": None, "result": None} for _key, value in sorted(installed_from(root, home).items())]
    return None, seed, True


def write_tracked(connection: Any, entries: list[dict[str, Any]], before: str | None) -> None:
    """Write the list, refused when the row no longer holds `before`, the text it was read as."""

    writes = _writes()
    try:
        writes.set_setting(connection, TRACKED_KEY, json.dumps(entries, sort_keys=True), before=before)
    except writes.SettingStale:
        raise IntakeError("the tracked repositories changed since they were read; read them again") from None


def tracked(connection: Any, root: pathlib.Path, home: pathlib.Path) -> dict[str, Any]:
    """Each tracked repository with the installed skills adopted from it, then the adopted ones not tracked."""

    _raw, entries, seeded = read_tracked(connection, root, home)
    found = installed_from(root, home)
    keys = {entry["url"].lower() for entry in entries}
    return {"key": TRACKED_KEY, "seeded": seeded,
            "repos": [{**entry, "skills": found.get(entry["url"].lower(), {}).get("skills", [])} for entry in entries],
            "untracked": [value for key, value in sorted(found.items()) if key not in keys]}


def track(connection: Any, url: str, scope: str | None, root: pathlib.Path, home: pathlib.Path) -> dict[str, Any]:
    """Add a repository to the list; one already there is left as it is."""

    repo = repo_url(url)
    raw, entries, _seeded = read_tracked(connection, root, home)
    if repo.lower() not in {entry["url"].lower() for entry in entries}:
        if len(entries) >= MAX_TRACKED:
            raise IntakeError(f"{MAX_TRACKED} repositories are tracked already; untrack one first")
        skills = installed_from(root, home).get(repo.lower(), {}).get("skills", [])
        default = "user" if skills and all(s["scope"] == "user" for s in skills) else "pack"
        entries.append({"url": repo, "scope": scope or default, "refreshed": None, "result": None})
        write_tracked(connection, entries, raw)
    return {**tracked(connection, root, home), "url": repo}


def untrack(connection: Any, url: str, root: pathlib.Path, home: pathlib.Path) -> dict[str, Any]:
    """Drop a repository from the list. Its installed skills stay; `removed` is the entry, for an undo."""

    repo = repo_url(url)
    raw, entries, _seeded = read_tracked(connection, root, home)
    removed = next((entry for entry in entries if entry["url"].lower() == repo.lower()), None)
    if removed is None:
        raise IntakeError(f"{repo} is not tracked; nothing written")
    write_tracked(connection, [entry for entry in entries if entry is not removed], raw)
    return {**tracked(connection, root, home), "url": repo, "removed": removed}


def _default_branch(work: pathlib.Path, remote: str) -> str:
    for line in _git(work, "ls-remote", "--symref", remote, "HEAD").splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
            return line[len("ref: refs/heads/"):-len("\tHEAD")]
    raise IntakeError(f"{remote} names no default branch")


def _recorded_at(url: str, branch: str) -> str | None:
    """The path a recorded skill URL names on `branch` ("" for the root), or None when it names another ref."""

    _remote, parts, kind = parse_url(url)
    if kind == "blob" and parts and parts[-1] == SKILL_FILE:
        parts = parts[:-1]
    joined = "/".join(parts)
    if not parts or joined == branch:
        return ""
    return joined[len(branch) + 1:] if joined.startswith(branch + "/") else None


def _bucket(report: dict[str, Any]) -> str:
    if report.get("mode") == "gone":
        return "gone"
    if "error" in report:
        return "failed"
    return {"re-import": "changed"}.get(report["mode"], report["mode"])


def _place(installed: list[dict[str, Any]], branch: str, paths: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    """Installed skills by the branch path they record; those recorded at another ref; and the paths those cover."""

    here, elsewhere = {}, []
    for skill in installed:
        path = _recorded_at(skill["url"], branch)
        if path is None:
            elsewhere.append(skill)
        else:
            here[path] = skill if path in paths else {**skill, "gone": True}
    # A skill installed from another ref is judged at that ref, and its path at the branch is not judged again.
    covered = {("/" + "/".join(parse_url(skill["url"])[1])).removesuffix("/" + SKILL_FILE) for skill in elsewhere}
    return here, elsewhere, {path for path in paths if path and any(c.endswith("/" + path) for c in covered)}


def _judged(report: dict[str, Any], path: str) -> dict[str, Any]:
    """One skill's report in a refresh: its first DIFF_LINES diff lines, and how many there are; `evaluate` gives them all."""

    report.pop("_files")
    return {"path": path, **report, "diff": report["diff"][:DIFF_LINES], "diff_lines": len(report["diff"])}


def _judge_tree(work: pathlib.Path, listing: list[tuple[str, str, str, str]], tree: dict[str, Any], entry: dict[str, Any],
                root: pathlib.Path, home: pathlib.Path, today: str) -> list[dict[str, Any]]:
    """Each skill folder at the fetched commit, judged under the URL an approval of it names."""

    out = []
    for path in tree["paths"]:
        if path in tree["skipped"]:
            continue
        own = tree["here"].get(path)
        url = own["url"] if own else f"{entry['url']}/tree/{tree['branch']}" + (f"/{path}" if path else "")
        rows = [row for row in listing if not path or row[3].startswith(path + "/")]
        try:
            candidate = _skill_at(work, rows, url, tree["commit"], path)
            out.append(_judged(judge(candidate, own["scope"] if own else entry["scope"], root, home, today, []), path))
        except IntakeError as error:
            out.append({"path": path, "url": url, "error": str(error)})
    return out


def _judge_rest(tree: dict[str, Any], root: pathlib.Path, home: pathlib.Path, today: str) -> list[dict[str, Any]]:
    """Skills recorded at another ref, each fetched by its own `evaluate`; then those removed from the branch."""

    out = []
    for skill in tree["elsewhere"]:
        try:
            out.append(_judged(evaluate(skill["url"], skill["scope"], root, home, today), ""))
        except IntakeError as error:
            out.append({"path": "", "url": skill["url"], "skill": skill["name"], "error": str(error)})
    out += [{"path": path, "url": skill["url"], "skill": skill["name"], "scope": skill["scope"], "mode": "gone",
             "error": f"no {SKILL_FILE} at {path} on {tree['branch']}: removed upstream"}
            for path, skill in sorted(tree["here"].items()) if skill.get("gone")]
    return out


def _summary(out: list[dict[str, Any]]) -> tuple[dict[str, int], str]:
    counts = {"new": 0, "changed": 0, "unchanged": 0, "blocked": 0, "gone": 0, "failed": 0}
    for report in out:
        counts[_bucket(report)] += 1
    return counts, ", ".join(f"{n} {name}" for name, n in counts.items() if n) or "no skills"


def survey(entry: dict[str, Any], root: pathlib.Path, home: pathlib.Path, today: str) -> dict[str, Any]:
    """Every skill of one tracked repository at its default branch, each judged as `evaluate` would.

    One fetch reads the whole tree. A skill installed from that branch keeps its
    recorded URL, so its report is the re-import's and its revision is the one
    `--approve` checks; a skill installed from another ref is judged by its own
    `evaluate`. Nothing installs.
    """

    recovered = recover(scope_roots("pack", root, home) + scope_roots("user", root, home))
    remote = entry["url"] + ".git"
    installed = adopted(root, home).get(entry["url"].lower(), {}).get("skills", [])
    with tempfile.TemporaryDirectory(prefix="sd-skill-intake-") as scratch:
        work = pathlib.Path(scratch) / "fetch"
        _git(pathlib.Path(scratch), "init", "-q", "--template=", str(work))
        branch = _default_branch(work, remote)
        _git(work, "fetch", "-q", "--depth", "1", "--no-tags", "--no-recurse-submodules", remote, branch)
        commit = _git(work, "rev-parse", "FETCH_HEAD^{commit}").strip()
        listing = _listing(work, "")
        folders = {str(pathlib.PurePosixPath(name).parent) for mode, _o, _s, name in listing
                   if pathlib.PurePosixPath(name).name == SKILL_FILE and mode not in ("120000", "160000")}
        paths = sorted("" if folder == "." else folder for folder in folders)  # "" is the repository root
        if len(paths) > MAX_REPO_SKILLS:
            raise IntakeError(f"{entry['url']} holds {len(paths)} skills, over the {MAX_REPO_SKILLS} a refresh judges")
        here, elsewhere, skipped = _place(installed, branch, paths)
        tree = {"branch": branch, "commit": commit, "paths": paths, "here": here, "elsewhere": elsewhere, "skipped": skipped}
        out = _judge_tree(work, listing, tree, entry, root, home, today)
    out += _judge_rest(tree, root, home, today)
    counts, result = _summary(out)
    return {"url": entry["url"], "branch": branch, "commit": commit, "skills": out, "counts": counts, "result": result,
            "recovered": recovered}


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def record_refresh(connection: Any, repo: str, at: str, result: str, root: pathlib.Path, home: pathlib.Path) -> str:
    """Write the refresh's time and result on its entry, read again first; "" when written, else why not.

    An entry untracked while the fetch ran stays untracked: the result is dropped, not the removal. So is the
    result of a refresh that started before the one recorded: the newer reading stays.
    """

    for _attempt in range(2):
        try:
            raw, entries, _seeded = read_tracked(connection, root, home)
            entry = next((each for each in entries if each["url"].lower() == repo.lower()), None)
            if entry is None:
                return f"{repo} was untracked while it refreshed"
            if entry["refreshed"] and entry["refreshed"] > at:
                return f"a newer refresh, started {entry['refreshed']}, is recorded"
            entry.update(refreshed=at, result=result[:RESULT_LENGTH])
            write_tracked(connection, entries, raw)
            return ""
        except IntakeError as error:
            why = str(error)
        except Exception as error:  # noqa: BLE001 - a failed write is named on the report, never a pass
            return f"{type(error).__name__}: {error}"
    return why


def refresh(connection: Any, url: str, root: pathlib.Path, home: pathlib.Path, today: str) -> dict[str, Any]:
    """Survey one tracked repository and record when and how it went. Nothing installs.

    A failed survey is recorded as failed and raised. A failed record leaves the
    report standing, `recorded` false and `unrecorded` saying why.
    """

    repo = repo_url(url)
    _raw, entries, _seeded = read_tracked(connection, root, home)
    entry = next((each for each in entries if each["url"].lower() == repo.lower()), None)
    if entry is None:
        raise IntakeError(f"{repo} is not tracked; track it first with --track")
    at = _now()
    try:
        report = survey(entry, root, home, today)
    except (IntakeError, OSError) as error:
        record_refresh(connection, entry["url"], at, f"failed: {_printable(str(error))}", root, home)
        raise IntakeError(str(error)) from error
    why = record_refresh(connection, entry["url"], at, report["result"], root, home)
    return {**report, "refreshed": at, "recorded": not why, "unrecorded": why}


def tracked_text(view: dict[str, Any]) -> str:
    out = [f"tracked{' (seeded from the installed skills, not yet written)' if view['seeded'] else ''}: "
           f"{len(view['repos'])} repositor{'y' if len(view['repos']) == 1 else 'ies'}"]
    for repo in view["repos"]:
        last = f"refreshed {repo['refreshed']}: {repo['result']}" if repo["refreshed"] else "never refreshed"
        out.append(f"  {repo['url']} ({repo['scope']}) · {len(repo['skills'])} adopted · {last}")
    for repo in view["untracked"]:
        out.append(f"untracked: {repo['url']} · {len(repo['skills'])} adopted · sd skill intake --track {repo['url']}")
    return _printable("\n".join(out))


def refresh_text(report: dict[str, Any]) -> str:
    out = [f"refreshed: {report['url']} at {report['branch']} {report['commit']}", f"result: {report['result']}"]
    out += [f"recovered: {line}" for line in report["recovered"]]
    if not report["recorded"]:
        out.append(f"not recorded: {report['unrecorded']}")
    for skill in report["skills"]:
        if "error" in skill:
            out.append(f"  {skill.get('mode', 'failed')}: {skill.get('skill') or skill['path'] or skill['url']}: {skill['error']}")
            continue
        line = f"  {skill['mode']}: {skill['skill']} ({skill['scope']}) · {skill['verdict']['action']} ({skill['verdict']['reason']})"
        if skill["mode"] in ("new", "re-import") and not any(f["severity"] == ADOPT.REFUSE for f in skill["risk"]):
            line += f"\n    approve: sd skill intake {skill['url']} --scope {skill['scope']} --approve {skill['revision']}"
        out.append(line)
    return _printable("\n".join(out))


def run_tracking(args: argparse.Namespace, connection: Any, root: pathlib.Path, home: pathlib.Path) -> int:
    """`--tracked`, `--track URL`, `--untrack URL` and `--refresh URL`: the list and one repository's survey."""

    if args.refresh:
        report = refresh(connection, args.refresh, root, home, datetime.date.today().isoformat())
        print(json.dumps(report, ensure_ascii=False) if args.json else refresh_text(report))
        return 0
    if args.track:
        view = track(connection, args.track, args.scope, root, home)
    elif args.untrack:
        view = untrack(connection, args.untrack, root, home)
    else:
        view = tracked(connection, root, home)
    print(json.dumps(view, ensure_ascii=False) if args.json else tracked_text(view))
    return 0
