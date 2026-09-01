# Fleet publish: tick only what the run proved

> [!important]
> **Stale as of 2026-09-01.**
> `scripts/sd-ai-command-pack-fleet-publish.py` and `tests/test_fleet_publish.py`
> already carry inline absent markers; they were deleted with the release train
> at step 0 (2026-08-29, #597). The rest of the page has lost its subject too:
> the `sd-fleet-refresh` skill and its `templates/.agents/skills/` source went
> with `templates/` on 2026-08-30 (step 3e, `43170716`, #610), `task.py archive`
> and `.trellis/tasks/<slug>/prd.md` were removed at step 2, and the fleet of
> consumer checkouts the publish helper wrote into was dropped by R10-D6.
>
> The text below is unedited. It is the record of what that machinery
> specified, not guidance for the repository as it stands. The triage that
> produced this notice is recorded under step 7 in
> `docs/work/2026-08-29-artifacts-as-product/implement.md`.

Scope/trigger: any change to how `scripts/sd-ai-command-pack-fleet-publish.py` [absent: removed with the release train in 0.72.0]
writes a consumer's archived PRD, and any change to the acceptance criteria the
`sd-fleet-refresh` skill authors. Established by the
`fleet-publish-archives-unchecked-criteria` task, after the 0.71.38 rollout
merged two consumers whose archives carried five empty boxes beside a task
marked `completed`.

Referred to here by task name rather than by directory path on purpose: a spec
that cites its establishing task by the live path breaks the documentation
path-reference gate the moment that task is archived, and citing the archive
path before the archive exists breaks it immediately.

## The rule

An archived PRD must report what the publish run actually verified. Two failures
sit on either side of that, and the worse one is not the obvious one:

- reporting verified work as unverified — the defect this replaces;
- reporting unverified work as verified — strictly worse, and the failure a
  blanket tick-everything pass would introduce.

So the verifier ticks a criterion only against a structured `verify:` tag, never
by matching the criterion's prose. Inferring "this sentence means check the
executable bit" from free text means a rewording silently changes what gets
asserted.

## Where the tick lands, and why there is no choice

`docs/spec/tooling/fleet-publish-generated-content.md` pins the completion
bundle to one shape: work commit (`H1`), archive, journal tail (`H3`). That
fixes the edit point.

`task.py archive` moves the task directory **and commits it** — `--no-commit` is
the opt-out, so committing is the default. The rewrite therefore happens against
the live `.trellis/tasks/<slug>/prd.md` immediately before that call, and the
archive commit carries it.

Both neighbouring placements fail, loudly rather than subtly:

- before `work_commit()` — task bookkeeping lands in the installer diff, which
  is the very delta the managed-scope criterion asserts;
- after the archive commit — needs a fourth commit. A receipt spanning it is
  rejected `bundle_scope_invalid`; a second bundle is rejected
  `completion_archive_move_missing`. Unrecoverable in place.

## Fail closed, and never guess

A criterion stays unticked when its tag is absent, its tag id is unknown, its
`lane-evidence` has no supplied result, or its verifier reports unverified. Each
one is named with a reason in a generated disposition block below the criteria
list, and returned as `uncheckedCriteria` in the helper's result.

An **unknown** tag id is the important case. It must never fall through to
"nothing objected, so tick it" — that is exactly how a verifier added later, or
a tag typo, would start ticking boxes nobody checked.

An already-ticked box is never unticked. It may reflect evidence the helper
cannot see, and removing it would be its own false claim.

Publish does not exit nonzero on unticked criteria. The deterministic-gate
criterion is routinely unverifiable in-process, so failing the lane on it would
halt every refresh on a condition the design expects. A truthful archive is the
fix; gating a merge on the unticked set is a separate decision.

## What the helper can and cannot prove

Publish holds the repo, the slug, the branch, the journal strings. It holds no
audit result, no release number, and no severity-gate disposition. That split
decides the verifiers:

- `install-audit` and `tracked-mode` read the consumer tree and prove their
  claim.
- `bundle-shape` is true by construction — publish is all-or-nothing, so a tick
  that would have been a lie never reaches a remote.
- `lane-evidence` is supplied through `--criterion-evidence` by the stage that
  produced the result, and is never computed.

Attributes carry what publish does not know. The install-audit criterion asserts
a release and a platform set, and the helper takes neither as an argument — so
both ride on the tag and the verifier compares against them. Without that, an
exit-0 audit would tick a sentence naming a version nothing ever looked at. A
malformed `--criterion-evidence` value is rejected at parse time, because a typo
resolving to "unverified" is indistinguishable from a stage that legitimately
could not verify.

## The rewrite is idempotent

The tick runs before `task.py archive`, and that call aborts with no rollback. A
retry re-enters with the boxes already flipped and a disposition block already
on disk. The block is delimited and replaced, not appended, and the blank lines
around it are normalized on both sides — an unnormalized boundary grows the file
by a line per attempt, which is the same append-per-retry bug one line at a
time.

## Skill copy

`templates/.agents/skills/sd-fleet-refresh/SKILL.md` is the source. Its one full
copy, `.agents/skills/sd-fleet-refresh/SKILL.md`, is the same file minus the
`model: sonnet` frontmatter and is **not** refreshed by `make generate` or
`make sync`: this skill is absent from the install manifest, so no installer
target owns it. The command and prompt surfaces are wrappers that do not embed
the body. Sync the copy explicitly; the surface-drift checker reports `clean`
while it is stale, so it cannot be the check for this.

Tests: `tests/test_fleet_publish.py` [absent: removed with the release train in 0.72.0]. The ordering rule is pinned by
`test_publish_lands_the_criteria_tick_inside_the_archive_commit`, which runs
`publish()` end to end and asserts which commit carries `prd.md` — a test that
calls the tick helper directly passes wherever the call site sits. The retry
rule is pinned by `test_criteria_rewrite_is_idempotent_across_a_retry`, and the
anti-guessing rule by `test_criteria_unknown_verifier_never_ticks`.
