# Pack-driven prism reviews ignore .prism/rules.json, and turning them on would break severity in ten repos

## Goal

Make pack-driven prism reviews honour the repository's own `.prism/rules.json`,
without that change silently replacing per-finding severity judgement with a
category lookup across the whole consumer fleet.

Three defects, and they must land in one order. The pack never passes `--rules`,
so every consumer's focus categories and required checks have been ignored by
every pack-driven review since the prism adapter shipped. Ten of eleven
consumers also ship a `severityOverrides` block that prism applies *after* the
model answers, rewriting each finding's severity from its category. Fixing the
first defect alone activates the second in ten repositories at once. And the
schema shipped beside those files marks the offending key **required**, so
removing it is itself a pack change before it is a fleet change.

## Background

### What the enumeration found

Every repository with a `.sd-ai-command-pack/` install also ships
`.prism/rules.json`. Nine of the eleven ship no `review.json`, so they run the
pack's `_default_config()` providers — builtin `prism`, 300s timeout, argv built
by `_expand_argv` in `plugins/sd/bin/sd-ai-command-pack-review-local.py:1420`.
That builder emits `prism review range|codebase … --format json` and nothing
else; `grep -c rules` over the file returns `0`.

```
consumer                                   rules.json  severityOverrides
mezmo/mezmo_benchmark                      091fba6f    YES
personal/anomaly-metric-creator            4bc4589b    YES
platypeeps/anomaly-metric-creator          4bc4589b    YES
platypeeps/hoa-manager                     5b19dd88    YES
platypeeps/loadsmith                       ceb3a092    YES
platypeeps/people-profiles                 ceb3a092    YES
platypeeps/sd-ai-command-pack              ceb3a092    YES
platypeeps/sd-github-review                b115de5c    no
platypeeps/se-ai-command-pack              9a6f02a5    YES
rwbp/rwbp-coordinator                      bb4e6d3a    YES
rwbp/rwbp-website                          ff2e12ce    YES
```

All ten `severityOverrides` blocks are byte-identical in content:

```json
{"bug":"high","correctness":"high","security":"high",
 "docs":"medium","maintainability":"medium","performance":"medium",
 "testing":"medium","style":"low"}
```

The eleventh, `sd-github-review`, had the block removed on 2026-08-24 under task
`08-09-review-gate-advisory-convergence` after it was shown to be destroying the
gate's only discrimination axis.

### The schema requires the key that has to go

`.prism/rules.schema.json` lists `severityOverrides` in its `required` array and
sets `additionalProperties: false`. Removing the key from a rules file makes
that file invalid against the schema shipped beside it. Three consequences, all
verified 2026-08-24:

- **`sd-github-review` is already invalid.** The block was removed there on
  2026-08-24 under `08-09-review-gate-advisory-convergence`; a required-key
  check reports `missing required keys: ['severityOverrides']`. Nothing
  validates the file at review time — the schema is editor-facing, and
  `pack.install-audit` checks that the file is installed, not what is in it —
  so the invalidity went unobserved. That is the same failure shape as the
  original defect: a file that describes the review and a review that does not
  read it.
- **The schema is pack-managed with `install: always`.** Editing it in a
  consumer is pointless; the next pack update overwrites it. The fix belongs in
  `templates/.prism/rules.schema.json`, which means the pack has to move before
  the fleet can.
- **`rules.json` is `install: if-not-exists`.** Consumer edits to it *are*
  durable. The fleet strip will not be undone by a pack update.

And `templates/.prism/rules.json` still carries the identical
`severityOverrides` block, so every repository installed from here on arrives
with the defect. That template is the copying source the hash pattern implied.

### Why severityOverrides has to go before `--rules` does

`ApplySeverityOverrides` (`internal/review/rules.go:82`, called from
`engine.go:166` and `engine.go:396`) runs client-side, after the model has
returned findings. It does not bias the model; it overwrites what the model
said. The consumer measurement that established this: on a 23-file branch the
`high` set was exactly `correctness 14 + security 3 + bug 2 = 19`, and the
advisory set exactly `docs 4 + maintainability 7 + testing 4 + style 3 = 18`.
Both sides exact, no finding anywhere off its category's mapped severity.

The pack's advisory gate reads the outstanding count, and `_is_advisory` has a
hard floor at `high`. A rules file that promotes every `correctness` finding to
`high` therefore guarantees a non-empty outstanding set on any review that finds
a correctness nit, regardless of whether the nit matters. Enabling `--rules`
against the current fleet would convert nine currently-unconfigured repositories
into that state in one release.

### Chunking is a separate, smaller gap

Stock prism sends the whole diff as a single request; `SplitIntoChunks` is
unreachable without a `chunkMaxBytes` config key that stock does not have.
`sd-github-review` works around this caller-side with a `prism-chunked` `argv`
provider (`scripts/prism-chunked-review.py`) declared in its own `review.json`.
That workaround is per-consumer and stays per-consumer for now: it is not a
correctness defect in the pack, and folding a chunking script into the payload
is a larger decision than this task should make. Recorded here so the scope
boundary is explicit rather than accidental.

## Requirements

1. **Strip `severityOverrides` from all ten consumers.** Not "advise against",
   not "document" — the block is removed from the file. `focus` and `required`
   stay as they are; they are what the consumer actually wants applied. The
   `description` field is amended where it references the removed key, because
   nine of the ten currently instruct the reader to "keep their category names
   in sync" with a block that will not exist.
