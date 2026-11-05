"""Your issues (sd:4628): each repo's Jira and GitHub issues assigned to or filed by the operator, on Today (sd:5645).

The rows are `sd_db.repos.mine_issues` (pack sd:4636): the open `shadow` issues whose tracker and repo match a repo's issue
sources (`jira=KEY`, `github=owner/name`, sd:3461) and whose `reason` is `assigned` or `filed`. Watched rows, and rows
synced before the reason was stored, stay synced and are not listed here. A read that fails is said, never an empty list:
a pack without `mine_issues`, and a database not yet migrated to the `reason` column, each name their remedy.

Issue intake (sd:4840) is Today's second list: each repo with `github_issues` on, its open issues someone else opened that
no sd item carries yet, from `sd_db.repos.intake_issues` (pack sd:4880); a repo whose `issues_scope` is mine lists
only those that reach the operator (pack sd:7672). Each row names the ref an item files it under,
`github:<owner>/<repo>#N`, which Today's File as item posts and `sd task add --ref` takes.

Details (sd:5877): each row of both lists also carries the `shadow` columns its Details show (`FACTS`, each None when
the sync did not store it) and the item filed under its ref, read from what `sd shadow sync` stored; no tracker is called.
A read of them that fails is the row's `unread`, so the page says the facts are unknown, never empty.

sd:5899: Your issues is one Jira and GitHub list. `with_github` adds the GitHub issues the Pull requests view used to
list: each issue `today_github.document` holds open, or closed in its window, that is the operator's (`mine`) and no
issue source already lists. A closed row carries its `state`; the page shows it under its closed filter only.

sd:6175: Hide is the workflow database's `view` state, the store Contributions' and Designs' Hide write, keyed
`issue:<row key>` (`view_key`); `with_views` marks each row of both lists `hidden`, and a store that does not read hides
nothing and says why. Refresh from GitHub starts `SYNC_JOB` through the route Run now posts; `sync_job` is its launchd state.

pack sd:7708: local categories for Jira issues, kept in the same view store and written to no tracker. The operator's
category names, in order, are the `tags` of one view row, `CATEGORIES_KEY`; a Jira row's category is the first of its own
view row's tags that names a listed category. `with_views` gives each Jira row of Your issues its `category` (None when it
has none) and the document its `categories`. `view` sets or clears a row's category; `categories` saves the list against
the one the page read, and renames a category with every issue under it in one transaction. Removing a name leaves its
issues' tags as they were, so they read as uncategorized, and Undo, which lists the name again, puts them back.
"""

from __future__ import annotations

import sqlite3

from sd_db import progress, repos, writes
from sd_db.errors import SdDbError

TRACKER = {"github": "GitHub", "jira": "Jira"}
#: Each Details fact (sd:5877) to the `shadow` column that holds it. The sync stores no labels, priority or description.
FACTS = {"slug": "repo", "state": "state", "status": "status", "assignee": "assignee", "reporter": "author",
         "created_at": "created_at", "updated_at": "updated_at"}
#: The source of an item filed under a tracker ref (`review.REF_SOURCE`).
REF_SOURCE = "task-ref"
#: The key prefix of an issue row's view state (sd:6175). A Contributions key starts `contribution:`, a Designs key
#: `designs/` and a Documents key is `<root key>/<file>`, so none meets `issue:`.
VIEW_ROOT = "issue"
#: The job Refresh from GitHub starts (sd:6175): the nightly `sd shadow sync`, through `/api/jobs/<name>/retry`.
SYNC_JOB = "shadow-sync-nightly"
#: The view row whose `tags` are the issue categories (pack sd:7708). A row key starts with its tracker and a colon, so no
#: issue's key (`view_key`) is this one.
CATEGORIES_KEY = f"{VIEW_ROOT}:categories"
#: The group of Jira rows with no listed category; a category may not take its name.
UNCATEGORIZED = "Uncategorized"


def fallback(entry: dict, row: dict) -> str:
    """A row's key when no ref is known: its tracker, repository path and reference, never the stored address."""
    return f"{row['tracker']}:{entry['repo_path']}{entry['ref']}"


