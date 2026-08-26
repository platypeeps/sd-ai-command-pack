# Ship canonical-entry-point routing as an `AGENTS.md` managed block

## Origin

Issue #486, filed 2026-08-16 from `se-ai-command-pack`. Pack half of that
repository's audit finding A-005 (P3/S); the other half is a Trellis change and
is deliberately not filed here. Predecessor task
`07-25-audit-workflow-entrypoint-routing` (platypeeps/se-ai-command-pack#211)
carries the measured divergence and the ownership reasoning.

## Problem

`se-ai-command-pack` added a repo-owned canonical-entry-point routing section to
its `AGENTS.md`, plus a routing test deriving the wrapped workflow set from
`.agents/skills/` and failing when the section drifts. (That test lives in the
filing repository, not this one; issue #486 names it. Paths in this PRD are
otherwise this checkout's.)

That fixes one document in one repository. It reaches no other consumer of this
pack, and every consumer wanting the rule hand-edits the same section and keeps
it in step by hand.

## Proposal

Ship the routing section as an installed **managed block**, mirroring the pack's
only existing `kind: "managed-block"` row.

Verified in this checkout on 2026-08-25:

- `manifest.json` holds exactly one managed-block row —
  `templates/.github/copilot-instructions.sd-ai-command-pack.md` →
  `.github/copilot-instructions.md`, anchor `.github`
  (`manifest.json:366-372`).
- Markers live in `installer/registry.py:2326-2329`
  (`MANAGED_BLOCK_KIND`, `COPILOT_GUIDANCE_START` / `_END`).
- The merge path is `installer/fileops.py:647`; removal cleanup is
  `installer/removal.py:349`; conversion categorization is
  `installer/conversion.py:184`; and `installer/thin.py:812-880` keeps a
  **per-managed-block-target table** of marker pair, diagnostic label, and
  thin-conversion disposition.
- `installer/registry.py:686` already asserts "Keep the managed-block update
  inside the current repository."

So a second managed-block target is not one manifest row — it is a row plus
entries in each of those surfaces. Enumerate them from the code, not from this
list, before implementing: the passing form of that check is a repo-wide sweep
for the existing target's marker constant, and every site it reaches needs a
decision.

Target shape from the issue:

- a manifest row targeting `AGENTS.md`
- an `SD-AI-COMMAND-PACK:ROUTING:START` / `:END` marker pair
- written **below** the Trellis block (`AGENTS.md:1-21` is `TRELLIS:START` /
  `TRELLIS:END`; the pack must not write inside it, and `trellis update`
  rewrites that block)

## Open question to settle before implementation

Does the block ship with a **pack-owned checker**, or stay
**documentation-only**?

That repository's routing test derives its expectations from
`.agents/skills/`, which does exist in a consumer — but consumers have no
obligation to run the observing repository's test suite. This decides whether
the managed block carries a verification story or just text, so it is a design
decision, not an implementation detail. Record the answer and the reasoning in
`design.md`; do not start implementation with it open.

## Rejected alternative (recorded so it is not re-proposed)

Suppressing or shadowing the duplicated `trellis:*` command surface at install
time. It deletes files `trellis update` rewrites, so it fights the other
installer instead of composing with it.

## Requirements

- R1: A manifest row installs the routing block into `AGENTS.md` under its own
  marker pair, written below the Trellis block and never inside it.
  **Amended 2026-08-25 — scoped to a well-formed Trellis block**: the pack
  appends below a properly terminated `TRELLIS:START`/`TRELLIS:END` pair and
  replaces its own block in place thereafter. It does not parse or repair
  another installer's markers, so an unterminated Trellis block, or a routing
  block a consumer hand-placed inside a Trellis block, is out of scope. See
  `design.md` §3 for the two named states and why guarding them would couple
  the pack to `trellis update`'s marker semantics.
- R2: Every surface that the existing managed-block target touches
  (registry markers, merge, removal, conversion, thin per-target table,
  surface-check) handles the new target. Derive that set by sweeping for the
  existing marker constant rather than from the list above.
- R3: Re-running install is idempotent; a consumer's own edits outside the
  markers survive, and edits inside them are replaced (the established
  managed-block contract — do not invent a second merge semantics).
- R4: Uninstall/removal cleans the block and leaves the rest of `AGENTS.md`
  intact, including the Trellis block.
- R5: **Behaviour in a repository with no SD pack installed does not change.**
- R6: The verification decision from the open question above is implemented as
  decided — either a pack-owned checker consumers can run, or an explicit
  written statement that the block is documentation-only and why.

## Acceptance Criteria

- [x] `design.md` records the checker-vs-documentation decision with reasoning,
      before implementation starts. Settled 2026-08-25: **documentation-only**
      (`design.md` §1).
- [ ] Fresh install into a repo with an `AGENTS.md` carrying only a Trellis
      block yields both blocks, routing below Trellis, Trellis byte-unchanged.
- [ ] Fresh install into a repo with no `AGENTS.md` behaves per the decided
      contract (create vs skip), and that choice is stated in `design.md`.
- [ ] Re-install is idempotent: byte-identical `AGENTS.md`, proven by hashing.
- [ ] Consumer text outside the markers survives install and re-install; text
      inside is replaced.
- [ ] Removal deletes the block and leaves the Trellis block and consumer text
      intact.
- [ ] A repository with no pack installed is byte-unchanged by the whole flow.
- [ ] Thin conversion handles the new target. **Amended — see `design.md` §5.**
      The `installer/thin.py` `BLOCK_MARKERS` table is reached only from
      `plan.block_strip` (`thin.py:871`, `thin.py:1013`), and a `repo-native`
      target classifies `keep`, so an entry there would be unreachable and no
      test could exercise it. The criterion's intent is met by asserting the
      classification instead: the conversion planner puts `AGENTS.md` in
      `keep`, not `block_strip` and not `blocked`.
- [ ] `make generate` / surface-check clean with the new manifest row.
- [ ] Changelog + version.

## Notes

- Complex task: needs `design.md` and `implement.md` before `task.py start`.
  The contract touches the installer, removal, thin conversion, and the surface
  closure, and it has one open decision.
- Filed as an issue rather than a PR because the observing repository has no
  standing authority to open pull requests here.

## Post-archive handoff

Not acceptance criteria — these happen after `task.py archive`, on the
synchronized default branch, and must not be left as unchecked criteria that
block archival:

- fleet rollout via the normal refresh, at the merged head
  (`implement.md` step 12).

## Amendments (2026-08-25)

- **Acceptance criterion 8 corrected.** Rationale and the measured call sites are
  in `design.md` §5; the criterion above carries the corrected form.
- **One R2 site is not reachable by the sweep the PRD prescribes.**
  `PROVENANCE_NEVER_VOUCHED_TARGETS`
  (`templates/scripts/sd-ai-command-pack-install-audit.py:128`) lists
  `.github/copilot-instructions.md` as a literal target-path string and
  references neither `COPILOT_GUIDANCE_START` nor `MANAGED_BLOCK_KIND`.
  Sweeping for the marker constant does not reach it; sweeping for the target
  path does. Recorded in `design.md` §6.1 and carried into the spec by
  `implement.md` step 10, so the next managed-block target does not repeat it.
- **R1 scoped to a well-formed Trellis block** (above). The unamended wording
  and `design.md` §3 were in direct contradiction: the design accepts two
  consumer-created states in which the routing block ends up inside the Trellis
  block, and `design.md` §8 test 14 asserts one of them. Enforcing the
  unscoped invariant would mean the pack validating `trellis update`'s markers.
- **Fleet rollout moved out of the acceptance criteria** into Post-archive
  handoff, matching the SD completion boundary. As an acceptance criterion it
  could never be satisfied before archival, since it happens after the merge.
