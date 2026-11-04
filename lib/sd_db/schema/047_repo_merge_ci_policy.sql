-- `repo.runner_merge` and `repo.ci` gain their `policy` keys, `merge` and
-- `ci.provider` (pack sd:7366 slice 1, design
-- docs/work/2026-11-03-repo-policy-fold/design.md). The columns stay until 48;
-- every writer sets both, and every reader reads the key.
--
-- `auto` arrives as `merge: auto` and `local` as `ci.provider: local`; the
-- defaults, `manual` and `github`, add nothing, since no key reads as them.
-- The policy's other keys are kept. A key the policy already holds wins. An
-- org or external policy takes no `merge` (note #34749), and a policy or
-- `ci` that is not an object takes no key: each reads `manual` or `github`.
-- Last, the columns are set from the policy, so every row agrees and a
-- reader of either gets one answer: that moves only an org or external row's
-- `auto`, a junk policy's settings and a `local` under a declared `jenkins`.
--
-- One transaction (`migrate` wraps the file): a failure leaves 46 with no key
-- written, and a rerun starts over.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped, after `bin/sd-db backup`. It takes the two keys out and leaves
-- the columns, which hold the same settings; a `jenkins` provider stays.
--
--   BEGIN;
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy.merge') WHERE json_extract(declarations, '$.policy.merge') IS NOT NULL;
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy.ci.provider') WHERE json_extract(declarations, '$.policy.ci.provider') IN ('github', 'local');
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy.ci') WHERE json_extract(declarations, '$.policy.ci') = '{}';
--   UPDATE repo SET declarations = json_remove(declarations, '$.policy') WHERE json_extract(declarations, '$.policy') = '{}';
--   UPDATE repo SET declarations = NULL WHERE declarations = '{}';
--   PRAGMA user_version = 46;
--   COMMIT;

UPDATE repo SET declarations = json_set(
        COALESCE(declarations, '{}'), '$.policy',
        json_set(COALESCE(json_extract(declarations, '$.policy'), '{}'), '$.merge', 'auto'))
    WHERE runner_merge = 'auto'
      AND COALESCE(json_type(declarations, '$.policy'), 'object') = 'object'
      AND json_type(declarations, '$.policy.merge') IS NULL
      AND COALESCE(json_extract(declarations, '$.policy.mode'), 'managed') = 'managed';

UPDATE repo SET declarations = json_set(
        COALESCE(declarations, '{}'), '$.policy',
        json_set(COALESCE(json_extract(declarations, '$.policy'), '{}'), '$.ci',
                 json_set(COALESCE(json_extract(declarations, '$.policy.ci'), '{}'), '$.provider', 'local')))
    WHERE ci = 'local'
      AND COALESCE(json_type(declarations, '$.policy'), 'object') = 'object'
      AND COALESCE(json_type(declarations, '$.policy.ci'), 'object') = 'object'
      AND json_type(declarations, '$.policy.ci.provider') IS NULL;

-- `writes.MERGE_SQL` and `writes.CI_SQL`, written out: a migration names no library constant.
UPDATE repo SET
        runner_merge = CASE WHEN json_extract(declarations, '$.policy.merge') = 'auto'
                             AND COALESCE(json_extract(declarations, '$.policy.mode'), 'managed') = 'managed'
                            THEN 'auto' ELSE 'manual' END,
        ci = CASE WHEN json_extract(declarations, '$.policy.ci.provider') = 'local' THEN 'local' ELSE 'github' END;
