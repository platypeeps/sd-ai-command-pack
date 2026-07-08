# Enable branch coverage in the install.py gate

## Goal

The CI-enforced "100% coverage" on install.py is line coverage only
(`.coveragerc` has no `branch = True`). A branch-enabled run measures
**99% with 16 partial branches**: 552→554, 848→850, 915→917,
1050→1052, 1108→1110, 1117→1119, 1167→1169, 1193→1195, 1458→1460,
1475→1473, 1621→1623, 1629→1631, 1693→1695, 1760→1772, 1964→1966,
1974→1977. Examples: `system_exit_detail` never sees a detail that
doesn't start with `"error: "` (552); `may_remove_pack_file` never
takes the no-file fall-through to "content differs" (1760→1772); the
remove flow never runs with a non-empty diff-check path list returning
0 (1974→1977). Several partial branches sit in remove mode — the
newest, least-reviewed subsystem (built without a Trellis task,
journal sessions 31-37). The 100% badge currently overstates what is
proven.

## Requirements

- R1: Set `branch = True` in `.coveragerc`, keeping
  `fail_under = 100`.
- R2: Add the ~16 missing branch tests (all cheap unit-level cases);
  prioritize the remove-mode branches.
- R3: CI (both matrix legs) and the documented local verification
  command stay green; update README's Verify section if the command
  output changes shape.
- R4: If any branch is genuinely unreachable, refactor it away rather
  than pragma-excluding it (pragma only with a justifying comment).

## Acceptance Criteria

- [x] `coverage report --fail-under=100` passes with branch coverage
  enabled (417 branches, 0 partial across install.py + installer/*;
  CI matrix validates 3.10 and 3.13). The pre-decomposition estimate
  of 16 partials matched exactly what measurement found; all 16
  directions now have focused tests.
- [x] No unexplained `# pragma: no branch` exclusions — zero pragmas
  added; every partial got a real test.
- [x] Full battery green: 319 tests, full-check exit 0. Shipped as
  PR #57.

## Notes

- Origin: 2026-07-06 deep review (Testing finding 1 MEDIUM; partial
  branch list measured in-session with coverage==7.6.0).
