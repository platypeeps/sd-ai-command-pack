-- `repo.jira_project`: the Jira project key a repository files issues in, or
-- NULL when it files none (sd:5103).
--
-- The operator files a sanitized issue from the dashboard; this names where a
-- Jira one goes. `repo.github_issues` says the same for GitHub. It is a
-- filing target, not the inbound issue source `repo.channels` names as
-- `jira=KEY`: the two may differ, and setting one changes nothing in the other.
-- `sd-db repo jira-project PATH KEY|off` sets it and `repos.jira_project`
-- reads it.
--
-- Every row starts NULL, off. The CHECK holds the spelling `channels` uses for
-- a key, `[A-Z][A-Z0-9_]+`, up to 255 characters, Jira's own ceiling.
-- `ADD COLUMN` for 015's reason: SQLite adds a column with a constant default
-- and a CHECK in place, touches no other table and moves no row.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops every setting; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE repo DROP COLUMN jira_project;
--   PRAGMA user_version = 35;
--   COMMIT;

ALTER TABLE repo ADD COLUMN jira_project TEXT
    CHECK (jira_project IS NULL OR (typeof(jira_project) = 'text'
        AND length(jira_project) BETWEEN 2 AND 255
        AND jira_project GLOB '[A-Z]*'
        AND jira_project NOT GLOB '*[^A-Z0-9_]*'));
