# Implementation: one canonical fleet path

Design: [`design.md`](design.md). PRD: [`prd.md`](prd.md).

Steps 1 to 5 are repository-local and executable now. Step 6 is the rollout and
cannot start until the machine install is at the release target, which is an
operator action. Steps are ordered by dependency, not by size.

## Step 0 — re-measure, do not trust the snapshot

`design.md` carries a 2026-08-17 measurement. Rebuild it first; a rollout planned
against stale pins moves the wrong consumers.

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json >/tmp/fleet.json
python3 - <<'PY'
import json
d=json.load(open('/tmp/fleet.json'))
print("target", d["targetPackVersion"], "machine", d["machineScope"]["packVersion"],
      "plugin", d["machineScope"]["pluginVersion"], d["machineScope"]["comparison"])
for r in d["repositories"]:
    g=r["report"]["git"]
    print(r["name"], r["pin"]["version"], r["report"]["versions"]["trellis"],
          g["branch"], g["workingTree"]["state"])
PY
```

There is no `git.dirty` key. Cleanliness is `git.workingTree.state` (`clean` or
otherwise) beside `staged`, `unstaged`, and `untracked` counts; a `.get("dirty")`
prints `None` for every consumer and reads as "nothing is dirty".

Reconcile every row that differs from the design's table and correct the design
in the same session. Specifically re-derive the dirty set: it decides which
consumers Step 6 may touch at all, and it changes without notice because the
checkouts are other people's working trees.

## Step 1 — the PRD amendment is already done

`prd.md`'s third criterion was restated **in planning** (dated amendment,
2026-08-17): each consumer is at target **or** carries a recorded reason, and the
task closes on a complete ledger rather than a uniform fleet. The original
wording is kept visible in the amendment note.

Nothing to execute here. What implementation owes is the ledger itself: one row
per consumer, **pin only**, filled in Step 6, with a reason for every consumer not
at target. Start it from Step 0's table so the skipped consumers are recorded
before any mutation, not reconstructed afterwards. The Trellis version has its own
ledger in `08-17-fleet-trellis-version-drift`; do not mix the two, or a consumer
skipped on one leg reads as skipped on both.

## Step 2 — the canonical-path doc

New file `docs/FLEET_CANONICAL_PATH.md`. Contents, from `design.md`'s four-leg
table:

1. one row per leg: canonical value, the command that prints the real value, the
   owning task, and what a deviation costs;
2. the rule that a leg's value is named by a command, never hardcoded — a
   literal `0.71.29` in prose goes stale on the next release and no gate fails;
3. the pin-versus-Trellis PR separation and why (revertability along one leg);
4. the smoke-PR checklist, five items, from `design.md`'s requirement 5 section;
   and
5. the precondition list, including that a thin consumer resolves its surfaces
   from the machine install, so the machine has to be at target first.

Then add exactly one link from `docs/FLEET_ROLLOUT.md` — procedure authority
pointing at value authority, not a copy of the table.

Watch two existing gates here:

- the documentation path-reference check
  (`scripts/sd-ai-command-pack-review-preflight.mjs:301`, passing message at
  `:3205`): named paths must "resolve to existing repo files or documented
  external/local-only paths". The canonical check's argv contains
  `$HOME/.agents/bin/sd-ai-command-pack-housekeeping.sh`, which is a local-only
  path outside the repository — write it so the check reads it as one, and do not
  assume it is exempt because it is inside a code fence. A deliberately absent
  path still cannot be expressed at all; that limitation is
  `08-08-preflight-absent-path-prose`.
- `make check`'s shipped-surface closure: a new `docs/` file is not a shipped
  surface, so no payload digest or manifest bump. Confirm with the gate rather
  than assuming — the run is cheap.

## Step 3 — normalize the candidate contract in `docs/fleet/consumers.json`

For each of the 8 consumers:

1. put the canonical pack-owned check **first** in `candidateChecks`, identical
   argv everywhere:
   `["bash", "-c", "bash \"$HOME/.agents/bin/sd-ai-command-pack-housekeeping.sh\" --self-test"]`
   — the entry se-ai-command-pack already carries. `design.md` settles why it and
   not the bare `review-preflight.mjs`: preflight's subject is a change set, and
   the candidate validator runs in a diff-less clone of the default branch.
   rwbp-website's preflight entry is therefore dropped rather than annotated.
2. keep at most one repo-owned check after it, and delete the ones that are a
   third name for review readiness rather than a stack difference —
   `check-review-churn.mjs`, `check-review-preflight.mjs`, and
   `check_review_readiness.sh --all --skip-build` are the candidates named in
   `design.md`.
3. add a `deviations` object naming the reason for every surviving repo-owned
   entry, keyed by field (`candidateChecks`, `candidatePrepare`).

Constraints that fail the run if broken, from
`scripts/sd_ai_command_pack_fleet_lib.py:679-691`:

- `candidateChecks` is parsed `allow_empty=False` — never normalize a consumer to
  zero checks;
- `candidatePrepare` is parsed `allow_empty=True` — se-ai-command-pack's empty
  array is already legal and stays; and
- unknown keys are ignored, so `deviations` cannot break an existing consumer of
  the manifest — and cannot enforce anything either, which is Step 4.

Do not change `rolloutPolicy`, `platforms`, `rolloutPriority`, or
`candidateTimeoutSeconds`. A deleted check is a real reduction in what the
candidate validator runs for that repo; state each deletion in the PR body with
the reason, since nobody else will notice a check that stopped running.

Three existing suites read this manifest or its shape —
`tests/test_fleet_preflight.py`, `tests/test_fleet_candidate.py`, and
`tests/test_status.py`. Run them before the full gate; a fixture that pins a
consumer's current `candidateChecks` will fail here, and that failure is a
question about the fixture, not a reason to revert the normalization.

## Step 4 — the gate that makes the annotation real

Add a check, run by `make check`, asserting for `docs/fleet/consumers.json`:

- every consumer's first `candidateChecks` entry is the canonical pack-owned
  argv;
- every subsequent `candidateChecks` entry has a non-empty
  `deviations.candidateChecks` reason;
- every non-empty `candidatePrepare` that is not the canonical one has a
  `deviations.candidatePrepare` reason; and
- the parser still accepts the file
  (`load_fleet_consumers` / `load_fleet_rollout_policy`).

A `tests/test_*.py` unittest is the cheapest home — the repo gate collects
`tests/` and forbids skips (`Makefile:49` fails on `skipped=[1-9]`), and this
check never needs to skip: it reads a file that is always present.

Falsifiable check for this step: add a bespoke entry with no reason to a scratch
copy of the manifest and confirm the test **fails**; a gate that passes on a
deliberately broken input is not a gate.

## Step 5 — machinery smoke, without mutation

Invoke the command `sd-fleet-refresh dry-run`. It is a **command invocation, not
a shell executable**: the procedure is source-only and is loaded by reading
`.agents/skills/sd-fleet-refresh/SKILL.md` from this checkout, so nothing on
`PATH` answers to that name and a `bash` block would fail with
`command not found`.

Expect: preflight recorded, current consumers marked `at-target`, every remaining
selected consumer marked `skipped`, no mutation, record completed
(`docs/FLEET_ROLLOUT.md:396`). Confirm afterwards that no consumer checkout
changed — compare against Step 0's table, since three of them were already dirty
before this task existed and "dirty" alone proves nothing:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(r["name"], r["report"]["git"]["workingTree"]) for r in d["repositories"]]'
```

