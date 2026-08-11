# Implementation plan — repoint surviving pack surfaces off removed paths

Ordered. Each step names the command that proves it, and the result that
counts as failure. Steps 1 and 2 are measurement and must run before any
edit — a baseline captured after the change proves nothing.

## 0. Baseline, before touching anything

```bash
.venv/bin/python .trellis/tasks/archive/2026-08/08-10-thin-conversion-tooling/research/fleet-blocker-scan.py --out /tmp/baseline.json
```

**Measured 2026-08-11:** `packDefects` **17 in 8 files** for the five
consumers carrying the pack's PR template, **15 in 7** for
`mezmo_benchmark`, `sd-github-review`, and `anomaly-metric-creator`. That
is this task's seven surfaces plus one synthetic `codex` row owned by
`08-11-thin-undeclared-codex-marker`. See the PRD's baseline-correction
section; the PRD's original 16/7 predates the detector that adds the
eighth.

The scanner needs `ROOT` pinned to run from its archived path — copy it
and replace `Path(__file__).resolve().parents[4]` with the repository
root. Do not edit the archived research file.

Record the baseline **per surface**, not only in aggregate. Step 9's
criteria are per-surface, and an aggregate that reaches zero cannot show
which surface got there.

## 1. Confirm D2's decided shape against the fixture

Settled during planning review: a **mode-aware managed block chosen at
install time** (design D2). Nothing here is open; this step verifies the
decided shape rather than choosing one. Build the converted fixture from
the archived tooling task and confirm that a thin checkout really does
carry no pack files under `.agents/` or `scripts/`, so the thin variant's
statement is true rather than merely convenient.

## 2. Confirm D3's resolved answer against a fixture

Already settled by code reading during planning review: a bare
unambiguous basename of a removed file is classified removed
(`thin-resweep.py:1231`), so dropping the `scripts/` prefix is not a fix
and the comment names the block's **owner** instead. Re-confirm against a
fixture whose `.gitignore` carries the chosen wording — the classifier
was read, not run, and the run is what counts.

## 3. Generator change (D1, as revised by D6)

**Superseded in shape, 2026-08-11 — see design D6.** There is no
resolution clause and no anchored per-target replacement. A third
`RewriteProfile` (`THIN_PROFILE`) supplies the thin wording, and the
installer applies it at `payload_source_bytes()` in
`installer/fileops.py`, the one point where a target's content is
decided. The bullets below are the original plan, kept because the
reasoning about *why token-level substitution fails* is still what rules
that approach out; the anchor/clause-map mechanics they prescribe are
not what was built.

### Original plan (mechanics superseded)

- Add the resolution clause to `RewriteProfile` in
  `installer/references.py` and replace the **whole authored clause** per
  profile — not the path token inside it. See design D1: the repo-native
  templates are the input to both payload builders
  (`generate-plugin.py:440`, `machinestage.py:169`), so token-level
  substitution gives the machine payload duplicate `~/.agents/bin` arms
  and the plugin an arm it cannot satisfy.
- Author the repo-native (three-arm) form in the template, since that is
  the form that must survive unrewritten.
- Anchor the replacement on a unique sentence and fail when the anchor is
  missing or matches more than once, the way
  `CLAUDE_COMMAND_BODY_INSERTIONS` already does with
  `body.count(anchor) != 1`. A silent no-op reintroduces the bug.
- Key the clause map by target and enforce exactly-one only for targets
  in it. `rewrite_text()` runs over every payload text file
  (`machinestage.py:140`, `generate-plugin.py:419`), so an unconditional
  assertion rejects unrelated files.
- Thread the target key through the plugin caller:
  `rewrite_markdown(text)` at `generate-plugin.py:307` takes text alone,
  while the machine caller already passes `key=target`. Without this the
  clause map cannot be consulted on the plugin path at all.
- Unit test each profile's output, and mutation-test: disable the
  replacement and confirm the tests fail. A test that passes with the
  change reverted proves nothing — that check caught two defective tests
  in the sibling task.

## 4. Copilot managed block (D2)

Edit `templates/.github/copilot-instructions.sd-ai-command-pack.md`,
strictly between the `SD-AI-COMMAND-PACK:COPILOT-GUIDANCE:START` and
`:END` markers. All **seven** hits — an earlier revision of this plan
enumerated six and lost the third glob, which alone would have made
`packDefects: 0` unreachable:

| Line | Citation | Kind |
|---|---|---|
| 8, 35, 89 | `docs/SD_AI_COMMAND_PACK.md` | path |
| 87 | `scripts/sd-ai-command-pack-install-audit.py` | path |
| 7 | `.agents/skills/sd-*/SKILL.md` | glob |
| 17 | `**/skills/sd-*/**` | glob |
| 32 | `scripts/sd-ai-command-pack-*` | glob |

Count the hits from the scanner output, not from this table, before
declaring the file done.

**Superseded 2026-08-11 — see design D6.** The file is not edited at
all. `normalize_managed_block_template()` takes the same `is_thin` flag
as the rest of the payload and rewrites the block through
`THIN_PROFILE`, so there is one authored template and two emissions.
That removes the second variant this step called for, and with it the
risk it was guarding against: the fat emission is byte-identical because
`is_thin` false is the untouched code path, not because a reviewer
compared two hand-maintained copies.

