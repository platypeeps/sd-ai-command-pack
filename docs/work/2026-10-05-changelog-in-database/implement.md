# Implement — changelog entries in the database

One repository, the pack. Six pull requests; the system repository does not
change. The design is in [design.md](design.md). Open questions Q1 to Q7 are
in its "Decisions and open questions" section. The steps follow the
recommendations; a different ruling changes the step it names.

Each step names its check and the result that means failure. Each check must
fail on `main` before the step's code lands.

## Step checklist

- [ ] 1. `bin/sd_changelog.py`: parser, row key, writer, reader. Size M, 4 h.
      Own PR.
      - `parse(body)` returns the entries of the `## Changelog` section, an
        empty list for `none` (Q1), or a refusal code: `changelog_missing`,
        `changelog_invalid`.
      - `private(text, patterns)` returns the matching line numbers.
      - `key(slug, pr)`, `write(connection, row)` through `sd_db.ship.save`,
        idempotent on `merge_commit` and `body_digest`.
      - `rows(connection, slug)` by range scan on `state`, newest revision
        per key.
      - Nothing calls them yet.
      - Check: `tests/test_sd_changelog.py` passes. It covers each refusal
        code, `none`, a slug with `_` that a `LIKE` would over-match, and a
        second `write` that adds no revision. Mutating the range bound to a
        `LIKE` fails the slug test.
- [ ] 2. `sd changelog render|show|import` in `bin/sd`. Size M, 4 h. Own PR.
      - Selection, order, region markers and `--release` as design point 3
        states. `--check` exits 1 on a difference.
      - Cross-check against squash messages since the newest `v*` tag (Q6:
        refuse). `import <pr>` writes a row from a squash message.
      - Privacy re-check of every row (Q7: refuse with no pattern file).
      - Check: a fixture repository with three rows renders byte-identical
        output twice, and again after the rows are written in reverse order.
        A deleted row makes render exit nonzero and name the pull request. A
        synthetic pattern match refuses. Swapping the sort key to `merged_at`
        fails the reverse-order test.
- [ ] 3. `sd-ship prepare` checks the section. Size M, 3 h. Own PR.
      - Only when `.github/sd-changelog.json` reads `{"mode": "database"}`
        at the head; otherwise nothing changes (R8).
      - Refuse a missing or invalid section, a privacy match (line numbers
        only; Q7: warn with no pattern file), and a diff that changes
        `CHANGELOG.md`, except a render branch that passes
        `sd changelog render --check`.
      - Save the parsed entries in the ship row.
      - Check: tests for PRD acceptance criteria 1, 2 and 7 pass in
        `tests/test_sd_ship.py`. Each fails with the new branch removed.
- [ ] 4. `sd-ship reconcile` writes the row. Size S, 2 h. Own PR.
      - In `reconcile`, after the merge evidence checks and before
        `self.save(phase="merged")`. Opted-in repositories only.
      - Check: PRD criterion 3 (two reconciles, one row) passes. A store
        whose `save` raises leaves the phase at `merge_dispatch`, and a
        second reconcile writes the row. Moving the write after the phase
        save fails that test.
- [ ] 5. Cutover: the pack opts in. Size S, 2 h. Own PR.
      - Add `.github/sd-changelog.json`, the empty marked region under
        `## Unreleased`, and the `## Changelog` section in
        `.github/PULL_REQUEST_TEMPLATE.md`.
      - Update `CONTRIBUTING.md` (the entry rule, and the terminal-release
        line per Q4), `WORKFLOW.md` and `skills/sd-ship/SKILL.md`.
      - This pull request itself carries `## Changelog`, so its merge writes
        the first row.
      - Check: after merge, `sd changelog show` prints that entry, and
        `git diff 5dff9e55 -- CHANGELOG.md` shows only the two marker lines
        added. Any other changed line fails R9.
- [ ] 6. First render pull request. Size S, 1 h.
      - Run `sd changelog render`, ship the branch.
      - Check: prepare passes `render --check`; a feature branch prepared in
        the same hour that edits `CHANGELOG.md` refuses with
        `changelog_edited`.
      - Q3: if the operator rules for a daily render, add the lane job here,
        plus 1 h.
- [ ] 7. Delete the keep-both resolver. Size S, 2 h. Own PR.
      - Precondition: no open pack branch changes `CHANGELOG.md` against
        `origin/main` (`git diff --name-only origin/main...<branch>` over
        every open pull request's head). Ask the operator first whether a
        repository that has not opted in relies on the resolver.
      - Remove every place design point 4 lists.
      - Check: `grep -rn sd_changelog_merge bin tests skills`
        returns nothing, and `make check` passes.

## Estimate

| Step | Hours |
| --- | --- |
| 1 | 4 |
| 2 | 4 |
| 3 | 3 |
| 4 | 2 |
| 5 | 2 |
| 6 | 1 (2 with a daily lane job) |
| 7 | 2 |
| Total | 18, or 19 with the daily job |

Review rounds are not included. At an assumed 1 h per pull request, the
total is about 24 h.

## After step 7

Re-run the measurement in [prd.md](prd.md) over the two weeks after step 5.
Expect zero `CHANGELOG.md` conflicts in feature branches. Any conflict names
a branch that edited the file and passed prepare, which is a defect in step 3.