def _details(connection: sqlite3.Connection, pairs: list[tuple[dict, dict]]) -> None:
    """Add to each listed entry its stored facts and the item filed under its ref, read by its pack row's tracker and
    url through `progress.tracker_items`, as both lists hold open rows only; a read that fails leaves every fact None
    and `unread` naming why."""
    try:
        stored_rows = {(tracker, found["url"]): found for tracker in {row["tracker"] for _, row in pairs}
                       for found in progress.tracker_items(connection, tracker=tracker)}
        for entry, row in pairs:
            stored = stored_rows.get((row["tracker"], row["url"]), {})
            entry.update({name: stored.get(column) for name, column in FACTS.items()}, unread="")
            slug = entry["slug"] or row.get("repo")
            ref = (f"jira:{entry['ref']}" if row["tracker"] == "jira" else
                   f"github:{slug}#{row['number']}" if slug and row["number"] is not None else None)
            held = None
            for key in dict.fromkeys((ref, ref.lower())) if ref else ():
                held = held or writes.item_by_external(connection, REF_SOURCE, key)
            entry["item"] = held["id"] if held is not None else None
            entry.setdefault("key", ref or fallback(entry, row))
    except (SdDbError, sqlite3.Error) as failure:
        for entry, row in pairs:
            entry.update({name: None for name in FACTS}, item=None, unread=str(failure) or "the stored issue was not read")
            entry.setdefault("key", fallback(entry, row))


def document(connection: sqlite3.Connection) -> dict:
    """`issues`, one object per listed issue, and `issues_error`, the reason none could be read or ""."""
    from .screens import _repo_labels

    read = getattr(repos, "mine_issues", None)
    if read is None:
        return {"issues": [], "issues_error": "this sd_db has no repos.mine_issues; update the command pack"}
    try:
        found = read(connection)
    except sqlite3.OperationalError as failure:
        reason = str(failure) or "the issues could not be read"
        if "no such column: reason" in reason:
            reason += "; run sd-db migrate"
        return {"issues": [], "issues_error": reason}
    except (SdDbError, sqlite3.Error) as failure:
        return {"issues": [], "issues_error": str(failure) or "the issues could not be read"}
    label = _repo_labels(found)
    issues, pairs = [], []
    for path, rows in found.items():
        for row in rows:
            url = row["url"] or ""
            issues.append({
                "repo": label(path), "repo_path": path, "tracker": TRACKER.get(row["tracker"], row["tracker"]),
                "ref": f"#{row['number']}" if row["number"] is not None else url.rstrip("/").rsplit("/", 1)[-1],
                "title": row["title"] or "", "reason": row["reason"], "last_seen": row["last_seen"],
                # Only a web address is a link; the page draws any other as text.
                "url": url if url.startswith("https://") else None,
            })
            pairs.append((issues[-1], row))
    _details(connection, pairs)
    return {"issues": issues, "issues_error": ""}


def with_github(document: dict, github: dict) -> dict:
    """`document` with the operator's GitHub issues from `github` (`today_github.document`) that it does not list, by
    ref; `github_error` names a GitHub read that failed, so the list never looks complete when it is not."""
    if github.get("error"):
        return {**document, "github_error": github["error"]}
    listed = {str(row.get("key", "")).lower() for row in document["issues"]}
    extra = []
    for entry in (*github["issues"], *(row for row in github["settled"] if row["kind"] == "issue")):
        key = f"github:{entry['ref']}"
        if not entry.get("mine") or key.lower() in listed:
            continue
        listed.add(key.lower())
        extra.append({"repo": entry["repo"], "repo_path": None, "tracker": "GitHub", "ref": f"#{entry['number']}", "key": key,
                      "title": entry["title"], "reason": entry["why"], "last_seen": None, "url": entry["url"],
                      "slug": entry["repo"], "state": entry["state"], "status": None, "assignee": entry.get("assignee"),
                      "reporter": entry.get("author"), "created_at": entry.get("created_at"),
                      "updated_at": entry.get("updated_at"), "item": entry["item"], "unread": ""})
    return {**document, "issues": [*document["issues"], *extra], "github_error": ""}


