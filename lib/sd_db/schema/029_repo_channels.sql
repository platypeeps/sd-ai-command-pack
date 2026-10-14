-- `repo.channels`: the publish channels a repository uses, and the folder
-- each one writes to (sd:3462, design sd:3471).
--
-- A JSON object such as `{"obsidian": {"folder": "Briefs/x"}, "drive": {}}`.
-- NULL means no setting: the repository publishes as it did before 29, so
-- nothing moves at migration. `sd-db repo channels PATH ...` sets it through
-- `sd_db.repos.set_channels`, which checks the closed vocabulary in
-- `sd_db.channels.validate`; the CHECK only keeps text that is not JSON out.
--
-- `ADD COLUMN` for 016's and 024's reason: SQLite adds a nullable column in
-- place, touches no other table and moves no row. Every existing row reads NULL.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops every setting; take `bin/sd-db backup` first.
--
--   BEGIN;
--   ALTER TABLE repo DROP COLUMN channels;
--   PRAGMA user_version = 28;
--   COMMIT;

ALTER TABLE repo ADD COLUMN channels TEXT
    CHECK (channels IS NULL OR json_valid(channels));
