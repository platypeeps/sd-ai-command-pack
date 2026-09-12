"""`sd suggest` — a framework suggestion is a row first and an issue only on request.

The skill this backs once told a model to file to a tracker the moment friction
cost a turn, while its own tooling section pointed at a standalone command that
was never built. A skill telling a model to call an API is the
shape that files duplicates: nothing local records that a suggestion was made,
so the only memory of it is the tracker, and reaching the tracker is exactly
the step that fails on a fork, in `guest` mode, or with no credential.

So the row comes first. `sd suggest add` writes a `proposal` note against a
work item in every mode and reaches nothing outside this machine. `sd suggest
publish` is the separate, explicit act that files one, and it refuses without a
`--to`, because the destination of a suggestion is a decision and never a
default.

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
whole rather than restated here.
"""

from __future__ import annotations

import pathlib

#: The `note.kind` this verb writes. In the schema's `CHECK` already.
PROPOSAL = "proposal"

#: What `publish` refuses to guess.
NO_DESTINATION = (
    "`sd suggest publish` needs `--to owner/repo`. The destination of a "
    "suggestion is a decision, and a default here files into whichever "
    "tracker happened to be configured when nobody was looking."
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
    print(f"`sd suggest publish --to owner/repo --note {note}` files it")
    return 0


def suggest_publish(args) -> int:
    """File one row as an issue at the destination `--to` names, after a dedup read."""
    import sd_lib  # noqa: PLC0415 - same

    rows = _rows()
    if not args.to:
        raise rows.RowsRefusal(NO_DESTINATION)
    root = sd_lib.repo_root(pathlib.Path.cwd())
    if root is None:
        raise rows.RowsRefusal("not inside a git repository")

    sd_db = rows.library()
    connection = rows.connect(sd_db)
    try:
        row = connection.execute(
            "SELECT body FROM note WHERE id = ? AND kind = ?", (args.note, PROPOSAL)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise rows.RowsRefusal(f"no {PROPOSAL} note with id {args.note}; `sd suggest add` prints it")
    title = row["body"].splitlines()[0][:120]

    # The dedup read the skill already requires at `skills/sd-suggest/SKILL.md:36`
    # -- "not 'I searched my memory' -- the list API call, actually made". It is
    # a read, so a failure here refuses rather than falling through to a file:
    # filing blind is the outcome the read exists to prevent.
    pr_state = sd_lib.sibling("sd_pr_state", "sd-pr-state")
    open_issues, error = pr_state.gh_json(
        ["api", f"repos/{args.to}/issues?state=open&per_page=100"], pathlib.Path(root)
    )
    if error:
        raise rows.RowsRefusal(f"cannot read {args.to}'s open issues, so filing blind: {error}")
    for issue in open_issues or []:
        if issue.get("title", "").strip().lower() == title.strip().lower():
            print(f"already open at {issue.get('html_url')}; filed nothing")
            return 0

    payload, error = pr_state.gh_json(
        ["api", "--method", "POST", f"repos/{args.to}/issues",
         "-f", f"title={title}", "-f", f"body={row['body']}"],
        pathlib.Path(root),
    )
    if error:
        raise rows.RowsRefusal(f"gh would not file the issue at {args.to}: {error}")
    print((payload or {}).get("html_url") or f"filed at {args.to}")
    return 0