def intake(connection: sqlite3.Connection) -> dict:
    """`intake`, one object per open third-party issue no item carries, and `intake_error`, why none could be read or ""."""
    from .screens import _repo_labels

    read = getattr(repos, "intake_issues", None)
    if read is None:
        return {"intake": [], "intake_error": "this sd_db has no repos.intake_issues; update the command pack"}
    try:
        found = read(connection)
    except sqlite3.OperationalError as failure:
        reason = str(failure) or "the issue intake could not be read"
        return {"intake": [], "intake_error": reason}
    except (SdDbError, sqlite3.Error) as failure:
        return {"intake": [], "intake_error": str(failure) or "the issue intake could not be read"}
    label = _repo_labels(found)
    rows, pairs = [], []
    for path, found_rows in found.items():
        for row in found_rows:
            url = row["url"] or ""
            rows.append({
                "repo": label(path), "repo_path": path, "ref": f"#{row['number']}",
                "key": f"github:{row['repo']}#{row['number']}", "title": row["title"] or "",
                "author": row["author"] or "", "last_seen": row["last_seen"],
                "url": url if url.startswith("https://") else None,
            })
            pairs.append((rows[-1], row))
    _details(connection, pairs)
    return {"intake": rows, "intake_error": ""}


def view_key(key: str) -> str:
    """A row's view-state key; lower case, as `_details` matches a ref, so a slug GitHub spells another way keeps it."""
    return f"{VIEW_ROOT}:{key.lower()}"


def with_views(document: dict, connection) -> dict:
    """`document` with each Your issues and Intake row's `hidden`, and `store` saying whether the view state was read.

    A read that fails hides nothing: every row shows, and `store.reason` says why Hide is off. Each Jira row of Your
    issues also carries its `category` and the document the `categories` (pack sd:7708); a failed read lists none.
    """
    from .documents_screen import views

    kept, unread = views(connection)
    names = listed(kept)
    for row in (*document.get("issues", ()), *document.get("intake", ())):
        state = kept.get(view_key(row["key"]), {})
        row["hidden"] = bool(state.get("hidden"))
        if row.get("tracker") == "Jira":
            row["category"] = next((tag for tag in state.get("tags", ()) if tag in names), None)
    return {**document, "categories": names, "store": {"available": not unread, "reason": unread}}


def listed(kept: dict) -> list[str]:
    """The issue categories in the operator's order (pack sd:7708), from the view rows `writes.views` read."""
    return list(kept.get(CATEGORIES_KEY, {}).get("tags", ()))


def sync_job(connection: sqlite3.Connection, backend) -> dict:
    """Refresh from GitHub's job as the jobs inventory reads it (`hoa_screen.JOB_KEYS`): the revision the retry route checks and the
    retry capability. A job that is not installed says the line that installs it; a read that fails says so, never off."""
    from sd_db import operations, workflow

    from .hoa_screen import JOB_KEYS

    try:
        job = operations.job_state(connection, SYNC_JOB, backend=backend)
    except workflow.WorkflowError as error:
        return {"name": SYNC_JOB, "error": f"{SYNC_JOB} is not an installed job ({error}); "
                                           f"local-cron-jobs/cron-jobs.sh install {SYNC_JOB} installs it"}
    except (OSError, SdDbError, sqlite3.Error) as failure:
        return {"name": SYNC_JOB, "error": f"{SYNC_JOB} was not read: {failure}"}
    return {key: job.get(key) for key in JOB_KEYS}


