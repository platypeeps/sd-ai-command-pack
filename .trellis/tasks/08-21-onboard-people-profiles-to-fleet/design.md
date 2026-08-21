# Design — onboard people-profiles to the fleet

## The ordering constraint that shapes everything

`docs/FLEET_ROLLOUT.md` fixes five steps: ship, refresh, rewrite, resweep,
convert. Measuring the tooling adds a sixth constraint the document does not
state, and it inverts the naive plan:

```
$ .venv/bin/python scripts/sd-ai-command-pack-thin-resweep.py people-profiles \
      --repo ~/repos/platypeeps/people-profiles
error: people-profiles is not a registered consumer; known consumers: …
```

`--repo` redirects *which tree* is scanned; it does not make an unregistered
name resolvable. So **registration precedes the resweep**, which precedes the
conversion. Registering only after the repository is thin is impossible.

The registry accommodates this directly. `sd_ai_command_pack_fleet_lib.py:25`
declares `FLEET_CONSUMER_MODES = ("fat", "thin")` with
`DEFAULT_FLEET_CONSUMER_MODE = "fat"`, so a consumer can be registered in the
shape it is actually in and converted afterwards. The conversion closes the
loop itself: `installer/thin.py:1042` calls `flip_registry_mode(root, consumer)`,
whose docstring names the failure it exists to prevent — "consumer converted,
registry did not", the pin-vs-mode skew.

Final order:

```
refresh (consumer)  →  rewrite citations (consumer)  →  register as fat (pack)
    →  resweep → clear verdict  →  convert (flips repo AND registry to thin)
    →  ledger regen (pack)  →  ruleset alignment  →  verify
```

## Boundaries

Two repositories change, and the split is not negotiable.

**people-profiles** receives the refreshed payload, the three citation
rewrites, and the thin conversion's deletions. **sd-ai-command-pack** receives
the registry row, the cohort assignment, the mode flip, and the regenerated
candidate ledger. The conversion command is the one action that writes to both:
it is run from the pack checkout against the consumer path, deleting
machine-scope files in the consumer while rewriting `docs/fleet/consumers.json`
in the pack. Both working trees must be clean when it runs, and both sets of
changes get committed separately afterwards.

GitHub ruleset state is a third surface, mutated through the API rather than
through either repository, with its rollback record already committed at
`.trellis/audit/copilot-ruleset-rollback-2026-08-21/`.

## The refresh

Measured against the current source:

```
installedVersion 0.55.0 → sourceVersion 0.71.40    state: refresh-required
changeCount 148   created 45   updated 86   refreshed 1   unchanged 71   would-retire 16
platforms active/installed: claude, gemini, github, opencode
```

The 16 retirements are the reason this is not a pure addition: surfaces the
pack has since withdrawn are still committed in that repository, and a refresh
that leaves them behind produces exactly the stale-forwarder residue that other
consumers had to clean up later. The refresh must be allowed to retire them.

`platforms` matters for the registry row: the active set is identical to all
eight existing consumers, so no new platform dimension enters the fleet.

## The rewrite is three prose citations, not a guard migration

The documented step 3 exists because consumers' executable guards name
`scripts/sd-ai-command-pack-*` paths that conversion deletes. This repository
has no such guard. Classifying every file containing such a reference against
the install receipt:

| class | files | disposition |
| --- | --- | --- |
| pack-owned | 61 | replaced by the refresh; current payload already uses the resolver |
| repo-authored | 3 | rewritten by hand, one reference each |

`.github/workflows/ci.yml` contains no reference to the pack, `~/.agents/bin`,
or `install.py`. The sole path assertion in `tests/test_installer.py` names one
of the repository's own skills. Nothing executable is coupled.

The three are `.trellis/spec/backend/quality-guidelines.md`,
`.trellis/spec/frontend/hook-guidelines.md`, and an archived task's
`research/review-risk-disposition.md`. They must cite
`.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` **as a plain
path**: FLEET_ROLLOUT records that a citation the tokenizer cannot see does not
count, measured on rwbp-coordinator where a hand-escaped regex left the file
blocked until the assertion became a literal `endsWith`.

Sequencing within the consumer: the refresh must land before the rewrite,
because the kept resolver path does not exist in the repository at 0.55.0 —
`.sd-ai-command-pack/bin/` is absent today. A rewrite that lands first cites a
file that is not there, which is the trap FLEET_ROLLOUT names explicitly.

