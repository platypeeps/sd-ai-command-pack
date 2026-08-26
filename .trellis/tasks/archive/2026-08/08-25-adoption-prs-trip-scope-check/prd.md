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
that nothing in its own lane can fail on — one lane warns, none blocks.

**Requirement 1 is now settled: exempt a diff whose every changed path is
pack-owned, and read ownership from the base copy of
`.sd-ai-command-pack/installed-targets.txt`.** Operator decision, 2026-08-26.

A correction to an earlier draft of this section, against interest. That draft
claimed the classifier hard-codes three paths and would therefore miss
`.prism/rules.schema.json`. That is wrong, and it was wrong because the Evidence
quote above stops two lines short of the end of the function. `is_pack_target_path`
falls through the `case` to a receipt lookup:

```sh
is_pack_target_path() {
  case "$path" in
    .sd-ai-command-pack/installed-targets.txt|.sd-ai-command-pack/manifest.json|.sd-ai-command-pack/provenance.json)
      return 0 ;;
  esac

  [[ -f "$TARGETS_FILE" ]] || return 1
  grep -Fxq -- "$path" "$TARGETS_FILE"
}
```

So *which files count as tooling/generated* is already receipt-derived and
already covers all 31 pack-owned targets in a consumer, `.prism/` included. The
`case` is a fast path, not the list.

The polarity also matters and the earlier draft had it backwards.
`is_pack_target_path` returning true marks a path as **in scope**, which is what
*triggers* the section requirement. It is not an exemption, and widening it
makes the defect worse rather than better.

The defect is one level up. `check_pr_body_scope` (`:301`) takes a
`scoped_count` and demands a section whenever that count is non-zero:

```sh
check_pr_body_scope() {
  local scoped_count="$1"
  if [[ "$scoped_count" -eq 0 ]]; then
    return 0
  fi
  ...
    unsatisfied:provided) fail "tooling/generated files changed, but ..." ;;
```

Nothing in that predicate can express "this diff is *only* pack files". An
adoption diff is all-scoped, so it is maximally guilty by a rule that was
written for the mixed case — authored work smuggled in alongside generated
output. That is the actual bug: a count where a ratio was meant.

The settled mechanism is therefore a new predicate at the body-check level, not
a change to `is_pack_target_path`: if every changed path is pack-owned, the body
requirement does not apply. Requirement 2 follows without a second rule — add
one authored file and the set is no longer all-pack-owned, so the section is
required again.

One hazard, and the exemption is what creates it. `TARGETS_FILE` resolves to the
working-tree copy:

```sh
TARGETS_FILE="${SD_AI_COMMAND_PACK_TARGETS_FILE:-$REPO_ROOT/.sd-ai-command-pack/installed-targets.txt}"
```

Today that is safe in the conservative direction: a PR that adds a path to the
receipt makes that path *count as scoped*, which is stricter, not looser. Under
an exemption the sign flips — appending an authored path to
`installed-targets.txt` would make that path pack-owned and exempt the diff that
carries it. The design must read ownership from the **base** copy
(`git show "$base_ref":.sd-ai-command-pack/installed-targets.txt`), which the
script can already reach because `scope_base_ref` (`:85`) resolves one for
`collect_changed_files`.

The known cost of the base-copy rule is over-strictness in one case: when a pack
version *adds* a new installed target, that path is absent from the base receipt
and the adoption PR still asks for a section. That fails safe, matches today's
behaviour exactly, and is rare enough to accept rather than engineer around.

Fail-closed is the second constraint: no resolvable base ref, or an unreadable
or malformed base receipt, must mean "no exemption", never "exempt everything".

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
that nothing in its own lane can fail on — one lane warns, none blocks.

**Requirement 1 is now settled: derive the exemption from
`.sd-ai-command-pack/installed-targets.txt`.** Operator decision, 2026-08-26.

What settled it was measuring the exemption the earlier draft proposed against
the adoption diffs it would have to cover. The proposal named three paths. It is
not enough, and not merely at risk of drifting — it is already short today:

```
$ grep -vc '^#' .sd-ai-command-pack/installed-targets.txt    # sd-github-review
31
$ grep -v '^#' .sd-ai-command-pack/installed-targets.txt \
    | grep -vc '^\.sd-ai-command-pack/'
27
```

Thirty-one pack-owned targets in one consumer, twenty-seven of them outside
`.sd-ai-command-pack/` — `.prism/rules.json`, `.prism/rules.schema.json`,
`.github/PULL_REQUEST_TEMPLATE.md`, `.claude/rules/`, the whole
`.github/prompts/` family. Real adoption history hits them:

```
$ git show --stat 99d8843     # "chore(sd-review): adopt pack 0.71.50"
 .prism/rules.schema.json            | 6 ------
 .sd-ai-command-pack/manifest.json   | 2 +-
 .sd-ai-command-pack/provenance.json | 4 ++--
```

A three-path exemption would have passed `fecad1c` and still failed `99d8843` —
one of the two adoption commits sampled in this consumer. The list is the wrong
shape for the problem: it hard-codes a subset of a set that `install.py` already
writes down.

Deriving from the receipt fixes that by construction, and carries requirement 2
for free: a file the operator authored is absent from `installed-targets.txt`,
so adding it to an adoption diff drops the exemption with no extra rule.

Two hazards the design must resolve rather than inherit:

- **Fail closed on an unusable receipt.** A missing, unreadable, or malformed
  `installed-targets.txt` must mean "require the section", never "exempt
  everything". The receipt is authorizing a gate to be skipped, so it is
  untrusted input — the same posture `installer/machinescope.py` already takes
  toward the machine receipt it validates before honoring deletes.