def view(payload: dict):
    """`POST /api/github/issues/view` (sd:6175): `{"key", "hidden"}`, as `designs.request` and
    `contribution_screen.view` take, or `{"key", "category"}` (pack sd:7708), a listed category's name or None to clear
    it; the write as `action_route` returns one. The write reads both lists again, so a key they no longer list is
    refused as stale and nothing is written; so is a category the list no longer holds."""
    from datetime import datetime, timezone

    from sd_db import workflow
    from sd_db.database import transaction

    from . import today_github

    key, hidden, category = payload.get("key"), payload.get("hidden"), payload.get("category", "")
    if set(payload) == {"key", "category"}:
        if not isinstance(key, str) or not (category is None or isinstance(category, str) and category):
            raise ValueError("Send the issue's key and a category's name, or null to clear it.")
    elif set(payload) != {"key", "hidden"} or not isinstance(key, str) or not isinstance(hidden, bool):
        raise ValueError("Send the issue's key and hidden, true or false.")
    if not hasattr(writes, "set_view"):
        raise ValueError("The command pack has no view store yet (sd:3430): pull it and restart the dashboard.")

    def write(connection):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        listed_rows = with_github(document(connection), today_github.document(connection, now=now))["issues"]
        if "hidden" in payload:
            if key.lower() not in {str(row["key"]).lower() for row in (*listed_rows, *intake(connection)["intake"])}:
                raise workflow.StaleItem(f"No issue {key} is listed. Nothing was hidden or shown. Read GitHub again.")
            return {"key": key, **writes.set_view(connection, view_key(key), hidden=hidden)}
        row = next((row for row in listed_rows if str(row["key"]).lower() == key.lower()), None)
        if row is None:
            raise workflow.StaleItem(f"No issue {key} is listed. No category was set. Read GitHub again.")
        if row["tracker"] != "Jira":
            raise ValueError(f"{key} is a {row['tracker']} issue; only a Jira issue takes a category.")
        with transaction(connection):
            if category is not None and category not in listed(writes.views(connection)):
                raise workflow.StaleItem(f"No category {category} is listed. No category was set. Read GitHub again.")
            state = writes.set_view(connection, view_key(key), tags=[category] if category else [])
        return {"key": key, "category": category, **state}

    return write


def category_names(names) -> list[str]:
    """`names` trimmed, as the view store keeps tags; raises `ValueError` naming the first rule one breaks."""
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("Send the categories as a list of names.")
    kept = [name.strip() for name in names]
    folded = [name.casefold() for name in kept]
    if any(not name or len(name) > writes.VIEW_TAG_LENGTH for name in kept):
        raise ValueError(f"A category's name is 1 to {writes.VIEW_TAG_LENGTH} characters.")
    if len(kept) > writes.VIEW_TAGS:
        raise ValueError(f"At most {writes.VIEW_TAGS} categories: remove one first.")
    if len(set(folded)) != len(folded):
        raise ValueError("Each category's name is its own, in any case.")
    if UNCATEGORIZED.casefold() in folded:
        raise ValueError(f"{UNCATEGORIZED} is the group of issues with no category; name the category another way.")
    return kept


def categories(payload: dict):
    """`POST /api/github/issues/categories` (pack sd:7708): `{"categories", "before"}` saves the list, or
    `{"rename", "to", "before"}` renames one category and every issue under it, in one transaction. `before` is the list
    the page read; a list that changed since is refused as stale and nothing is written. Answers the list written."""
    from sd_db import workflow
    from sd_db.database import transaction

    if set(payload) == {"categories", "before"}:
        names, rename = category_names(payload["categories"]), None
    elif set(payload) == {"rename", "to", "before"} and isinstance(payload["rename"], str):
        names, rename = None, (payload["rename"], category_names([payload["to"]])[0])
    else:
        raise ValueError("Send categories and before, or rename, to and before.")
    before = payload["before"]
    if not isinstance(before, list):
        raise ValueError("Send before, the categories the page read.")
    if not hasattr(writes, "set_view"):
        raise ValueError("The command pack has no view store yet (sd:3430): pull it and restart the dashboard.")

    def write(connection):
        with transaction(connection):
            kept = writes.views(connection)
            held = listed(kept)
            if held != before:
                raise workflow.StaleItem("The categories changed since the page read them. Nothing was saved. Read GitHub again.")
            moved = 0
            new = names
            if rename is not None:
                old, to = rename
                if old not in held:
                    raise workflow.StaleItem(f"No category {old} is listed. Nothing was renamed. Read GitHub again.")
                new = category_names([to if name == old else name for name in held])
                for key, state in kept.items():
                    if key.startswith(f"{VIEW_ROOT}:") and key != CATEGORIES_KEY and old in state["tags"]:
                        writes.set_view(connection, key, tags=[to if tag == old else tag for tag in state["tags"]])
                        moved += 1
            writes.set_view(connection, CATEGORIES_KEY, tags=new)
        return {"categories": new, "moved": moved}

    return write
