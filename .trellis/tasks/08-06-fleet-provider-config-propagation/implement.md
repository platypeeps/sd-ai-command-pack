# Implementation plan

Order matters: the detector (steps 1–4) is independently shippable and
satisfies R3 plus the PRD's last acceptance criterion on its own. The
installer change (steps 5–6) depends on the artifact existing. Steps 1–4
are also the rollback point — reverting 5–6 leaves a working detector.

## Step 1 — Establish the historical digests

The generator must not invent history it cannot see. **As implemented**, the
seeding moved into the generator itself: the first time it sees a source it
derives that source's digests from `git log --follow`, and it refuses on a
shallow clone rather than seeding a partial list that would report holders of
the missing versions as customized. Once a source is recorded, its digests
are only appended to — never re-derived — so a later history rewrite cannot
retract a digest a consumer is actually holding.

This step therefore stays as an independent measurement: derive the expected
counts by hand and check the generator's output against them.

For each `if-not-exists` source, enumerate its distinct blobs:

```bash
for p in templates/.gito/config.toml templates/.prism/rules.json; do
  echo "== $p"
  git log --follow --format=%H -- "$p" | while read -r c; do
    git rev-parse "$c:$p" 2>/dev/null
  done | awk '!seen[$0]++'
done
```

Expect 3 blobs for `.gito/config.toml` and 5 for `.prism/rules.json`
(measured 2026-08-11). A different count is a signal to stop and re-read,
not to proceed — it means the file's history is not what the design assumed.

Convert each blob to the digest form the installer computes. Use the pack's
own `source_digest` helper rather than `sha256sum`, so the stored value is
byte-for-byte what the comparison will produce; a `git show <blob>` written
to a temp file and hashed through that helper is the safe route.

**Validation**: the current template's digest appears in each source's list,
and equals `source_digest` of the working-tree file.

## Step 2 — Write the generator

New `.github/scripts/generate-provider-config-history.py`, invoked from
`prepare-release.py` beside the existing generator chain.

Behavior:

- read `manifest.json`, select every record with `install == "if-not-exists"`;
- for each, compute the current template's digest;
- read the existing artifact; append the digest if absent, preserving order;
- add a `sources` entry for a source the artifact does not yet know, seeded
  from git history per step 1;
- record that digest as the entry's explicit `current`. **As implemented**,
  `current` is stated rather than inferred from the tail of `digests`: a
  template that reverts to bytes it shipped before adds no new digest, so the
  tail would then name the wrong content, and the consumer-side reader has no
  templates of its own to check against;
- write only `templates/docs/sd-ai-command-pack-provider-config-history.json`.
  **As implemented**, the root `docs/` copy comes from the self-sync
  `install.py . --force` that runs immediately after in `prepare-release.py`,
  which is why the generator is ordered before it rather than writing the
  mirror itself;
- never remove a digest or a source. Removal is what would silently re-arm
  the trap for a consumer sitting on the dropped version.

A source that disappears from the manifest keeps its entry. It costs a few
bytes and it keeps the artifact honest about what was once shipped.

**Validation**: run it twice on a clean tree; the second run leaves the
template byte-identical (`git diff --exit-code`).

## Step 3 — Register the artifact in the manifest

Add the `shared` / `doc` / `always` record from design D6a. Regenerate any
manifest-derived surface that enumerates payload files, by running the
generator that owns it rather than editing its output.

**Validation**: `make check` — specifically the template/root mirror gate and
the shipped-surface closure check, both of which read this file's two copies.

## Step 4 — The detector (R3)

`scripts/sd-ai-command-pack-install-audit.py:427` already places
`if-not-exists` targets in its `expected` set, so the target is inspected
today and only the verdict is missing.

Add: for each `if-not-exists` target present on disk, compute its digest and
compare against the artifact's list for that source. A digest matching
nothing is reported as a finding naming the target and stating that it
matches no shipped template. A digest matching an older entry is reported as
behind, naming that the current template differs. A missing or malformed
artifact is reported as an unavailable check, never as a pass.

