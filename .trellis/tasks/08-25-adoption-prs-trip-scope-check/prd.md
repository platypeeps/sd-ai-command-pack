# Pack adoption PRs trip the pack's own tooling/generated scope check

The review-scope check names `.sd-ai-command-pack/manifest.json` and
`.sd-ai-command-pack/provenance.json` as in-scope paths. A pack-version
adoption commit changes exactly those two files and nothing else. So the
consumer-side ritual the pack exists to produce is, by construction, a diff the
pack's own gate refuses unless a human writes a scope section into the PR body.

## Evidence

`scripts/sd-ai-command-pack-review-scope.sh` matches the paths explicitly:

```sh
is_pack_target_path() {
  case "$path" in
    .sd-ai-command-pack/installed-targets.txt|.sd-ai-command-pack/manifest.json|.sd-ai-command-pack/provenance.json)
      return 0
      ;;
  esac
```

and `check_pr_body_scope` treats a marker-free body as fatal, not advisory, by
whichever route the body arrived — env-provided or fetched through `gh`:

```sh
    unsatisfied:provided)
      fail "tooling/generated files changed, but the provided PR body does not include a recognized tooling/generated scope section"
      ;;
    unsatisfied:resolved)
      fail "tooling/generated files changed, but the PR body does not include a recognized tooling/generated scope section"
```

The repro below supplies the body through `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`, so
it exercises `unsatisfied:provided`. An open PR whose body `gh` resolves takes
`unsatisfied:resolved`. Both `fail`.

Reproduced 2026-08-25 in a consumer checkout with an adoption-shaped diff — one
modified `.sd-ai-command-pack/provenance.json`, nothing else — and the body an
adoption PR actually carries:

```
$ SD_AI_COMMAND_PACK_SCOPE_PR_BODY="chore(sd-review): adopt pack 0.71.51" \
    bash ~/.agents/bin/sd-ai-command-pack-review-scope.sh
info: Scope categories:
  - copied/generated Trellis or sd-ai-command-pack files
info: Changed scope files:
  - .sd-ai-command-pack/provenance.json
error: tooling/generated files changed, but the provided PR body does not include a recognized tooling/generated scope section
$ echo $?
1
```

## Why the existing escape hatch does not reach this case

The pack already knows how to satisfy its own gate:
`scripts/sd-ai-command-pack-pr-body-scope.py --prepare-tooling-body` writes the
section from the branch diff, and `plugins/sd/skills/sd-create-pr/SKILL.md:347`
invokes it. That covers a PR opened *through* `sd-create-pr`.

Adoption is not opened through `sd-create-pr`, and the path it *is* opened
through does not call the preparer either.

The pack has a fleet campaign controller: `sd-fleet-refresh`
(`.agents/skills/sd-fleet-refresh/SKILL.md`, source-checkout-only, procedure in
`docs/FLEET_ROLLOUT.md`). It issues the install, pushes the head, opens the PR,
runs the review classifier, and merges. Step 6 of that procedure specifies what
the PR body's verification summary must attribute, so the controller does author
bodies — and nothing in the skill or its `references/` mentions a scope section,
`--prepare-tooling-body`, or the review-scope check. Grepped, not remembered:
`grep -rn -i "tooling/generated|scope section|prepare-tooling" .agents/skills/sd-fleet-refresh/`
returns nothing.

Two corrections to an earlier draft of this PRD, both against interest.
`install.py --thin <consumer>` is **not** the adoption step: `--thin` is a
one-time conversion to a thin install, documented as requiring
`--resweep-verdict`, so it runs once per repo rather than once per version. And
`--configure-fleet`, while genuinely only a machine-local `sd-status` discovery
profile, is not the whole of the pack's fleet machinery —
`docs/fleet/consumers.json` carries cohorts, per-consumer
`candidatePrepare`/`candidateChecks`, and a rollout policy the controller
consumes.

**That open question is now settled: the lane can run the classifier, but never
in a mode that can fail.** Three findings:

1. No consumer's `candidateChecks` in `docs/fleet/consumers.json` invokes
   `sd-ai-command-pack-review-scope.sh` or `sd-ai-command-pack-full-check.sh`
   *directly*. But two of the nine do not declare repo-local commands at all:
   `rwbp-website` runs
   `node "$HOME/.agents/bin/sd-ai-command-pack-review-preflight.mjs"` and
   `se-ai-command-pack` runs the pack's housekeeping self-test. Both are pack
   helpers.
2. That preflight helper **does** reach the scope classifier.
   `checkScopeAdvisory()` in `scripts/sd-ai-command-pack-review-preflight.mjs:4880`
   shells out to `sd-ai-command-pack-review-scope.sh`. So the classifier
   executes inside `rwbp-website`'s lane on every campaign.
3. It cannot fail there, for two independent reasons. The helper pins
   `SD_AI_COMMAND_PACK_SCOPE_CHECK: 'advisory'`, and `is_advisory` in the bash
   script (`:449`) routes that to `warn` plus a machine-readable
   `sd-ai-command-pack-scope-advisory:` line rather than `fail`. And the Node
   side never inspects the exit status at all — it greps stdout for the marker
   and calls `warn()`. A fatal advisory would break the helper's own contract.

Separately, `LANE_STAGES` in `scripts/sd-ai-command-pack-fleet-controller.py`
orders `local-checks` **before** `pr-publication`, so no PR exists when
candidate checks run and the body resolver has nothing to read. That is a second
reason the lane cannot trip on the body, not the first one.

