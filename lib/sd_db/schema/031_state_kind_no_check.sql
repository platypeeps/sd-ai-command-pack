-- `state.kind` loses its CHECK (sd:3506). `writes.STATE_KINDS` is the one
-- list: `record_state` refuses a kind outside it, so the CHECK was a second
-- copy, and SQLite cannot alter one. Migrations 007, 027, 028 and 030 each
-- rebuilt the whole table, the hub's largest, to add one word. With no CHECK
-- a new kind is a library change and no migration.
--
-- The CHECK text is edited in place, as 009 edited `item.kind`'s: removing a
-- CHECK changes nothing on disk, so no row moves and no table is rebuilt.
-- `replace` swaps the exact block 030 wrote, comment lines included, so the
-- stored schema does not keep a comment that says the CHECK is the list.
--
-- Two guards hold the edit to the shapes this file knows. The first, before
-- `writable_schema` is on, accepts the block 030 wrote or the one this file
-- leaves: a restore replays migrations onto a snapshot that may already
-- carry the second (`backup.py`, `_upgrade_restore_candidate`), and there
-- the `replace` finds nothing and changes nothing. The second, after it is
-- reset, accepts only no CHECK left anywhere in `state`, so a second CHECK
-- on the kind cannot survive. A refusal fails the guard's own CHECK, in a
-- temporary table so it does not hang on `state`'s constraints; that aborts
-- the transaction and leaves the file at 30.
--
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped, after `bin/sd-db backup`. It puts the CHECK back as 030 wrote it,
-- which holds only while every row's kind is one of the nine:
-- `SELECT DISTINCT kind FROM state` first, and delete or keep back any other.
--
--   BEGIN;
--   PRAGMA writable_schema = ON;
--   UPDATE sqlite_master SET sql = replace(sql,
--       '    -- The operational records that are not items. `writes.STATE_KINDS`' || char(10) ||
--       '    -- is their list, and the library validates it (031).' || char(10) ||
--       '    kind            TEXT NOT NULL,',
--       '    -- The operational records that are not items. A kind not in this list' || char(10) ||
--       '    -- has no home, which is the point: it is added here, in review, before' || char(10) ||
--       '    -- anything writes it.' || char(10) ||
--       '    kind            TEXT NOT NULL' || char(10) ||
--       '                    CHECK (kind IN (''checkpoint'', ''verified'', ''restore'',' || char(10) ||
--       '                                    ''watermark'', ''heartbeat'', ''check'',' || char(10) ||
--       '                                    ''snooze'', ''view'', ''setting'')),')
--    WHERE type = 'table' AND name = 'state';
--   PRAGMA writable_schema = RESET;
--   CREATE TABLE migration_031_cookie (x INTEGER);
--   DROP TABLE migration_031_cookie;
--   PRAGMA user_version = 30;
--   COMMIT;

-- The first guard, before `writable_schema` is switched on: `state` is in
-- the shape 030 left or the one this file leaves.
CREATE TEMP TABLE migration_031_guard (
    refused TEXT CONSTRAINT migration_031_refuses_an_unknown_state_shape CHECK (refused IS NULL)
);
INSERT INTO migration_031_guard
SELECT 'state'
 WHERE NOT EXISTS (
     SELECT 1 FROM sqlite_master
      WHERE type = 'table' AND name = 'state'
        AND (instr(sql, '    -- The operational records that are not items. A kind not in this list' || char(10) ||
                       '    -- has no home, which is the point: it is added here, in review, before' || char(10) ||
                       '    -- anything writes it.' || char(10) ||
                       '    kind            TEXT NOT NULL' || char(10) ||
                       '                    CHECK (kind IN (''checkpoint'', ''verified'', ''restore'',' || char(10) ||
                       '                                    ''watermark'', ''heartbeat'', ''check'',' || char(10) ||
                       '                                    ''snooze'', ''view'', ''setting'')),')
          OR instr(sql, '    -- is their list, and the library validates it (031).' || char(10) ||
                        '    kind            TEXT NOT NULL,')));

PRAGMA writable_schema = ON;

UPDATE sqlite_master
   SET sql = replace(
       sql,
       '    -- The operational records that are not items. A kind not in this list' || char(10) ||
       '    -- has no home, which is the point: it is added here, in review, before' || char(10) ||
       '    -- anything writes it.' || char(10) ||
       '    kind            TEXT NOT NULL' || char(10) ||
       '                    CHECK (kind IN (''checkpoint'', ''verified'', ''restore'',' || char(10) ||
       '                                    ''watermark'', ''heartbeat'', ''check'',' || char(10) ||
       '                                    ''snooze'', ''view'', ''setting'')),',
       '    -- The operational records that are not items. `writes.STATE_KINDS`' || char(10) ||
       '    -- is their list, and the library validates it (031).' || char(10) ||
       '    kind            TEXT NOT NULL,')
 WHERE type = 'table' AND name = 'state';

PRAGMA writable_schema = RESET;

-- The second guard, after `writable_schema` is reset so a refusal never
-- leaves it set: no CHECK is left anywhere in `state`.
INSERT INTO migration_031_guard
SELECT 'state'
 WHERE NOT EXISTS (
     SELECT 1 FROM sqlite_master
      WHERE type = 'table' AND name = 'state'
        AND instr(upper(sql), 'CHECK') = 0
        AND instr(sql, '    -- is their list, and the library validates it (031).' || char(10) ||
                       '    kind            TEXT NOT NULL,'));
DROP TABLE migration_031_guard;

-- `writable_schema` leaves the schema cookie untouched, so a connection that is
-- already open would keep the old CHECK; this pair bumps it, as 009's does.
CREATE TABLE migration_031_cookie (x INTEGER);
DROP TABLE migration_031_cookie;