## The untracked `.bak` obstacle

The resweep requires a clean worktree, because "converting a dirty tree mixes
the conversion's deletions with the consumer's uncommitted work." The
repository carries five untracked leftovers:

```
scripts/sd-ai-command-pack-housekeeping.sh.bak
scripts/sd-ai-command-pack-housekeeping-result.py.bak
scripts/sd-ai-command-pack-review-preflight.mjs.bak
scripts/sd-ai-command-pack-pr-eligibility.py.bak
scripts/sd-ai-command-pack-review-scope.sh.bak
```

Every one is named after a pack script, and `install.py --backup` is documented
as saving "a `.bak` copy next to each overwritten or deleted file" — so these
are the residue of an earlier `--force --backup` refresh, not hand edits. That
identification matters twice. It tells us what they are, and it warns that the
refresh in Step 1 can manufacture up to 86 more of them if it passes `--backup`,
re-dirtying the tree immediately before the step that requires it clean. The
refresh therefore runs without `--backup`; git history is the backup.

They remain untracked, so no commit removes them, and they remain somebody
else's files. The design decision is to **surface and ask** rather than delete.
If they may go, deleting them is sufficient; if they must be kept, moving them
outside the repository also satisfies the resweep.

## Registry row

Priority 80 is unoccupied — the existing ladder runs 10, 20, 30, 40, 50, 60,
70, 90 — and sits naturally before `anomaly-metric-creator`.

```json
{
  "name": "people-profiles",
  "github": "platypeeps/people-profiles",
  "pathHint": "~/repos/platypeeps/people-profiles",
  "platforms": ["claude", "gemini", "github", "opencode"],
  "rolloutPriority": 80,
  "candidateTimeoutSeconds": 180,
  "candidateChecks": [
    ["python3", "scripts/validate_repo.py"],
    ["python3", "-m", "unittest", "discover", "-s", "tests"]
  ],
  "mode": "fat"
}
```

`candidateChecks` mirrors the repository's own `.sd-ai-command-pack/check.json`,
which declares both `repository-validation` (`python3 scripts/validate_repo.py`)
and `unit-tests`. Both are carried: dropping the unit tests would let a
candidate pass validation while its own suite is broken. Both targets are
repo-authored and survive conversion, so they stay runnable after the repo goes
thin — a machine-scope script would not.

`candidateChecks` is also the one candidate field the registry parser requires
to be non-empty (`_parse_candidate_commands(..., allow_empty=False)`), whereas
`candidatePrepare` is optional (`allow_empty=True`) and this consumer needs no
prepare step.

**Cohort: `final`.** Not `canary`. A consumer being onboarded has never been
driven by a refresh lane, and `canary` is sequential-first: a failure there
stalls the cohorts behind it. `final` is also sequential, runs last, and
already holds `anomaly-metric-creator`, so a failure costs nothing downstream.
It can be promoted once it has survived a real refresh.

## Rollback

Each stage reverses independently, which is why they are separate commits:

| stage | reversal |
| --- | --- |
| refresh | `git revert` in people-profiles |
| citation rewrite | `git revert` in people-profiles |
| registry row | remove the row and the cohort entry, regenerate the ledger |
| conversion | `install.py <target> --revert-thin --consumer people-profiles` restores the machine-scope payload and rewrites the receipts as a fat install |
| ruleset | `PUT` the snapshot's rules back from the committed audit record |

The conversion is the only stage with a purpose-built undo, and it is the only
one that deletes files, which is why it runs last among the repository changes.

## What could go wrong

- **The resweep returns `blocked`.** Most likely cause is residue no resolver
  reaches — glob patterns in prose, change-classifier fixture lists. These need
  rewriting or recorded acceptance; a resolver cannot rewrite a glob. This is a
  stop-and-fix, not a force-through: `--thin` will not accept a `blocked`
  verdict.
- **The refresh's 16 retirements break something repo-authored.** The repo's
  own tests and `validate_repo.py` are the check; they run before the PR opens.
- **The ledger goes stale mid-task.** The registry row and the mode flip each
  move the fleet manifest digest, so the ledger is regenerated twice — once
  after registration, once after conversion. The pre-push hook catches a miss.