This proves the manifest parses, the cohorts resolve, and each consumer is
reachable. It proves nothing about the pins.

## Step 6 — the rollout (gated)

**Gate A, operator:** the machine install must be at the release target. It is
behind today, and every thin consumer resolves its surfaces from it.

```bash
bash scripts/sd-ai-command-pack-pack-update.sh   # run from this checkout; machine-scope write
```

Do not run this without the operator asking for it, and do not proceed while the
plugin and receipt still report `skew`.

**Gate B, sequencing:** run `08-08-copilot-request-policy` (T-48) first if the
one-review-per-head observation is wanted from this pass. Otherwise record
explicitly that smoke item 2 is deferred and expect duplicate Copilot requests.
Do not patch the request surfaces from inside a rollout lane.

**Gate C, cleanliness:** exclude every dirty consumer. Never stash, reset, clean,
or commit in another checkout. Record each exclusion in the ledger from Step 1.

Then run the campaign through its own procedure by invoking the command
`sd-fleet-refresh` (again a command, not a shell executable). It owns preflight,
cohorts, lanes, review, and the gated merges; this task does not re-implement any
of it.

For each consumer PR, record the five smoke items from `design.md`. After each
merge, verify the pin moved:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(r["name"], r["pin"]["version"]) for r in d["repositories"]]'
```

## Step 7 — the Trellis leg is another task

Filed 2026-08-17 as `08-17-fleet-trellis-version-drift` (eight consumers measured
at 0.6.7 against 0.6.14 here, plus the reporting-visibility question). Nothing to
execute here. Two obligations remain on this task:

- the canonical-path doc's Trellis row names that task as the leg's owner; and
- no rollout PR from Step 6 may carry a `trellis update` diff. If a consumer's
  refresh somehow produces one, stop that lane rather than merging a mixed PR —
  `design.md` explains why the legs stay apart.

## Validation

```bash
.venv/bin/python -m unittest tests.test_fleet_preflight tests.test_fleet_candidate \
  tests.test_status -q                           # the three manifest-aware suites
make check                                       # Step 3's parse + Step 4's gate
git status --short                               # this repo only; consumers untouched
```

Plus the command `sd-fleet-refresh dry-run` for Step 5 — no mutation, and not a
shell command.

Report the dry-run outcome and the per-consumer ledger, not a summary sentence. A
skipped consumer is not a rolled-out one.

## Rollback points

- After Step 2: additive doc; revert the commit.
- After Step 3: the manifest change is text; revert restores the previous
  candidate contract exactly. Any check deleted in Step 3 comes back with it.
- After Step 4: one test file; reverting restores previous `make check` behavior.
- After Step 5: nothing to roll back — `dry-run` mutates nothing.
- After Step 6: per-consumer. An unmerged PR is closed and its branch deleted
  (the campaign's own recovery path). A merged one is reverted in that
  consumer's repository by its owner, and the pin leg is revertable
  independently of the Trellis leg precisely because that leg is a separate task
  with separate PRs.

## Out of scope

- Re-deciding the CI lane shape (`08-08-ci-lane-cost`) or the Copilot request
  surfaces (`08-08-copilot-request-policy`).
- Writing into, cleaning, or committing in any consumer checkout.
- Running the machine-scope pack update unasked.
- Changing `rolloutPolicy` cohorts or concurrency.
