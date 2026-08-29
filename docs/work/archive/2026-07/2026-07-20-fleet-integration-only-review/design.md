# Fleet integration-only review design

## Boundary

The optimization applies only to consumer pull requests created by the
source-checkout-only `sd-fleet-refresh` workflow. Source implementation pull
requests keep the normal `sd-review-pr` remote-review convergence loop.

A consumer refresh may skip a new remote implementation-review request only
when a source-side classifier proves that the exact current branch is a pure
installer-managed refresh of a verified published release. Skipping a new
request does not skip deterministic local checks, existing conversation and
thread inspection, required GitHub checks, head identity, mergeability, or the
housekeeping merge gate.

The public fleet argument `remote-review` forces the normal review profile.
There is no public `integration-only` switch. Ambiguity and classifier errors
fall back to normal remote review instead of failing open.

## Source-side classifier

Add `scripts/sd-ai-command-pack-fleet-review-classify.py` as a source-only,
read-only command. It receives a configured fleet consumer name, the consumer
repository path, the exact base commit captured before the refresh branch was
created, and the release remote. It derives expected platforms and target
version from the canonical fleet and pack manifests.

The classifier proves these contracts in order:

1. Reuse the release-identity guard to verify the local and remote raw tag,
   tag ancestry, tagged/current payload, and tagged/current full-fleet
   candidate evidence.
2. Require the requested consumer to exist in the fleet manifest and resolve
   to the configured local path.
3. Require a clean consumer worktree, an exact `HEAD`, and the supplied base
   commit to be an ancestor of that head.
4. Run the authoritative read-only installer `--check --json` inspection from
   the source checkout. Require state `current`, zero planned changes, matching
   source/installed release versions, the expected installed platforms, and a
   passed exact install audit.
5. Read and validate the installed-targets receipt at both the exact base
   commit and the current filesystem. The allowed path set is the union of
   both receipts plus the three receipt/provenance files. The base receipt is
   required so retired payload deletions remain classifiable.
6. Collect the committed branch diff with rename detection disabled so both
   sides of a delete/add or rename remain visible. Require a non-empty diff and
   every changed path to be in the allowed set.

The inspection contract already validates current receipt path safety,
manifest/provenance consistency, vouched hashes, expected targets, and audit
completeness. The classifier independently validates the historical receipt
loaded from Git before using it as an allowlist.

## Output and exit model

Human output states `integration-only` or `remote-review-required` and prints
bounded reasons. JSON schema version 1 contains:

- eligibility and classification;
- consumer, repository, base commit, and head commit;
- verified release identity and installed version/platforms when available;
- sorted changed, allowed, and disallowed paths; and
- deterministic reasons.

Exit `0` means eligible for integration-only review. Exit `1` means the branch
must use normal remote review, including controlled configuration, Git,
release, inspection, receipt, dirty-tree, or diff failures. The command never
fetches, writes, requests review, or changes branches.

## Review orchestration

`sd-fleet-refresh` captures the consumer base commit, performs the install,
audit, local gate, and refresh commit, then runs the classifier before choosing
a review profile.

For an eligible branch, it invokes `sd-review-pr` with a trusted internal
fleet context containing the source checkout, consumer name, base commit,
release remote, and exact classified head. `sd-review-pr` accepts this context
only while already executing the resolved `sd-fleet-refresh` workflow. It
reruns the classifier after resolving the PR and requires local, PR, and
classified heads to agree before suppressing the configured remote-review
request.

The integration-only profile otherwise follows the normal review loop:
deterministic full-check, first-review advisory disposition, full existing
review/comment/thread reads, CI inspection, fixes and replies when needed, one
PR-scoped learning pass, and explicit finish-work deferral to the fleet
housekeeping tail. If a fix changes the head, classification reruns. A new
consumer-owned or ambiguous change switches the same invocation to normal
remote review.

When `remote-review` is set or initial classification is not eligible,
`sd-fleet-refresh` invokes the standard `sd-review-pr` profile. No source PR
behavior changes.

## Safety and compatibility

- Integration-only is an internal profile, not a user-spoofable public
  `sd-review-pr` argument.
- A successful classifier is head-bound and is rerun by the review owner.
- Existing unresolved threads block both profiles and remain authoritative at
  the housekeeping merge gate.
- Expected platforms come from the fleet manifest rather than caller text.
- The classifier uses exact commits and disables rename collapsing, so retired
  files and renamed paths cannot disappear from the allowlist decision.
- Existing `no-merge` behavior remains a fleet tail decision after review and
  watch settle.

## Rejected alternatives

- Skip remote review based only on a tooling/generated scope message: advisory
  classification does not prove release identity, audit, provenance, or an
  installer-only diff.
- Trust only the current receipt: retired payload deletions would appear
  consumer-owned and path replacement could hide historical ownership.
- Add a public `integration-only` flag to `sd-review-pr`: callers outside the
  source fleet workflow could bypass the required release/candidate proof.
- Ignore existing Copilot comments because no new request is made: old valid
  feedback must still block merge.
- Re-request Copilot on every consumer head: it repeats source implementation
  review without improving installed integration evidence.
