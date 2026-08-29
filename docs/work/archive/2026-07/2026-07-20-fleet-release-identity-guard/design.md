# Fleet release identity guard design

## Boundary

Fleet preflight remains the only entry point that decides whether consumer
mutation may begin. Before it classifies or prints any consumer as mutable, it
must prove that the current source checkout represents a published release.
The proof is read-only and covers four identities:

1. the current `manifest.json` version and installable payload digest;
2. the local immutable `v<version>` tag and its resolved commit;
3. the same tag ref advertised by the configured Git remote; and
4. the current full-fleet candidate ledger and fleet manifest.

The guard does not create, fetch, move, or delete tags. A checkout without the
matching local tag fails with a fetch-tags remedy. Comparing the local raw tag
object ID with the remote ref makes a locally observed tag rewrite fail closed.

## Shared release identity

Add a source-only Python module under `.github/scripts/` for exact-commit
release identity work. It owns bounded Git execution, exact-tree manifest and
payload loading (including tracked symlink resolution), tag/ref comparison,
and candidate-ledger validation. Both the existing auto-tag planner and fleet
preflight use this module so tag creation and rollout cannot drift into
different payload-digest interpretations.

The module exposes two distinct operations:

- validate candidate evidence at an exact commit for tag planning; and
- verify an existing release tag against the current filesystem payload,
  current fleet manifest, and current candidate ledger for rollout.

`sd_ai_command_pack_fleet_lib.py` remains the owner of manifest parsing,
payload digest framing, fleet parsing, and ledger validation. The new module
composes those contracts and does not duplicate them.

## Verification sequence

Fleet preflight verifies the release in this order:

1. Load and validate the current pack manifest and compute its payload digest.
2. Resolve `refs/tags/v<version>` locally and resolve its commit.
3. Query the configured remote for the exact tag ref and require its raw object
   ID to equal the local raw object ID.
4. Require the tag commit to be an ancestor of the current checkout commit.
5. Load the tagged manifest from the exact Git tree and require the same
   version and payload digest as the current checkout.
6. Validate the candidate ledger stored at the tagged commit.
7. Validate the current candidate ledger against the current payload and
   current fleet manifest.

This allows later documentation or Trellis bookkeeping commits on `main`
because `HEAD` need not equal the tag. It rejects any later installable-payload
change under the same version because the filesystem and tag digests differ.

## Output and failure model

Human output prints one release-identity line before the fleet target and
consumer rows. JSON becomes a schema-versioned object with a
`releaseIdentity` object and a `consumers` array instead of an unlabelled top-
level array.

Successful identity output includes the status, version, tag, resolved commit,
and payload digest. A failed guard prints a controlled `release identity
error:` diagnostic and exits `1` before evaluating or printing consumer
mutation rows. Configuration or malformed-data errors remain controlled and do
not produce tracebacks.

## Safety and compatibility

- Preflight performs no fetch and no writes.
- `dry-run` uses the same guard; it is not an escape hatch.
- Consumer filtering happens only after the release identity passes, so a
  narrow filter cannot bypass the guard.
- The remote defaults to `origin` and is configurable only through an explicit
  preflight argument for mirrors and tests.
- Existing tag creation remains idempotent and continues to refuse moving an
  existing GitHub tag.

## Rejected alternatives

- Trust the manifest version alone: this reproduced the unreleased 0.23.7
  consumption failure.
- Check only that a tag name exists: a mismatched or rewritten tag would still
  pass.
- Fetch tags automatically: that mutates operator state inside a read-only
  preflight.
- Reimplement payload hashing in preflight: tag-time and rollout-time identity
  could diverge.
