# Improve sibling-loader diagnostic messages (_UnsafeSiblingPath wording)

## Goal

Follow-up from fleet review (0.64.3 PR #195 and 0.64.4 PR #198, Copilot).
Scoped for **0.64.5** as child A of `08-04-0-64-5-followup-hardening`. Core work:
map `ENOTDIR → missing` in the unsafe-sibling loader (both branches, both twins)
so an unresolvable-parent path reads as "not found" rather than "present but
refused", with parity-preserving tests. The original "recovery schema-version
mismatch omits expected-vs-actual" concern is VERIFIED ALREADY FIXED
(recovery-artifacts.py:455/459 emits both) and is out of scope.

## Requirements

Child A of `08-04-0-64-5-followup-hardening`. Full design in the parent
`design.md` §A and `implement.md` Phase A.

- Map `ENOTDIR → "missing"` in BOTH the advisory `lstat` branch and the
  authoritative `O_NOFOLLOW`-open branch of `status.py` and `surface-check.py`, in
  `scripts/` AND `templates/scripts/` (byte-identical twins). Preserve
  advisory/authoritative parity; behavior stays fail-closed (diagnostic only).
- Caller wording already reads correctly for `missing` (status.py:935/1337 "not
  installed"; surface-check.py:344 "missing source validator module: {relative}") —
  VERIFY only; the reason-code flip alone yields the right message. No rewrite.
- Diagnostics may keep the repo-relative path (intended); the contract forbids
  only absolute/home paths and credentials.
- Update the advisory parity test to assert `missing` (status + surface), AND add
  an authoritative-branch test (mock `os.lstat` to a regular file so the real
  `os.open(O_NOFOLLOW)` raises ENOTDIR) — the existing test only exercises `lstat`.
- OUT OF SCOPE (verified fixed): recovery schema-mismatch already emits
  expected-vs-actual (`recovery-artifacts.py:459`). fleet-controller loader
  unchanged (no granular reasons).

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

- [ ] `ENOTDIR` yields `missing` in all four twin files, both branches.
- [ ] `scripts/` and `templates/scripts/` twins remain byte-identical.
- [ ] Caller messages verified correct for `missing`; no absolute/home path or
  credential leaked (repo-relative path allowed).
- [ ] Advisory AND authoritative-branch tests assert `missing` (status + surface);
  `ruff check` clean.
- [ ] `.venv/bin/python -m unittest tests.test_helper_loader_safety` green.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
