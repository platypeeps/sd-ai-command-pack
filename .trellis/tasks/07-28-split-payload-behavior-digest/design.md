# Design — split the candidate payload digest

## Scope boundary

`payload_digest` and `validate_candidate_ledger` in
`scripts/sd_ai_command_pack_fleet_lib.py` (`:663` and `:728`), the candidate
ledger schema, and the one committed ledger instance at
`docs/fleet/candidate-validation.json`. No change to fleet refresh, consumer
install, or the manifest format itself.

## What the digest actually covers

```python
digest.update(b"sd-ai-command-pack-candidate-payload-v1\0")
digest.update(json.dumps(manifest, sort_keys=True, ...).encode("utf-8"))   # :683
for source in sorted(sources):                                             # :692
    digest.update(source.encode("utf-8"))
    digest.update(b"\0x\0" if payload.executable else b"\0-\0")
    digest.update(hashlib.sha256(payload.content).digest())
```

Two independent inputs: the **whole manifest document**, and the **content of
every source**. Excluding doc *content* from the second loop does not stop a doc
change from moving the digest, because adding, removing, or retargeting a doc
entry changes the manifest blob hashed at `:683`. **The manifest must be projected
to behavior-relevant fields before hashing, or R3 does not work.** This is the
part the finding does not mention and it is the substantive design decision here.

## Measured premise — R3 as written covers 3 files, not "documentation"

`manifest.json` carries 754 entries:

| kind | count |
|---|---|
| skill | 411 |
| command | 198 |
| workflow | 66 |
| prompt | 44 |
| script | 26 |
| config | 5 |
| doc | 3 |
| managed-block | 1 |

Only three sources are `kind: "doc"`:

- `templates/docs/SD_AI_COMMAND_PACK.md`
- `templates/.github/PULL_REQUEST_TEMPLATE.md`
- `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md`

The two restamps the PRD cites are consistent with these — `38502b11` is
literally *"restamp candidate ledger for doc-inclusive payload"* and `fe69f4dc`
follows planning-finalization work, which is the third file. So the premise holds.

**But the third file is not informational.** `planning-adversarial-review.md` is a
contract agents execute; the repo's own `.claude/rules/` points at it as binding.
Classifying it alongside a PR template means a consumer could receive a changed
adversarial-review contract with no revalidation. The 411 `kind: "skill"` entries
are prose too, and nobody would argue those are informational — in this
architecture prose *is* behavior. `kind` is therefore the wrong discriminator on
its own.

**Recommendation:** behavior digest excludes `kind: "doc"` **minus an explicit
behavioral-doc allowlist**, and `planning-adversarial-review.md` starts on that
allowlist. Cheaper and more honest than reclassifying it, and the allowlist is the
place a future reviewer looks when asking "why did this doc trigger revalidation?"

## Contract

Two digests, each with its own domain separator so they can never collide:

- `behavior:` `b"sd-ai-command-pack-candidate-behavior-v1\0"` — projected manifest
  plus content of every non-excluded source.
- `content:` `b"sd-ai-command-pack-candidate-content-v1\0"` — the excluded set.

Manifest projection for the behavior digest: keep `source`, `target`, `kind`,
`platform`, `install`, `anchor` for included entries only; keep top-level
`schemaVersion`, `version`, `requiresTrellis`. Drop `description` and `license`
— prose fields that move without behavioral meaning.

`validate_candidate_ledger` hard-fails on behavior mismatch (today's behavior at
`:743-751`) and records content mismatch without erroring. Both digests stay in
the ledger so a content change remains auditable — PRD R4.

**`packVersion` is a separate gate and stays untouched.** `:742-750` checks
`packVersion`, `payloadDigest`, and `fleetManifestDigest` as three independent
fields, so splitting the payload digest does nothing to the first. That is
correct and deliberate: `version` moves only at a `release:` commit — verified
against `7bc8cd40` and `26167356`, two doc-only commits that changed
`manifest.json` without touching its `version` field — and a release restamp is
expected work. The problem this task removes is the *mid-cycle* restamp, where a
typo fix moves `payloadDigest` alone while `packVersion` is stable. Keeping
`version` inside the behavior projection is therefore redundant rather than
harmful; it is retained so the projection stays a strict subset of the manifest
document and needs no special-casing.

## Compatibility

`CANDIDATE_LEDGER_SCHEMA_VERSION` is `2` (`fleet_lib.py:19`) and the validator
rejects any other value at `:736`. Adding fields bumps it to `3`, which
invalidates every existing ledger by construction. That is correct and intended,
but it means **one forced restamp at rollout** — the last one. Sequence it so the
restamp and the schema bump land together; a bump without a restamp red-lights
the fleet gate.

Consumers do not read the ledger; it gates the pack side only. No consumer-visible
change.

## Rollout and rollback

Land behind the schema bump in a single change: split, projection, allowlist,
validator, restamped ledger. Rollback is reverting that commit plus restoring the
previous ledger blob — both are in the same commit, so a plain revert is
sufficient.

## Risk

The failure mode to avoid is a behavior digest that is too *narrow*: a shipped
script change that does not move it would let a real behavioral regression reach
consumers past a green gate. Test the negative direction explicitly, not just the
doc-edit case.
