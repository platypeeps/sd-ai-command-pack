-- `repo.declarations`: a repository's declarations for the pack's readers,
-- one JSON object keyed by kind, or NULL when it declares none (sd:5109).
--
-- The kinds are `review` (the routing policy `sd-review` reads), `gate_reuse`
-- (the gate receipt key), `check_scope` (the docs-only check scope) and
-- `status` (accepted protection gaps). Each value is the object the
-- repository's `.github/sd-<kind>.json` file held before this column. The
-- operator's rule moves non-secret configuration into the database, and the
-- branch-protection audit trail that read the gap at the reviewed commit was
-- dropped (system sd:5109, note #23246).
-- `sd-db repo declare PATH KIND JSON|off` sets one kind through
-- `sd_db.repos.set_declaration`, and `repos.declarations` reads them. The
-- CHECK keeps out text that is not a JSON object; the writer checks the kinds.
--
-- `ADD COLUMN` for 029's reason: SQLite adds a nullable column in place,
-- touches no other table and moves no row. Every existing row reads NULL.
-- The reverse, run by hand with the runner, the dashboard and the serve agent
-- stopped. It drops every declaration; take `bin/sd-db backup` first:
--
--   BEGIN;
--   ALTER TABLE repo DROP COLUMN declarations;
--   PRAGMA user_version = 36;
--   COMMIT;

ALTER TABLE repo ADD COLUMN declarations TEXT
    CHECK (declarations IS NULL OR (json_valid(declarations) AND json_type(declarations) = 'object'));
