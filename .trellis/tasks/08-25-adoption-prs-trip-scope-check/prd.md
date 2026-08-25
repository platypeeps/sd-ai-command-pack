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

and `check_pr_body_scope` treats a resolved, marker-free body as fatal, not
advisory:

```sh
    unsatisfied:provided)
      fail "tooling/generated files changed, but the provided PR body does not include a recognized tooling/generated scope section"
```

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

Adoption is not opened through `sd-create-pr`. There is no adoption skill —
`plugins/sd/skills/` has no rollout or adopt entry — and `install.py`'s
`--configure-fleet` builds a machine-local discovery profile for `sd-status`,
not a rollout. Adoption is `install.py --thin <consumer>`, then a commit and a
PR the operator opens by hand, per repo. Nothing in that path calls the
preparer, so the section is a thing the operator must remember N times.

## How it was found

Rolling 0.71.51 to eight consumers on 2026-08-25. All eight PR bodies were
uniform; seven passed CI and `platypeeps/hoa-manager` failed, because that repo
alone carried a repo-local CI mirror of this check. Clearing it cost a PR-body
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
