-- Four `shadow` columns (pack sd:5496), so the dashboard lists what the
-- operator filed this year:
--
-- `created_at` is when the tracker created the row, as UTC ISO text (Jira
-- `created`, GitHub `createdAt`). `filed` is 1 when the operator filed the
-- row and 0 when not. It is kept apart from `reason`, which names only the
-- strongest of assigned and filed: a Jira ticket the operator filed and holds
-- reads `assigned` there, and filed here. `status` is Jira's status name
-- (`In Review`); `state` keeps open/closed, and GitHub rows store NULL, as
-- GitHub has no status beyond its state. `assignee` is Jira's assignee display
-- name, or GitHub's assignee logins joined by `, `; the empty string is
-- unassigned.
--
-- NULL is unknown in every column: a row synced before 40, a value that did not
-- read, or a GitHub row whose `author:@me` search did not complete. A collect
-- writes NULL for unknown, and `upsert_shadow` keeps the stored value for it.
--
-- `ADD COLUMN`, as 039: SQLite adds a nullable column in place, touches no
-- other table and moves no row. Every existing row reads NULL until a collect
-- sees it again: the nightly window for recent rows, and once for older ones,
-- `JIRA_JQL='reporter = currentUser() AND created >= startOfYear()' sd shadow
-- sync` and `sd shadow sync --since <January 1st>`.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops the four stored values; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE shadow DROP COLUMN assignee;
--   ALTER TABLE shadow DROP COLUMN status;
--   ALTER TABLE shadow DROP COLUMN filed;
--   ALTER TABLE shadow DROP COLUMN created_at;
--   PRAGMA user_version = 39;
--   COMMIT;

ALTER TABLE shadow ADD COLUMN created_at TEXT;
ALTER TABLE shadow ADD COLUMN filed INTEGER CHECK (filed IN (0, 1));
ALTER TABLE shadow ADD COLUMN status TEXT;
ALTER TABLE shadow ADD COLUMN assignee TEXT;
