#!/usr/bin/env python3
"""Publish a fleet consumer refresh with finish-work folded into the reviewed head.

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
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

DEFAULT_REPOMIX_SCRIPT = "scripts/update_repomix"
DEFAULT_REPOMIX_OUTPUT = "docs/repomix-map.md"
TASK_ROOT = ".trellis/tasks"
# Working-tree paths that may legitimately be dirty when the helper starts: the
# active task, the journal workspace, the regenerated map, and the pack-managed
# platform surfaces the installer just rewrote. Anything else dirty means unrelated
# work would be swept into the publication commit, so the helper fails closed.
DEFAULT_ALLOWED_PREFIXES = (
    ".trellis/",
    ".agents/",
    ".claude/",
    ".codex/",
    ".cursor/",
    ".gemini/",
    ".github/",
    ".kiro/",
    ".opencode/",
    ".qoder/",
    ".sd-ai-command-pack/",
    "docs/repomix-map.md",
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


def git_out(argv: Sequence[str], *, cwd: Path) -> str:
    return (run(["git", *argv], cwd=cwd).stdout or "").strip()


def porcelain_paths(cwd: Path) -> list[str]:
    """Return the set of paths that appear dirty in ``git status --porcelain``."""

    raw = run(["git", "status", "--porcelain"], cwd=cwd).stdout or ""
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


def is_allowed(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


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


def check_preconditions(repo: Path, slug: str, prefixes: Sequence[str]) -> None:
    top = git_out(["rev-parse", "--show-toplevel"], cwd=repo)
    if Path(top).resolve() != repo.resolve():
        raise PublishError(
            f"{repo} is not the git worktree root (top-level is {top})", code=3
        )
    resolve_task_dir(repo, slug)
    disallowed = [
        path for path in porcelain_paths(repo) if not is_allowed(path, prefixes)
    ]
    if disallowed:
        raise PublishError(
            "working tree is dirty outside the managed allowlist: "
            + ", ".join(sorted(disallowed))
            + " (commit or stash unrelated work, or extend --allow-path-prefix)",
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
    task_dir.rename(archive_dir)
    try:
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


def work_commit(repo: Path, message_file: Path) -> str:
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-q", "-F", str(message_file)], cwd=repo)
    return git_out(["rev-parse", "HEAD"], cwd=repo)


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
) -> str:
    run(
        [python_bin, str(Path(".trellis/scripts/task.py")), "archive", slug],
        cwd=repo,
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
    return git_out(["rev-parse", "HEAD"], cwd=repo)


def completion_receipt(
    repo: Path, base: str, head: str, receipt_out: Path
) -> str:
    result = run(
        [
            "node",
            "scripts/sd-ai-command-pack-review-preflight.mjs",
            "final-bundle",
            "--mode",
            "completion",
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
    prefixes = tuple(DEFAULT_ALLOWED_PREFIXES) + tuple(args.allow_path_prefix or ())
    record_session = (
        Path(args.record_session)
        if args.record_session
        else Path(__file__).resolve().parent
        / "sd-ai-command-pack-record-session.py"
    )
    receipt_out = Path(args.receipt_out).resolve()
    month = args.archive_month or datetime.now(timezone.utc).strftime("%Y-%m")

    check_preconditions(repo, args.slug, prefixes)
    base = git_out(["rev-parse", "HEAD"], cwd=repo)

    indexed = (repo / args.repomix_script).exists() and (
        repo / args.repomix_output
    ).exists()
    if indexed:
        regenerate_repomix_post_archive(
            repo, args.slug, args.repomix_script, args.repomix_output, month
        )

    h1 = work_commit(repo, Path(args.work_message_file).resolve())
    h3 = archive_and_journal(
        repo,
        args.slug,
        python_bin=args.python,
        record_session=record_session,
        title=args.title,
        summary=args.summary,
        commit=h1,
        changes=args.change,
        tests=args.test,
    )
    status = completion_receipt(repo, h1, h3, receipt_out)
    if status != "valid":
        raise PublishError(
            f"completion receipt status is {status!r}, not 'valid' (not pushed); "
            f"see {receipt_out}",
            code=4,
        )
    assert_trellis_only_delta(repo, h1, h3)

    pushed = False
    if not args.no_push:
        run(["git", "push", "-u", args.remote, args.branch], cwd=repo)
        pushed = True

    return {
        "repo": str(repo),
        "slug": args.slug,
        "base": base,
        "h1": h1,
        "h3": h3,
        "receipt": status,
        "repomixIndexed": indexed,
        "pushed": pushed,
        "receiptPath": str(receipt_out),
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
