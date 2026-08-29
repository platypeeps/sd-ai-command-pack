# Design — make release-prep reach a changed candidate validator

Child 2 of `08-09-thin-migration`, contract C-F. Pack-internal: nothing here
touches a consumer repository.

Scope narrowed after planning review; see `prd.md` and the concern ledger in
D7a. The thin-shape half is `08-11-thin-candidate-loop-shape`.

## D1. Bind the validator's own source into the ledger

**Decision: bind a validator digest into the candidate ledger. Rejected: a
`--force-validation` flag.**

A flag is opt-in, and the caller that would have to remember it is
`prepare-release.py` — the same file whose early return created the defect. A
flag moves the failure from "the loop silently skipped" to "the loop silently
skipped unless somebody typed a flag", which is the same failure with a longer
name. Digest binding makes the skip unreachable after a validator edit, with no
operator memory in the path, and it is the only one of the two that acceptance
criterion 1 can measure.

### What the tuple contains, and what it deliberately does not

```python
CANDIDATE_LEDGER_SCHEMA_VERSION = 3          # was 2

# The validator source the payload digest cannot see.
#
# Measured 2026-08-11: this file has no manifest.json row and no templates/
# twin -- zero rows match it -- so `payloadDigest` is blind to it, and that
# single omission is the entire reachability defect.
#
# `scripts/sd_ai_command_pack_fleet_lib.py` is deliberately NOT here. It looks
# like a second blind spot and is not one: its row is
# source=templates/scripts/sd_ai_command_pack_fleet_lib.py,
# target=scripts/sd_ai_command_pack_fleet_lib.py, so the authoritative
# template is payload-declared and editing it already moves `payloadDigest`.
# Adding it would hash a `make sync` mirror -- a file regenerated from the
# real source -- which is a second, weaker answer to a question `payloadDigest`
# already answers correctly.
CANDIDATE_VALIDATOR_SOURCES: tuple[str, ...] = (
    "scripts/sd-ai-command-pack-fleet-candidate-check.py",
)
```

### Signatures

```python
def candidate_validator_digest(source_loader: Callable[[str], bytes]) -> str:
    """sha256 over CANDIDATE_VALIDATOR_SOURCES, path-qualified and ordered.

    Takes a loader rather than a root: see D1a. The loader raises for a
    missing source; this function never substitutes a default.
    """

def filesystem_candidate_validator_digest(root: Path) -> str:
    """Working-tree wrapper. The only form the two working-tree sites use."""

def validate_candidate_ledger(
    ledger: Mapping[str, Any],
    *,
    expected_version: str,
    expected_payload_digest: str,
    expected_fleet_digest: str,
    expected_validator_digest: str,        # new, keyword-only, required
    consumers: list[FleetConsumer],
) -> list[str]:
```

**The primitive takes a loader; the wrapper takes a root. Nothing takes both.**
Planning review found the first draft using both spellings interchangeably;
they are now distinct names with distinct types, so the confusion cannot recur
silently.

### Composition, and the one place it departs from `payload_digest`

Composed as `payload_digest` composes sources (`fleet_lib.py:736-741`): for
each path in sorted order, feed the path bytes, a separator, and
`sha256(content)`. Sorting and path-qualification are inherited for the same
reasons — order independence and resistance to a rename that swaps two files'
contents.

**The executable marker is not included**, and `payload_digest` includes it
(`fleet_lib.py:739`). That difference is deliberate and measured: the
candidate validator is mode `-rw-r--r--` and is invoked as
`sys.executable <path>` (`surface-check.py:679`), never as a bare
executable, so its permission bit changes no behavior. Hashing it would make
`chmod +x` invalidate a ledger whose validator behaves identically. The
payload digest is right to include it for files that *are* executed directly;
this digest is right to omit it.

### Contract

| Field | Type | Source |
|---|---|---|
| `validatorDigest` | `"sha256:<64 hex>"` | `candidate_validator_digest(loader)` |

### Validation and error matrix

