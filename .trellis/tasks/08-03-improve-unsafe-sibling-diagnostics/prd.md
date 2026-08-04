# Improve sibling-loader diagnostic messages (_UnsafeSiblingPath wording)

## Goal

Deferred follow-up from 0.64.3 fleet review (rwbp-coordinator PR #195, Copilot). _UnsafeSiblingPath now conflates missing-helper with unsafe/unsupported load (O_NOFOLLOW-unavailable, symlink, non-regular); 'helper is not installed' / 'missing source validator module' messages are imprecise for the unsafe cases. Also recovery schema-version mismatch error omits expected-vs-actual. Improve wording without weakening the fail-safe behavior. Candidate for 0.64.4.

## Requirements

- TBD

### Additional evidence — 0.64.4 fleet review (rwbp-coordinator PR #198, Copilot)

Copilot flagged that `ENOTDIR` (a non-directory parent path component ⇒ the
module is unresolvable at the computed path) is classified as `non_regular`
("present but refused") rather than `missing`. Both the advisory `lstat` branch
and the authoritative `O_NOFOLLOW`-open branch map `ENOTDIR → non_regular`
(status.py:857/882, surface-check equivalents), and `test_helper_loader_safety.py`
`test_enotdir_parent_maps_to_specific_reason` asserts that parity. Behavior is
unchanged (fail-closed) — this is diagnostic accuracy only. If the next pack
version adopts `ENOTDIR → missing`, change BOTH branches and update that test in
lockstep to preserve advisory/authoritative parity.

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
