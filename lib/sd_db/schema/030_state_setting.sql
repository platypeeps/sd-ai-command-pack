-- `setting` joins the `state` kinds (sd:3989, design sd:3983 slice P1): a
-- value the operator sets once for every machine, keyed by its dotted name
-- (`sd.copilot_review`, `dashboard.home_tiles`). One row per write, with
-- `{"value": ...}` in the body; an unset writes the same key with a null
-- value, so a value still in an old file cannot come back. The latest row for
-- a key is the answer, read through 013's `state_by_kind_key`. Nothing
-- expires a row, so the rows are the history Undo reads.
--
-- SQLite cannot alter a CHECK constraint, so the table is rebuilt the way
-- 028 rebuilt it: renamed away, recreated, the rows copied with their ids,
-- the old one dropped, and all four indexes recreated -- `state_by_kind`
-- from 001, `runner_heartbeat` from 005, `runner_check` from 007 and
-- `state_by_kind_key` from 013. Nothing references `state` by foreign key,
-- so the rename rewrites no other table.
--
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped, after `bin/sd-db backup`. It drops the setting rows, which the 29
-- shape cannot hold, and they may be the only copy of a value. So first save
-- them: `sd config list sd --json` and the `dashboard.home_tiles` row's text
-- go to a file under the bulk root. Reverse any later migration first, in
-- its own header, then this one. Then the older `sd config set` writes each
-- saved fleet key back to `config.json`, and the tile text goes back to
-- `home-tiles.conf`.
--
--   BEGIN;
--   DELETE FROM state WHERE kind = 'setting';
--   ALTER TABLE state RENAME TO state_before_reverse;
--   CREATE TABLE state (
--       id              INTEGER PRIMARY KEY,
--       kind            TEXT NOT NULL
--                       CHECK (kind IN ('checkpoint', 'verified', 'restore',
--                                       'watermark', 'heartbeat', 'check',
--                                       'snooze', 'view')),
--       key             TEXT,
--       timestamp       TEXT NOT NULL,
--       body            TEXT,
--       resolved_at     TEXT
--   );
--   INSERT INTO state (id, kind, key, timestamp, body, resolved_at)
--       SELECT id, kind, key, timestamp, body, resolved_at FROM state_before_reverse;
--   DROP TABLE state_before_reverse;
--   CREATE INDEX state_by_kind ON state (kind, timestamp);
--   CREATE UNIQUE INDEX runner_heartbeat ON state(key) WHERE kind = 'heartbeat' AND key = 'runner';
--   CREATE UNIQUE INDEX runner_check ON state(key) WHERE kind = 'check';
--   CREATE INDEX state_by_kind_key ON state (kind, key, id);
--   PRAGMA user_version = 29;
--   COMMIT;

ALTER TABLE state RENAME TO state_before_030;
CREATE TABLE state (
    id              INTEGER PRIMARY KEY,
    -- The operational records that are not items. A kind not in this list
    -- has no home, which is the point: it is added here, in review, before
    -- anything writes it.
    kind            TEXT NOT NULL
                    CHECK (kind IN ('checkpoint', 'verified', 'restore',
                                    'watermark', 'heartbeat', 'check',
                                    'snooze', 'view', 'setting')),
    key             TEXT,
    timestamp       TEXT NOT NULL,
    body            TEXT,
    resolved_at     TEXT
);
INSERT INTO state (id, kind, key, timestamp, body, resolved_at)
    SELECT id, kind, key, timestamp, body, resolved_at FROM state_before_030;
DROP TABLE state_before_030;
CREATE INDEX state_by_kind ON state (kind, timestamp);
CREATE UNIQUE INDEX runner_heartbeat ON state(key)
    WHERE kind = 'heartbeat' AND key = 'runner';
CREATE UNIQUE INDEX runner_check ON state(key)
    WHERE kind = 'check';
CREATE INDEX state_by_kind_key ON state (kind, key, id);
