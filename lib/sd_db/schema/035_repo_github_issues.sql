-- `repo.github_issues`: 1 when the repository takes GitHub issues from people
-- outside the workflow, 0 otherwise (sd:4827, system sd:4810).
--
-- Agents follow one rule: work lives in sd items, not GitHub issues. A
-- repository with this on answers its reporters: an agent maps each open issue
-- to one sd item, comments for the reporter and closes the issue with
-- `gh issue close` when the item is done. Filing an issue stays denied.
-- `sd-db repo github-issues PATH on|off` sets it, `repo list` shows it, and
-- `repos.github_issues` reads it.
--
-- Every row starts at 0, off, so the rule holds for every repository until the
-- operator turns one on. `ADD COLUMN` for 015's reason: SQLite adds a column
-- with a constant default and a CHECK in place, touches no other table and
-- moves no row.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops every setting; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE repo DROP COLUMN github_issues;
--   PRAGMA user_version = 34;
--   COMMIT;

ALTER TABLE repo ADD COLUMN github_issues INTEGER NOT NULL DEFAULT 0
    CHECK (github_issues IN (0, 1));
