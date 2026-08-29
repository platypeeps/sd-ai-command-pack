# Design: tick what the run proved, leave the rest visibly unticked

## Where the tick can land

`scripts/sd-ai-command-pack-fleet-publish.py` folds one head in a fixed shape,
and `.trellis/spec/tooling/fleet-publish-generated-content.md` establishes that
the shape is not negotiable: work commit (`H1`) then archive then journal tail
(`H3`). That constrains the edit point more than it first appears.

`task.py archive` moves the task directory **and commits it** — the abort path
in `archive_and_journal()` exists precisely because the move can land on disk
while the commit fails. So the tick must be written into the live
`.trellis/tasks/<slug>/prd.md` **before** that call, and the archive commit then
carries it.

Two placements are wrong and both fail loudly rather than subtly, which is worth
recording so nobody re-derives them:

- Ticking before `work_commit()` puts `prd.md` in `H1`. `H1` is the installer
  diff; the task's own bookkeeping riding in it muddies the very delta the
  managed-scope criterion asserts.
- Ticking after the archive commit needs a fourth commit. A receipt spanning it
  is rejected `bundle_scope_invalid`, and a second bundle is rejected
  `completion_archive_move_missing`. Unrecoverable in place.

So: a `tick_acceptance_criteria()` step inside `archive_and_journal()`,
immediately before the `task.py archive` invocation. `assert_trellis_only_delta()`
still passes — `.trellis/` is exactly where the edit lands.

## The evidence problem

The five criteria a refresh PRD carries are not one kind of claim. Measured
against what the publish process actually holds at that moment:

| Criterion | Provable in-process? |
| --- | --- |
| install audit passes, provenance at the target release | **Yes** — `sd-ai-command-pack-install-audit.py` is a pack helper, resolvable beside this script exactly as the record-session wrapper and review preflight already are. |
| tracked mode is `100755`, not `100644` | **Yes** — `git ls-files -s` against the consumer worktree. |
| the consumer's declared check command passes | **No** — manifest-declared and per-consumer; already run at the `local-checks` stage. Re-running it here is duplicate cost for a result the lane already holds. |
| deterministic gate passes, or findings dispositioned with zero blockers | **No** — the severity-gate disposition is a lane artifact and cannot be re-derived from the tree. |
| published as one PR whose head carries work + archive + journal | **Yes, conditionally** — see below. |

The publish helper's argument surface confirms the gap: it takes `repo`, `slug`,
`--branch`, `--title`, `--summary`, `--change`, `--test`. Nothing carries an
audit result or a gate disposition.

The bundle-shape criterion deserves its own note. At tick time the archive and
journal commits do not exist yet, so ticking it looks like asserting the future.
It is safe because publish is all-or-nothing: if the bundle does not form, the
receipt comes back invalid and publish raises before the push. A tick that would
have been a lie never reaches a remote, let alone merged history.

## Mechanism

**Evidence tags on criteria.** The refresh PRD emits each criterion with an HTML
comment naming the evidence that would settle it:

```
- [ ] <!-- verify: install-audit release=0.71.39 platforms=claude,gemini,github,opencode --> The sd-ai-command-pack install audit passes ...
- [ ] <!-- verify: tracked-mode path=.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py --> ... reports mode `100755` ...
- [ ] <!-- verify: lane-evidence id=check-command --> The consumer's declared check command passes.
```

The comment is invisible in rendered Markdown, so a reader sees the criterion
unchanged. Prose stays authored per consumer; only the tag is structured. A
verifier keys off the tag, never off matching the sentence — inferring "this
criterion means check the exec bit" from free text is the failure mode that
produces confidently wrong ticks.

**Verifier registry.** Tag id maps to a callable returning
`(verified: bool, note: str)`. Built in: `install-audit`, `tracked-mode`,
`bundle-shape`. Each either proves its claim from the consumer tree or reports
why it could not.

Attributes carry what publish does not know. The install-audit criterion asserts
a *release* and a *platform set*, and publish's argument surface holds neither —
so both ride on the tag and the verifier compares against them. Without that, an
exit-0 audit would tick a sentence naming a version the verifier never looked
at. Same reason `tracked-mode` takes its path and expected mode from the tag
rather than hard-coding the one path this release happened to care about.

