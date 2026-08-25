# Implementation — prism rules flag, made fleet-safe

> **Reordered 2026-08-24, at the start of implementation.** The first plan ran
> the fleet edit as Phase 1, before any pack change. That is impossible:
> `.prism/rules.schema.json` lists `severityOverrides` under `required`, and the
> schema is `install: always`, so it reaches a consumer only through a pack
> release. Stripping the key first leaves every repository holding a file
> invalid against the schema beside it — the state `sd-github-review` has been
> in, unobserved, since 2026-08-24. Phases below are in execution order.
>
> An earlier revision kept the old numbers with a "runs later" note. That
> produced two contradictions — a pre-release fleet scan that could not pass,
> and a post-release receipt check expecting `applied` while the guard was still
> refusing — so the numbers were changed instead of annotated.

## Phase 0 — pack templates

Requirement 1b. The schema has to stop forbidding the end state before anything
else can reach it.

- [ ] **0.1** `templates/.prism/rules.schema.json`: drop `severityOverrides`
      from `required`. Leave it in `properties` — `additionalProperties: false`
      means deleting the property would forbid the key outright rather than
      merely stop requiring it. This task's position is that the key is a bad
      idea, not that it is unrepresentable.
- [ ] **0.2** `templates/.prism/rules.json`: remove the `severityOverrides`
      block, and amend the `description` sentence instructing the reader to keep
      `focus` and `severityOverrides` category names in sync.
- [ ] **0.3** Regenerate the mirrors and `plugins/sd/machine-payload/`
      derivatives. `tests/test_generated_parity.py:334` and
      `tests/test_review_scope.py:1583` both reference these two paths and will
      catch a partial regeneration.
- [ ] **0.4** Confirm the schema change only widens what validates: every
      consumer's current `rules.json` — block still present — still passes.
      Dropping a `required` entry cannot invalidate anything, so a failure here
      means the wrong edit was made.

## Phase 1 — pack change

- [ ] **1.1** Add `_prism_rules(repo)` to
      `plugins/sd/bin/sd-ai-command-pack-review-local.py`. Four outcomes per the
      design table. Read through the existing `_read_json(..., limit=…)` helper,
      not `json.load` — this is consumer-controlled input.
- [ ] **1.2** Thread the decision: extra parameter on `_expand_argv`, appended
      in the three `adapter == "prism"` branches only (`:1420`–`:1445`); extra
      `rules=` keyword on `_run_provider`, merged into the attempt `base` dict.
- [ ] **1.3** Compute the decision once at the call site (`:2231`), above the
      dict comprehension. It depends only on `repo`.
- [ ] **1.4** Sync `plugins/sd/machine-payload/scripts/` from
      `plugins/sd/bin/`. Verify with
      `diff -q plugins/sd/bin/sd-ai-command-pack-review-local.py plugins/sd/machine-payload/scripts/sd-ai-command-pack-review-local.py`
      — must print nothing. Acceptance criterion 6, first half.

## Phase 2 — tests

- [ ] **2.1** `_expand_argv` carries `--rules .prism/rules.json` for
      `branch_delta`, `codebase` and `worktree`. Acceptance criterion 2.
- [ ] **2.2** `_expand_argv` carries no `--rules` when the file is absent, and
      the argv is otherwise byte-identical to today's. This is the
      no-behaviour-change guarantee for consumers without a rules file.
- [ ] **2.3** A rules file containing `severityOverrides` produces no `--rules`,
      `record["status"] == "refused"`, and the review still completes.
      Acceptance criterion 3.
- [ ] **2.4** Unreadable and non-object rules files produce `unreadable`, not an
      exception and not a failed review.
- [ ] **2.5** `gito` and `argv` adapter argv are unchanged by the new parameter.
- [ ] **2.6** Full suite plus `pack.install-audit`. Acceptance criterion 6.

## Phase 3 — release and rollout

- [ ] **3.1** Version bump, changelog. The entry must say that consumers
      shipping `.prism/rules.json` will see their `focus` and `required` applied
      **for the first time** once they strip `severityOverrides`, and that new
      findings are the expected outcome rather than a regression.
- [ ] **3.2** Roll to consumers. This is what delivers the new schema, which is
      `install: always`. `rules.json` is `install: if-not-exists` and is not
      touched by the rollout — that is Phase 4's job.
- [ ] **3.3** Spot-check two receipts. Expect `rules.status == "refused"`, not
      `"applied"`: every consumer still carries the block at this point, so the
      guard is doing its job and behaviour is unchanged from before the release.
      An `"applied"` here would mean the guard is not working.

**Rollback point.** Everything so far is revertible from the pack alone; no
consumer file has been edited. Behaviour across the fleet is identical to before
the release, by construction.

## Phase 4 — fleet edit

