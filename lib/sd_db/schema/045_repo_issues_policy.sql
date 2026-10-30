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
-- stopped. `read` reads back as off; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE repo ADD COLUMN github_issues INTEGER NOT NULL DEFAULT 0 CHECK (github_issues IN (0, 1));
--   UPDATE repo SET github_issues = 1 WHERE json_extract(declarations, '$.policy.issues') = 'ask';
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy.issues') WHERE json_extract(declarations, '$.policy.issues') IS NOT NULL;
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy') WHERE json_extract(declarations, '$.policy') = '{}';
--   UPDATE repo SET declarations = NULL WHERE declarations = '{}';
--   PRAGMA user_version = 44;
--   COMMIT;

UPDATE repo SET declarations = json_set(
        COALESCE(declarations, '{}'), '$.policy',
        json_set(COALESCE(json_extract(declarations, '$.policy'), '{}'), '$.issues', 'ask'))
    WHERE github_issues = 1;

ALTER TABLE repo DROP COLUMN github_issues;
