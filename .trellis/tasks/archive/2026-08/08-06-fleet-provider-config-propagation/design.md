# Design: a delivery path for `if-not-exists` provider configs

## Scope / trigger

Cross-layer install contract change plus a new release-time generated
artifact, so this needs code-spec depth: signatures, a shipped schema, a
validation matrix, and named tests.

Pack-side only. See D7 for what this task deliberately does not do.

## The seam

`installer/fileops.py:403` is the whole problem, in three lines:

```python
    if destination.exists():
        current = destination.read_bytes()
        if current == new_content:
            return InstallResult(file, InstallStatus.UNCHANGED, ...)
        if file.install == IF_NOT_EXISTS or file.target in FORCE_PRESERVED_TARGETS:
            return InstallResult(file, InstallStatus.PRESERVED, ...)
```

`PRESERVED` is returned for two populations the installer cannot currently
tell apart:

1. a consumer that edited the file — must not be touched (R2); and
2. a consumer still carrying a *previously shipped* default it never
   touched — the population the fix exists for (R1).

Everything below is the machinery to separate those two, and nothing more.
`if-not-exists` stays `if-not-exists`; the constraint forbidding `always` is
respected because a file matching no shipped digest is still preserved.

The `or file.target in FORCE_PRESERVED_TARGETS` arm above is **not** a second
population. Both `if-not-exists` configs are also members of that set, where
it says the same thing their install policy already says — it exists to keep
`--force` from overriding them. Implementation confirmed this the hard way:
excluding `FORCE_PRESERVED_TARGETS` from the new predicate made the feature
inert for its entire population, reporting `preserved` on a scratch consumer
that should have refreshed. The predicate keys on `file.install` alone.

## D1 — Where prior shipped digests come from

**A shipped, release-generated digest history.** One JSON artifact, listed in
`manifest.json` like any other payload file, mapping each `if-not-exists`
source to the ordered set of sha256 digests that source has ever had in a
release.

Rejected alternatives:

- *Consumer-side record at install time* — ruled out by N1. Existing
  checkouts recorded nothing, and they are exactly the population needing
  the fix.
- *Release-tag lookup at install time* — requires `.git` and network or a
  full clone at install. A machine install under `~/.agents` has neither
  guaranteed. Fails closed in the wrong direction: no history means every
  consumer looks customized.
- *Digest list inside `manifest.json`* — workable, but `manifest.json` is
  the installed-file contract and is compared byte-for-byte by mirror gates;
  growing it once per release per template adds churn to a file many checks
  read. A separate artifact keeps that blast radius small.

Bootstrap is a one-off backfill from this repository's own history, which is
tractable because the population is tiny: `templates/.gito/config.toml` has
**3** distinct blobs across its whole history and `templates/.prism/rules.json`
has **5**, measured 2026-08-11 by enumerating `git rev-parse <commit>:<path>`
over `git log --follow`. The backfill is committed once; from then on the
release generator appends.

The generator runs inside `prepare-release.py`, beside the existing
`generate-command-surfaces` / `generate-plugin` / surface-partition steps, so
a release that changes a template cannot ship without recording it.

### Schema

`docs/sd-ai-command-pack-provider-config-history.json`, schema version 1
(generated at `templates/docs/...` and mirrored to the repo root — see D6a):

```json
{
  "schemaVersion": 1,
  "sources": {
    "templates/.gito/config.toml": {
      "target": ".gito/config.toml",
      "current": "8caa6fb1...",
      "digests": ["e3b0c442...", "8caa6fb1..."]
    },
    "templates/.prism/rules.json": {
      "target": ".prism/rules.json",
      "current": "8caa6fb1...",
      "digests": ["cea5089e..."]
    }
  }
}
```

- `digests` is append-only and includes the *current* template's digest.
  Order is oldest-first and carries no meaning beyond provenance; for the
  installer, membership is the only thing read.
- `current` names the digest of the template as of this release. It was added
  during implementation for the consumer-side reader (D3), which has no
  templates of its own to compare against and so cannot derive currency from
  membership alone. It is stated rather than taken from the tail of
  `digests`, because a template that reverts to bytes it shipped before adds
  no new digest and would leave the tail naming the wrong content.
- The key set is derived from the manifest's `if-not-exists` records at
  generation time, not hand-maintained. R4 is structural, not a promise: a
  third `if-not-exists` file joins automatically.

## D2 — What the installer does with it

At the seam, before returning `PRESERVED`:

