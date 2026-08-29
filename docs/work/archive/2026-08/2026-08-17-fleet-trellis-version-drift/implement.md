# Implementation: fleet Trellis version drift

Two legs. Leg A is code in this repository and is the whole of the work that
happens here. Leg B is uptake in eight external repositories and produces a
ledger, not a diff. Leg A lands first — Leg B's verification quotes the report
Leg A fixes.

## Step 0 — re-measure, do not trust `design.md`

`design.md`'s table is from 2026-08-18 and is already historical by the time this
runs. The dirty set moved between the PRD's snapshot and the design's; assume it
moved again.

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json > /tmp/fleet-before.json
python3 - <<'PY'
import json
d = json.load(open("/tmp/fleet-before.json"))
for r in d["repositories"]:
    rep = r.get("report") or {}
    g = rep.get("git") or {}
    print("%-24s %-8s %-9s %-10s %s" % (
        r["name"], (rep.get("versions") or {}).get("trellis"),
        (r.get("pin") or {}).get("version"),
        (g.get("workingTree") or {}).get("state"), g.get("branch")))
PY
cat .trellis/.version                       # the target
```

Record this as the ledger's before-column. Keep `/tmp/fleet-before.json`; Step 5
diffs against it.

## Leg A — make the drift visible

### Step A1 — carry the target into the report

In `collect_fleet` (`scripts/sd-ai-command-pack-status.py:3934`), read this
repository's vendored version beside the existing pack target and add it to the
returned mapping:

```python
trellis_target = read_version(pack_root / ".trellis/.version")
```

Add `"targetTrellisVersion": trellis_target,` to the returned dict next to
`"targetPackVersion": target,` (`:4047`). `read_version` (`:612`) already returns
`str | None`, so an unreadable file is `None` and every consumer of the field
must handle that — do not substitute a placeholder string here.

Do **not** bump `SCHEMA_VERSION` (`:31`). It reads `2`, and `releaseTarget` and
`machineScope` are both present in a version-2 report, so the file's established
rule is that an additive top-level field does not move it. `tests/test_status.py:395`
pins `report["schemaVersion"] == 2`; that assertion must still pass unchanged. No
existing field changes meaning.

### Step A2 — print it in every row

In `render_fleet` (`:4064`), append one field to the row built at `:4141-4147`,
outside the thin/fat branch so both modes get it:

```python
f"trellis {versions.get('trellis') or 'unknown'}; "
```

Place it directly after `pack_label` so the two version facts read together. The
`or 'unknown'` mirrors the `or 'none'` already used for the fat pack label — a
consumer whose `.trellis/.version` is missing reports `unknown`, never a blank or
an omitted field.

Do **not** touch the `attention` computation at `:4070-4090`. `design.md` records
why, and the invariant comment at `:4082` is the thing being preserved.

### Step A3 — emit the skew record

In `fleet_step_records` (`:3722`), take the target as a new keyword argument —
and pass it from the single call site in `collect_fleet`, which already computes
it in Step A1 — then add one record after the existing pin/machine skew rows:

```python
drifted = [
    item["name"]
    for item in available
    if item["report"]["versions"].get("trellis") != trellis_target
]
```

Guard it on `trellis_target is not None` — with no readable target there is
nothing to compare, and a row claiming eight consumers drifted from `None` is
worse than silence. That guard is not theoretical: `tests/test_status.py`
already calls `collect_fleet` with fixture pack roots (`:2712`, `:2801`,
`:2878`) that need not contain `.trellis/.version`, so existing tests exercise
the `None` path on day one. Nothing calls `fleet_step_records` directly, so the
new keyword argument breaks no caller. Emit at `FLEET_STEP_RANK_SKEW` (`:148`), naming the
consumers, in the same imperative shape as the neighbouring rows:

> `Upgrade Trellis on <names> to the vendored version (<target>).`

`fleet_follow_ups` (`:3914`) derives `F-*` rows from the complete record set, so
this reaches the follow-up list without further wiring. Verify that rather than
assume it.

### Step A4 — tests

In `tests/test_status.py`. Its fixture already writes `.trellis/.version` with
`0.6.7` (`:145`), so a drift case needs only a differing pack root.

Four cases, and the third is the one that catches a lazy fix:

1. A thin consumer row contains `trellis <version>`.
2. A **fat** consumer row contains it too — `design.md` corrects the PRD here;
   the silence was never mode-specific, and a fix that only touches the thin
   branch would pass a thin-only test while leaving half the fleet silent.
3. A consumer at the target emits **no** skew record, and one below it emits
   exactly one naming that consumer. Assert on the record set, not on the
   truncated human list.
4. An unreadable `.trellis/.version` on a consumer renders `trellis unknown`;
   an unreadable one on the *pack root* emits no skew record at all.

### Step A5 — local gate

```bash
.venv/bin/python -m unittest tests.test_status -q
make check
git status --short
```

`make check` is `test lint audit full-check` (`Makefile:106`). No payload under
`templates/**` changes here, so there is no `manifest.json` bump, no `make sync`,
no `make generate`, and no candidate-ledger refresh. If `git status --short`
shows a generated file moving, something in this step was wrong — stop rather
than committing it.

### Step A6 — ship

Ordinary single-PR flow for this repository. This PR contains the collector
change and its tests and nothing else; it is not part of either fleet campaign
and does not wait on one.

## Leg B — the eight upgrades

### Step B1 — ownership, per lane, at lane start

Re-run Step 0's measurement immediately before each lane and exclude any
consumer that is dirty *at that moment*. Never carry Step 0's snapshot forward,
never stash/reset/clean/commit in another checkout, and record every exclusion
with the timestamp that justified it. This is the same rule
`08-08-fleet-one-path` Step 6 Gate C applies, for the same reason.

A consumer on a feature branch is a separate question from a dirty one. The
branch is cut from the consumer's default branch either way, so a feature branch
does not by itself make the write unsafe — but if that branch is an open
**pack-refresh** PR, `design.md`'s interaction section applies: cut from the
default branch, never from the refresh branch, or the merged diff carries both
legs and violates requirement 2.

### Step B2 — order

Read the cohorts from `docs/fleet/consumers.json`'s `rolloutPolicy` at run time —
canary sequential, post-canary bounded, final sequential. Do not transcribe them
into the ledger and work from the copy.

### Step B3 — one consumer

Per consumer, in its own checkout, on a branch cut from its default branch:

1. Run the Trellis update to the target from Step 0.
2. Confirm the diff touches only Trellis-owned paths — no pin, no provider
   config, no bookkeeping. `git diff --name-only <default>...HEAD` and read it.
   A stray path means stop, not amend-and-continue.
3. Review against `.trellis/spec/tooling/vendored-trellis-compatibility.md`.
   That spec is the checklist; a lane that cannot answer it stops.
4. Open the PR, let that repository's own gates run, merge under them.
5. Verify uptake and quote **both** surfaces. The PRD's acceptance criterion
   names the JSON field, and the human row is what Leg A added; quoting only
   one leaves the other unproven:

```bash
T=scripts/sd-ai-command-pack-toolchain.sh
bash $T run-python -- scripts/sd-ai-command-pack-status.py fleet --json \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print([(r['name'],r['report']['versions']['trellis']) for r in d['repositories'] if r['name']=='<consumer>'])"
bash $T run-python -- scripts/sd-ai-command-pack-status.py fleet | grep '<consumer>'
```

If an upgrade breaks the consumer, record it and stop **for that consumer**. Do
not repair the incompatibility here — `07-09-trellis-version-compatibility` owns
any contract change, per the PRD's out-of-scope section.

### Step B4 — the ledger is the deliverable

One row per consumer, eight rows, no omissions: before-version, after-version or
the reason it was skipped with the measurement time, and the PR link where one
was opened. A consumer with no row is not a passing consumer. A uniform fleet is
explicitly not the deliverable (PRD requirement 1).

## Step 5 — close out

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json > /tmp/fleet-after.json
python3 - <<'PY'
import json
b = {r["name"]: ((r.get("report") or {}).get("versions") or {}).get("trellis")
     for r in json.load(open("/tmp/fleet-before.json"))["repositories"]}
a = {r["name"]: ((r.get("report") or {}).get("versions") or {}).get("trellis")
     for r in json.load(open("/tmp/fleet-after.json"))["repositories"]}
for name in b:
    print("%-24s %s -> %s" % (name, b[name], a.get(name)))
PY
```

Every row moved to the target or has a recorded reason. A skipped consumer is
not a rolled-out one; report the ledger, not a summary sentence.

## Rollback points

- After A1-A3: one function set plus tests in one commit; revert it.
- After A6: revert the merged PR here. No consumer is affected — Leg A writes
  nothing outside this repository.
- After each B3: reverted in that consumer's repository by its owner. The legs
  revert independently, which is the entire reason requirement 2 forbids a
  combined PR.

## Validation

```bash
.venv/bin/python -m unittest tests.test_status -q
make check
git status --short                # this repo only; no consumer touched by Leg A
```

Plus, for Leg B, the per-consumer quoted JSON field and `fleet` row from Step B3
item 5, and the before/after table from Step 5.

## Out of scope

- Upgrading Trellis in this repository or choosing the target version.
- The pack pin leg (`08-08-fleet-one-path`), review lane
  (`08-08-copilot-request-policy`), CI shape (`08-08-ci-lane-cost`).
- Adding Trellis to the `attention` counter — `design.md` records why, and doing
  it requires a matching JSON skew field to keep the `:4081` invariant true.
- The `comparison: "unknown"` gap recorded at the end of `design.md`. It is real
  and it is the pack leg's.