| Condition | Result |
|---|---|
| `schemaVersion == 2` (pre-upgrade ledger) | `candidate ledger schemaVersion must be 3` → stale → validator runs |
| `validatorDigest` absent | mismatch → stale → validator runs |
| `validatorDigest` present, differs | mismatch → stale → validator runs |
| source unreadable in the working tree | `FleetConfigError`, release-prep fails — never "assume unchanged" |
| source absent at a historical commit | named error, fail closed — never fall back to the working tree |
| all four fields match | ledger current → documented skip stands (PRD requirement 3) |

**No new finding code.** A mismatch surfaces through the existing
`provenance.candidate-stale` finding (`surface-check.py:696`) against the same
`docs/fleet/candidate-validation.json` path. `_candidate_refresh_required`
(`prepare-release.py:109-160`) validates the *exact* shape of that one finding
and raises on anything else, so a new code would fail release-prep with
"surface closure contains a non-candidate finding" rather than triggering
validation. Reusing the code is a compatibility requirement, not a shortcut.

## D1a. Why a loader seam and not a root path

`validate_candidate_ledger` has three call sites, and they do not all read the
working tree:

| Call site | Ledger being validated | Correct digest source |
|---|---|---|
| `fleet-candidate-check.py:399` (`check_ledger`) | the one it is about to write | working tree |
| `release_identity.py:333` | current ledger | working tree |
| `release_identity.py:283` (`verify_candidate_ledger_at_commit`) | **a ledger at `commit_sha`** | **blobs at that commit** |

The third is why the first draft of this design was wrong. That call already
pairs its ledger with `payload_digest_at_commit(repo, commit_sha, manifest)`,
reading blobs from git rather than the working tree, precisely so a release's
recorded evidence is checked against the tree that produced it. A digest
function reading the working tree would compare a historical ledger against
today's validator: the check would break the moment the validator changed after
the release commit, and the failure would read as tampered evidence rather than
a design error.

The loader seam makes that site expressible —
`candidate_validator_digest(loader_at_commit(repo, commit_sha))` — reusing the
mechanism `payload_digest_at_commit` already uses.

## D2. Where the edit goes

`templates/scripts/sd_ai_command_pack_fleet_lib.py` is the authoritative source
(`CONTRIBUTING.md:143`); `scripts/sd_ai_command_pack_fleet_lib.py` is a mirror
that `make sync` (`Makefile:35`) rewrites from it. **The edit goes in the
template**, and `make sync` propagates it. Editing the mirror is how the
mechanism gets erased before it is ever validated — planning review caught the
plan doing exactly that.

`scripts/sd-ai-command-pack-fleet-candidate-check.py` has no template and is
edited in place. That asymmetry is the defect's own cause and is worth stating
plainly rather than smoothing over.

## D3. Where the digest is produced

`current_evidence` (`fleet-candidate-check.py:323`) already computes the
expected version, payload digest, fleet digest, and consumers, and is the
single producer feeding **both** `check_ledger` (line 386, what the surface
check shells out to) and `ledger_content` (line 337, which writes the ledger).
The validator digest becomes a fifth return value there, so the written field
and the checked field come from one expression. Computing them in two places is
how they drift.

## D4. Compatibility and rollout

The ledger is source-owned (`docs/fleet/candidate-validation.json`) with three
direct `validate_candidate_ledger` call sites (D1a), the last reached from
`create-release-tag.py:124` with the head SHA and from
`release_identity.py:403` with a tag's commit.

The surface check is **not** a fourth call site, and the difference is load
bearing. It shells out to `fleet-candidate-check.py --check-ledger` as a
subprocess and turns a nonzero exit into the finding
(`surface-check.py:673-700`). So the comparison runs inside the very script
whose digest is being compared: an edit changes both its behavior and its
digest, and the staleness probe executes the edited code. That self-consistency
is what makes the mechanism airtight rather than circular, and it is why no
separate wiring into the surface check is needed. The subprocess runs under a
60-second timeout, which one file read does not threaten.

**A schema bump looks like it should invalidate every past release's ledger,
and does not.** The tag path is gated at `release_identity.py:395-400`, which
requires the tag's payload digest to equal the current checkout's *before* the
ledger is read; an older tag fails there, on the payload, and never reaches the
schema comparison. The head-SHA path validates a ledger written by the code
being released. Both only ever see a ledger whose schema matches the constant
checking it. Raised as blocking during review and rebutted on that evidence;
recorded so it is not re-derived.

