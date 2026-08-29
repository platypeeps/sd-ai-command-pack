---
title: "PARKED: Define Trellis version compatibility contract when incompatibilities appear"
status: planning
created: 2026-07-09
---
# PARKED: Define Trellis version compatibility contract when incompatibilities appear

## Goal

Capture the conditional task for a declared Trellis version compatibility
contract. The pack currently relies on active Trellis installs plus install
audits rather than a hard version range. A version-range contract should be
introduced only when a real Trellis version incompatibility appears.

## Trigger

Waiting for external trigger: a consumer repo, installer run, audit, or review
cycle shows that a specific Trellis version is too old, too new, or missing a
runtime behavior required by the pack.

Source:
`.trellis/tasks/archive/2026-07/07-06-introduce-platform-registry/prd.md`.

## Trigger Status — 2026-07-28

The 2026-07-28 repo audit is a triggering event of the named kind, and it fires
the trigger **partially**. Finding A-113 establishes an unbounded upstream pin,
not an observed behavioral incompatibility:

- `README.md:27` instructs `npm install -g @mindfoldhq/trellis@latest`.
- `templates/docs/SD_AI_COMMAND_PACK.md:9` ships that same instruction to every
  consumer.
- `.trellis/.version:1` pins 0.6.7, and `.trellis/.template-hashes.json` carries
  114 template hashes against that pin. (1,448 is the tracked `.trellis` file
  count, not the hash count.)

So the pack tells consumers to install an arbitrary future Trellis while the
vendored tree assumes 0.6.7 contracts. That is the exposure this task was parked
against, now confirmed and shipped downstream. It is still not a demonstration
that a specific version breaks the pack, so the 2026-07-14 re-evaluation's
conclusion — no speculative version-range gate without evidence — still holds
for the full contract.

Disposition: unpark the bounded scope in R5/R6 below. The full compatibility
contract (R1-R4) stays parked until a concrete incompatibility appears.

## Trigger Status — 2026-08-20

The trigger now fires **fully**, with the concrete incompatibility R1 has been
waiting for. Surfaced by task `08-20-retire-pre-0616-trellis-compat`; recorded
here, not fixed there.

Measured 2026-08-20:

- `.trellis/.version` is `0.6.16-sd.7` in this repository and in all eight fleet
  consumers.
- That build comes from the fork `github.com:sdelmas/Trellis`
  (`packages/cli/package.json` = `0.6.16-sd.7`). It shares the npm *name*
  `@mindfoldhq/trellis` but is **never published**: `npm view
  @mindfoldhq/trellis version` returns `0.6.15`, and no `-sd` tag exists.
- So `npm install -g @mindfoldhq/trellis@latest` — the instruction this task's
  R5 is about — installs a CLI **below** the vendored build every repository in
  the fleet runs.

The incompatibility is not cosmetic. The pack does not ship
`.trellis/scripts/**` (`manifest.json` sets `requiresTrellis: true`, a boolean
with no version component); the consumer's own CLI writes that tree. A
consumer who follows the documented instruction and then runs `trellis update`
**downgrades** their vendored runtime below the supported floor now recorded in
`.trellis/spec/tooling/vendored-trellis-compatibility.md`.

This answers R1 and constrains R2: the contract cannot be a published-version
range, because the supported build is not published. It also sharpens R4 — the
floor must be an *identity* comparison, since `0.6.16-sd.7` carries a prerelease
segment and sorts below `0.6.16` under semver, so a `>=0.6.16` gate would reject
the entire converged fleet.

R5's four occurrences are all still live. Note the stale citation corrected:
the asserted string is at `tests/install_test_support.py:641`, not `:457`.

Deliberately **not** unparked here. The fix needs a decision this task owns —
what the supported bootstrap path *is* for a fork-distributed runtime — and that
decision is user-facing across `README.md` and shipped consumer docs. Recording
the evidence is what `08-20` scoped itself to do.

## Requirements

Still parked (R1-R4) — R1's evidence now exists (see Trigger Status
— 2026-08-20); R2-R4 need the bootstrap decision:

