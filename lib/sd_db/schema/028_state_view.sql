-- `view` joins the `state` kinds (sd:3430): a Documents file the operator
-- pinned, hid or tagged on the dashboard. One row per write, keyed by the
-- root key and the file under it (`system/index.html`), with `pinned`,
-- `hidden` and `tags` in the body; clearing them writes the same key with
-- all three cleared. The latest row for a key is the answer, read through
-- 013's `state_by_kind_key`. Nothing expires a row.
--
-- SQLite cannot alter a CHECK constraint, so the table is rebuilt the way
-- 027 rebuilt it: renamed away, recreated, the rows copied with their ids,
-- the old one dropped, and all four indexes recreated -- `state_by_kind`
-- from 001, `runner_heartbeat` from 005, `runner_check` from 007 and
-- `state_by_kind_key` from 013. Nothing references `state` by foreign key,
-- so the rename rewrites no other table.
--
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops the view rows, which the 27 shape cannot hold, so every
-- pinned, hidden or tagged document shows plain again.
--
--   BEGIN;
--   DELETE FROM state WHERE kind = 'view';
--   ALTER TABLE state RENAME TO state_before_reverse;
--   CREATE TABLE state (
--       id              INTEGER PRIMARY KEY,
--       kind            TEXT NOT NULL
--                       CHECK (kind IN ('checkpoint', 'verified', 'restore',
--                                       'watermark', 'heartbeat', 'check',
--                                       'snooze')),
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
--   PRAGMA user_version = 27;
--   COMMIT;

ALTER TABLE state RENAME TO state_before_028;
CREATE TABLE state (
    id              INTEGER PRIMARY KEY,
    -- The operational records that are not items. A kind not in this list
    -- has no home, which is the point: it is added here, in review, before
    -- anything writes it.
    kind            TEXT NOT NULL
                    CHECK (kind IN ('checkpoint', 'verified', 'restore',
                                    'watermark', 'heartbeat', 'check',
                                    'snooze', 'view')),
    key             TEXT,
    timestamp       TEXT NOT NULL,
    body            TEXT,
    resolved_at     TEXT
);
INSERT INTO state (id, kind, key, timestamp, body, resolved_at)
    SELECT id, kind, key, timestamp, body, resolved_at FROM state_before_028;
DROP TABLE state_before_028;
CREATE INDEX state_by_kind ON state (kind, timestamp);
CREATE UNIQUE INDEX runner_heartbeat ON state(key)
    WHERE kind = 'heartbeat' AND key = 'runner';
CREATE UNIQUE INDEX runner_check ON state(key)
    WHERE kind = 'check';
CREATE INDEX state_by_kind_key ON state (kind, key, id);
