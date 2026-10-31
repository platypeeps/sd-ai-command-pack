-- `repo.github_issues` moves into the `policy` declaration as `issues`
-- (pack sd:6849, design docs/work/2026-10-29-repo-policy/design.md).
--
-- `issues` takes `off`, `read` or `ask` (note #34749: no `auto`). A row with
-- the column on arrives as `ask`: an agent reads its issues and maps each to
-- an sd item, as before, and every write it drafts waits for the operator.
-- A row with it off gains nothing: no `issues` key reads as `off`. The
-- policy's other keys are kept. Then the column goes, so one place holds the
-- setting; `sd-db repo github-issues PATH off|read|ask` writes the key.
--
-- One transaction (`migrate` wraps the file): a failure leaves 44 with the
-- column and no key written, and a rerun starts over.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. `read` reads back as off; take `bin/sd-db backup` first. It
-- rebuilds `repo` rather than adding the column at the end, as 026's does, so
-- `github_issues` sits where 035 put it and a backup restore compares the
-- table to 44's shape. Foreign keys are off for the rebuild, as `DROP TABLE
-- repo` would check them.
--
--   PRAGMA foreign_keys = OFF;
--   BEGIN;
--   CREATE TABLE repo_at_44 (
--       path TEXT PRIMARY KEY, remote TEXT, mode TEXT,
--       runner_merge TEXT NOT NULL DEFAULT 'manual' CHECK (runner_merge IN ('manual', 'auto')),
--       pieces_source TEXT NOT NULL DEFAULT 'file' CHECK (pieces_source IN ('file', 'retiring', 'row')),
--       created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
--       managed INTEGER NOT NULL DEFAULT 0 CHECK (managed IN (0, 1)),
--       ci TEXT NOT NULL DEFAULT 'github' CHECK (ci IN ('github', 'local')),
--       lane_host TEXT CHECK (lane_host IS NULL OR (lane_host <> '' AND lane_host NOT GLOB '*[^a-z0-9-]*')),
--       channels TEXT CHECK (channels IS NULL OR json_valid(channels)),
--       clone_profiles TEXT CHECK (clone_profiles IS NULL OR clone_profiles IN ('personal', 'work', 'terra', 'personal,work', 'personal,terra', 'work,terra', 'personal,work,terra')),
--       dependabot INTEGER NOT NULL DEFAULT 0 CHECK (dependabot IN (0, 1)),
--       github_issues INTEGER NOT NULL DEFAULT 0 CHECK (github_issues IN (0, 1)),
--       jira_project TEXT CHECK (jira_project IS NULL OR (typeof(jira_project) = 'text' AND length(jira_project) BETWEEN 2 AND 255 AND jira_project GLOB '[A-Z]*' AND jira_project NOT GLOB '*[^A-Z0-9_]*')),
--       declarations TEXT CHECK (declarations IS NULL OR (json_valid(declarations) AND json_type(declarations) = 'object')));
--   INSERT INTO repo_at_44 (path, remote, mode, runner_merge, pieces_source, created_at, updated_at, managed, ci,
--                           lane_host, channels, clone_profiles, dependabot, github_issues, jira_project, declarations)
--       SELECT path, remote, mode, runner_merge, pieces_source, created_at, updated_at, managed, ci,
--              lane_host, channels, clone_profiles, dependabot,
--              json_extract(declarations, '$.policy.issues') IS 'ask', jira_project, declarations FROM repo;
--   DROP TABLE repo;
--   ALTER TABLE repo_at_44 RENAME TO repo;
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy.issues') WHERE json_extract(declarations, '$.policy.issues') IS NOT NULL;
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy') WHERE json_extract(declarations, '$.policy') = '{}';
--   UPDATE repo SET declarations = NULL WHERE declarations = '{}';
--   PRAGMA user_version = 44;
--   COMMIT;
--   PRAGMA foreign_keys = ON;

UPDATE repo SET declarations = json_set(
        COALESCE(declarations, '{}'), '$.policy',
        json_set(COALESCE(json_extract(declarations, '$.policy'), '{}'), '$.issues', 'ask'))
    WHERE github_issues = 1;

ALTER TABLE repo DROP COLUMN github_issues;
