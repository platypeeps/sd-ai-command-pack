# Fleet Consumer Conversion: Running The Installer Against Another Repository

> [!important]
> **Stale as of 2026-09-01.**
> This page describes running `install.py <consumer>` from this checkout against
> another repository. Neither half survives: `install.py` was deleted on
> 2026-08-30 by step 3e (`43170716`, #610), and the fleet-of-consumer-checkouts
> model was dropped by decision R10-D6 -- `bin/sd-status` now opens with "There
> is no repo-path argument and no fleet walk (R10-D6)". `bin/sd_install.py` is
> machine-scope and never writes a tracked file in any repository. The
> `sd-status fleet` report, the `--thin`/`--resweep-verdict` cohort and the
> `.trellis/**` row in the error matrix all name surfaces that no longer exist.
>
> The text below is unedited. It is the record of what that machinery
> specified, not guidance for the repository as it stands. The triage that
> produced this notice is recorded under step 7 in
> `docs/work/2026-08-29-artifacts-as-product/implement.md`.

> When a task refreshes one or more registered fleet consumers by running
> `install.py <consumer>` from this checkout.

---

## Scenario: Converting Registered Consumers

### 1. Scope / Trigger

Trigger: any run that invokes `install.py` with a target outside this
repository — a fleet consumer refresh, a provider-config conversion, a version
rollout. Not triggered by the self-install, `make sync`, which is
`install.py . --force` (Makefile) and writes the same full payload — the
distinction is the target, this repository rather than somebody else's, not the
size of the write.

Consumer mutation needs explicit per-cohort user authorization. That
authorization is granted for a *stated* cohort, and the sections below exist
because the installer's blast radius is routinely much larger than the cohort
the user named.

### 2. Signatures

```bash
python3 install.py <consumer-path> --force            # writes the whole payload
python3 install.py <consumer-path> --force --dry-run  # same classification, no writes
python3 install.py <consumer-path> --status --audit --json
python3 install.py <consumer-path> --thin --resweep-verdict <path>   # separate cohort
```

Report verbs, one per path: `overwritten`, `updated`, `created`, `retired`,
`refreshed` (a superseded provider config), `preserved` (a locally owned file),
`unchanged`, `skipped` (adapter anchor absent).

### 3. Contracts

`--force` is **not** a targeted write. It refreshes every payload path for the
target's detected adapters, so a consumer several versions behind receives a
full version upgrade whichever single file motivated the run.

> Measure the blast radius with `--force --dry-run` and count the report's
> verbs *before* accepting that an authorized cohort can be delivered by the
> installer. A cohort named after one file can still be 80+ written paths.

`preserved` is the mechanism that protects a locally owned file — the installer
classifies it, the calling task does not avoid it. Verification is therefore a
digest comparison recorded **before** the install and repeated after, per
consumer. A digest taken afterwards proves nothing.

Never hand-edit a consumer's provider config to reach the same end state as
`refreshed`. The classification is computed against the shipped digest history;
a hand-written file has no lineage in it and the detector reports it `local`
from then on, permanently exempting it from future refreshes.

`--thin` is a different cohort and cannot be reached accidentally: it requires
`--resweep-verdict`. An ordinary forced install always leaves a fat install fat.

### 4. Validation & Error Matrix

| Condition | Required behavior |
|---|---|
| Cohort authorized by name, dry run shows a version upgrade riding along | Stop and settle scope with the user; the authorization covered the named cohort |
| Locally owned file's digest changed across the install | Abort before committing; this is an R2-class violation, not a diff to review |
| `".trellis/**"` still present in a converted `.gito/config.toml` | Abort before committing |
| Installed version after the run is not the pack version | Abort before committing |
| Consumer tree dirty | Stash on the consumer's **current** branch and record the ref before anything else, or skip the consumer |
| Consumer on a feature branch with no upstream | Resolve its default branch from the consumer (`refs/remotes/origin/HEAD`), never assume `main` is checked out |

Gate these in the conversion script itself with `set -e` and explicit
`exit 1` checks, so a failure stops before the commit rather than producing a
pull request somebody has to read to discover the problem.

### 5. Good/Base/Bad Cases

- **Good:** dry-run every consumer first, convert one canary alone, read its
  real diff, then repeat. The canary is what turns an unreviewable fan-out into
  a reviewed pattern.
- **Base:** a clean synchronized consumer — branch from its default, install,
  commit exactly what the installer wrote, push, open a PR in that repository.
  The pack never pushes to a consumer's default branch and never merges there.
- **Bad:** converting every consumer in one sweep because the cohort was
  authorized, when the dry run would have shown each conversion is also a
  seven-minor-version upgrade.

### 6. Tests Required

There is no unit test for a cross-repository conversion; the evidence is the
recorded measurement. Each conversion records, in the owning task:

- the pre-install digest of every locally owned file it must not change, and
  the post-install digest of the same file;
- the report's verb counts and the resulting `M/D/A` path counts;
- the pull request URL in the consumer's own repository;
- every stash ref created, its original branch, and its restore outcome.

### 7. Wrong vs Correct

#### Wrong

```bash
git -C "$P" stash push -u -m "..."     # stashed while already on the new branch
git -C "$P" switch -c chore/refresh
python3 install.py "$P" --force
git -C "$P" commit -am refresh && git -C "$P" push
git -C "$P" stash pop                  # lands someone else's work on the conversion branch
```

#### Correct

```bash
ORIG=$(git -C "$P" symbolic-ref --quiet --short HEAD)
git -C "$P" stash push -u -m "..."          # on the branch the work belongs to
DEFAULT=$(git -C "$P" symbolic-ref --quiet --short refs/remotes/origin/HEAD | sed 's|^origin/||')
git -C "$P" switch "$DEFAULT" && git -C "$P" switch -c chore/refresh
python3 install.py "$P" --force
# ... verify digests, commit, push, open the PR ...
git -C "$P" switch "$ORIG" && git -C "$P" stash pop
```

---

## Common Mistake: Reading The Post-Conversion Fleet Count As Incomplete

**Symptom**: after converting every consumer, `sd-status fleet` still reports
some targets `superseded`, and the run looks half-finished.

**Cause**: the detector reads each consumer's **checked-out working tree**. A
consumer switched back to its original branch — which is exactly what restoring
a stash requires — shows its pre-conversion file, even though the conversion is
committed and pushed on another branch.

**Fix**: count open pull requests, not detector states, while conversions are in
review. The registry-level count only reaches zero after the consumers merge,
which is a post-archive handoff and never an acceptance criterion of the
converting task.

**Prevention**: when a task's success measure lives in repositories it cannot
merge into, write the measure down as a handoff before implementation starts.
