# Implement: Retire the codex vendored-retention carve-out

Branch off `main`. Pack-only change; no consumer repository is touched at any
step.

## Step 0 — establish the falsifiable baseline (before any edit)

Record what a codex declaration currently costs, so step 6 can prove it reached
zero rather than asserting it. `classify_target` is pure — no receipt, no
filesystem — so the baseline needs no synthetic consumer:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from pathlib import Path
from installer import conversion

part = conversion.load_partition(Path('docs/fleet/surface-partition.json'))
base = frozenset({"claude", "gemini", "github", "opencode"})

def buckets(plats):
    out = {}
    for target in part.rows:
        bucket, _ = conversion.classify_target(target, part, plats)
        out.setdefault(bucket, set()).add(target)
    return out

without, with_codex = buckets(base), buckets(base | {"codex"})
for k in sorted(set(without) | set(with_codex)):
    print(f"{k:12} without_codex={len(without.get(k,())):>4}  with_codex={len(with_codex.get(k,())):>4}")
extra = with_codex.get("keep", set()) - without.get("keep", set())
print(f"\nextra targets kept when codex is declared: {len(extra)}")
from collections import Counter
print(Counter(t.split('/')[0] for t in extra))
EOF
```

Executed against the pre-change tree, this prints:

```
delete       without_codex= 168  with_codex=  91
keep         without_codex= 557  with_codex= 634