So the PR #292 failure came from GitHub Actions **after** publication, not from
the fleet lane. The distinction that matters for the campaign is *not enforced*
rather than *not invoked*: the fleet lane will surface this defect as a warning
on `rwbp-website`, and will not block on it anywhere.

## What survives

The defect narrows to two blocking paths, plus one non-blocking surface:

- an operator running `check:full` by hand on an adoption branch, which is the
  repro in **Evidence** and still fails at exit 1;
- a consumer whose own CI enforces the check on the published PR;
- non-blocking: `rwbp-website`'s lane, where the pack preflight will emit the
  `sd-ai-command-pack-scope-advisory:` warning on every adoption campaign. It
  costs nothing but noise, and it is the one place the fleet operator will
  actually see this defect without going looking for it.

As of 2026-08-25 the second path is **empty across the fleet**:
`platypeeps/hoa-manager#293` deleted the only mirror. That is a statement about
today's fleet, not a guarantee — nothing stops a consumer from adding one, and
the pack-owned templates still tell them the section is required (requirement 3).

This materially shrinks requirement 1. "Emit the section during adoption" no
longer has a controller bug to fix: the controller would be adding a section
that nothing in its own lane can fail on — one lane warns, none blocks. The remaining honest options are to exempt the
adoption diff in the scope check itself, or to accept that the check is a
manual-path tool and say so in the templates. Re-open requirement 1 against
these facts before design.

Also verified while settling this: hoa-manager's `candidateChecks` entry still
resolves — `scripts/check-review-preflight.mjs` still exists after #293, which
removed one function from it rather than the file. No fleet-registry breakage.

## How it was found

Rolling 0.71.51 to eight consumers on 2026-08-25 — **by hand, not through
`sd-fleet-refresh`**, which is itself worth recording: the controller exists and
the operator did not use it, so this rollout is evidence about the manual path
and only indirectly about the controller. All eight PR bodies were uniform;
seven passed CI and `platypeeps/hoa-manager` failed, because that repo alone
carried a repo-local CI mirror of this check. Clearing it cost a PR-body
edit plus a close/reopen, because a body-dependent check reads the snapshotted
`GITHUB_EVENT_PATH` payload and `edited` is not a CI trigger.

The mirror has since been removed there (`platypeeps/hoa-manager#293`, which
deleted `scripts/check-review-preflight.mjs` [absent: consumer repo, not this
one]'s `checkGeneratedScopeBody` and its four env vars). That removes the CI
symptom in one repo. It does not touch this defect: the other seven passed CI
only because they do not run the check in CI at all, and the pack's local gate
still refuses every one of their adoption branches under `check:full`.

## Why it matters

The failure is not silent, but it is systematic and it scales with the fleet: N
consumers means N chances to forget, and the one repo that enforced it in CI is
the one that paid. A gate that fires on the pack's own routine output is
training operators to route around it, which is how the hoa-manager mirror came
to be deleted rather than fixed.

It also makes the requirement invisible where it is cheapest to satisfy.
`--prepare-tooling-body` exists and works; the adoption path simply never
reaches it.

## Requirements

1. A pack-version adoption PR does not require a hand-written scope section.
   Whether that is an exemption for a diff confined to
   `.sd-ai-command-pack/manifest.json`, `provenance.json`, and
   `installed-targets.txt`, or an adoption path that calls
   `--prepare-tooling-body` and emits the section itself, is open — see Notes.
2. Whatever the mechanism, a diff that adds authored changes alongside the pack
   files is still required to declare scope. The exemption, if that is the
   route, must not be satisfiable by *including* the pack files in a larger
   change.
3. `templates/.github/PULL_REQUEST_TEMPLATE.md:6` and
   `templates/.github/copilot-instructions.sd-ai-command-pack.md:61` tell
   consumers and Copilot that the section is required. The pack installs no CI
   check that enforces it, so a consumer reading those files cannot tell where
   the requirement lives. Their wording tracks whatever requirement 1 settles
   on.

## Acceptance criteria

- [ ] A test drives the scope check over a changed-file set of exactly
      `.sd-ai-command-pack/manifest.json` and
      `.sd-ai-command-pack/provenance.json` with a marker-free PR body, and
      asserts it passes. The same test fails against today's code.
- [ ] A companion test pins requirement 2: the same marker-free body with one
      authored file added to that set still fails, so the exemption cannot be
      widened by piggybacking.
- [ ] `installed-targets.txt` is covered either way, since `install.py` rewrites
      it whenever the target set changes and an adoption diff may carry three
      files rather than two.
- [ ] External evidence: the repro in Evidence, rerun unchanged in a consumer
      checkout, exits `0` with no `error:` line. This is the shape the defect
      broke and it cannot be asserted from inside the pack.

## Notes

Filed 2026-08-25 from the consumer side, after the eight-repo 0.71.51 rollout.
Not planned — `design.md` and `implement.md` are unwritten, and requirement 1 is
a genuine fork:

- **Exempt the adoption diff.** Cheapest, and honest: there is nothing for a
  human to declare about a two-file version bump that the diff does not already
  say. Risk is that the exemption list drifts from what `install.py` actually
  writes.
- **Emit the section during adoption.** Keeps the gate uniform and reuses
  `--prepare-tooling-body`, but needs an adoption path that owns PR creation,
  which does not exist today and is a larger piece of work than the defect.

Settle that before `task.py start`. Related: `08-25-gito-adapter-drops-head`,
also filed from the consumer side on the same day and likewise unplanned.
