-- `personal` and `skill-review` leave `item.kind` (sd:7004, design
-- docs/work/2026-11-01-retire-item-kinds/design.md). A `personal` row adds
-- nothing over a task; the catalogue now files a review as a `task` row
-- whose `fields.skill_review.action` is `review`. Every row of either kind
-- becomes a `task` row; nothing else on it moves, and no row is added, since
-- a restore refuses a replay that changes a table's row count (`backup.py`,
-- `_upgrade_restore_candidate`).
--
-- The CHECK text is edited in place, as 009 and 032 did: four foreign keys
-- onto `item(id)` rule out a rebuild (009 says why). `workflow.schema_kinds`
-- reads the list from this text.
--
-- Two guards, as in 032. The first, before `writable_schema` is on, accepts
-- `item` only with the list 032 left or the one this file leaves: a restore
-- replays onto either, and on the second the `UPDATE` and the `replace`
-- change nothing. The second, after it is reset, accepts only the table's
-- three CHECKs as written, with neither word left and no row of either kind.
-- A refusal fails the guard's own CHECK, in a temporary table so it does not
-- hang on `item`'s constraints; that aborts the transaction `migrate` wraps
-- the file in and leaves the file at 45 with every row as it was.
--
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped, after `bin/sd-db backup`. It widens the list back; a moved row
-- stays a `task`, since this file records no original kind.
--
--   BEGIN;
--   PRAGMA writable_schema = ON;
--   UPDATE sqlite_master SET sql = replace(sql,
--       '''report'',' || char(10) || '                                    ''followup'',' || char(10),
--       '''report'',' || char(10) || '                                    ''skill-review'',' || char(10) || '                                    ''personal'', ''followup'',' || char(10))
--    WHERE type = 'table' AND name = 'item';
--   PRAGMA writable_schema = RESET;
--   CREATE TABLE migration_046_cookie (x INTEGER);
--   DROP TABLE migration_046_cookie;
--   PRAGMA user_version = 45;
--   COMMIT;

CREATE TEMP TABLE migration_046_guard (
    refused TEXT CONSTRAINT migration_046_refuses_an_unknown_item_shape CHECK (refused IS NULL)
);
INSERT INTO migration_046_guard
SELECT 'item'
 WHERE NOT EXISTS (
     SELECT 1 FROM sqlite_master
      WHERE type = 'table' AND name = 'item'
        AND (instr(sql, 'CHECK (kind IN (''work'', ''idea'', ''task'', ''report'',' || char(10) ||
                        '                                    ''skill-review'',' || char(10) ||
                        '                                    ''personal'', ''followup'',' || char(10) ||
                        '                                    ''work-idea'', ''personal-idea'')),')
          OR instr(sql, 'CHECK (kind IN (''work'', ''idea'', ''task'', ''report'',' || char(10) ||
                        '                                    ''followup'',' || char(10) ||
                        '                                    ''work-idea'', ''personal-idea'')),')));

UPDATE item SET kind = 'task' WHERE kind IN ('personal', 'skill-review');

PRAGMA writable_schema = ON;

UPDATE sqlite_master
   SET sql = replace(
       sql,
       '''report'',' || char(10) || '                                    ''skill-review'',' || char(10) ||
       '                                    ''personal'', ''followup'',' || char(10),
       '''report'',' || char(10) || '                                    ''followup'',' || char(10))
 WHERE type = 'table' AND name = 'item';

PRAGMA writable_schema = RESET;

INSERT INTO migration_046_guard
SELECT 'item'
 WHERE EXISTS (SELECT 1 FROM item WHERE kind IN ('personal', 'skill-review'))
    OR NOT EXISTS (
     SELECT 1 FROM sqlite_master
      WHERE type = 'table' AND name = 'item'
        AND instr(sql, 'CHECK (kind IN (''work'', ''idea'', ''task'', ''report'',' || char(10) ||
                       '                                    ''followup'',' || char(10) ||
                       '                                    ''work-idea'', ''personal-idea'')),')
        AND length(sql) - length(replace(upper(sql), 'CHECK', '')) = 3 * length('CHECK')
        AND instr(sql, 'CHECK (status IN (''planning'', ''ready'', ''in_progress'',' || char(10) ||
                       '                                      ''ready_to_send'', ''blocked'', ''done''))')
        AND instr(sql, 'CHECK (gate_generation >= 0)')
        AND instr(sql, '''personal''') = 0 AND instr(sql, '''skill-review''') = 0);
DROP TABLE migration_046_guard;

-- `writable_schema` leaves the schema cookie untouched, so a connection that is
-- already open would keep the old CHECK; this pair bumps it, as 032's does.
CREATE TABLE migration_046_cookie (x INTEGER);
DROP TABLE migration_046_cookie;
