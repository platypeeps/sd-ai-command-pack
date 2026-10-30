-- Three `shadow` columns (pack sd:6711), so the Pull requests view can keep
-- the open pull requests that are ready to merge:
--
-- `review_decision` is GitHub's `reviewDecision`, lower-cased: `approved`,
-- `changes_requested`, `review_required`, or `none` when GitHub names none.
-- `checks` is the head commit's `statusCheckRollup` state, lower-cased:
-- `success`, `failure`, `error`, `pending`, `expected`, or `none` when the
-- head has no check. `mergeable` is `mergeable`, `conflicting` or `unknown`.
--
-- NULL is not read in every column: an issue, a row synced before 44, or a
-- field that did not read. `upsert_shadow` keeps the stored value for NULL,
-- and the view says not read for it, never ready.
--
-- `ADD COLUMN`, as 040: SQLite adds a nullable column in place, touches no
-- other table and moves no row. An open pull request reads NULL until the
-- next sync sees it again.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops the three stored values; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE shadow DROP COLUMN mergeable;
--   ALTER TABLE shadow DROP COLUMN checks;
--   ALTER TABLE shadow DROP COLUMN review_decision;
--   PRAGMA user_version = 43;
--   COMMIT;

ALTER TABLE shadow ADD COLUMN review_decision TEXT;
ALTER TABLE shadow ADD COLUMN checks TEXT;
ALTER TABLE shadow ADD COLUMN mergeable TEXT;
