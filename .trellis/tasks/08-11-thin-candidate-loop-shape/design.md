# Design: rescope the candidate validator loop to the thin shape

Child of `08-09-thin-migration`, contract C-F, second half. The first half —
making release-prep *reach* a changed validator — shipped as
`08-10-thin-candidate-loop-rescope` (0.69.0, PR #425). Because it did, every
claim below is measurable: an edit to
`scripts/sd-ai-command-pack-fleet-candidate-check.py` now moves
`validatorDigest` and makes release-prep run the validator.

## Evidence this design is built on

Measured against `main` at `015903d8`, not recalled:

- `validate_consumer` (`fleet-candidate-check.py:139-318`) does exactly five
  things per consumer: `git remote get-url origin`, `git clone --single-branch`,
  `install.py <clone> --force --platform ...` (`:227-247`),
  `install-audit.py --repo <clone> --expected-platform ...` (`:250-270`), then
  the consumer's `candidatePrepare` and `candidateChecks` (`:272-307`). There is
  no plugin build, no `claude` invocation, no machine install, and no resweep.
- **No consumer in `docs/fleet/consumers.json` carries a `mode` key at all.**
  Verified after the 0.69.0 merge by enumerating the actual key set of all eight
  records: `candidateChecks`, `candidatePrepare`, `candidateTimeoutSeconds`,
  `github`, `name`, `pathHint`, `platforms`, `rolloutPriority`. The schema-5
  registry has never written one. Every reader therefore takes
  `DEFAULT_FLEET_CONSUMER_MODE` (`fleet_lib.py:26`), which is `"fat"`.

  This strengthens rather than weakens the argument that follows. "Run each
  consumer in its declared mode" would today branch on a value no record
  supplies, so the thin lane would be unreachable for every consumer while the
  run reported eight passes. It also makes acceptance criterion 2's registry
  check a matter of *bytes*, not values: `git diff --exit-code
  docs/fleet/consumers.json` is the only form that cannot be satisfied by a
  reader supplying the default, which is exactly how the earlier draft of this
  document came to assert eight `fat` values that do not exist.
- Every consumer's resweep verdict was `blocked` at the 2026-08-10 fleet scan,
  with `blockers` (consumer-authored references to removed paths) ranging from
  16 (`sd-github-review`) to 207 (`anomaly-metric-creator`). The `packDefects`
  column in that scan (15-17 per consumer) predates
  `08-10-thin-prompt-surface-repoint` and `08-11-thin-undeclared-codex-marker`,
  both since archived; it is stale and must be re-measured, not carried.
- `claude` is present on this machine at 2.1.220, and
  `claude plugin validate --strict` exists with exactly that spelling
  (`claude plugin validate [--strict] <path>`).
- **`claude --plugin-dir` does not detect a bad plugin directory.** Measured:

  ```console
  $ claude --plugin-dir /nonexistent/plugin/path -p "say ok"
  ok
  EXIT=0
  ```

  A path that does not exist produces a normal answer and a zero exit. The
  flag's own help says "for this session only" — it is a session convenience,
  not a validator, and it has no non-interactive failure channel. See D5.
- `install.py --machine` takes `--home` and `--state-home`, both documented as
  the containment seam: "a scratch prefix keeps a trial install contained"
  (`install.py:383`).
- `.github/scripts/generate-plugin.py` takes `--check` and `--root`; `--root`
  defaults to the repository root and is the seam for building into a scratch
  tree.
- **Two consumers' registered `candidateChecks` invoke pack-owned scripts by
  repository-relative path**, and thin conversion removes exactly those files.
  Checked each declared command against `manifest.json`:

  | consumer | check command | manifest |
  | --- | --- | --- |
  | `se-ai-command-pack` | `bash scripts/sd-ai-command-pack-housekeeping.sh --self-test` | **pack-owned** |
  | `rwbp-website` | `node scripts/sd-ai-command-pack-review-preflight.mjs` | **pack-owned** |

  The other six name consumer-authored scripts (`scripts/update_repomix`,
  `scripts/check-review-churn.mjs`, `tools/check_ci_review_contract.py`, `npm`
  targets) that a conversion leaves in place. `THIN_PROFILE`
  (`installer/references.py:334-337`) rewrites such references to
  `~/.agents/bin/{name}`, but it rewrites *files inside the consumer*, not this
  repository's fleet registry. Both rows are `kind: script`, and the surface
  spec's family table maps the `scripts/` prefix to the `agents-bin` family with
  destination `<home>/.agents/bin`, so a conversion relocates them out of the
  repository rather than leaving a copy behind. See D6.
- **`command_environment` (`fleet-candidate-check.py:67-84`) does not set
  `HOME`.** It copies `os.environ`, clears `CACHE_ENV_KEYS`, and sets
  `CACHE_ROOT_ENV` plus the candidate-check marker. So a `~`-rooted lookup made
  by a consumer's own check resolves against the real invoking home. Harmless
  for a fat consumer, whose checks are all repository-relative; not harmless for
  a thin one, whose pack helpers live at `~/.agents/bin`. See D7.

## The shape question, answered first

The four concerns all descend from one unexamined assumption in the prior
attempt: that "validate the thin shape" means **converting a disposable
consumer clone with `install.py --thin`**. It does not, and requirement 1 never
said it did. Requirement 1 enumerates four steps — build the plugin,
`claude plugin validate --strict`, a `claude --plugin-dir` load smoke, and a
machine install into a scratch prefix — and **not one of them is a consumer
conversion**. All four are pack-side artifacts: they are what a thin consumer
*consumes*, and they are identical for every consumer. (The third of the four
turns out not to be executable as written; D5 replaces it and records the
deviation against the PRD rather than dropping the requirement silently.)

That reading is not a convenience. A conversion in the loop is impossible
today by measurement: all eight consumers resweep `blocked`, and
`install.py:898-901` re-runs the resweep and refuses on any binding reason. A
design whose central step cannot execute against any real input is not a design.

So the loop splits in two:

- **The thin artifact lane** — build, validate, drift-check, machine-install. Runs
  **once per candidate**, not once per consumer: the artifacts do not vary by
  consumer, and running them eight times would multiply the cost of the most
  expensive steps for no additional evidence.
- **The per-consumer lane** — each consumer's clone is put into the shape that
  consumer will actually be in, and its own `candidatePrepare` /
  `candidateChecks` run there.

## D1 — C-1: the loop never writes this repository's fleet registry

**Concern.** `apply_conversion` calls `flip_registry_mode`
(`installer/thin.py:967-972`) on success, rewriting `docs/fleet/consumers.json`
in *this* checkout. A validator that mutates its own source tree is not a
validator, and it would destroy the byte-stability of the registry that
acceptance criterion 2 depends on.

**Resolution: dissolved, not mitigated.** Under the shape above the loop never
calls `install.py --thin`, so `flip_registry_mode` is never reached. There is no
flag to add and no isolated-registry mechanism to build.

A converted consumer's clone arrives *already thin* — the conversion happened in
that consumer's own repository, in its own PR, long before release-prep clones
it. The loop reads the clone's pin to decide which lane to run (D3), and reads
the registry's `mode` only to record a skew note. It writes neither.

**Wrong**

```python
# Put the clone in thin shape by converting it here.
run(["install.py", str(clone), "--thin", "--consumer", consumer.name, ...])
# -> rewrites docs/fleet/consumers.json in the pack checkout, and refuses
#    anyway because every consumer resweeps `blocked`.
```

**Correct**

```python
# The clone is already in its declared shape; put the *pack's* artifacts in
# thin shape once, and install into the clone with the mode-appropriate call.
thin_artifacts = build_thin_artifacts(pack_root, work_root)   # once per run
pin = conversion.thin_pin_state(clone)      # what the checkout IS  -- D3
declared = declared_mode(consumer)          # what the pack BELIEVES -- note only
```

Acceptance criterion 2's registry check is therefore a *regression* test rather
than a hope: `docs/fleet/consumers.json` is byte-identical before and after.

## D2 — C-2: the clean-tree precondition never arises

**Concern.** A conversion needs a prior install to have placed the payload, but
installing dirties the clone, and `thin-resweep.py:1723-1727` turns a dirty
worktree into a `blocked` verdict that `install.py:898` refuses on.

**Resolution: dissolved by D1.** No conversion, no resweep binding, no
clean-tree precondition. The fat lane still runs `install.py --force`, which
dirties the clone exactly as it does today, and nothing downstream of it reads
worktree cleanliness.

The resweep does not disappear from the design — see D4 — but it is run for
*reporting*, not as a conversion precondition.

**Amended during implementation.** This section originally ran that resweep on
the pristine clone "before any install, where cleanliness is a fact rather than
an obstacle". That ordering is wrong, and measurably so. A pristine clone
carries whatever pack version the consumer last installed, so a resweep there
measures the **previous release** and attributes its defects to the candidate.
Measured: `sd-github-review`'s vendored
`.claude/sd-ai-command-pack/planning-adversarial-review.md` still invoked the
`codex` CLI at lines 42, 43, 56, and 58 — a defect this pack had already
removed — and the candidate was failed for it.

The resweep therefore runs **after** the install. Cleanliness stops being free
and becomes something the lane must produce: the install is committed in the
disposable clone first, with
`git add --all` and a `git -c user.name=candidate … commit --allow-empty`. That
is honest here rather than a workaround — the clone exists to be thrown away,
and committing is what makes "this tree contains the candidate" a fact the
resweep can read rather than noise it has to be told to ignore.

The ordering fix is visible in the numbers: installing the candidate *lowered*
blocker counts against the pre-install baseline on five consumers
(anomaly-metric-creator 207→200, rwbp-website 68→64, hoa-manager 37→34,
loadsmith 56→52, mezmo_benchmark 47→46), because the candidate fixes references
the previously installed release still carried.

## D3 — C-3: branch on the checkout's own pin, with the predicate install.py uses

**Concern.** An unconditional `--platform` lane breaks against an already-thin
checkout: `install.py:1474` routes it into the thin-refresh branch, where
`--platform` is explicitly rejected (`_thin_refresh_rejection`,
`install.py:1268-1272`, "a thin consumer's platform set is owned by its pin").

**Resolution.** Branch on `conversion.thin_pin_state(clone)` — the same
predicate `install.py` itself branches on — never on the registry's declared
mode.

The distinction matters and is the whole of C-3: the registry records what the
pack *believes*, the pin records what the checkout *is*. They disagree exactly
during the window between a consumer's conversion PR merging and the registry
flip landing, which `flip_registry_mode`'s own docstring calls out as an
accepted skew ("consumer converted, registry did not"). Branching on the
registry would send a `--platform` call at a genuinely thin checkout during
precisely the skew the system is designed to tolerate.

| `thin_pin_state(clone)` | install call | audit call |
| --- | --- | --- |
| `PIN_STATE_FAT` | `install.py <clone> --force --platform ...` | `--expected-platform ...` (unchanged) |
| `PIN_STATE_THIN` | `install.py <clone> --force` (thin refresh; **no** `--platform`) | thin-aware audit, platforms from the pin |
| `PIN_STATE_MALFORMED` | none | none — `failed`, with the pin state named |

`malformed` fails rather than guessing, matching `install.py:1490-1512`, which
refuses in both directions for exactly that state.

The declared registry `mode` is still read, and a disagreement between it and
the pin is recorded in the ledger as a note. It is not an error: it is the
documented skew, and the ledger is the right place for it to be visible.

## D4 — C-4: the policy answer

**The question, restated exactly:** does a consumer the pack cannot convert
fail `make release-prep`?

**Answer: no for consumer-owned blockers, yes for pack-owned defects.** The
split is not invented for this task — it is the distinction `decide()` already
draws, in the buckets it already separates, for the reason its own comment
already gives (`thin-resweep.py:1704-1709`):

> a caller that is told `blocked` and not why cannot act on it, and "the tree
> was dirty" and "the pack ships a broken reference" call for opposite
> responses.

Applied to the release gate:

- **A pack-owned defect that survives the conversion's own rewrite fails
  release-prep.** A pack-owned reference to a path the conversion removes is a
  defect in the artifact being released, found by the gate that exists to find
  it. The pack can fix it before shipping, and
  `08-10-thin-prompt-surface-repoint` and `08-11-thin-undeclared-codex-marker`
  are two already-shipped proofs that this is ordinary pack work.

  **Amended during implementation — the raw count is the wrong measurement.**
  This section originally said `packDefects > 0` fails release-prep. It does
  not, and the difference is not a tuning choice. The resweep's `packDefects`
  bucket (`thin-resweep.py:1592-1598`) is a **pre-rewrite** count: it records
  pack-owned content that *cites* a removed path, and the resweep never calls
  `rewrite_text`. But every kept text file passes through
  `rewrite_text(text, profile=THIN_PROFILE, key=entry)` at `thin.py:651` during
  the conversion, and `THIN_PROFILE` repoints exactly these citations —
  `scripts/sd-ai-command-pack-review.py` becomes
  `~/.agents/bin/sd-ai-command-pack-review.py`. A file in that bucket is
  therefore evidence of nothing until the rewrite has been applied to it.

  Measured: `check_text_residue` over all seven flagged files in this
  repository, and over the same files in the real `sd-github-review` checkout,
  reports **0 files with residue**. Acting on the raw count would have meant
  hardcoding `~/.agents/bin` into prose that fat consumers read.

  The gate is therefore residue **after** the rewrite, computed by
  `surviving_pack_defects`: rewrite the flagged file under `THIN_PROFILE`, then
  run `check_text_residue` on the result. What survives is real — a glob like
  `scripts/sd-ai-command-pack-*.py` is not a path the rewrite can repoint, and
  it still fails. What does not survive is recorded as a note, so the count
  stays visible without being a verdict.

  A surviving defect is nonetheless attributed **per consumer**, not once per
  run, and that is deliberate. The resweep does not audit the pack in the
  abstract: it scans *that consumer's tree* for citations of paths the
  conversion removes, so the count varies with which pack surfaces that
  consumer vendors and cites. The 2026-08-10 scan measured 15-17 across the
  eight — a spread, not a constant. Collapsing them into one run-level failure
  would discard the only signal that says which consumer surfaces the defect.
- **`blockers > 0`, `missingFiles > 0`, or a dirty worktree do not fail
  release-prep.** They are conditions in a repository the pack does not own and
  cannot fix. Failing on them makes every pack release hostage to eight
  consumer backlogs — 207 of them in `anomaly-metric-creator` alone — and the
  first thing anyone does with a release gate that cannot be satisfied is turn
  it off.

**But "does not fail" must not become "reported as passed".** That is precisely
the defect the sibling task just fixed at a different layer: a gate that
certifies a validation it never ran. So the result gains a third status.

### The status contract

`CandidateResult.status` becomes a three-value enum:

| status | meaning | release-prep |
| --- | --- | --- |
| `passed` | every step ran and succeeded | continues |
| `failed` | a step ran and failed, or a pack-owned defect was found | **exits nonzero** |
| `blocked` | a consumer-owned precondition prevented the thin lane; nothing was falsely certified | continues, with the reasons recorded |

`blocked` requires a non-empty `reasons` array. A `blocked` result with no
reasons is itself a validation error — an unexplained skip is the failure mode
this status exists to prevent.

### The ledger contract must agree

`validate_candidate_ledger` (`fleet_lib.py:902-906`) today rejects any consumer
whose recorded status is not `passed`. That is now too strict in one direction
and not strict enough in another:

- accept `blocked` **only** when the ledger row carries a non-empty `reasons`
  array;
- keep rejecting `failed` and every unknown status;
- keep rejecting a missing or unknown consumer — the ledger must still name all
  eight, because "absent" is the one shape that could hide a skipped consumer.

The ledger row therefore gains `reasons: string[]` (empty for `passed`). This
is a candidate-ledger schema change, so `CANDIDATE_LEDGER_SCHEMA_VERSION` goes
3 → 4 and old ledgers self-migrate by going stale, exactly as 2 → 3 did.

**Wrong**

```python
if result.get("status") != "passed":
    errors.append(f"... status is {result.get('status')!r}; expected 'passed'")
```

**Correct**

```python
status = result.get("status")
if status == "blocked":
    # A blocked consumer is recorded, never certified. The reasons are the
    # whole point: a ledger that says "blocked" and not why is a skipped
    # consumer wearing a status.
    if not isinstance(result.get("reasons"), list) or not result["reasons"]:
        errors.append(f"candidate ledger {consumer.name} is blocked with no reasons")
elif status != "passed":
    errors.append(
        f"candidate ledger {consumer.name} status is {status!r}; "
        "expected 'passed' or 'blocked'"
    )
```

`fleet-candidate-check.py:520` — which returns 1 when any result is not
`passed` and suppresses the ledger — narrows to "not `passed` **and** not
`blocked`", so a fleet of blocked consumers still writes a truthful ledger.

## D5 — the thin artifact lane

Runs once per candidate run, before the per-consumer loop, into the same
`work_root` temporary directory the loop already creates
(`fleet-candidate-check.py:480`).

1. `python generate-plugin.py --root <work_root>/pack` — build into a scratch
   copy, never the checkout. The pack checkout is the input to release-prep, and
   a validator that rewrites its own input is the same category of error as D1.
2. `claude plugin validate <work_root>/pack/plugins/sd --strict`.
3. `python generate-plugin.py --check` against the **checkout** — the drift
   gate. See below; this replaces requirement 1's `--plugin-dir` load smoke.
4. `python install.py --machine --home <work_root>/home --state-home
   <work_root>/state` — contained by construction, per `install.py:383`. The
   scratch prefix is not discarded: D7 hands it to the thin per-consumer lane
   as `HOME`, which is what makes a thin consumer's `~/.agents/bin` lookups
   resolve to the candidate instead of the invoking developer's install.

Any step failing makes the whole run `failed` and release-prep exit nonzero
(requirement 4). This lane is consumer-independent, so its failure is not
attributed to a consumer.

### Requirement 1's load smoke cannot be implemented as written

The PRD names `claude --plugin-dir` as the third step. Measured, it exits 0
against `/nonexistent/plugin/path` while answering the prompt normally. It has
three disqualifying properties, any one of which is sufficient:

- **It does not fail.** A gate whose negative case exits 0 certifies nothing —
  the same defect class as the sibling task's, one layer up.
- **It requires a model call.** `-p` is the only non-interactive form, so the
  step would put a billable, network-dependent, credentialed API request inside
  `make release-prep`. Requirement 5 forbids a skip path, so every release-prep
  on every developer machine would need working `claude` auth.
- **Its own help scopes it to a session** ("Load a plugin from a directory or
  .zip for this session only"). It is a convenience for interactive use, not a
  validation surface, and no `--strict`-equivalent exists on it.

`claude plugin validate --strict` already covers the manifest — "unrecognized
fields, missing metadata, and other issues that the runtime tolerates" — which
is the substance the smoke was reaching for. The remaining gap is *drift*:
whether the committed plugin matches what the generator would produce.
`generate-plugin.py --check` answers exactly that, deterministically, offline,
with a real nonzero exit.

**This is a deviation from PRD requirement 1 and is recorded as one.** The PRD
must be amended to name the three executable steps before `task.py start`;
implementing against an unamended requirement would leave a criterion that
cannot be ticked honestly.

## D6 — a thin consumer's registered checks point at removed files

Two of the eight consumers register a `candidateChecks` command that invokes a
pack-owned script by repository-relative path (see the evidence table). Those
files exist in a fat consumer because the pack vendors them; a thin consumer
does not have them, by definition. So for a converted `se-ai-command-pack`, the
loop would run `bash scripts/sd-ai-command-pack-housekeeping.sh --self-test`
inside a clone where that file was deleted, and get a shell "No such file or
directory".

**That must not be `failed`.** Nothing is wrong with the candidate: the pack
built correctly, the install succeeded, and the plugin validated. What is wrong
is a *registry record* that still describes the consumer's fat shape. Reporting
it as a pack failure would block every release after the first conversion, for
a reason no pack change can fix.

**Resolution.** Before running a thin consumer's `candidateChecks`, resolve each
command's program argument against the clone. When it names a path that does
not exist in the clone **and** that path is manifest-declared — i.e. the pack
owns it and the conversion removed it — the consumer is `blocked`, with a reason
naming the command and the `~/.agents/bin/<name>` form the record should use
instead. A non-existent path the pack does *not* own stays a genuine failure;
that is the consumer's own broken check, not conversion fallout.

The lane is deliberately narrow: it does not rewrite the registry, and it does
not guess. Repointing a consumer's `candidateChecks` at `~/.agents/bin` belongs
to that consumer's conversion PR, and the reason string says so.

## D7 — the thin lane must run the consumer's checks against the candidate

`command_environment` does not set `HOME`. For the fat lane that is correct and
must not change: every fat consumer's checks are repository-relative, and
overriding `HOME` would perturb tool caches for no benefit.

For the thin lane it is a correctness bug rather than a fidelity nicety. A thin
consumer's pack helpers resolve through `~/.agents/bin` (`THIN_PROFILE`,
`installer/references.py:334-337`). With the invoking `HOME` inherited, those
lookups reach **whatever pack the developer or CI runner happens to have
installed** — quite possibly an older release, possibly none. The candidate
would then be certified by running someone else's pack.

Setting `HOME` in the child environment is sufficient, and the surface spec's
phrasing invites doubt on that point — it says the home directory comes from
`Path.home()`, "never a raw `$HOME` read". That rules out
`os.environ["HOME"]`, not the environment variable itself. Measured:

```console
$ HOME=/tmp/fakehome python -c "from pathlib import Path; print(Path.home())"
/tmp/fakehome
```

`Path.home()` is `expanduser("~")`, which consults `HOME` first on POSIX. So the
child environment is the correct seam and no `--home` threading is needed for
the consumer's own checks.

**Resolution.** The thin per-consumer lane runs `candidatePrepare` and
`candidateChecks` with `HOME` set to the same `<work_root>/home` that D5's
machine install wrote, and `state_home` pointed at `<work_root>/state`. This is
the one place the two lanes are coupled, and the coupling is the point: the
artifact lane's machine install becomes the thing under test rather than a
build-and-throw-away.

The fat lane's environment is unchanged. A test must pin both halves — that a
fat consumer's checks see the inherited `HOME`, and that a thin consumer's see
the scratch prefix — because a single shared environment builder that quietly
started overriding `HOME` for everyone would be an invisible behavior change to
six passing consumers.

### `claude` unavailability is a failure, never a skip

Requirement 5. If `claude` is not resolvable, steps 2 and 3 report
`unavailable` and the run exits nonzero. There is no environment variable, no
`--skip-thin`, and no "degrade to fat" path — an unrunnable validation that
reports success is the exact shape of the defect this whole contract exists to
close. CI must therefore have `claude` available for release-prep; that is a
stated prerequisite, not a fallback to design around.

## Validation and error matrix

| condition | outcome |
| --- | --- |
| plugin build fails | run `failed`, release-prep nonzero |
| `plugin validate --strict` nonzero | run `failed`, release-prep nonzero |
| `generate-plugin.py --check` reports drift | run `failed`, release-prep nonzero |
| machine install to scratch prefix nonzero | run `failed`, release-prep nonzero |
| `claude` not resolvable | run `failed`, diagnostic names it `unavailable` |
| consumer resweep pack defect that still names a root pack resource after the `THIN_PROFILE` rewrite | consumer `failed`, release-prep nonzero |
| consumer resweep pack defect the rewrite repoints | note recorded, not a verdict |
| consumer resweep `blockers`/`missingFiles`/dirty only | consumer `blocked`, reasons recorded, release-prep continues |
| clone pin `malformed` | consumer `failed`, pin state named |
| clone pin `thin`, install with `--platform` | must not happen — D3; a test pins it |
| thin clone, check names a manifest-declared path absent from the clone | consumer `blocked`, reason names the command and the `~/.agents/bin` form — D6 |
| thin clone, check names a non-manifest path absent from the clone | consumer `failed` — the consumer's own broken check |
| thin clone's checks run with the inherited `HOME` | must not happen — D7; a test pins the scratch prefix |
| fat clone's checks run with an overridden `HOME` | must not happen — D7; a test pins the inherited value |
| ledger row `blocked` with empty `reasons` | ledger invalid |
| ledger row `failed` or unknown status | ledger invalid |
| ledger missing a consumer | ledger invalid (unchanged) |

## Good / base / bad cases

- **Good** — all eight clones pin `fat`, thin artifact lane green, every
  consumer's own checks pass: eight `passed` rows, ledger written, release-prep
  continues, and `docs/fleet/consumers.json` is byte-identical afterward.
- **Base** — today's real fleet: artifact lane green, every consumer `blocked`
  on consumer-authored references with reasons recorded. Release-prep continues
  and the ledger truthfully says no consumer was thin-certified.
- **Bad** — the pack ships a reference the conversion's rewrite cannot repoint,
  such as the glob `scripts/sd-ai-command-pack-*.py`: one or more consumers
  `failed` on surviving residue, release-prep exits nonzero, and the fix is a
  pack-side PR.

## Compatibility and rollback

Schema 3 → 4 self-migrates in both directions: a schema mismatch marks the
ledger stale, and a stale ledger is a regeneration, not a failure. The
historical-tag path is unaffected for the reason recorded in the sibling task's
design — `release_identity.py:395-400` gates on the tag's payload equalling the
current checkout before reading the ledger.

Rollback is `git revert` of the commit. No rollback-only code.

## Non-goals

- Converting any consumer. Children 3-5 own that, blocked on explicit per-cohort
  user authorization.
- Re-measuring the fleet. The stale `packDefects` column is re-measured by a
  resweep run, not by this design. (It since was: a full-fleet run at this
  branch's HEAD recorded 14-16 pre-rewrite citations per consumer and **zero**
  surviving after the rewrite.)
