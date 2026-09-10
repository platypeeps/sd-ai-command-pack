# Work

Each directory here is one unit of work: `<YYYY-MM-DD>-<slug>/` holding
`prd.md`, and `design.md` / `implement.md` only when requested.

`.status-source` in this work root selects the status source, including when
`--work-dir` selects a root other than `docs/work`. With `row`, progress
lives in the database; active PRDs carry no `status:` field. With `file` or no
marker, the legacy reader uses `status:` in PRD frontmatter: `planning`, `ready`,
`in_progress`, or `done`. An unrecognized marker is an error to resolve, not a
reason to fall back to frontmatter. An item that is `ready` or `in_progress`
states acceptance criteria and carries no open `BLOCKING` line; an
`in_progress` item records the `branch:` it lives on.

`sd sweep` reports idle items without moving them or changing their status.
Finishing work leaves its directory in place. A slice merge records progress;
only a verified delivery closes the item. No status-only commit or automatic
archive is needed.
