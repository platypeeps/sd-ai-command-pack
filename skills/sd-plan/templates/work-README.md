# Work

Each directory here is one work item: `<YYYY-MM-DD>-<slug>/design.md`.
Write it only when the shape needs agreement before the code.
The item's sd row holds status, progress and decisions.
Older items keep their `prd.md` and `implement.md`; write no new ones.

The file/row status rules stand until sd:3015.
`.status-source` in this work root selects the status source, including when
`--work-dir` selects a root other than `docs/work`. With `row`, progress
lives in the database; active PRDs carry no `status:` field. With `file` or no
marker, the legacy reader uses `status:` in PRD frontmatter: `planning`, `ready`,
`in_progress`, or `done`. An unrecognized marker is an error to resolve, not a
reason to fall back to frontmatter. An item that is `ready` or `in_progress`
states acceptance criteria and carries no open `BLOCKING` line; an
`in_progress` item records the `branch:` it lives on.
Finishing work leaves its directory in place.
