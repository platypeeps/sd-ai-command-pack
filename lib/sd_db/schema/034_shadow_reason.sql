-- `shadow.reason`: why a synced row is the operator's (sd:4636, operator
-- decision of 2026-10-14 on sd:4628). Today and Tasks show a repository's
-- issues that are `assigned` to or `filed` by the operator and hide the rest.
--
-- `assigned` and `filed` are the operator's own; `watched` is every other
-- match: a GitHub mention or review request, a Jira watch, a custom JQL's hit.
-- One value per row, the strongest that holds, in that order. NULL is
-- unknown: a row synced before 34, a row only an importer wrote, or a row a
-- collect saw while a stronger bucket's search failed. Unknown is not
-- watched, and the next complete collect of the row replaces it.
--
-- This reverses 001's note that `why` has no column here. `why` is still a
-- property of one collect; `reason` is what that collect concludes about the
-- row, and `shadow_sync.store` writes it with the other fields it refreshes.
--
-- `ADD COLUMN` for 016's and 024's reason: SQLite adds a nullable column in
-- place, touches no other table and moves no row. Every existing row reads NULL.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops every reason; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE shadow DROP COLUMN reason;
--   PRAGMA user_version = 33;
--   COMMIT;

ALTER TABLE shadow ADD COLUMN reason TEXT
    CHECK (reason IS NULL OR reason IN ('assigned', 'filed', 'watched'));
