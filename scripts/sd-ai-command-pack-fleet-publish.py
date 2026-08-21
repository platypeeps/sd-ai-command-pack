#!/usr/bin/env python3
"""Publish a fleet consumer refresh with finish-work folded into the reviewed head.

Consumer-only: this helper is for fleet CONSUMER repos. It refuses to run against a
repo carrying the completion-mode bookkeeping gate
(``.github/scripts/bookkeeping_ci_scope.py``) — e.g. the sd-ai-command-pack repo
itself — because the fold pattern trips that gate; such a repo must self-release via
``sd-finish-work``. See ``check_preconditions``.

This codifies the proven ``publish-lane3`` campaign procedure so the pr-publication
stage produces a branch whose head ALREADY contains every bookkeeping artifact
(archived task + recorded journal), leaving the merge stage with zero head-advance
and no successor publication to reclassify.

Sequence (H1 = work commit, H3 = published head)::

    0. preconditions: git worktree root, task dir owned + inside .trellis/tasks/,
       working tree dirty ONLY within the managed allowlist.
    1. if the tree is repomix-indexed (scripts/update_repomix + docs/repomix-map.md),
       transactionally move the active task to its archive location, regenerate the
       repomix map against that POST-archive layout, then move the task back. The map
       committed at H1 therefore already matches the tree finish-work will produce, so
       the completion delta stays ``.trellis``-only (no bundle_scope_invalid drift).
    2. WORK commit (H1): pack + active task + regenerated map.
    3. real ``task.py archive`` (the move finish-work performs) + ``add_session`` via
       the shipped ``record-session`` wrapper (real commit subjects, no placeholders).
    4. completion receipt: review-preflight ``final-bundle --mode completion`` from
       base H1 to head H3.
    5. assert the H1..H3 delta is ``.trellis``-only, then push. No merge here.

Failure-safety (required, not optional):

* Refuses to run on a tree dirty outside the managed allowlist, or when the task dir
  is missing / not inside ``.trellis/tasks/``.
* The repomix move-simulate runs under a ``finally`` that restores the task to its
  original path on ANY error or interrupt, so a mid-run crash never strands the task
  in the archive location.
* ``update_repomix`` may write ONLY ``docs/repomix-map.md``; any other touched path
  aborts before the work commit.
* The H1..H3 delta is asserted ``.trellis``-only before push.

Exit codes::

    0  published (or, with --no-push, validated and left unpushed)
    2  argument / environment error
    3  precondition failure (dirty tree, ownership, missing task)
    4  completion receipt not ``valid`` (not pushed)
    5  H1..H3 delta touched a non-.trellis path (not pushed)
    6  update_repomix wrote outside docs/repomix-map.md (not committed)
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Collection, Iterator, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sd_ai_command_pack_lib import run_git_minimal  # noqa: E402

DEFAULT_REPOMIX_SCRIPT = "scripts/update_repomix"
DEFAULT_REPOMIX_OUTPUT = "docs/repomix-map.md"
TASK_ROOT = ".trellis/tasks"
PACK_MANIFEST_RELATIVE = ".sd-ai-command-pack/manifest.json"
# Residue: working-tree paths that may legitimately be dirty when the helper
# starts and that no installer payload target covers. The installer-managed
# surfaces are NOT listed here -- derive_allowed_paths() reads them from the
# consumer's own manifest, because a hand-maintained platform list silently
# drifts from the payload and then fails every lane on the consumer that
# gained a new target directory. Anything dirty outside the union of this
# residue and the derived set means unrelated work would be swept into the
# publication commit, so the helper fails closed.
#
# Split the same way derived targets are: a directory here is prefix-matched, a
# file is exact-matched. A residue *file* left in the prefix tuple would sanction
# `.gitignore.bak` and `docs/repomix-map.md.orig` for the same startswith reason
# a derived `scripts/a.py` would sanction `scripts/a.py.orig`.
DEFAULT_ALLOWED_PREFIXES = (
    # Trellis owns this: the active task and the journal workspace are dirty
    # by design at the moment this helper runs.
    ".trellis/",
    # The installer's own receipts (manifest, provenance, installed-targets),
    # rewritten by the install that precedes publication. Not payload targets,
    # so the manifest never names them.
    ".sd-ai-command-pack/",
)
DEFAULT_ALLOWED_EXACT = (
    # The map generator's output, regenerated after the archive move.
    "docs/repomix-map.md",
    # Carries the pack-managed .obsidian-kb block. refresh_managed_ignore_block()
    # rewrites it before the work commit, and an operator who already ran
    # housekeeping arrives here with it dirty.
    ".gitignore",
)

# Acceptance-criteria ticking. A refresh PRD's criteria are prose authored per
# consumer, so the verifier keys off a structured tag and NEVER off matching the
# sentence: inferring "this criterion means check the exec bit" from free text
# is how a rewording silently changes what gets asserted. An untagged criterion,
# an unknown tag id, and a tag whose evidence is missing all stay unticked.
#
# The comment form is invisible in rendered Markdown, so the archived PRD reads
# exactly as authored.
ACCEPTANCE_HEADING = "## Acceptance Criteria"
DISPOSITION_START = "<!-- sd-ai-command-pack:criteria-disposition:start -->"
DISPOSITION_END = "<!-- sd-ai-command-pack:criteria-disposition:end -->"
CRITERION_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<state>[ xX])\] (?P<body>.*)$")
VERIFY_TAG_RE = re.compile(r"<!--\s*verify:\s*(?P<id>[a-z0-9-]+)(?P<attrs>[^>]*?)-->")
ATTR_RE = re.compile(r"(?P<key>[a-z0-9-]+)=(?P<value>\S+)")
PROVENANCE_RE = re.compile(
    r"Installed payload provenance: version (?P<version>[^;\s]+)"
)


class PublishError(Exception):
    """A publish precondition or invariant was violated. Carries an exit code."""

    def __init__(self, message: str, *, code: int) -> None:
        super().__init__(message)
        self.code = code


def run(
    argv: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(argv),
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stdout or "").strip().splitlines()[-1:] or [""]
        raise PublishError(
            f"command failed ({' '.join(argv)}): {detail[0]}", code=2
        )
    return result


def git_run(
    argv: Sequence[str], *, cwd: Path
) -> subprocess.CompletedProcess[str]:
    """Run ``git <argv>`` via the shared lib helper, preserving ``run``'s contract.

    Mirrors the former ``run`` git call: stderr merged into stdout, no timeout,
    and a nonzero exit raises the same ``PublishError`` with the reconstructed
    ``git ...`` command in the message.
    """

    result = run_git_minimal(
        list(argv), cwd=cwd, timeout=None, stderr=subprocess.STDOUT
    )
    if result.returncode != 0:
        detail = (result.stdout or "").strip().splitlines()[-1:] or [""]
        raise PublishError(
            f"command failed (git {' '.join(argv)}): {detail[0]}", code=2
        )
    return result


def git_out(argv: Sequence[str], *, cwd: Path) -> str:
    return (git_run(argv, cwd=cwd).stdout or "").strip()


def porcelain_paths(cwd: Path) -> list[str]:
    """Return the set of paths that appear dirty in ``git status --porcelain``."""

    raw = git_run(["status", "--porcelain"], cwd=cwd).stdout or ""
    paths: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        entry = line[3:] if len(line) > 3 else line
        # Renames/copies render as "old -> new"; the new path is what will be staged.
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        paths.append(entry.strip().strip('"'))
    return paths


def is_allowed(
    path: str, prefixes: Sequence[str], exact: Collection[str] = ()
) -> bool:
    """Allow ``path`` when it matches a prefix, or equals an exact entry.

    The two sets are not interchangeable. A payload target like
    ``scripts/a.py`` must not be prefix-matched: ``startswith`` would also
    sanction ``scripts/a.py.orig``, letting an editor backup ride into the
    publication commit. Directory prefixes still need prefix semantics, and so
    does every operator-supplied --allow-path-prefix value.
    """

    if path in exact:
        return True
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def derive_allowed_paths(repo: Path) -> tuple[tuple[str, ...], frozenset[str]]:
    """Read the consumer's installed manifest into (prefixes, exact) sets.

    Fails closed with a named reason: a missing, unreadable, malformed, or
    target-less manifest refuses the publish rather than falling back to a
    literal list, because a silent fallback is the drift this replaces.
    """

    manifest_path = repo / PACK_MANIFEST_RELATIVE
    if not manifest_path.is_file():
        raise PublishError(
            f"manifest_missing: no installed pack manifest at "
            f"{PACK_MANIFEST_RELATIVE}; cannot derive the managed allowlist",
            code=3,
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PublishError(
            f"manifest_unreadable: cannot read {PACK_MANIFEST_RELATIVE}: {error}",
            code=3,
        ) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise PublishError(
            f"manifest_malformed: {PACK_MANIFEST_RELATIVE} is not an object with "
            "a 'files' list",
            code=3,
        )

    derived_prefixes: set[str] = set()
    derived_exact: set[str] = set()
    skipped = 0
    for entry in payload["files"]:
        target = entry.get("target") if isinstance(entry, dict) else None
        if not isinstance(target, str) or not target:
            skipped += 1
            continue
        if target.startswith("/") or ".." in Path(target).parts:
            skipped += 1
            continue
        head = target.split("/", 1)[0]
        if head.startswith("."):
            derived_prefixes.add(f"{head}/")
        else:
            derived_exact.add(target)

    if not derived_prefixes and not derived_exact:
        raise PublishError(
            f"manifest_targets_empty: {PACK_MANIFEST_RELATIVE} declares no usable "
            f"target ({skipped} entr{'y' if skipped == 1 else 'ies'} skipped as "
            "malformed or unsafe)",
            code=3,
        )
    prefixes = tuple(sorted(set(DEFAULT_ALLOWED_PREFIXES) | derived_prefixes))
    return prefixes, frozenset(set(DEFAULT_ALLOWED_EXACT) | derived_exact)


def resolve_task_dir(repo: Path, slug: str) -> Path:
    task_dir = (repo / TASK_ROOT / slug).resolve()
    root = (repo / TASK_ROOT).resolve()
    if root not in task_dir.parents:
        raise PublishError(
            f"task {slug!r} does not resolve inside {TASK_ROOT}/", code=3
        )
    if not task_dir.is_dir():
        raise PublishError(
            f"task directory not found: {TASK_ROOT}/{slug}", code=3
        )
    return task_dir


def check_preconditions(
    repo: Path,
    slug: str,
    prefixes: Sequence[str],
    exact: Collection[str] = (),
    preflight: Path | None = None,
    record_session: Path | None = None,
) -> None:
    top = git_out(["rev-parse", "--show-toplevel"], cwd=repo)
    if Path(top).resolve() != repo.resolve():
        raise PublishError(
            f"{repo} is not the git worktree root (top-level is {top})", code=3
        )
    # Self-publish guard: refuse to run against a repo that carries the
    # completion-mode bookkeeping gate. The fold pattern (work + archive + journal
    # in one head) trips that gate's completion_archive_move_missing check, so a
    # repo with .github/scripts/bookkeeping_ci_scope.py must self-release via
    # sd-finish-work, not this consumer-only helper. Keyed on the gate, not pack
    # identity: any repo adopting the gate is protected.
    if (repo / ".github" / "scripts" / "bookkeeping_ci_scope.py").exists():
        raise PublishError(
            "refusing to run: target carries the completion-mode bookkeeping gate "
            "that a folded publish would violate (fleet-publish is consumer-only); "
            "use sd-finish-work for a folded-bookkeeping release",
            code=3,
        )
    # Prove both pack helpers are reachable while this run is still a no-op.
    # Neither is consumed until after the work commit: record-session at the
    # journal step, the preflight at the receipt step, both downstream of a
    # branch this helper has already written to -- and there is no resume path
    # (resolve_task_dir below requires a live task directory the archive has by
    # then moved). A dependency that can be checked before the first side
    # effect must be.
    for label, helper, flag in (
        ("review preflight", preflight, "--review-preflight"),
        ("record-session wrapper", record_session, "--record-session"),
    ):
        if helper is not None and not helper.is_file():
            raise PublishError(
                f"{label} not found at {helper} (fleet-publish resolves pack "
                f"helpers from the source checkout that owns it; pass {flag} "
                "to override)",
                code=3,
            )
    resolve_task_dir(repo, slug)
    disallowed = [
        path
        for path in porcelain_paths(repo)
        if not is_allowed(path, prefixes, exact)
    ]
    if disallowed:
        raise PublishError(
            "working tree is dirty outside the managed allowlist: "
            + ", ".join(sorted(disallowed))
            + f" (allowlist: {len(prefixes)} prefix(es) and {len(exact)} exact "
            f"path(s), combining {PACK_MANIFEST_RELATIVE}, the built-in "
            "residue, and any --allow-path-prefix override; commit or stash "
            "unrelated work, or extend --allow-path-prefix)",
            code=3,
        )


@contextlib.contextmanager
def task_moved_to_archive(repo: Path, slug: str, month: str) -> Iterator[Path]:
    """Move the active task to its archive path, yielding it, then ALWAYS move back.

    The restore runs in ``finally`` so an error while the task is moved aside never
    leaves it stranded in the archive location.
    """

    task_dir = repo / TASK_ROOT / slug
    archive_parent = repo / TASK_ROOT / "archive" / month
    archive_dir = archive_parent / slug
    archive_parent.mkdir(parents=True, exist_ok=True)
    try:
        task_dir.rename(archive_dir)
        yield archive_dir
    finally:
        if archive_dir.exists() and not task_dir.exists():
            archive_dir.rename(task_dir)
        # Tidy the scaffolding we created; ignore if other archives live there.
        with contextlib.suppress(OSError):
            archive_parent.rmdir()
        with contextlib.suppress(OSError):
            (repo / TASK_ROOT / "archive").rmdir()


def regenerate_repomix_post_archive(
    repo: Path, slug: str, script: str, output: str, month: str
) -> None:
    """Pre-compute the POST-archive repomix map so H1 already matches finish-work."""

    with task_moved_to_archive(repo, slug, month):
        # Baseline AFTER the move so the move itself cancels out and only
        # update_repomix's own writes remain in the delta.
        baseline = set(porcelain_paths(repo))
        run(["bash", script], cwd=repo)
        touched = {path for path in porcelain_paths(repo) if path not in baseline}
    # Whatever update_repomix changed must be confined to the declared output path.
    stray = sorted(path for path in touched if path != output)
    if stray:
        raise PublishError(
            f"update_repomix wrote outside {output}: " + ", ".join(stray),
            code=6,
        )


def refresh_managed_ignore_block(repo: Path, python_bin: str) -> str:
    """Regenerate the pack-managed .obsidian-kb ignore block BEFORE the work commit.

    Housekeeping runs this same helper at the merge gate. When a release changes
    the managed block, letting housekeeping be the first to write it dirties the
    tree only after the completion bundle is published -- and that is
    unrecoverable in place: a receipt whose span contains .gitignore is
    `bundle_scope_invalid`, and a second bundle is `completion_archive_move_missing`
    because the archive move happens once. Running it here puts the change in H1,
    where it belongs.

    Argument form must stay identical to sd-ai-command-pack-housekeeping.sh's:
    no --if-present, which returns early when .obsidian-kb is absent and would
    skip the very block housekeeping still writes. The helper resolves its own
    root from the working directory, so cwd must be the consumer.

    The KB folder is regenerable and ignored, so a helper failure is advisory:
    report it and let the refresh proceed exactly as it does today.

    A nonzero exit does not mean the block went unwritten. The helper calls
    ensure_gitignore() before it copies anything, then exits 3 when only the
    KB copies hit conflicts and 2 on a hard OSError partway through. So the
    returned state is decided by whether .gitignore actually changed, not by
    the exit code -- reporting "failed" on an exit 3 would tell an operator the
    block is stale when it is in fact refreshed and already inside H1.
    """

    helper = repo / "scripts" / "sd-ai-command-pack-update-spec-kb.py"
    if not helper.is_file():
        return "absent"
    gitignore = repo / ".gitignore"
    before = gitignore.read_bytes() if gitignore.is_file() else None
    completed = run([python_bin, str(helper)], cwd=repo, check=False)
    if completed.returncode == 0:
        return "refreshed"
    after = gitignore.read_bytes() if gitignore.is_file() else None
    block_written = after != before
    detail = ((completed.stdout or "").strip().splitlines()[-1:] or [""])[0]
    tail = (
        "; the managed ignore block was still rewritten and will be included in"
        " the work commit"
        if block_written
        # Unchanged means not regenerated this run -- it may already be current.
        # Do not word this as though the block were absent.
        else "; continuing without regenerating it (housekeeping will report any"
        " drift)"
    )
    print(
        f"warning: managed ignore-block refresh exited {completed.returncode}"
        + (f": {detail}" if detail else "")
        + tail,
        file=sys.stderr,
    )
    return "refreshed" if block_written else "failed"


def work_commit(repo: Path, message_file: Path) -> str:
    git_run(["add", "-A"], cwd=repo)
    git_run(["commit", "-q", "-F", str(message_file)], cwd=repo)
    return git_out(["rev-parse", "HEAD"], cwd=repo)


@dataclasses.dataclass(frozen=True)
class Criterion:
    """One ``- [ ]`` / ``- [x]`` line inside the acceptance-criteria section."""

    line: int
    ticked: bool
    tag: str | None
    attrs: dict[str, str]
    prose: str


@dataclasses.dataclass(frozen=True)
class CriteriaSection:
    """The parsed section: its line span and the criteria inside it."""

    start: int
    end: int
    records: list[Criterion]


@dataclasses.dataclass(frozen=True)
class VerifyContext:
    """What a verifier is allowed to consult.

    Deliberately narrow. A verifier that could reach the whole argument
    namespace would be able to tick a criterion from an operator-supplied
    string that no stage ever checked.
    """

    repo: Path
    python_bin: str
    evidence: dict[str, tuple[bool, str]]
    work_commit: str


def parse_acceptance_criteria(text: str) -> CriteriaSection | None:
    """Split the ``## Acceptance Criteria`` section into per-criterion records.

    Returns ``None`` when the heading is absent. That is a valid PRD -- a
    lightweight consumer task need not carry criteria -- and failing a publish
    over a section that was never required would be the wrong trade.
    """

    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == ACCEPTANCE_HEADING:
            start = index + 1
            break
    if start is None:
        return None
    # Stop at the next section. The refresh PRD carries "## Post-archive
    # handoff" directly after the criteria, and swallowing it would put the
    # disposition block inside the wrong section.
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    records: list[Criterion] = []
    for index in range(start, end):
        match = CRITERION_RE.match(lines[index])
        if match is None:
            continue
        body = match.group("body")
        tag = VERIFY_TAG_RE.search(body)
        records.append(
            Criterion(
                line=index,
                ticked=match.group("state") in {"x", "X"},
                tag=tag.group("id") if tag else None,
                attrs=dict(ATTR_RE.findall(tag.group("attrs"))) if tag else {},
                prose=VERIFY_TAG_RE.sub("", body).strip(),
            )
        )
    return CriteriaSection(start=start, end=end, records=records)


def _split_attr(value: str | None) -> list[str]:
    return [item for item in (value or "").split(",") if item]


def _verify_install_audit(
    record: Criterion, ctx: VerifyContext
) -> tuple[bool, str]:
    helper = SCRIPT_DIR / "sd-ai-command-pack-install-audit.py"
    if not helper.is_file():
        return False, f"install-audit helper not found at {helper}"
    attrs = record.attrs
    release = attrs.get("release")
    if not release:
        # The criterion names a version; this helper takes no release argument,
        # so without the tag a passing exit code would tick a sentence whose
        # version was never compared to anything.
        return False, "tag omits release=, so the asserted version is unverifiable"
    argv = [ctx.python_bin, str(helper), "--repo", str(ctx.repo)]
    for platform in _split_attr(attrs.get("platforms")):
        argv.extend(["--expected-platform", platform])
    result = run(argv, cwd=ctx.repo, check=False)
    if result.returncode != 0:
        return False, f"install audit exited {result.returncode}"
    found = PROVENANCE_RE.search(result.stdout or "")
    if found is None:
        return False, "install audit reported no provenance version"
    if found.group("version") != release:
        return (
            False,
            f"install audit reports {found.group('version')}, tag expects {release}",
        )
    return True, f"install audit passed; provenance {release}"


def _verify_tracked_mode(
    record: Criterion, ctx: VerifyContext
) -> tuple[bool, str]:
    attrs = record.attrs
    path = attrs.get("path")
    if not path:
        return False, "tag omits path="
    expected = attrs.get("mode", "100755")
    # Route git through the shared lib helper, not run(["git", ...]): the
    # git-invocation boundary test rejects an argv literal here. git_run is the
    # wrong helper for a verifier -- it raises on nonzero, which would abort a
    # publish over a criterion that should merely have stayed unticked.
    result = run_git_minimal(
        ["ls-files", "-s", "--", path],
        cwd=ctx.repo,
        timeout=None,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        return False, f"git ls-files exited {result.returncode} for {path}"
    line = (result.stdout or "").strip()
    if not line:
        return False, f"{path} is not tracked"
    mode = line.split(None, 1)[0]
    if mode != expected:
        return False, f"{path} is tracked {mode}, tag expects {expected}"
    return True, f"{path} is tracked {mode}"


def _verify_bundle_shape(
    record: Criterion, ctx: VerifyContext
) -> tuple[bool, str]:
    """The work commit exists and the completion bundle is being formed.

    This reads as asserting the future, because the archive and journal commits
    do not exist yet. It is safe because publish is all-or-nothing: if the
    bundle does not form, the completion receipt is not ``valid`` and publish
    raises before the push. A tick that would have been a lie never reaches a
    remote, let alone merged history.
    """

    return True, f"work commit {ctx.work_commit} created; bundle forming"


def _verify_lane_evidence(
    record: Criterion, ctx: VerifyContext
) -> tuple[bool, str]:
    key = record.attrs.get("id")
    if not key:
        return False, "tag omits id="
    entry = ctx.evidence.get(key)
    if entry is None:
        return False, f"no --criterion-evidence supplied for {key!r}"
    verified, note = entry
    if note:
        return verified, note
    return verified, f"lane evidence {key!r} supplied as " + (
        "verified" if verified else "unverified"
    )


CRITERION_VERIFIERS: dict[
    str, Callable[[Criterion, VerifyContext], tuple[bool, str]]
] = {
    "install-audit": _verify_install_audit,
    "tracked-mode": _verify_tracked_mode,
    "bundle-shape": _verify_bundle_shape,
    "lane-evidence": _verify_lane_evidence,
}


def parse_criterion_evidence(
    values: Sequence[str],
) -> dict[str, tuple[bool, str]]:
    """Parse ``--criterion-evidence id=verified|unverified[:note]`` values.

    Malformed input is rejected here rather than at use time: a typo that
    silently produced "no evidence supplied" would look identical to a stage
    that legitimately could not verify its criterion.
    """

    evidence: dict[str, tuple[bool, str]] = {}
    for value in values:
        key, separator, remainder = value.partition("=")
        if not separator or not key.strip():
            raise PublishError(
                f"--criterion-evidence {value!r} is not id=verified|unverified"
                "[:note]",
                code=2,
            )
        verdict, _, note = remainder.partition(":")
        if verdict not in {"verified", "unverified"}:
            raise PublishError(
                f"--criterion-evidence {value!r} has verdict {verdict!r}; "
                "expected 'verified' or 'unverified'",
                code=2,
            )
        evidence[key.strip()] = (verdict == "verified", note.strip())
    return evidence


def _strip_disposition_block(lines: list[str]) -> list[str]:
    """Remove a previously written block so the rewrite is idempotent.

    The tick runs *before* ``task.py archive``, and that call aborts loudly with
    no rollback. A retry therefore re-enters with the boxes already flipped and
    a block already on disk; appending would stack one block per attempt.
    """

    start = end = None
    for index, line in enumerate(lines):
        if line.strip() == DISPOSITION_START:
            start = index
        elif line.strip() == DISPOSITION_END and start is not None:
            end = index
            break
    if start is None or end is None:
        return lines
    # Consume the blank lines this function's own writer put around the block.
    # Leaving them behind grows the file by two lines per retry, which is the
    # same append-per-attempt bug one level down.
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    while end + 1 < len(lines) and not lines[end + 1].strip():
        end += 1
    return lines[:start] + lines[end + 1 :]


def _render_disposition_block(unchecked: Sequence[dict[str, str]]) -> list[str]:
    lines = [DISPOSITION_START]
    if unchecked:
        lines.append(
            "> **Not verified by the publish run.** These criteria stay unticked:"
        )
        lines.append(">")
        for item in unchecked:
            lines.append(f"> - {item['prose']} — {item['reason']}")
    else:
        lines.append(
            "> Every acceptance criterion was verified by the publish run."
        )
    lines.append(DISPOSITION_END)
    return lines


def tick_acceptance_criteria(
    repo: Path,
    slug: str,
    *,
    python_bin: str,
    evidence: dict[str, tuple[bool, str]],
    work_commit_sha: str,
) -> dict[str, object]:
    """Tick criteria this run proved; leave the rest visibly unticked.

    Must be called before ``task.py archive`` -- that command moves the task
    directory *and* commits it, so this is the last point at which the edit
    still lands inside the archive commit. Writing it earlier would put task
    bookkeeping in the work commit; writing it later needs a fourth commit that
    the completion receipt rejects.
    """

    prd = repo / TASK_ROOT / slug / "prd.md"
    if not prd.is_file():
        return {"state": "absent", "unchecked": [], "detail": "prd.md not found"}
    text = prd.read_text(encoding="utf-8")
    parsed = parse_acceptance_criteria(text)
    if parsed is None:
        return {
            "state": "no-criteria-section",
            "unchecked": [],
            "detail": f"{ACCEPTANCE_HEADING} is not present",
        }
    ctx = VerifyContext(
        repo=repo,
        python_bin=python_bin,
        evidence=evidence,
        work_commit=work_commit_sha,
    )
    lines = text.splitlines()
    unchecked: list[dict[str, str]] = []
    ticked = 0
    for record in parsed.records:
        if record.ticked:
            # Never untick. A box ticked by hand may reflect evidence this
            # helper cannot see; removing it would be its own false claim.
            continue
        if record.tag is None:
            unchecked.append(
                {"prose": record.prose, "reason": "no `verify:` tag"}
            )
            continue
        verifier = CRITERION_VERIFIERS.get(record.tag)
        if verifier is None:
            unchecked.append(
                {
                    "prose": record.prose,
                    "reason": f"unknown verifier `{record.tag}`",
                }
            )
            continue
        verified, note = verifier(record, ctx)
        if not verified:
            unchecked.append({"prose": record.prose, "reason": note})
            continue
        lines[record.line] = lines[record.line].replace("- [ ]", "- [x]", 1)
        ticked += 1

    lines = _strip_disposition_block(lines)
    reparsed = parse_acceptance_criteria("\n".join(lines))
    assert reparsed is not None
    insert_at = reparsed.end
    # Normalize the blank lines on both sides of the insertion point to exactly
    # one. Without this the first pass and a retry disagree by a blank line --
    # the same append-per-attempt drift as a duplicated block, one line at a
    # time -- because the source already separates the list from the next
    # section and the strip above consumes that separator on re-entry.
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    tail = insert_at
    while tail < len(lines) and not lines[tail].strip():
        tail += 1
    block = _render_disposition_block(unchecked)
    # Keep one blank line on each side so the block renders as its own
    # paragraph rather than joining the last list item.
    lines = lines[:insert_at] + [""] + block + [""] + lines[tail:]
    prd.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return {
        "state": "rewritten",
        "ticked": ticked,
        "unchecked": unchecked,
        "detail": f"{ticked} criterion(s) ticked, {len(unchecked)} left unticked",
    }


def archive_and_journal(
    repo: Path,
    slug: str,
    *,
    python_bin: str,
    record_session: Path,
    title: str,
    summary: str,
    commit: str,
    changes: Sequence[str],
    tests: Sequence[str],
    criterion_evidence: dict[str, tuple[bool, str]] | None = None,
) -> tuple[str, dict[str, object]]:
    # Tick before the archive, not after: task.py archive moves the task
    # directory AND commits it (--no-commit is opt-out), so this is the last
    # point at which the rewrite still lands inside the archive commit.
    criteria = tick_acceptance_criteria(
        repo,
        slug,
        python_bin=python_bin,
        evidence=criterion_evidence or {},
        work_commit_sha=commit,
    )
    # Loud abort, no rollback: a consumer runs its own (unpatched) task.py, so a
    # transient .git/index.lock can make the archive move on disk but fail to
    # commit. We do NOT attempt a rollback — task.py's archive also flips task
    # status, detaches children, and clears sessions before the move, so a
    # dir-only undo here would leave a partial, misleading state. Instead surface
    # the likely cause + exact recovery and stop.
    archive = run(
        [python_bin, str(Path(".trellis/scripts/task.py")), "archive", slug],
        cwd=repo,
        check=False,
    )
    if archive.returncode != 0:
        detail = ((archive.stdout or "").strip().splitlines()[-1:] or [""])[0]
        raise PublishError(
            f"task.py archive failed for {slug!r} ({detail}). Likely transient "
            ".git/index.lock contention: the task may already be moved on disk and "
            "staged but not committed. fleet-publish performs no rollback (the "
            "archive also flips task status, detaches children, and clears "
            "sessions, so a partial undo would corrupt state). Recover with "
            "`git status` — complete or discard the archive commit — or re-run the "
            "fleet action from a clean tree.",
            code=2,
        )
    session_cmd = [
        python_bin,
        str(record_session),
        "--title",
        title,
        "--summary",
        summary,
        "--commit",
        commit,
    ]
    for change in changes:
        session_cmd.extend(["--change", change])
    for test in tests:
        session_cmd.extend(["--test", test])
    run(session_cmd, cwd=repo)
    return git_out(["rev-parse", "HEAD"], cwd=repo), criteria


def completion_receipt(
    repo: Path, base: str, head: str, receipt_out: Path, preflight: Path
) -> str:
    # The preflight is a pack helper, not a consumer file: this script is
    # source-only (SOURCE_ONLY_ALLOWED_PACK_FILES) and a thin consumer vendors
    # no scripts/sd-ai-command-pack-* at all, so a consumer-relative path finds
    # nothing and node exits without stdout -- surfacing as an unparseable
    # empty receipt rather than the missing file it is. Resolve it beside this
    # script, exactly as publish() already resolves the record-session wrapper.
    #
    # --repo is not redundant with cwd. review-preflight's defaultRootDir()
    # consults SD_AI_COMMAND_PACK_REPO_ROOT before it falls back to
    # `git rev-parse --show-toplevel` in the inherited cwd, and the consumer
    # full check exports that variable. Without an explicit --repo, an ambient
    # value would silently produce a well-formed receipt describing the pack
    # checkout while claiming to describe the consumer.
    result = run(
        [
            "node",
            str(preflight),
            "final-bundle",
            "--mode",
            "completion",
            "--repo",
            str(repo),
            "--base",
            base,
            "--head",
            head,
            "--json",
        ],
        cwd=repo,
        check=False,
    )
    receipt_out.write_text(result.stdout or "", encoding="utf-8")
    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError as error:
        raise PublishError(
            f"completion receipt was not valid JSON: {error}", code=4
        ) from None
    return str(payload.get("status", "unknown"))


def assert_trellis_only_delta(repo: Path, base: str, head: str) -> None:
    changed = git_out(["diff", "--name-only", base, head], cwd=repo).splitlines()
    stray = sorted(
        path for path in changed if path.strip() and not path.startswith(".trellis/")
    )
    if stray:
        raise PublishError(
            "H1..H3 delta touched non-.trellis paths (finish-work must be "
            ".trellis-only): " + ", ".join(stray),
            code=5,
        )


def publish(args: argparse.Namespace) -> dict[str, object]:
    repo = Path(args.repo).resolve()
    derived_prefixes, exact = derive_allowed_paths(repo)
    prefixes = derived_prefixes + tuple(args.allow_path_prefix or ())
    record_session = (
        Path(args.record_session).resolve()
        if args.record_session
        else Path(__file__).resolve().parent
        / "sd-ai-command-pack-record-session.py"
    )
    preflight = (
        Path(args.review_preflight).resolve()
        if args.review_preflight
        else Path(__file__).resolve().parent
        / "sd-ai-command-pack-review-preflight.mjs"
    )
    receipt_out = Path(args.receipt_out).resolve()
    month = args.archive_month or datetime.now(timezone.utc).strftime("%Y-%m")

    check_preconditions(
        repo,
        args.slug,
        prefixes,
        exact,
        preflight=preflight,
        record_session=record_session,
    )
    base = git_out(["rev-parse", "HEAD"], cwd=repo)

    # Before the map: the block can newly ignore .obsidian-kb, and repomix must
    # index the final ignore state or housekeeping's later run rewrites the map.
    ignore_block = refresh_managed_ignore_block(repo, args.python)

    indexed = (repo / args.repomix_script).exists() and (
        repo / args.repomix_output
    ).exists()
    if indexed:
        regenerate_repomix_post_archive(
            repo, args.slug, args.repomix_script, args.repomix_output, month
        )

    h1 = work_commit(repo, Path(args.work_message_file).resolve())
    h3, criteria = archive_and_journal(
        repo,
        args.slug,
        python_bin=args.python,
        record_session=record_session,
        title=args.title,
        summary=args.summary,
        commit=h1,
        changes=args.change,
        tests=args.test,
        criterion_evidence=parse_criterion_evidence(args.criterion_evidence),
    )
    status = completion_receipt(repo, h1, h3, receipt_out, preflight)
    if status != "valid":
        raise PublishError(
            f"completion receipt status is {status!r}, not 'valid' (not pushed); "
            f"see {receipt_out}",
            code=4,
        )
    assert_trellis_only_delta(repo, h1, h3)

    pushed = False
    if not args.no_push:
        git_run(["push", "-u", args.remote, args.branch], cwd=repo)
        pushed = True

    return {
        "repo": str(repo),
        "slug": args.slug,
        "base": base,
        "h1": h1,
        "h3": h3,
        "receipt": status,
        "repomixIndexed": indexed,
        "ignoreBlock": ignore_block,
        "pushed": pushed,
        "receiptPath": str(receipt_out),
        "acceptanceCriteria": criteria,
        "uncheckedCriteria": criteria.get("unchecked", []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Publish a fleet consumer refresh with finish-work folded into the "
            "reviewed head (drift-safe, move-preserving)."
        )
    )
    parser.add_argument("repo", help="Consumer repository worktree root")
    parser.add_argument("slug", help="Active Trellis task slug under .trellis/tasks/")
    parser.add_argument("--branch", required=True, help="Branch to push")
    parser.add_argument("--title", required=True, help="Journal session title")
    parser.add_argument("--summary", required=True, help="Journal session summary")
    parser.add_argument(
        "--change",
        action="append",
        required=True,
        help="Main Changes journal bullet (repeatable); forwarded to record-session",
    )
    parser.add_argument(
        "--test",
        action="append",
        required=True,
        help="Testing journal line (repeatable); forwarded to record-session",
    )
    parser.add_argument(
        "--work-message-file",
        required=True,
        help="File containing the WORK (H1) commit message",
    )
    parser.add_argument(
        "--receipt-out",
        required=True,
        help="Path to write the completion receipt JSON",
    )
    parser.add_argument("--remote", default="origin", help="Push remote")
    parser.add_argument(
        "--allow-path-prefix",
        action="append",
        default=[],
        help="Extra dirty-tree allowlist prefix (repeatable)",
    )
    parser.add_argument(
        "--repomix-script", default=DEFAULT_REPOMIX_SCRIPT, help="update_repomix path"
    )
    parser.add_argument(
        "--repomix-output",
        default=DEFAULT_REPOMIX_OUTPUT,
        help="The only path update_repomix may write",
    )
    parser.add_argument(
        "--record-session",
        default=None,
        help="Path to the record-session wrapper (defaults next to this script)",
    )
    parser.add_argument(
        "--review-preflight",
        default=None,
        help="Path to the review-preflight helper (defaults next to this script)",
    )
    parser.add_argument(
        "--criterion-evidence",
        action="append",
        default=[],
        help=(
            "Evidence for a lane-evidence acceptance criterion, as "
            "id=verified|unverified[:note] (repeatable). Supplies the result "
            "of a stage this helper cannot re-derive; anything without a "
            "matching value stays unticked."
        ),
    )
    parser.add_argument(
        "--python", default="python3", help="Interpreter for Trellis scripts"
    )
    parser.add_argument(
        "--archive-month",
        default=None,
        help="YYYY-MM archive cohort (defaults to current UTC month)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Validate and stop before pushing (dry-run)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = publish(args)
    except PublishError as error:
        print(f"fleet-publish: {error}", file=sys.stderr)
        return error.code
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