extra targets kept when codex is declared: 77
Counter({'.agents': 49, 'scripts': 26, 'docs': 2})
```

77 = 49 + 26 + 2, independently matching the machine receipt's `agents-skills`,
`agents-bin`, and `agents-docs` family counts.

These are partition-target counts over all 725 rows (168 + 557 = 725). They are
**not** the plan-level `166/13/27` and `91/13/102` figures in the archived
conversion-tooling artifacts, which are receipt-derived and use a different
denominator. Do not reconcile the two sets; they measure different things.

**Gate:** if the two columns are already identical, requirement 1 is already
satisfied and this task's premise is wrong — stop and re-derive before editing.

## Step 1 — the change itself

`.github/scripts/partition-surfaces.py:170-172`:

```python
PLATFORM_RETAIN_VENDORED_FOR: dict[str, tuple[str, ...]] = {
    "shared": ("pi",),
}
```

## Step 2 — correct the four rationale sites

None of these change behavior; all of them are the false claim this task retires.

1. `:140-142` — codex disposition. Keep `(REPO_NATIVE, False)`. Replace "never
   reads `~/.agents/skills`" with the two true reasons: `.codex/**` rows have no
   machine destination family (`family_for_target` returns `None`, and
   `machinepayload.py:47-49` fails closed on that), and Codex reads project-root
   `.codex/`. Cite `research/codex-skills-resolution-probe.md`.
2. `:163-169` — retention rationale. Codex is no longer among the platforms
   needing a vendored copy; say why in one clause and point at the probe.
3. `.trellis/spec/backend/manifest-and-filesystem.md:125-133` — `["codex", "pi"]`
   → `["pi"]`, and rewrite the Codex clause. The detection rule below it is
   unchanged and must stay.
4. `installer/conversion.py:310-320` — the R17-C1 comment explains the bug using
   a codex-declaring consumer's "102 residual targets". Restate against `pi` so
   the comment describes a configuration that still exists. The code is correct;
   only the narration is stale.

## Step 3 — the marker rule

`scripts/sd-ai-command-pack-thin-resweep.py`.

- Add the retained-platform set as a parameter to `platform_marker_hits`
  (`:788-794`). `scan()` already has `partition` at `:1360` and calls the
  function at `:1628`, so this is one argument.
- Derive it from the partition: the union of every machine platform's
  `retainVendoredFor` list. Do not hardcode `{"pi"}`.
- `MARKER_PLATFORMS` keeps `("codex", "pi")` — detection and pack-defect
  classification are unchanged.
- Consumer-owned hits (`:860`, `:884`, and the `$CODEX_HOME` / CLI marker sites)
  route to `blockers` when the platform is retained, `advisories` otherwise.
  Pack-owned hits keep going to `packDefects` regardless.
- Add `"advisories"` to the `hits` dict at `:814`; the outer buckets already
  carry it (`:1384`) and the merge loop at `:1631` needs no change.
- Rewrite the `:657-704` rationale block. It is the primary statement of the
  false premise. Keep R12/R13/R14/R15/R16's history — those rounds were right
  about detection — and correct only the retention consequence, noting that
  `:691-694`'s "asks for a declaration that changes nothing" standard is what now
  covers every codex marker rather than just the empty-directory one.

## Step 4 — regenerate

```bash
make generate
git diff --stat docs/fleet/surface-partition.json plugins/sd/machine-payload/partition.json
```

Both must change, and only in `platforms.shared.retainVendoredFor`. A change to
`counts` means a disposition moved — that is not this task and must be
investigated before continuing.

```bash
python3 .github/scripts/partition-surfaces.py --check   # must exit 0
```

## Step 5 — tests

Update the ones pinning the shipped value. There are **two** such assertions, not
one — the second is easy to miss because it asserts the whole `shared` dict
rather than the field:

- `tests/test_partition_surfaces.py:136-143` — asserts
  `committed["platforms"]["shared"]` equals a dict containing
  `"retainVendoredFor": ["codex", "pi"]`. Its comment at `:130-131` also repeats
  the falsified "never reads `~/.agents/skills`" claim and must be corrected with
  it; the adjacent `codex` disposition assertion stays as-is, since `repo-native`
  is still the right answer.
- `tests/test_partition_surfaces.py:488` — **leave unchanged.** Executing the
  suite corrected this line: it sits inside
  `test_retention_field_round_trips_and_stays_sorted`, which *mocks*
  `PLATFORM_RETAIN_VENDORED_FOR` to `("pi", "codex")` so the emitted list can be
  asserted sorted. The value is the test's own unsorted input, not a claim about
  the shipped disposition, and editing it to `["pi"]` destroys the sort coverage.
- `tests/test_partition_surfaces.py:173-174` — prose mentioning "codex or pi".
- `:158-168` and `:170-190` loop over the list and need no change; confirm they
  still pass rather than editing them.

Retarget the fixture-based retention tests so the **mechanism stays exercised**
(design.md, "Preserving retention coverage"). These build their own inline
partitions and are not assertions about the shipped value:

- `tests/test_conversion_plan.py:107` (fixture), `:176-186`, `:431`
- `tests/test_thin_apply.py:285-292`
- `tests/test_thin_resweep.py:394-422`

The R17-C1 both-directions agreement test between `classify_target` and
`expected_residual_targets` is retargeted, never deleted.

New tests:

1. **The load-bearing one.** Two conversion plans for one synthetic consumer
   whose declared platforms differ only by `codex` are identical — same keep
   set, same remove set. Assert set equality, not counts.
2. `pi` retention still produces a non-empty retained slice, so test 1 cannot
   pass by retention being globally broken.
3. Undeclared codex usage lands in `advisories`; undeclared pi usage still lands
   in `blockers`; a pack-owned codex directory still lands in `packDefects`.
4. The blocking set is partition-derived: a fixture partition that retains
   `codex` makes the codex marker block again.

Test 4 is what stops step 3 from silently degrading into a hardcoded `{"pi"}`.

## Step 6 — verify against the step-0 baseline

Re-run step 0's probe. The two plans must now be identical, and the 77-row delta
must be gone. This is the acceptance criterion; a passing test suite alone does
not establish it.

## Step 7 — sweep for stale claims

`make check` cannot catch prose. Enumerate from the filesystem — but **not with
bare numeric greps.** `77`, `102`, and `179` match dependency hashes in
`requirements-dev.txt` and unrelated line numbers by the hundred; a sweep built
that way returns noise and gets skipped. Anchor on the claim instead:

```bash
LIVE='--include=*.py --include=*.md --include=*.json --include=*.toml'

# A. the falsified claims
grep -rn $LIVE -E "never reads .~/\.agents/skills|cannot consume the machine-installed|user root is .\\\$CODEX_HOME" . \
  | grep -v node_modules | grep -v 'tasks/archive/' | grep -v '^./CHANGELOG.md'

# B. retention stated as a live codex consequence
grep -rn $LIVE -E "(declar\w+ )?codex.{0,40}(retain|75|77|102)|retain.{0,40}codex" . \
  | grep -v node_modules | grep -v 'tasks/archive/' | grep -vi changelog
```

Run against the pre-change tree, sweep A returns five sites and B returns ten.
Excluding this task's own artifacts, the live ones are:

| Site | Owner | Handling |
|------|-------|----------|
| `.github/scripts/partition-surfaces.py:141` | this task | step 2.1 |
| `scripts/sd-ai-command-pack-thin-resweep.py:664` | this task | step 3 |
| `.trellis/spec/backend/manifest-and-filesystem.md:130-133` | this task | step 2.3 |
| `installer/conversion.py:313` | this task | step 2.4 |
| `tests/test_partition_surfaces.py:141` (the assertion spanning `:136-143`), `:488`; `test_conversion_plan.py:107, 182, 431`; `test_thin_apply.py:288`; `test_thin_resweep.py:398` | this task | step 5 |
| `.trellis/tasks/08-09-deployment-thin-consumers/prd.md:122-126` | **parent task** | hand over |
| `.trellis/tasks/08-09-thin-migration/design.md:26` | **sibling task** | hand over |
| `.trellis/tasks/08-10-thin-canary-conversion/prd.md:137, 196, 239` | **sibling task** | hand over |

The parent PRD at `:122-126` repeats the falsified claim verbatim; the canary PRD
carries it at `:137` and the measured 75-target retention figure at `:196` and
`:239`. Those three files are other active tasks — record what needs changing and
hand it over rather than editing them inside this task's commit.

Its other `retainVendoredFor` mentions (`:135`, `:140`, `:148`, `:199`, `:248`)
describe the mechanism generically and stay true, because the mechanism survives
through `pi`. Do not rewrite them.

`.trellis/tasks/archive/**` and shipped `CHANGELOG.md` entries are historical
records of what was true when written and are **not** rewritten.

### Hand-over (executed sweep, post-change)

Three active tasks own prose this change falsifies. Recorded here rather than
edited, so the correction lands in the task that owns the artifact:

| File | Line(s) | What is now wrong | Correction |
|------|---------|-------------------|------------|
| `.trellis/tasks/08-09-deployment-thin-consumers/prd.md` | 118-130 | Acceptance criterion "Codex/pi retention holds" states `shared` carries `["codex", "pi"]` and repeats the falsified "never reads `~/.agents/skills`" justification verbatim | Retitle to pi retention; `shared` carries `["pi"]`; cite the probe |
| `.trellis/tasks/08-09-thin-migration/design.md` | 26 | Pinned baseline "Only `shared` carries `retainVendoredFor: ["codex", "pi"]`" | `["pi"]` |
| `.trellis/tasks/08-10-thin-canary-conversion/prd.md` | 133-140 | Undeclared-codex usage described as a blocker, justified by "Codex cannot consume the machine-installed plugin at all" | It is now an advisory; the machine install serves Codex through `$HOME/.agents/skills` |
| `.trellis/tasks/08-10-thin-canary-conversion/prd.md` | 196-198 | "declaring `codex` retains 75 further machine targets ... 104 removals, not 179" | Declaring `codex` retains nothing; the removal count is 179 on both branches |
| `.trellis/tasks/08-10-thin-canary-conversion/prd.md` | 235-250 | Two acceptance criteria conditioned on a canary declaring `codex` — a 75-target residual, and "retention runs against a real consumer for the first time" | Neither applies; the marker no longer forces a per-consumer choice |

`08-10-thin-canary-conversion/prd.md:248`'s wider `retainVendoredFor` discussion
stays true through `pi`. `.trellis/tasks/archive/**` and shipped `CHANGELOG.md`
entries are historical and are not rewritten.

## Step 8 — CHANGELOG and release

New entry: the carve-out is retired on executed probe evidence; name the probe
file; state that consumers declaring `codex` no longer retain the shared slice.
Do not edit the 0.64.35 entry.

## Step 9 — full gate

```bash
make check
```

## Rollback points

- Through step 3: `git checkout` the touched files; nothing generated yet.
- After step 4: `git checkout` sources, re-run `make generate` to restore both
  artifacts.
- After merge: revert the tuple and regenerate. Pack-only, so no consumer needs
  action; a consumer converted meanwhile is not corrupted — its next refresh
  would retain rows it does not need.

## Out of scope

Editing `08-10-thin-canary-conversion`'s PRD, obtaining canary cohort
authorization, probing `pi`, and adding the `$CODEX_HOME/skills` family.
