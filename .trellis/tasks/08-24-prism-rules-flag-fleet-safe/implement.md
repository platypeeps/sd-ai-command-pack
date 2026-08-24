# Implementation — prism rules flag, made fleet-safe

> **HOLD, 2026-08-24 — do not begin Phase 1.** Ten of the eleven consumer
> repositories are being worked on by other sessions. The fleet edit touches
> `.prism/rules.json` in each of them and must not race that work. Wait for the
> operator's explicit go-ahead before the first edit or `task.py start`.
>
> The enumeration table in `prd.md` is a 2026-08-24 snapshot and will be stale
> by the time the hold lifts. Step 1.1 already re-enumerates from the
> filesystem; treat any difference as the table being wrong, not the scan.

## Phase 1 — fleet edit (prerequisite)

Requirement 1. This lands before any pack change reaches a release.

- [ ] **1.1** Re-enumerate from the filesystem, not from `prd.md`:
      ```bash
      for f in ~/repos/*/*/.prism/rules.json; do
        python3 -c 'import json,sys
      d=json.load(open(sys.argv[1]))
      print(sys.argv[1]) if "severityOverrides" in d else None' "$f"
      done
      ```
      The table in `prd.md` is a snapshot from 2026-08-24; treat any difference
      as the enumeration being right and the table being stale.
- [ ] **1.2** For each repository the enumeration names: remove the
      `severityOverrides` key only. Leave `$schema`, `description`, `focus` and
      `required` byte-identical — `required` is the field that differs across
      consumers and is the one thing in these files that was deliberately
      authored per repository.
- [ ] **1.3** One commit per repository, on a branch, in that repository. Do not
      push. The commit message states what the block did (client-side severity
      overwrite after the model answers, `internal/review/rules.go:82`) rather
      than that it was removed.
- [ ] **1.4** Re-run 1.1. Expect no output. This is acceptance criterion 1.

**Rollback point.** Phase 1 is independently valuable and independently
revertible; nothing in Phase 2 has shipped yet. If Phase 2 is abandoned, the
fleet is left with rules files that describe what a review would do if rules
were passed — which is still more honest than the current state.

## Phase 2 — pack change

- [ ] **2.1** Add `_prism_rules(repo)` to
      `plugins/sd/bin/sd-ai-command-pack-review-local.py`. Four outcomes per the
      design table. Read through the existing `_read_json(..., limit=…)` helper,
      not `json.load` — this is consumer-controlled input.
- [ ] **2.2** Thread the decision: extra parameter on `_expand_argv`, appended
      in the three `adapter == "prism"` branches only (`:1420`–`:1445`); extra
      `rules=` keyword on `_run_provider`, merged into the attempt `base` dict.
- [ ] **2.3** Compute the decision once at the call site (`:2231`), above the
      dict comprehension. It depends only on `repo`.
- [ ] **2.4** Sync `plugins/sd/machine-payload/scripts/` from
      `plugins/sd/bin/`. Verify with
      `diff -q plugins/sd/bin/sd-ai-command-pack-review-local.py plugins/sd/machine-payload/scripts/sd-ai-command-pack-review-local.py`
      — must print nothing. Acceptance criterion 6, first half.

## Phase 3 — tests

- [ ] **3.1** `_expand_argv` carries `--rules .prism/rules.json` for
      `branch_delta`, `codebase` and `worktree`. Acceptance criterion 2.
- [ ] **3.2** `_expand_argv` carries no `--rules` when the file is absent, and
      the argv is otherwise byte-identical to today's. This is the
      no-behaviour-change guarantee for consumers without a rules file.
- [ ] **3.3** A rules file containing `severityOverrides` produces no `--rules`,
      `record["status"] == "refused"`, and the review still completes.
      Acceptance criterion 3.
- [ ] **3.4** Unreadable and non-object rules files produce `unreadable`, not an
      exception and not a failed review.
- [ ] **3.5** `gito` and `argv` adapter argv are unchanged by the new parameter.
- [ ] **3.6** Full suite plus `pack.install-audit`. Acceptance criterion 6.

## Phase 4 — live verification

Unit tests prove the flag is constructed. They cannot prove prism reads it, so
this phase is not optional.

- [ ] **4.1** Run a real review in a consumer **other than**
      `sd-github-review` — that repository has a `prism-chunked` `argv` provider
      and would exercise a path the fleet does not use. Pick one running pack
      defaults: `loadsmith`, `hoa-manager`, `rwbp-website`, `people-profiles`.
- [ ] **4.2** Probe run. Acceptance criterion 5. Plant a marker string in a
      scratch diff, point `--rules` at a scratch rules file whose `required`
      block demands a finding for that marker, disable prism's response cache
      for the run, and confirm the finding appears. Repeat without `--rules` and
      confirm it does not. Do **not** substitute a category check: prism
      hardcodes the same eight categories at `internal/review/prompt.go:28` that
      every consumer lists under `focus`, so that test passes unconditionally.
      The cache must be off — prism's cache key excludes the rules file, so a
      replay returns the no-rules answer while looking like a rules run.
- [ ] **4.3** Confirm `attempt.json` carries `rules.status == "applied"`, and in
      a scratch copy with `severityOverrides` re-added, `"refused"` with the key
      named. Acceptance criterion 4.
- [ ] **4.4** Confirm the severity distribution is not a category lookup:
      at least one category must appear at two different severities across the
      run. If every finding sits at its category's old mapped severity, either
      the fleet edit missed this repository or the overrides are coming from
      somewhere else — stop and find out which. Acceptance criterion 7.

## Phase 5 — release

- [ ] **5.1** Version bump, changelog. The changelog entry must say that
      consumers shipping `.prism/rules.json` will see their `focus` and
      `required` applied **for the first time**, and that new findings are the
      expected outcome rather than a regression.
- [ ] **5.2** Re-run 1.1 once more immediately before release. A repository
      installed between Phase 1 and Phase 5 arrives with a copied rules file,
      which is how all ten got theirs.
- [ ] **5.3** Roll to consumers; spot-check two receipts for
      `rules.status == "applied"`.

## Rollback

Phase 2 is a single commit touching one file and its mirror; revert restores
today's argv exactly, since the no-rules-file path is asserted byte-identical in
3.2. Phase 1 needs no rollback — a rules file without `severityOverrides` is
inert against a pack that does not pass `--rules`.

## Deliberately not here

- **4b.5**, `_disposition_counts` not writing the advisory classification back
  to `receipt.findings[]`. No ordering dependency either way.
- Chunking, and the four stock-prism defects on `~/repos/ai/prism` branch
  `fix/chunking-rules-maxtokens`.
