# Split behavior and content payload digests

## Goal

Stop doc-only edits from invalidating the fleet candidate-validation gate, so a typo fix no longer costs a cross-repo revalidation across eight consumers before fleet refresh.

## Requirements

- `payload_digest` (`scripts/sd_ai_command_pack_fleet_lib.py:663`) must be split into a behavior digest (scripts, config, managed blocks, topology) and an informational content digest.
- `validate_candidate_ledger` (fleet_lib.py:731) must gate on the behavior digest only; a content-digest change records but does not reject.
- `kind: "doc"` sources must not contribute to the behavior digest, **except**
  those on an explicit behavioral-doc allowlist. Only 3 of 754 manifest entries
  are `kind: "doc"`, and one of them —
  `templates/.claude/sd-ai-command-pack/planning-adversarial-review.md` — is a
  contract agents execute, not reference material. See `design.md`.
- The manifest projection must exclude the same set. `payload_digest`
  (`fleet_lib.py:683`) hashes the entire manifest document as well as each
  source, so excluding doc *content* alone leaves a doc entry able to move the
  behavior digest.
- The ledger must still record both digests so a content change remains auditable.

## Acceptance Criteria

- [ ] Editing only a `kind: "doc"` source leaves the behavior digest unchanged and `validate_candidate_ledger` passes without restamping.
- [ ] Editing a shipped script changes the behavior digest and still hard-rejects a stale ledger.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-057 (P2 · M · Plausible · consumer-impact).
- `docs/fleet/candidate-validation.json` was restamped twice in 90 minutes (38502b11, fe69f4dc) for a documentation reword during the v0.56.0 cut.
- Today the digest hashes all 754 sources including `kind: "doc"`.
- Tracked-stale against `07-28-roll-out-stabilized-pack-release-to-fleet`, which consumes the candidate ledger as a precondition without splitting the digest.
- **Premise verified and narrowed 2026-07-28.** Both cited restamps are genuinely
  doc-driven — `38502b11` is titled *"restamp candidate ledger for doc-inclusive
  payload"* and `fe69f4dc` follows the planning-finalization work that edits
  `planning-adversarial-review.md`. But `kind` alone is the wrong discriminator:
  411 of 754 entries are `kind: "skill"`, which is also prose, and in this
  architecture prose is behavior. The split turns on *behavioral vs
  informational*, not on the `kind` field. Design records the allowlist that makes
  that distinction explicit.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