1b. **The schema stops requiring it, and the template stops shipping it.**
   `templates/.prism/rules.schema.json` drops `severityOverrides` from
   `required`; `templates/.prism/rules.json` drops the block. Without the first,
   every stripped file is schema-invalid. Without the second, the next
   repository installed arrives carrying the defect. The schema is
   `install: always`, so it reaches consumers only through a pack release —
   which is why the pack now moves before the fleet, not after.
2. **The pack passes `--rules` to prism when the consumer's rules file exists.**
   The path resolves against the repository under review, not the pack install
   and not the process working directory. When no rules file exists the argv is
   unchanged from today, so consumers without one see no behaviour change.
3. **The pack refuses to pass a rules file containing `severityOverrides`.** A
   guard, not a convention — this defect returns the moment anyone copies an old
   rules file into a new repository, and the fleet has already demonstrated that
   copying is how these files propagate. The refusal must name the file and the
   key, and must not fail the review outright: a review that runs without rules
   is the current behaviour and is strictly better than no review.
4. **The behaviour is observable in the receipt.** A reader of a review receipt
   can tell whether rules were applied, and if they were not, why. Today nothing
   in the receipt distinguishes "rules applied" from "rules silently ignored",
   which is the reason this defect survived across eleven repositories.
5. **No consumer is left in a state where the gate is stricter than before
   without someone having chosen that.** *(Verified by criteria 1 and 7.)* Requirement 1 makes rules safe to
   enable; this requirement is the check on it — a consumer whose `required`
   checks now actually run may legitimately surface new findings, and that is
   acceptable, but the severity distribution must not shift by category lookup.

## Constraints

- `.sd-ai-command-pack/*.json` is the only consumer path `pack.install-audit`
  allowlists. Any per-consumer configuration this task adds lives there.
- `plugins/sd/bin/` and `plugins/sd/machine-payload/scripts/` are byte-identical
  mirrors. Both move together or the install audit fails.
- Ten of the eleven consumers are separate git repositories with their own
  review gates. The rules-file edit is a fleet change, not a single commit.
- `.prism/rules.schema.json` is `install: always` and `.prism/rules.json` is
  `install: if-not-exists` (`manifest.json`). The first cannot be fixed
  per-consumer; the second cannot be fixed centrally.
- The prism binary in use is stock (`~/repos/ai/prism`, patch retired
  2026-08-24). `--rules` is present in stock `addReviewFlags`, so requirement 2
  needs no upstream change.

## Acceptance Criteria

- [ ] **0. Every consumer's `rules.json` validates against the
      `rules.schema.json` installed beside it**, before and after the strip.
      Enumerated from the filesystem across all eleven. `sd-github-review`
      fails this today; it must pass when the task closes.
- [ ] **1. No consumer ships `severityOverrides`, and neither does the
      template.** `templates/.prism/rules.json` is checked alongside the
      consumers — it is the source they were copied from. Enumerated from the
      filesystem, not from a list in this document:
      `for f in ~/repos/*/*/.prism/rules.json; do python3 -c 'import json,sys;
      d=json.load(open(sys.argv[1])); print(sys.argv[1]) if "severityOverrides"
      in d else None' "$f"; done` prints nothing.
- [ ] **2. `--rules` reaches prism when the file exists.** A `_expand_argv` unit
      test asserts the flag and resolved path for `branch_delta`, `codebase` and
      `worktree` scopes, and asserts its absence when the file does not exist.
- [ ] **3. A rules file containing `severityOverrides` is refused, and the
      review still runs.** Test asserts argv carries no `--rules`, the review
      completes, and the reason is recorded.
- [ ] **4. The receipt says which of the three happened** — rules applied, no
      rules file, or rules refused — for a real review in a repository with a
      rules file present.
- [ ] **5. A live probe run proves the rules text reached the model.** A
      scratch rules file whose `required` block demands a finding keyed to a
      marker string planted in the diff, run with prism's response cache
      disabled: the finding appears with the rules file and does not appear
      without it. Not a category check — `prism internal/review/prompt.go:28`
      hardcodes the same eight categories every consumer lists under `focus`,
      so "all findings fall inside `focus`" is true of every prism run ever
      made and distinguishes nothing.
- [ ] **6. `plugins/sd/bin/` and `plugins/sd/machine-payload/scripts/` remain
      identical**, and `pack.install-audit` passes.
- [ ] **7. Severity is still a per-finding judgement, not a category lookup.**
      In a live review of a consumer running pack defaults, at least one
      category appears at two different severities. If every finding sits at its
      category's old mapped severity, either the fleet edit missed that
      repository or the overrides come from somewhere else.

## Out of scope

- Chunking. `sd-github-review`'s `prism-chunked` provider stays a per-consumer
  workaround; whether the pack should ship chunking is a separate decision.
- Follow-up **4b.5** (`_disposition_counts` never writes the advisory
  classification back to `receipt.findings[]`). Same task family, different
  defect, no ordering dependency on this one.
- Upstreaming the four stock-prism defects (`chunkMaxBytes`, `LoadRules`
  default, `MaxTokens` from config, request timeout). Tracked separately in
  `~/repos/ai/prism` branch `fix/chunking-rules-maxtokens`.

## Provenance

Both defects were found by running the shipped 0.71.47 gate over a real branch
in `platypeeps/sd-github-review`, not by re-reading the diff. Filed as
follow-ups 4b.5 and 4b.6 on `08-24-local-gate-advisory-severity` (branch
`followup/local-gate-advisory-severity-consumer-findings`, commit `17af0a43`).
The consumer-side write-up is `sd-github-review` task
`08-09-review-gate-advisory-convergence`, sections "Replay, 2026-08-24" and
"Second replay, 2026-08-24".
