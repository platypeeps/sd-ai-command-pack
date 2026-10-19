-- `shadow.merged_at` and `shadow.closed_at`: when the tracker merged or closed
-- a row (sd:5303), as UTC ISO text, for the system dashboard's Contributions
-- page, which shows when each row settled.
--
-- The GitHub collector reads both from the search page it already fetches
-- (`closedAt`, and `mergedAt` on a pull request), and the direct read that
-- closes an issue a sweep missed reads `closed_at`; neither costs a request.
-- NULL is unknown or not settled: a row synced before 38, a row only an
-- importer or the Jira collector wrote, or an open row. A reopened row loses
-- its close date; a date that does not parse keeps the stored one.
-- `contributions.projection` reads both for each GitHub row by its url.
--
-- `ADD COLUMN` for 034's reason: SQLite adds a nullable column in place,
-- touches no other table and moves no row. Every existing row reads NULL,
-- until a collect sees it again: the nightly window for recent rows, and
-- `sd shadow sync --since <date>` for older ones.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops every date; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE shadow DROP COLUMN merged_at;
--   ALTER TABLE shadow DROP COLUMN closed_at;
--   PRAGMA user_version = 37;
--   COMMIT;

ALTER TABLE shadow ADD COLUMN merged_at TEXT;
ALTER TABLE shadow ADD COLUMN closed_at TEXT;
