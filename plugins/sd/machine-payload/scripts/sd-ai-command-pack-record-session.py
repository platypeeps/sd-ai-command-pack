#!/usr/bin/env python3
"""Record a Trellis session journal entry without template placeholders.

``add_session.py`` renders Testing and Next Steps through a bullet helper that
applies its prefix unconditionally, stamping ``- [OK] `` onto every item. A
line that already carries a status marker would become
``- [OK] [WARN] flaky lane``, and a pre-bulleted line ``- [OK] - already
bulleted``. This wrapper therefore normalizes those lines itself and patches
the two sections into the freshly written entry, rather than passing ``--test``
/ ``--next-step`` through.

Everything the runtime does correctly is delegated to it: the commit table is
rendered by ``add_session.py`` from the OIDs alone, including subject
resolution and cell escaping. This wrapper passes the Main Changes body through
``--content-file``, asserts the requested commits were recorded, verifies no
placeholders remain, and only then commits the journal.

If a previous run appended the session but failed later while staging or
committing, a retry patches the modified latest session instead of calling
``add_session.py`` again and duplicating the entry. (This is a different case
from ``add_session.py --idempotency-key``, which makes an already-*committed*
identical record a no-op; the entry this handles was never committed.)

The current git branch is passed explicitly when the caller does not provide
``--branch``, keeping the recorded branch tied to the checkout that did the
work as a stated invariant rather than an inherited default.

Supported vendored-Trellis floor: see
``.trellis/spec/tooling/vendored-trellis-compatibility.md``.

Exit codes:

* ``0`` - entry recorded (and committed unless ``--no-commit``).
* ``1`` - the entry could not be completed (placeholders remain, patch
  anchors missing, or the Trellis script failed).
* ``2`` - argument or environment error (unknown commit hash, missing
  Trellis script, not a git repository).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from sd_ai_command_pack_lib import (
    DEFAULT_TRELLIS_TIMEOUT,
    CommandError,
    atomic_write_text,
    build_environment_blocked_evidence,
    run_command,
)
from sd_ai_command_pack_lib import (
    run_git as run_git_command,
)

ADD_SESSION = Path(".trellis/scripts/add_session.py")
WORKSPACE = ".trellis/workspace"
PLACEHOLDERS = ("(Add details)", "(Add test results)", "(see git log)")
SESSION_HEADING_RE = re.compile(r"^## Session \d+: (.+)$", re.MULTILINE)
# Commit-table cells: | `b371f91` | subject |
JOURNAL_COMMIT_CELL_RE = re.compile(r"\|\s*`([0-9a-f]{7,40})`\s*\|")
MAX_DERIVED_COMMIT_SCAN = 200
MAX_DERIVED_COMMITS = 25


def run_git(*args: str) -> subprocess.CompletedProcess:
    return run_git_command(list(args), context="run git")


def commit_subject(commit_hash: str) -> str | None:
    result = run_git(
        "log", "-1", "--format=%s", "--end-of-options", commit_hash, "--"
    )
    if result.returncode != 0:
        return None
    subject = result.stdout.strip().splitlines()
    # A valid commit can carry an empty subject (--allow-empty-message);
    # only a failed lookup means the hash is unknown.
    return subject[0] if subject else "(empty subject)"


def recorded_commit_hashes() -> set[str]:
    """Every commit hash already cited by a journal commit table."""
    recorded: set[str] = set()
    for journal in Path(WORKSPACE).glob("*/journal*.md"):
        try:
            text = journal.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        recorded.update(JOURNAL_COMMIT_CELL_RE.findall(text))
    return recorded


def derive_work_commits() -> list[str]:
    """Unrecorded work commits reachable from HEAD, oldest first.

    ``add_session.py`` writes "(No commits - planning session)" whenever no
    hash is supplied, and the pack's own final-bundle validator then rejects
    that session with ``journal_commit_missing`` — two pack surfaces
    disagreeing by default, so the documented invocation produces an artifact
    the documented validator always refuses.

    Deriving the obvious answer removes the trap without guessing. A commit
    counts only when no journal already cites it and it changes something
    outside the workspace, so journal and index commits never nominate
    themselves. ``--commit -`` still asserts "genuinely none".

    Returns an empty list whenever the answer is not obvious — nothing to
    record, git unavailable, no recorded boundary inside the scan window, or
    more candidates than one session plausibly covers — leaving the previous
    behavior intact rather than inventing a commit list.
    """
    result = run_git(
        "log", f"--max-count={MAX_DERIVED_COMMIT_SCAN}", "--format=%H", "HEAD"
    )
    if result.returncode != 0:
        return []
    recorded = recorded_commit_hashes()
    if not recorded:
        return []
    candidates: list[str] = []
    for full_hash in result.stdout.split():
        if any(full_hash.startswith(short) for short in recorded):
            break
        candidates.append(full_hash)
    else:
        # Never reached a recorded commit inside the scan window, so the
        # boundary is unknown and these may reach back into ancient history.
        return []
    work: list[str] = []
    for full_hash in candidates:
        files = run_git(
            "show", "--name-only", "--format=", "--end-of-options", full_hash, "--"
        )
        if files.returncode != 0:
            return []
        paths = [line for line in files.stdout.splitlines() if line.strip()]
        if paths and all(path.startswith(f"{WORKSPACE}/") for path in paths):
            continue
        work.append(full_hash)
    if len(work) > MAX_DERIVED_COMMITS:
        return []
    work.reverse()
    return work


def current_git_branch() -> str | None:
    """Return the checked-out branch, or None for detached/unavailable git."""
    result = run_git("branch", "--show-current")
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def modified_workspace_journals() -> list[Path]:
    # -z gives NUL-delimited, unquoted paths, avoiding core.quotePath's
    # C-style escaping entirely (spaces and non-ASCII stay literal).
    result = run_git(
        "status",
        "--porcelain",
        "-z",
        "--untracked-files=all",
        "--",
        WORKSPACE,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise SystemExit(f"error: git status failed for {WORKSPACE}{suffix}")
    journals = []
    tokens = result.stdout.split("\0")
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if len(token) < 4:
            continue
        status_code = token[:2]
        path_text = token[3:]
        if "R" in status_code or "C" in status_code:
            # Rename/copy entries carry a second NUL-delimited token for the
            # other side of the move; the first token is the current path.
            if index < len(tokens):
                index += 1
        if path_text.endswith(".md") and "/journal-" in path_text:
            journals.append(Path(path_text))
    return journals


def existing_session_journals(journals: list[Path], title: str) -> list[Path]:
    """Return modified journals whose latest session has the retry title."""
    matches: list[Path] = []
    for journal in journals:
        try:
            text = journal.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            continue
        headings = list(SESSION_HEADING_RE.finditer(text))
        if headings and headings[-1].group(1) == title:
            matches.append(journal)
    return matches


def replace_section(block: str, heading: str, lines: list[str]) -> str | None:
    """Replace the body under `heading` in the session block; None if absent.

    A section with no content is omitted entirely from the rendered entry, so
    absence is an expected layout difference handled by
    ``replace_or_insert_section``, not an error here.
    """
    head = f"{heading}\n"
    start = block.find(head)
    if start == -1:
        return None
    body_at = start + len(head)
    end = block.find("\n### ", body_at)
    if end == -1:
        end = len(block)
    return block[:body_at] + "\n" + "\n".join(lines) + "\n" + block[end:]


def replace_or_insert_section(
    block: str, heading: str, lines: list[str], before: str | None = None
) -> str:
    """Replace the section body, or insert the whole section when absent.

    When inserting, place the section immediately before the `before`
    heading if that heading exists (to preserve the canonical Trellis
    section order); otherwise append at the end of the block.
    """
    patched = replace_section(block, heading, lines)
    if patched is not None:
        return patched
    section = f"\n\n{heading}\n\n" + "\n".join(lines)
    if before is not None:
        anchor = block.find(f"{before}\n")
        if anchor != -1:
            insert_at = block.rfind("\n\n", 0, anchor)
            if insert_at != -1:
                return block[:insert_at] + section + block[insert_at:]
    return block.rstrip("\n") + section + "\n"


def patch_last_session(
    journal: Path,
    title: str,
    hashes: list[str],
    tests: list[str],
    next_steps: list[str],
) -> str | None:
    """Patch the freshly appended session in place; return an error or None."""
    try:
        text = journal.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        return f"cannot read {journal}: {exc}"
    marker = f": {title}\n"
    heading_at = text.rfind(marker)
    if heading_at == -1:
        return f"could not find the new session heading for {title!r} in {journal}"
    block_start = text.rfind("\n## Session ", 0, heading_at)
    if block_start == -1:
        return f"could not find the session block start in {journal}"
    block = text[block_start:]

    # `add_session.py` resolves every subject from the same object database
    # this wrapper probes and renders the cell with `escape_markdown_cell`,
    # which collapses whitespace and escapes backslashes as well as pipes.
    # Rewriting the row here would only re-render it less correctly, so the
    # wrapper asserts the runtime recorded what it asked for and leaves the
    # rendering alone.
    for commit_hash in hashes:
        if f"`{commit_hash}`" not in block:
            return f"missing commit table row for {commit_hash} in {journal}"

    # The runtime omits a section it has no content for, and this wrapper
    # never passes --test, so the heading is normally absent and gets
    # inserted. On a retry the previous run's heading is already there and is
    # replaced instead. Canonical order: Testing before Status, Next Steps
    # after Status — anchor the Testing insert accordingly.
    block = replace_or_insert_section(
        block, "### Testing", tests, before="### Status"
    )

    if next_steps:
        block = replace_or_insert_section(block, "### Next Steps", next_steps)
    elif "### Next Steps\n" not in block:
        # The runtime omits this section when it has no content. Journal
        # entries carry it either way, so write the documented default rather
        # than leaving readers to infer completion from an absent heading.
        block = replace_or_insert_section(
            block, "### Next Steps", ["- None - task complete"]
        )

    remaining = [p for p in PLACEHOLDERS if p in block]
    if remaining:
        return f"placeholders remain after patching {journal}: {', '.join(remaining)}"

    try:
        atomic_write_text(journal, text[:block_start] + block, errors="strict")
    except OSError as exc:
        return f"cannot write {journal}: {exc}"
    return None


def _emit_recorded(journal: Path, *, committed: bool, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"outcome": "recorded", "committed": committed}))
        return
    if committed:
        print(f"Recorded session in {journal} and committed the journal entry.")
    else:
        print(f"Recorded session in {journal} (not committed).")


def _emit_git_metadata_block(
    *, operation: str, checkpoint: str, diagnostic: str, as_json: bool
) -> None:
    """Emit the shared git-metadata block after a successful journal append.

    The journal entry is already written and is re-detected (not re-appended) on
    retry, so the mutation is partial but recoverable and the commit is safe to
    retry once the Git write boundary is repaired. The fragment only rides the
    stdout channel under ``--json``; the human stderr output is unchanged.
    """

    if not as_json:
        return
    evidence = build_environment_blocked_evidence(
        boundary="git-metadata",
        operation=operation,
        checkpoint=checkpoint,
        mutation_state="partial-recoverable",
        retryable=True,
        recovery_action={
            "kind": "skill",
            "instruction": (
                "Repair the Git write boundary, then re-run record-session with "
                "the same --title; it reuses the already-written journal entry "
                "and retries the commit without duplicating it."
            ),
        },
        diagnostic=diagnostic,
    )
    print(json.dumps({"outcome": "blocked", "environmentBlocked": evidence}))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Record a complete Trellis session journal entry."
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument(
        "--commit",
        default="",
        help=(
            "Comma-separated commit hashes. Omit to derive the unrecorded work "
            "commits on HEAD; pass '-' to record a session with no commits."
        ),
    )
    parser.add_argument(
        "--change",
        action="append",
        required=True,
        help="Main Changes bullet (repeatable); '- ' is added when missing",
    )
    parser.add_argument(
        "--test",
        dest="tests",
        action="append",
        required=True,
        help=(
            "Testing line (repeatable): '- '-prefixed lines pass through, "
            "'[...]'-marked lines are bulleted, bare lines get '- [OK] '"
        ),
    )
    parser.add_argument(
        "--next-step",
        dest="next_steps",
        action="append",
        default=[],
        help="Next Steps bullet (repeatable); defaults to task-complete",
    )
    parser.add_argument("--branch", help="Passed through to add_session.py")
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Leave the workspace changes uncommitted",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Emit machine-readable stdout, including a structured "
            "environment-blocked fragment when a Git write boundary stops the "
            "commit after the journal entry is written"
        ),
    )
    args = parser.parse_args(argv[1:])

    toplevel = run_git("rev-parse", "--show-toplevel")
    if toplevel.returncode != 0:
        print("error: not a git repository", file=sys.stderr)
        return 2
    # Normalize to the repository root so the relative Trellis paths and
    # git pathspecs resolve when invoked from a subdirectory.
    os.chdir(toplevel.stdout.strip())
    if not ADD_SESSION.is_file():
        print(f"error: {ADD_SESSION} not found; is Trellis initialized?", file=sys.stderr)
        return 2

    commit_arg = args.commit.strip()
    asserted_no_commits = commit_arg == "-"
    if asserted_no_commits:
        # add_session.py's explicit no-commits sentinel.
        commit_arg = ""
    hashes = [h.strip() for h in commit_arg.split(",") if h.strip()]
    if not hashes and not asserted_no_commits:
        hashes = derive_work_commits()
        if hashes and not args.json:
            print(
                f"[sd-record-session] --commit not given; recording "
                f"{len(hashes)} unrecorded work commit(s): "
                f"{', '.join(h[:7] for h in hashes)}. "
                "Pass --commit - to record a session with no commits.",
                file=sys.stderr,
            )
    seen_hashes: set[str] = set()
    for commit_hash in hashes:
        if commit_hash.startswith("-"):
            print(f"error: invalid commit hash: {commit_hash}", file=sys.stderr)
            return 2
        if commit_hash in seen_hashes:
            print(f"error: duplicate commit hash: {commit_hash}", file=sys.stderr)
            return 2
        seen_hashes.add(commit_hash)
    # `add_session.py` also refuses an unresolvable OID before writing
    # anything, so this probe no longer supplies the subject -- it preserves
    # this wrapper's exit-code contract, where a bad argument exits 2 rather
    # than surfacing the runtime's failure as a generic 1.
    for commit_hash in hashes:
        if commit_subject(commit_hash) is None:
            print(f"error: unknown commit hash: {commit_hash}", file=sys.stderr)
            return 2

    def as_bullet(line: str) -> str:
        stripped = line.strip()
        return line if stripped.startswith("- ") else f"- {stripped}"

    def as_test_line(line: str) -> str:
        stripped = line.strip()
        if stripped.startswith("- "):
            return line
        if stripped.startswith("["):
            # Already carries a status marker ([WARN], [SKIP], ...);
            # do not stamp [OK] over it.
            return f"- {stripped}"
        return f"- [OK] {stripped}"

    changes = [as_bullet(c) for c in args.change]
    tests = [as_test_line(t) for t in args.tests]
    next_steps = [as_bullet(n) for n in args.next_steps]

    before_journals = modified_workspace_journals()
    retry_journals = existing_session_journals(before_journals, args.title)
    if len(retry_journals) > 1:
        print(
            "error: multiple modified journals already contain a session titled "
            f"{args.title!r}; refusing to append another entry",
            file=sys.stderr,
        )
        return 1
    if retry_journals:
        journals = retry_journals
    else:
        before = set(before_journals)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8", errors="strict"
        ) as handle:
            handle.write("\n".join(changes) + "\n")
            content_file = Path(handle.name)
        try:
            command = [
                sys.executable,
                str(ADD_SESSION),
                "--title",
                args.title,
                "--summary",
                args.summary,
                "--content-file",
                str(content_file),
                "--no-commit",
            ]
            if hashes:
                command.extend(["--commit", ",".join(hashes)])
            # resolve_session_branch already prefers the checkout over stale
            # task.json metadata. Passing it explicitly keeps that tie a stated
            # invariant of this wrapper rather than an inherited default.
            branch = args.branch or current_git_branch()
            if branch:
                command.extend(["--branch", branch])
            result = run_command(
                command,
                timeout=DEFAULT_TRELLIS_TIMEOUT,
                capture_output=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                context="record the Trellis session journal",
            )
            if result.returncode != 0:
                # Operator-facing tool: surface the Trellis script's own output
                # (missing developer init, index marker issues, ...).
                if result.stdout:
                    print(result.stdout, file=sys.stderr)
                print(
                    f"error: add_session.py exited {result.returncode}",
                    file=sys.stderr,
                )
                return 1
        finally:
            content_file.unlink(missing_ok=True)

        after = modified_workspace_journals()
        journals = [j for j in after if j not in before] or after
    if len(journals) != 1:
        # A journal dirtied before the run makes the before/after set
        # ambiguous; the entry we just wrote is the one carrying the title.
        marker = f": {args.title}\n"
        titled = []
        for j in journals:
            try:
                if marker in j.read_text(encoding="utf-8", errors="strict"):
                    titled.append(j)
            except (OSError, UnicodeError):
                continue
        if len(titled) == 1:
            journals = titled
    if len(journals) != 1:
        print(
            "error: expected exactly one modified journal file, found: "
            + (", ".join(str(j) for j in journals) or "none"),
            file=sys.stderr,
        )
        return 1

    error = patch_last_session(
        journals[0], args.title, hashes, tests, next_steps
    )
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.no_commit:
        _emit_recorded(journals[0], committed=False, as_json=args.json)
        return 0

    # Stage only what this run wrote: the journal entry plus the sibling
    # index.md that add_session.py maintains. A bare `git add` on the
    # workspace would sweep unrelated dirty files into the commit.
    stage = [journals[0], journals[0].parent / "index.md"]
    stage_args = [str(path) for path in stage if path.exists()]
    try:
        added = run_git("add", "--", *stage_args)
        if added.returncode != 0:
            # Surface git's own output (pathspec, permission, index-lock
            # errors), matching the commit and add_session failure paths.
            for stream in (added.stdout, added.stderr):
                if stream:
                    print(stream, file=sys.stderr)
            print("error: git add failed", file=sys.stderr)
            _emit_git_metadata_block(
                operation="stage the session journal",
                checkpoint="journal-recorded",
                diagnostic="\n".join(
                    stream for stream in (added.stdout, added.stderr) if stream
                ),
                as_json=args.json,
            )
            return 1
        commit = run_command(
            ["git", "commit", "-m", "chore: record journal", "--", *stage_args],
            capture_output=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            context="commit the session journal",
        )
        if commit.returncode != 0:
            print(commit.stdout, file=sys.stderr)
            print("error: git commit failed", file=sys.stderr)
            _emit_git_metadata_block(
                operation="commit the session journal",
                checkpoint="journal-staged",
                diagnostic=commit.stdout or "",
                as_json=args.json,
            )
            return 1
    except CommandError as error:
        # git itself could not run (missing binary or timeout), never a parsed
        # stderr guess. The journal is already written and re-detected on retry,
        # so this is a retryable git-metadata block with no duplicated mutation.
        print(f"error: {error}", file=sys.stderr)
        _emit_git_metadata_block(
            operation="run git to commit the session journal",
            checkpoint="journal-recorded",
            diagnostic=str(error),
            as_json=args.json,
        )
        return 2

    _emit_recorded(journals[0], committed=True, as_json=args.json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except CommandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