The first `make release-prep` after this lands sees `schemaVersion == 2`, calls
the ledger stale, runs the validator, and rewrites it at 3. That run is the
migration.

**Rollback** is `git revert`: the schema-3 file goes stale against the reverted
constant, release-prep runs the reverted validator once, and rewrites at 2. The
rollback path exercises the same mechanism as the rollout, which is why no
rollback-only code exists.

## D5. Test plan

New `tests/test_fleet_candidate_validator_digest.py`: digest stability;
path-qualification; the six rows of D1's error matrix; **the historical-source
test that fails when the commit-scoped site is fed the working tree** (PRD
criterion 3); and fail-closed on a source missing at a commit.

Extended `tests/test_release_prep.py:90`: the skip still holds when all four
fields match, and no longer holds when only the validator digest differs.
Extend, never delete — it is the coverage behind PRD requirement 3.

**Fixtures (concern C-7).** Existing tests build trees that contain no
validator source: `test_fleet_candidate.py:388` constructs a temporary manifest
root and calls `current_evidence`/`check_ledger`, and
`test_release_identity.py:87,117` commits a minimal repository whose ledger has
no `validatorDigest`. Fail-closed loading breaks both. They are updated to
materialize the validator source, and the missing-source path gets its own
explicit test rather than being discovered as an unrelated failure.

Mutation testing over the digest comparison is mandatory
(`PYTHONDONTWRITEBYTECODE=1`): a comparison that passes when digests differ
reproduces the exact defect being fixed.

## D6. How each acceptance criterion is proven

| Criterion | Proof |
|---|---|
| Changed validator + current ledger still validates | Edit the validator, leave the ledger, `make release-prep`, observe it run |
| Skip survives an unchanged tree | Second consecutive run reports the ledger current |
| Every call site's digest matches its ledger's tree | Test that fails when the historical site is fed the working tree |
| Missing historical source fails closed | Explicit test on a commit lacking the source |
| Mutation killed | Mutant accepting differing digests dies |
| `make check` | Run it |

## D7a. Planning review concern ledger (2026-08-11)

Two lanes ran: the host's own, and this repository's Codex appendix lane
(`docs/planning-adversarial-review-codex.md`). Rounds 1–2 host, round 3 Codex.

| ID | Severity | Concern | Disposition |
|---|---|---|---|
| C-1 | critical | `--thin` without `--consumer` is rejected; with it, `flip_registry_mode` (`installer/thin.py:967-976`) flips a real registry entry to `thin`, mutating the source checkout | **deferred** to `08-11-thin-candidate-loop-shape` |
| C-2 | critical | A candidate install dirties the clone, `thin-resweep.py:1723` turns a dirty worktree into a blocked verdict, and `install.py:898` refuses it — the ordering defeats itself | **deferred** |
| C-3 | high | The fat-install-first lane passes `--platform`, which an already-thin checkout rejects (`install.py:1268`, via `install.py:1474`) | **deferred** |
| C-4 | high | `blocked` cannot coexist with a written ledger: `fleet-candidate-check.py:502` fails on any non-`passed`, `fleet_lib.py:829` rejects it in validation. Also a release-gate policy call | **deferred**, policy question travels with it |
| C-5 | critical | The plan edited the `scripts/` mirror and called `templates/` a generated twin, exactly inverting `CONTRIBUTING.md:143`; `make sync` would erase the mechanism | **addressed** — D2, and `CANDIDATE_VALIDATOR_SOURCES` no longer names fleet_lib at all |
| C-6 | medium | Digest API used loader and root-path spellings interchangeably; executable participation undecided | **addressed** — D1 gives them distinct names and types, and settles the executable bit on measured evidence |
| C-7 | medium | Fixtures build trees with no validator source, which fail-closed loading breaks | **addressed** — D5 |
| C-8 | high | Schema bump appears to invalidate historical ledgers | **rebutted** — D4, payload-equality gate precedes the schema check |

Concerns C-1 through C-4 all belong to the thin-shape half and are the reason
this task was narrowed. No unresolved blocking concern remains in the
narrowed scope.
