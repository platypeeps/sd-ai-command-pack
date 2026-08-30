# Work

Each directory here is one unit of work: `<YYYY-MM-DD>-<slug>/` holding
`prd.md`, and `design.md` / `implement.md` when the work warrants them.

`status:` in the PRD frontmatter is one of `planning`, `ready`, `in_progress`,
`done`. An item that is `ready` or `in_progress` states acceptance criteria and
carries no open `BLOCKING` line; an `in_progress` item records the `branch:` it
lives on.

Merged and long-idle items are swept to `archive/YYYY-MM/` by `sd-plan`. Nothing
here is generated, and nothing outside git holds the authoritative copy.
