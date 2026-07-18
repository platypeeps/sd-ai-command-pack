# SD status command design

## Architecture

Add `templates/scripts/sd-ai-command-pack-status.py` as the shipped source of
truth and keep `scripts/sd-ai-command-pack-status.py` as its byte-identical
dogfood mirror. The script uses only the Python standard library, invokes Git
and optional `gh` through direct argv, reads JSON structurally, and never runs a
mutating command.

Add `sd-status` to `COMMAND_REGISTRY` in the orientation/knowledge family. The
canonical skill at `templates/.agents/skills/sd-status/SKILL.md` owns workflow
instructions; `templates/.commands/sd-status.md` is the neutral adapter body.
The existing generator creates all platform adapters, skill fanout, manifest
rows, and the help catalog. The status script itself is a static shared
manifest entry.

## CLI Contract

```text
python3 scripts/sd-ai-command-pack-status.py [fleet] [options]
```

Public options:

- no positional mode: report the current repository
- `fleet`: report every repository in the resolved source-owned fleet manifest
- `--repo PATH`: inspect another local repository in local mode
- `--fleet-manifest PATH`: override fleet manifest discovery for this run
- `--json`: emit schema-versioned JSON only
- `--no-network`: skip optional GitHub reads and label them unavailable

Internal housekeeping options:

- `--expect-clean`
- `--refs-refreshed`
- `--remote NAME`
- `--default-branch NAME`
- `--source-branch NAME`
- `--keep-remote-branch`
- `--dry-run`
- repeated `--prior-anomaly TEXT`

Exit `0` means a requested report was collected. Ordinary report mode does not
turn a dirty tree or stale pack into command failure. Exit `1` means collection
could not inspect the requested repository or strict housekeeping expectations
failed. Argparse retains exit `2` for invalid usage.

## Local Data Model

Use normalized dictionaries for Git, versions, GitHub, Trellis, and final
report state, with an immutable command-result boundary for subprocesses. JSON
schema version 1 contains:

```json
{
  "schemaVersion": 1,
  "mode": "local",
  "repository": {"path": "...", "name": "...", "github": "owner/repo"},
  "git": {
    "branch": "main",
    "detached": false,
    "workingTree": {"state": "clean", "staged": 0, "unstaged": 0, "untracked": 0},
    "upstream": "origin/main",
    "ahead": 0,
    "behind": 0,
    "refsFreshness": "cached"
  },
  "versions": {"sdAiCommandPack": "0.19.0", "trellis": "..."},
  "github": {"status": "available", "currentPr": null, "openPrs": [], "openIssues": []},
  "trellis": {"activeTask": null, "inProgress": [], "planned": []},
  "anomalies": [],
  "nextSteps": []
}
```

Use porcelain-v2 Git status for stable staged/unstaged/untracked counts and its
branch metadata for upstream divergence; missing upstream is represented
explicitly. Compare default local/remote refs directly for strict housekeeping
verification. Read pack/Trellis versions from their
local metadata files. Resolve the active Trellis task through the repo-owned
task command when available, then read task JSON; scan direct task directories
for bounded in-progress and planning candidates.

GitHub reads are best effort and scoped to the resolved repository slug. Bound
open PR/issue arrays to the first five in human output while retaining up to 100
in JSON. A relevant PR is the source-branch PR supplied by housekeeping, or the
current feature branch PR in standalone mode. Include state, merge timestamp,
URL, check summary when available, and submitted review count.

## Human Output

Local mode prints:

1. `SD status: healthy|attention` with repository and freshness; an invalid
   repository fails before rendering a report.
2. `Expected clean state` for Git facts, preserving housekeeping familiarity.
3. `Delivery` for versions and current/relevant PR.
4. `Inventory` for open PRs/issues and Trellis work.
5. `Anomalies`, always present.
6. `Next Steps`, always present and numbered.