- **The receipt is itself in the diff.** `install.py` rewrites
  `installed-targets.txt` whenever the target set changes, so an adoption diff
  may legitimately modify the very file the exemption is read from. Evaluating
  the exemption against the *head* copy lets a PR widen its own exemption by
  adding an authored path to the receipt. Which copy governs — base, head, or
  both under a content check — is a design decision, not an implementation
  detail.

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
   **Settled 2026-08-26:** `check_pr_body_scope` does not demand a section when
   *every* changed path is pack-owned. Ownership is the existing
   `is_pack_target_path` predicate, which is already receipt-derived, evaluated
   against the **base** copy of `.sd-ai-command-pack/installed-targets.txt`
   rather than the working-tree copy. The change is at the body-check level;
   `is_pack_target_path` itself is not widened. See Evidence for why, for the
   receipt-in-diff hazard the exemption creates, and for the fail-closed rule.
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

- [x] A test drives the scope check over a changed-file set of exactly
      `.sd-ai-command-pack/manifest.json` and
      `.sd-ai-command-pack/provenance.json` with a marker-free PR body, and
      asserts it passes. The same test fails against today's code.
      → `test_adoption_diff_of_manifest_and_provenance_needs_no_section`,
      observed red before the change.
- [x] A test covers a pack-owned path **outside** `.sd-ai-command-pack/` —
      `.prism/rules.schema.json`, which real adoption history exercises
      (`99d8843`).
      → `test_adoption_diff_covering_a_pack_file_outside_the_pack_dir_is_exempt`.
- [x] A companion test pins requirement 2: the same marker-free body with one
      authored file added to that set still fails.
      → `test_one_authored_file_alongside_pack_files_still_requires_a_section`,
      plus `test_an_untracked_authored_file_denies_the_exemption` for the
      unstaged case, which an earlier revision of the design got wrong.
- [x] Fail-closed is pinned by test.
      → `test_receipt_absent_at_base_denies_the_exemption` and
      `test_empty_receipt_at_base_denies_the_exemption`. **Two cases, not the
      four this criterion originally named.** "Base ref unresolvable" is not
      reachable: `scope_base_ref` falls back to the discovered default branch,
      pinned instead by
      `test_an_unresolvable_configured_base_ref_falls_back_and_still_decides`.
      "Unreadable" is not distinctly reachable through git, which either
      resolves a blob or does not; it collapses into the absent case.
- [x] Receipt-in-diff is pinned by test.
      → `test_appending_an_authored_path_to_the_receipt_does_not_exempt_it`,
      and confirmed externally below.
- [x] `installed-targets.txt` is itself exempt.
      → `test_installed_targets_itself_may_change_in_an_adoption_diff`.
- [x] External evidence: the repro in Evidence, rerun unchanged in a consumer
      checkout, exits `0` with no `error:` line.

      Run 2026-08-26 against a clone of `platypeeps/sd-github-review` at
      `8f5a409` — a **thin** install, so the script under test is the machine
      layer's, which is the path the Evidence repro names. Before, machine
      layer 0.71.53:

      ```
      info: Changed scope files:
        - .sd-ai-command-pack/provenance.json
      error: tooling/generated files changed, but the provided PR body does not include a recognized tooling/generated scope section
      exit: 1
      ```

      After, 0.71.55 staged into a scratch prefix via
      `install.py --machine --home` so the operator's own `~/.agents` was not
      written to:

      ```
      info: Changed scope files:
        - .sd-ai-command-pack/provenance.json
      info: All changed files are pack-owned at origin/main; adoption diff, no scope section required.
      exit: 0
      ```

      Requirement 2 and the tamper case, same consumer, same script: one
      authored file alongside → exit 1; appending `authored_change.py` to the
      working-tree receipt and then changing it → still exit 1.

## Notes

Filed 2026-08-25 from the consumer side, after the eight-repo 0.71.51 rollout.

Requirement 1 was a genuine fork and is now closed. The four candidates, and why
the receipt-derived one won on 2026-08-26:

- **Exempt an all-pack-owned diff, ownership read from the base receipt** —
  chosen. It reuses `is_pack_target_path`, which is already receipt-derived and
  already covers all 31 pack-owned targets, and moves the fix to the predicate
  that is actually wrong: a body check keyed on a non-zero count of scoped files
  cannot distinguish "only pack files" from "authored work alongside pack
  files". Satisfies requirement 2 without a second rule. Cost is that the
  receipt becomes gate-authorizing input, which is why the base copy governs.
- **Exempt a hard-coded path list** — rejected as the wrong level. It would
  duplicate coverage `is_pack_target_path` already derives from the receipt, and
  drift from it. The earlier draft argued this list was also incomplete; that
  argument was mistaken and is corrected in Evidence.
- **Emit the section during adoption** — rejected as out of proportion. It needs
  an adoption path that owns PR creation, which does not exist; `sd-fleet-refresh`
  authors bodies but never calls `--prepare-tooling-body`, and `sd-create-pr`
  calls the preparer but adoption does not go through it. Building that
  subsystem to fix a gate predicate is the larger piece of work.
- **Declare the check a manual-path tool** — rejected because it leaves the
  defect in place and only relabels it. Requirement 3's template wording still
  needs to track the settled mechanism either way.

`design.md` and `implement.md` remain unwritten; the fork no longer blocks them.
Related: `08-25-gito-adapter-drops-head`, filed from the consumer side on the
same day, since shipped in 0.71.52.