Mirror the same two states into `sd-status fleet`'s per-consumer row. That
half is not a convenience: it is the only surface that can satisfy the PRD's
last acceptance criterion, because it reads consumer files from the pack
checkout and needs no artifact in the consumer (design D3). The audit half
reads the consumer's own copy, which only arrives by install — after which
step 6 has already refreshed the config — so the audit reports customized
consumers going forward, never the stale ones this task starts from.

**Validation**, two parts:

- Audit: run against a scratch checkout seeded with (a) the current template,
  (b) the 0.64.20 blob, (c) the 0.64.20 blob plus one added line, with the
  artifact placed at its target path. Expect clean / behind / unmatched.
- Fleet: run `sd-status fleet` read-only against the real registry before any
  installer change exists. Against the 2026-08-11 measurement in `prd.md`,
  expect for `.gito/config.toml` eight consumers behind and zero unmatched,
  and for `.prism/rules.json` one current, one behind, six unmatched. Any
  other split means the artifact's digests are wrong — most likely a blob the
  backfill missed — and step 6 must not proceed on them.

## Step 5 — `InstallStatus.REFRESHED`

Add the member to `installer/status.py:15` and thread it through every
consumer of that enum. Do not guess the call sites:

```bash
grep -rn "InstallStatus\.\|PRESERVED" installer/ scripts/ tests/
```

Every summary counter, report renderer, and exit-code mapping that
enumerates statuses must name the new one explicitly. A status that falls
through a dict lookup or an `if/elif` chain into an "other" bucket is the
defect to watch for here — it makes the feature invisible in the report that
justifies it.

**Validation**: `grep` shows no status dispatch that handles `PRESERVED`
without also handling `REFRESHED`.

## Step 6 — The seam

At `installer/fileops.py:403`, between the byte-equality check and the
`IF_NOT_EXISTS` early return:

```python
if file.install == IF_NOT_EXISTS and digest_of(current) in history_for(file):
    # the pack shipped these exact bytes; they are not a local decision
    ... write new_content ...
    return InstallResult(file, InstallStatus.REFRESHED, ...)
```

Constraints from the design, restated because each is a way to get this
wrong:

- `digest_of(current)` compares against what **this mode** would have
  written (D6), not the raw template.
- `FORCE_PRESERVED_TARGETS` is **not** an additional exclusion. Planning
  assumed those were a separate population; they are not. Both
  `if-not-exists` configs are also in that set, so excluding them would have
  made this inert for its entire population — measured during implementation
  as `preserved` where `refreshed` was expected. The predicate therefore
  guards on `file.install != IF_NOT_EXISTS` alone, and a named regression
  test (`test_force_preserved_membership_does_not_veto_a_shipped_default`)
  holds that line.
- No `--force` gate (D2).
- A missing or malformed artifact returns `PRESERVED` (D2), never a write.
- The symlink path at `:360` stays `PRESERVED`. Provenance vouches regular
  files only, so a refresh there would write a file the audit cannot then
  verify; a symlink at a config path is also itself a local decision, which
  is exactly the case this feature must not overwrite.

**Validation**: the seven tests named in design "Tests required", plus a full
`make check`.

## Validation commands

```bash
python3 -m pytest tests/ -k "install or fileops or audit"
python3 .github/scripts/generate-provider-config-history.py && git diff --exit-code
make check
```

`make check` runs the mirror and closure gates that this task's new payload
file is subject to; a green pytest run alone does not cover step 3.

## Review gates

- After step 4: the detector must report the three seeded states correctly
  before the installer is touched. If it cannot, the artifact's digests are
  wrong and step 6 would act on bad data.
- After step 6: run `install.py --check` against a scratch consumer copy in
  both fat and thin mode. A `vouched target content drifted` result means the
  digest/provenance/content triple that `payload_source_bytes` documents has
  been desynchronized — stop and fix, do not regenerate around it.

## Rollback points

- Steps 1–4 revert independently and leave a useful detector.
- Step 6 reverts alone; the artifact and detector stay.
- Nothing in this task mutates a consumer repository, so there is no
  external rollback to plan (design D7).

## Out of scope

Converting the eight fleet consumers. It requires explicit per-cohort user
authorization and is filed as a follow-up (see `prd.md` acceptance criteria
and design D7).
