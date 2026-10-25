-- The build dispatcher's run columns on `runner_run` (pack sd:6093, design
-- system docs/work/2026-10-24-build-dispatcher). A Build press queues one
-- `assignment` per item (role `author`, lane `parallel`, scope `build`); a
-- claim writes one `runner_run` per bundle attempt and one `runner_lease`.
-- The retired runner's columns serve as they are; these are the ones a
-- headless builder run needs and the runner never had:
--
-- `step`, the step the supervisor is on, written before it starts;
-- `heartbeat_at`, its last beat, the reap's compare-and-set key; `model`, the
-- model the bundle runs on; `session_id`, the builder's Claude session, so it
-- never counts twice; `log_path`, its stream-json log; `builder_pgid`, its
-- process group, which the reap and the timeout kill; `builder_start`, its
-- leader's `ps -o lstart=`, without which nothing kills the group; and
-- `final`, its last stream line, the judge's evidence. (The `--   ` lines
-- below are the reverse, which the tests run; nothing else starts so.)
--
-- `ADD COLUMN`, as 041: SQLite adds a nullable column in place and moves no
-- row. Every existing run reads NULL in each, which is what a runner run
-- holds: `runner_journal.canonical` reads a journal written before this file
-- as NULL in each too, so the backup's journal check still matches its row.
--
-- The reverse, run by hand with the dashboard and the serve agent stopped. It
-- drops every build run's step, beat and evidence, so cancel or let every
-- build run end first; take `bin/sd-db backup` before:
--
--   BEGIN;
--   ALTER TABLE runner_run DROP COLUMN final;
--   ALTER TABLE runner_run DROP COLUMN builder_start;
--   ALTER TABLE runner_run DROP COLUMN builder_pgid;
--   ALTER TABLE runner_run DROP COLUMN log_path;
--   ALTER TABLE runner_run DROP COLUMN session_id;
--   ALTER TABLE runner_run DROP COLUMN model;
--   ALTER TABLE runner_run DROP COLUMN heartbeat_at;
--   ALTER TABLE runner_run DROP COLUMN step;
--   PRAGMA user_version = 41;
--   COMMIT;

ALTER TABLE runner_run ADD COLUMN step TEXT;
ALTER TABLE runner_run ADD COLUMN heartbeat_at TEXT;
ALTER TABLE runner_run ADD COLUMN model TEXT;
ALTER TABLE runner_run ADD COLUMN session_id TEXT;
ALTER TABLE runner_run ADD COLUMN log_path TEXT;
ALTER TABLE runner_run ADD COLUMN builder_pgid INTEGER;
ALTER TABLE runner_run ADD COLUMN builder_start TEXT;
ALTER TABLE runner_run ADD COLUMN final TEXT;
