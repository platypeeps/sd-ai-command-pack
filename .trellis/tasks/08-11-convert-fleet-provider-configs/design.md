# Design: converting eight consumers off superseded provider configs

## What this task actually changes

Nothing in this repository. Every write lands in a consumer checkout, through
`install.py`, and reaches that consumer's default branch only via its own pull
request. This repo's role is to be the pack source checkout the installer reads
from, and to hold the record of what was done.

That inverts the usual safety question. There is no local gate to satisfy here;
the gates are eight separate repositories' review paths, and the only thing
this task controls is what it puts in front of them.

## The mechanism and its real boundary

`install.py <consumer> --force` writes the whole payload for the target's
detected platforms. The provider-config conversion the cohort authorizes is one
line of its report:

```
refreshed   .gito/config.toml
preserved   .prism/rules.json
```

`refreshed` fires for a target whose content matches a superseded shipped
revision; `preserved` for one the consumer has edited. That classification is
the installer's, computed against the shipped digest history
`08-06-fleet-provider-config-propagation` added — this task does not
reimplement it, and must not hand-edit a consumer's config to reach the same
end state, because a hand-edit produces a file with no digest lineage and the
detector will report it `local` forever after.

The boundary that matters: `preserved` is what protects R2. The six locally
owned `.prism/rules.json` files are untouched because the installer classifies
them, not because this task avoids them. Verification is therefore a byte
comparison after the fact, not an intention stated before it.

`--thin` is a separate flag requiring `--resweep-verdict`; a forced install
cannot convert a fat install to thin by accident, so the unauthorized thin
cohort is out of reach by construction rather than by care.

## Order: canary, then the rest

`sd-github-review` goes first, alone. It is clean, synchronized, and the only
consumer whose `.prism/rules.json` the detector already calls `current`, so its
diff is the cleanest available read of what the upgrade does — no `preserved`
line to explain, no local provider edits sitting next to the change.

The remaining seven wait on that PR being reviewed. This is the whole risk
control: the first diff is inspected by a human before the pattern is repeated
seven times.

## Per-consumer sequence

For each consumer, in registry order after the canary:

1. Confirm the checkout is available and read its branch, tree state, and
   upstream from a fresh `sd-status fleet --json --no-network`, never from a
   table written earlier in the session.
2. If the tree is dirty, record the checkout's current branch, then
   `git stash push -u -m "sd-ai-command-pack provider config conversion
   <date>"`, and record the resulting ref in `prd.md` before going further. A
   stash that does not report a created ref stops that consumer.
3. Branch from the consumer's default branch.
4. Run `install.py <path> --force` from this checkout.
5. Commit exactly what the installer wrote, push, open a PR against that
   consumer's default branch, and stop. This task never merges a consumer PR.
6. If a stash was taken, switch the checkout back to the branch recorded in
   step 2 and restore it there. A conflicting restore stops that consumer and
   is reported; it is not resolved by this run.

Step 6 is deliberately after the commit rather than after the merge: leaving
someone else's uncommitted work stashed while a PR sits in review would be
worse than the dirty tree it came from. Restoring onto the recorded branch
rather than wherever the checkout happens to sit matters just as much — the
conversion branch is this task's, and someone else's work does not belong on
it.

## What could go wrong, and what catches it

| Risk | Catch |
|---|---|
| A `preserved` file is written anyway | Byte comparison of the six `.prism/rules.json` files before and after, per consumer |
| The installer converts a fat install to thin | `--thin` is absent from every command; verified by the receipt's recorded mode after each install |
| A stash is taken and never restored | Every stash ref is written to `prd.md` at creation, and the final report enumerates each as restored or not |
| A conversion lands on the wrong base | `mezmo_benchmark` is on a feature branch with no upstream; its default branch is resolved from the consumer, not assumed to be checked out |
| A consumer's own checks fail on the upgrade | That PR stays open and is reported; this task has no authority to merge or to weaken a consumer's gate |

## Rollback

Per consumer, before merge: close the PR and delete its branch; the consumer's
default branch never moved. After a consumer merges its own PR, rollback is
that consumer's revert, not this task's — which is the honest consequence of
R3 and the reason the canary exists.