**External evidence.** `lane-evidence` tags resolve from a new repeatable flag,
`--criterion-evidence <id>=<verified|unverified>[:<note>]`, supplied by whoever
ran the stage that produced the result. This is the half no helper can evaluate,
and the PRD is right that the answer is both mechanisms rather than one.

**Fail closed, three ways.** A criterion is left unticked when its tag is absent,
its tag id is unknown, its `lane-evidence` has no matching flag, or its verifier
returns unverified. In every one of those, publish appends a generated
disposition block beneath the criteria list naming each unticked criterion and
the reason, and returns `uncheckedCriteria` in its result JSON. The defect being
fixed is an archive that silently reports verified work as unverified; an archive
that silently reports unverified work as verified is strictly worse, so the
registry never guesses and an unknown tag is never a tick.

Publish does **not** exit nonzero on unticked criteria. Criterion four is
routinely unverifiable-in-process, and failing the lane on it would halt every
refresh on a condition the design expects. The archive telling the truth is the
fix. Consuming `uncheckedCriteria` at `merge-eligibility` is a plausible
follow-on and is deliberately out of scope here.

## Rejected

- **Blanket tick-everything on successful publish.** Directly prohibited by the
  PRD, and correctly: it converts a visible gap into an invisible false claim.
- **Operator reconciliation alone.** Already the status quo by convention, and
  the 0.71.38 rollout is the disproof — ticked by hand on two consumers, missed
  on two others in the same campaign.
- **Inferring criterion meaning from its prose.** No stable contract; a reworded
  criterion silently changes what gets asserted.
- **A new commit after the archive.** Rejected by the bundle shape above.

## Blast radius

- `scripts/sd-ai-command-pack-fleet-publish.py` — the only tracked copy of the
  helper. Verified with `git ls-files`; it is not fanned out to `templates/` or
  the plugin payload. It is source-only, so resolving a sibling helper always
  lands in `scripts/`.

  The helpers it *invokes* are fanned out — install-audit and the review
  preflight each have four tracked copies. That costs nothing here because this
  change calls them and does not modify them, but do not read the single-copy
  fact above as applying to them.
- The refresh skill has a source and one full copy.
  `templates/.agents/skills/sd-fleet-refresh/SKILL.md` is the source, read by
  `.github/scripts/generate-command-surfaces.py`. `.agents/skills/sd-fleet-refresh/SKILL.md`
  is the same file minus the `model: sonnet` frontmatter.

  It is **not** refreshed by `make generate` or `make sync`, contrary to what
  the fan-out for other skills would suggest: `sd-fleet-refresh` is absent from
  the install manifest entirely — a maintainer surface that operates *on*
  consumers is not shipped *to* them — so no installer target covers the copy.
  The `.github` prompt, `.opencode` command, and `templates/.commands` entries
  are ~46-line wrappers that do not embed the body, so they need nothing.

  Verified rather than assumed: after editing the source,
  `.github/scripts/check-command-surface-drift.py` reported `clean` and
  `install.py . --check` reported `planned changes: 0`, while the `.agents`
  copy still lacked the new text. Sync it explicitly, or the skill an agent
  actually loads in this checkout stays stale.
- `tests/test_fleet_publish.py` — `unittest` classes, not bare functions.
- A new rule under `.trellis/spec/tooling/`.

Deliberately untouched: the `seeded-task` validator in the review preflight.
Rejecting an untagged criterion at task-creation time is a coherent follow-on,
but that helper has four tracked copies and pulling them into this change trades
a narrow fix for a wide one.

## The two consumers already carrying empty boxes

anomaly-metric-creator PR 395 and hoa-manager PR 279 merged with all five boxes
empty. Recommendation: **leave them, and annotate**.

Ticking them now would assert that those runs verified those criteria. What can
be re-derived today is that the *current* state satisfies them, which is a
different claim — the archive is a record of what a run checked, not of what
happens to be true afterwards. Rewriting it to claim verification after the fact
is the falsely-verified failure mode this task exists to prevent, applied to its
own cleanup.

Instead, append one dated line to each archived PRD noting the boxes were left
unticked because the publish path never ticked them, and naming this task. That
is honest, cheap, and needs no claim about what those runs did.

This is a judgment call with a real alternative, and it is the one item here
worth overriding at the review gate.