Ordinary status classifies dirty/diverged/task state as attention and next-step
evidence, not anomalies. Under `--expect-clean`, default-branch, clean-tree,
sync, branch inventory, source-branch cleanup, and prior housekeeping failures
become anomalies and determine exit status. Dry-run labels final verification
as a preview instead of asserting cleanup occurred.

## Fleet Mode

Ship the shared fleet parser beside the status script. Fleet mode validates the
canonical manifest and inspects each resolved checkout without invoking
installed copies. Resolve configuration in this order:

1. public `--fleet-manifest PATH`
2. `SD_AI_COMMAND_PACK_FLEET_MANIFEST`
3. the machine profile selected by `SD_AI_COMMAND_PACK_FLEET_CONFIG`,
   `$XDG_CONFIG_HOME/sd-ai-command-pack/config.json`, or
   `~/.config/sd-ai-command-pack/config.json`
4. `docs/fleet/consumers.json` in the current canonical pack source checkout

The profile schema is deliberately small: `schemaVersion: 1`, required
`packSource`, optional `fleetManifest`, and optional string-valued
`pathOverrides` keyed by fleet consumer name. Omitted or relative
`fleetManifest` resolves under `packSource`; relative `packSource` and checkout
overrides resolve against the profile directory. Manifest paths supplied
through CLI/environment resolve from the current directory. The profile never
carries rollout policy or commands.

The target pack version comes from the canonical `sd-ai-command-pack` manifest
associated with the resolved fleet manifest or profile source. Another pack
identity, malformed JSON, missing helper, or missing source version produces a
controlled error without traceback. Profile path overrides take precedence over
checked-in `pathHint` values only for local checkout lookup.

Human output begins with
aggregate totals and then prints one stable row per consumer in rollout order:

```text
P10 rwbp-coordinator  clean  main  cached:sync  pack 0.19.0  PRs 0  tasks 0/2
```

Missing clones and unavailable data retain their row. Attention detail and
numbered next steps follow the table. Fleet mode does not run per-repo CI or
refresh commands.

## Housekeeping Delegation

The Bash housekeeping script continues to own fetch, merge, switch, pull, and
branch deletion. It prints `Tasks performed`, then invokes the sibling
toolchain helper to run the sibling status script with strict internal context.
Prior mutation anomalies are passed as repeated argv values. The collector
owns final Git checks, GitHub/Trellis inventory, anomalies, and next steps.

Remove the old housekeeping expected-state/inventory arrays and collector
functions so there is one implementation. If the status script/toolchain is
missing or cannot start, housekeeping prints a concise anomaly and exits
nonzero; it never silently falls back to stale duplicated logic.

## Compatibility And Release

This is a new shipped command and script, so bump the pack from `0.18.0` to
`0.19.0`, add a changelog entry, regenerate command surfaces and root mirrors,
refresh docs/KB/provenance, and regenerate the payload-bound candidate ledger.
There is no legacy command alias. `install.py --configure-fleet` is opt-in,
honors `--dry-run`, preserves existing path overrides, and cannot be combined
with inspection or removal modes. Status never writes this profile.

## Security And Privacy

Never print environment variables, auth tokens, remote URLs containing
credentials, or raw command diagnostics that may contain secrets. Normalize
GitHub identity to an owner/repository slug. Bound user-controlled GitHub/task
titles and replace control characters before rendering.

## Rejected Alternatives

- Keep status inside the skill as ad hoc commands: output and housekeeping
  behavior would drift by platform and agent.
- Make status fetch by default: violates the read-only promise and makes a
  quick local report depend on network mutation.
- Keep housekeeping's final collector as a fallback: preserves two policy
  authorities and defeats the requested consolidation.
- Make fleet mode a separate command: duplicates reporting logic and weakens
  the simple local-versus-fleet interface.
- Move `docs/fleet/consumers.json` into the home directory: that would make
  release evidence and rollout policy machine-specific and non-reproducible.
