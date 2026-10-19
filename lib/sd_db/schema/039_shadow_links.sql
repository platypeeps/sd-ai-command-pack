-- `shadow.branch` and `shadow.linked_issues`: a pull request's head branch
-- and the issues it closes (sd:5315, for the system's sd:5308), so the
-- Contributions page can show what each pull request is for.
--
-- The GitHub collector reads both from the search page it already fetches
-- (`headRefName`, `closingIssuesReferences(first: 10)`); neither costs a
-- request. `linked_issues` is a JSON array of issue urls, at most ten, `[]`
-- when the pull request closes none. NULL is unknown: an issue row, a row
-- synced before 39, or a page whose field did not read; a collect that cannot
-- read either keeps the stored value. Jira keys are not stored: a reader
-- finds them in the title or the branch (`shadow_sync.jira_links`).
--
-- `ADD COLUMN` for 034's reason: SQLite adds a nullable column in place,
-- touches no other table and moves no row. Every existing row reads NULL.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops every branch and link; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE shadow DROP COLUMN branch;
--   ALTER TABLE shadow DROP COLUMN linked_issues;
--   PRAGMA user_version = 38;
--   COMMIT;

ALTER TABLE shadow ADD COLUMN branch TEXT;
ALTER TABLE shadow ADD COLUMN linked_issues TEXT
    CHECK (linked_issues IS NULL OR (json_valid(linked_issues) AND json_type(linked_issues) = 'array'));