| current file digest | action | status |
|---|---|---|
| equals the current template | nothing | `unchanged` (today's behavior) |
| in the history, not current | write the current template | **`refreshed`** (new) |
| in no history entry | nothing | `preserved` (today's behavior) |
| history artifact missing or malformed | nothing | `preserved`, plus a named diagnostic |

`refreshed` is a new `InstallStatus` member rather than a reuse of `updated`
or `overwritten`. Those two already mean "an `always` file was replaced" and
"a conflict was forced"; folding a third meaning into either makes every
existing report ambiguous about whether a local decision was discarded. The
whole value of this feature is that a reader can tell the difference.

A missing or malformed history fails **closed** — toward `preserved`. The
failure mode of the opposite choice is overwriting a customized config, which
is exactly R2.

The symlink branch earlier in `install_file` keeps returning `PRESERVED`
unconditionally. A symlink at a config path is itself a local decision, and
provenance vouches regular files only — refreshing there would write a file
the install audit could not subsequently verify.

This is not gated on `--force`. A file that byte-matches something the pack
itself shipped is not a local decision, so refreshing it is ordinary install
behavior; requiring `--force` would mean the fix reaches nobody who does not
already know they need it.

## D3 — Reporting what stays preserved (R3)

After D2, a surviving `preserved` on an `if-not-exists` target means one of:
the consumer customized it, or it holds a variant this pack never shipped.
Either way it is now a *decision*, not an accident, and R3 wants it visible.

Two surfaces, both read-only:

- `scripts/sd-ai-command-pack-install-audit.py` gains a finding naming the
  target, its digest, and that it matches no shipped template — so the
  consumer's own CI shows it.
- `sd-status fleet` reports the same per consumer, so one command answers
  "who is behind on a provider config".

The last PRD acceptance criterion asks that a stale consumer be visible
*before* the change lands, and only one of these two surfaces can deliver
that. The audit reads the consumer's own copy of the artifact, which arrives
by install — and by the time an install has delivered it, D2 has already
refreshed the config, so the audit can never observe the stale state it was
meant to report. `sd-status fleet` has no such circularity: it runs from the
pack checkout, reads the eight consumer files directly, and needs neither an
installer change nor an artifact in the consumer. The fleet surface is what
satisfies that criterion; the audit surface is what keeps a *customized*
consumer visible afterwards, in its own CI, which is R3's other half.

This also means the fleet surface must land before the installer change, not
alongside it — see `implement.md`'s step ordering.

## D4 — Added-lines divergence is customization, not a merge

Open question resolved: a config whose content is the old template *plus*
local lines is `preserved` and reported, never merged.

A three-way merge over TOML and JSON means owning conflict semantics for two
formats, and getting it wrong writes a broken provider config into a working
repository. The reported-preserved path costs a human one manual merge and
cannot corrupt anything.

The reported population is not zero. Measured 2026-08-11, six of eight
consumers' `.prism/rules.json` match no blob this repository has ever
shipped — `rwbp-coordinator` carries its own `required` rules and its own
focus ordering. Those six are the standing evidence that R2 protects real
work, and they are exactly what D3's report is for. Merging them
automatically would be the worst version of this feature: a JSON `required`
array is a list of review rules a team wrote, and silently unioning ours into
it changes what their reviewer enforces.

## D5 — Content removal is acceptable here, by construction

The 0.64.21 change both adds and removes lines, so "the new template drops a
line the consumer depends on" is not hypothetical. It is still fine: the
refresh only ever runs when the consumer's bytes are exactly what this pack
shipped. The consumer expressed no preference — the pack did — so replacing
it with the pack's current preference restores intent rather than overriding
one. The moment a consumer expresses a preference, D2's third row applies and
nothing is touched.

## D6 — Thin mode: measured, and still not assumed

`payload_source_bytes(file, source, is_thin=is_thin)` rewrites payload text
during a thin install. If either config's bytes were rewritten, the digest on
disk would not be the digest of the template, history membership would silently
never match, and the mechanism would be dead in exactly the mode the fleet is
converting to.

Measured 2026-08-11 by calling
`rewrite_text(text, profile=THIN_PROFILE, key=target)` on both templates:

```text
.gito/config.toml identical
.prism/rules.json identical
```

Neither config carries a reference the thin profile rewrites, so today the
template digest is the installed digest in both modes. That is a property of
today's file contents, not of the design — one added `scripts/` citation in a
future template would break it silently.

So the comparison is still written against whatever the current mode would
have written, never unconditionally against the raw template, and a test
covers both modes. The measurement says the correct implementation costs
nothing today; it does not say the shortcut is safe.

## D6a — Where the artifact lives, and who reads it

Two readers, one file:

- `install.py` reads it from the **pack source tree**. The installer always
  runs from a pack checkout or the machine payload, so it needs no consumer
  copy for D2.
- the install audit reads it from the **consumer**, because a fat consumer's
  vendored `scripts/sd-ai-command-pack-install-audit.py` runs in that
  consumer's own CI with no pack checkout in reach. Under thin mode the same
  script resolves from `~/.agents/bin` against the machine payload.

The second reader is what puts the artifact in `manifest.json`, as a `shared`
`doc` with `install: always`:

```json
{"platform": "shared", "kind": "doc",
 "source": "templates/docs/sd-ai-command-pack-provider-config-history.json",
 "target": "docs/sd-ai-command-pack-provider-config-history.json",
 "install": "always"}
```

`docs/` currently holds exactly one shipped target, so this is the second.
The pack repo's template/root mirror gate requires the generated file to exist
byte-identically at both `templates/docs/...` and `docs/...`. **As
implemented**, the generator writes only the template and the root copy comes
from the self-sync `install.py . --force` that already runs later in
`prepare-release.py` — one writer, one mirroring mechanism, and the manifest
record above is what makes the install produce it. That ordering constraint
(generator strictly before the self-sync install) is asserted in
`tests/test_release_prep.py`, and the mirror itself is part of this task's
validation rather than a surprise at release time.

## D7 — Scope boundary

This task ships the mechanism and the detector. It does **not** convert the
eight consumer repositories, even though the PRD's fifth acceptance criterion
is written that way: mutating repositories outside this one requires explicit
per-cohort user authorization that the autonomous run does not hold. That
criterion moves to a follow-up task, and this PRD is amended to say so.

The split is also the safer order. The detector lands first and proves who is
actually affected, so the conversion runs against measured state rather than
a table taken on 2026-08-06.

## D8 — Nothing depends on consumers keeping the blanket exclusion

The PRD's fifth open question, answered by enumeration rather than memory.
Every non-task reference to `".trellis/**"` in this repository:

- `CHANGELOG.md` — two historical entries describing the 0.64.21 narrowing.
- `tests/test_review_scope.py:1538` — the constant
  `GITO_TRELLIS_FORBIDDEN_EXCLUSIONS`, which asserts the blanket entry is
  *absent*. It is a negative control for the narrow shape, not a dependency
  on the broad one.

No script, skill, spec, or gate reads the blanket entry or assumes a consumer
has it. Narrowing it fleet-wide breaks nothing.

The one behavioral change is the intended one: a task-only or spec-only diff
that previously reached the provider empty now carries content, so it costs a
real local-provider round where it used to cost a dead end. That is the fix,
not a side effect.

The enumeration also turned up the gap this task's detector fills.
`test_gito_config_templates_are_installed` (`tests/test_review_scope.py:1554`)
runs `assert_gito_trellis_exclusion_is_narrow` against
`config_files[0].source` — the **template** — and nothing anywhere asserts the
shape of a consumer's installed copy. The pack has always guaranteed what it
ships and never what consumers hold, which is exactly how eight consumers came
to sit on a superseded default with every check green.

## Validation matrix

| condition | expected |
|---|---|
| target byte-identical to current template | `unchanged`, no write |
| target byte-identical to an older shipped digest | `refreshed`, file now equals current template |
| target equals old template plus one added line | `preserved`, file byte-unchanged, reported |
| target absent | `created` (unchanged behavior) |
| history artifact absent | `preserved`, diagnostic names the missing artifact |
| history artifact malformed or wrong schema version | `preserved`, diagnostic names the reason |
| thin install, target matches an older digest | `refreshed`, mode-correct content written |
| a third `if-not-exists` record added to the manifest | generator includes it with no code edit |

## Good / base / bad cases

All three are real fleet rows as of 2026-08-11, not invented scenarios:

- **Good**: `hoa-manager`'s `.gito/config.toml` matches an older shipped
  blob; a normal install refreshes it to the narrowed exclusion list and
  reports `refreshed`. Seven other consumers are in the identical state.
- **Base**: `sd-github-review`'s `.prism/rules.json` already equals the
  current template; `unchanged`, nothing written.
- **Bad**: `rwbp-coordinator`'s `.prism/rules.json` matches no shipped blob —
  it holds that team's own `required` rules. Nothing is written, and the
  report names it as matching no shipped template. A run that overwrites it is
  the defect this design exists to prevent, and five more consumers are in the
  same state.

## Tests required

1. `refreshed` on an older-digest match, asserting both the status and the
   resulting bytes.
2. `preserved` on a one-line-added file, asserting the bytes are unchanged.
3. `preserved` plus diagnostic when the history artifact is missing, and
   again when its `schemaVersion` is unknown.
4. Both statuses under a thin install, proving D6's rewrite question is
   actually handled rather than assumed.
5. Generator test: an added `if-not-exists` manifest record appears in the
   generated history with no other edit.
6. Generator idempotence: running it twice changes nothing; changing a
   template appends exactly one digest.
7. Detector test: a preserved-and-unmatched target appears in the audit
   output with its target name.

## Wrong vs correct

### Wrong

```python
if file.install == IF_NOT_EXISTS and force:
    write(new_content)          # --force now discards local customization
```

Reintroduces exactly the failure R2 exists to prevent, and hides it behind a
flag people already pass habitually.

### Correct

```python
if file.install == IF_NOT_EXISTS:
    if source_digest(current) in shipped_history_for(file):
        write(new_content)      # the pack shipped this; it is not a decision
        return InstallResult(file, InstallStatus.REFRESHED, ...)
    return InstallResult(file, InstallStatus.PRESERVED, ...)
```

The predicate is provenance, not a flag: replace only what this pack itself
put there.
