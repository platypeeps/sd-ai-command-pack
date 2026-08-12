# Implementation plan

## Order

Phase A is the canary and stops for review. Phase B is the remaining seven and
does not begin until the canary PR has been reviewed.

## Phase A — canary: `sd-github-review`

- [ ] A1. Re-measure: `sd-status fleet --json --no-network`; confirm
      `sd-github-review` is `available`, `clean`, `synchronized`, and its
      `.gito/config.toml` still `superseded`.
- [ ] A2. Record the pre-conversion digest of its `.prism/rules.json`
      (`shasum -a 256`) in `prd.md`.
- [ ] A3. Branch from its default branch:
      `git -C <path> switch -c chore/sd-ai-command-pack-0.71.1`.
- [ ] A4. `python3 install.py <path> --force` from this checkout. Retain the
      report.
- [ ] A5. Verify: `.prism/rules.json` digest unchanged from A2; the report
      shows `refreshed .gito/config.toml`; the install mode is still fat;
      `grep -c '".trellis/\*\*"' <path>/.gito/config.toml` is 0.
- [ ] A6. Commit exactly the installer's paths, push, open the PR against that
      consumer's default branch with the measurement in its body.
- [ ] A7. Stop. Report the PR and wait for review.

Validation for Phase A:

```bash
python3 install.py <path> --status --audit --json
git -C <path> status --porcelain
shasum -a 256 <path>/.prism/rules.json
grep -c '"\.trellis/\*\*"' <path>/.gito/config.toml
```

## Phase B — the remaining seven

Registry order, one consumer at a time, each through A1–A6 — A2's
`.prism/rules.json` digest is recorded for **every** consumer before its own
install, not only for the canary, since C3 compares all six locally owned files
against a pre-install digest and a digest taken afterwards proves nothing.

A stashed consumer also gets two extra steps around the push: record its
original branch alongside the stash ref, and `git switch` back to that branch
before restoring, so the stash does not land on the conversion branch it was
never taken from.

Additions per consumer:

- [ ] B1. `rwbp-coordinator` — clean; no stash step.
- [ ] B2. `hoa-manager` — clean; no stash step.
- [ ] B3. `rwbp-website` — clean; no stash step.
- [ ] B4. `se-ai-command-pack` — clean; no stash step.
- [ ] B5. `loadsmith` — dirty. Stash first, record the ref in `prd.md`, restore
      after the push. Its `.prism/rules.json` is `superseded`, not local, so it
      is expected to show a second `refreshed` line; that is inside R1, not a
      violation of R2.
- [ ] B6. `anomaly-metric-creator` — dirty. Stash, record, restore.
- [ ] B7. `mezmo_benchmark` — dirty and on `cr/triage-grading-channel` with no
      upstream. Stash, record, resolve its default branch from the consumer
      itself, branch from that, restore after the push.

## Closing

- [ ] C1. Re-run `sd-status fleet --json --no-network`; record the resulting
      provider-config table in `prd.md`.
- [ ] C2. Enumerate every stash created, with ref and restore outcome.
- [ ] C3. Byte-compare the six locally owned `.prism/rules.json` files against
      their A2-style pre-digests and write down, for each owner, the shipped
      delta it is missing.
- [ ] C4. Note in `prd.md` that the eight consumer PRs are the gate: this task
      does not merge them, so `superseded` stays non-zero in the registry until
      the consumers merge on their own schedule.

## Rollback points

- Before A6: discard the consumer branch; nothing was pushed.
- After A6, before merge: close the PR, delete the branch.
- Any stash restore that conflicts: stop that consumer, leave the stash in
  place, report its ref.
