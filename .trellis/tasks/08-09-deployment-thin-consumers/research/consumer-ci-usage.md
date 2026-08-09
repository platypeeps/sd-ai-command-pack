# Research: what consumer CI actually does with the vendored pack

Date: 2026-08-09. Sources: local checkouts of two of the eight fleet
consumers (`rwbp-coordinator`, `rwbp-website`), both with
`.github/workflows/ci.yml` referencing the pack.

## Finding: consumer CI syntax-checks the payload; it executes nothing

`rwbp-coordinator` `ci.yml` (the only pack references in the file,
lines ~110-121):

```yaml
for script in \
  scripts/classify-ci-changes.sh \
  scripts/sd-ai-command-pack-full-check.sh \
  scripts/sd-ai-command-pack-housekeeping.sh \
  scripts/sd-ai-command-pack-review-local.sh \
  scripts/sd-ai-command-pack-review-scope.sh
do
  bash -n "$script"
done
node --check scripts/sd-ai-command-pack-review-preflight.mjs
python3 -m json.tool .prism/rules.json > /dev/null
python3 -m json.tool .prism/rules.schema.json > /dev/null
```

- `bash -n` and `node --check` are syntax lints of vendored pack
  code — validation the pack's own repo already performs before
  release. No pack script is functionally executed in consumer CI.
- The `.prism` JSON checks validate vendored review-provider config —
  same category.
- `rwbp-website` shows the same pattern (pack references confined to
  `ci.yml` lint steps).

## Implication for the requirement set

PRD requirement 3 assumed a "consumer-repo-required because CI
executes it" category needing a pinned-fetch bootstrap. For the two
consumers inspected, that category is empty: the CI steps exist only
*because* the payload is vendored (lint what you carry). Under the
thin model those steps are deleted along with the payload, and no
bootstrap may be needed at all — the pin + repo config could be the
entire consumer footprint.

## Full-fleet sweep (GitHub API, all 8 consumers, 2026-08-09)

| Consumer | Pack references in workflows |
|----------|------------------------------|
| rwbp-coordinator | `bash -n` / `node --check` lint only |
| rwbp-website | lint only |
| loadsmith | shellcheck-lane include/exclude globs only |
| hoa-manager | `bash -n` / `node --check` lint only |
| mezmo_benchmark | `bash -n` lint + change-classification regex naming pack paths (CI routing, no execution) |
| se-ai-command-pack | none |
| sd-github-review | none |
| anomaly-metric-creator | lint + **one functional execution** + sync automation |

The single functional execution in the fleet
(`anomaly-metric-creator` `ci.yml:293`):

```yaml
uv run --python 3.14 --no-project python scripts/sd-ai-command-pack-pr-body-scope.py
```

`anomaly-metric-creator` also carries
`sd-ai-command-pack-sync.yml`, which clones the pack repo, runs
`install.py --force`, and opens a refresh PR — the vendoring sync
automation itself, which the thin model deletes rather than migrates.

## Conclusion for design

The consumer bootstrap requirement collapses from "a mechanism every
consumer needs" to "one script, one consumer": `pr-body-scope.py` in
`anomaly-metric-creator`. Design options, smallest first: (a) vendor
just that one script there as repo-owned config, (b) pinned-fetch of
that single file with digest check, (c) move PR-body scope validation
out of consumer CI entirely. Every other consumer's footprint under
the thin model is the version pin plus repo config; their CI pack
steps (lint of vendored code) are deleted with the payload.

## Residual verification (cheap, before migration child ships)

- Consumer-side non-CI automation (git hooks, Make targets, docs
  instructing humans to run vendored scripts) — grep at migration
  time per consumer; not a design blocker.