Requirement 1. Seven repositories by hand; two more are handled by the rollout
and two are already clean. See design, "Most of the fleet edit is already
automated".

- [ ] **4.0** Confirm the rollout in Phase 3 did **not** use `install.py
      --force`. Force overrides `if-not-exists` and would overwrite consumer
      rules files wholesale, destroying per-repository `required` checks —
      eleven of them in `hoa-manager`, twelve in `rwbp-coordinator`. Observed
      directly: `make sync` is `install.py . --force` and it rewrote this
      repository's own `.prism/rules.json`.
- [ ] **4.0b** Confirm `loadsmith` and `people-profiles` came back `refreshed`
      rather than `preserved`. They held the previous shipped default
      `cea5089e` byte-for-byte, which is now on the history `digests` list. If
      they read `preserved`, the history regeneration did not ship and the
      remaining steps are hiding a broken mechanism.

- [ ] **4.1** Re-enumerate from the filesystem, not from `prd.md`:
      ```bash
      for f in ~/repos/*/*/.prism/rules.json; do
        python3 -c 'import json,sys
      d=json.load(open(sys.argv[1]))
      print(sys.argv[1]) if "severityOverrides" in d else None' "$f"
      done
      ```
      The table in `prd.md` is a snapshot from 2026-08-24; treat any difference
      as the enumeration being right and the table being stale.
- [ ] **4.2** For each repository named: remove the `severityOverrides` key, and
      amend `description` where it references it — nine of the ten say "keeps
      focus and severityOverrides separate; keep their category names in sync",
      which becomes an instruction about a block that no longer exists.
      `hoa-manager`'s description does not mention it and stays as it is. Leave
      `$schema`, `focus` and `required` byte-identical: `required` differs across
      consumers and is the one thing in these files deliberately authored per
      repository.
- [ ] **4.3** One commit per repository, on a branch, in that repository. Do not
      push. `git add` the rules file by path — several of these repositories have
      untracked work from other sessions and `git add -A` would sweep it in. The
      commit message states what the block did (client-side severity overwrite
      after the model answers, `internal/review/rules.go:82`) rather than that it
      was removed.
- [ ] **4.4** Re-run 4.1. Expect no output, and check
      `templates/.prism/rules.json` too. Acceptance criterion 1. The count of
      repositories edited by hand in 4.2 plus those refreshed in 4.0b plus those
      already clean must equal the eleven the scan finds — if it does not, a
      repository was missed rather than handled.
- [ ] **4.5** Validate every consumer's `rules.json` against the
      `rules.schema.json` beside it. All eleven pass, including
      `sd-github-review`, which fails today. Acceptance criterion 0.

## Phase 5 — live verification

Unit tests prove the flag is constructed. They cannot prove prism reads it, so
this phase is not optional.

- [ ] **5.1** Run a real review in a consumer **other than**
      `sd-github-review` — that repository has a `prism-chunked` `argv` provider
      and would exercise a path the fleet does not use. Pick one running pack
      defaults: `loadsmith`, `hoa-manager`, `rwbp-website`, `people-profiles`.
- [ ] **5.2** Probe run. Acceptance criterion 5. Plant a marker string in a
      scratch diff, point `--rules` at a scratch rules file whose `required`
      block demands a finding for that marker, disable prism's response cache
      for the run, and confirm the finding appears. Repeat without `--rules` and
      confirm it does not. Do **not** substitute a category check: prism
      hardcodes the same eight categories at `internal/review/prompt.go:28` that
      every consumer lists under `focus`, so that test passes unconditionally.
      The cache must be off — prism's cache key excludes the rules file, so a
      replay returns the no-rules answer while looking like a rules run.
- [ ] **5.3** Confirm `attempt.json` now carries `rules.status == "applied"`,
      and in a scratch copy with `severityOverrides` re-added, `"refused"` with
      the key named. Acceptance criterion 4.
- [ ] **5.4** Confirm the severity distribution is not a category lookup: at
      least one category appears at two different severities across the run. If
      every finding sits at its category's old mapped severity, either the fleet
      edit missed this repository or the overrides come from somewhere else —
      stop and find out which. Acceptance criterion 7.

## Rollback

Phase 1 is a single commit touching one file and its mirror; revert restores
today's argv exactly, since the no-rules-file path is asserted byte-identical in
2.2. Phase 0 only widens the schema and removes a template default, so reverting
it cannot invalidate a consumer file that was valid. Phase 4 is per-repository
and independently revertible; a rules file without `severityOverrides` is inert
against a pack that has not shipped Phase 1.

## Deliberately not here

- **4b.5**, `_disposition_counts` not writing the advisory classification back
  to `receipt.findings[]`. No ordering dependency either way.
- Chunking, and the four stock-prism defects on `~/repos/ai/prism` branch
  `fix/chunking-rules-maxtokens`.
