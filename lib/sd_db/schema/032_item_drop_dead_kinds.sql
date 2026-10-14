-- `proposal` and `dep` leave `item.kind` (sd:3510). Neither has a producer
-- and the hub never held a row of either: `proposal` was reserved, and the
-- `proposal` that lives is the note kind; `dep` named "something a `work`
-- item waits on", and nothing ever wrote one. `skill-review` stays: the
-- skills catalogue files it (`skills_catalog.py`).
--
-- The CHECK text is edited in place, as 009 widened it: narrowing a CHECK
-- moves no row, and the four foreign keys onto `item(id)` rule out a rebuild
-- (009 says why). `workflow.schema_kinds` reads the list from this text, so
-- the library follows it with no constant to change.
--
-- Two guards hold the edit to the shapes this file knows. The first, before
-- `writable_schema` is on, refuses while a row still holds either kind, which
-- the narrower CHECK would leave failing `PRAGMA integrity_check`, and accepts
-- `item` only with the list 009 left or the one this file leaves: a restore
-- replays migrations onto a snapshot that may already carry the second
-- (`backup.py`, `_upgrade_restore_candidate`), and there the `replace` finds
-- nothing and changes nothing. The second, after it is reset, accepts only
-- the table's three CHECKs, each as written: the new kind list, the status
-- list and the gate generation's; and neither word left anywhere. A
-- refusal fails the guard's own CHECK, in a temporary table so it does not
-- hang on `item`'s constraints; that aborts the transaction and leaves the
-- file at 31.
--
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped, after `bin/sd-db backup`. It widens the list back; no row changes.
--
--   BEGIN;
--   PRAGMA writable_schema = ON;
--   UPDATE sqlite_master SET sql = replace(sql,
--       '''report'',' || char(10) || '                                    ''skill-review'',' || char(10),
--       '''report'',' || char(10) || '                                    ''proposal'', ''skill-review'', ''dep'',' || char(10))
--    WHERE type = 'table' AND name = 'item';
--   PRAGMA writable_schema = RESET;
--   CREATE TABLE migration_032_cookie (x INTEGER);
--   DROP TABLE migration_032_cookie;
--   PRAGMA user_version = 31;
--   COMMIT;

CREATE TEMP TABLE migration_032_guard (
    refused TEXT CONSTRAINT migration_032_refuses_a_dead_kind_row_or_an_unknown_item_shape CHECK (refused IS NULL)
);
INSERT INTO migration_032_guard
SELECT 'item'
 WHERE EXISTS (SELECT 1 FROM item WHERE kind IN ('proposal', 'dep'))
    OR NOT EXISTS (
     SELECT 1 FROM sqlite_master
      WHERE type = 'table' AND name = 'item'
        AND (instr(sql, '''report'',' || char(10) || '                                    ''proposal'', ''skill-review'', ''dep'',' || char(10))
          OR instr(sql, '''report'',' || char(10) || '                                    ''skill-review'',' || char(10))));

PRAGMA writable_schema = ON;

UPDATE sqlite_master
   SET sql = replace(
       sql,
       '''report'',' || char(10) || '                                    ''proposal'', ''skill-review'', ''dep'',' || char(10),
       '''report'',' || char(10) || '                                    ''skill-review'',' || char(10))
 WHERE type = 'table' AND name = 'item';

PRAGMA writable_schema = RESET;

INSERT INTO migration_032_guard
SELECT 'item'
 WHERE NOT EXISTS (
     SELECT 1 FROM sqlite_master
      WHERE type = 'table' AND name = 'item'
        AND instr(sql, 'CHECK (kind IN (''work'', ''idea'', ''task'', ''report'',' || char(10) ||
                       '                                    ''skill-review'',' || char(10) ||
                       '                                    ''personal'', ''followup'',' || char(10) ||
                       '                                    ''work-idea'', ''personal-idea'')),')
        AND length(sql) - length(replace(upper(sql), 'CHECK', '')) = 3 * length('CHECK')
        AND instr(sql, 'CHECK (status IN (''planning'', ''ready'', ''in_progress'',' || char(10) ||
                       '                                      ''ready_to_send'', ''blocked'', ''done''))')
        AND instr(sql, 'CHECK (gate_generation >= 0)')
        AND instr(sql, '''proposal''') = 0 AND instr(sql, '''dep''') = 0);
DROP TABLE migration_032_guard;

-- `writable_schema` leaves the schema cookie untouched, so a connection that is
-- already open would keep the old CHECK; this pair bumps it, as 009's does.
CREATE TABLE migration_032_cookie (x INTEGER);
DROP TABLE migration_032_cookie;