Both emissions still need a test — a fat install emits all three globs,
a thin install emits none.

## 5. KB script provenance comment (D3)

`templates/scripts/sd-ai-command-pack-update-spec-kb.py:442` only. Leave
line 1116 and `BIN_LITERAL_ALLOWLIST` alone — see design D3.

## 6. PR template (D4)

**No edit needed, 2026-08-11 — see design D6.** Lines 7 and 14 are
ordinary path citations (`docs/SD_AI_COMMAND_PACK.md` and
`` `bash scripts/sd-ai-command-pack-full-check.sh` ``), so the profile
rewrites them like any other text. Verified by running the rewrite over
the template: both lines change, nothing else does.

The force-preserved behaviour is unchanged and still bounds the claim —
an existing consumer's own copy is never overwritten by a refresh
(`installer/fileops.py:366`). A *conversion* does repoint it, because
the file is in `plan.keep`.

## 7. Version and changelog — before release-prep, not after

`manifest.json` bump plus a matching top `CHANGELOG.md` heading. This
comes first: `make release-prep` validates both in the same run
(`prepare-release.py:307`, `:337`), so running it before the bump fails
on a prerequisite this plan already knows about. An earlier revision of
this plan had these two steps the other way round.

## 8. Propagate and gate

```bash
make sync && make generate && make release-prep
make test > /tmp/repoint-test.log 2>&1; echo "MAKE-TEST-EXIT=$?" >> /tmp/repoint-test.log
```

No manual mirror edits. `MAKE-TEST-EXIT=0`, and `make check` green.

## 9. Acceptance measurement

Four runs, and all four are required. Three of them are the ones the PRD
warns get skipped because the diff looks complete:

1. Refreshed **and** KB-refreshed consumer: `packDefects: 0`.
2. Refreshed but **not** KB-refreshed: still reports the `obsidian-kb`
   hit. If this comes back clean, the extra conversion step is ceremonial
   and the PRD's central claim is wrong — stop and re-plan.
3. Fresh install into an empty target: writes the corrected PR template.
4. Refresh of an existing consumer: PR template reported `PRESERVED`, its
   stale line a `blocker`, for all eight.

Both a thin and a fat checkout are exercised, and the assertion is
**per surface**: each of the seven resolves its cited path in each
layout, checked one at a time against the step-0 per-surface baseline.
PRD acceptance criteria 1 and 2 say "all seven", so a run that reports
only an aggregate does not close them. Breaking fat to fix thin trades
one outage for another, and fat is what all eight consumers run today.

Step 3's generator change gets its own assertion here. The original D1
failure mode (duplicate arms in the machine body, an unsatisfiable arm
in the plugin body) cannot occur under D6 — there are no arms, and the
payload builders are untouched. What replaces it is the pair D6 makes
load-bearing, and both are measured on a real converted fixture rather
than read off a diff:

- `install.py --check` on a *freshly converted* consumer reports
  `state: current`, not `invalid`;
- a subsequent refresh exits 0 and leaves the repointed text in place.

**Measured 2026-08-11** — both hold; before D6 they were `invalid` and
rc 2. Per-surface counts are in design D6's verification table: 17 fat
hits, 0 thin, across all seven surfaces.

## 10. Checklist steps for children 3–5

Add two consumer-side steps to the conversion PR checklist, together:
repoint the consumer's own PR template, and run the KB refresh. Both are
invisible in a pack diff that otherwise looks finished, which is why they
go in writing rather than in someone's memory.

**Done 2026-08-11.** They landed as steps 2b and 2c of requirement 1's
per-consumer sequence in `08-10-thin-canary-conversion/prd.md`, plus a
matching acceptance criterion. Child 3 is the only place the sequence is
written out — children 4 and 5 both defer to it by reference
(`08-10-thin-post-canary-conversion/prd.md:18`,
`08-10-thin-final-conversion-gate-retirement/prd.md:17`) — so one edit
covers all three cohorts.

Why each survives the conversion, measured rather than assumed:

| Surface | Partition row | Conversion disposition | Cleared by |
|---|---|---|---|
| `.gitignore` | none | `block_strip` | re-running the KB script |
| `.github/PULL_REQUEST_TEMPLATE.md` | `repo-native` | `keep` | the rewrite, for matched forms only |

`plan.keep` is what child 2b's install-time rewrite walks, and
`classify_target` puts a row-less target in `block_strip`
(`installer/conversion.py:178`), so `.gitignore` is outside the rewrite
entirely. That is the same fact step 9's acceptance run 2 predicts from
the other direction — a refreshed but not KB-refreshed consumer still
reports the `obsidian-kb` hit.

## Rollback

Every edit is a text change under `templates/` and `.github/`, plus
generated mirrors. `git revert` of the merge commit restores the previous
shipped payload; the version bump reverts with it. No consumer state
changes until a consumer refreshes, so a revert before any consumer
refresh is complete.