- R1: Identify the exact Trellis behavior or file contract that is incompatible.
- R2: Decide where the compatibility contract belongs: manifest metadata,
  installer preflight, install audit warning/error, docs, or a combination.
- R3: Keep local-only installs and consumer refreshes understandable when the
  version check blocks or warns.
- R4: Avoid hardcoding a version range without evidence from the triggering
  incompatibility.

Unparked 2026-07-28 (R5-R6) — bounded by finding A-113, no version-range gate:

- R5: Stop shipping a floating upstream pin. Replace `@latest` at all four
  tracked occurrences, not just the two the audit cited. **Superseded in part
  by Trigger Status — 2026-08-20:** the vendored build is now `0.6.16-sd.7`,
  not `0.6.7`, and it is not published to npm at all, so "pin to the version
  the repo vendors" has no npm spelling. R5 now requires the bootstrap decision
  (what a consumer should actually install), not a string substitution. A caret range (`@^0.6`)
  is the speculative compatibility range R4 forbids: nothing in this repo
  demonstrates that 0.6.8 or 0.6.9 is compatible. If the exact pin is judged too
  brittle for consumers, that is a deliberate override of R4 and the rationale
  must be recorded here before the change lands.
  - `README.md:27` (cited by A-113),
  - `templates/docs/SD_AI_COMMAND_PACK.md:9` (cited by A-113),
  - `docs/SD_AI_COMMAND_PACK.md:9` — the source twin of the shipped doc; leaving
    it behind breaks generated parity, and
  - `tests/install_test_support.py:641` — asserts the literal string, so it fails
    the moment the docs change.

  Changing the documented install instruction to match what the repo already
  vendors is not the speculative version-range gate R4 forbids; it is removing an
  unbounded claim.
- R6: Alternatively or additionally, have the install audit **warn** — never
  fail — when the installed Trellis version differs from `.trellis/.version`.
  A warning surfaces skew without inventing a compatibility range, so it is
  available before R1's evidence exists.

## Acceptance Criteria

Bounded scope (actionable now):

- [ ] `git grep 'trellis@latest'` returns no live occurrence outside the audit
  ledger and this task's own evidence; the documented version equals
  `.trellis/.version` (or a recorded R4 override justifies the range).
- [ ] `docs/SD_AI_COMMAND_PACK.md` and `templates/docs/SD_AI_COMMAND_PACK.md`
  remain identical, and `make sync` plus generated-parity checks pass. (There is
  no `templates/README.md`; README has no twin.)
- [ ] `tests/install_test_support.py` asserts the new string and passes.
- [ ] If R6 is taken: a fixture with a mismatched installed Trellis version
  produces a warning and a zero exit, and a matching version produces neither.

Full contract (remains parked until R1 has evidence):

- [ ] The triggering incompatibility is linked and described.
- [ ] The pack reports the compatibility issue with clear remediation guidance.
- [ ] Tests cover both compatible and incompatible Trellis versions or fixture
  equivalents.
- [ ] Docs explain the compatibility policy and how users should update Trellis.

## Notes

- Trigger partially fired 2026-07-28, then fully 2026-08-20: see both Trigger
  Status sections. R1 now has its evidence; R2-R5 need the bootstrap decision;
  R6 remains available independently.
- Audit source: `.trellis/audit/report-2026-07-28.md` — finding A-113
  (P3 · S · Plausible · dependencies). Ledger entry A-113 tracks this task as
  its owner.
- Re-evaluated 2026-07-14 against the installed Trellis runtime and canonical
  Trellis 0.6.7 checkout. No pack behavior in that P3 sweep exposed a concrete
  version incompatibility, so a speculative version-range gate remains
  unwarranted. A-113 does not change that conclusion — it is an unbounded
  install instruction, not an observed break.
- The title still reads PARKED because the majority of the task is. Rename it if
  and when R1-R4 become actionable.

## Rescope (2026-08-08)

R5/R6 (pin freshness fix) are live; R1-R4 are parked. Priority set P3.
08-08-trellis-upgrade supersedes the version-drift portion of this task's
motivation; what remains is the compatibility-contract surface only.
