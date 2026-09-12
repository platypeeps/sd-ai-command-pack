"""Task controls and workspace reads, backed by the dashboard's operations.

These verbs do not need a checkout. A new task takes the repository enclosing
the current directory by default; ``--no-repo`` files one that belongs to no
checkout, and ``--here`` refuses rather than filing a repo-less task.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import stat
from typing import Any

import sd_handoff_rows
import sd_lib


class WorkRefusal(Exception):
    """A workflow operation was refused without changing its state."""


def _task_repo(args: argparse.Namespace, connection: Any) -> str | None:
    """Which checkout a new task owns, defaulting to the one enclosing cwd.

    Filing from inside a checkout and getting no repository is the mistake
    ``--here`` existed to prevent, and a flag nobody remembers prevents
    nothing: 41 of the rows it guards were filed without it. So the enclosing
    repository is the default and the flags are the two exceptions --
    ``--no-repo`` for work that belongs to no checkout, ``--here`` to refuse
    rather than file a repo-less task by accident.

    Two things make the default narrower than "whatever cwd is in".

    A linked worktree resolves to its main checkout. The worktree is a
    temporary path and the row outlives it, so storing the worktree would
    name a directory that is gone by the time anyone reads the row.

    An unregistered checkout falls back to no repository rather than
    refusing. `capture_task` rejects a repo the `repo` table does not carry,
    so a default that passed cwd through unconditionally would turn
    `sd task add` from a verb that works anywhere into one that fails in
    every checkout nobody has registered. A default may not break the
    command; only an explicit `--here` gets to refuse, and it says which of
    the two reasons applied.
    """
    if args.no_repo:
        return None
    root = sd_lib.repo_root()
    if root is None:
        if args.here:
            raise WorkRefusal("--here requires a Git checkout")
        return None
    repo = str(sd_lib.main_worktree_root(root))
    if connection.execute("SELECT 1 FROM repo WHERE path = ?", (repo,)).fetchone():
        return repo
    if args.here:
        raise WorkRefusal(f"--here: {repo} is not a registered repository")
    return None


def _belongs_to(value: str) -> str:
    """Which checkout `--belongs-to` names, read the way `add` reads cwd.

    Not spelled `--repo`, and the reason is R10-D6 rather than taste:
    `tests/test_verb_inventory.py` refuses that option name anywhere under
    `bin/`, because a command that can be *pointed at* another checkout is one
    that can act on it. This flag only sets a field on a row -- the command
    still runs where the caller stands -- but `sd task add` met the same
    question one verb earlier and answered it without `--repo` too, in the
    `--here` / `--no-repo` pair. One family, one spelling; a second answer
    here would make the rule read as negotiable.

    A row's `repo` is an absolute path and a foreign key into the `repo`
    table, so the argument has to become one before the library sees it.
    `--belongs-to .` from inside a checkout is the spelling a caller standing
    in the misfiled row's real repository will reach for, and a relative path
    is what a shell hands over; both resolve here rather than arriving as a
    string the `repo` table has never heard of.

    A linked worktree resolves to its main checkout for the reason `add` does:
    the worktree is a temporary path and the row outlives it. A path that is
    no checkout at all is passed through resolved, because a registered
    repository is whatever the `repo` table carries and this is not the place
    that decides -- `edit_item` refuses an unregistered path by name, and one
    rule with one owner is the point of the move going through the library.
    """
    path = pathlib.Path(value).expanduser()
    root = sd_lib.repo_root(path)
    if root is None:
        return str(path.resolve())
    return str(sd_lib.main_worktree_root(root))


def _edit_changes(args: argparse.Namespace) -> dict[str, Any]:
    """The fields `edit` was asked to set, or a refusal naming the omission.

    Lifted out of `run` rather than left inline: `edit` is the one verb whose
    arguments need work before the library sees them -- a cleared field is a
    `None` no `getattr` loop can distinguish from an absent one, and a
    checkout is a path that has to be resolved -- and `run`'s job is to pick
    the operation, not to do this.
    """
    changes: dict[str, Any] = {
        field: getattr(args, field) for field in ("title", "body", "priority", "due")
        if getattr(args, field) is not None
    }
    if args.clear_priority:
        changes["priority"] = None
    if args.clear_due:
        changes["due"] = None
    # The field `add` sets and nothing could change afterwards. It is not in
    # the loop above because the flag carries a path and the row carries a
    # checkout; `_belongs_to` is the one step between them, and `edit_item` --
    # not this function -- decides whether the checkout is registered and
    # writes the note that records the move.
    if args.belongs_to is not None:
        changes["repo"] = _belongs_to(args.belongs_to)
    if args.no_repo:
        changes["repo"] = None
    if not changes:
        raise WorkRefusal("edit requires a field to change")
    return changes


def _library():
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.workflow as workflow
    except ImportError as error:
        raise WorkRefusal(
            "the installed sd_db lacks workflow controls; install the current "
            "system/local-sd-db build"
        ) from error
    return sd_db, workflow


#: What `register` calls that a build predating it does not carry, as
#: `(module suffix, attribute)`.
#:
#: The import above cannot stand in for this. `sd_db.workflow` has existed for
#: a long time and imports cleanly on every build; `register_work_item` is new
#: inside it. Checking only that the module arrived would let a stale library
#: reach the call and fail there as an `AttributeError` -- a traceback, in a
#: verb that is careful never to produce one, and naming a Python attribute
#: rather than the install that is behind. Named, all three, so the remedy is
#: a sentence instead of a stack.
REGISTER_NEEDS = (
    ("workflow", "register_work_item"),
    ("repos", "registered_for"),
    ("sources.docs_work", "default_branch"),
)


def _register_library(sd_db):
    """The three modules `register` reads and writes through, or a refusal.

    Checked before the first of them is called, so a machine carrying a build
    that predates the verb is told which install to fix rather than which
    attribute was absent.
    """

    import importlib  # noqa: PLC0415 - only this verb needs it

    found = {}
    missing = []
    for module_name, attribute in REGISTER_NEEDS:
        try:
            module = importlib.import_module(f"sd_db.{module_name}")
        except ImportError:
            missing.append(f"sd_db.{module_name}")
            continue
        if not hasattr(module, attribute):
            missing.append(f"sd_db.{module_name}.{attribute}")
            continue
        found[module_name] = module
    if missing:
        raise WorkRefusal(
            "the installed sd_db cannot register work items; it is missing "
            + ", ".join(missing)
            + ". Install the current system/local-sd-db build with the pack's "
            "installer (`sd-install`), which provisions it from the `system` "
            "checkout at its tag, then run this again."
        )
    return tuple(found[name] for name, _ in REGISTER_NEEDS)


def _frontmatter(prd: pathlib.Path) -> tuple[str, str]:
    """`title:` and `created:`, or a refusal naming the file and what it lacks."""

    try:
        from sd_db.sources.frontmatter import FrontmatterError  # noqa: PLC0415
        from sd_db.sources.frontmatter import read as read_frontmatter  # noqa: PLC0415
    except ImportError as error:
        raise WorkRefusal(
            "the installed sd_db cannot read work-item frontmatter; install "
            "the current system/local-sd-db build"
        ) from error
    try:
        front, _ = read_frontmatter(prd.read_text(encoding="utf-8"))
    except (FrontmatterError, OSError, UnicodeError) as failure:
        raise WorkRefusal(f"{prd}: {failure}") from failure
    title, created = front.get("title"), front.get("created")
    if not title or not created:
        raise WorkRefusal(
            f"{prd} needs `title:` and `created:` in its frontmatter; "
            "the row takes its name and its date from the file, not from you")
    return str(title), str(created)


def _register(sd_db, connection, args, who: str) -> Any:
    """Make the row that owns a `docs/work` folder already on disk.

    The folder is the input and git is the rest of it: the title and date come
    from the frontmatter, the branch and commit from the checkout, and the
    status is always `planning`, because an item nobody has started is what a
    new folder is. Nothing here decides anything, which is why it takes no
    flags beyond the path.

    There is no repository argument, for the reason `sd-status` has none
    (R10-D6): the checkout is the one enclosing the working directory, and the
    path is relative to it. A row whose path resolved against a checkout the
    caller was not standing in would name a file nobody can read. Which *row*
    that checkout belongs to is a further question, answered below by its
    origin rather than by its place on this disk.
    """

    workflow, repos, docs_work = _register_library(sd_db)
    root = sd_lib.repo_root()
    if root is None:
        raise WorkRefusal("register requires a Git checkout")
    prd = (root / args.path).resolve()
    try:
        relative = prd.relative_to(root).as_posix()
    except ValueError:
        raise WorkRefusal(f"{args.path} is outside {root}") from None
    if not prd.is_file():
        raise WorkRefusal(f"no file at {prd}")
    title, created = _frontmatter(prd)
    # The repository this checkout *is*, not the directory it sits in. A
    # runner clone carries the same files at another path, and resolving by
    # path alone refuses every run made from one.
    origin = sd_lib.git_output(["remote", "get-url", "origin"], root)
    repo = repos.registered_for(connection, str(root), origin or None)
    commit = sd_lib.git_output(
        ["log", "-1", "--format=%H", "--", relative], root)
    # The branch the work will land on, read from `origin/HEAD`, and never the
    # one that happens to be checked out. Registration comes before the work
    # branch exists (`sd-plan` writes the plan at step 2 and branches at step
    # 6), so the checked-out branch is whatever the planner was standing on --
    # `main`, or some unrelated feature branch, or the literal string `HEAD`
    # on a detached checkout. The library's own reader answers it, so a folder
    # registered here and one registered by `sd-db work register` get the same
    # row rather than two spellings of the branch.
    return workflow.register_work_item(
        connection, repo=repo, path=relative, title=title, created_at=created,
        branch=docs_work.default_branch(root),
        source_commit=commit or None, who=who,
    )


def _emit(value: Any, *, machine: bool) -> None:
    if machine:
        print(json.dumps(value, ensure_ascii=False))
        return
    rows = value if isinstance(value, list) else [value["item"]]
    if not rows:
        print("No items.")
    for row in rows:
        priority = f" · P{row['priority']}" if row.get("priority") else ""
        due = f" · due {row['due']}" if row.get("due") else ""
        print(f"#{row['id']}  {row['status']}  {row['title']}{priority}{due}")
    if isinstance(value, dict):
        # `register` is the one verb that can do nothing and still succeed.
        # Registering twice is deliberately not an error -- the unique index
        # makes the second call safe -- but a caller who cannot tell the two
        # apart will read "here is the row" as "I just made it".
        if value.get("created") is False:
            print("already registered; nothing changed")
        for note in value.get("notes", []):
            resolved = " · resolved" if note.get("resolved_at") else ""
            print(f"  note #{note['id']} · {note['kind']}{resolved}: {note['body']}")
        print(f"revision: {value['revision']}")


#: A delivery commit as `sd_db.progress` requires it to be spelled: the full
#: object name, lowercase, SHA-1 or SHA-256. Abbreviations are refused there
#: and are refused here, so `--delivered-by` and `sd work deliver` accept
#: exactly the same argument and a caller who learns one has learned both.
COMMIT_LENGTHS = (40, 64)
COMMIT_DIGITS = frozenset("0123456789abcdef")


def _is_commit(value: str) -> bool:
    """Whether `value` is a full lowercase object name, and nothing shorter."""
    return len(value) in COMMIT_LENGTHS and COMMIT_DIGITS.issuperset(value)


#: What `sd work deliver` writes on the transition it makes, and therefore
#: what `--delivered-by` writes on the transition a task makes. One sentence,
#: one format, so "which commit delivered this item" is one query over
#: `note.kind = 'status'` rather than one per kind.
DELIVERY_REASON = "delivered at {commit} on {ref}"


def _verified_tip(root: pathlib.Path) -> tuple[str, str]:
    """The default branch's current tip, fetched, and the ref it was read from.

    The same thing `sd_db.progress._delivery_evidence` establishes before it
    will record a delivery, asked here through `sd_lib.upstream` because a
    checkout with no remote still has a default branch and a feature branch's
    unpushed trailer must not stand in for its tip.
    """
    remote, default = sd_lib.upstream(root)
    if not remote:
        head = sd_lib.git_output(["symbolic-ref", "--quiet", "HEAD"], root)
        if head not in ("refs/heads/main", "refs/heads/master"):
            raise WorkRefusal("a local-only delivery must be verified on main or master")
        tip = sd_lib.git_output(["rev-parse", "--verify", "HEAD^{commit}"], root)
        if not tip:
            raise WorkRefusal(f"{root} has no commit on {head} to verify against")
        return tip, head
    if sd_lib.git_output(["fetch", "--no-tags", remote, default], root) is None:
        raise WorkRefusal(f"could not fetch {remote} {default}; delivery cannot be verified")
    tip = sd_lib.git_output(["rev-parse", "--verify", "FETCH_HEAD^{commit}"], root)
    if not tip:
        raise WorkRefusal(f"{remote}/{default} yielded no tip to verify against")
    return tip, f"{remote}/{default}"


def _delivery_reason(row: Any, commit: str) -> str:
    """The delivery sentence for `commit`, or a refusal naming what failed.

    `sd work deliver` is the only writer of delivery evidence and it refuses a
    `kind=task` row outright, so an ordinary task closed with `task status
    done` recorded who and when and nothing about what shipped it. The
    verification is not the part that belonged to work items -- reachability
    and a `Delivers:` trailer are facts about a commit, not about a kind -- so
    it is asked here and the answer goes on the transition.

    A trailer git will not read back is named as that, and never as a missing
    one. `demoted_trailers` is the whole of sd:590 in this path: the blank line
    that costs an item its evidence looks exactly like an author who forgot.
    """
    if not _is_commit(commit):
        raise WorkRefusal("--delivered-by takes the full lowercase commit ID")
    if not row["repo"]:
        raise WorkRefusal(
            f"item {row['id']} belongs to no checkout, so no commit can be verified "
            "for it; `sd task edit` with `--belongs-to` names one")
    root = pathlib.Path(row["repo"])
    if not root.is_dir():
        raise WorkRefusal(f"{root} is unavailable; delivery cannot be verified")
    if sd_lib.git_output(["rev-parse", "--verify", f"{commit}^{{commit}}"], root) != commit:
        raise WorkRefusal(f"{root} has no commit {commit}")
    tip, ref = _verified_tip(root)
    if sd_lib.git_output(["merge-base", "--is-ancestor", commit, tip], root) is None:
        raise WorkRefusal(f"{commit} is not reachable from {ref}")
    message = sd_lib.git_output(["show", "-s", "--format=%B", commit], root) or ""
    wanted = f"sd:{row['id']}"
    demoted = [line for line in sd_lib.demoted_trailers(message)
               if line.partition(":")[0] == "Delivers" and line.partition(":")[2].strip() == wanted]
    if demoted:
        raise WorkRefusal(
            f"{commit} states {demoted[0]!r} outside the trailer block git reads, so "
            "nothing can see it; re-record it contiguously with the other trailers")
    block = sd_lib.trailer_block(message).splitlines()
    if not any(line.partition(":")[0] == "Delivers" and line.partition(":")[2].strip() == wanted
               for line in block):
        raise WorkRefusal(f"{commit} carries no `Delivers: {wanted}` trailer")
    return DELIVERY_REASON.format(commit=commit, ref=ref)


def _status_reason(workflow: Any, connection: Any, args: argparse.Namespace) -> str | None:
    """What the transition records, verifying `--delivered-by` before it moves.

    Read and refused before the write, because a status that landed and then
    failed to record what shipped it is the hole the flag exists to close.
    """
    if not args.delivered_by:
        return args.reason
    if args.status != "done":
        raise WorkRefusal("--delivered-by belongs on the move to done")
    row = workflow.item_state(connection, args.item)["item"]
    if row["kind"] != "task":
        raise WorkRefusal(
            f"item {args.item} is a work item; `sd work deliver {args.item} "
            f"{args.delivered_by}` records its delivery")
    return _delivery_reason(row, args.delivered_by)


def _refuse_task_delivery(workflow: Any, connection: Any, args: argparse.Namespace) -> None:
    """Refuse `deliver` on an ordinary task, saying where the evidence goes.

    The library refuses it one call later and says only that the operation is
    for work items, which leaves a caller holding a real merged SHA with
    nowhere to put it -- four items closed on 2026-09-12 lost theirs that way,
    and the workaround was a note written by hand. A dead end that knows the
    way out and does not say it is the defect here, not the kind check.
    """
    if workflow.item_state(connection, args.item)["item"]["kind"] == "task":
        raise WorkRefusal(
            f"item {args.item} is an ordinary task, and delivery evidence for one "
            f"is recorded by `sd task status {args.item} done --delivered-by "
            f"{args.commit}`, which verifies the same commit")


def run(args: argparse.Namespace) -> int:
    sd_db, workflow = _library()
    write = args.work_action not in {"today", "items", "item"}
    connection = sd_handoff_rows.connect(sd_db, write=write)
    try:
        action = args.work_action
        who = getpass.getuser()
        revision = getattr(args, "if_revision", None)
        result: Any
        if action == "today":
            result = [dict(row) for row in sd_db.reads.today_items(connection)]
        elif action == "items":
            result = [dict(row) for row in sd_db.reads.backlog_items(connection)]
            result = [row for row in result
                      if (not args.open or row["status"] != "done")
                      and (not args.kind or row["kind"] == args.kind)
                      and (not args.status or row["status"] == args.status)]
        elif action == "item":
            result = workflow.item_state(connection, args.item)
        elif action == "add":
            result = workflow.capture_task(
                connection, title=args.title, body=args.body, priority=args.priority,
                due=args.due, repo=_task_repo(args, connection), who=who,
            )
        elif action == "edit":
            changes = _edit_changes(args)
            result = workflow.edit_item(
                connection, args.item, changes, who=who, expected_revision=revision)
        elif action == "status":
            result = workflow.change_status(
                connection, args.item, args.status, who=who,
                expected_revision=revision,
                reason=_status_reason(workflow, connection, args))
        elif action == "note":
            result = workflow.add_item_note(
                connection, args.item, body=args.body, kind=args.kind, who=who,
                expected_revision=revision)
        elif action == "resolve":
            result = workflow.resolve_item_note(
                connection, args.note, who=who, expected_revision=revision)
        elif action == "register":
            result = _register(sd_db, connection, args, who)
        elif action in {"relink", "cancel", "deliver"}:
            import sd_db.progress as progress

            if action == "relink":
                result = progress.relink_artifact(
                    connection, args.item, args.path, who=who, expected_revision=revision)
            elif action == "cancel":
                result = progress.cancel_work(
                    connection, args.item, reason=args.reason, who=who,
                    expected_revision=revision)
            else:
                _refuse_task_delivery(workflow, connection, args)
                result = progress.deliver_work(
                    connection, args.item, args.commit, who=who,
                    expected_revision=revision)
        else:
            raise WorkRefusal(f"unknown workflow operation: {action}")
        _emit(result, machine=args.json)
        return 0
    except sd_db.SdDbError as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()


def _output(parser: argparse.ArgumentParser, action: str, *, revision: bool = False) -> None:
    parser.add_argument("--json", action="store_true", help="machine-readable")
    if revision:
        parser.add_argument("--if-revision", help="refuse if the item changed since this revision")
    parser.set_defaults(handler=run, work_action=action)


def _contribution_library():
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.contributions as contributions
    except ImportError as error:
        raise WorkRefusal(
            "the installed sd_db lacks contribution controls; install the current "
            "system/local-sd-db build"
        ) from error
    return sd_db, contributions


def _contribution_changes(path: str) -> dict[str, Any]:
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON number: {value}")

    try:
        # Nonblocking open also makes FIFO input refuse instead of waiting for a writer.
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("input must be a regular file")
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError("input exceeds 65536 bytes")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        return value
    except (OSError, ValueError, RecursionError) as error:
        raise WorkRefusal(f"contribution input refused: {error}") from error


CONTRIBUTION_ORDER = (
    "url", "local_clone", "local_branch", "tested_commit", "blocked_on", "depends_on",
    "evidence", "reasons", "event_ids", "attention_sources",
)

# Printed by the header lines above the loop, so the loop must not repeat them.
CONTRIBUTION_SHOWN = (
    "key", "lane", "title", "local_status", "external_state", "freshness", "evidence_verified",
)


def _emit_contributions(value: Any, *, machine: bool) -> None:
    if machine:
        print(json.dumps(value, ensure_ascii=False))
        return
    if isinstance(value, dict) and "item" in value:
        _emit(value, machine=False)
        print(f"contribution: item:{value['item']['id']}")
        return
    rows = value if isinstance(value, list) else [value.get("contribution")]
    for row in rows:
        if row is None:
            continue
        print(f"{row['key']}  {row['lane']}  {row['title']}")
        print(f"  local: {row.get('local_status')} · external: {row.get('external_state')}"
              f" · freshness: {row.get('freshness')}")
        print(f"  evidence_verified: {json.dumps(row.get('evidence_verified', False))}")
        # Order here, membership from the row: the seven keys this tuple did
        # not name were dropped in silence on every live contribution.
        for field in sd_lib.display_fields(row, CONTRIBUTION_ORDER, CONTRIBUTION_SHOWN):
            if row.get(field):
                print(f"  {field}: {json.dumps(row[field], ensure_ascii=False)}")
    if not rows:
        print("No contributions.")
    if isinstance(value, dict):
        print(f"key: {value['key']}")
        for field in ("attention", "notifications"):
            print(f"{field}: {json.dumps(value.get(field), ensure_ascii=False)}")
        print(f"revision: {value['revision']}")


def run_contribution(args: argparse.Namespace) -> int:
    changes = _contribution_changes(args.file) if args.verb in {"add", "edit"} else None
    sd_db, contributions = _contribution_library()
    connection = None
    try:
        connection = sd_handoff_rows.connect(sd_db, write=args.verb not in {"list", "show"})
        who = getpass.getuser()
        result: Any
        if args.verb == "add":
            result = contributions.capture(connection, title=args.title, changes=changes, who=who)
        elif args.verb == "edit":
            result = contributions.configure(
                connection, args.item, changes, who=who, expected_revision=args.if_revision)
        elif args.verb == "list":
            result = contributions.projection(connection)
        elif args.verb in {"show", "ack"}:
            if args.verb == "show":
                result = contributions.snapshot(connection, args.key)
            else:
                result = contributions.acknowledge(
                    connection, args.key, args.event, who=who, expected_revision=args.if_revision)
            result = {**result, "contribution": next(
                (row for row in contributions.projection(connection)
                 if row["key"] == result["key"] or f"item:{row.get('item_id')}" == result["key"]
                 or any(source["key"] == result["key"] for source in row.get("attention_sources", []))),
                None,
            )}
        else:
            raise WorkRefusal(f"unknown contribution operation: {args.verb}")
        _emit_contributions(result, machine=args.json)
        return 0
    except sd_db.SdDbError as error:
        raise WorkRefusal(str(error)) from error
    finally:
        if connection is not None:
            connection.close()


def _register_contributions(verbs: Any) -> None:
    group = verbs.add_parser("contribution", help="track local work and upstream contribution attention")
    actions = group.add_subparsers(dest="verb", required=True)
    for action in ("add", "edit", "list", "show", "ack"):
        parser = actions.add_parser(action)
        parser.add_argument("--json", action="store_true", help="machine-readable")
        parser.set_defaults(handler=run_contribution)
        if action in {"add", "edit"}:
            parser.add_argument("--file", required=True, help="contribution changes as JSON (maximum 64 KiB)")
            if action == "add":
                parser.add_argument("title")
            else:
                parser.add_argument("item", type=int)
                parser.add_argument("--if-revision", help="item revision from sd store item")
        if action in {"show", "ack"}:
            parser.add_argument("key", help="item:ID or github:https://github.com/OWNER/REPO/pull/NUMBER")
        if action == "ack":
            parser.add_argument("--event", action="append", required=True, help="observed event ID; repeat as needed")
            parser.add_argument("--if-revision", required=True, help="checkpoint revision from contribution show")


def register(groups: Any, store: Any) -> None:
    """Extend the existing parser, preserving the plugin note-store verbs."""
    today = groups.add_parser("today", help="due and active work, in dashboard order")
    _output(today, "today")

    items = store.add_parser("items", help="workspace items from the shared database")
    items.add_argument("--open", action="store_true", help="exclude done items")
    items.add_argument("--kind", help="filter by item kind")
    items.add_argument("--status", help="filter by workflow status")
    _output(items, "items")
    item = store.add_parser("item", help="one workspace item, notes, and revision")
    item.add_argument("item", type=int)
    _output(item, "item")

    task = groups.add_parser("task", help="capture and manage work without files or GitHub")
    verbs = task.add_subparsers(dest="verb", required=True)
    _register_contributions(verbs)
    add = verbs.add_parser("add", help="capture a standalone task")
    add.add_argument("title")
    add.add_argument("--body", default="")
    add.add_argument("--priority", type=int, choices=range(1, 5))
    add.add_argument("--due", help="YYYY-MM-DD")
    where = add.add_mutually_exclusive_group()
    where.add_argument("--here", action="store_true",
                       help="refuse unless this is a checkout (one is used by default)")
    where.add_argument("--no-repo", action="store_true",
                       help="file a task that belongs to no checkout")
    _output(add, "add")

    edit = verbs.add_parser("edit", help="change a task's details")
    edit.add_argument("item", type=int)
    edit.add_argument("--title")
    edit.add_argument("--body")
    priority = edit.add_mutually_exclusive_group()
    priority.add_argument("--priority", type=int, choices=range(1, 5))
    priority.add_argument("--clear-priority", action="store_true")
    due = edit.add_mutually_exclusive_group()
    due.add_argument("--due", help="YYYY-MM-DD")
    due.add_argument("--clear-due", action="store_true")
    # `--belongs-to` and not `--repo`: see `_belongs_to`. `--no-repo` is the
    # word `add` already uses for the same idea, so the pair reads the same on
    # both verbs.
    belongs = edit.add_mutually_exclusive_group()
    belongs.add_argument("--belongs-to", metavar="PATH",
                         help="move the task to a registered checkout (`.` is this one)")
    belongs.add_argument("--no-repo", action="store_true",
                         help="leave the task belonging to no checkout")
    _output(edit, "edit", revision=True)

    status = verbs.add_parser("status", help="change status with an atomic history entry")
    status.add_argument("item", type=int)
    status.add_argument("status")
    reason = status.add_mutually_exclusive_group()
    reason.add_argument("--reason")
    # `--delivered-by` and not `--commit`: the row records what delivered the
    # task, and the word says so where `--commit` would only say which one.
    # Exclusive with `--reason` because both write the same field and a caller
    # supplying both would have one of them silently dropped.
    reason.add_argument("--delivered-by", metavar="SHA",
                        help="full SHA carrying `Delivers: sd:<id>`, verified against "
                             "the default branch and recorded on the transition")
    _output(status, "status", revision=True)

    note = verbs.add_parser("note", help="add an item note or follow-up")
    note.add_argument("item", type=int)
    note.add_argument("--body", required=True)
    note.add_argument("--kind", default="comment",
                      choices=("comment", "followup", "question", "decision", "proposal"),
                      help="note kind (default: comment)")
    _output(note, "note", revision=True)
    resolve = verbs.add_parser("resolve", help="resolve an item note")
    resolve.add_argument("note", type=int)
    _output(resolve, "resolve", revision=True)

    work = groups.add_parser("work", help="maintain artifact links and verified completion")
    working = work.add_subparsers(dest="verb", required=True)
    relink = working.add_parser("relink", help="link a moved artifact without changing item identity")
    relink.add_argument("item", type=int)
    relink.add_argument("path", help="existing artifact path relative to the item's repository")
    _output(relink, "relink", revision=True)
    cancel = working.add_parser("cancel", help="record a deliberate cancellation, with a reason")
    cancel.add_argument("item", type=int)
    cancel.add_argument("--reason", required=True)
    _output(cancel, "cancel", revision=True)
    register_verb = working.add_parser(
        "register", help="make the row that owns a docs/work folder on disk")
    register_verb.add_argument(
        "path", help="docs/work/<item>/prd.md, relative to the repository")
    _output(register_verb, "register")

    deliver = working.add_parser("deliver", help="verify a delivery commit and complete its item")
    deliver.add_argument("item", type=int)
    deliver.add_argument("commit", help="full commit SHA carrying the item's Delivers trailer")
    _output(deliver, "deliver", revision=True)
