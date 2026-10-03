"""`sd suggest` — a framework suggestion is a row first and an sd item only on request.

The skill this backs once told a model to file to a tracker the moment friction
cost a turn, while its own tooling section pointed at a standalone command that
was never built. A skill telling a model to call an API is the
shape that files duplicates: nothing local records that a suggestion was made,
so the only memory of it is the tracker, and reaching the tracker is exactly
the step that fails on a fork, in `guest` mode, or with no credential.

So the row comes first. `sd suggest add` writes a `proposal` note against a
work item in every mode and reaches nothing outside this machine. `sd suggest
publish` is the separate, explicit act that turns one into an sd item of its
own, and it refuses without a `--belongs-to`, because the checkout a
suggestion belongs to is a decision and never a default.

It files no GitHub issue (sd:2002). Since 2026-09-28 every issue is filed in
the sd database, and this repository has GitHub issues disabled, so the
`gh api repos/<to>/issues` path `publish` once took pointed at a tracker nobody
reads. `--to owner/repo` is kept only to refuse by name.

Two things this deliberately does not do:

  * **It is not a `bin/sd-suggest` executable.** Criterion 28 says publishing
    must be no palette entry, and a verb under `sd` is not an installed
    entrypoint while a standalone binary is. The group is the enforcement.
  * **It does not resolve the item for you.** `--item` names a directory under
    `docs/work/`, the same refusal `bin/sd-note` makes and for the same reason:
    a suggestion filed against the wrong item is worse than one not filed.

`sd_db.add_note(kind='proposal')` is the write, and it is not new -- the
vocabulary is the `CHECK` on `note.kind` in the schema, which already carries
`proposal` beside `followup`. The library frame, the connection and the item
resolver are `bin/sd_handoff_rows.py`'s, built for criterion 29 and reused
whole rather than restated here. `publish` writes its item through
`sd_db.workflow.capture_task`, the one `sd task add` uses, and reads its
checkout the way `sd task edit --belongs-to` does.
"""

from __future__ import annotations

import pathlib

#: The `note.kind` this verb writes. In the schema's `CHECK` already.
PROPOSAL = "proposal"

#: What `publish` refuses to guess.
NO_DESTINATION = (
    "`sd suggest publish` needs `--belongs-to PATH`, a registered checkout. The "
    "checkout a suggestion belongs to is a decision, and a default here files "
    "into whichever repository happened to be current when nobody was looking."
)

#: What `--to` now answers. It named a GitHub repository to file an issue in.
RETIRED_TO = (
    "`--to owner/repo` is retired: `sd suggest publish` files an sd item, never a "
    "GitHub issue (sd:2002). Name the checkout with `--belongs-to PATH`."
)


def _rows():
    """`bin/sd_handoff_rows.py`, which owns the library frame and the resolver."""
    import sd_handoff_rows  # noqa: PLC0415 - deferred, as the module docstring says

    return sd_handoff_rows


def suggest_add(args) -> int:
    """Write one `proposal` row against a work item. Reaches nothing outside."""
    import sd_lib  # noqa: PLC0415 - same

    rows = _rows()
    root = sd_lib.repo_root(pathlib.Path.cwd())
    if root is None:
        raise rows.RowsRefusal("not inside a git repository")
    item_dir = pathlib.Path(root) / sd_lib.WORK_DIR / args.item
    if not item_dir.is_dir():
        raise rows.RowsRefusal(f"no work item at {item_dir}")

    # The mode is recorded on the row, not consulted for permission. Criterion
    # 28 says the row is written in every mode; what the mode changes is only
    # what `publish` may later do with it, and that is `publish`'s question.
    where = sd_lib.mode(pathlib.Path(root))
    sd_db = rows.library()
    connection = rows.connect(sd_db, write=True)
    try:
        item = rows.item_for(connection, sd_db, root, item_dir)
        if item is None:
            raise rows.RowsRefusal(
                f"the database holds no {sd_lib.ITEM_ROW_SOURCE} row for "
                f"{item_dir.name}. Import the work item before recording a proposal; "
                "`sd-status` only reports."
            )
        note = sd_db.add_note(connection, item["id"], PROPOSAL, f"[{where}] {args.body}")
    finally:
        connection.close()
    print(f"proposal [{note}] on {item_dir.name}, in {where} mode; filed nowhere")
    print(f"`sd suggest publish --belongs-to PATH --note {note}` files it")
    return 0


def suggest_publish(args) -> int:
    """File one row as an sd item in the checkout `--belongs-to` names, after a dedup read."""
    import getpass  # noqa: PLC0415 - same

    import sd_lib  # noqa: PLC0415 - same
    import sd_work  # noqa: PLC0415 - same

    rows = _rows()
    if getattr(args, "to", ""):
        raise rows.RowsRefusal(RETIRED_TO)
    if not getattr(args, "belongs_to", ""):
        raise rows.RowsRefusal(NO_DESTINATION)
    sd_db, workflow = sd_work._library()
    connection = rows.connect(sd_db, write=True)
    try:
        row = connection.execute(
            "SELECT body FROM note WHERE id = ? AND kind = ?", (args.note, PROPOSAL)
        ).fetchone()
        if row is None:
            raise rows.RowsRefusal(
                f"no {PROPOSAL} note with id {args.note}; `sd suggest add` prints it")
        title = row["body"].splitlines()[0][:120]

        # The row's own spelling of the checkout, as `sd task add` stores it
        # (sd:1439): `capture_task` refuses a repository the `repo` table does
        # not carry, and the dedup read below compares against that spelling.
        key = sd_work._belongs_to(args.belongs_to)
        registered = sd_lib.repo_row(connection, key)
        if registered is None:
            raise rows.RowsRefusal(f"--belongs-to: {key} is not a registered repository")
        repo = str(registered["path"])

        # The dedup read the skill requires at `skills/sd-suggest/SKILL.md` --
        # an open item in that checkout with the same title is the suggestion
        # already filed, so this files nothing and says which item holds it.
        # `same_repo` rather than an equality probe, so every stored form of the
        # checkout matches (sd:1439, `tests/test_home_relative.py`).
        for item in connection.execute(
            "SELECT id, title, repo FROM item WHERE status != 'done'"
        ):
            if (sd_lib.same_repo(item["repo"], repo)
                    and item["title"].strip().lower() == title.strip().lower()):
                print(f"already open as sd:{item['id']}; filed nothing")
                return 0

        state = workflow.capture_task(
            connection, title=title,
            body=f"{row['body']}\n\nFrom proposal note {args.note}.",
            repo=repo, who=getpass.getuser(),
        )
    except sd_db.SdDbError as error:
        raise rows.RowsRefusal(str(error)) from error
    finally:
        connection.close()
    print(f"filed sd:{state['item']['id']} in {repo}; the proposal note stays")
    return 0
