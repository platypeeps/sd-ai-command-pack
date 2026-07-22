# Design: Add sd-github-review to fleet

## Overview

Extend the schema-version-4 fleet inventory with one consumer while preserving
the existing rollout policy. The source manifest remains authoritative; tests,
operator documentation, and the generated candidate ledger move with it.

## Fleet Contract

Add this consumer to `docs/fleet/consumers.json`:

```json
{
  "name": "sd-github-review",
  "github": "platypeeps/sd-github-review",
  "pathHint": "~/repos/platypeeps/sd-github-review",
  "platforms": ["claude", "gemini", "github", "opencode"],
  "rolloutPriority": 70,
  "candidateTimeoutSeconds": 180,
  "candidatePrepare": [["npm", "ci"]],
  "candidateChecks": [
    ["npm", "test"],
    ["npm", "run", "check"],
    ["npm", "run", "validate:metadata"]
  ]
}
```

Append `sd-github-review` to the bounded-parallel `post-canary` cohort. This
keeps the existing three sequential canaries unchanged and preserves
`anomaly-metric-creator` as the sole sequential final consumer.

## Candidate Data Flow

1. The source validator clones `platypeeps/sd-github-review` into a disposable
   directory.
2. It installs the working pack candidate and audits the four selected
   platforms.
3. `npm ci` installs the locked `yaml` development dependency inside the
   disposable clone. No active checkout is touched.
4. The validator runs the target repository's three read-only CI gates.
5. A filtered run proves the new consumer contract without replacing canonical
   evidence.
6. An all-consumer run writes the schema-version-2 candidate ledger with eight
   passing rows and the updated fleet digest.

## Source And Derived Files

- Source policy: `docs/fleet/consumers.json`
- Inventory regression: `tests/test_fleet_preflight.py`
- Operator contract: `docs/FLEET_ROLLOUT.md`
- Discoverability text, only where the fleet count/order is stated, including
  `README.md`
- Derived evidence: `docs/fleet/candidate-validation.json`

No installer, shared fleet-library, or consumer-repository behavior should
change unless validation exposes a genuine compatibility defect.

## Compatibility And Safety

- Keep the existing four-platform convention; do not add optional local
  platform surfaces.
- Use argv arrays already supported by schema version 4; do not introduce shell
  interpolation or a schema bump.
- Use the existing bounded 180-second timeout. The baseline target test suite
  finishes well below this limit.
- Treat `npm ci` as preparation because it mutates only the disposable clone's
  dependency tree. Candidate checks remain read-only.
- Preserve full-fleet continuation and atomic-ledger semantics. A filtered or
  failed run cannot certify the release.

## Rollback

Before merge, revert the manifest/test/doc changes and restore the prior
candidate ledger. After merge, use a normal revert and regenerate the ledger
against the restored seven-consumer manifest; never hand-edit digest fields.
