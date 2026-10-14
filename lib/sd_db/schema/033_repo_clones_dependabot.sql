-- `repo.clone_profiles` and `repo.dependabot`: two lists that lived in
-- config files move to the row (design sd:3983, sd:3984; pack sd:4043).
--
-- `clone_profiles` names the machine kinds `repo-sync` clones the repository
-- on: `personal` (the hub), `work` and `terra`. NULL means none. A set has one
-- spelling, its words in that order, so the CHECK is a closed list.
-- `sd-db repo clones PATH WORDS` and `sd-db repo seed --clones PROFILE` set it
-- through `sd_db.repos.set_clones`; `sd-db repo list --clones PROFILE` reads it.
--
-- `dependabot` is 1 for a repository outside the owner rule whose Dependabot
-- pull requests the daily sweep may take (`sd-db repo dependabot PATH yes`).
-- Every row starts at 0, as `allowed-repos.conf` started empty.
--
-- `ADD COLUMN` for 016's and 024's reason: SQLite adds a column in place,
-- touches no other table and moves no row. Both statements run in the one
-- transaction `migrate` wraps the file in, so a failure leaves neither.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops both lists; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE repo DROP COLUMN dependabot;
--   ALTER TABLE repo DROP COLUMN clone_profiles;
--   PRAGMA user_version = 32;
--   COMMIT;

ALTER TABLE repo ADD COLUMN clone_profiles TEXT
    CHECK (clone_profiles IS NULL OR clone_profiles IN (
        'personal', 'work', 'terra', 'personal,work', 'personal,terra', 'work,terra',
        'personal,work,terra'));

ALTER TABLE repo ADD COLUMN dependabot INTEGER NOT NULL DEFAULT 0
    CHECK (dependabot IN (0, 1));
