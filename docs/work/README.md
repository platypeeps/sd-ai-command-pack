# Work items

Create one directory per item: `<YYYY-MM-DD>-<slug>/prd.md`.
Add `design.md` and `implement.md` when needed.

This checkout reads status from the database, as `docs/work/.status-source` specifies.
Do not add `status:` to active PRD frontmatter.
Keep archived frontmatter as historical evidence.

For an existing task or followup, add `item: sd:<id>` to the PRD frontmatter.
Do not register another work row for that task.
Resolve any existing duplicate path registration first; path bindings take precedence.

For new work, run `bin/sd work register docs/work/<item>/prd.md` from this checkout.
Registration creates the row in `planning`.

Reference the item with one `Work:` line in the pull request.
Move completed items to `archive/YYYY-MM/` when their archive conditions hold.
The [archive index](archive/README.md) links the removed historical snapshot.
Follow [the documentation conventions](../../CONTRIBUTING.md#documentation-and-decisions) when recording decisions and history.
